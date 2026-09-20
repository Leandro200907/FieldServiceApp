"""Alerta de vencimiento — agregado persistente y sus políticas (especificación 4.6,
modelo-dominio 2.3/2.4, flujo 3.4). La función pura vive en `app/core/alertas.py`.

Ciclo (todo lo dispara el reloj `sincronizar`, salvo las acciones humanas):
- abrir al cruzar el primer umbral (`AlertaDeVencimientoAbierta`) y notificar a técnico,
  supervisor y responsable;
- `recordatorio` si no hubo acción registrada (una alerta pausada o reconocida no insiste);
- `vencido`: `DocumentoVencido` → política de revaluación (A-07) + notificación prioritaria
  al supervisor; `escalado` en T+N sin resolución → `AlertaEscalada` al rol configurable;
- acción registrada (carga de documento en cualquier confianza, excepción) → `pausada_por_accion`
  (`AlertaPausada`); sobre `vencido`, la excepción sólo marca `bajo_excepcion`;
- `DocumentoVerificado` que cubre la fuente → `resuelta` (`AlertaResuelta`); la fuente
  reemplazada/anulada también resuelve (motivo distinto, auditable);
- reconocer pausa las notificaciones `reconocimiento_dias`, nunca cierra el ciclo.
Coalescing: por etapa (una notificación por cruce) y por destinatario (un solo job de
`notificaciones` por destinatario y corrida, con todas sus alertas).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.alcance import alcance_de_sujetos, sujeto_en_alcance
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento, registrar_evento_interno
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.core.alertas import ParametrosAlerta, avanza, destinatarios_de, etapa_de
from app.worker.cola import encolar

# --------------------------------------------------------------------------- configuración


def parametros(session: Session, tenant_id: str) -> ParametrosAlerta:
    fila = session.execute(
        text("SELECT plazo_aviso_dias, escalamiento_dias, rol_escalamiento, reconocimiento_dias FROM modulo1.configuracion_alertas WHERE tenant_id = :t"),
        {"t": tenant_id},
    ).mappings().first()
    return ParametrosAlerta(**dict(fila)) if fila else ParametrosAlerta()


def configurar(session: Session, identidad: Identidad, *, plazo_aviso_dias: int, escalamiento_dias: int,
               rol_escalamiento: str, reconocimiento_dias: int) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION)
    t = identidad.tenant_id
    session.execute(
        text(
            "INSERT INTO modulo1.configuracion_alertas (tenant_id, plazo_aviso_dias, escalamiento_dias, rol_escalamiento, reconocimiento_dias, actualizado_por) "
            "VALUES (:t, :p, :n, :r, :k, :u) ON CONFLICT (tenant_id) DO UPDATE SET plazo_aviso_dias = EXCLUDED.plazo_aviso_dias, "
            "escalamiento_dias = EXCLUDED.escalamiento_dias, rol_escalamiento = EXCLUDED.rol_escalamiento, "
            "reconocimiento_dias = EXCLUDED.reconocimiento_dias, actualizado_en = now(), actualizado_por = EXCLUDED.actualizado_por"
        ),
        {"t": t, "p": plazo_aviso_dias, "n": escalamiento_dias, "r": rol_escalamiento, "k": reconocimiento_dias, "u": identidad.usuario_id},
    )
    registrar_evento_interno(session, t, "ConfiguracionDeAlertasActualizada",
                             {"plazo_aviso_dias": plazo_aviso_dias, "escalamiento_dias": escalamiento_dias,
                              "rol_escalamiento": rol_escalamiento, "reconocimiento_dias": reconocimiento_dias}, identidad.usuario_id)
    return {**configuracion(session, identidad), "eventos": ["ConfiguracionDeAlertasActualizada"]}


def configuracion(session: Session, identidad: Identidad) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    p = parametros(session, identidad.tenant_id)
    overrides = [dict(f) for f in session.execute(
        text("SELECT requisito_definicion_id::text, nombre, plazo_aviso_dias FROM modulo1.definicion_requisito "
             "WHERE tenant_id = :t AND plazo_aviso_dias IS NOT NULL AND activa ORDER BY nombre"), {"t": identidad.tenant_id}).mappings()]
    return {"plazo_aviso_dias": p.plazo_aviso_dias, "escalamiento_dias": p.escalamiento_dias, "rol_escalamiento": p.rol_escalamiento,
            "reconocimiento_dias": p.reconocimiento_dias, "plazos_por_requisito": overrides}


# --------------------------------------------------------------------------- fuentes


_SQL_FUENTES = """
SELECT 'documento' AS fuente_tipo, d.documento_id AS fuente_id, d.sujeto_id, l.tipo_sujeto, d.requisito_definicion_id, d.vigente_hasta,
       r.plazo_aviso_dias
