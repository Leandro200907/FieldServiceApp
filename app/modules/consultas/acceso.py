"""Acceso compartido por las piezas Consultas y OC: identidad autenticada y "universo"
del supervisor (2.2 de no-funcionales).

`identidad_actual` se reexporta desde `app.auth.dependencies` (pieza Auth).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.identidad import Identidad, Rol

from app.auth.dependencies import identidad_actual  # noqa: F401 - reexport para oc/consultas


def ve_todo_el_tenant(identidad: Identidad) -> bool:
    """responsable_legajos y configuracion ven toda la empresa; el resto se acota."""
    return identidad.tiene_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)


def universo_del_supervisor(session: Session, identidad: Identidad, hoy) -> list[str]:
    """Sujetos con `asignacion_supervisor` vigente hacia este usuario, más los
    vehículos/equipos bajo custodia vigente de esos sujetos (brief, "su universo")."""
    filas = session.execute(
        text(
            """
            WITH personas AS (
                SELECT sujeto_id FROM modulo1.asignacion_supervisor
                WHERE supervisor_usuario_id = :u AND estado = 'vigente' AND desde <= :hoy
            )
            SELECT sujeto_id FROM personas
            UNION
            SELECT c.recurso_id
            FROM modulo1.periodo_custodia p
            JOIN modulo1.custodia_recurso c ON c.custodia_id = p.custodia_id
            WHERE p.estado = 'vigente' AND p.custodio_id IN (SELECT sujeto_id FROM personas)
            """
        ),
        {"u": identidad.usuario_id, "hoy": hoy},
    ).all()
    return [f[0] for f in filas]


def alcance_de_sujetos(session: Session, identidad: Identidad, hoy) -> list[str] | None:
    """None = sin filtro (ve todo el tenant); lista = solo esos sujeto_id.

    Un técnico solo se ve a sí mismo; un supervisor, su universo. Un supervisor sin
    asignaciones ve una lista vacía, no todo (el filtro vacío no debe abrir el alcance).
    """
    if ve_todo_el_tenant(identidad):
        return None
    if identidad.tiene_rol(Rol.SUPERVISOR):
        return universo_del_supervisor(session, identidad, hoy)
    return [identidad.sujeto_id] if identidad.sujeto_id else []
