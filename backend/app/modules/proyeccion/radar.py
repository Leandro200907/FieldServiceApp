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
from app.auth.alcance import alcance_de_sujetos, sujeto_en_alcance
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
from app.modules.consultas.backlog_documental import evaluar_oc_backlog
from app.modules.oc.catalogos_maestros import nombres_oc


ADVERTENCIA = (
    "Este análisis es informativo. No representa disponibilidad, compatibilidad, "
    "capacidad, planificación ni asignación de recursos."
)
ROLES_RADAR = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.CONFIGURACION)
ROLES_DETALLE = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
ESTADOS_OC = (
    "sin_alertas_documentales",
    "con_alertas_documentales",
    "informacion_incompleta",
    "sin_matriz",
    "fuera_de_alcance",
)
LIMITE_DIAS = 366


def _exigir_rango(desde: date, hasta: date) -> None:
    if hasta < desde:
        raise ErrorDeDominio("`hasta` no puede ser anterior a `desde`", {"desde": str(desde), "hasta": str(hasta)})
    if (hasta - desde).days > LIMITE_DIAS:
        raise ErrorDeDominio("El rango pedido excede 366 días", codigo="rango_temporal_excedido")


def _filtro_ocs(tenant_id: str, desde: date, hasta: date, filtros: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    condiciones = ["tenant_id = :t", "estado = 'activo'", "vigencia_desde <= :hasta", "vigencia_hasta >= :desde"]
    params: dict[str, Any] = {"t": tenant_id, "desde": desde, "hasta": hasta}
    for campo in ("cliente_id", "locacion_id", "tipo_servicio_id"):
        if filtros.get(campo):
            condiciones.append(f"{campo} = CAST(:{campo} AS uuid)")
            params[campo] = filtros[campo]
    if filtros.get("q"):
        condiciones.append("(clave_origen ILIKE :q OR referencia ILIKE :q)")
        params["q"] = f"%{filtros['q'].strip()}%"
    return condiciones, params


def _contar_ocs(session: Session, tenant_id: str, desde: date, hasta: date, filtros: dict[str, Any]) -> int:
    condiciones, params = _filtro_ocs(tenant_id, desde, hasta, filtros)
    return int(session.execute(
        text("SELECT count(*) FROM modulo1.oc WHERE " + " AND ".join(condiciones)), params,
    ).scalar_one())


def _ocs(session: Session, tenant_id: str, desde: date, hasta: date, filtros: dict[str, Any],
         *, offset: int = 0, limit: int | None = None) -> list[dict[str, Any]]:
    condiciones, params = _filtro_ocs(tenant_id, desde, hasta, filtros)
    paginacion = ""
    if limit is not None:
        paginacion = " LIMIT :limit OFFSET :offset"
        params.update({"limit": limit, "offset": offset})
    filas = session.execute(text(
        "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
        "vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE " + " AND ".join(condiciones) +
        " ORDER BY vigencia_desde, clave_origen" + paginacion
    ), params).mappings().all()
    return [dict(f) for f in filas]


def _legajos(session: Session, tenant_id: str) -> list[dict[str, Any]]:
    filas = session.execute(text(
        "SELECT sujeto_id, tipo_sujeto, identificador_natural, nombre_apellido FROM modulo1.legajo "
        "WHERE tenant_id = :t AND dado_de_baja_en IS NULL ORDER BY tipo_sujeto, identificador_natural, sujeto_id"
    ), {"t": tenant_id}).mappings().all()
    return [dict(f) for f in filas]


def _legajos_visibles(session: Session, identidad: Identidad) -> list[dict[str, Any]]:
    """Legajos del tenant acotados al universo del supervisor (A-04); responsable/configuración ven todos.

    Excepción radar: el legajo `empresa` entra siempre — no es sujeto propuesto ni entra en
    `alcance_de_sujetos`, pero la matriz lo evalúa implícitamente (habilitante 1.8) y ocultarlo
    daría un falso verde documental en el backlog."""
    todos = _legajos(session, identidad.tenant_id)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    if alcance is None:
        return todos
    permitidos = set(alcance)
    return [
        legajo for legajo in todos
        if legajo["tipo_sujeto"] == "empresa" or legajo["sujeto_id"] in permitidos
    ]


def _matrices_y_requisitos(session: Session, tenant_id: str, oc: dict[str, Any], desde: date, hasta: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, date]]]:
    """Devuelve tramos evaluables y los huecos exactos de matriz."""
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
    huecos_matriz: list[dict[str, date]] = []
    for inicio, siguiente in zip(cortes, cortes[1:]):
        fin = siguiente - timedelta(days=1)
        aplicables = [m for m in matrices if m["vigente_desde"] <= inicio and
                      (m["vigente_hasta"] is None or m["vigente_hasta"] >= inicio)]
        if not aplicables:
            huecos_matriz.append({"desde": inicio, "hasta": fin})
            if requisitos_particulares:
                tramos.append({
                    "matriz_version_id": None,
                    "version": None,
                    "fuente": "requisito_particular",
                    "vigente_desde": inicio,
                    "vigente_hasta": fin,
                    "desde": inicio,
                    "hasta": fin,
                    "requisitos": list(requisitos_particulares),
                })
            continue
        elegida = max(aplicables, key=lambda m: (m["vigente_desde"], m["version"]))
        tramos.append({**elegida, "desde": inicio, "hasta": fin})
    for tramo in tramos:
        existentes = {r.requisito_definicion_id for r in tramo["requisitos"]}
        tramo["requisitos"].extend(r for r in requisitos_particulares if r.requisito_definicion_id not in existentes)
    if not tramos and not huecos_matriz:
        huecos_matriz.append({"desde": desde, "hasta": hasta})
    return tramos, particulares_dict, huecos_matriz


