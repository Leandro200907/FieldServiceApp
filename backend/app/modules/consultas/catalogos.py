"""Consultas auxiliares (H-06) y legajo compuesto del técnico (H-05).

Con estas listas todo comando del OpenAPI puede operarse sin tipear identificadores:
sujetos, definiciones, matrices, usuarios, documentos, excepciones, constancias,
custodias, lotes y asignaciones de supervisor. Todas: permiso por rol (matriz 2.2),
alcance multi-tenant (RLS + `alcance_de_sujetos`), paginación `offset/limit` y búsqueda
`q` (ILIKE) donde tiene sentido. Devuelven `{items, total, offset, limit}`.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, Prohibido
from app.auth.alcance import ROLES_CON_TODO_LECTURA, alcance_de_sujetos, recursos_bajo_custodia
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant

TODOS = (Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO)
ADMIN = (Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
OPERATIVOS = (Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)


def _paginar(session: Session, sql_base: str, cond: str, orden: str, params: dict[str, Any], p: Pagina) -> dict[str, Any]:
    total = session.execute(text(f"SELECT count(*) FROM ({sql_base}{cond}) x"), params).scalar()
    filas = session.execute(text(f"{sql_base}{cond} ORDER BY {orden} OFFSET :off LIMIT :lim"), {**params, "off": p.offset, "lim": p.limit}).mappings().all()
    return envolver([{k: (str(v) if hasattr(v, "hex") else v) for k, v in dict(f).items()} for f in filas], int(total or 0), p)


def _alcance(session: Session, identidad: Identidad, params: dict[str, Any], columna: str = "sujeto_id") -> str:
    alcance = alcance_de_sujetos(session, identidad, hoy_del_tenant(session, identidad.tenant_id))
    if alcance is None:
        return ""
    params["alcance"] = alcance
    return f" AND {columna} = ANY(CAST(:alcance AS text[]))"


def _q(q: str | None, params: dict[str, Any], *columnas: str) -> str:
    if not q:
        return ""
    params["q"] = f"%{q.strip()}%"
    return " AND (" + " OR ".join(f"{c} ILIKE :q" for c in columnas) + ")"


# --------------------------------------------------------------------------- H-05: mi legajo compuesto


def mi_legajo(session: Session, identidad: Identidad) -> dict[str, Any]:
    """Vista compuesta de quien la pide (2.4 / anexo de la vista compuesta / H-05 ampliado a
    Supervisor): su persona + los vehículos y equipos bajo su propia custodia vigente, cada
    uno con su legajo. Cualquier usuario activo con `sujeto_id` propio la tiene —técnico o
    supervisor, el rol no importa—; siempre sobre sí mismo, nunca sobre datos de otra
    persona (el filtro es `identidad.sujeto_id`, no un id que el llamador pueda elegir)."""
    from app.modules.consultas.servicio import legajo

    if not identidad.sujeto_id:
        raise Prohibido("Solo un usuario con legajo propio tiene 'mi legajo'")
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    recursos = recursos_bajo_custodia(session, identidad.sujeto_id, hoy)
    persona = legajo(session, identidad, identidad.sujeto_id)
    custodiados = []
    for r in recursos:
        periodo = session.execute(text(
            "SELECT c.tipo_recurso, p.periodo_id::text, p.desde FROM modulo1.periodo_custodia p "
            "JOIN modulo1.custodia_recurso c ON c.tenant_id = p.tenant_id AND c.custodia_id = p.custodia_id "
            "WHERE p.tenant_id = :t AND c.recurso_id = :r AND p.estado = 'vigente' AND p.desde <= :hoy"),
            {"t": identidad.tenant_id, "r": r, "hoy": hoy}).mappings().first()
        custodiados.append({"tipo_recurso": periodo["tipo_recurso"], "periodo_id": periodo["periodo_id"], "custodia_desde": periodo["desde"],
                            **legajo(session, identidad, r)})
    return {"hoy": persona["hoy"], "persona": persona, "recursos_bajo_custodia": custodiados,
            "resumen": {"vencidos": persona["resumen"]["vencidos"] + sum(c["resumen"]["vencidos"] for c in custodiados),
                        "vigentes_hoy": persona["resumen"]["vigentes_hoy"] + sum(c["resumen"]["vigentes_hoy"] for c in custodiados)}}


# --------------------------------------------------------------------------- H-06: catálogos


def sujetos(session: Session, identidad: Identidad, p: Pagina, q: str | None = None, tipo_sujeto: str | None = None, activos: bool | None = True) -> dict[str, Any]:
    identidad.exigir_rol(*TODOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = "" + _alcance(session, identidad, params)
    if tipo_sujeto:
        cond += " AND tipo_sujeto = :ts"
        params["ts"] = tipo_sujeto
    if activos is True:
        cond += " AND dado_de_baja_en IS NULL"
    elif activos is False:
        cond += " AND dado_de_baja_en IS NOT NULL"
    cond += _q(q, params, "sujeto_id", "identificador_natural")
    sql = "SELECT sujeto_id, tipo_sujeto, identificador_natural, dado_de_baja_en, creado_en FROM modulo1.legajo WHERE tenant_id = :t"
    return _paginar(session, sql, cond, "tipo_sujeto, sujeto_id", params, p)


def definiciones_requisito(session: Session, identidad: Identidad, p: Pagina, q: str | None = None, categoria: str | None = None,
                           tipo_sujeto_aplicable: str | None = None, activas: bool | None = True) -> dict[str, Any]:
    identidad.exigir_rol(*TODOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = ""
    if categoria:
        cond += " AND categoria = :c"
        params["c"] = categoria
    if tipo_sujeto_aplicable:
        cond += " AND tipo_sujeto_aplicable = :ts"
        params["ts"] = tipo_sujeto_aplicable
    if activas is not None:
        cond += " AND activa = :a"
        params["a"] = activas
    cond += _q(q, params, "nombre")
    sql = ("SELECT requisito_definicion_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id, activa, definicion_global_id, "
           "copiada_de_version, plazo_aviso_dias, creado_en FROM modulo1.definicion_requisito WHERE tenant_id = :t")
    return _paginar(session, sql, cond, "tipo_sujeto_aplicable, nombre", params, p)


def matrices(session: Session, identidad: Identidad, p: Pagina, cliente_id: str | None = None, solo_vigentes: bool = False) -> dict[str, Any]:
    """Todas las versiones de matriz del tenant (clave + versión + vigencia + cantidad de líneas)."""
    identidad.exigir_rol(*OPERATIVOS)
    params: dict[str, Any] = {"t": identidad.tenant_id, "hoy": hoy_del_tenant(session, identidad.tenant_id)}
    cond = ""
    if cliente_id:
        cond += " AND cliente_id = :c"
        params["c"] = cliente_id
    if solo_vigentes:
        cond += " AND vigente_desde <= :hoy AND (vigente_hasta IS NULL OR vigente_hasta >= :hoy)"
    sql = ("SELECT m.matriz_version_id, m.cliente_id, m.locacion_id, m.tipo_servicio_id, m.version, m.vigente_desde, m.vigente_hasta, m.fuente, m.autor, "
           "m.matriz_global_id, m.copiada_de_version, m.creado_en, "
           "(SELECT count(*) FROM modulo1.linea_requisito l WHERE l.tenant_id = m.tenant_id AND l.matriz_version_id = m.matriz_version_id) AS lineas "
           "FROM modulo1.matriz_requisitos m WHERE m.tenant_id = :t")
    return _paginar(session, sql, cond, "m.cliente_id, m.locacion_id, m.tipo_servicio_id, m.version DESC", params, p)


def usuarios(session: Session, identidad: Identidad, p: Pagina, q: str | None = None, rol: str | None = None, activos: bool | None = True) -> dict[str, Any]:
    """Para asignar/reasignar supervisor y configurar alertas. Sin hash ni datos sensibles."""
    identidad.exigir_rol(*ADMIN)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = ""
    if rol:
        cond += " AND :rol = ANY(roles)"
        params["rol"] = rol
    if activos is not None:
        cond += " AND activo = :a"
        params["a"] = activos
    cond += _q(q, params, "email", "nombre")
    sql = "SELECT usuario_id, email, nombre, roles, sujeto_id, activo, creado_en FROM modulo1.usuario WHERE tenant_id = :t"
    return _paginar(session, sql, cond, "nombre, email", params, p)


def documentos(session: Session, identidad: Identidad, p: Pagina, sujeto_id: str | None = None, estado_version: str | None = "vigente",
               estado_confirmacion: str | None = None, archivo_estado: str | None = None) -> dict[str, Any]:
    """Documentos (todas las versiones si `estado_version` es null): para confirmar,
    rechazar, adjuntar evidencia o descargar."""
    identidad.exigir_rol(*TODOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = _alcance(session, identidad, params, "d.sujeto_id")
    if sujeto_id:
        cond += " AND d.sujeto_id = :s"
        params["s"] = sujeto_id
    if estado_version:
        cond += " AND d.estado_version = :ev"
        params["ev"] = estado_version
    if estado_confirmacion:
        cond += " AND d.estado_confirmacion = :ec"
        params["ec"] = estado_confirmacion
    if archivo_estado:
        cond += " AND d.archivo_estado = :ae"
        params["ae"] = archivo_estado
    sql = ("SELECT d.documento_id, d.sujeto_id, d.requisito_definicion_id, r.nombre AS requisito, d.version, d.vigente_desde, d.vigente_hasta, "
           "d.estado_version, d.estado_confirmacion, d.origen, d.origen_propuesta, d.lote_id, d.archivo_estado, d.creado_en "
           "FROM modulo1.documento d LEFT JOIN modulo1.definicion_requisito r ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id "
           "WHERE d.tenant_id = :t")
    return _paginar(session, sql, cond, "d.sujeto_id, r.nombre, d.version DESC", params, p)


def excepciones(session: Session, identidad: Identidad, p: Pagina, sujeto_id: str | None = None, estado: str | None = "otorgada",
                commitment_id: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(*OPERATIVOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = _alcance(session, identidad, params, "e.sujeto_id")
    if sujeto_id:
        cond += " AND e.sujeto_id = :s"
        params["s"] = sujeto_id
    if estado:
        cond += " AND e.estado = :e"
        params["e"] = estado
    if commitment_id:
        cond += " AND e.commitment_id = :c"
        params["c"] = commitment_id
    sql = ("SELECT e.excepcion_id, e.referencia_evaluacion, e.sujeto_id, e.requisito_definicion_id, r.nombre AS requisito, e.commitment_id, e.estado, "
           "e.otorgada_por, e.motivo, e.vigencia, e.evidencia, e.creado_en FROM modulo1.excepcion e "
           "JOIN modulo1.definicion_requisito r ON r.tenant_id = e.tenant_id AND r.requisito_definicion_id = e.requisito_definicion_id WHERE e.tenant_id = :t")
    return _paginar(session, sql, cond, "e.creado_en DESC", params, p)


def constancias(session: Session, identidad: Identidad, p: Pagina, sujeto_id: str | None = None, estado: str | None = "vigente",
                cliente_id: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(*OPERATIVOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = _alcance(session, identidad, params, "c.sujeto_id")
    if sujeto_id:
        cond += " AND c.sujeto_id = :s"
        params["s"] = sujeto_id
    if estado:
        cond += " AND c.estado = :e"
        params["e"] = estado
    if cliente_id:
        cond += " AND c.cliente_id = :cl"
        params["cl"] = cliente_id
    sql = ("SELECT c.constancia_id, c.sujeto_id, c.requisito_definicion_id, r.nombre AS requisito, c.cliente_id, c.commitment_id, c.estado, c.emisor, "
           "c.evidencia, c.vigencia, c.reemplazada_por, c.registrada_por, c.creado_en FROM modulo1.constancia_cliente c "
           "JOIN modulo1.definicion_requisito r ON r.tenant_id = c.tenant_id AND r.requisito_definicion_id = c.requisito_definicion_id WHERE c.tenant_id = :t")
    return _paginar(session, sql, cond, "c.creado_en DESC", params, p)


def custodias(session: Session, identidad: Identidad, p: Pagina, recurso_id: str | None = None, custodio_id: str | None = None,
              solo_vigentes: bool = False) -> dict[str, Any]:
    """Períodos de custodia (para corregir_custodia y para ver quién tiene qué)."""
    identidad.exigir_rol(*TODOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = _alcance(session, identidad, params, "c.recurso_id")
    if recurso_id:
        cond += " AND c.recurso_id = :r"
        params["r"] = recurso_id
    if custodio_id:
        cond += " AND p.custodio_id = :cu"
        params["cu"] = custodio_id
    if solo_vigentes:
        cond += " AND p.estado = 'vigente'"
    sql = ("SELECT p.periodo_id, c.custodia_id, c.recurso_id, c.tipo_recurso, p.custodio_id, p.desde, p.hasta, p.estado, p.corregido_por, p.creado_en "
           "FROM modulo1.periodo_custodia p JOIN modulo1.custodia_recurso c ON c.tenant_id = p.tenant_id AND c.custodia_id = p.custodia_id WHERE p.tenant_id = :t")
    return _paginar(session, sql, cond, "c.recurso_id, p.desde DESC", params, p)


def lotes(session: Session, identidad: Identidad, p: Pagina, estado: str | None = None, entidad: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(*ADMIN)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = ""
    if estado:
        cond += " AND estado = :e"
        params["e"] = estado
    if entidad:
        cond += " AND entidad = :en"
        params["en"] = entidad
    sql = ("SELECT lote_id, origen, entidad, estado, filas_totales, filas_aceptadas, filas_rechazadas, fecha "
           "FROM modulo1.lote_importacion WHERE tenant_id = :t")
    return _paginar(session, sql, cond, "fecha DESC", params, p)


def asignaciones_supervisor(session: Session, identidad: Identidad, p: Pagina, supervisor_usuario_id: str | None = None,
                            sujeto_id: str | None = None, solo_vigentes: bool = True) -> dict[str, Any]:
    identidad.exigir_rol(*OPERATIVOS)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = _alcance(session, identidad, params, "a.sujeto_id")
    if supervisor_usuario_id:
        cond += " AND a.supervisor_usuario_id = :u"
        params["u"] = supervisor_usuario_id
    if sujeto_id:
        cond += " AND a.sujeto_id = :s"
        params["s"] = sujeto_id
    if solo_vigentes:
        cond += " AND a.estado = 'vigente'"
    sql = ("SELECT a.asignacion_id, a.sujeto_id, a.supervisor_usuario_id, u.nombre AS supervisor, u.email AS supervisor_email, a.desde, a.hasta, a.estado, a.asignada_por, a.creado_en "
           "FROM modulo1.asignacion_supervisor a LEFT JOIN modulo1.usuario u ON u.tenant_id = a.tenant_id AND u.usuario_id = a.supervisor_usuario_id WHERE a.tenant_id = :t")
    return _paginar(session, sql, cond, "a.sujeto_id, a.desde DESC", params, p)
