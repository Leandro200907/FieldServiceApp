"""Calendario de vencimientos documentales, independiente de las OC."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio
from app.auth.alcance import alcance_de_sujetos
from app.auth.identidad import Identidad, Rol
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant

ADVERTENCIA = "Información documental calculada con los datos registrados a la fecha. No implica planificación, disponibilidad ni asignación operativa."
LIMITE_DIAS = 366
ROLES_CALENDARIO = (Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR, Rol.TECNICO)


def _exigir_rango(desde: date, hasta: date, hoy: date, limite_pasado: date | None = None) -> None:
    if hasta < desde:
        raise ErrorDeDominio("`hasta` no puede ser anterior a `desde`", {"desde": str(desde), "hasta": str(hasta)})
    if limite_pasado is not None and desde < limite_pasado:
        raise ErrorDeDominio("`desde` no puede ser anterior a hoy - 366 días", {"desde": str(desde), "minimo": str(limite_pasado)}, codigo="rango_temporal_excedido")
    if (hasta - desde).days > LIMITE_DIAS:
        raise ErrorDeDominio("El rango pedido excede 366 días", {"desde": str(desde), "hasta": str(hasta)}, codigo="rango_temporal_excedido")


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
    """Devuelve evidencia que vence en un rango, sin consultar matrices ni OC."""
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
    for fila in filas:
        item = dict(fila)
        item["id"] = str(item["id"])
        if item["requisito_definicion_id"] is not None:
            item["requisito_definicion_id"] = str(item["requisito_definicion_id"])
        item["dias_para_vencer"] = (item["vigente_hasta"] - hoy).days
        item["referencia"] = f"evidencia:{item['categoria']}:{item['id']}"
        items.append(item)
    salida = envolver(items, int(total or 0), p)
    salida.update({"hoy": hoy, "desde": desde, "hasta": hasta, "advertencia": ADVERTENCIA})
    return salida