def _requisito(fila: dict[str, Any], particular: bool = False) -> RequisitoAplicable:
    return RequisitoAplicable(str(fila["requisito_definicion_id"]), fila["nombre"], fila["categoria"],
                              fila["tipo_sujeto_aplicable"], aplica=True)


def _evidencias(session: Session, tenant_id: str, sujeto_id: str | None = None) -> dict[tuple[str, str], list[EvidenciaDocumental]]:
    condicion_sujeto = " AND d.sujeto_id = :s" if sujeto_id is not None else ""
    params = {"t": tenant_id, "s": sujeto_id}
    filas = session.execute(text("""
        SELECT d.documento_id::text AS evidencia_id, d.sujeto_id, d.requisito_definicion_id::text,
               d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.estado_version,
               d.origen_propuesta, d.sucede_a::text AS sucede_a,
               CASE WHEN d.archivo_estado = 'confirmado' THEN d.archivo_validacion
                    WHEN d.clave_storage IS NULL THEN 'sin_archivo' ELSE 'pendiente' END AS archivo_validacion
        FROM modulo1.documento d WHERE d.tenant_id = :t AND d.vigente_hasta IS NOT NULL
          AND d.estado_version IN ('vigente', 'sucedida')
    """ + condicion_sujeto), params).mappings().all()
    por_clave: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for f in filas:
        d = dict(f)
        por_clave[(d["sujeto_id"], d["requisito_definicion_id"])].append(d)
    salida: dict[tuple[str, str], list[EvidenciaDocumental]] = defaultdict(list)
    for clave, grupo in por_clave.items():
        vigente = next((g for g in grupo if g["estado_version"] == "vigente"), None)
        promover_sucedida: str | None = None
        if (
            vigente
            and vigente.get("origen_propuesta")
            and vigente["estado_confirmacion"] == "declarado"
            and vigente.get("sucede_a")
        ):
            promover_sucedida = str(vigente["sucede_a"])
            grupo = [g for g in grupo if g["estado_version"] != "vigente" or not g.get("origen_propuesta")]
        for d in grupo:
            if promover_sucedida and d["estado_version"] == "sucedida" and str(d["evidencia_id"]) == promover_sucedida:
                d = {**d, "estado_version": "vigente"}
            salida[clave].append(
                EvidenciaDocumental(
                    d["evidencia_id"],
                    d["requisito_definicion_id"],
                    d["vigente_desde"],
                    d["vigente_hasta"],
                    EstadoConfirmacionDocumental(d["estado_confirmacion"]),
                    EstadoVersionEvidencia(d["estado_version"]),
                    EstadoValidacionArchivo(d["archivo_validacion"]),
                )
            )
    return salida


