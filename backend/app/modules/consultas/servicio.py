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
from app.modules.consultas.cobertura_live import (
    candidatos_detalle,
    estado_cobertura_global,
    resumen_por_tipo,
)


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
               d.estado_confirmacion, d.origen_propuesta, d.locacion_id
        FROM modulo1.documento d
        LEFT JOIN modulo1.definicion_requisito r
          ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
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


def backlog_oc(
    session: Session,
    identidad: Identidad,
    p: Pagina,
    *,
    estado: str | None = "activo",
    estado_cobertura: str | None = None,
    vigencia_desde: date | None = None,
    vigencia_hasta: date | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    """Backlog de OC con cobertura en vivo (1.12 / D-A bis). Sin `ultima_decision`."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    estados_cov = ("cubierta", "no_cubierta", "sin_matriz", "empresa_bloquea")
    if estado_cobertura and estado_cobertura not in estados_cov:
        raise ErrorDeDominio("estado_cobertura inválido", {"validos": list(estados_cov)})
    if estado and estado not in ("activo", "cancelado"):
        raise ErrorDeDominio("estado inválido", {"estado": estado, "validos": ["activo", "cancelado"]})

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
    where = ("WHERE " + " AND ".join(condiciones)) if condiciones else ""

    def _enriquecer(fila: Any) -> dict[str, Any] | None:
        d = _plano(fila)
        clave = d["clave_origen"]
        _, ev, sin_matriz = _evaluar_cobertura_oc(session, identidad, clave)
        ec = estado_cobertura_global(ev, sin_matriz=sin_matriz)
        if estado_cobertura and ec != estado_cobertura:
            return None
        d["estado_cobertura"] = ec
        d["por_tipo"] = resumen_por_tipo(ev) if not sin_matriz else []
        d["modo"] = "consulta"
        return d

    if estado_cobertura:
        total = 0
        items: list[dict[str, Any]] = []
        cursor = 0
        lote = 50
        while True:
            filas = session.execute(
                text(
                    f"SELECT o.oc_id, o.clave_origen, o.referencia, o.cliente_id, o.locacion_id, o.tipo_servicio_id, "
                    f"o.vigencia_desde, o.vigencia_hasta, o.estado, o.lote_id, o.creado_en, o.actualizado_en "
                    f"FROM modulo1.oc o {where} ORDER BY o.vigencia_desde, o.clave_origen "
                    f"OFFSET :off LIMIT :lim"
                ),
                {**params, "off": cursor, "lim": lote},
            ).mappings().all()
            if not filas:
                break
            for f in filas:
                item = _enriquecer(f)
                if item is None:
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
            f"o.vigencia_desde, o.vigencia_hasta, o.estado, o.lote_id, o.creado_en, o.actualizado_en "
            f"FROM modulo1.oc o {where} ORDER BY o.vigencia_desde, o.clave_origen OFFSET :off LIMIT :lim"
        ),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    items = [_enriquecer(f) for f in filas]
    return envolver([i for i in items if i is not None], int(total or 0), p)


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
    _, ev, sin_matriz = _evaluar_cobertura_oc(session, identidad, commitment_id)
    return {
        "commitment_id": commitment_id,
        "oc": _plano(oc),
        "modo": "consulta",
        "estado_cobertura": estado_cobertura_global(ev, sin_matriz=sin_matriz),
        "veredicto_de_cumplimiento": ev.get("veredicto_de_cumplimiento"),
        "resultado_de_decision": ev.get("resultado_de_decision"),
        "por_tipo": resumen_por_tipo(ev) if not sin_matriz else [],
        "grupos_candidatos": candidatos_detalle(ev) if not sin_matriz else [],
        "requisitos_faltantes": ev.get("requisitos_faltantes") or [],
        "version_matriz": ev.get("version_matriz"),
        "tipos_fuera_de_alcance": ev.get("tipos_fuera_de_alcance") or [],
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


def incumplimiento_empresa(session: Session, identidad: Identidad) -> dict[str, Any]:
    """Estado actual del aviso de incumplimiento de empresa (2.9): lo consulta el
    consumidor de `CumplimientoEmpresaAfectado`, que es un aviso flaco sin causas."""
    from app.core.incumplimiento_empresa import estado_actual

    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    return {"aviso": _plano(estado_actual(session, identidad.tenant_id) or {}) or None}