FROM modulo1.documento d
JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
JOIN modulo1.definicion_requisito r ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
WHERE d.tenant_id = :t AND d.estado_version = 'vigente' AND d.requisito_definicion_id IS NOT NULL AND l.dado_de_baja_en IS NULL
UNION ALL
SELECT 'acreditacion_competencia', a.acreditacion_id, a.persona_id, 'persona', a.requisito_definicion_id, a.vigente_hasta, r.plazo_aviso_dias
FROM modulo1.acreditacion_competencia a
JOIN modulo1.legajo l ON l.tenant_id = a.tenant_id AND l.sujeto_id = a.persona_id
JOIN modulo1.definicion_requisito r ON r.tenant_id = a.tenant_id AND r.requisito_definicion_id = a.requisito_definicion_id
WHERE a.tenant_id = :t AND l.dado_de_baja_en IS NULL
UNION ALL
SELECT 'induccion', i.induccion_id, i.persona_id, 'persona', i.requisito_definicion_id, i.vigente_hasta, r.plazo_aviso_dias
FROM modulo1.induccion i
JOIN modulo1.legajo l ON l.tenant_id = i.tenant_id AND l.sujeto_id = i.persona_id
JOIN modulo1.definicion_requisito r ON r.tenant_id = i.tenant_id AND r.requisito_definicion_id = i.requisito_definicion_id
WHERE i.tenant_id = :t AND l.dado_de_baja_en IS NULL
UNION ALL
SELECT 'constancia_del_cliente', c.constancia_id, c.sujeto_id, l.tipo_sujeto, c.requisito_definicion_id, c.vigencia, r.plazo_aviso_dias
FROM modulo1.constancia_cliente c
JOIN modulo1.legajo l ON l.tenant_id = c.tenant_id AND l.sujeto_id = c.sujeto_id
JOIN modulo1.definicion_requisito r ON r.tenant_id = c.tenant_id AND r.requisito_definicion_id = c.requisito_definicion_id
WHERE c.tenant_id = :t AND c.estado = 'vigente' AND c.vigencia IS NOT NULL AND l.dado_de_baja_en IS NULL
"""


def _con_plazo(p: ParametrosAlerta, plazo_requisito: int | None) -> ParametrosAlerta:
    return p if plazo_requisito is None else ParametrosAlerta(plazo_requisito, p.escalamiento_dias, p.rol_escalamiento, p.reconocimiento_dias)


# --------------------------------------------------------------------------- destinatarios


def _usuarios_por_rol(session: Session, tenant_id: str, rol: str) -> list[str]:
    return [str(u) for u in session.execute(
        text("SELECT usuario_id FROM modulo1.usuario WHERE tenant_id = :t AND activo AND :r = ANY(roles) ORDER BY usuario_id"),
        {"t": tenant_id, "r": rol}).scalars()]


def _persona_responsable(session: Session, tenant_id: str, sujeto_id: str, tipo_sujeto: str) -> str | None:
    """La persona detrás de la alerta: el propio sujeto si es persona; el custodio vigente
    si es vehículo/equipo; nadie para la empresa."""
    if tipo_sujeto == "persona":
        return sujeto_id
    if tipo_sujeto in ("vehiculo", "equipo"):
        return session.execute(text(
            "SELECT p.custodio_id FROM modulo1.periodo_custodia p JOIN modulo1.custodia_recurso c ON c.tenant_id = p.tenant_id AND c.custodia_id = p.custodia_id "
            "WHERE p.tenant_id = :t AND c.recurso_id = :r AND p.estado = 'vigente'"), {"t": tenant_id, "r": sujeto_id}).scalar()
    return None


def _destinatarios(session: Session, tenant_id: str, alerta: dict[str, Any], roles: list[str], hoy: date) -> list[tuple[str, str | None]]:
    """[(rol, usuario_id|None)]: técnico y supervisor resueltos a un usuario concreto; los
    roles administrativos van como broadcast (usuario NULL) para no fijar una persona."""
    salida: list[tuple[str, str | None]] = []
    persona = _persona_responsable(session, tenant_id, alerta["sujeto_id"], alerta["tipo_sujeto"])
    for rol in roles:
        if rol == "tecnico":
            if persona:
                u = session.execute(text("SELECT usuario_id FROM modulo1.usuario WHERE tenant_id = :t AND sujeto_id = :s AND activo AND 'tecnico' = ANY(roles)"),
                                    {"t": tenant_id, "s": persona}).scalar()
                if u:
                    salida.append(("tecnico", str(u)))
        elif rol == "supervisor":
            if persona:
                u = session.execute(text("SELECT supervisor_usuario_id FROM modulo1.asignacion_supervisor WHERE tenant_id = :t AND sujeto_id = :s "
                                         "AND estado = 'vigente' AND desde <= :hoy"), {"t": tenant_id, "s": persona, "hoy": hoy}).scalar()
                if u:
                    salida.append(("supervisor", str(u)))
                    continue
            salida.append(("supervisor", None))  # sin supervisor asignado: broadcast al rol
        else:
            salida.append((rol, None))
    return salida


def _notificar_etapa(session: Session, tenant_id: str, alerta: dict[str, Any], etapa: str, p: ParametrosAlerta, hoy: date) -> list[str]:
    roles, prioridad = destinatarios_de(etapa, p)
    for rol, usuario in _destinatarios(session, tenant_id, alerta, roles, hoy):
        session.execute(
            text("INSERT INTO modulo1.alerta_notificacion (tenant_id, alerta_id, etapa, prioridad, destinatario_rol, destinatario_usuario_id, fecha) "
                 "VALUES (:t, :a, :e, :p, :r, :u, :f)"),
            {"t": tenant_id, "a": str(alerta["alerta_id"]), "e": etapa, "p": prioridad, "r": rol, "u": usuario, "f": hoy},
        )
    return roles


# --------------------------------------------------------------------------- reloj


def _resolver(session: Session, tenant_id: str, alerta_id: str, motivo: str, ref: str | None, ahora: datetime) -> None:
    session.execute(
        text("UPDATE modulo1.alerta_vencimiento SET estado = 'resuelta', resuelta_en = :ahora, resuelta_motivo = :m, resuelta_ref = :ref, actualizado_en = now() "
             "WHERE tenant_id = :t AND alerta_id = :a AND estado <> 'resuelta'"),
        {"t": tenant_id, "a": alerta_id, "m": motivo, "ref": ref, "ahora": ahora},
    )
    registrar_evento_interno(session, tenant_id, "AlertaResuelta", {"alerta_id": alerta_id, "resuelta_en": ahora, "motivo": motivo, "ref": ref}, None)


def sincronizar(session: Session, tenant_id: str, ahora: datetime) -> dict[str, int]:
    """Una corrida del control de vencimientos para un tenant: abre, avanza etapas,
    resuelve fuentes desaparecidas y deja las notificaciones pendientes (sin entregarlas)."""
    hoy = hoy_del_tenant(session, tenant_id, ahora)
    p_tenant = parametros(session, tenant_id)
    r = {"revisadas": 0, "abiertas": 0, "avanzadas": 0, "resueltas_sin_fuente": 0, "vencidas": 0, "escaladas": 0}

    fuentes = {(f["fuente_tipo"], str(f["fuente_id"])): dict(f) for f in session.execute(text(_SQL_FUENTES), {"t": tenant_id}).mappings()}
    abiertas = {(a["fuente_tipo"], str(a["fuente_id"])): dict(a) for a in session.execute(
        text("SELECT * FROM modulo1.alerta_vencimiento WHERE tenant_id = :t AND estado <> 'resuelta' FOR UPDATE"), {"t": tenant_id}).mappings()}

    # 1) alertas cuya fuente dejó de ser la vigente. Si la sucedió una versión NO verificada
    #    (propuesta, lote declarado), la alerta sigue viva sobre la fecha original: lo
    #    declarado no prueba nada (1.10) y el ciclo debe llegar a `vencido` si no se
    #    verifica. Si no queda ninguna versión vigente (anulada, revertida, legajo de
    #    baja) → resuelta con motivo auditable. La verificada la resuelve el hook.
    for clave, a in list(abiertas.items()):
        if clave in fuentes:
            continue
        sucesora_declarada = a["fuente_tipo"] == "documento" and session.execute(text(
            "SELECT 1 FROM modulo1.documento d JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id "
            "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.requisito_definicion_id = :r AND d.estado_version = 'vigente' "
            "AND d.estado_confirmacion = 'declarado' AND l.dado_de_baja_en IS NULL"),
            {"t": tenant_id, "s": a["sujeto_id"], "r": str(a["requisito_definicion_id"])}).first() is not None
        if sucesora_declarada:
            fuentes[clave] = {"fuente_tipo": a["fuente_tipo"], "fuente_id": a["fuente_id"], "sujeto_id": a["sujeto_id"], "tipo_sujeto": a["tipo_sujeto"],
                              "requisito_definicion_id": a["requisito_definicion_id"], "vigente_hasta": a["vigente_hasta"], "plazo_aviso_dias": None}
            continue
        _resolver(session, tenant_id, str(a["alerta_id"]), "fuente_reemplazada_o_anulada", None, ahora)
        abiertas.pop(clave)
        r["resueltas_sin_fuente"] += 1

    # 2) abrir / avanzar
    for clave, f in fuentes.items():
        r["revisadas"] += 1
        p = _con_plazo(p_tenant, f["plazo_aviso_dias"])
        etapa = etapa_de(f["vigente_hasta"], hoy, p)
        a = abiertas.get(clave)
        if a is None:
            if etapa is None:
                continue
            alerta_id = str(uuid.uuid4())
            session.execute(
                text("INSERT INTO modulo1.alerta_vencimiento (alerta_id, tenant_id, fuente_tipo, fuente_id, sujeto_id, tipo_sujeto, requisito_definicion_id, "
                     "vigente_hasta, etapa, estado, abierta_en, etapa_desde, escalada_en) VALUES (:a, :t, :ft, :fi, :s, :ts, :r, :vh, :e, 'abierta', :hoy, :hoy, "
                     "CASE WHEN :e = 'escalado' THEN :hoy END)"),
                {"a": alerta_id, "t": tenant_id, "ft": f["fuente_tipo"], "fi": str(f["fuente_id"]), "s": f["sujeto_id"], "ts": f["tipo_sujeto"],
                 "r": str(f["requisito_definicion_id"]), "vh": f["vigente_hasta"], "e": etapa, "hoy": hoy},
            )
            a = {"alerta_id": alerta_id, "sujeto_id": f["sujeto_id"], "tipo_sujeto": f["tipo_sujeto"]}
            payload = {"alerta_id": alerta_id, "fuente_tipo": f["fuente_tipo"], "fuente_id": str(f["fuente_id"]), "documento_id": str(f["fuente_id"]),
                       "sujeto_id": f["sujeto_id"], "tipo_sujeto": f["tipo_sujeto"], "requisito_definicion_id": str(f["requisito_definicion_id"]),
                       "vigente_hasta": f["vigente_hasta"].isoformat(), "etapa": etapa, "dias_restantes": (f["vigente_hasta"] - hoy).days}
            registrar_evento_interno(session, tenant_id, "AlertaDeVencimientoAbierta", payload, None)
            roles = _notificar_etapa(session, tenant_id, a, etapa, p, hoy)
            session.execute(text("UPDATE modulo1.alerta_vencimiento SET destinatarios_notificados_en_esta_etapa = :d WHERE tenant_id = :t AND alerta_id = :a"),
                            {"d": roles, "t": tenant_id, "a": alerta_id})
            r["abiertas"] += 1
            if etapa in ("vencido", "escalado"):
                _al_vencer(session, tenant_id, f, alerta_id, hoy)
                r["vencidas"] += 1
            if etapa == "escalado":
                _al_escalar(session, tenant_id, alerta_id, hoy)
                r["escaladas"] += 1
            continue

        if not avanza(a["etapa"], etapa):
            continue
        # cruza un umbral: la etapa avanza siempre; si estaba pausada y llega T sin verificación → vuelve a abierta(vencido)
        etapa_previa = a["etapa"]
        pausada = a["estado"] == "pausada_por_accion"
        session.execute(
            text("UPDATE modulo1.alerta_vencimiento SET etapa = :e, etapa_desde = :hoy, destinatarios_notificados_en_esta_etapa = '{}', "
                 "estado = CASE WHEN :e IN ('vencido', 'escalado') THEN 'abierta' ELSE estado END, "
                 "escalada_en = CASE WHEN :e = 'escalado' THEN :hoy ELSE escalada_en END, actualizado_en = now() "
                 "WHERE tenant_id = :t AND alerta_id = :a"),
            {"e": etapa, "hoy": hoy, "t": tenant_id, "a": str(a["alerta_id"])},
        )
        r["avanzadas"] += 1
        silenciada = a["reconocida_hasta"] is not None and a["reconocida_hasta"] >= hoy
        if etapa == "recordatorio" and (pausada or silenciada):
            continue  # recordatorio solo "si no hubo acción registrada"
        roles = _notificar_etapa(session, tenant_id, a, etapa, p, hoy)
        session.execute(text("UPDATE modulo1.alerta_vencimiento SET destinatarios_notificados_en_esta_etapa = :d WHERE tenant_id = :t AND alerta_id = :a"),
                        {"d": roles, "t": tenant_id, "a": str(a["alerta_id"])})
        if etapa in ("vencido", "escalado") and etapa_previa in ("aviso", "recordatorio"):
            _al_vencer(session, tenant_id, f, str(a["alerta_id"]), hoy)
            r["vencidas"] += 1
        if etapa == "escalado":
            _al_escalar(session, tenant_id, str(a["alerta_id"]), hoy)
            r["escaladas"] += 1
    return r


def _al_vencer(session: Session, tenant_id: str, f: dict[str, Any], alerta_id: str, hoy: date) -> None:
    """DocumentoVencido: cambio de entrada del snapshot → política de revaluación (A-07);
    la empresa la trata `registrar_vencimientos_de_empresa` (2.9) en el mismo reloj."""
    registrar_evento(
        session, tenant_id, "DocumentoVencido",
        {"alerta_id": alerta_id, "fuente_tipo": f["fuente_tipo"], "fuente_id": str(f["fuente_id"]), "documento_id": str(f["fuente_id"]),
         "sujeto_id": f["sujeto_id"], "tipo_sujeto": f["tipo_sujeto"], "requisito_definicion_id": str(f["requisito_definicion_id"]),
         "vigente_hasta": f["vigente_hasta"].isoformat(), "vencido_en": hoy.isoformat()},
        None,
    )


def _al_escalar(session: Session, tenant_id: str, alerta_id: str, hoy: date) -> None:
    registrar_evento_interno(session, tenant_id, "AlertaEscalada", {"alerta_id": alerta_id, "escalada_en": hoy.isoformat()}, None)


def entregar_notificaciones(session: Session, tenant_id: str, ahora: datetime) -> dict[str, int]:
    """Coalescing por destinatario: todas las notificaciones pendientes de un mismo
    destinatario salen en UN job de `notificaciones` con la lista de alertas."""
    pendientes = session.execute(
        text("SELECT n.notificacion_id, n.alerta_id, n.etapa, n.prioridad, n.destinatario_rol, n.destinatario_usuario_id, n.fecha, "
             "a.sujeto_id, a.tipo_sujeto, a.requisito_definicion_id, a.vigente_hasta, a.fuente_tipo, a.bajo_excepcion, d.nombre AS requisito "
             "FROM modulo1.alerta_notificacion n JOIN modulo1.alerta_vencimiento a ON a.tenant_id = n.tenant_id AND a.alerta_id = n.alerta_id "
             "JOIN modulo1.definicion_requisito d ON d.tenant_id = a.tenant_id AND d.requisito_definicion_id = a.requisito_definicion_id "
             "WHERE n.tenant_id = :t AND n.entregada_en IS NULL ORDER BY n.destinatario_rol, n.destinatario_usuario_id, a.vigente_hasta FOR UPDATE OF n SKIP LOCKED"),
        {"t": tenant_id},
    ).mappings().all()
    grupos: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for n in pendientes:
        grupos.setdefault((n["destinatario_rol"], str(n["destinatario_usuario_id"]) if n["destinatario_usuario_id"] else None), []).append(dict(n))
    for (rol, usuario), items in grupos.items():
        job_id = encolar(session, "notificaciones", {
            "tipo": "AlertasDeVencimiento", "destinatario_rol": rol, "destinatario_usuario_id": usuario,
            "prioridad": "alta" if any(i["prioridad"] == "alta" for i in items) else "normal",
            "alertas": [{"alerta_id": str(i["alerta_id"]), "etapa": i["etapa"], "sujeto_id": i["sujeto_id"], "tipo_sujeto": i["tipo_sujeto"],
                         "requisito": i["requisito"], "vigente_hasta": i["vigente_hasta"].isoformat(), "fuente_tipo": i["fuente_tipo"],
                         "bajo_excepcion": i["bajo_excepcion"]} for i in items],
        }, tenant_id=tenant_id)
        session.execute(text("UPDATE modulo1.alerta_notificacion SET entregada_en = :ahora, job_id = :j WHERE tenant_id = :t AND notificacion_id = ANY(:ids)"),
                        {"ahora": ahora, "j": job_id, "t": tenant_id, "ids": [i["notificacion_id"] for i in items]})
        registrar_evento_interno(session, tenant_id, "NotificacionEmitida",
                                 {"destinatario_rol": rol, "destinatario_usuario_id": usuario, "alertas": len(items), "job_id": job_id}, None)
    return {"notificaciones": len(pendientes), "mensajes": len(grupos)}


def avisar_oc_sin_matriz(session: Session, tenant_id: str, ahora: datetime) -> dict[str, int]:
    """Flujo 3.6 / 2.5: OC activa cuya clave (cliente, locación, tipo de servicio) no tiene
    matriz vigente hoy → `OcSinMatriz` + notificación a configuración, una vez por OC."""
    hoy = hoy_del_tenant(session, tenant_id, ahora)
    filas = session.execute(text(
        "SELECT o.oc_id, o.clave_origen, o.cliente_id, o.locacion_id, o.tipo_servicio_id FROM modulo1.oc o "
        "WHERE o.tenant_id = :t AND o.estado = 'activo' AND NOT EXISTS (SELECT 1 FROM modulo1.matriz_requisitos m "
        "  WHERE m.tenant_id = o.tenant_id AND m.cliente_id = o.cliente_id AND m.locacion_id = o.locacion_id AND m.tipo_servicio_id = o.tipo_servicio_id "
        "  AND m.vigente_desde <= :hoy AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= :hoy)) "
        "AND NOT EXISTS (SELECT 1 FROM modulo1.aviso_oc_sin_matriz s WHERE s.tenant_id = o.tenant_id AND s.oc_id = o.oc_id)"),
        {"t": tenant_id, "hoy": hoy}).mappings().all()
    for f in filas:
        payload = {"oc_id": str(f["oc_id"]), "clave_origen": f["clave_origen"], "cliente_id": str(f["cliente_id"]), "locacion_id": str(f["locacion_id"]),
                   "tipo_servicio_id": str(f["tipo_servicio_id"]), "fecha": hoy.isoformat()}
        evento_id = registrar_evento_interno(session, tenant_id, "OcSinMatriz", payload, None)
        session.execute(text("INSERT INTO modulo1.aviso_oc_sin_matriz (tenant_id, oc_id, notificado_en, evento_id) VALUES (:t, :o, :ahora, :e) ON CONFLICT DO NOTHING"),
                        {"t": tenant_id, "o": str(f["oc_id"]), "ahora": ahora, "e": evento_id})
        encolar(session, "notificaciones", {"tipo": "OcSinMatriz", "destinatario_rol": "configuracion", **payload}, tenant_id=tenant_id)
    return {"oc_sin_matriz": len(filas)}


# --------------------------------------------------------------------------- acciones humanas (hooks)


def registrar_accion(session: Session, tenant_id: str, sujeto_id: str, requisito_definicion_id: str, tipo: str, ref: str, ahora: datetime | None = None) -> int:
    """Carga de documento (cualquier confianza) o excepción sobre el requisito de una alerta
    abierta → pausa la cadena de recordatorios. Sobre `vencido`, la excepción no pausa:
    marca `bajo_excepcion` (evita el bloqueo operativo, no resuelve)."""
    instante = ahora or ahora_utc()
    filas = session.execute(
        text("SELECT alerta_id, etapa, estado FROM modulo1.alerta_vencimiento WHERE tenant_id = :t AND sujeto_id = :s "
             "AND requisito_definicion_id = :r AND estado <> 'resuelta' FOR UPDATE"),
        {"t": tenant_id, "s": sujeto_id, "r": requisito_definicion_id},
    ).mappings().all()
    for a in filas:
        if tipo == "excepcion" and a["etapa"] in ("vencido", "escalado"):
            session.execute(text("UPDATE modulo1.alerta_vencimiento SET bajo_excepcion = true, ultima_accion_tipo = :tipo, ultima_accion_en = :ahora, "
                                 "ultima_accion_ref = :ref, actualizado_en = now() WHERE tenant_id = :t AND alerta_id = :a"),
                            {"tipo": tipo, "ahora": instante, "ref": ref, "t": tenant_id, "a": str(a["alerta_id"])})
            continue
        session.execute(text("UPDATE modulo1.alerta_vencimiento SET estado = 'pausada_por_accion', ultima_accion_tipo = :tipo, ultima_accion_en = :ahora, "
                             "ultima_accion_ref = :ref, actualizado_en = now() WHERE tenant_id = :t AND alerta_id = :a"),
                        {"tipo": tipo, "ahora": instante, "ref": ref, "t": tenant_id, "a": str(a["alerta_id"])})
        if a["estado"] != "pausada_por_accion":
            registrar_evento_interno(session, tenant_id, "AlertaPausada", {"alerta_id": str(a["alerta_id"]), "pausada_en": instante, "accion": tipo, "ref": ref}, None)
    return len(filas)


def resolver_por_verificacion(session: Session, tenant_id: str, sujeto_id: str, requisito_definicion_id: str, fuente_id: str,
                              vigente_hasta: date | None, ahora: datetime | None = None) -> int:
    """`DocumentoVerificado` que cubre el requisito: resuelve las alertas de ese (sujeto,
    requisito) cuya fuente es otra (la versión renovada) y cuya fecha queda superada."""
    instante = ahora or ahora_utc()
    hoy = hoy_del_tenant(session, tenant_id, instante)
    if vigente_hasta is not None and vigente_hasta < hoy:
        return 0  # verificar algo ya vencido no cubre nada
    filas = session.execute(
        text("SELECT alerta_id FROM modulo1.alerta_vencimiento WHERE tenant_id = :t AND sujeto_id = :s AND requisito_definicion_id = :r "
             "AND estado <> 'resuelta' AND fuente_id <> CAST(:f AS uuid) AND (:vh IS NULL OR vigente_hasta < CAST(:vh AS date)) FOR UPDATE"),
        {"t": tenant_id, "s": sujeto_id, "r": requisito_definicion_id, "f": fuente_id, "vh": vigente_hasta},
    ).scalars().all()
    for alerta_id in filas:
        _resolver(session, tenant_id, str(alerta_id), "verificacion", fuente_id, instante)
    return len(filas)


def reconocer(session: Session, identidad: Identidad, *, alerta_id: str, comentario: str | None = None) -> dict[str, Any]:
    """Reconocer pausa las notificaciones `reconocimiento_dias`; NO cierra el ciclo (2.4)."""
    identidad.exigir_rol(Rol.SUPERVISOR, Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    a = session.execute(text("SELECT alerta_id, sujeto_id, estado FROM modulo1.alerta_vencimiento WHERE tenant_id = :t AND alerta_id = :a FOR UPDATE"),
                        {"t": t, "a": alerta_id}).mappings().first()
    hoy = hoy_del_tenant(session, t)
    if a is None or not sujeto_en_alcance(session, identidad, a["sujeto_id"], hoy):
        raise NoEncontrado("Alerta inexistente", {"alerta_id": alerta_id})
    if a["estado"] == "resuelta":
        raise Conflicto("La alerta ya está resuelta", {"alerta_id": alerta_id})
    p = parametros(session, t)
    hasta = hoy + timedelta(days=p.reconocimiento_dias)
    session.execute(text("UPDATE modulo1.alerta_vencimiento SET reconocida_hasta = :h, ultima_accion_tipo = 'reconocimiento', ultima_accion_en = now(), "
                         "ultima_accion_ref = :u, actualizado_en = now() WHERE tenant_id = :t AND alerta_id = :a"),
                    {"h": hasta, "u": identidad.usuario_id, "t": t, "a": alerta_id})
    registrar_evento_interno(session, t, "AlertaDeVencimientoReconocida", {"alerta_id": alerta_id, "reconocida_hasta": hasta.isoformat(), "comentario": comentario}, identidad.usuario_id)
    return {"alerta_id": alerta_id, "reconocida_hasta": hasta.isoformat(), "eventos": ["AlertaDeVencimientoReconocida"]}


# --------------------------------------------------------------------------- read models


_SQL_ALERTA = """
SELECT a.alerta_id::text, a.fuente_tipo, a.fuente_id::text, a.sujeto_id, a.tipo_sujeto, a.requisito_definicion_id::text, d.nombre AS requisito,
       a.vigente_hasta, a.etapa, a.estado, a.bajo_excepcion, a.ultima_accion_tipo, a.ultima_accion_en, a.ultima_accion_ref, a.reconocida_hasta,
       a.destinatarios_notificados_en_esta_etapa, a.abierta_en, a.etapa_desde, a.escalada_en, a.resuelta_en, a.resuelta_motivo, a.resuelta_ref
