"""Timeline de vigencias por recurso con ventanas de OC (D-A bis)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.alcance import alcance_de_sujetos
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant
from app.core.estado_documental import (
    EstadoConfirmacionDocumental,
    EstadoRequisitoDocumental,
    EstadoValidacionArchivo,
    EstadoVersionEvidencia,
    EvaluacionDocumentalEntrada,
    EvidenciaDocumental,
    RequisitoAplicable,
    evaluar_requisito_documental,
)
from app.core.orquestacion import cobertura_de_oc
from app.comun.reloj import ahora_utc

LIMITE_DIAS = 366
ROLES = (Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION, Rol.SUPERVISOR, Rol.TECNICO)


def _estado_visual(
    hoy: date,
    desde: date,
    hasta: date | None,
    confirmacion: str,
    archivo_validacion: str,
    *,
    plazo_aviso_dias: int,
) -> str:
    """Color del tramo: D19 — sin respaldo válido no se dibuja como cobertura (no verde).

    «Por vencer» usa `estado_vigencia_presentacion` con el plazo del tenant o el override
    del requisito (`plazo_aviso_dias`), igual que la ficha de legajo.
    """
    from app.modules.consultas.presentacion_evidencia import estado_vigencia_presentacion

    if hasta is not None and hasta < hoy:
        return "vencido"
    if archivo_validacion != "valido":
        if confirmacion == "declarado":
            return "declarado_sin_verificar"
        if archivo_validacion == "invalido":
            return "evidencia_invalida"
        if archivo_validacion == "pendiente":
            return "archivo_en_revision"
        return "sin_archivo_respaldo"
    vencido = hasta is not None and hasta < hoy
    est = estado_vigencia_presentacion(
        hoy,
        vigente_hasta=hasta,
        vencido=vencido,
        plazo_aviso_dias=plazo_aviso_dias,
    )
    if est == "vencida":
        return "vencido"
    if est == "por_vencer":
        return "por_vencer"
    return "vigente"


def _exigir_rango(desde: date, hasta: date, hoy: date) -> None:
    if hasta < desde:
        raise ErrorDeDominio("`hasta` no puede ser anterior a `desde`")
    if (hasta - desde).days > LIMITE_DIAS:
        raise ErrorDeDominio("El rango excede 366 días", codigo="rango_temporal_excedido")
    if desde < hoy - timedelta(days=LIMITE_DIAS):
        raise ErrorDeDominio("`desde` demasiado en el pasado", codigo="rango_temporal_excedido")


def timeline_recursos(
    session: Session,
    identidad: Identidad,
    p: Pagina,
    *,
    desde: date,
    hasta: date,
    tipo_sujeto: str | None = None,
    oc_id: str | None = None,
    q: str | None = None,
    solo_quiebres: bool = False,
) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES)
    tenant_id = identidad.tenant_id
    hoy = hoy_del_tenant(session, tenant_id)
    from app.modules.consultas.presentacion_evidencia import _cargar_plazo_tenant, _plazo_aviso

    plazo_tenant = _cargar_plazo_tenant(session, tenant_id)
    _exigir_rango(desde, hasta, hoy)
    alcance = alcance_de_sujetos(session, identidad, hoy)

    cond = "WHERE l.tenant_id = :t AND l.dado_de_baja_en IS NULL"
    params: dict[str, Any] = {"t": tenant_id}
    if alcance is not None:
        params["alcance"] = list(alcance)
        cond += " AND (l.tipo_sujeto = 'empresa' OR l.sujeto_id = ANY(CAST(:alcance AS text[])))"
    if tipo_sujeto:
        cond += " AND l.tipo_sujeto = :ts"
        params["ts"] = tipo_sujeto
    if q:
        cond += " AND (l.sujeto_id ILIKE :q OR l.identificador_natural ILIKE :q OR l.nombre_apellido ILIKE :q)"
        params["q"] = f"%{q.strip()}%"

    tipos_oc: set[str] | None = None
    oc_filtro: dict[str, Any] | None = None
    if oc_id:
        oc_filtro = session.execute(
            text(
                "SELECT oc.oc_id, oc.clave_origen, oc.referencia, oc.vigencia_desde, oc.vigencia_hasta, "
                "oc.cliente_id, oc.locacion_id, oc.tipo_servicio_id, oc.estado AS estado_oc, "
                "op.nombre AS operadora_nombre, loc.nombre AS locacion_nombre, ts.nombre AS servicio_nombre "
                "FROM modulo1.oc oc "
                "LEFT JOIN modulo1.operadora_documental op ON op.tenant_id = oc.tenant_id AND op.operadora_id = oc.cliente_id "
                "LEFT JOIN modulo1.locacion_oc loc ON loc.tenant_id = oc.tenant_id AND loc.locacion_id = oc.locacion_id "
                "LEFT JOIN modulo1.tipo_servicio_oc ts ON ts.tenant_id = oc.tenant_id AND ts.tipo_servicio_id = oc.tipo_servicio_id "
                "WHERE oc.tenant_id = :t AND oc.oc_id = CAST(:id AS uuid)"
            ),
            {"t": tenant_id, "id": oc_id},
        ).mappings().first()
        if oc_filtro is None:
            raise NoEncontrado("OC inexistente", {"oc_id": oc_id})
        oc_filtro = dict(oc_filtro)
        try:
            ev = cobertura_de_oc(session, tenant_id, oc_filtro["clave_origen"], ahora_utc(), candidatos=alcance)
            tipos_oc = {t for t in (ev.get("snapshot") or {}).get("tipos_exigidos") or [] if t != "empresa"}
        except ErrorDeDominio:
            tipos_oc = set()
        if tipos_oc:
            params["tipos_oc"] = list(tipos_oc)
            cond += " AND l.tipo_sujeto = ANY(CAST(:tipos_oc AS text[]))"

    total = session.execute(text(f"SELECT count(*) FROM modulo1.legajo l {cond}"), params).scalar()
    legajos = session.execute(
        text(
            f"SELECT l.sujeto_id, l.tipo_sujeto, l.identificador_natural, l.nombre_apellido FROM modulo1.legajo l {cond} "
            f"ORDER BY l.tipo_sujeto, l.identificador_natural OFFSET :off LIMIT :lim"
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()

    ocs = session.execute(
        text(
            "SELECT oc.oc_id, oc.clave_origen, oc.referencia, oc.vigencia_desde, oc.vigencia_hasta, oc.estado AS estado_oc, "
            "op.nombre AS operadora_nombre, loc.nombre AS locacion_nombre, ts.nombre AS servicio_nombre "
            "FROM modulo1.oc oc "
            "LEFT JOIN modulo1.operadora_documental op ON op.tenant_id = oc.tenant_id AND op.operadora_id = oc.cliente_id "
            "LEFT JOIN modulo1.locacion_oc loc ON loc.tenant_id = oc.tenant_id AND loc.locacion_id = oc.locacion_id "
            "LEFT JOIN modulo1.tipo_servicio_oc ts ON ts.tenant_id = oc.tenant_id AND ts.tipo_servicio_id = oc.tipo_servicio_id "
            "WHERE oc.tenant_id = :t AND oc.estado = 'activo' "
            "AND oc.vigencia_desde <= :hasta AND oc.vigencia_hasta >= :desde ORDER BY oc.vigencia_desde"
        ),
        {"t": tenant_id, "desde": desde, "hasta": hasta},
    ).mappings().all()
    if oc_filtro:
        ocs = [oc_filtro]

    items: list[dict[str, Any]] = []
    for legajo in legajos:
        sid = legajo["sujeto_id"]
        docs = session.execute(
            text(
                "SELECT d.documento_id, d.requisito_definicion_id, r.nombre, r.categoria, r.plazo_aviso_dias, "
                "d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.estado_version, "
                "CASE WHEN d.archivo_estado = 'confirmado' THEN d.archivo_validacion ELSE 'sin_archivo' END AS archivo_validacion "
                "FROM modulo1.documento d "
                "LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = d.requisito_definicion_id "
                "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.estado_version = 'vigente' "
                "AND d.vigente_hasta IS NOT NULL "
                "AND d.vigente_hasta >= :desde AND d.vigente_desde <= :hasta"
            ),
            {"t": tenant_id, "s": sid, "desde": desde, "hasta": hasta},
        ).mappings().all()
        tramos = []
        for d in docs:
            tramos.append({
                "requisito_definicion_id": str(d["requisito_definicion_id"]) if d["requisito_definicion_id"] else None,
                "requisito": d["nombre"],
                "categoria": d["categoria"],
                "vigente_desde": d["vigente_desde"].isoformat(),
                "vigente_hasta": d["vigente_hasta"].isoformat(),
                "estado_confirmacion": d["estado_confirmacion"],
                "estado_visual": _estado_visual(
                    hoy,
                    d["vigente_desde"],
                    d["vigente_hasta"],
                    d["estado_confirmacion"],
                    d["archivo_validacion"],
                    plazo_aviso_dias=_plazo_aviso(d.get("plazo_aviso_dias"), plazo_tenant),
                ),
            })

        cruces: list[dict[str, Any]] = []
        for oc in ocs:
            if legajo["tipo_sujeto"] == "empresa":
                continue
            oc_desde, oc_hasta = oc["vigencia_desde"], oc["vigencia_hasta"]
            if oc_hasta < desde or oc_desde > hasta:
                continue
            quiebres: list[dict[str, Any]] = []
            llega = True
            try:
                ev = cobertura_de_oc(session, tenant_id, oc["clave_origen"], ahora_utc(), candidatos=alcance)
                sujeto_ev = next((s for s in ev.get("por_sujeto") or [] if s["sujeto_id"] == sid), None)
                if sujeto_ev is None:
                    continue
                llega = bool(sujeto_ev.get("asignable"))
                for req in sujeto_ev.get("requisitos") or []:
                    rid = req.get("requisito_definicion_id")
                    evidencias = session.execute(
                        text(
                            "SELECT documento_id, vigente_desde, vigente_hasta, estado_confirmacion, estado_version, "
                            "CASE WHEN archivo_estado = 'confirmado' THEN archivo_validacion ELSE 'sin_archivo' END AS archivo_validacion "
                            "FROM modulo1.documento WHERE tenant_id = :t AND sujeto_id = :s AND requisito_definicion_id = CAST(:r AS uuid) "
                            "AND estado_version = 'vigente' AND vigente_hasta IS NOT NULL"
                        ),
                        {"t": tenant_id, "s": sid, "r": rid},
                    ).mappings().all()
                    evids = tuple(
                        EvidenciaDocumental(
                            str(e["documento_id"]), str(rid), e["vigente_desde"], e["vigente_hasta"],
                            EstadoConfirmacionDocumental(e["estado_confirmacion"]),
                            EstadoVersionEvidencia(e["estado_version"]),
                            EstadoValidacionArchivo(e["archivo_validacion"]),
                        )
                        for e in evidencias
                    )
                    res = evaluar_requisito_documental(EvaluacionDocumentalEntrada(
                        oc_desde, oc_hasta,
                        RequisitoAplicable(str(rid), req.get("nombre") or "", "documento", legajo["tipo_sujeto"]),
                        evids,
                    ))
                    if res.estado == EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO:
                        ev = next((e for e in evids if e.evidencia_id == res.evidencia_id), None)
                        fecha = ev.vigente_hasta if ev and ev.vigente_hasta else res.primer_quiebre
                        if fecha and oc_desde <= fecha <= oc_hasta:
                            quiebres.append({"fecha": fecha.isoformat(), "requisito": req.get("nombre"), "tipo": "vence"})
                            llega = False
                    elif res.estado == EstadoRequisitoDocumental.FALTANTE:
                        ev = next((e for e in evids if e.evidencia_id == res.evidencia_id), None)
                        if ev and ev.vigente_desde and ev.vigente_desde > oc_desde:
                            quiebres.append({"fecha": ev.vigente_desde.isoformat(), "requisito": req.get("nombre"), "tipo": "inicia"})
                            llega = False
            except ErrorDeDominio:
                llega = False
            cruces.append({
                "oc_id": str(oc["oc_id"]),
                "clave_origen": oc["clave_origen"],
                "referencia": oc.get("referencia"),
                "vigencia_desde": oc_desde.isoformat(),
                "vigencia_hasta": oc_hasta.isoformat(),
                "operadora_nombre": oc.get("operadora_nombre"),
                "locacion_nombre": oc.get("locacion_nombre"),
                "servicio_nombre": oc.get("servicio_nombre"),
                "estado_oc": oc.get("estado_oc"),
                "llega_cubierto": llega and not quiebres,
                "quiebres": quiebres,
            })

        if solo_quiebres and not any(c["quiebres"] for c in cruces):
            continue
        items.append({
            "sujeto_id": sid,
            "tipo_sujeto": legajo["tipo_sujeto"],
            "identificador": legajo["identificador_natural"],
            "nombre_apellido": legajo.get("nombre_apellido"),
            "tramos": tramos,
            "ocs": cruces,
        })

    salida = envolver(items, int(total or 0), p)
    salida.update({"hoy": hoy.isoformat(), "desde": desde.isoformat(), "hasta": hasta.isoformat()})
    return salida
