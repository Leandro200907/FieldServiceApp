"""Idempotency-Key de transporte (8.2) con RESERVA ATÓMICA antes del efecto (A-03).

Uso:
    resultado = ejecutar_idempotente(tenant_id, clave, fingerprint, efecto)
donde `efecto(session) -> dict` corre dentro de una `tenant_session` propia.

Ciclo (tabla `idempotency_keys`, migración 0007):

  1. RESERVA — transacción corta y commiteada: `INSERT … ON CONFLICT DO NOTHING RETURNING`.
     Si no insertó, la clave ya existe:
       - `completada` y mismo fingerprint → REPLAY exacto del resultado guardado.
       - `completada` y otro fingerprint → 409 `clave_idempotencia_reutilizada`.
       - `en_proceso` con reserva vigente → 409 `operacion_en_proceso` (otra solicitud
         está ejecutando el efecto ahora mismo; el cliente reintenta y recibe el replay).
       - `en_proceso` vencida (proceso caído entre reserva y efecto) → se retoma con
         `UPDATE … WHERE estado='en_proceso' AND reservada_hasta < now() RETURNING` (exactamente
         una fila; si otro la retomó primero → 409).
       - `completada` pero pasada `expira_en` (24 h) → se reutiliza como nueva.
  2. EFECTO — en su propia transacción; en esa MISMA transacción la reserva pasa a
     `completada` con el resultado (`UPDATE … WHERE estado='en_proceso'`, 1 fila).
  3. Si el efecto falla, la reserva se libera (DELETE en una transacción aparte) para
     que el cliente pueda reintentar sin esperar el vencimiento.

Garantía: el efecto de negocio nunca corre dos veces para la misma clave del mismo
tenant, ni bajo solicitudes simultáneas — la unicidad la da la PK (tenant_id, clave).
Para ImportarLote prevalece `lote:<lote_id>` como clave (regla 6 del brief).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto

TTL_HORAS = 24
RESERVA_SEGUNDOS = 120  # tope de una ejecución; pasado esto, otra solicitud puede retomar


def fingerprint_de(metodo: str, ruta: str, body: Any) -> str:
    """Huella estable de la solicitud: método + ruta + body canonizado (claves ordenadas)."""
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(f"{metodo.upper()} {ruta}\n{canon}".encode()).hexdigest()


def _abrir_por_defecto(tenant_id: str):
    from app.db import tenant_session

    return tenant_session(tenant_id)


def _reservar(s: Session, tenant_id: str, clave: str, fingerprint: str) -> dict[str, Any] | None:
    """Devuelve None si la reserva quedó a nombre de esta solicitud; si no, el resultado a
    replicar. Levanta Conflicto en los demás casos."""
    insertada = s.execute(
        text(
            "INSERT INTO modulo1.idempotency_keys (tenant_id, idempotency_key, estado, fingerprint, resultado, "
            " expira_en, reservada_en, reservada_hasta) "
            "VALUES (:t, :k, 'en_proceso', :fp, NULL, now() + make_interval(hours => :h), now(), "
            "        now() + make_interval(secs => :r)) "
            "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING idempotency_key"
        ),
        {"t": tenant_id, "k": clave, "fp": fingerprint, "h": TTL_HORAS, "r": RESERVA_SEGUNDOS},
    ).first()
    if insertada is not None:
        return None

    fila = s.execute(
        text(
            "SELECT estado, fingerprint, resultado, reservada_hasta < now() AS vencida, expira_en < now() AS expirada "
            "FROM modulo1.idempotency_keys WHERE tenant_id = :t AND idempotency_key = :k FOR UPDATE"
        ),
        {"t": tenant_id, "k": clave},
    ).mappings().first()
    if fila is None:  # borrada entre el INSERT y el SELECT (reserva liberada): reintentar
        return _reservar(s, tenant_id, clave, fingerprint)

    if fila["estado"] == "completada" and not fila["expirada"]:
        if fila["fingerprint"] != fingerprint:
            raise Conflicto(
                "La Idempotency-Key ya se usó con otra solicitud (ruta o body distintos)",
                {"idempotency_key": clave},
                codigo="clave_idempotencia_reutilizada",
            )
        return fila["resultado"]

    if fila["estado"] == "en_proceso" and not fila["vencida"]:
        raise Conflicto(
            "Otra solicitud con la misma Idempotency-Key está en proceso; reintentar en unos segundos",
            {"idempotency_key": clave},
            codigo="operacion_en_proceso",
        )

    # Reserva vencida, o completada ya expirada: retomarla — exactamente una fila.
    retomada = s.execute(
        text(
            "UPDATE modulo1.idempotency_keys SET estado = 'en_proceso', fingerprint = :fp, resultado = NULL, "
            " expira_en = now() + make_interval(hours => :h), reservada_en = now(), "
            " reservada_hasta = now() + make_interval(secs => :r) "
            "WHERE tenant_id = :t AND idempotency_key = :k "
            "  AND ((estado = 'en_proceso' AND reservada_hasta < now()) OR expira_en < now()) "
            "RETURNING idempotency_key"
        ),
        {"t": tenant_id, "k": clave, "fp": fingerprint, "h": TTL_HORAS, "r": RESERVA_SEGUNDOS},
    ).rowcount
    if retomada != 1:
        raise Conflicto("Otra solicitud retomó la operación", {"idempotency_key": clave}, codigo="operacion_en_proceso")
    return None


def ejecutar_idempotente(
    tenant_id: str,
    clave: str | None,
    fingerprint: str,
    efecto: Callable[[Session], dict[str, Any]],
    abrir_sesion: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    abrir = abrir_sesion or _abrir_por_defecto
    if not clave:
        with abrir(tenant_id) as s:
            return efecto(s)

    with abrir(tenant_id) as s:  # 1) reserva, commiteada antes del efecto
        replay = _reservar(s, tenant_id, clave, fingerprint)
    if replay is not None:
        return replay

    try:
        with abrir(tenant_id) as s:  # 2) efecto + completar la reserva, misma transacción
            resultado = efecto(s)
            completadas = s.execute(
                text(
                    "UPDATE modulo1.idempotency_keys SET estado = 'completada', resultado = CAST(:r AS jsonb) "
                    "WHERE tenant_id = :t AND idempotency_key = :k AND estado = 'en_proceso'"
                ),
                {"t": tenant_id, "k": clave, "r": json.dumps(resultado, default=str)},
            ).rowcount
            if completadas != 1:
                # La reserva ya no es nuestra (venció y otro la retomó): no consolidar.
                raise Conflicto("La reserva de idempotencia venció durante la ejecución",
                                {"idempotency_key": clave}, codigo="operacion_en_proceso")
            return resultado
    except Exception:
        with abrir(tenant_id) as s:  # 3) liberar la reserva (solo si sigue siendo nuestra)
            s.execute(
                text("DELETE FROM modulo1.idempotency_keys WHERE tenant_id = :t AND idempotency_key = :k "
                     "AND estado = 'en_proceso' AND fingerprint = :fp"),
                {"t": tenant_id, "k": clave, "fp": fingerprint},
            )
        raise
