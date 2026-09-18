"""Envelope de error único para toda la API (9.6).

Todo error sale con la misma forma:
    {"error": {"codigo": "...", "mensaje": "...", "detalles": {...} | null}}
y el status HTTP correspondiente. Los routers levantan `ErrorDeDominio` (o sus
subclases) y el handler registrado en app/main.py lo traduce — nunca se arman
respuestas de error a mano en un router.
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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


def envelope(codigo: str, mensaje: str, detalles: Any = None) -> dict:
    return {"error": {"codigo": codigo, "mensaje": mensaje, "detalles": jsonable_encoder(detalles)}}


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErrorDeDominio)
    async def _dominio(_: Request, exc: ErrorDeDominio):
        return JSONResponse(status_code=exc.status, content=envelope(exc.codigo, exc.mensaje, exc.detalles))

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content=envelope("validacion", "Request inválido", exc.errors()))

    @app.exception_handler(Exception)
    async def _generico(_: Request, exc: Exception):
        return JSONResponse(status_code=500, content=envelope("error_interno", "Error interno"))
