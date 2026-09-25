Warning: truncated output (original token count: 4013)
Total output lines: 273

"""Radar documental de sólo lectura.

Consulta OC, matrices, requisitos, legajos y evidencias. Deliberadamente no importa ni
consulta operación, asignaciones, custodia, excepciones o evaluaciones históricas.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant
from app.core.estado_documental import (
    EstadoConfirmacionDocumental,
    EstadoValidacionArchivo,
    EstadoVersionEvidencia,
    EvaluacionDocumentalEntrada,
    EvidenciaDocumental,
    RequisitoAplicable,
    evaluar_requisito_documental,
)
from app.core.radar_documental import ResumenDocumental, resumir_oc, resumir_resultados


ADVERTENCIA = (
    "Este análisis es informativo. No representa disponibilidad, compatibilidad, "
    "capacidad, planificación ni asignación de recursos."
)
ROLES_RADAR = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.CONFIGURACION)
ROLES_DETALLE = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
ESTADOS_OC = ("sin_alertas_documentales", "con_alertas_documentales", "informacion_incompleta", "sin_matriz")
LIMITE_DIAS = 366


def _exigir_rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise ErrorDeDominio("`hasta` no puede ser anterior a `desde`", {"desde": str(desde), "hasta": str(hasta)})
    if (hasta - desde).days > LIMITE_DIAS:
        raise ErrorDeDominio("El rango pedido excede 366 días", codigo="rango_temporal_excedido")


def _ocs(session: Session, tenant_id: str, desde: date, hasta: date, filtros: dict[str, Any]) -> list[dict[str, Any]]:
    condiciones = ["tenant_id = :t", "estado = 'activo'", "vigencia_desde <= :hasta", "vigencia_hasta >= :desde"]
    params: dict[str, Any] = …3013 tokens truncated…one.utc), "desde": desde, "hasta": hasta,
                   "advertencia": ADVERTENCIA})
    return salida


def detalle_oc(session: Session, identidad: Identidad, oc_id: str) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_DETALLE)
    fila = session.execute(text("SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE tenant_id=:t AND oc_id=CAST(:id AS uuid)"), {"t": identidad.tenant_id, "id": oc_id}).mappings().first()
    if fila is None: raise NoEncontrado("OC inexistente", {"oc_id": oc_id})
    oc = dict(fila); legajos = _legajos(session, identidad.tenant_id)
    calculo = _evaluar_oc(session, identidad.tenant_id, oc, legajos, _evidencias(session, identidad.tenant_id), oc["vigencia_desde"], oc["vigencia_hasta"])
    matrices = [{k: t[k] for k in ("matriz_version_id", "version", "fuente", "desde", "hasta")} for t in calculo["tramos"]]
    grupos = [{"tipo_sujeto": tipo, "legajos": [l for l in calculo["legajos"] if l["tipo_sujeto"] == tipo]}
              for tipo in ("empresa", "persona", "vehiculo", "equipo")]
    return {"oc": {k: (str(v) if k.endswith("_id") else v) for k, v in oc.items()},
            "estado_documental": calculo["estado"].estado, "matrices_utilizadas": matrices,
            "requisitos_particulares": [
                {**p, "requisito_definicion_id": str(p["requisito_definicion_id"])}
                for p in calculo["requisitos_particulares"]
            ], "grupos": grupos, "advertencia": ADVERTENCIA}


def detalle_legajo(session: Session, identidad: Identidad, oc_id: str, sujeto_id: str) -> dict[str, Any]:
    detalle = detalle_oc(session, identidad, oc_id)
    for grupo in detalle["grupos"]:
        for legajo in grupo["legajos"]:
            if legajo["sujeto_id"] == sujeto_id:
                return {"oc": detalle["oc"], "legajo": legajo, "advertencia": ADVERTENCIA}
    raise NoEncontrado("Legajo inexistente o inactivo", {"sujeto_id": sujeto_id})