def _tipos_fuera_de_alcance(
    session: Session,
    tenant_id: str,
    identidad: Identidad,
    tipos_requeridos: set[str],
    legajos_visibles: list[dict[str, Any]],
) -> list[str]:
    hoy = hoy_del_tenant(session, tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    if alcance is None:
        return []
    visibles = {l["tipo_sujeto"] for l in legajos_visibles}
    todos = _legajos(session, tenant_id)
    fuera: list[str] = []
    for tipo in sorted(tipos_requeridos):
        if tipo == "empresa" or tipo in visibles:
            continue
        if any(l["tipo_sujeto"] == tipo for l in todos):
            fuera.append(tipo)
    return fuera


def _evaluar_oc(
    session: Session,
    tenant_id: str,
    oc: dict[str, Any],
    legajos: list[dict[str, Any]],
    evidencias: dict[tuple[str, str], list[EvidenciaDocumental]],
    desde: date,
    hasta: date,
    *,
    tipos_disponibles: set[str] | None = None,
    tipos_fuera_de_alcance: list[str] | None = None,
) -> dict[str, Any]:
    inicio, fin = max(desde, oc["vigencia_desde"]), min(hasta, oc["vigencia_hasta"])
    tramos, particulares, huecos_matriz = _matrices_y_requisitos(session, tenant_id, oc, inicio, fin)
    tipos_requeridos = {req.tipo_sujeto for tramo in tramos for req in tramo["requisitos"]}
    disponibles = tipos_disponibles if tipos_disponibles is not None else {l["tipo_sujeto"] for l in legajos}
    fuera_set = set(tipos_fuera_de_alcance or [])
    tipos_sin_legajos = sorted(tipos_requeridos - disponibles - fuera_set)
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
                    "accion_sugerida_fecha": resultado.accion_sugerida_fecha,
                    "vigente_hasta": evidencia.vigente_hasta if evidencia else None,
                    "estado_confirmacion": evidencia.estado_confirmacion.value if evidencia else None,
                    "archivo_validacion": evidencia.archivo_validacion.value if evidencia else None,
                    "requerido": resultado.estado.value != "no_aplica",
                })
        resumen = resumir_resultados(_resultado_desde_dict(r) for r in resultados)
        detalle_legajos.append({**legajo, "estado_documental": resumen.estado,
                                "primer_quiebre": resumen.primer_quiebre, "requisitos": resultados,
                                "_resumen": resumen})
    resumenes_oc = [l["_resumen"] for l in detalle_legajos]
    resumenes_oc.extend(
        ResumenDocumental("informacion_incompleta", None, 0, 1)
        for _ in tipos_sin_legajos
    )
    resumenes_oc.extend(
        ResumenDocumental("fuera_de_alcance", None, 0, 0)
        for _ in fuera_set
        if _ in tipos_requeridos
    )
    resumen_oc = resumir_oc(resumenes_oc, sin_matriz=bool(huecos_matriz))
    for legajo in detalle_legajos:
        legajo.pop("_resumen")
    return {"estado": resumen_oc, "tramos": tramos, "requisitos_particulares": particulares,
            "legajos": detalle_legajos, "tipos_requeridos": sorted(tipos_requeridos),
            "tipos_sin_legajos": tipos_sin_legajos, "tipos_fuera_de_alcance": sorted(fuera_set & tipos_requeridos),
            "huecos_matriz": huecos_matriz}


