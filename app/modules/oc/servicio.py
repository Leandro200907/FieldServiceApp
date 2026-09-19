"""Backlog de OC (documentacion-habilitante 1.12): ImportarLote de órdenes de compra y
CancelarOC.

ImportarLote es UNA transacción e idempotente por `lote_id` (regla dura 6): la clave
`lote:<lote_id>` en idempotency_keys guarda el resultado y una segunda llamada lo
devuelve sin re-aplicar nada. Es incremental: `clave_origen` identifica la OC en el
origen, así que una clave conocida actualiza la OC (y `actualizado_en`) en vez de
duplicarla — para eso está `uq_oc_clave_origen` (migración 0003_oc_uq_clave_origen).
Las filas inválidas se rechazan de a una y quedan listadas en `detalle_filas_rechazadas`;
el resto del lote se aplica igual.
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento

ORIGENES = ("planilla", "drive")
CAMPOS_OBLIGATORIOS = ("clave_origen", "cliente_id", "locacion_id", "tipo_servicio_id", "vigencia_desde", "vigencia_hasta")


def clave_idempotencia_lote(lote_id: str) -> str:
    return f"lote:{lote_id}"


# --------------------------------------------------------------------- validación


def _uuid(valor: Any) -> str:
    return str(uuid.UUID(str(valor)))


def _fecha(valor: Any) -> date:
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor))


def validar_fila(fila: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    """Devuelve (fila_normalizada, None) o (None, motivo). Nunca levanta: una fila mala
    no puede tirar el lote entero."""
    faltantes = [c for c in CAMPOS_OBLIGATORIOS if fila.get(c) in (None, "")]
    if faltantes:
        return None, f"campos faltantes: {', '.join(faltantes)}"
    try:
        desde, hasta = _fecha(fila["vigencia_desde"]), _fecha(fila["vigencia_hasta"])
    except (ValueError, TypeError):
        return None, "vigencia_desde/vigencia_hasta no son fechas ISO válidas"
    if desde > hasta:
        return None, "vigencia invertida: vigencia_desde > vigencia_hasta"
    try:
        normalizada = {
            "clave_origen": str(fila["clave_origen"]).strip(),
            "referencia": (str(fila["referencia"]).strip() or None) if fila.get("referencia") is not None else None,
            "cliente_id": _uuid(fila["cliente_id"]),
            "locacion_id": _uuid(fila["locacion_id"]),
            "tipo_servicio_id": _uuid(fila["tipo_servicio_id"]),
            "vigencia_desde": desde,
            "vigencia_hasta": hasta,
        }
    except (ValueError, TypeError):
        return None, "cliente_id/locacion_id/tipo_servicio_id no son UUID válidos"
    if not normalizada["clave_origen"]:
        return None, "campos faltantes: clave_origen"
    return normalizada, None


# --------------------------------------------------------------------- comandos


def importar_lote_oc(
    session: Session, identidad: Identidad, lote_id: str, origen: str, filas: list[dict[str, Any]]
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    tenant_id = identidad.tenant_id
    if origen not in ORIGENES:
        raise ErrorDeDominio("origen inválido", {"origen": origen, "validos": list(ORIGENES)})
    lote_id = str(uuid.UUID(str(lote_id)))

    # La idempotencia por `lote:<lote_id>` la resuelve el router (reserva atómica, A-03).
    # La clave de idempotencia expira (24 h) pero el lote queda: si existe, tampoco se
    # re-aplica — se reconstruye el resultado desde lote_importacion.
    from app.comun.idempotencia import hash_canonico

    hash_contenido = hash_canonico([dict(f) for f in filas])
    lote_existente = session.execute(
        text(
            "SELECT filas_totales, filas_aceptadas, filas_rechazadas, detalle_filas_rechazadas, estado, hash_archivo "
            "FROM modulo1.lote_importacion WHERE lote_id = :l"
        ),
        {"l": lote_id},
    ).mappings().first()
    if lote_existente is not None:
        if lote_existente["hash_archivo"] != hash_contenido:
            raise Conflicto(
                "El lote ya fue importado con otro contenido; un lote_id identifica un contenido único",
                {"lote_id": lote_id},
                codigo="lote_contenido_distinto",
            )
        oc_ids = [
            str(f[0])
            for f in session.execute(text("SELECT oc_id FROM modulo1.oc WHERE lote_id = :l ORDER BY clave_origen"), {"l": lote_id})
        ]
        return {
            "lote_id": lote_id,
            "estado": lote_existente["estado"],
            "filas_totales": lote_existente["filas_totales"],
            "filas_aceptadas": lote_existente["filas_aceptadas"],
            "filas_rechazadas": lote_existente["filas_rechazadas"],
            "detalle_filas_rechazadas": lote_existente["detalle_filas_rechazadas"],
            "oc_ids": oc_ids,
            "ya_aplicado": True,
            "eventos": [],
        }

    # Dentro del mismo lote una clave_origen repetida es ambigua: se acepta la primera
    # y se rechazan las siguientes.
    vistas: set[str] = set()
    aceptadas: list[dict[str, Any]] = []
    rechazadas: list[dict[str, Any]] = []
    for indice, fila in enumerate(filas):
        normalizada, motivo = validar_fila(fila if isinstance(fila, dict) else {})
        if normalizada is None:
            rechazadas.append({"indice": indice, "clave_origen": (fila or {}).get("clave_origen"), "motivo": motivo})
            continue
        if normalizada["clave_origen"] in vistas:
            rechazadas.append({"indice": indice, "clave_origen": normalizada["clave_origen"], "motivo": "clave_origen repetida en el lote"})
            continue
        vistas.add(normalizada["clave_origen"])
        aceptadas.append(normalizada)

    session.execute(
        text(
            "INSERT INTO modulo1.lote_importacion "
            "(lote_id, tenant_id, origen, entidad, filas_totales, filas_aceptadas, filas_rechazadas, detalle_filas_rechazadas, hash_archivo) "
            "VALUES (:l, :t, :o, 'oc', :tot, :ok, :ko, CAST(:det AS jsonb), :hash)"
        ),
        {
            "l": lote_id,
            "hash": hash_contenido,
            "t": tenant_id,
            "o": origen,
            "tot": len(filas),
            "ok": len(aceptadas),
            "ko": len(rechazadas),
            "det": _json(rechazadas),
        },
    )

    oc_ids: list[str] = []
    creadas = actualizadas = 0
    for fila in aceptadas:
        # `xmax = 0` distingue INSERT de UPDATE en el RETURNING del UPSERT. `estado` no se
        # toca a propósito: una OC cancelada no se reactiva por reimportarla.
        resultado = session.execute(
            text(
                """
                INSERT INTO modulo1.oc (tenant_id, clave_origen, referencia, cliente_id, locacion_id,
                                        tipo_servicio_id, vigencia_desde, vigencia_hasta, lote_id)
                VALUES (:t, :clave, :ref, :cli, :loc, :tipo, :desde, :hasta, :l)
                ON CONFLICT (tenant_id, clave_origen) DO UPDATE SET
                    referencia = EXCLUDED.referencia,
                    cliente_id = EXCLUDED.cliente_id,
                    locacion_id = EXCLUDED.locacion_id,
                    tipo_servicio_id = EXCLUDED.tipo_servicio_id,
                    vigencia_desde = EXCLUDED.vigencia_desde,
                    vigencia_hasta = EXCLUDED.vigencia_hasta,
                    lote_id = EXCLUDED.lote_id,
                    actualizado_en = now()
                RETURNING oc_id, (xmax = 0) AS insertada
                """
            ),
            {
                "t": tenant_id,
                "clave": fila["clave_origen"],
                "ref": fila["referencia"],
                "cli": fila["cliente_id"],
                "loc": fila["locacion_id"],
                "tipo": fila["tipo_servicio_id"],
                "desde": fila["vigencia_desde"],
                "hasta": fila["vigencia_hasta"],
                "l": lote_id,
            },
        ).first()
        oc_ids.append(str(resultado[0]))
        if resultado[1]:
            creadas += 1
        else:
            actualizadas += 1

    registrar_evento(
        session,
        tenant_id,
        "LoteAplicado",
        {
            "lote_id": lote_id,
            "entidad": "oc",
            "origen": origen,
            "filas_totales": len(filas),
            "filas_aceptadas": len(aceptadas),
            "filas_rechazadas": len(rechazadas),
            "oc_creadas": creadas,
            "oc_actualizadas": actualizadas,
        },
        identidad.usuario_id,
    )
    resultado_cmd = {
        "lote_id": lote_id,
        "estado": "aplicado",
        "filas_totales": len(filas),
        "filas_aceptadas": len(aceptadas),
        "filas_rechazadas": len(rechazadas),
        "detalle_filas_rechazadas": rechazadas,
        "oc_ids": oc_ids,
        "oc_creadas": creadas,
        "oc_actualizadas": actualizadas,
        "ya_aplicado": False,
        "eventos": ["LoteAplicado"],
    }
    return resultado_cmd


def cancelar_oc(session: Session, identidad: Identidad, oc_id: str | None, clave_origen: str | None) -> dict[str, Any]:
    """Pasa la OC a `cancelado`. Se identifica por `oc_id` o por `clave_origen`."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    if not oc_id and not clave_origen:
        raise ErrorDeDominio("Hay que indicar oc_id o clave_origen")
    if oc_id:
        fila = session.execute(
            text("SELECT oc_id, clave_origen, estado FROM modulo1.oc WHERE oc_id = :id FOR UPDATE"),
            {"id": str(uuid.UUID(str(oc_id)))},
        ).first()
    else:
        fila = session.execute(
            text("SELECT oc_id, clave_origen, estado FROM modulo1.oc WHERE clave_origen = :c FOR UPDATE"),
            {"c": clave_origen},
        ).first()
    if fila is None:
        raise NoEncontrado("OC inexistente", {"oc_id": oc_id, "clave_origen": clave_origen})
    if fila[2] == "cancelado":
        raise Conflicto("La OC ya está cancelada", {"oc_id": str(fila[0])})
    session.execute(
        text("UPDATE modulo1.oc SET estado = 'cancelado', actualizado_en = now() WHERE oc_id = :id"),
        {"id": str(fila[0])},
    )
    # No hay evento de catálogo para la cancelación de OC (brief): queda en el UPDATE y en
    # `actualizado_en`. No se inventan nombres de evento.
    return {"oc_id": str(fila[0]), "clave_origen": fila[1], "estado": "cancelado", "eventos": []}


def _json(valor: Any) -> str:
    import json

    return json.dumps(valor, default=str, ensure_ascii=False)
