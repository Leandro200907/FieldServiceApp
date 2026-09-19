"""Consultas de Módulo 1 (GET /v1/consultas/*): solo lectura, SQL explícito, alcance por
rol resuelto en `app.auth.alcance`. "Hoy" siempre es `hoy_del_tenant` (regla dura 2) y
`vigente_hasta` es inclusive en todos los cálculos.

`cobertura_oc` es el barrido en MODO CONSULTA (`app.core.orquestacion.cobertura_de_oc`):
nunca persiste. Las decisiones persistidas se leen con `decisiones_oc` / `decision`,
filtradas por visibilidad (A-04).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.auth.alcance import alcance_de_sujetos, filtro_decisiones_visibles
from app.core.orquestacion import cobertura_de_oc


# --------------------------------------------------------------------- utilidades


def _plano(fila: Any) -> dict[str, Any]:
    """Row mapping → dict serializable (uuid y fechas a str; jsonb queda como viene)."""
    salida: dict[str, Any] = {}
    for clave, valor in dict(fila).items():
        if isinstance(valor, uuid.UUID):
            salida[clave] = str(valor)
        elif isinstance(valor, (date, datetime)):
            salida[clave] = valor.isoformat()
        else:
            salida[clave] = valor
    return salida


def _con_vigencia(fila: dict[str, Any], hoy: date) -> dict[str, Any]:
    """Agrega `vigente_hoy` (inclusive en ambos bordes) y `dias_para_vencer` (negativo si
    ya venció). `fila` trae las fechas crudas (date), no serializadas."""
    desde: date = fila["vigente_desde"]
    hasta: date = fila["vigente_hasta"]
    salida = _plano(fila)
    salida["vigente_hoy"] = desde <= hoy <= hasta
    salida["dias_para_vencer"] = (hasta - hoy).days
    salida["vencido"] = hasta < hoy
    return salida


# Evidencia vigente unificada: documentos (solo versión vigente), acreditaciones e
# inducciones — las tres con la misma forma para legajo y tablero.
_SQL_EVIDENCIA = """
    WITH evidencia AS (
        SELECT 'documento' AS tipo, d.documento_id AS id, d.sujeto_id, d.requisito_definicion_id,
               r.nombre AS requisito, r.categoria, d.vigente_desde, d.vigente_hasta,
               d.estado_confirmacion, d.origen_propuesta, NULL::uuid AS locacion_id
        FROM modulo1.documento d
        LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = d.requisito_definicion_id
        WHERE d.estado_version = 'vigente'
        UNION ALL
        SELECT 'acreditacion', a.acreditacion_id, a.persona_id, a.requisito_definicion_id,
               r.nombre, r.categoria, a.vigente_desde, a.vigente_hasta,
               a.estado_confirmacion, false, NULL::uuid
        FROM modulo1.acreditacion_competencia a
        LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = a.requisito_definicion_id
        UNION ALL
        SELECT 'induccion', i.induccion_id, i.persona_id, i.requisito_definicion_id,
               r.nombre, r.categoria, i.vigente_desde, i.vigente_hasta,
               i.estado_confirmacion, false, i.locacion_id
        FROM modulo1.induccion i
        LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = i.requisito_definicion_id
    )
"""


def _filtro_alcance(alcance: list[str] | None, params: dict[str, Any]) -> str:
    if alcance is None:
        return ""
    params["alcance"] = list(alcance)
    return " AND sujeto_id = ANY(CAST(:alcance AS text[]))"


# --------------------------------------------------------------------- consultas


def legajo(session: Session, identidad: Identidad, sujeto_id: str) -> dict[str, Any]:
    """Estado del legajo de un sujeto. Técnico: solo el propio; supervisor: su universo;
    responsable_legajos / configuracion: todo el tenant."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION, Rol.SUPERVISOR, Rol.TECNICO)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    if alcance is not None and sujeto_id not in alcance:
        raise Prohibido("El sujeto está fuera del alcance del usuario", {"sujeto_id": sujeto_id})

    datos = session.execute(
        text(
            "SELECT legajo_id, sujeto_id, tipo_sujeto, identificador_natural, dado_de_baja_en, creado_en "
            "FROM modulo1.legajo WHERE sujeto_id = :s"
        ),
        {"s": sujeto_id},
    ).mappings().first()
    if datos is None:
        raise NoEncontrado("Legajo inexistente", {"sujeto_id": sujeto_id})

    filas = session.execute(
        text(_SQL_EVIDENCIA + " SELECT * FROM evidencia WHERE sujeto_id = :s ORDER BY vigente_hasta, tipo, requisito"),
        {"s": sujeto_id},
    ).mappings().all()
    items = [_con_vigencia(dict(f), hoy) for f in filas]
    return {
        "hoy": hoy.isoformat(),
        "legajo": _plano(datos),
        "documentos": [i for i in items if i["tipo"] == "documento"],
        "acreditaciones": [i for i in items if i["tipo"] == "acreditacion"],
        "inducciones": [i for i in items if i["tipo"] == "induccion"],
        "resumen": {
            "total": len(items),
            "vigentes_hoy": sum(1 for i in items if i["vigente_hoy"]),
            "vencidos": sum(1 for i in items if i["vencido"]),
        },
    }


