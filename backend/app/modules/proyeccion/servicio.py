"""Proyección documental (docs/PROYECCION_DOCUMENTAL.md): tres consultas de solo lectura,
`consulta` en el sentido cerrado de 2.1 de modelo-dominio.md — nunca persiste, nunca crea
tareas, nunca emite eventos, nunca modifica una decisión histórica. Reutiliza el motor
puro (`app/core/evaluacion.py`, vía `app/core/proyeccion.py`) y la orquestación existente
(`app/core/orquestacion.py`: `matriz_vigente`, `lineas_efectivas`, `definiciones_de`,
`cargar_evidencias`, `buscar_oc`) tal cual están — no les agrega reglas de negocio nuevas.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.alcance import alcance_de_sujetos, filtro_decisiones_visibles
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant
from app.core.orquestacion import (
    buscar_oc,
    cargar_constancias,
    cargar_evidencias,
    cargar_excepciones,
    definiciones_de,
    lineas_efectivas,
    matriz_vigente,
)
from app.core.proyeccion import Candidato, Intervalo, calcular_intervalos

ADVERTENCIA = "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
LIMITE_DIAS = 366
ESTADOS_RESUMEN = (
    "sin_matriz", "pendiente_de_planificacion", "bloqueo_confirmado",
    "requiere_revision", "riesgo_documental", "sin_riesgos_detectados",
    "vigencia_finalizada",
)

# `calendario_vigencias` amplía deliberadamente a técnico (punto 3 del documento): ya ve
# lo mismo, sin rango, en `mi_legajo`.
ROLES_CALENDARIO = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO)
ROLES_PROYECCION = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)


def _exigir_rango(desde: date, hasta: date, hoy: date, limite_pasado: date | None = None) -> None:
    if hasta < desde:
        raise ErrorDeDominio("`hasta` no puede ser anterior a `desde`", {"desde": str(desde), "hasta": str(hasta)})
    if limite_pasado is not None and desde < limite_pasado:
        raise ErrorDeDominio(
            "`desde` no puede ser anterior a hoy - 366 días", {"desde": str(desde), "minimo": str(limite_pasado)},
            codigo="rango_temporal_excedido",
        )
    if (hasta - desde).days > LIMITE_DIAS:
        raise ErrorDeDominio(
            "El rango pedido excede 366 días", {"desde": str(desde), "hasta": str(hasta)},
            codigo="rango_temporal_excedido",
        )


# --------------------------------------------------------------------------- calendario_vigencias


_SQL_CALENDARIO = """
    WITH evidencia AS (
        SELECT 'documento' AS categoria, d.documento_id AS id, d.sujeto_id, l.tipo_sujeto,
               l.identificador_natural, d.requisito_definicion_id, r.nombre AS requisito,
               d.vigente_desde, d.vigente_hasta, d.estado_confirmacion,
               (CASE WHEN d.archivo_estado = 'confirmado' THEN d.archivo_validacion ELSE NULL END) AS archivo_validacion
        FROM modulo1.documento d
        JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
        LEFT JOIN modulo1.definicion_requisito r ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
        WHERE d.tenant_id = :t AND d.estado_version = 'vigente' AND l.dado_de_baja_en IS NULL
        UNION ALL
        SELECT 'competencia', a.acreditacion_id, a.persona_id, l.tipo_sujeto, l.identificador_natural,
               a.requisito_definicion_id, r.nombre, a.vigente_desde, a.vigente_hasta, a.estado_confirmacion, NULL
        FROM modulo1.acreditacion_competencia a
        JOIN modulo1.legajo l ON l.tenant_id = a.tenant_id AND l.sujeto_id = a.persona_id
        LEFT JOIN modulo1.definicion_requisito r ON r.tenant_id = a.tenant_id AND r.requisito_definicion_id = a.requisito_definicion_id
        WHERE a.tenant_id = :t AND l.dado_de_baja_en IS NULL
        UNION ALL
        SELECT 'induccion', i.induccion_id, i.persona_id, l.tipo_sujeto, l.identificador_natural,
               i.requisito_definicion_id, r.nombre, i.vigente_desde, i.vigente_hasta, i.estado_confirmacion, NULL
        FROM modulo1.induccion i
        JOIN modulo1.legajo l ON l.tenant_id = i.tenant_id AND l.sujeto_id = i.persona_id
        LEFT JOIN modulo1.definicion_requisito r ON r.tenant_id = i.tenant_id AND r.requisito_definicion_id = i.requisito_definicion_id
        WHERE i.tenant_id = :t AND l.dado_de_baja_en IS NULL
    )