def _resultado_desde_dict(d: dict[str, Any]):
    from app.core.estado_documental import EstadoRequisitoDocumental, ResultadoRequisitoDocumental
    return ResultadoRequisitoDocumental(
        EstadoRequisitoDocumental(d["estado"]),
        d["primer_quiebre"],
        d["evidencia_id"],
        d["motivo"],
        d["accion_sugerida"],
        d.get("accion_sugerida_fecha"),
    )


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
    legajos = _legajos_visibles(session, identidad)
    evidencias = _evidencias(session, identidad.tenant_id)
    items: list[dict[str, Any]] = []

    def _adjuntar_habilitacion(item: dict[str, Any], oc: dict[str, Any], inicio: date, fin: date) -> None:
        eval_doc = evaluar_oc_backlog(
            session,
            identidad,
            {
                "clave_origen": oc["clave_origen"],
                "cliente_id": str(oc["cliente_id"]),
                "locacion_id": str(oc["locacion_id"]),
                "tipo_servicio_id": str(oc["tipo_servicio_id"]),
                "vigencia_desde": inicio,
                "vigencia_hasta": fin,
            },
        )
        item.update(
            {
                "disponibilidad_por_tipo": eval_doc.get("disponibilidad_por_tipo") or [],
                "impacto_por_tipo": eval_doc.get("impacto_por_tipo") or [],
                "alertas_ciertas": eval_doc.get("alertas_ciertas") or [],
                "tiene_alertas": bool(eval_doc.get("tiene_alertas")),
            }
        )
        alertas = item.get("alertas_ciertas") or []
        for disp in item.get("disponibilidad_por_tipo") or []:
            tipo = disp.get("tipo_sujeto")
            disp["tipo_sin_habilitados"] = any(
                a.get("codigo") == "tipo_sin_habilitados" and a.get("tipo_sujeto") == tipo for a in alertas
            )

    def evaluar_item(oc: dict[str, Any]) -> dict[str, Any] | None:
        inicio, fin = max(desde, oc["vigencia_desde"]), min(hasta, oc["vigencia_hasta"])
        tramos, _, _ = _matrices_y_requisitos(session, identidad.tenant_id, oc, inicio, fin)
        tipos_req = {req.tipo_sujeto for tramo in tramos for req in tramo["requisitos"]}
        fuera = _tipos_fuera_de_alcance(session, identidad.tenant_id, identidad, tipos_req, legajos)
        calculo = _evaluar_oc(
            session, identidad.tenant_id, oc, legajos, evidencias, desde, hasta,
            tipos_fuera_de_alcance=fuera,
        )
        estado: ResumenDocumental = calculo["estado"]
        if estados and estado.estado not in estados:
            return None
        resumen = _resumen_por_tipo(calculo["legajos"])
        motivos = [f"{v['con_alertas']} {k} con alertas documentales" for k, v in resumen.items() if v["con_alertas"]]
        motivos.extend(
            f"Sin legajos activos del tipo {tipo} para evaluar los requisitos documentales"
            for tipo in calculo["tipos_sin_legajos"]
        )
        motivos.extend(
            f"Hay recursos del tipo {tipo} fuera de tu alcance"
            for tipo in calculo.get("tipos_fuera_de_alcance") or []
        )
        if calculo["huecos_matriz"]:
            motivos.append("Hay períodos sin matriz de requisitos aplicable")
        item = {
            **{k: (str(v) if k.endswith("_id") else v) for k, v in oc.items()},
            "estado_documental": estado.estado,
            "primer_quiebre": estado.primer_quiebre,
            "resumen": resumen,
            "motivos_resumidos": motivos,
        }
        item.update(
            nombres_oc(
                session,
                identidad.tenant_id,
                str(oc["cliente_id"]),
                str(oc["locacion_id"]),
                str(oc["tipo_servicio_id"]),
            )
        )
        _adjuntar_habilitacion(item, oc, inicio, fin)
        return item

    if not estados:
        total = _contar_ocs(session, identidad.tenant_id, desde, hasta, filtros)
        for oc in _ocs(session, identidad.tenant_id, desde, hasta, filtros, offset=p.offset, limit=p.limit):
            item = evaluar_item(oc)
            if item is not None:
                items.append(item)
    else:
        total = 0
        cursor = 0
        tamano_lote = 100
        while True:
            lote = _ocs(session, identidad.tenant_id, desde, hasta, filtros, offset=cursor, limit=tamano_lote)
            if not lote:
                break
            for oc in lote:
                item = evaluar_item(oc)
                if item is not None:
                    if p.offset <= total < p.offset + p.limit:
                        items.append(item)
                    total += 1
            cursor += len(lote)
            if len(lote) < tamano_lote:
                break
    salida = envolver(items, total, p)
    salida.update({"calculado_en": datetime.now(timezone.utc), "desde": desde, "hasta": hasta,
                   "advertencia": ADVERTENCIA})
    return salida


def _oc_por_id(session: Session, tenant_id: str, oc_id: str) -> dict[str, Any]:
    fila = session.execute(text("SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
                                "vigencia_desde, vigencia_hasta FROM modulo1.oc "
                                "WHERE tenant_id=:t AND oc_id=CAST(:id AS uuid)"),
                           {"t": tenant_id, "id": oc_id}).mappings().first()
    if fila is None:
        raise NoEncontrado("OC inexistente", {"oc_id": oc_id})
    return dict(fila)


