"""Identidad autenticada — el ÚNICO origen válido del tenant_id en runtime (8.1).

`Identidad` la construye app/auth/dependencies.py a partir del JWT validado; los routers
la reciben por Depends y abren `tenant_session(identidad.tenant_id)`. Ningún router
acepta tenant_id por query/body/header.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from app.api.errores import Prohibido


class Rol(str, Enum):
    CONFIGURACION = "configuracion"
    RESPONSABLE_LEGAJOS = "responsable_legajos"
    SUPERVISOR = "supervisor"
    TECNICO = "tecnico"


@dataclass(frozen=True)
class Identidad:
    tenant_id: str
    usuario_id: str
    roles: frozenset[Rol] = field(default_factory=frozenset)
    sujeto_id: str | None = None  # Legajo propio (técnico 1:1; supervisor opcional)

    def tiene_rol(self, *roles: Rol) -> bool:
        return any(r in self.roles for r in roles)

    def exigir_rol(self, *roles: Rol) -> None:
        """Matriz de permisos 2.2 de no-funcionales: un permiso exclusivo de un rol se
        ejerce solo si el usuario tiene ESE rol."""
        if not self.tiene_rol(*roles):
            raise Prohibido(
                "El usuario no tiene un rol habilitado para este comando",
                {"roles_requeridos": [r.value for r in roles]},
            )