def propuestas_pendientes(session: Session, identidad: Identidad, p: Pagina) -> dict[str, Any]:
    """Documentos propuestos por técnicos que esperan Confirmar/Rechazar."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    condicion = "WHERE d.origen_propuesta = true AND d.estado_confirmacion = 'declarado' AND d.estado_version = 'vigente'"
    total = session.execute(text(f"SELECT count(*) FROM modulo1.documento d {condicion}")).scalar()
    filas = session.execute(
        text(
            "SELECT d.documento_id, d.sujeto_id, d.requisito_definicion_id, r.nombre AS requisito, d.numero, "
            "d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.origen, d.confianza_extraccion, d.creado_en "
            "FROM modulo1.documento d "
            "LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = d.requisito_definicion_id "
            f"{condicion} ORDER BY d.creado_en, d.documento_id OFFSET :off LIMIT :lim"
        ),
        {"off": p.offset, "lim": p.limit},
    ).mappings().all()
    return envolver([_con_vigencia(dict(f), hoy) for f in filas], int(total or 0), p)


def tablero_vencimientos(session: Session, identidad: Identidad, dias: int, p: Pagina) -> dict[str, Any]:
    """Evidencia vigente que vence dentro de `dias` (inclusive) o ya venció, ordenada por
    `vigente_hasta`. responsable_legajos: toda la empresa; supervisor: su universo."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    if dias < 0:
        raise ErrorDeDominio("dias debe ser >= 0", {"dias": dias})
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    params: dict[str, Any] = {"limite": hoy + timedelta(days=dias)}
    condicion = "WHERE vigente_hasta <= :limite" + _filtro_alcance(alcance, params)
    total = session.execute(text(_SQL_EVIDENCIA + f" SELECT count(*) FROM evidencia {condicion}"), params).scalar()
    filas = session.execute(
        text(_SQL_EVIDENCIA + f" SELECT * FROM evidencia {condicion} ORDER BY vigente_hasta, sujeto_id, tipo OFFSET :off LIMIT :lim"),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    salida = envolver([_con_vigencia(dict(f), hoy) for f in filas], int(total or 0), p)
    salida["hoy"] = hoy.isoformat()
    salida["hasta"] = params["limite"].isoformat()
    return salida


def backlog_oc(session: Session, identidad: Identidad, estado: str | None, p: Pagina) -> dict[str, Any]:
    """OCs (por defecto las activas) con su ÚLTIMA decisión global. Para el supervisor,
    esa última decisión se devuelve solo si todos sus sujetos propuestos están en su
    universo (2.3 §3); si no, `ultima_decision` es null — nunca se sustituye por una
    decisión anterior visible, porque se presentaría como "última" algo que no lo es.
    La cobertura en vivo se pide aparte con `cobertura_oc`."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    params: dict[str, Any] = {"alcance": list(alcance) if alcance is not None else None}
    condicion = ""
    if estado:
        if estado not in ("activo", "cancelado"):
            raise ErrorDeDominio("estado inválido", {"estado": estado, "validos": ["activo", "cancelado"]})
        condicion = "WHERE o.estado = :estado"
        params["estado"] = estado
    total = session.execute(text(f"SELECT count(*) FROM modulo1.oc o {condicion}"), params).scalar()
    filas = session.execute(
        text(
            f"""
            SELECT o.oc_id, o.clave_origen, o.referencia, o.cliente_id, o.locacion_id, o.tipo_servicio_id,
                   o.vigencia_desde, o.vigencia_hasta, o.estado, o.lote_id, o.creado_en, o.actualizado_en,
                   e.referencia_evaluacion, e.veredicto_de_cumplimiento, e.resultado_de_decision,
                   e.creado_en AS evaluada_en, e.visible
            FROM modulo1.oc o
            LEFT JOIN LATERAL (
                SELECT e.referencia_evaluacion, e.veredicto_de_cumplimiento, e.resultado_de_decision, e.creado_en,
                       (true {filtro_decisiones_visibles(alcance)}) AS visible
                FROM modulo1.evaluacion_habilitacion e
                WHERE e.commitment_id = o.clave_origen
                ORDER BY e.creado_en DESC, e.referencia_evaluacion DESC LIMIT 1
            ) e ON true
            {condicion}
            ORDER BY o.vigencia_desde, o.clave_origen OFFSET :off LIMIT :lim
            """
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    items = []
    for f in filas:
        d = _plano(f)
        decision = None
        visible = d.pop("visible", None)
        if d.pop("referencia_evaluacion", None) is not None and visible:
            decision = {
                "referencia_evaluacion": str(f["referencia_evaluacion"]),
                "veredicto_de_cumplimiento": d["veredicto_de_cumplimiento"],
                "resultado_de_decision": d["resultado_de_decision"],
                "creado_en": d["evaluada_en"],
            }
        for k in ("veredicto_de_cumplimiento", "resultado_de_decision", "evaluada_en"):
            d.pop(k, None)
        d["ultima_decision"] = decision
        items.append(d)
    return envolver(items, int(total or 0), p)


def cobertura_oc(session: Session, identidad: Identidad, commitment_id: str) -> dict[str, Any]:
    """Cobertura de una OC en MODO CONSULTA (2.1: no persiste, no crea tareas, no emite
    eventos). Candidatos: todo el tenant para el responsable; solo su universo para el
    supervisor (matriz 2.2: "su universo"). Nunca reutiliza una decisión persistida ni
    devuelve sujetos fuera del alcance."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    oc = session.execute(
        text("SELECT oc_id, clave_origen, estado, vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE clave_origen = :c"),
        {"c": commitment_id},
    ).mappings().first()
    if oc is None:
        raise NoEncontrado("OC inexistente", {"commitment_id": commitment_id})
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    cobertura = cobertura_de_oc(session, identidad.tenant_id, commitment_id, ahora_utc(), candidatos=alcance)
    ev = _plano(cobertura)
    return {
        "commitment_id": oc["clave_origen"],
        "oc": _plano(oc),
        "modo": "consulta",
        "veredicto_de_cumplimiento": ev["veredicto_de_cumplimiento"],
        "resultado_de_decision": ev["resultado_de_decision"],
        "por_sujeto": ev["por_sujeto"],
        "requisitos_faltantes": ev["requisitos_faltantes"],
        "version_matriz": ev["version_matriz"],
    }


