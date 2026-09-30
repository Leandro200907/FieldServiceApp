"""Catálogos de operadora (cliente OC), locación y tipo de servicio."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.normalizar_texto import normalizar_clave
from app.comun.paginacion import Pagina, envolver


def _sugerencias(session: Session, tenant_id: str, tabla: str, clave: str, limite: int = 3) -> list[str]:
    filas = session.execute(
        text(f"SELECT nombre FROM modulo1.{tabla} WHERE tenant_id = :t ORDER BY nombre LIMIT 50"),
        {"t": tenant_id},
    ).scalars().all()
    ordenadas = sorted(filas, key=lambda n: (normalizar_clave(n) != clave, n))
    return [str(n) for n in ordenadas[:limite]]


def resolver_operadora(session: Session, tenant_id: str, nombre: str) -> tuple[str | None, str | None]:
    clave = normalizar_clave(nombre)
    fila = session.execute(
        text(
            "SELECT operadora_id::text, nombre FROM modulo1.operadora_documental "
            "WHERE tenant_id = :t AND lower(nombre) = lower(:n) LIMIT 1"
        ),
        {"t": tenant_id, "n": nombre.strip()},
    ).first()
    if fila:
        return fila[0], None
    for candidato in session.execute(
        text("SELECT operadora_id::text, nombre FROM modulo1.operadora_documental WHERE tenant_id = :t"),
        {"t": tenant_id},
    ):
        if normalizar_clave(candidato[1]) == clave:
            return candidato[0], None
    sug = _sugerencias(session, tenant_id, "operadora_documental", clave)
    return None, f"operadora desconocida: «{nombre.strip()}»" + (f" — ¿quisiste decir {', '.join(sug)}?" if sug else "")


def resolver_locacion(
    session: Session, tenant_id: str, operadora_id: str, nombre: str,
) -> tuple[str | None, str | None]:
    clave = normalizar_clave(nombre)
    for fila in session.execute(
        text(
            "SELECT locacion_id::text, nombre FROM modulo1.locacion_oc "
            "WHERE tenant_id = :t AND operadora_id = CAST(:o AS uuid)"
        ),
        {"t": tenant_id, "o": operadora_id},
    ):
        if normalizar_clave(fila[1]) == clave or fila[1].lower() == nombre.strip().lower():
            return fila[0], None
    sug = [
        r[0]
        for r in session.execute(
            text(
                "SELECT nombre FROM modulo1.locacion_oc "
                "WHERE tenant_id = :t AND operadora_id = CAST(:o AS uuid) ORDER BY nombre LIMIT 50"
            ),
            {"t": tenant_id, "o": operadora_id},
        )
    ]
    orden = sorted(sug, key=lambda n: (normalizar_clave(n) != clave, n))[:3]
    return None, f"locación desconocida: «{nombre.strip()}»" + (f" — ¿quisiste decir {', '.join(orden)}?" if orden else "")


def resolver_tipo_servicio(session: Session, tenant_id: str, nombre: str) -> tuple[str | None, str | None]:
    clave = normalizar_clave(nombre)
    for fila in session.execute(
        text("SELECT tipo_servicio_id::text, nombre FROM modulo1.tipo_servicio_oc WHERE tenant_id = :t"),
        {"t": tenant_id},
    ):
        if normalizar_clave(fila[1]) == clave or fila[1].lower() == nombre.strip().lower():
            return fila[0], None
    sug = _sugerencias(session, tenant_id, "tipo_servicio_oc", clave)
    return None, f"tipo de servicio desconocido: «{nombre.strip()}»" + (f" — ¿quisiste decir {', '.join(sug)}?" if sug else "")


def resolver_fila_por_nombres(session: Session, tenant_id: str, fila: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    operadora = (fila.get("operadora") or fila.get("Operadora") or "").strip()
    locacion = (fila.get("locacion") or fila.get("Locación") or fila.get("locación") or "").strip()
    tipo = (fila.get("tipo_servicio") or fila.get("Tipo de servicio") or "").strip()
    if not operadora or not locacion or not tipo:
        return None, "faltan columnas Operadora, Locación o Tipo de servicio"
    op_id, err = resolver_operadora(session, tenant_id, operadora)
    if err:
        return None, err
    loc_id, err = resolver_locacion(session, tenant_id, op_id, locacion)
    if err:
        return None, err
    ts_id, err = resolver_tipo_servicio(session, tenant_id, tipo)
    if err:
        return None, err
    base = dict(fila)
    base["cliente_id"] = op_id
    base["locacion_id"] = loc_id
    base["tipo_servicio_id"] = ts_id
    return base, None


def alta_operadora(session: Session, identidad: Identidad, nombre: str) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    nombre = nombre.strip()
    if not nombre:
        raise ErrorDeDominio("nombre obligatorio")
    existente = session.execute(
        text(
            "SELECT operadora_id FROM modulo1.operadora_documental "
            "WHERE tenant_id = :t AND lower(nombre) = lower(:n)"
        ),
        {"t": identidad.tenant_id, "n": nombre},
    ).scalar()
    if existente:
        oid = existente
    else:
        oid = session.execute(
            text("INSERT INTO modulo1.operadora_documental (tenant_id, nombre) VALUES (:t, :n) RETURNING operadora_id"),
            {"t": identidad.tenant_id, "n": nombre},
        ).scalar()
    return {"operadora_id": str(oid), "nombre": nombre}


def alta_locacion(session: Session, identidad: Identidad, operadora_id: str, nombre: str) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    nombre = nombre.strip()
    if not nombre:
        raise ErrorDeDominio("nombre obligatorio")
    lid = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO modulo1.locacion_oc (locacion_id, tenant_id, operadora_id, nombre) "
            "VALUES (CAST(:id AS uuid), :t, CAST(:o AS uuid), :n)"
        ),
        {"id": lid, "t": identidad.tenant_id, "o": operadora_id, "n": nombre},
    )
    return {"locacion_id": lid, "operadora_id": operadora_id, "nombre": nombre}


def alta_tipo_servicio(session: Session, identidad: Identidad, nombre: str) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    nombre = nombre.strip()
    if not nombre:
        raise ErrorDeDominio("nombre obligatorio")
    tid = str(uuid.uuid4())
    session.execute(
        text(
            "INSERT INTO modulo1.tipo_servicio_oc (tipo_servicio_id, tenant_id, nombre) "
            "VALUES (CAST(:id AS uuid), :t, :n)"
        ),
        {"id": tid, "t": identidad.tenant_id, "n": nombre},
    )
    return {"tipo_servicio_id": tid, "nombre": nombre}


def listar_catalogos(session: Session, identidad: Identidad) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION, Rol.SUPERVISOR)
    t = identidad.tenant_id
    operadoras = [
        {"operadora_id": str(r[0]), "nombre": r[1]}
        for r in session.execute(
            text("SELECT operadora_id, nombre FROM modulo1.operadora_documental WHERE tenant_id = :t ORDER BY nombre"),
            {"t": t},
        )
    ]
    locaciones = [
        {"locacion_id": str(r[0]), "operadora_id": str(r[1]), "nombre": r[2]}
        for r in session.execute(
            text(
                "SELECT locacion_id, operadora_id, nombre FROM modulo1.locacion_oc "
                "WHERE tenant_id = :t ORDER BY nombre"
            ),
            {"t": t},
        )
    ]
    tipos = [
        {"tipo_servicio_id": str(r[0]), "nombre": r[1]}
        for r in session.execute(
            text("SELECT tipo_servicio_id, nombre FROM modulo1.tipo_servicio_oc WHERE tenant_id = :t ORDER BY nombre"),
            {"t": t},
        )
    ]
    return {"operadoras": operadoras, "locaciones": locaciones, "tipos_servicio": tipos}


def nombres_oc(session: Session, tenant_id: str, cliente_id: str, locacion_id: str, tipo_servicio_id: str) -> dict[str, str | None]:
    op = session.execute(
        text("SELECT nombre FROM modulo1.operadora_documental WHERE tenant_id = :t AND operadora_id = CAST(:id AS uuid)"),
        {"t": tenant_id, "id": cliente_id},
    ).scalar()
    loc = session.execute(
        text("SELECT nombre FROM modulo1.locacion_oc WHERE tenant_id = :t AND locacion_id = CAST(:id AS uuid)"),
        {"t": tenant_id, "id": locacion_id},
    ).scalar()
    ts = session.execute(
        text("SELECT nombre FROM modulo1.tipo_servicio_oc WHERE tenant_id = :t AND tipo_servicio_id = CAST(:id AS uuid)"),
        {"t": tenant_id, "id": tipo_servicio_id},
    ).scalar()
    return {
        "operadora_nombre": str(op) if op else None,
        "locacion_nombre": str(loc) if loc else None,
        "tipo_servicio_nombre": str(ts) if ts else None,
    }
