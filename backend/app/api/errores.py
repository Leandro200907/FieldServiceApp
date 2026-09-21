"""Envelope de error único para toda la API (9.6) y diagnóstico de errores internos.

Todo error sale con la misma forma:
    {"error": {"codigo": "...", "mensaje": "...", "detalles": {...} | null, "request_id": "..."}}
y el status HTTP correspondiente. Los routers levantan `ErrorDeDominio` (o sus
subclases) y el handler registrado en app/main.py lo traduce — nunca se arman
respuestas de error a mano en un router.

Diagnóstico (cierre operativo):
- cada request lleva un `request_id` (header `X-Request-ID` entrante o uuid4 nuevo),
  devuelto siempre en el header `X-Request-ID` de la respuesta;
- un 500 se registra con stack trace, método, ruta y `request_id`; al cliente sólo le
  llega un mensaje genérico con el `request_id` para correlacionar. NUNCA se registran
  headers, cuerpos, tokens ni contraseñas;
- los 422 de validación no devuelven el `input` recibido (podría ser una contraseña).
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth.passwords import PasswordDemasiadoLarga

log = logging.getLogger("modulo1.api")

HEADER_REQUEST_ID = "X-Request-ID"


class ErrorDeDominio(Exception):
    status = 422
    codigo = "regla_de_dominio"

    def __init__(self, mensaje: str, detalles: dict[str, Any] | None = None, codigo: str | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.detalles = detalles
        if codigo:
            self.codigo = codigo


class NoEncontrado(ErrorDeDominio):
    status = 404
    codigo = "no_encontrado"


class Conflicto(ErrorDeDominio):
    status = 409
    codigo = "conflicto"


class NoAutenticado(ErrorDeDominio):
    status = 401
    codigo = "no_autenticado"


class Prohibido(ErrorDeDominio):
    status = 403
    codigo = "prohibido"


def envelope(codigo: str, mensaje: str, detalles: Any = None, request_id: str | None = None) -> dict:
    cuerpo: dict[str, Any] = {"codigo": codigo, "mensaje": mensaje, "detalles": jsonable_encoder(detalles)}
    if request_id:
        cuerpo["request_id"] = request_id
    return {"error": cuerpo}


def request_id_de(request: Request) -> str:
    return getattr(request.state, "request_id", None) or "-"


def _respuesta(request: Request, status: int, codigo: str, mensaje: str, detalles: Any = None) -> JSONResponse:
    rid = request_id_de(request)
    return JSONResponse(status_code=status, content=envelope(codigo, mensaje, detalles, rid), headers={HEADER_REQUEST_ID: rid})


def _errores_de_validacion_sin_input(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Ubicación, tipo y mensaje del error; nunca el valor recibido (`input`) ni el `ctx`
    (que puede contener el valor o una excepción con él)."""
    return [{"loc": e.get("loc"), "tipo": e.get("type"), "mensaje": e.get("msg")} for e in exc.errors()]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Asigna/propaga el `request_id` y lo devuelve en todas las respuestas."""

    async def dispatch(self, request: Request, call_next):
        entrante = request.headers.get(HEADER_REQUEST_ID, "").strip()
        rid = entrante[:64] if entrante and entrante.isprintable() else str(uuid.uuid4())
        request.state.request_id = rid
        respuesta = await call_next(request)
        respuesta.headers[HEADER_REQUEST_ID] = rid
        return respuesta


def registrar_handlers(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(ErrorDeDominio)
    async def _dominio(request: Request, exc: ErrorDeDominio):
        return _respuesta(request, exc.status, exc.codigo, exc.mensaje, exc.detalles)

    @app.exception_handler(RequestValidationError)
    async def _validacion(request: Request, exc: RequestValidationError):
        return _respuesta(request, 422, "validacion", "Request inválido", _errores_de_validacion_sin_input(exc))

    @app.exception_handler(PasswordDemasiadoLarga)
    async def _password_larga(request: Request, exc: PasswordDemasiadoLarga):
        # Red de seguridad para cualquier ruta que hashee (alta/cambio de contraseña):
        # 422 estable, sin la contraseña en la respuesta ni en el log.
        return _respuesta(request, 422, exc.codigo, str(exc), {"max_bytes": 72, "bytes_recibidos": exc.bytes_recibidos})

    @app.exception_handler(IntegrityError)
    async def _integridad(request: Request, exc: IntegrityError):
        # Red de seguridad: una restricción de la base (UNIQUE/CHECK/FK) que la lógica no
        # anticipó — típicamente una carrera — es un conflicto reintentable, no un 500.
        # La transacción ya quedó revertida por tenant_session.
        nombre = getattr(getattr(exc, "orig", None), "diag", None)
        restriccion = getattr(nombre, "constraint_name", None)
        return _respuesta(request, 409, "conflicto_concurrencia",
                          "La operación chocó con una restricción de la base; reintentar", {"restriccion": restriccion})

    @app.exception_handler(Exception)
    async def _generico(request: Request, exc: Exception):
        # Stack trace completo al log con el request_id; sólo método y ruta (sin query,
        # sin headers, sin cuerpo). Al cliente: mensaje genérico + request_id.
        log.error(
            "500 request_id=%s %s %s -> %s",
            request_id_de(request), request.method, request.url.path, type(exc).__name__,
            exc_info=exc,
        )
        return _respuesta(request, 500, "error_interno", "Error interno; informá el request_id")
