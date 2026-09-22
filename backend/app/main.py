"""FastAPI app — monta los routers de cada módulo bajo /v1 (9.6, versionado desde el día uno).

Cada módulo expone un `router` en app/<paquete>/router.py; los de comandos exponen
POST /comandos/<nombre>, los de consultas GET /consultas/<nombre>.
"""
import importlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errores import registrar_handlers
from app.config import describir_entorno
from app.openapi_extra import enriquecer
from app.version import VERSION

log = logging.getLogger("modulo1.api")


@asynccontextmanager
async def _ciclo_de_vida(_: FastAPI):
    log.info("api arranca: version=%s %s", VERSION, describir_entorno())  # sin secretos ni DSN completo
    yield


app = FastAPI(title="Módulo 1 — Documentación habilitante", version=VERSION, lifespan=_ciclo_de_vida)
registrar_handlers(app)

PREFIJO = "/v1"

ROUTERS = [
    "app.api.salud",
    "app.auth.router",
    "app.modules.legajos.router",
    "app.modules.requisitos.router",
    "app.modules.operacion.router",
    "app.modules.alertas.router",
    "app.modules.paquete.router",
    "app.modules.capacidades_router",
    "app.modules.evidencia.router",
    "app.modules.oc.router",
    "app.modules.consultas.router",
    "app.storage.router",
]


def _montar_routers() -> None:
    """Importa todos los routers listados en `ROUTERS`. Si alguno falta, el arranque
    falla explícitamente (ModuleNotFoundError) en lugar de levantar una API con rutas
    ausentes en silencio."""
    for nombre in ROUTERS:
        mod = importlib.import_module(nombre)
        app.include_router(mod.router, prefix=PREFIJO)


_montar_routers()

# El esquema OpenAPI que la API sirve en `/openapi.json` es el MISMO objeto, ya
# enriquecido, que usa `scripts/generar_openapi.py` para el archivo canónico (9.6,
# auditoría externa hallazgo 3): `app.openapi()` construye y cachea el esquema crudo en
# `app.openapi_schema`; `enriquecer` lo muta in place, así que la caché queda enriquecida
# y las llamadas siguientes (incluida la ruta real `/openapi.json`) devuelven eso mismo.
enriquecer(app.openapi())