def detalle_oc(session: Session, identidad: Identidad, oc_id: str, p: Pagina | None = None) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_DETALLE)
    p = p or Pagina(offset=0, limit=50)
    oc = _oc_por_id(session, identidad.tenant_id, oc_id)
    legajos = _legajos_visibles(session, identidad)
    tramos, _, _ = _matrices_y_requisitos(
        session, identidad.tenant_id, oc, oc["vigencia_desde"], oc["vigencia_hasta"],
    )
    tipos_req = {req.tipo_sujeto for tramo in tramos for req in tramo["requisitos"]}
    fuera = _tipos_fuera_de_alcance(session, identidad.tenant_id, identidad, tipos_req, legajos)
    calculo = _evaluar_oc(
        session, identidad.tenant_id, oc, legajos, _evidencias(session, identidad.tenant_id),
        oc["vigencia_desde"], oc["vigencia_hasta"], tipos_fuera_de_alcance=fuera,
    )
    matrices = [{k: t[k] for k in ("matriz_version_id", "version", "fuente", "desde", "hasta")}
                for t in calculo["tramos"] if t["matriz_version_id"] is not None]
    legajos_pagina = calculo["legajos"][p.offset:p.offset + p.limit]
    grupos = []
    for tipo in ("empresa", "persona", "vehiculo", "equipo"):
        legajos_tipo = [l for l in calculo["legajos"] if l["tipo_sujeto"] == tipo]
        grupos.append({"tipo_sujeto": tipo, "requerido": tipo in calculo["tipos_requeridos"],
               "sin_legajos_requeridos": tipo in calculo["tipos_sin_legajos"],
               "legajos": [l for l in legajos_pagina if l["tipo_sujeto"] == tipo], "total": len(legajos_tipo),
               "offset": p.offset, "limit": p.limit})
    inicio, fin = oc["vigencia_desde"], oc["vigencia_hasta"]
    eval_doc = evaluar_oc_backlog(
        session,
        identidad,
        {
            "clave_origen": oc["clave_origen"],
            "cliente_id": str(oc["cliente_id"]),
            "locacion_id": str(oc["locacion_id"]),
            "tipo_servicio_id": str(oc["tipo_servicio_id"]),
            "vigencia_desde": inicio,
            "vigencia_hasta": fin,
        },
    )
    alertas = eval_doc.get("alertas_ciertas") or []
    disponibilidad = list(eval_doc.get("disponibilidad_por_tipo") or [])
    for disp in disponibilidad:
        tipo = disp.get("tipo_sujeto")
        disp["tipo_sin_habilitados"] = any(
            a.get("codigo") == "tipo_sin_habilitados" and a.get("tipo_sujeto") == tipo for a in alertas
        )
    oc_con_nombres = {k: (str(v) if k.endswith("_id") else v) for k, v in oc.items()}
    oc_con_nombres.update(
        nombres_oc(
            session,
            identidad.tenant_id,
            str(oc["cliente_id"]),
            str(oc["locacion_id"]),
            str(oc["tipo_servicio_id"]),
        )
    )
    return {
        "oc": oc_con_nombres,
        "estado_documental": calculo["estado"].estado,
        "matrices_utilizadas": matrices,
        "requisitos_particulares": [
            {**p, "requisito_definicion_id": str(p["requisito_definicion_id"])}
            for p in calculo["requisitos_particulares"]
        ],
        "huecos_matriz": calculo["huecos_matriz"],
        "grupos": grupos,
        "disponibilidad_por_tipo": disponibilidad,
        "impacto_por_tipo": eval_doc.get("impacto_por_tipo") or [],
        "alertas_ciertas": alertas,
        "tiene_alertas": bool(eval_doc.get("tiene_alertas")),
        "total_legajos": len(legajos),
        "offset": p.offset,
        "limit": p.limit,
        "advertencia": ADVERTENCIA,
    }


def detalle_legajo(session: Session, identidad: Identidad, oc_id: str, sujeto_id: str) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_DETALLE)
    oc = _oc_por_id(session, identidad.tenant_id, oc_id)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    fila = session.execute(text(
        "SELECT sujeto_id, tipo_sujeto, identificador_natural, nombre_apellido FROM modulo1.legajo "
        "WHERE tenant_id=:t AND sujeto_id=:s AND dado_de_baja_en IS NULL"
    ), {"t": identidad.tenant_id, "s": sujeto_id}).mappings().first()
    if fila is None:
        raise NoEncontrado("Legajo inexistente o inactivo", {"sujeto_id": sujeto_id})
    legajo = dict(fila)
    if legajo["tipo_sujeto"] != "empresa" and not sujeto_en_alcance(session, identidad, sujeto_id, hoy):
        raise NoEncontrado("Legajo inexistente o inactivo", {"sujeto_id": sujeto_id})
    legajos_visibles = _legajos_visibles(session, identidad)
    tipos_disponibles = {l["tipo_sujeto"] for l in legajos_visibles}
    calculo = _evaluar_oc(
        session, identidad.tenant_id, oc, [legajo], _evidencias(session, identidad.tenant_id, sujeto_id),
        oc["vigencia_desde"], oc["vigencia_hasta"], tipos_disponibles=tipos_disponibles,
    )
    return {"oc": {k: (str(v) if k.endswith("_id") else v) for k, v in oc.items()},
            "legajo": calculo["legajos"][0], "advertencia": ADVERTENCIA}

