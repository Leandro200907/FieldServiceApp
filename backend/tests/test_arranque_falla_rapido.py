"""Auditoría externa: `_montar_routers` tragaba `ModuleNotFoundError` y dejaba arrancar
la API igual si un módulo listado en `ROUTERS` no existía — en producción eso significa
rutas enteras ausentes en silencio, sin ningún error visible en el arranque."""
from __future__ import annotations

import pytest

from app import main as main_module


def test_montar_routers_falla_si_un_modulo_de_router_no_existe(monkeypatch):
    monkeypatch.setattr(main_module, "ROUTERS", ["app.modules.no_existe_de_verdad_xyz"])
    with pytest.raises(ModuleNotFoundError):
        main_module._montar_routers()