def _filas_decision(fila: Any) -> dict[str, Any]:
    d = _plano(fila)
    d["referencia_evaluacion"] = str(fila["referencia_evaluacion"])
    return d


def decisiones_oc(session: Session, identidad: Identidad, commitment_id: str, p: Pagina) -> dict[str, Any]:
    """Historial de decisiones persistidas de una OC, filtrado por visibilidad (2.3 §3)."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    params = {"c": commitment_id, "alcance": list(alcance) if alcance is not None else None}
    filtro = filtro_decisiones_visibles(alcance)
    total = session.execute(
        text(f"SELECT count(*) FROM modulo1.evaluacion_habilitacion e WHERE e.commitment_id = :c {filtro}"), params
    ).scalar()
    filas = session.execute(
        text(
            f"""
            SELECT e.referencia_evaluacion, e.commitment_id, e.veredicto_de_cumplimiento, e.resultado_de_decision,
                   e.por_sujeto, e.requisitos_faltantes, e.version_matriz, e.creado_en,
                   (SELECT array_agg(p.sujeto_id ORDER BY p.sujeto_id) FROM modulo1.evaluacion_sujeto_propuesto p
                     WHERE p.evaluacion_id = e.referencia_evaluacion) AS sujetos_propuestos
            FROM modulo1.evaluacion_habilitacion e
            WHERE e.commitment_id = :c {filtro}
            ORDER BY e.creado_en DESC OFFSET :off LIMIT :lim
            """
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    return envolver([_filas_decision(f) for f in filas], int(total or 0), p)


def decision(session: Session, identidad: Identidad, referencia_evaluacion: str) -> dict[str, Any]:
    """Una decisión por id. Fuera de alcance → 404 (no se confirma su existencia)."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    fila = session.execute(
        text(
            f"""
            SELECT e.referencia_evaluacion, e.commitment_id, e.veredicto_de_cumplimiento, e.resultado_de_decision,
                   e.por_sujeto, e.requisitos_faltantes, e.version_matriz, e.snapshot, e.creado_en,
                   (SELECT array_agg(p.sujeto_id ORDER BY p.sujeto_id) FROM modulo1.evaluacion_sujeto_propuesto p
                     WHERE p.evaluacion_id = e.referencia_evaluacion) AS sujetos_propuestos
            FROM modulo1.evaluacion_habilitacion e
            WHERE e.referencia_evaluacion = CAST(:r AS uuid) {filtro_decisiones_visibles(alcance)}
            """
        ),
        {"r": referencia_evaluacion, "alcance": list(alcance) if alcance is not None else None},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Decisión inexistente", {"referencia_evaluacion": referencia_evaluacion})
    return _filas_decision(fila)


