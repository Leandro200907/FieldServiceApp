"""Hash y verificación de contraseñas con bcrypt (9.2).

Se usa `bcrypt` directo, no passlib: passlib está roto con bcrypt >= 4.1 en Python
3.13 (lee `bcrypt.__about__`, que ya no existe).

Límite por BYTES, no por caracteres (M-06): bcrypt sólo mira los primeros 72 bytes de
la contraseña codificada en UTF-8 y trunca el resto en silencio. Una contraseña de 72
caracteres multibyte supera el límite. Acá se mide `len(password.encode("utf-8"))` y
nunca se trunca: hashear una contraseña más larga es un error de dominio (422 estable),
y verificar una más larga es simplemente "no coincide" — jamás se compara el prefijo.
"""
from __future__ import annotations

import bcrypt

MAX_BYTES = 72  # límite duro del algoritmo bcrypt
_COSTO = 12


class PasswordDemasiadoLarga(ValueError):
    """La contraseña supera los MAX_BYTES bytes en UTF-8. No lleva la contraseña."""

    codigo = "password_demasiado_larga"

    def __init__(self, bytes_recibidos: int):
        super().__init__(f"La contraseña no puede superar los {MAX_BYTES} bytes en UTF-8 (recibidos: {bytes_recibidos})")
        self.bytes_recibidos = bytes_recibidos


def bytes_de(password: str) -> int:
    return len(password.encode("utf-8"))


def validar_longitud(password: str) -> None:
    """Rechaza (sin truncar) toda contraseña que bcrypt no pueda procesar entera."""
    n = bytes_de(password)
    if n > MAX_BYTES:
        raise PasswordDemasiadoLarga(n)


def hashear_password(password: str) -> str:
    """Devuelve el hash bcrypt (str con sal incluida) listo para `usuario.password_hash`.
    Lanza PasswordDemasiadoLarga si supera los 72 bytes: nunca se hashea un prefijo."""
    return bcrypt.hashpw(_a_bytes(password), bcrypt.gensalt(rounds=_COSTO)).decode("ascii")


def verificar_password(password: str, password_hash: str | None) -> bool:
    """True si la contraseña coincide con el hash. Un hash malformado o vacío, o una
    contraseña más larga que el límite, es simplemente "no coincide" — nunca revienta con
    excepción hacia el login ni compara los primeros 72 bytes."""
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(_a_bytes(password), password_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False


def _a_bytes(password: str) -> bytes:
    validar_longitud(password)
    return password.encode("utf-8")
