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
    "app.modules.oc.router",
    "app.modules.consultas.router",
    "app.storage.router",
]


def _montar_routers() -> None:
    """Importa routers de forma tolerante: si un módulo todavía no existe, la app
    igual levanta (útil mientras las piezas se construyen en paralelo)."""
    for nombre in ROUTERS:
        try:
            mod = importlib.import_module(nombre)
        except ModuleNotFoundError as e:
            if e.name and nombre.startswith(e.name):
                continue
            raise
        app.include_router(mod.router, prefix=PREFIJO)


_montar_routers()
