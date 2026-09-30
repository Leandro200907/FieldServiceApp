"""Evaluación documental del backlog de OC sin veredicto de cobertura (D-E)."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.auth.identidad import Identidad
from app.core.estado_documental import (
    EvaluacionDocumentalEntrada,
    EstadoRequisitoDocumental,
    evaluar_requisito_documental,
)
from app.core.radar_documental import ESTADOS_ALERTA, ESTADOS_INCOMPLETOS
from app.modules.proyeccion import radar as radar_mod

_ETIQUETA = {"persona": "Técnicos", "vehiculo": "Vehículos", "equipo": "Equipos", "empresa": "Empresa"}


def _dias_inclusive(desde: date, hasta: date) -> int:
    return (hasta - desde).days + 1


def _reqs_tipo(tramo: dict[str, Any], tipo: str) -> list[Any]:
    return [r for r in tramo["requisitos"] if r.tipo_sujeto == tipo]


def _eval_legajo_tramo(
    legajo: dict[str, Any],
    tramo: dict[str, Any],
    evidencias: dict[tuple[str, str], list[Any]],
) -> tuple[bool, list[dict[str, Any]]]:
    detalle: list[dict[str, Any]] = []
    for req in _reqs_tipo(tramo, legajo["tipo_sujeto"]):
        evs = tuple(evidencias.get((legajo["sujeto_id"], req.requisito_definicion_id), ()))
        res = evaluar_requisito_documental(
            EvaluacionDocumentalEntrada(tramo["desde"], tramo["hasta"], req, evs),
        )
        detalle.append(
            {
                "requisito": req.nombre,
                "estado": res.estado.value,
                "primer_quiebre": res.primer_quiebre,
                "motivo": res.motivo,
                "vigente_hasta": next((e.vigente_hasta for e in evs if e.evidencia_id == res.evidencia_id), None) if res.evidencia_id else None,
            }
        )
        if res.estado in ESTADOS_ALERTA or res.estado in ESTADOS_INCOMPLETOS:
            return False, detalle
    return True, detalle


def _eval_legajo_ventana(
    legajo: dict[str, Any],
    tramos: list[dict[str, Any]],
    evidencias: dict[tuple[str, str], list[Any]],
    inicio: date,
    fin: date,
) -> str:
    """Clasifica: habilitado_toda_ventana | se_cae_en_ventana | no_habilitado."""
    if not tramos:
        return "no_habilitado"
    caida: dict[str, Any] | None = None
    for tramo in tramos:
        ok, det = _eval_legajo_tramo(legajo, tramo, evidencias)
        if not ok:
            for d in det:
                if d["estado"] == EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO.value:
                    caida = d
            return "se_cae_en_ventana" if caida else "no_habilitado"
    # Todos los tramos OK — ¿vigente todo el período completo de la OC?
    for tramo in tramos:
        for req in _reqs_tipo(tramo, legajo["tipo_sujeto"]):
            evs = tuple(evidencias.get((legajo["sujeto_id"], req.requisito_definicion_id), ()))
            res = evaluar_requisito_documental(
                EvaluacionDocumentalEntrada(inicio, fin, req, evs),
            )
            if res.estado != EstadoRequisitoDocumental.VIGENTE_TODO_EL_PERIODO:
                return "se_cae_en_ventana"
    return "habilitado_toda_ventana"


def evaluar_oc_backlog(
    session: Session,
    identidad: Identidad,
    oc: dict[str, Any],
) -> dict[str, Any]:
    inicio, fin = oc["vigencia_desde"], oc["vigencia_hasta"]
    todos = radar_mod._legajos(session, identidad.tenant_id)
    visibles = radar_mod._legajos_visibles(session, identidad)
    ids_visibles = {l["sujeto_id"] for l in visibles}
    evidencias = radar_mod._evidencias(session, identidad.tenant_id)
    tramos, _, huecos = radar_mod._matrices_y_requisitos(session, identidad.tenant_id, oc, inicio, fin)
    tipos_req = {req.tipo_sujeto for tramo in tramos for req in tramo["requisitos"]}
    fuera = set(radar_mod._tipos_fuera_de_alcance(session, identidad.tenant_id, identidad, tipos_req, visibles))
    MSG_FUERA = "hay recursos habilitados fuera de tu alcance"

    alertas: list[dict[str, Any]] = []
    if huecos:
        for h in huecos:
            alertas.append(
                {
                    "codigo": "sin_matriz",
                    "mensaje": "Sin matriz aplicable en el tramo",
                    "desde": h["desde"].isoformat(),
                    "hasta": h["hasta"].isoformat(),
                }
            )
    elif not tramos:
        alertas.append(
            {
                "codigo": "sin_matriz",
                "mensaje": "Sin matriz aplicable",
                "desde": inicio.isoformat(),
                "hasta": fin.isoformat(),
            }
        )

    disponibilidad: list[dict[str, Any]] = []
    impacto: list[dict[str, Any]] = []

    def procesar_tipo(tipo: str) -> None:
        legajos_tipo = [l for l in todos if l["tipo_sujeto"] == tipo]
        toda: list[dict[str, Any]] = []
        cae: list[dict[str, Any]] = []
        no: list[dict[str, Any]] = []
        for leg in legajos_tipo:
            cls = _eval_legajo_ventana(leg, tramos, evidencias, inicio, fin)
            item = {
                "sujeto_id": leg["sujeto_id"],
                "nombre": leg.get("identificador_natural") or leg["sujeto_id"],
            }
            if cls == "habilitado_toda_ventana":
                toda.append(item)
            elif cls == "se_cae_en_ventana":
                vigente_hasta = None
                req_nombre = None
                for tramo in tramos:
                    _, det = _eval_legajo_tramo(leg, tramo, evidencias)
                    hit = next((d for d in det if d["estado"] == EstadoRequisitoDocumental.VENCE_DURANTE_PERIODO.value), None)
                    if hit:
                        vigente_hasta = hit.get("vigente_hasta")
                        req_nombre = hit.get("requisito")
                        break
                if vigente_hasta:
                    item["fecha"] = vigente_hasta.isoformat() if hasattr(vigente_hasta, "isoformat") else str(vigente_hasta)
                    item["requisito"] = req_nombre
                cae.append(item)
            else:
                no.append(item)

        tramos_sin: list[dict[str, str]] = []

        def _ok_en_dia(dia: date) -> bool:
            tramo_dia = next((t for t in tramos if t["desde"] <= dia <= t["hasta"]), None)
            if tramo_dia is None:
                return True
            mini = {"desde": dia, "hasta": dia, "requisitos": tramo_dia["requisitos"]}
            return any(_eval_legajo_tramo(l, mini, evidencias)[0] for l in legajos_tipo)

        cursor = inicio
        while cursor <= fin:
            if legajos_tipo and not _ok_en_dia(cursor):
                tramos_sin.append({"desde": cursor.isoformat(), "hasta": cursor.isoformat()})
            cursor += timedelta(days=1)
        comprimidos: list[dict[str, str]] = []
        for t in tramos_sin:
            if comprimidos and comprimidos[-1]["hasta"] == (date.fromisoformat(t["desde"]) - timedelta(days=1)).isoformat():
                comprimidos[-1]["hasta"] = t["hasta"]
            else:
                comprimidos.append(dict(t))

        habilitados_fuera = [x for x in toda if x["sujeto_id"] not in ids_visibles]
        toda_v = [x for x in toda if x["sujeto_id"] in ids_visibles]
        cae_v = [x for x in cae if x["sujeto_id"] in ids_visibles]
        no_v = [x for x in no if x["sujeto_id"] in ids_visibles]

        # La alerta cierta es tenant-wide. Si hay habilitados fuera del universo, no es
        # cierta para el supervisor: se informa el hueco de visibilidad, nunca el rojo.
        if comprimidos and tipo != "empresa" and not habilitados_fuera:
            alertas.append(
                {
                    "codigo": "tipo_sin_habilitados",
                    "tipo_sujeto": tipo,
                    "mensaje": f"Ningún legajo habilitado de tipo {tipo}",
                    "tramos": comprimidos,
                }
            )
        if tipo == "empresa" and comprimidos:
            alertas.append(
                {
                    "codigo": "empresa_no_habilitada",
                    "mensaje": "La empresa no está habilitada en algún tramo de la ventana",
                    "tramos": comprimidos,
                }
            )

        partes = [
            f"{len(toda_v)} habilitados toda la ventana" if toda_v else None,
            f"{len(cae_v)} se caen en la ventana" if cae_v else None,
            f"{len(no_v)} no habilitados" if no_v else None,
            MSG_FUERA if habilitados_fuera else None,
        ]
        texto = f"{_ETIQUETA.get(tipo, tipo)}: " + " · ".join(p for p in partes if p)
        if not any(partes) and tipo in fuera:
            texto = f"{_ETIQUETA.get(tipo, tipo)}: fuera de tu alcance"
        disponibilidad.append(
            {
                "tipo_sujeto": tipo,
                "etiqueta": _ETIQUETA.get(tipo, tipo),
                "estado": "fuera_de_alcance" if (tipo in fuera and not comprimidos) else "ok",
                "texto": texto,
                "habilitados_toda_ventana": toda_v,
                "se_cae_en_ventana": cae_v,
                "no_habilitados": no_v,
            }
        )
        if comprimidos and not habilitados_fuera:
            dias = sum(_dias_inclusive(date.fromisoformat(a["desde"]), date.fromisoformat(a["hasta"])) for a in comprimidos)
            impacto.append({"tipo_sujeto": tipo, "dias_sin_habilitados": dias, "tramos": comprimidos})

    if "empresa" in tipos_req or any(l["tipo_sujeto"] == "empresa" for l in todos):
        procesar_tipo("empresa")
    for tipo in sorted(t for t in tipos_req if t != "empresa"):
        procesar_tipo(tipo)

    return {
        "alertas_ciertas": alertas,
        "tiene_alertas": len(alertas) > 0,
        "disponibilidad_por_tipo": disponibilidad,
        "impacto_por_tipo": impacto,
        "tipos_fuera_de_alcance": sorted(fuera),
    }
