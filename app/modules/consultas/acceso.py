"""Acceso compartido por las piezas Consultas y OC.

La lógica de alcance vive en `app.auth.alcance` (única fuente de verdad del "universo
del supervisor"); acá solo se reexporta para no cambiar los imports de esta pieza.
"""
from __future__ import annotations

from app.auth.alcance import alcance_de_sujetos, universo_del_supervisor  # noqa: F401
from app.auth.dependencies import identidad_actual  # noqa: F401 - reexport para oc/consultas
from app.auth.identidad import Identidad, Rol


def ve_todo_el_tenant(identidad: Identidad) -> bool:
    """responsable_legajos y configuracion ven toda la empresa; el resto se acota."""
    return identidad.tiene_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
