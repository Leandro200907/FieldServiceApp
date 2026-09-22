"""Idempotency-Key de transporte (8.2) con reserva atómica, ámbito por actor y exclusión
real durante el efecto (A-03, versión corregida).

Uso:
    resultado = ejecutar_idempotente(tenant_id, actor_id, clave, fingerprint, efecto)
donde `efecto(session) -> dict` corre dentro de una `tenant_session` propia.

Algoritmo (tabla `idempotency_keys`, migraciones 0007 + 0009):

  Tx A — RESERVA (transacción corta, commiteada):
    INSERT (tenant, actor, clave, 'en_proceso', fingerprint, reservation_token=T) ON CONFLICT
    DO NOTHING RETURNING. Si no insertó, la clave ya existe para este actor:
      - fingerprint distinto → 409 `clave_idempotencia_reutilizada`. SIEMPRE, en cualquier
        estado: una clave nunca cambia de fingerprint (ni por vencimiento ni por fallo).
      - `completada` → REPLAY del resultado guardado.
      - `en_proceso` → se intenta la recuperación en Tx B.

  Tx B — EFECTO (una sola transacción, con la fila bloqueada de punta a punta):
    SELECT … FOR UPDATE NOWAIT sobre la fila. Lock ocupado → otra ejecución está corriendo
    el efecto AHORA → 409 `operacion_en_proceso` (no importa `reservada_hasta`).
    Con el lock:
      - `completada` (terminó entre A y B) → replay.
      - `en_proceso` con nuestro token → somos el propietario.
      - `en_proceso` con otro token → reserva huérfana (su proceso murió o falló: el lock
        estaba libre). Se recupera con token NUEVO — el fingerprint ya se verificó igual.
    efecto(session) → UPDATE … SET completada, resultado WHERE estado='en_proceso' AND
    reservation_token = :nuestro (exactamente 1 fila) → commit (libera el lock).

  Fallo del efecto → rollback de Tx B: la fila sigue `en_proceso` sin lock; el próximo
  intento con el mismo fingerprint la recupera. Caída del proceso → Postgres libera el
  lock; mismo camino. Nunca dos efectos concurrentes para (tenant, actor, clave): el lock
  de fila lo impide durante la ejecución y la PK antes de ella.

Ámbito por actor: la PK incluye `actor_id`. Otro usuario del tenant que reutilice la
clave entra por su propio ámbito y ejecuta el comando completo (autorización y alcance
incluidos); nunca obtiene el replay ajeno.

Autorización dinámica: `prevalidar(session)` (si se pasa) corre SIEMPRE, en su propia
sesión de solo lectura, antes de reservar o de reproducir. Ahí va el alcance actual del
recurso (universo del supervisor, visibilidad de la decisión, …): si el actor perdió el
alcance desde que ejecutó, recibe 403/404 y no el replay almacenado. El rol se exige
antes de llamar. No repite el efecto de negocio.

Para ImportarLote la clave es `lote:<lote_id>` y el fingerprint incluye el hash canónico
de las filas (8.2: idempotente por lote, pero un mismo lote con contenido distinto es un
conflicto, no un replay silencioso).
"""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Callable

from psycopg.errors import LockNotAvailable
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.errores import Conflicto

TTL_HORAS = 24
RESERVA_SEGUNDOS = 120  # informativo: duración esperada de una ejecución


def fingerprint_de(metodo: str, ruta: str, body: Any) -> str:
    """Huella estable de la solicitud: método + ruta + body canonizado (claves ordenadas)."""
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)
    return hashlib.sha256(f"{metodo.upper()} {ruta}\n{canon}".encode()).hexdigest()