"""


def calendario_vigencias(
    session: Session, identidad: Identidad, p: Pagina, *,
    desde: date | None = None, hasta: date | None = None,
    tipo_sujeto: str | None = None, categoria: str | None = None,
    estado: str = "todos", q: str | None = None,
) -> dict[str, Any]:
    """Punto 3: "¿qué evidencia vence entre estas dos fechas?" — sin mirar ninguna matriz
    ni ninguna OC. Mismo universo que `tablero_vencimientos`, ampliado a técnico."""
    identidad.exigir_rol(*ROLES_CALENDARIO)
    tenant_id = identidad.tenant_id
    hoy = hoy_del_tenant(session, tenant_id)
    desde = desde or hoy
    hasta = hasta or (desde + timedelta(days=30))
    _exigir_rango(desde, hasta, hoy, limite_pasado=hoy - timedelta(days=LIMITE_DIAS))
    if estado not in ("vigente", "vencido", "todos"):
        raise ErrorDeDominio("estado inválido", {"estado": estado, "validos": ["vigente", "vencido", "todos"]})

    alcance = alcance_de_sujetos(session, identidad, hoy)
    params: dict[str, Any] = {"t": tenant_id, "desde": desde, "hasta": hasta}
    cond = " WHERE vigente_hasta BETWEEN :desde AND :hasta"
    if alcance is not None:
        params["alcance"] = list(alcance)
        cond += " AND sujeto_id = ANY(CAST(:alcance AS text[]))"
    if tipo_sujeto:
        cond += " AND tipo_sujeto = :ts"
        params["ts"] = tipo_sujeto
    if categoria:
        cond += " AND categoria = :cat"
        params["cat"] = categoria
    if estado == "vencido":
        cond += " AND vigente_hasta < :hoy"
        params["hoy"] = hoy
    elif estado == "vigente":
        cond += " AND vigente_hasta >= :hoy"
        params["hoy"] = hoy
    if q:
        cond += " AND (sujeto_id ILIKE :q OR identificador_natural ILIKE :q)"
        params["q"] = f"%{q.strip()}%"

    total = session.execute(text(_SQL_CALENDARIO + f"SELECT count(*) FROM evidencia{cond}"), params).scalar()
    filas = session.execute(
        text(_SQL_CALENDARIO + f"SELECT * FROM evidencia{cond} ORDER BY vigente_hasta, sujeto_id OFFSET :off LIMIT :lim"),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    items = []
    for f in filas:
        d = dict(f)
        d["id"] = str(d["id"])
        if d["requisito_definicion_id"] is not None:
            d["requisito_definicion_id"] = str(d["requisito_definicion_id"])
        d["dias_para_vencer"] = (d["vigente_hasta"] - hoy).days
        d["referencia"] = f"evidencia:{d['categoria']}:{d['id']}"
        items.append(d)
    salida = envolver(items, int(total or 0), p)
    salida["hoy"] = hoy
    salida["desde"] = desde
    salida["hasta"] = hasta
    salida["advertencia"] = ADVERTENCIA
    return salida


# --------------------------------------------------------------------------- punto 4: conjunto de sujetos


def _candidatos_del_alcance(session: Session, tenant_id: str, alcance: list[str] | None) -> list[Candidato]:
    params: dict[str, Any] = {"t": tenant_id}
    cond = ""
    if alcance is not None:
        params["alcance"] = list(alcance)
        cond = " AND sujeto_id = ANY(CAST(:alcance AS text[]))"
    filas = session.execute(
        text(
            "SELECT sujeto_id, tipo_sujeto FROM modulo1.legajo "
            f"WHERE tenant_id = :t AND dado_de_baja_en IS NULL{cond} ORDER BY sujeto_id"
        ),
        params,
    ).mappings().all()
    return [Candidato(str(f["sujeto_id"]), f["tipo_sujeto"]) for f in filas]


def conjunto_de_sujetos(session: Session, identidad: Identidad, commitment_id: str, hoy: date) -> dict[str, Any]:
    """Punto 4: última decisión visible (4.1) o candidatos del alcance (4.2)."""
    alcance = alcance_de_sujetos(session, identidad, hoy)
    fila = session.execute(
        text(
            "SELECT e.referencia_evaluacion, e.creado_en, "
            "(SELECT array_agg(p.sujeto_id) FROM modulo1.evaluacion_sujeto_propuesto p "
            " WHERE p.evaluacion_id = e.referencia_evaluacion) AS sujeto_ids "
            "FROM modulo1.evaluacion_habilitacion e WHERE e.commitment_id = :c"
            + filtro_decisiones_visibles(alcance) +
            " ORDER BY e.creado_en DESC LIMIT 1"
        ),
        {"c": commitment_id, "alcance": list(alcance) if alcance is not None else None},
    ).mappings().first()
    if fila is not None and fila["sujeto_ids"]:
        candidatos_tipo = session.execute(
            text("SELECT sujeto_id, tipo_sujeto FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = ANY(:ids)"),
            {"t": identidad.tenant_id, "ids": list(fila["sujeto_ids"])},
        ).mappings().all()
        return {
            "origen": "ultima_decision_visible",
            "referencia_evaluacion": str(fila["referencia_evaluacion"]),
            "evaluada_en": fila["creado_en"],
            "sujeto_ids": sorted(fila["sujeto_ids"]),
            "candidatos": [Candidato(str(f["sujeto_id"]), f["tipo_sujeto"]) for f in candidatos_tipo],
        }
    candidatos = _candidatos_del_alcance(session, identidad.tenant_id, alcance)
    return {
        "origen": "candidatos_del_alcance",
        "referencia_evaluacion": None,
        "evaluada_en": None,
        "sujeto_ids": sorted(c.sujeto_id for c in candidatos),
        "candidatos": candidatos,
    }


# --------------------------------------------------------------------------- motor por OC


def _tipos_y_requisitos(session: Session, tenant_id: str, commitment_id: str, oc: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, str], dict[str, str], dict[str, Any]] | None:
    """Requisitos exigidos por tipo (fijos para toda la OC, punto 1), nombres para causas,
    clasificación por requisito (B-02: la necesita el motor para constancias/excepciones —
    sólo bloqueante_duro admite constancia, sólo excepcionable admite excepción con
    efecto), y la matriz vigente. `None` si no hay matriz vigente al día de ingreso."""
    matriz = matriz_vigente(session, tenant_id, oc["cliente_id"], oc["locacion_id"], oc["tipo_servicio_id"], oc["vigencia_desde"])
    if matriz is None:
        return None
    lineas = lineas_efectivas(session, tenant_id, commitment_id, str(matriz["matriz_version_id"]))
    definiciones = definiciones_de(session, tenant_id, list(lineas))
    requisitos_por_tipo: dict[str, list[str]] = {}
    nombres: dict[str, str] = {}
    clasificaciones: dict[str, str] = {}
    for req_id, linea in lineas.items():
        d = definiciones.get(req_id)
        if d is None:
            continue
        requisitos_por_tipo.setdefault(d["tipo_sujeto_aplicable"], []).append(req_id)
        nombres[req_id] = d["nombre"]
        clasificaciones[req_id] = linea["clasificacion"]
    return requisitos_por_tipo, nombres, clasificaciones, {"matriz_version_id": str(matriz["matriz_version_id"]), "version": matriz["version"]}


def _resumen_desde_intervalos(intervalos: list[Intervalo]) -> tuple[str, date | None, list[str]]:
    """Punto 7: NO es `peor(intervalos)`. Devuelve (estado, primer_quiebre, motivos_resumidos
    — los `motivo` de las causas del intervalo que efectivamente explica el resumen)."""
    if not intervalos:
        return "sin_riesgos_detectados", None, []
    primero = intervalos[0]
    if primero.estado in ("bloqueo_confirmado", "requiere_revision"):
        return primero.estado, primero.desde, [c.motivo for c in primero.causas]
    for i in intervalos[1:]:
        if i.estado in ("bloqueo_confirmado", "requiere_revision"):
            return "riesgo_documental", i.desde, [c.motivo for c in i.causas]
    return "sin_riesgos_detectados", None, []


def _intervalo_a_dict(i: Intervalo) -> dict[str, Any]:
    d: dict[str, Any] = {
        "desde": i.desde, "hasta": i.hasta, "estado": i.estado,
        "capacidad_documental_potencial": i.capacidad_documental_potencial,
    }
    if i.causas:
        d["causas"] = [
            {
                "tipo_sujeto": c.tipo_sujeto, "requisito_definicion_id": c.requisito_definicion_id,
                "motivo": c.motivo, "sujetos_que_pierden_cobertura": c.sujetos_que_pierden_cobertura,
                "sujetos_que_mantienen_cobertura": c.sujetos_que_mantienen_cobertura,
            }
            for c in i.causas
        ]
    return d


def _causa_sin_evaluar(motivo: str) -> list[dict[str, Any]]:
    return [{"motivo": motivo}]


# --------------------------------------------------------------------------- proyeccion_documental


def proyeccion_documental(
    session: Session, identidad: Identidad, commitment_id: str, *,
    desde: date | None = None, hasta: date | None = None, detalle: str = "resumen",
) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_PROYECCION)
    if detalle not in ("resumen", "diario"):
        raise ErrorDeDominio("detalle inválido", {"detalle": detalle, "validos": ["resumen", "diario"]})
    tenant_id = identidad.tenant_id
    oc = buscar_oc(session, tenant_id, commitment_id)
    if oc is None:
        raise NoEncontrado("OC inexistente", {"commitment_id": commitment_id})
    hoy = hoy_del_tenant(session, tenant_id)
    desde = desde or max(hoy, oc["vigencia_desde"])
    hasta_explicito = hasta is not None
    # B-03: el default de `hasta` es la vigencia de la OC, pero recortado al tope de 366
    # días — antes una OC de más de un año explotaba 422 con la llamada más obvia (sin
    # parámetros). Un `hasta` explícito que exceda el tope sigue dando 422 en `_exigir_rango`.
    hasta = hasta or min(oc["vigencia_hasta"], desde + timedelta(days=LIMITE_DIAS))
    if desde < oc["vigencia_desde"]:
        raise ErrorDeDominio("`desde` no puede ser anterior a la vigencia de la OC",
                             {"desde": str(desde), "oc_vigencia_desde": str(oc["vigencia_desde"])})
    # B-03/B-07 (observación de seguimiento de la auditoría externa, 2026-09-22, opción A
    # elegida explícitamente): una OC cuya vigencia ya terminó antes de `desde` da
    # `hasta < desde` únicamente por el DEFAULT (`hasta` = `oc.vigencia_hasta`, en el
    # pasado) — eso es un hecho estructural de la OC, no un pedido inválido, y se resuelve
    # más abajo como `vigencia_finalizada` (mismo criterio que ya usa el backlog, B-07).
    # Un `hasta` explícito que quede antes de `desde` SIGUE siendo 422: ahí sí es un
    # pedido mal formado de quien consulta, no un hecho de la OC.
    vigencia_ya_finalizada = not hasta_explicito and hasta < desde
    if not vigencia_ya_finalizada:
        _exigir_rango(desde, hasta, hoy)

    conjunto = conjunto_de_sujetos(session, identidad, commitment_id, hoy)
    salida: dict[str, Any] = {
        "commitment_id": commitment_id,
        "referencia": f"oc:{commitment_id}",
        "hoy": hoy,
        "oc": {"cliente_id": str(oc["cliente_id"]), "locacion_id": str(oc["locacion_id"]),
               "tipo_servicio_id": str(oc["tipo_servicio_id"]),
               "vigencia_desde": oc["vigencia_desde"], "vigencia_hasta": oc["vigencia_hasta"]},
        "desde": desde, "hasta": hasta,
        "sujetos": {k: conjunto[k] for k in ("origen", "referencia_evaluacion", "evaluada_en", "sujeto_ids")},
        "advertencia": ADVERTENCIA,
    }
    # Precedencia del punto 7: `sin_matriz` SIEMPRE se chequea antes que
    # `pendiente_de_planificacion`, sin importar si además faltan candidatos.
    resultado_tipos = _tipos_y_requisitos(session, tenant_id, commitment_id, oc)
    if resultado_tipos is None:
        salida["estado"] = "sin_matriz"
        salida["matriz"] = None
        salida["intervalos"] = []
        salida["causas"] = _causa_sin_evaluar(
            f"No hay matriz vigente para (cliente_id, locacion_id, tipo_servicio_id) al día de ingreso de la OC ({oc['vigencia_desde']})"
        )
        return salida
    if not conjunto["candidatos"]:
        # Hay matriz resuelta (si no, ya se salió arriba con `sin_matriz`) — se informa
        # igual: `pendiente_de_planificacion` es "falta el conjunto de sujetos", no "no
        # se sabe qué exige la OC". `matriz` sólo es `null` cuando el estado es `sin_matriz`.
        requisitos_por_tipo_pendiente, _nombres_pendiente, _clasif_pendiente, version_matriz_pendiente = resultado_tipos
        salida["estado"] = "pendiente_de_planificacion"
        salida["matriz"] = {**version_matriz_pendiente, "tipos_exigidos": sorted(requisitos_por_tipo_pendiente)}
        salida["intervalos"] = []
        salida["causas"] = _causa_sin_evaluar("No hay decisión visible para esta OC ni candidatos en el alcance de quien consulta")
        return salida
    if vigencia_ya_finalizada:
        # Hay matriz Y candidatos (si no, ya se salió arriba) — lo único que falta es una
        # ventana real que evaluar: la vigencia de la OC ya terminó antes de `desde`.
        requisitos_por_tipo_vf, _nombres_vf, _clasif_vf, version_matriz_vf = resultado_tipos
        salida["estado"] = "vigencia_finalizada"
        salida["matriz"] = {**version_matriz_vf, "tipos_exigidos": sorted(requisitos_por_tipo_vf)}
        salida["intervalos"] = []
        salida["causas"] = _causa_sin_evaluar("La vigencia de la OC ya terminó antes del inicio de la ventana evaluada")
        return salida

    requisitos_por_tipo, nombres, clasificaciones, version_matriz = resultado_tipos
    definiciones = definiciones_de(session, tenant_id, [r for reqs in requisitos_por_tipo.values() for r in reqs])
    # B-06: acota a los candidatos de ESTA OC, no a todo el tenant con ese requisito.
    evidencias = cargar_evidencias(session, tenant_id, definiciones, [c.sujeto_id for c in conjunto["candidatos"]])
    constancias = cargar_constancias(session, tenant_id, str(oc["cliente_id"]), date.min)
    excepciones = cargar_excepciones(session, tenant_id, commitment_id, date.min)
    intervalos = calcular_intervalos(
        conjunto["candidatos"], requisitos_por_tipo, nombres, evidencias, desde, hasta,
        clasificaciones=clasificaciones, constancias=constancias, excepciones=excepciones,
        cliente_id=str(oc["cliente_id"]), commitment_id=commitment_id,
    )
    estado, _primer_quiebre, _motivos = _resumen_desde_intervalos(intervalos)
    salida["matriz"] = {**version_matriz, "tipos_exigidos": sorted(requisitos_por_tipo)}
    salida["estado"] = estado
    salida["intervalos"] = [_intervalo_a_dict(i) for i in intervalos]
    if detalle == "diario":
        estado_por_dia: dict[str, str] = {}
        for i in intervalos:
            dia = i.desde
            while dia <= i.hasta:
                estado_por_dia[dia.isoformat()] = i.estado
                dia += timedelta(days=1)
        salida["estado_por_dia"] = estado_por_dia
    return salida


# --------------------------------------------------------------------------- proyeccion_documental_backlog


def proyeccion_documental_backlog(
    session: Session, identidad: Identidad, p: Pagina, *,
    estado_oc: str = "activo", estados: list[str] | None = None, horizonte_dias: int = 30,
) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_PROYECCION)
    if estado_oc not in ("activo", "cancelado"):
        raise ErrorDeDominio("estado_oc inválido", {"estado_oc": estado_oc, "validos": ["activo", "cancelado"]})
    if horizonte_dias > LIMITE_DIAS:
        raise ErrorDeDominio("`horizonte_dias` no puede superar 366", {"horizonte_dias": horizonte_dias}, codigo="rango_temporal_excedido")
    if estados:
        invalidos = [e for e in estados if e not in ESTADOS_RESUMEN]
        if invalidos:
            raise ErrorDeDominio("estado inválido", {"invalidos": invalidos, "validos": list(ESTADOS_RESUMEN)})

    tenant_id = identidad.tenant_id
    hoy = hoy_del_tenant(session, tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)

    ocs = session.execute(
        text(
            "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta "
            "FROM modulo1.oc WHERE tenant_id = :t AND estado = :eo ORDER BY clave_origen"
        ),
        {"t": tenant_id, "eo": estado_oc},
    ).mappings().all()

    items: list[dict[str, Any]] = []
    for oc in ocs:
        oc = dict(oc)
        commitment_id = oc["clave_origen"]
        conjunto = conjunto_de_sujetos(session, identidad, commitment_id, hoy)
        # Alcance por OC (punto 10): sólo entra si al menos un candidato del conjunto está
        # en el universo de quien consulta — nunca se sustituye por "sin datos".
        if alcance is not None and not (set(conjunto["sujeto_ids"]) & set(alcance)):
            continue
        desde = max(hoy, oc["vigencia_desde"])
        hasta = min(oc["vigencia_hasta"], desde + timedelta(days=horizonte_dias))
        fila: dict[str, Any] = {
            "commitment_id": commitment_id,
            "referencia": f"oc:{commitment_id}",
            # B-05: para que el frontend arme "OC 45000218 · Cliente Norte" sin otro GET.
            "oc_referencia": oc["referencia"],
            "cliente_id": str(oc["cliente_id"]), "locacion_id": str(oc["locacion_id"]),
            "vigencia_desde": oc["vigencia_desde"], "vigencia_hasta": oc["vigencia_hasta"],
            "origen_calculo": conjunto["origen"],
        }
        # Precedencia del punto 7: `sin_matriz` antes que `pendiente_de_planificacion`.
        resultado_tipos = _tipos_y_requisitos(session, tenant_id, commitment_id, oc)
        if resultado_tipos is None:
            fila["estado"] = "sin_matriz"
            fila["primer_quiebre"] = None
            fila["capacidad_documental_potencial_hoy"] = {}
            fila["motivos_resumidos"] = ["No hay matriz vigente para (cliente_id, locacion_id, tipo_servicio_id) al día de ingreso de la OC"]
        elif not conjunto["candidatos"]:
            fila["estado"] = "pendiente_de_planificacion"
            fila["primer_quiebre"] = None
            fila["capacidad_documental_potencial_hoy"] = {}
            fila["motivos_resumidos"] = ["No hay decisión visible para esta OC ni candidatos en el alcance de quien consulta"]
        elif hasta < desde:
            # OC activa cuya ventana ya terminó antes de `desde` (punto 10): sin intervalos
            # que calcular. B-07: esto NO es "todavía no hay candidatos/decisión" —
            # `pendiente_de_planificacion` mentía semánticamente acá (auditoría externa
            # 2026-09-22) — es un estado propio, estructural, igual que `sin_matriz`.
            fila["estado"] = "vigencia_finalizada"
            fila["primer_quiebre"] = None
            fila["capacidad_documental_potencial_hoy"] = {}
            fila["motivos_resumidos"] = ["La vigencia de la OC ya terminó antes del inicio de la ventana evaluada"]
        else:
            requisitos_por_tipo, nombres, clasificaciones, _ = resultado_tipos
            definiciones = definiciones_de(session, tenant_id, [r for reqs in requisitos_por_tipo.values() for r in reqs])
            # B-06: acota a los candidatos de ESTA OC, no a todo el tenant con ese requisito.
            evidencias = cargar_evidencias(session, tenant_id, definiciones, [c.sujeto_id for c in conjunto["candidatos"]])
            constancias = cargar_constancias(session, tenant_id, str(oc["cliente_id"]), date.min)
            excepciones = cargar_excepciones(session, tenant_id, commitment_id, date.min)
            intervalos = calcular_intervalos(
                conjunto["candidatos"], requisitos_por_tipo, nombres, evidencias, desde, hasta,
                clasificaciones=clasificaciones, constancias=constancias, excepciones=excepciones,
                cliente_id=str(oc["cliente_id"]), commitment_id=commitment_id,
            )
            estado, primer_quiebre, motivos = _resumen_desde_intervalos(intervalos)
            fila["estado"] = estado
            fila["primer_quiebre"] = primer_quiebre
            fila["capacidad_documental_potencial_hoy"] = intervalos[0].capacidad_documental_potencial
            fila["motivos_resumidos"] = motivos
        if estados and fila["estado"] not in estados:
            continue
        items.append(fila)

    total = len(items)
    pagina = items[p.offset: p.offset + p.limit]
    salida = envolver(pagina, total, p)
    salida["hoy"] = hoy
    salida["horizonte_dias"] = horizonte_dias
    salida["advertencia"] = ADVERTENCIA
    return salida


# --------------------------------------------------------------------------- detalle_proyeccion_documental (Q-DOC-03)


def _oc_activas_superpuestas(session: Session, tenant_id: str, desde: date, hasta: date) -> list[dict[str, Any]]:
    """OC activas cuya vigencia se superpone con `[desde, hasta]` — mismo universo por
    defecto que `proyeccion_documental_backlog` (`estado_oc='activo'`)."""
    filas = session.execute(
        text(
            "SELECT oc_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, vigencia_desde, vigencia_hasta "
            "FROM modulo1.oc WHERE tenant_id = :t AND estado = 'activo' "
            "AND vigencia_desde <= :hasta AND vigencia_hasta >= :desde ORDER BY clave_origen"
        ),
        {"t": tenant_id, "desde": desde, "hasta": hasta},
    ).mappings().all()
    return [dict(f) for f in filas]


def _matrices_aplicables(
    session: Session, identidad: Identidad, tenant_id: str, hoy: date,
    sujeto_id: str, tipo_sujeto: str, requisito_definicion_id: str | None,
    vigente_desde: date, vigente_hasta: date,
) -> list[dict[str, Any]]:
    """Punto 15.2: para cada OC activa candidata, reutiliza `conjunto_de_sujetos` (4.1/4.2)
    y `_tipos_y_requisitos` (motor por OC) tal cual existen — ninguna regla nueva, sólo se
    los invoca con `sujeto_id`/`requisito_definicion_id` fijos en vez de recorrer todos."""
    if requisito_definicion_id is None:
        return []
    matches: list[dict[str, Any]] = []
    for oc in _oc_activas_superpuestas(session, tenant_id, vigente_desde, vigente_hasta):
        commitment_id = oc["clave_origen"]
        conjunto = conjunto_de_sujetos(session, identidad, commitment_id, hoy)
        if sujeto_id not in conjunto["sujeto_ids"]:
            continue
        resultado_tipos = _tipos_y_requisitos(session, tenant_id, commitment_id, oc)
        if resultado_tipos is None:
            continue
        requisitos_por_tipo, _nombres, _clasificaciones, version_matriz = resultado_tipos
        if requisito_definicion_id in requisitos_por_tipo.get(tipo_sujeto, []):
            matches.append({
                "commitment_id": commitment_id,
                "matriz_version_id": version_matriz["matriz_version_id"],
                "version": version_matriz["version"],
                "origen_calculo": conjunto["origen"],
            })
    return matches


def _detalle_evidencia(session: Session, identidad: Identidad, referencia: str) -> dict[str, Any]:
    identidad.exigir_rol(*ROLES_CALENDARIO)
    resto = referencia[len("evidencia:"):]
    partes = resto.split(":", 1)
    if len(partes) != 2 or partes[0] not in ("documento", "competencia", "induccion") or not partes[1]:
        raise ErrorDeDominio("referencia inválida", {"referencia": referencia})
    categoria, id_ = partes
    tenant_id = identidad.tenant_id
    hoy = hoy_del_tenant(session, tenant_id)
    fila = session.execute(
        text(_SQL_CALENDARIO + "SELECT * FROM evidencia WHERE categoria = :categoria AND id::text = :id"),
        {"t": tenant_id, "categoria": categoria, "id": id_},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Evidencia inexistente", {"referencia": referencia})
    alcance = alcance_de_sujetos(session, identidad, hoy)
    if alcance is not None and fila["sujeto_id"] not in alcance:
        # Nunca 403: no se revela que el recurso existe fuera del alcance propio.
        raise NoEncontrado("Evidencia inexistente", {"referencia": referencia})
    d = dict(fila)
    requisito_definicion_id = str(d["requisito_definicion_id"]) if d["requisito_definicion_id"] is not None else None
    matrices = _matrices_aplicables(
        session, identidad, tenant_id, hoy, d["sujeto_id"], d["tipo_sujeto"],
        requisito_definicion_id, d["vigente_desde"], d["vigente_hasta"],
    )
    return {
        "tipo": "evidencia",
        "referencia": referencia,
        "categoria": d["categoria"],
        "id": str(d["id"]),
        "sujeto_id": d["sujeto_id"],
        "tipo_sujeto": d["tipo_sujeto"],
        "identificador_natural": d["identificador_natural"],
        "requisito_definicion_id": requisito_definicion_id,
        "requisito": d["requisito"],
        "vigente_desde": d["vigente_desde"],
        "vigente_hasta": d["vigente_hasta"],
        "estado_confirmacion": d["estado_confirmacion"],
        "archivo_validacion": d["archivo_validacion"],
        "hoy": hoy,
        "aplicabilidad": "exigida_por_oc" if matrices else "informativa",
        "matrices_aplicables": matrices,
        "advertencia": ADVERTENCIA,
    }


def _detalle_oc(session: Session, identidad: Identidad, referencia: str) -> dict[str, Any]:
    commitment_id = referencia[len("oc:"):]
    salida = proyeccion_documental(session, identidad, commitment_id)
    salida["tipo"] = "oc"
    salida["referencia"] = referencia
    return salida


def detalle_proyeccion_documental(session: Session, identidad: Identidad, referencia: str) -> dict[str, Any]:
    """Punto 15: detalle genérico por referencia opaca, emitida sin cambios por
    `calendario_vigencias` (`evidencia:{categoria}:{id}`) y por `proyeccion_documental`/
    `proyeccion_documental_backlog` (`oc:{commitment_id}`). El rol se valida DESPUÉS de
    parsear el prefijo, nunca antes."""
    if referencia.startswith("evidencia:"):
        return _detalle_evidencia(session, identidad, referencia)
    if referencia.startswith("oc:"):
        return _detalle_oc(session, identidad, referencia)
    raise ErrorDeDominio("referencia inválida", {"referencia": referencia})
