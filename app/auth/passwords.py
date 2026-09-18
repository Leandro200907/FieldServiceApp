"""Hash y verificación de contraseñas con bcrypt (9.2).

Se usa `bcrypt` directo, no passlib: passlib está roto con bcrypt >= 4.1 en Python
3.13 (lee `bcrypt.__about__`, que ya no existe). bcrypt trunca a 72 bytes, así que
se limita explícitamente para que dos contraseñas que difieren después del byte 72
no se comporten como iguales sin que nadie lo sepa.
"""
from __future__ import annotations

import bcrypt

_MAX_BYTES = 72
_COSTO = 12


def hashear_password(password: str) -> str:
    """Devuelve el hash bcrypt (str con sal incluida) listo para `usuario.password_hash`."""
    return bcrypt.hashpw(_a_bytes(password), bcrypt.gensalt(rounds=_COSTO)).decode("ascii")


def verificar_password(password: str, password_hash: str | None) -> bool:
    """True si la contraseña coincide con el hash. Un hash malformado o vacío es
    simplemente "no coincide" — nunca revienta con excepción hacia el login."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_a_bytes(password), password_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def _a_bytes(password: str) -> bytes:
    datos = password.encode("utf-8")
    if len(datos) > _MAX_BYTES:
        raise ValueError("La contraseña no puede superar los 72 bytes")
    return datos