FROM modulo1.alerta_vencimiento a
JOIN modulo1.definicion_requisito d ON d.tenant_id = a.tenant_id AND d.requisito_definicion_id = a.requisito_definicion_id
WHERE a.tenant_id = :t
"""


def _filtro_alcance(alcance: list[str] | None, params: dict[str, Any]) -> str:
    if alcance is None:
        return ""
    params["alcance"] = alcance
    return " AND a.sujeto_id = ANY(CAST(:alcance AS text[]))"


def alertas_abiertas(session: Session, identidad: Identidad, p: Pagina, sujeto_id: str | None = None, etapa: str | None = None) -> dict[str, Any]:
    """Tablero: alertas no resueltas, por sujeto y etapa; alcance por rol (2.3 de no-funcionales)."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO, Rol.CONFIGURACION)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = " AND a.estado <> 'resuelta'" + _filtro_alcance(alcance_de_sujetos(session, identidad, hoy), params)
    if sujeto_id:
        cond += " AND a.sujeto_id = :s"
        params["s"] = sujeto_id
    if etapa:
        cond += " AND a.etapa = :e"
        params["e"] = etapa
    total = session.execute(text(f"SELECT count(*) FROM ({_SQL_ALERTA}{cond}) x"), params).scalar()
    filas = session.execute(text(f"{_SQL_ALERTA}{cond} ORDER BY a.vigente_hasta, a.sujeto_id OFFSET :off LIMIT :lim"),
                            {**params, "off": p.offset, "lim": p.limit}).mappings().all()
    salida = envolver([dict(f) for f in filas], int(total or 0), p)
    salida["hoy"] = hoy.isoformat()
    salida["por_etapa"] = dict(session.execute(text(f"SELECT a.etapa, count(*) FROM ({_SQL_ALERTA}{cond}) a GROUP BY a.etapa"), params).all())
    return salida


