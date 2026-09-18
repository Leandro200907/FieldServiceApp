"""FastAPI app — monta los routers de cada módulo bajo /v1 (9.6, versionado desde el día uno).

Cada módulo expone un `router` en app/<paquete>/router.py; los de comandos exponen
POST /comandos/<nombre>, los de consultas GET /consultas/<nombre>.
"""
import importlib

from fastapi import FastAPI

from app.api.errores import registrar_handlers

app = FastAPI(title="Módulo 1 — Documentación habilitante", version="1")
registrar_handlers(app)

PREFIJO = "/v1"

ROUTERS = [
    "app.auth.router",
    "app.modules.legajos.router",
    "app.modules.requisitos.router",
    "app.modules.operacion.router",
    "app.modules.oc.router",
    "app.modules.consultas.router",
    "app.storage.router",
]


@app.get(f"{PREFIJO}/salud")
def salud() -> dict:
    return {"ok": True}


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
