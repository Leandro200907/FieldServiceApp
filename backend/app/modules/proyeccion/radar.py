"""Cálculo documental del radar dentro del módulo de proyección existente.

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
    params: dict[str, Any] = {"t": tenant_id, "desde": desde, "hasta": hasta}
    for campo in ("cliente_id", "locacion_id", "tipo_servicio_id"):
        if filtros.get(campo):
            condiciones.append(f"{campo} = CAST(:{campo} AS uuid)")
            params[campo] = filtros[campo]
    if filtros.get("q"):
        condiciones.append("(clave_origen ILIKE :q OR referencia ILIKE :q)")
        params["q"] = f"%{filtros['q'].strip()}%"
    filas = session.execute(text(
        "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
        "vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE " + " AND ".join(condiciones) +
        " ORDER BY vigencia_desde, clave_origen"
    ), params).mappings().all()
    return [dict(f) for f in filas]


def _legajos(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    filas = session.execute(text(
        "SELECT sujeto_id, tipo_sujeto, identificador_natural FROM modulo1.legajo "
        "WHERE tenant_id = :t AND dado_de_baja_en IS NULL ORDER BY tipo_sujeto, identificador_natural, sujeto_id"
    ), {"t": tenant_id}).mappings().all()
    return [dict(f) for f in filas]


def _matrices_y_requisitos(session: Session, tenant_id: str, oc: dict[str, Any], desde: date, hasta: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """Devuelve tramos de matriz; cualquier hueco mantiene `sin_matriz` como precedencia."""
    filas = session.execute(text("""
        SELECT m.matriz_version_id, m.version, m.vigente_desde, m.vigente_hasta, m.fuente,
               r.requisito_definicion_id, r.nombre, r.categoria, r.tipo_sujeto_aplicable,
               false AS particular
        FROM modulo1.matriz_requisitos m
        JOIN modulo1.linea_requisito lr ON lr.tenant_id = m.tenant_id AND lr.matriz_version_id = m.matriz_version_id
        JOIN modulo1.definicion_requisito r ON r.tenant_id = lr.tenant_id AND r.requisito_definicion_id = lr.requisito_definicion_id
        WHERE m.tenant_id = :t AND m.cliente_id = :cli AND m.locacion_id = :loc
          AND m.tipo_servicio_id = :tipo AND m.vigente_desde <= :hasta
          AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= :desde) AND r.activa
        ORDER BY m.vigente_desde, m.version, r.tipo_sujeto_aplicable, r.nombre
    """), {"t": tenant_id, "cli": oc["cliente_id"], "loc": oc["locacion_id"],
             "tipo": oc["tipo_servicio_id"], "desde": desde, "hasta": hasta}).mappings().all()
    por_matriz: dict[str, dict[str, Any]] = {}
    for fila in filas:
        d = dict(fila); mid = str(d["matriz_version_id"])
        tramo = por_matriz.setdefault(mid, {
            "matriz_version_id": mid, "version": d["version"], "fuente": d["fuente"],
            "vigente_desde": d["vigente_desde"], "vigente_hasta": d["vigente_hasta"],
            "requisitos": [],
        })
        tramo["requisitos"].append(_requisito(d))
    matrices = list(por_matriz.values())
    particulares = session.execute(text("""
        SELECT r.requisito_definicion_id, r.nombre, r.categoria, r.tipo_sujeto_aplicable
        FROM modulo1.requisito_particular p
        JOIN modulo1.definicion_requisito r ON r.tenant_id = p.tenant_id AND r.requisito_definicion_id = p.requisito_definicion_id
        WHERE p.tenant_id = :t AND p.commitment_id = :c AND r.activa
        ORDER BY r.tipo_sujeto_aplicable, r.nombre
    """), {"t": tenant_id, "c": oc["clave_origen"]}).mappings().all()
    particulares_dict = [dict(f) for f in particulares]
    requisitos_particulares = [_requisito(f, particular=True) for f in particulares_dict]
    # Construye intervalos donde la matriz elegida no cambia. Si dos versiones se
    # superponen se conserva la de inicio más reciente y, a igual inicio, mayor versión,
    # igual que `matriz_vigente`; así una versión abierta anterior no se evalúa dos veces.
    limites = {desde, hasta + timedelta(days=1)}
    for matriz in matrices:
        if desde < matriz["vigente_desde"] <= hasta:
            limites.add(matriz["vigente_desde"])
        if matriz["vigente_hasta"] is not None and desde <= matriz["vigente_hasta"] < hasta:
            limites.add(matriz["vigente_hasta"] + timedelta(days=1))
    cortes = sorted(limites)
    tramos: list[dict[str, Any]] = []
    sin_matriz = False
    for inicio, siguiente in zip(cortes, cortes[1:]):
        fin = siguiente - timedelta(days=1)
        aplicables = [m for m in matrices if m["vigente_desde"] <= inicio and
                      (m["vigente_hasta"] is None or m["vigente_hasta"] >= inicio)]
        if not aplicables:
            sin_matriz = True
            continue
        elegida = max(aplicables, key=lambda m: (m["vigente_desde"], m["version"]))
        tramos.append({**elegida, "desde": inicio, "hasta": fin})
    for tramo in tramos:
        existentes = {r.requisito_definicion_id for r in tramo["requisitos"]}
        tramo["requisitos"].extend(r for r in requisitos_particulares if r.requisito_definicion_id not in existentes)
    sin_matriz = sin_matriz or not tramos
    return tramos, particulares_dict, sin_matriz


def _requisito(fila: dict[str, Any], particular: bool = False) -> RequisitoAplicable:
    return RequisitoAplicable(str(fila["requisito_definicion_id"]), fila["nombre"], fila["categoria"],
                              fila["tipo_sujeto_aplicable"], aplica=True)


def _evidencias(session: Session, tenant_id: str) -> dict[tuple[str, str], list[EvidenciaDocumental]]:
    filas = session.execute(text("""
        SELECT d.documento_id::text AS evidencia_id, d.sujeto_id, d.requisito_definicion_id::text,
               d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.estado_version,
               CASE WHEN d.archivo_estado = 'confirmado' THEN d.archivo_validacion
                    WHEN d.clave_storage IS NULL THEN 'sin_archivo' ELSE 'pendiente' END AS archivo_validacion
        FROM modulo1.documento d WHERE d.tenant_id = :t
        UNION ALL
        SELECT a.acreditacion_id::text, a.persona_id, a.requisito_definicion_id::text,
               a.vigente_desde, a.vigente_hasta, a.estado_confirmacion, 'vigente', 'sin_archivo'
        FROM modulo1.acreditacion_competencia a WHERE a.tenant_id = :t
        UNION ALL
        SELECT i.induccion_id::text, i.persona_id, i.requisito_definicion_id::text,
               i.vigente_desde, i.vigente_hasta, i.estado_confirmacion, 'vigente', 'sin_archivo'
        FROM modulo1.induccion i WHERE i.tenant_id = :t
    """), {"t": tenant_id}).mappings().all()
    salida: dict[tuple[str, str], list[EvidenciaDocumental]] = defaultdict(list)
    for f in filas:
        d = dict(f)
        salida[(d["sujeto_id"], d["requisito_definicion_id"])].append(EvidenciaDocumental(
            d["evidencia_id"], d["requisito_definicion_id"], d["vigente_desde"], d["vigente_hasta"],
            EstadoConfirmacionDocumental(d["estado_confirmacion"]), EstadoVersionEvidencia(d["estado_version"]),
            EstadoValidacionArchivo(d["archivo_validacion"]),
        ))
    return salida


def _evaluar_oc(session: Session, tenant_id: str, oc: dict[str, Any], legajos: list[dict[str, Any]],
                evidencias: dict[tuple[str, str], list[EvidenciaDocumental]], desde: date, hasta: date) -> dict[str, Any]:
    inicio, fin = max(desde, oc["vigencia_desde"]), min(hasta, oc["vigencia_hasta"])
    tramos, particulares, sin_matriz = _matrices_y_requisitos(session, tenant_id, oc, inicio, fin)
    detalle_legajos: list[dict[str, Any]] = []
    for legajo in legajos:
        resultados = []
        for tramo in tramos:
            for req in tramo["requisitos"]:
                if req.tipo_sujeto != legajo["tipo_sujeto"]:
                    continue
                evidencias_requisito = tuple(evidencias.get((legajo["sujeto_id"], req.requisito_definicion_id), ()))
                resultado = evaluar_requisito_documental(EvaluacionDocumentalEntrada(
                    tramo["desde"], tramo["hasta"], req,
                    evidencias_requisito,
                ))
                evidencia = next((e for e in evidencias_requisito if e.evidencia_id == resultado.evidencia_id), None)
                resultados.append({
                    "matriz_version_id": tramo["matriz_version_id"], "version_matriz": tramo["version"],
                    "periodo_desde": tramo["desde"], "periodo_hasta": tramo["hasta"],
                    "requisito_definicion_id": req.requisito_definicion_id, "nombre": req.nombre,
                    "estado": resultado.estado.value, "primer_quiebre": resultado.primer_quiebre,
                    "evidencia_id": resultado.evidencia_id, "motivo": resultado.motivo,
                    "accion_sugerida": resultado.accion_sugerida,
                    "vigente_hasta": evidencia.vigente_hasta if evidencia else None,
                    "estado_confirmacion": evidencia.estado_confirmacion.value if evidencia else None,
                    "archivo_validacion": evidencia.archivo_validacion.value if evidencia else None,
                })
        resumen = resumir_resultados(_resultado_desde_dict(r) for r in resultados)
        detalle_legajos.append({**legajo, "estado_documental": resumen.estado,
                                "primer_quiebre": resumen.primer_quiebre, "requisitos": resultados,
                                "_resumen": resumen})
    resumen_oc = resumir_oc((l["_resumen"] for l in detalle_legajos), sin_matriz=sin_matriz)
    for legajo in detalle_legajos:
        legajo.pop("_resumen")
    return {"estado": resumen_oc, "tramos": tramos, "requisitos_particulares": particulares,
            "legajos": detalle_legajos}


def _resultado_desde_dict(d: dict[str, Any]):
    from app.core.estado_documental import EstadoRequisitoDocumental, ResultadoRequisitoDocumental
    return ResultadoRequisitoDocumental(EstadoRequisitoDocumental(d["estado"]), d["primer_quiebre"],
                                         d["evidencia_id"], d["motivo"], d["accion_sugerida"])


def _resumen_por_tipo(legajos: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    nombres = {"empresa": "empresa", "persona": "personas", "vehiculo": "vehiculos", "equipo": "equipos"}
    salida = {v: {"total": 0, "con_alertas": 0, "incompletos": 0} for v in nombres.values()}
    for legajo in legajos:
        r = salida[nombres[legajo["tipo_sujeto"]]]; r["total"] += 1
        r["con_alertas"] += legajo["estado_documental"] == "con_alertas_documentales"
        r["incompletos"] += legajo["estado_documental"] == "informacion_incompleta"
    return salida


def radar_backlog(session: Session, identidad: Identidad, p: Pagina, *, desde: date | None = None,
                  hasta: date | None = None, estados: list[str] | None = None, **filtros: Any) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_RADAR)
    hoy = hoy_del_tenant(session, identidad.tenant_id); desde = desde or hoy; hasta = hasta or desde + timedelta(days=60)
    _exigir_rango(desde, hasta)
    if estados and any(e not in ESTADOS_OC for e in estados):
        raise ErrorDeDominio("estado inválido", {"validos": list(ESTADOS_OC)})
    ocs = _ocs(session, identidad.tenant_id, desde, hasta, filtros)
    legajos = _legajos(session, identidad.tenant_id); evidencias = _evidencias(session, identidad.tenant_id)
    items = []
    for oc in ocs:
        calculo = _evaluar_oc(session, identidad.tenant_id, oc, legajos, evidencias, desde, hasta)
        estado: ResumenDocumental = calculo["estado"]
        if estados and estado.estado not in estados: continue
        resumen = _resumen_por_tipo(calculo["legajos"])
        motivos = [f"{v['con_alertas']} {k} con alertas documentales" for k, v in resumen.items() if v["con_alertas"]]
        items.append({**{k: (str(v) if k.endswith("_id") else v) for k, v in oc.items()},
                      "estado_documental": estado.estado, "primer_quiebre": estado.primer_quiebre,
                      "resumen": resumen, "motivos_resumidos": motivos})
    total = len(items); salida = envolver(items[p.offset:p.offset + p.limit], total, p)
    salida.update({"calculado_en": datetime.now(timezone.utc), "desde": desde, "hasta": hasta,
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


