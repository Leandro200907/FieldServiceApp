"""Identidad de servicio y estado acumulado por tenant."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from app.auth.identidad import Identidad, Rol
from scripts.administracion import crear_tenant, crear_usuario, desactivar_usuario
from scripts.demo.config import ROLES, TenantDemo


def identidad_de(tenant_id: str, usuario_id: str, rol: str, sujeto_id: str | None = None) -> Identidad:
    return Identidad(
        tenant_id=tenant_id,
        usuario_id=usuario_id,
        roles=frozenset({Rol(rol)}),
        sujeto_id=sujeto_id,
    )


@dataclass
class UsuarioDemo:
    email: str
    nombre: str
    rol: str
    usuario_id: str
    sujeto_id: str | None = None
    activo: bool = True


@dataclass
class EstadoTenant:
    spec: TenantDemo
    tenant_id: str
    usuarios: list[UsuarioDemo] = field(default_factory=list)
    sujetos: dict[str, str] = field(default_factory=dict)  # clave lógica → sujeto_id
    requisitos: dict[str, str] = field(default_factory=dict)  # nombre demo → uuid
    catalogos: dict[str, str] = field(default_factory=dict)  # operadora/loc/ts keys
    documentos: dict[str, str] = field(default_factory=dict)
    ocs: dict[str, str] = field(default_factory=dict)  # escenario → oc_id
    paquete_vigente_url: str | None = None
    alerta_id: str | None = None
    notas_supervisor: dict[str, str] = field(default_factory=dict)  # email supervisor → nota en tabla final

    def uid(self, rol: str, n: int) -> UsuarioDemo:
        for u in self.usuarios:
            if u.rol == rol and u.email.startswith(f"{rol}{n}@"):
                return u
        raise KeyError(f"usuario {rol}{n}")

    def idn(self, rol: str, n: int = 1) -> Identidad:
        u = self.uid(rol, n)
        return identidad_de(self.tenant_id, u.usuario_id, rol, u.sujeto_id)


def crear_usuarios_demo(est: EstadoTenant, password: str, nombres_iter) -> None:
    est.tenant_id = crear_tenant(est.spec.slug, est.spec.nombre, "America/Argentina/Buenos_Aires")

    for rol in ROLES:
        for n in (1, 2, 3):
            nom, ape = next(nombres_iter)
            email = f"{rol}{n}@{est.spec.slug}.demo.test"
            sujeto = None
            if rol == "tecnico":
                sujeto = f"persona_{est.spec.slug.replace('-', '_')}_t{n}"
                est.sujetos[f"tecnico{n}"] = sujeto
            uid = crear_usuario(est.spec.slug, email, f"{nom} {ape}", [rol], password, sujeto)
            est.usuarios.append(UsuarioDemo(email=email, nombre=f"{nom} {ape}", rol=rol, usuario_id=uid, sujeto_id=sujeto))

    extra_email = f"inactivo@{est.spec.slug}.demo.test"
    uid_inactivo = crear_usuario(est.spec.slug, extra_email, "Usuario Inactivo Demo", ["configuracion"], password, None)
    desactivar_usuario(est.spec.slug, extra_email)
    est.usuarios.append(UsuarioDemo(email=extra_email, nombre="Usuario Inactivo Demo", rol="configuracion", usuario_id=uid_inactivo, activo=False))