def hash_canonico(datos: Any) -> str:
    """Checksum estable de un contenido (p. ej. las filas de un lote)."""
    return hashlib.sha256(json.dumps(datos, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode()).hexdigest()


def _abrir_por_defecto(tenant_id: str):
    from app.db import tenant_session

    return tenant_session(tenant_id)


def _conflicto_reutilizada(clave: str) -> Conflicto:
    return Conflicto(
        "La Idempotency-Key ya se usó con otra solicitud (ruta, operación o body distintos)",
        {"idempotency_key": clave},
        codigo="clave_idempotencia_reutilizada",
    )


def _conflicto_en_proceso(clave: str) -> Conflicto:
    return Conflicto(
        "Otra solicitud con la misma Idempotency-Key está en proceso; reintentar en unos segundos",
        {"idempotency_key": clave},
        codigo="operacion_en_proceso",
    )


def _reservar(s: Session, tenant_id: str, actor_id: str, clave: str, fingerprint: str, token: uuid.UUID) -> dict | None:
    """None → seguir a Tx B. dict → replay. Conflicto → fingerprint distinto."""
    insertada = s.execute(
        text(
            "INSERT INTO modulo1.idempotency_keys (tenant_id, actor_id, idempotency_key, estado, fingerprint, "
            " reservation_token, resultado, expira_en, reservada_en, reservada_hasta) "
            "VALUES (:t, :a, :k, 'en_proceso', :fp, :tok, NULL, now() + make_interval(hours => :h), now(), "
            "        now() + make_interval(secs => :r)) "
            "ON CONFLICT (tenant_id, actor_id, idempotency_key) DO NOTHING RETURNING idempotency_key"
        ),
        {"t": tenant_id, "a": actor_id, "k": clave, "fp": fingerprint, "tok": token, "h": TTL_HORAS, "r": RESERVA_SEGUNDOS},
    ).first()
    if insertada is not None:
        return None
    fila = s.execute(
        text(
            "SELECT estado, fingerprint, resultado FROM modulo1.idempotency_keys "
            "WHERE tenant_id = :t AND actor_id = :a AND idempotency_key = :k"
        ),
        {"t": tenant_id, "a": actor_id, "k": clave},
    ).mappings().first()
    if fila is None:  # improbable: fila purgada entre el INSERT y el SELECT
        return _reservar(s, tenant_id, actor_id, clave, fingerprint, token)
    if fila["fingerprint"] != fingerprint:
        raise _conflicto_reutilizada(clave)
    if fila["estado"] == "completada":
        return fila["resultado"]
    return None


def ejecutar_idempotente(
    tenant_id: str,
    actor_id: str,
    clave: str | None,
    fingerprint: str,
    efecto: Callable[[Session], dict[str, Any]],
    abrir_sesion: Callable[[str], Any] | None = None,
    prevalidar: Callable[[Session], None] | None = None,
) -> dict[str, Any]:
    abrir = abrir_sesion or _abrir_por_defecto
    if prevalidar is not None:
        with abrir(tenant_id) as s:  # alcance ACTUAL, siempre, aunque haya replay
            prevalidar(s)
    if not clave:
        with abrir(tenant_id) as s:
            return efecto(s)
    actor_id = str(actor_id)
    mi_token = uuid.uuid4()

    with abrir(tenant_id) as s:  # Tx A
        replay = _reservar(s, tenant_id, actor_id, clave, fingerprint, mi_token)
    if replay is not None:
        return replay

    with abrir(tenant_id) as s:  # Tx B
        try:
            fila = s.execute(
                text(
                    "SELECT estado, fingerprint, resultado, reservation_token FROM modulo1.idempotency_keys "
                    "WHERE tenant_id = :t AND actor_id = :a AND idempotency_key = :k FOR UPDATE NOWAIT"
                ),
                {"t": tenant_id, "a": actor_id, "k": clave},
            ).mappings().first()
        except OperationalError as exc:
            if isinstance(exc.orig, LockNotAvailable):
                raise _conflicto_en_proceso(clave) from None
            raise
        if fila is None:
            raise _conflicto_en_proceso(clave)
        if fila["fingerprint"] != fingerprint:
            raise _conflicto_reutilizada(clave)
        if fila["estado"] == "completada":
            return fila["resultado"]
        if fila["reservation_token"] != mi_token:
            # Reserva huérfana (lock libre ⇒ nadie ejecutando): la recuperamos con token nuevo.
            mi_token = uuid.uuid4()
            s.execute(
                text(
                    "UPDATE modulo1.idempotency_keys SET reservation_token = :tok, reservada_en = now(), "
                    " reservada_hasta = now() + make_interval(secs => :r) "
                    "WHERE tenant_id = :t AND actor_id = :a AND idempotency_key = :k AND estado = 'en_proceso'"
                ),
                {"tok": mi_token, "r": RESERVA_SEGUNDOS, "t": tenant_id, "a": actor_id, "k": clave},
            )

        resultado = efecto(s)

        consolidadas = s.execute(
            text(
                "UPDATE modulo1.idempotency_keys SET estado = 'completada', resultado = CAST(:r AS jsonb), "
                " reservation_token = NULL "
                "WHERE tenant_id = :t AND actor_id = :a AND idempotency_key = :k "
                "  AND estado = 'en_proceso' AND reservation_token = :tok"
            ),
            {"t": tenant_id, "a": actor_id, "k": clave, "r": json.dumps(resultado, default=str), "tok": mi_token},
        ).rowcount
        if consolidadas != 1:
            # Imposible con el lock de fila sostenido; si pasa, no se confirma nada.
            raise _conflicto_en_proceso(clave)
        return resultado