def historial_supervision(session: Session, identidad: Identidad, sujeto_id: str, p: Pagina) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
    total = session.execute(
        text("SELECT count(*) FROM modulo1.asignacion_supervisor WHERE sujeto_id = :s"), {"s": sujeto_id}
    ).scalar()
    filas = session.execute(
        text(
            "SELECT a.asignacion_id, a.sujeto_id, a.supervisor_usuario_id, u.nombre AS supervisor_nombre, "
            "a.desde, a.hasta, a.estado, a.asignada_por, a.creado_en "
            "FROM modulo1.asignacion_supervisor a "
            "LEFT JOIN modulo1.usuario u ON u.usuario_id = a.supervisor_usuario_id "
            "WHERE a.sujeto_id = :s ORDER BY a.desde, a.creado_en OFFSET :off LIMIT :lim"
        ),
        {"s": sujeto_id, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    return envolver([_plano(f) for f in filas], int(total or 0), p)


def log_auditoria(
    session: Session,
    identidad: Identidad,
    tipo: str | None,
    desde: datetime | None,
    hasta: datetime | None,
    p: Pagina,
) -> dict[str, Any]:
    """event_log del tenant, más reciente primero."""
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
    condiciones: list[str] = []
    params: dict[str, Any] = {}
    if tipo:
        condiciones.append("tipo = :tipo")
        params["tipo"] = tipo
    if desde is not None:
        condiciones.append("ocurrido_en >= :desde")
        params["desde"] = desde
    if hasta is not None:
        condiciones.append("ocurrido_en <= :hasta")
        params["hasta"] = hasta
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = session.execute(text(f"SELECT count(*) FROM modulo1.event_log {where}"), params).scalar()
    filas = session.execute(
        text(
            f"SELECT id, evento_id, tipo, payload, ocurrido_en FROM modulo1.event_log {where} "
            "ORDER BY ocurrido_en DESC, id DESC OFFSET :off LIMIT :lim"
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    return envolver([_plano(f) for f in filas], int(total or 0), p)


def matriz_vigente(
    session: Session,
    identidad: Identidad,
    cliente_id: str,
    locacion_id: str,
    tipo_servicio_id: str,
    fecha: date | None,
) -> dict[str, Any]:
    """Versión de matriz vigente en `fecha` (default: hoy del tenant; ambos bordes
    inclusive) para (cliente, locación, tipo de servicio), con sus líneas."""
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO)
    fecha = fecha or hoy_del_tenant(session, identidad.tenant_id)
    version = session.execute(
        text(
            "SELECT matriz_version_id, cliente_id, locacion_id, tipo_servicio_id, version, vigente_desde, vigente_hasta, "
            "fuente, archivo_de_respaldo, autor, creado_en "
            "FROM modulo1.matriz_requisitos "
            "WHERE cliente_id = :c AND locacion_id = :l AND tipo_servicio_id = :t "
            "AND vigente_desde <= :f AND (vigente_hasta IS NULL OR vigente_hasta >= :f) "
            "ORDER BY version DESC LIMIT 1"
        ),
        {"c": cliente_id, "l": locacion_id, "t": tipo_servicio_id, "f": fecha},
    ).mappings().first()
    if version is None:
        raise NoEncontrado(
            "No hay versión de matriz vigente en esa fecha",
            {"cliente_id": cliente_id, "locacion_id": locacion_id, "tipo_servicio_id": tipo_servicio_id, "fecha": fecha.isoformat()},
        )
    lineas = session.execute(
        text(
            "SELECT lr.requisito_definicion_id, r.nombre AS requisito, r.categoria, r.tipo_sujeto_aplicable, "
            "lr.clasificacion, lr.bloqueante_durante_ejecucion "
            "FROM modulo1.linea_requisito lr "
            "LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = lr.requisito_definicion_id "
            "WHERE lr.matriz_version_id = :m ORDER BY r.tipo_sujeto_aplicable, r.nombre"
        ),
        {"m": str(version["matriz_version_id"])},
    ).mappings().all()
    salida = _plano(version)
    salida["fecha_consultada"] = fecha.isoformat()
    salida["lineas"] = [_plano(f) for f in lineas]
    return salida
