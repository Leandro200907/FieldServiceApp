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
    legajos = radar_mod._legajos_visibles(session, identidad)
    evidencias = radar_mod._evidencias(session, identidad.tenant_id)
    tramos, _, huecos = radar_mod._matrices_y_requisitos(session, identidad.tenant_id, oc, inicio, fin)
    tipos_req = {req.tipo_sujeto for tramo in tramos for req in tramo["requisitos"]}
    fuera = set(radar_mod._tipos_fuera_de_alcance(session, identidad.tenant_id, identidad, tipos_req, legajos))

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
        if tipo in fuera:
            disponibilidad.append(
                {
                    "tipo_sujeto": tipo,
                    "etiqueta": _ETIQUETA.get(tipo, tipo),
                    "estado": "fuera_de_alcance",
                    "texto": f"{_ETIQUETA.get(tipo, tipo)}: fuera de tu alcance",
                    "habilitados_toda_ventana": [],
                    "se_cae_en_ventana": [],
                    "no_habilitados": [],
                }
            )
            return
        legajos_tipo = [l for l in legajos if l["tipo_sujeto"] == tipo]
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
                _, det = _eval_legajo_tramo(leg, tramos[-1], evidencias) if tramos else (False, [])
                quiebre = next((d for d in det if d.get("primer_quiebre")), None)
                if quiebre:
                    item["fecha"] = quiebre["primer_quiebre"].isoformat() if quiebre.get("primer_quiebre") else None
                    item["requisito"] = quiebre.get("requisito")
                cae.append(item)
            else:
                no.append(item)

        # Tramos sin ningún legajo habilitado
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
        # Comprimir tramos consecutivos
        comprimidos: list[dict[str, str]] = []
        for t in tramos_sin:
            if comprimidos and comprimidos[-1]["hasta"] == (date.fromisoformat(t["desde"]) - timedelta(days=1)).isoformat():
                comprimidos[-1]["hasta"] = t["hasta"]
            else:
                comprimidos.append(dict(t))

        if comprimidos and tipo != "empresa":
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
            f"{len(toda)} habilitados toda la ventana" if toda else None,
            f"{len(cae)} se caen en la ventana" if cae else None,
            f"{len(no)} no habilitados" if no else None,
        ]
        texto = f"{_ETIQUETA.get(tipo, tipo)}: " + " · ".join(p for p in partes if p)
        disponibilidad.append(
            {
                "tipo_sujeto": tipo,
                "etiqueta": _ETIQUETA.get(tipo, tipo),
                "estado": "ok",
                "texto": texto,
                "habilitados_toda_ventana": toda,
                "se_cae_en_ventana": cae,
                "no_habilitados": no,
            }
        )
        if comprimidos:
            dias = sum(_dias_inclusive(date.fromisoformat(a["desde"]), date.fromisoformat(a["hasta"])) for a in comprimidos)
            impacto.append({"tipo_sujeto": tipo, "dias_sin_habilitados": dias, "tramos": comprimidos})

    if "empresa" in tipos_req or any(l["tipo_sujeto"] == "empresa" for l in legajos):
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
