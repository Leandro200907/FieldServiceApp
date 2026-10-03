"""OCs donde un requisito deja de cubrir el período (mismo barrido que acciones pendientes)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterator

from sqlalchemy.orm import Session

from app.auth.identidad import Identidad
from app.comun.reloj import hoy_del_tenant


def _as_date(value: date | str) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def referencia_oc(oc: dict[str, Any]) -> dict[str, str]:
    return {
        "clave_origen": str(oc["clave_origen"]),
        "oc_id": str(oc["oc_id"]),
        "vigencia_desde": _as_date(oc["vigencia_desde"]).isoformat(),
        "vigencia_hasta": _as_date(oc["vigencia_hasta"]).isoformat(),
    }


def oc_en_curso(oc: dict[str, Any], hoy: date) -> bool:
    return _as_date(oc["vigencia_desde"]) <= hoy <= _as_date(oc["vigencia_hasta"])


def ordenar_ocs_afectadas(ocs: list[dict[str, str]], hoy: date) -> list[dict[str, str]]:
    return sorted(
        ocs,
        key=lambda ref: (
            0 if oc_en_curso(ref, hoy) else 1,
            _as_date(ref["vigencia_desde"]),
        ),
    )


def _agregar_oc(destino: list[dict[str, str]], oc_ref: dict[str, str]) -> None:
    if oc_ref not in destino:
        destino.append(oc_ref)


def iter_vence_durante_en_ocs(
    session: Session,
    identidad: Identidad,
    *,
    desde: date,
    hasta: date,
    filtros: dict[str, Any] | None = None,
    sujeto_id: str | None = None,
    tipo_recurso: str | None = None,
) -> Iterator[tuple[str, str, dict[str, str]]]:
    """Emite (sujeto_id, requisito_definicion_id, referencia_oc) por cada OC afectada."""
    from app.modules.proyeccion import radar as radar_mod

    filtros = dict(filtros or {})
    legajos = radar_mod._legajos_visibles(session, identidad)
    evidencias = radar_mod._evidencias(session, identidad.tenant_id)
    ocs = radar_mod._ocs(session, identidad.tenant_id, desde, hasta, filtros, offset=0, limit=500)
    operadoras = filtros.get("operadora_ids")
    if operadoras:
        permitidos = set(operadoras)
        ocs = [o for o in ocs if str(o["cliente_id"]) in permitidos]

    for oc in ocs:
        inicio, fin = max(desde, _as_date(oc["vigencia_desde"])), min(hasta, _as_date(oc["vigencia_hasta"]))
        calc = radar_mod._evaluar_oc(session, identidad.tenant_id, oc, legajos, evidencias, inicio, fin)
        for leg in calc["legajos"]:
            if sujeto_id and leg["sujeto_id"] != sujeto_id:
                continue
            if tipo_recurso and leg["tipo_sujeto"] != tipo_recurso:
                continue
            for req in leg.get("requisitos") or []:
                if req.get("estado") != "vence_durante_periodo":
                    continue
                rid = str(req.get("requisito_definicion_id") or "")
                if not rid:
                    continue
                yield leg["sujeto_id"], rid, referencia_oc(oc)


def mapa_ocs_afectadas_por_requisito(
    session: Session,
    identidad: Identidad,
    *,
    sujeto_id: str,
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
) -> dict[str, list[dict[str, str]]]:
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    desde = vigencia_desde or hoy
    hasta = vigencia_hasta or (hoy + timedelta(days=60))
    mapa: dict[str, list[dict[str, str]]] = {}
    for suj, rid, oc_ref in iter_vence_durante_en_ocs(
        session, identidad, desde=desde, hasta=hasta, sujeto_id=sujeto_id,
    ):
        if suj != sujeto_id:
            continue
        _agregar_oc(mapa.setdefault(rid, []), oc_ref)
    for rid in mapa:
        mapa[rid] = ordenar_ocs_afectadas(mapa[rid], hoy)
    return mapa


def adjuntar_ocs_afectadas_evidencias(
    session: Session,
    identidad: Identidad,
    sujeto_id: str,
    items: list[dict[str, Any]],
) -> None:
    mapa = mapa_ocs_afectadas_por_requisito(session, identidad, sujeto_id=sujeto_id)
    for item in items:
        rid = str(item.get("requisito_definicion_id") or "")
        item["ocs_afectadas"] = mapa.get(rid, [])