def historial_alertas(session: Session, identidad: Identidad, p: Pagina, sujeto_id: str | None = None) -> dict[str, Any]:
    """Auditoría: todas las alertas (incluidas las resueltas y por qué) con sus eventos."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.CONFIGURACION)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = _filtro_alcance(alcance_de_sujetos(session, identidad, hoy), params)
    if sujeto_id:
        cond += " AND a.sujeto_id = :s"
        params["s"] = sujeto_id
    total = session.execute(text(f"SELECT count(*) FROM ({_SQL_ALERTA}{cond}) x"), params).scalar()
    filas = [dict(f) for f in session.execute(text(f"{_SQL_ALERTA}{cond} ORDER BY a.creado_en DESC OFFSET :off LIMIT :lim"),
                                              {**params, "off": p.offset, "lim": p.limit}).mappings()]
    ids = [f["alerta_id"] for f in filas]
    eventos: dict[str, list[dict[str, Any]]] = {i: [] for i in ids}
    if ids:
        for ev in session.execute(text("SELECT tipo, payload, ocurrido_en AS creado_en FROM modulo1.event_log WHERE tenant_id = :t AND payload->>'alerta_id' = ANY(:ids) "
                                       "AND tipo IN ('AlertaDeVencimientoAbierta','AlertaPausada','AlertaResuelta','AlertaEscalada','AlertaDeVencimientoReconocida','DocumentoVencido') "
                                       "ORDER BY ocurrido_en, id"), {"t": identidad.tenant_id, "ids": ids}).mappings():
            eventos[ev["payload"]["alerta_id"]].append({"tipo": ev["tipo"], "en": ev["creado_en"], **{k: v for k, v in ev["payload"].items() if k != "alerta_id"}})
    for f in filas:
        f["eventos"] = eventos[f["alerta_id"]]
    return envolver(filas, int(total or 0), p)
