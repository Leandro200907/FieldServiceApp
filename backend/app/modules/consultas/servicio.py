"""Servicios de lectura documental e históricos internos.

Las funciones vinculadas con cobertura, decisiones y supervisión ya no están publicadas
por el router de Módulo 1. Se conservan temporalmente como lógica interna para alertas,
revaluación y una futura integración explícita con Módulo 2. "Hoy" siempre es
`hoy_del_tenant` y `vigente_hasta` es inclusivo.
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
from app.modules.consultas.backlog_documental import evaluar_oc_backlog
from app.modules.oc.catalogos_maestros import nombres_oc


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
    hasta: date | None = fila["vigente_hasta"]
    salida = _plano(fila)
    salida["vigente_hoy"] = desde <= hoy and (hasta is None or hoy <= hasta)
    salida["dias_para_vencer"] = (hasta - hoy).days if hasta is not None else None
    salida["vencido"] = hasta is not None and hasta < hoy
    return salida


# Evidencia vigente unificada físicamente en `documento`; la categoría del requisito
# conserva la forma de respuesta histórica para no romper consumidores.
_SQL_EVIDENCIA = """
    WITH evidencia AS (
        SELECT CASE r.categoria WHEN 'competencia' THEN 'acreditacion'
                                WHEN 'induccion' THEN 'induccion'
                                ELSE 'documento' END AS tipo,
               d.documento_id AS id, d.sujeto_id, d.requisito_definicion_id,
               r.nombre AS requisito, r.categoria, d.vigente_desde, d.vigente_hasta,
               d.estado_confirmacion, d.origen_propuesta, d.locacion_id,
               l.identificador_natural
        FROM modulo1.documento d
        LEFT JOIN modulo1.definicion_requisito r
          ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
        LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
        WHERE d.estado_version = 'vigente'
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

    from app.core.consulta_documental import resumen_legajo_con_en_regla
    from app.modules.consultas.presentacion_evidencia import filas_evidencia_para_legajo

    datos = session.execute(
        text(
            "SELECT legajo_id, sujeto_id, tipo_sujeto, identificador_natural, nombre_apellido, dado_de_baja_en, creado_en "
            "FROM modulo1.legajo WHERE sujeto_id = :s"
        ),
        {"s": sujeto_id},
    ).mappings().first()
    if datos is None:
        raise NoEncontrado("Legajo inexistente", {"sujeto_id": sujeto_id})

    items = filas_evidencia_para_legajo(session, identidad.tenant_id, sujeto_id, hoy)
    from app.modules.consultas.presentacion_evidencia import adjuntar_rechazos_operadora

    adjuntar_rechazos_operadora(session, identidad.tenant_id, items)
    from app.modules.consultas.legajo_exigidos import fusionar_legajo_con_exigidos

    datos_legajo = _plano(datos)
    items, resumen_ex = fusionar_legajo_con_exigidos(session, identidad, sujeto_id, datos_legajo, items, hoy)
    from app.modules.consultas.ficha_legajo import enriquecer_items_ficha_legajo

    enriquecer_items_ficha_legajo(session, identidad.tenant_id, items, hoy)
    from app.modules.consultas.legajo_exigidos import reaplicar_gestion_responsable_respaldo

    reaplicar_gestion_responsable_respaldo(items)
    resumen = resumen_legajo_con_en_regla(items)
    resumen.update(resumen_ex)
    return {
        "hoy": hoy.isoformat(),
        "legajo": _plano(datos),
        "documentos": [i for i in items if i["tipo"] == "documento"],
        "acreditaciones": [i for i in items if i["tipo"] == "acreditacion"],
        "inducciones": [i for i in items if i["tipo"] == "induccion"],
        "resumen": resumen,
    }


def propuestas_pendientes(session: Session, identidad: Identidad, p: Pagina) -> dict[str, Any]:
    """Documentos propuestos por técnicos que esperan Confirmar/Rechazar."""
    from app.modules.consultas.presentacion_evidencia import EXPLICACION_ESTADO, enriquecer_fila_evidencia, _cargar_plazo_tenant

    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    plazo_tenant = _cargar_plazo_tenant(session, identidad.tenant_id)
    condicion = "WHERE d.estado_version = 'propuesta' AND d.estado_confirmacion = 'declarado'"
    total = session.execute(text(f"SELECT count(*) FROM modulo1.documento d {condicion}")).scalar()
    filas = session.execute(
        text(
            "SELECT d.documento_id, d.sujeto_id, l.tipo_sujeto, l.identificador_natural, l.nombre_apellido, "
            "d.requisito_definicion_id, r.nombre AS requisito, d.numero, "
            "d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, d.origen, d.confianza_extraccion, d.creado_en, "
            "d.origen_propuesta, d.estado_version, d.archivo_estado, d.archivo_validacion, d.clave_storage, "
            "r.plazo_aviso_dias "
            "FROM modulo1.documento d "
            "LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = d.requisito_definicion_id "
            "LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id "
            f"{condicion} ORDER BY d.creado_en, d.documento_id OFFSET :off LIMIT :lim"
        ),
        {"off": p.offset, "lim": p.limit},
    ).mappings().all()
    items: list[dict[str, Any]] = []
    for f in filas:
        base = _con_vigencia(dict(f), hoy)
        fila_pres = {
            **dict(f),
            "estado_confirmacion": f["estado_confirmacion"],
            "origen_propuesta": True,
            "vencido": base["vencido"],
        }
        enriquecida = enriquecer_fila_evidencia(fila_pres, hoy, plazo_tenant)
        base["estado_presentacion"] = "propuesta_en_revision"
        base["estado_presentacion_explicacion"] = EXPLICACION_ESTADO["propuesta_en_revision"]
        base["archivo_validacion"] = enriquecida.get("archivo_validacion")
        items.append(base)
    return envolver(items, int(total or 0), p)


def tablero_vencimientos(session: Session, identidad: Identidad, dias: int, p: Pagina) -> dict[str, Any]:
    """Evidencia vigente que vence dentro de `dias` (inclusive) o ya venció, ordenada por
    `vigente_hasta`. responsable_legajos: toda la empresa; supervisor: su universo."""
    from app.modules.consultas.presentacion_evidencia import filas_evidencia_para_legajo

    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    if dias < 0:
        raise ErrorDeDominio("dias debe ser >= 0", {"dias": dias})
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    limite = hoy + timedelta(days=dias)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = "WHERE tenant_id = :t AND dado_de_baja_en IS NULL"
    if alcance is not None:
        params["alcance"] = list(alcance)
        cond += " AND sujeto_id = ANY(CAST(:alcance AS text[]))"
    sujetos = session.execute(
        text(f"SELECT sujeto_id FROM modulo1.legajo {cond}"),
        params,
    ).scalars().all()
    items: list[dict[str, Any]] = []
    for sid in sujetos:
        items.extend(filas_evidencia_para_legajo(session, identidad.tenant_id, sid, hoy))
    items = [i for i in items if i.get("vigente_hasta") and date.fromisoformat(i["vigente_hasta"]) <= limite]
    items.sort(key=lambda i: (i["vigente_hasta"], i["sujeto_id"], i.get("tipo") or ""))
    total = len(items)
    paginados = items[p.offset : p.offset + p.limit]
    salida = envolver(paginados, total, p)
    salida["hoy"] = hoy.isoformat()
    salida["hasta"] = limite.isoformat()
    return salida


def _evaluar_cobertura_oc(
    session: Session,
    identidad: Identidad,
    clave_origen: str,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Devuelve (fila_oc, evaluación_viva, sin_matriz). Modo consulta; no persiste."""
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    alcance = alcance_de_sujetos(session, identidad, hoy)
    try:
        ev = cobertura_de_oc(session, identidad.tenant_id, clave_origen, ahora_utc(), candidatos=alcance)
        oc = session.execute(
            text(
                "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
                "estado, vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE clave_origen = :c"
            ),
            {"c": clave_origen},
        ).mappings().first()
        return dict(oc or {}), ev, False
    except ErrorDeDominio as exc:
        if exc.codigo != "sin_matriz_vigente":
            raise
        oc = session.execute(
            text(
                "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
                "estado, vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE clave_origen = :c"
            ),
            {"c": clave_origen},
        ).mappings().first()
        if oc is None:
            raise NoEncontrado("OC inexistente", {"commitment_id": clave_origen}) from exc
        return dict(oc), {"por_sujeto": [], "requisitos_faltantes": [], "resultado_de_decision": "no_puede_asignarse"}, True


def _rango_mes(mes: str) -> tuple[date, date]:
    """`mes` = YYYY-MM → primer y último día del mes."""
    try:
        anio_s, mes_s = mes.split("-", 1)
        anio, mes_i = int(anio_s), int(mes_s)
        if mes_i < 1 or mes_i > 12:
            raise ValueError
    except ValueError as exc:
        raise ErrorDeDominio("mes inválido (use YYYY-MM)", {"mes": mes}) from exc
    desde = date(anio, mes_i, 1)
    if mes_i == 12:
        hasta = date(anio, 12, 31)
    else:
        hasta = date(anio, mes_i + 1, 1) - timedelta(days=1)
    return desde, hasta


def _oc_reprogramada(session: Session, oc_id: str) -> bool:
    n = session.execute(
        text(
            "SELECT count(*) FROM modulo1.event_log "
            "WHERE tipo = 'CompromisoModificado' AND payload->>'oc_id' = :id"
        ),
        {"id": oc_id},
    ).scalar()
    return int(n or 0) > 0


def _enriquecer_backlog(
    session: Session,
    identidad: Identidad,
    fila: Any,
    *,
    hasta_eval: date | None = None,
) -> dict[str, Any]:
    d = _plano(fila)
    oc_datos = {
        "clave_origen": fila["clave_origen"],
        "cliente_id": str(fila["cliente_id"]),
        "locacion_id": str(fila["locacion_id"]),
        "tipo_servicio_id": str(fila["tipo_servicio_id"]),
        "vigencia_desde": fila["vigencia_desde"],
        "vigencia_hasta": fila["vigencia_hasta"],
    }
    evaluacion = evaluar_oc_backlog(session, identidad, oc_datos, hasta_filtro=hasta_eval)
    pq = evaluacion.get("primer_quiebre_documental")
    if pq is not None and hasattr(pq, "isoformat"):
        evaluacion = {**evaluacion, "primer_quiebre_documental": pq.isoformat()}
    d.update(nombres_oc(session, identidad.tenant_id, d["cliente_id"], d["locacion_id"], d["tipo_servicio_id"]))
    d.update(evaluacion)
    d["modo"] = "consulta"
    d["reprogramada"] = _oc_reprogramada(session, d["oc_id"])
    if "origen_oc" in fila.keys():
        d["origen_oc"] = fila["origen_oc"]
    return d


def backlog_oc(
    session: Session,
    identidad: Identidad,
    p: Pagina,
    *,
    estado: str | None = "activo",
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
    mes: str | None = None,
    q: str | None = None,
    operadora_id: list[str] | None = None,
    locacion_id: str | None = None,
    tipo_recurso: str | None = None,
    solo_con_alertas: bool | None = None,
    solo_reprogramadas: bool | None = None,
) -> dict[str, Any]:
    """Backlog de OC en modo consulta (D-E): alertas ciertas, sin veredicto de cobertura."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    from app.core.ventana_backlog import rango_backlog_documental

    _, eval_hasta = rango_backlog_documental(
        session, identidad.tenant_id, hoy, vigencia_desde=vigencia_desde, vigencia_hasta=vigencia_hasta,
    )
    if estado and estado not in ("activo", "cancelado"):
        raise ErrorDeDominio("estado inválido", {"estado": estado, "validos": ["activo", "cancelado"]})
    if vigencia_desde is None:
        vigencia_desde = hoy
    if mes:
        m_desde, m_hasta = _rango_mes(mes)
        vigencia_desde = m_desde if vigencia_desde is None else max(vigencia_desde, m_desde)
        vigencia_hasta = m_hasta if vigencia_hasta is None else min(vigencia_hasta, m_hasta)

    condiciones: list[str] = []
    params: dict[str, Any] = {}
    if estado:
        condiciones.append("o.estado = :estado")
        params["estado"] = estado
    if vigencia_desde:
        condiciones.append("o.vigencia_hasta >= :vdesde")
        params["vdesde"] = vigencia_desde
    if vigencia_hasta:
        condiciones.append("o.vigencia_desde <= :vhasta")
        params["vhasta"] = vigencia_hasta
    if q:
        condiciones.append("(o.clave_origen ILIKE :q OR o.referencia ILIKE :q)")
        params["q"] = f"%{q.strip()}%"
    if operadora_id:
        condiciones.append("o.cliente_id = ANY(CAST(:ops AS uuid[]))")
        params["ops"] = operadora_id
    if locacion_id:
        condiciones.append("o.locacion_id = CAST(:loc AS uuid)")
        params["loc"] = locacion_id
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    def _filtrar_post(item: dict[str, Any]) -> bool:
        if solo_con_alertas and not item.get("tiene_alertas"):
            return False
        if solo_reprogramadas and not item.get("reprogramada"):
            return False
        if tipo_recurso:
            tipos = {a.get("tipo_sujeto") for a in item.get("alertas_ciertas", []) if a.get("tipo_sujeto")}
            disp = item.get("disponibilidad_por_tipo") or []
            if tipo_recurso not in tipos and not any(d.get("tipo_sujeto") == tipo_recurso for d in disp):
                return False
        return True

    necesita_post = bool(solo_con_alertas or solo_reprogramadas or tipo_recurso)
    if necesita_post:
        total = 0
        items: list[dict[str, Any]] = []
        cursor = 0
        lote = 50
        while True:
            filas = session.execute(
                text(
                    f"SELECT o.oc_id, o.clave_origen, o.referencia, o.cliente_id, o.locacion_id, o.tipo_servicio_id, "
                    f"o.vigencia_desde, o.vigencia_hasta, o.estado, o.lote_id, o.origen_oc, o.creado_en, o.actualizado_en "
                    f"FROM modulo1.oc o {where} ORDER BY o.vigencia_desde, o.clave_origen OFFSET :off LIMIT :lim"
                ),
                {**params, "off": cursor, "lim": lote},
            ).mappings().all()
            if not filas:
                break
            for f in filas:
                fin_oc = min(f["vigencia_hasta"], eval_hasta)
                item = _enriquecer_backlog(session, identidad, f, hasta_eval=fin_oc)
                if not _filtrar_post(item):
                    continue
                if total >= p.offset and len(items) < p.limit:
                    items.append(item)
                total += 1
            cursor += len(filas)
            if len(filas) < lote:
                break
        return envolver(items, total, p)

    total = session.execute(text(f"SELECT count(*) FROM modulo1.oc o {where}"), params).scalar()
    filas = session.execute(
        text(
            f"SELECT o.oc_id, o.clave_origen, o.referencia, o.cliente_id, o.locacion_id, o.tipo_servicio_id, "
            f"o.vigencia_desde, o.vigencia_hasta, o.estado, o.lote_id, o.origen_oc, o.creado_en, o.actualizado_en "
            f"FROM modulo1.oc o {where} ORDER BY o.vigencia_desde, o.clave_origen OFFSET :off LIMIT :lim"
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    items = [
        _enriquecer_backlog(
            session,
            identidad,
            f,
            hasta_eval=min(f["vigencia_hasta"], eval_hasta),
        )
        for f in filas
    ]
    return envolver(items, int(total or 0), p)


def cobertura_oc(
    session: Session,
    identidad: Identidad,
    *,
    commitment_id: str | None = None,
    oc_id: str | None = None,
) -> dict[str, Any]:
    """Detalle de cobertura en vivo de una OC (modo consulta)."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    if oc_id and not commitment_id:
        fila = session.execute(
            text("SELECT clave_origen FROM modulo1.oc WHERE oc_id = CAST(:id AS uuid)"),
            {"id": oc_id},
        ).scalar()
        if fila is None:
            raise NoEncontrado("OC inexistente", {"oc_id": oc_id})
        commitment_id = str(fila)
    if not commitment_id:
        raise ErrorDeDominio("Indique oc_id o commitment_id (clave_origen)")
    oc = session.execute(
        text(
            "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
            "estado, vigencia_desde, vigencia_hasta FROM modulo1.oc WHERE clave_origen = :c"
        ),
        {"c": commitment_id},
    ).mappings().first()
    if oc is None:
        raise NoEncontrado("OC inexistente", {"commitment_id": commitment_id})
    oc_plano = _plano(oc)
    evaluacion = evaluar_oc_backlog(
        session,
        identidad,
        {
            "clave_origen": oc["clave_origen"],
            "cliente_id": str(oc["cliente_id"]),
            "locacion_id": str(oc["locacion_id"]),
            "tipo_servicio_id": str(oc["tipo_servicio_id"]),
            "vigencia_desde": oc["vigencia_desde"],
            "vigencia_hasta": oc["vigencia_hasta"],
        },
    )
    oc_plano.update(nombres_oc(session, identidad.tenant_id, oc_plano["cliente_id"], oc_plano["locacion_id"], oc_plano["tipo_servicio_id"]))
    historial = session.execute(
        text(
            "SELECT ocurrido_en, payload FROM modulo1.event_log "
            "WHERE tipo = 'CompromisoModificado' AND payload->>'commitment_id' = :c ORDER BY ocurrido_en"
        ),
        {"c": commitment_id},
    ).mappings().all()
    return {
        "commitment_id": commitment_id,
        "oc": oc_plano,
        "modo": "consulta",
        "reprogramada": len(historial) > 0,
        "historial_compromiso": [
            {
                "fecha": h["ocurrido_en"].isoformat(),
                "motivo": (h["payload"] or {}).get("motivo"),
                "origen": (h["payload"] or {}).get("origen", "planilla"),
                "anterior": (h["payload"] or {}).get("anterior"),
                "nuevo": (h["payload"] or {}).get("nuevo"),
            }
            for h in historial
        ],
        **evaluacion,
    }


def _fecha_desde_cuando_bloquea(
    hoy: date,
    oc: dict[str, Any],
    req: dict[str, Any],
    fallback: date,
) -> date:
    from app.core.consulta_documental import fecha_desde_cuando_bloquea

    return fecha_desde_cuando_bloquea(hoy, oc, req, fallback)


def acciones_pendientes(
    session: Session,
    identidad: Identidad,
    p: Pagina,
    *,
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
    mes: str | None = None,
    q: str | None = None,
    operadora_id: list[str] | None = None,
    locacion_id: str | None = None,
    tipo_recurso: str | None = None,
) -> dict[str, Any]:
    """Renovaciones/regularizaciones que afectan OCs activas (modo consulta)."""
    from app.core.consulta_documental import (
        accion_sugerida_para_req,
        cargar_propuestas_pendientes,
        efecto_accion_documental,
        fecha_desde_cuando_bloquea,
        ventana_evaluacion_oc,
    )
    from app.modules.consultas.ocs_afectadas import ordenar_ocs_afectadas, referencia_oc
    from app.modules.proyeccion import radar as radar_mod

    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    from app.core.ventana_backlog import rango_backlog_documental

    hoy = hoy_del_tenant(session, identidad.tenant_id)
    desde, hasta = rango_backlog_documental(
        session, identidad.tenant_id, hoy, vigencia_desde=vigencia_desde, vigencia_hasta=vigencia_hasta,
    )
    propuestas = cargar_propuestas_pendientes(session, identidad.tenant_id)
    if mes:
        m_desde, m_hasta = _rango_mes(mes)
        desde, hasta = m_desde, m_hasta
    from app.core.consulta_documental import cargar_entregas_operadora

    legajos = radar_mod._legajos_visibles(session, identidad)
    evidencias = radar_mod._evidencias(session, identidad.tenant_id)
    entregas = cargar_entregas_operadora(session, identidad.tenant_id)
    filtros = {"q": q, "locacion_id": locacion_id}
    if operadora_id and len(operadora_id) == 1:
        filtros["cliente_id"] = operadora_id[0]
    ocs = radar_mod._ocs(session, identidad.tenant_id, max(desde, hoy), hasta, filtros, offset=0, limit=500)
    if operadora_id and len(operadora_id) > 1:
        permitidos = set(operadora_id)
        ocs = [o for o in ocs if str(o["cliente_id"]) in permitidos]
    agrupadas: dict[tuple[str, str], dict[str, Any]] = {}
    estados_accion = {
        "vence_durante_periodo",
        "vencido_antes_inicio",
        "faltante",
        "evidencia_invalida",
        "pendiente_revision",
    }
    for oc in ocs:
        inicio, fin = ventana_evaluacion_oc(hoy, oc, hasta_filtro=min(hasta, oc["vigencia_hasta"]))
        oc_eval = {
            "clave_origen": oc["clave_origen"],
            "cliente_id": str(oc["cliente_id"]),
            "locacion_id": str(oc["locacion_id"]),
            "tipo_servicio_id": str(oc["tipo_servicio_id"]),
            "vigencia_desde": oc["vigencia_desde"],
            "vigencia_hasta": oc["vigencia_hasta"],
        }
        eval_oc = evaluar_oc_backlog(session, identidad, oc_eval, hasta_filtro=fin)
        if eval_oc.get("estado_documental") == "sin_matriz":
            continue
        op_id = str(oc["cliente_id"])
        calc = radar_mod._evaluar_oc(
            session,
            identidad.tenant_id,
            oc,
            legajos,
            evidencias,
            inicio,
            fin,
            entregas=entregas,
            operadora_id=op_id,
        )
        genera_alerta = eval_oc.get("tiene_alertas")
        for leg in calc["legajos"]:
            if tipo_recurso and leg["tipo_sujeto"] != tipo_recurso:
                continue
            for req in leg.get("requisitos") or []:
                if req.get("estado") not in estados_accion and not req.get("es_rechazo_operadora"):
                    continue
                rid = str(req.get("requisito_definicion_id") or "")
                if not rid:
                    continue
                accion = accion_sugerida_para_req(
                    req,
                    propuestas_pendientes=propuestas,
                    sujeto_id=leg["sujeto_id"],
                    requisito_definicion_id=rid,
                )
                if not accion:
                    continue
                fb = fecha_desde_cuando_bloquea(hoy, oc, req, inicio)
                fecha_limite = fb.isoformat()
                fecha_accion = req.get("accion_sugerida_fecha")
                if hasattr(fecha_accion, "isoformat"):
                    fecha_accion = fecha_accion.isoformat()
                elif fecha_accion is not None:
                    fecha_accion = str(fecha_accion)
                clave = (leg["sujeto_id"], rid)
                oc_ref = referencia_oc(oc)
                efecto = efecto_accion_documental(hoy, oc, req, inicio)
                if clave in agrupadas:
                    item = agrupadas[clave]
                    if oc_ref not in item["ocs_afectadas"]:
                        item["ocs_afectadas"].append(oc_ref)
                    item["genera_alerta_cierta"] = bool(item["genera_alerta_cierta"] or genera_alerta)
                    if fecha_limite < item["fecha_limite"]:
                        item["fecha_limite"] = fecha_limite
                        item["efecto"] = efecto
                    if fecha_accion and (not item["accion_sugerida_fecha"] or fecha_accion < item["accion_sugerida_fecha"]):
                        item["accion_sugerida_fecha"] = fecha_accion
                    continue
                agrupadas[clave] = {
                    "requisito": req.get("nombre"),
                    "requisito_definicion_id": rid,
                    "legajo_id": leg["sujeto_id"],
                    "legajo_nombre": leg.get("nombre_apellido") or leg.get("identificador_natural") or leg["sujeto_id"],
                    "nombre_apellido": leg.get("nombre_apellido"),
                    "identificador_natural": leg.get("identificador_natural"),
                    "tipo_sujeto": leg["tipo_sujeto"],
                    "fecha_limite": fecha_limite,
                    "accion_sugerida": accion,
                    "accion_sugerida_fecha": fecha_accion,
                    "ocs_afectadas": [oc_ref],
                    "efecto": efecto,
                    "genera_alerta_cierta": genera_alerta,
                }
    hoy_acciones = hoy_del_tenant(session, identidad.tenant_id)
    for item in agrupadas.values():
        item["ocs_afectadas"] = ordenar_ocs_afectadas(item["ocs_afectadas"], hoy_acciones)
    acciones = list(agrupadas.values())
    acciones.sort(
        key=lambda a: (
            0 if a.get("genera_alerta_cierta") else 1,
            a.get("fecha_limite") or "",
            -len(a.get("ocs_afectadas") or []),
        )
    )
    total = len(acciones)
    pagina = acciones[p.offset : p.offset + p.limit]
    return envolver(pagina, total, p)


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
        condiciones.append("e.tipo = :tipo")
        params["tipo"] = tipo
    if desde is not None:
        condiciones.append("e.ocurrido_en >= :desde")
        params["desde"] = desde
    if hasta is not None:
        condiciones.append("e.ocurrido_en <= :hasta")
        params["hasta"] = hasta
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""
    total = session.execute(text(f"SELECT count(*) FROM modulo1.event_log e {where}"), params).scalar()
    filas = session.execute(
        text(
            f"SELECT e.id, e.evento_id, e.tipo, e.payload, e.ocurrido_en, u.nombre AS usuario_nombre "
            f"FROM modulo1.event_log e "
            f"LEFT JOIN modulo1.usuario u ON u.tenant_id = e.tenant_id "
            f"  AND u.usuario_id::text = e.payload->>'usuario_id' "
            f"{where} "
            "ORDER BY e.ocurrido_en DESC, e.id DESC OFFSET :off LIMIT :lim"
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    salida = []
    for f in filas:
        fila = _plano(f)
        uid = (fila.get("payload") or {}).get("usuario_id")
        if fila.get("usuario_nombre") is None and uid == "sistema":
            fila["usuario_nombre"] = "Sistema"
        fila["legajo_requisito_etiqueta"] = _etiqueta_legajo_requisito_auditoria(
            session, identidad.tenant_id, fila.get("tipo") or "", fila.get("payload") or {},
        )
        salida.append(fila)
    return envolver(salida, int(total or 0), p)


def _etiqueta_legajo_requisito_auditoria(
    session: Session,
    tenant_id: str,
    tipo: str,
    payload: dict[str, Any],
) -> str | None:
    if tipo == "OcSinMatriz":
        clave = payload.get("clave_origen")
        if clave:
            return f"OC {clave}"
        return None
    if tipo == "CumplimientoEmpresaAfectado":
        leg = session.execute(
            text(
                "SELECT identificador_natural FROM modulo1.legajo "
                "WHERE tenant_id = :t AND tipo_sujeto = 'empresa' LIMIT 1"
            ),
            {"t": tenant_id},
        ).scalar()
        empresa = leg or "Empresa"
        return f"{empresa} · Cumplimiento documental"
    if tipo == "EvidenciaAdjuntada":
        doc_id = payload.get("documento_id")
        if not doc_id:
            return None
        fila = session.execute(
            text(
                "SELECT d.sujeto_id, d.requisito_definicion_id, l.nombre_apellido, l.identificador_natural, "
                "l.tipo_sujeto, r.nombre AS requisito "
                "FROM modulo1.documento d "
                "LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id "
                "LEFT JOIN modulo1.definicion_requisito r ON r.requisito_definicion_id = d.requisito_definicion_id "
                "WHERE d.tenant_id = :t AND d.documento_id = CAST(:d AS uuid)"
            ),
            {"t": tenant_id, "d": str(doc_id)},
        ).mappings().first()
        if not fila:
            return None
        if fila["tipo_sujeto"] == "persona" and fila.get("nombre_apellido"):
            persona = fila["nombre_apellido"]
        else:
            persona = fila.get("identificador_natural") or str(fila["sujeto_id"])
        if fila.get("requisito"):
            return f"{persona} · {fila['requisito']}"
        return persona
    if tipo == "LocacionOcCreada":
        loc_id = payload.get("locacion_id")
        op_id = payload.get("operadora_id")
        if not loc_id or not op_id:
            return None
        fila = session.execute(
            text(
                "SELECT o.nombre AS operadora, l.nombre AS locacion "
                "FROM modulo1.locacion_oc l "
                "JOIN modulo1.operadora_documental o ON o.tenant_id = l.tenant_id AND o.operadora_id = l.operadora_id "
                "WHERE l.tenant_id = :t AND l.locacion_id = CAST(:l AS uuid)"
            ),
            {"t": tenant_id, "l": str(loc_id)},
        ).mappings().first()
        if fila:
            return f"{fila['operadora']} · {fila['locacion']}"
        return None
    sujeto_id = payload.get("sujeto_id")
    req_id = payload.get("requisito_definicion_id")
    if not sujeto_id:
        return None
    leg = session.execute(
        text(
            "SELECT nombre_apellido, identificador_natural, tipo_sujeto FROM modulo1.legajo "
            "WHERE tenant_id = :t AND sujeto_id = :s"
        ),
        {"t": tenant_id, "s": str(sujeto_id)},
    ).mappings().first()
    req_nombre = None
    if req_id:
        req_nombre = session.execute(
            text(
                "SELECT nombre FROM modulo1.definicion_requisito "
                "WHERE tenant_id = :t AND requisito_definicion_id = CAST(:r AS uuid)"
            ),
            {"t": tenant_id, "r": str(req_id)},
        ).scalar()
    if leg and leg["tipo_sujeto"] == "persona" and leg.get("nombre_apellido"):
        persona = leg["nombre_apellido"]
    else:
        persona = (leg or {}).get("identificador_natural") or str(sujeto_id)
    if req_nombre:
        return f"{persona} · {req_nombre}"
    return persona if persona else None


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


def incumplimiento_empresa(session: Session, identidad: Identidad) -> dict[str, Any]:
    """Estado actual del aviso de incumplimiento de empresa (2.9): lo consulta el
    consumidor de `CumplimientoEmpresaAfectado`, que es un aviso flaco sin causas."""
    from app.core.incumplimiento_empresa import estado_actual

    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    return {"aviso": _plano(estado_actual(session, identidad.tenant_id) or {}) or None}

