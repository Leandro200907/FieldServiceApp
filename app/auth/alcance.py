"""Alcance de visibilidad por rol — única fuente de verdad del "universo del supervisor"
(2.2 y 2.3 de modulo1-no-funcionales.md).

Dos preguntas distintas, que se responden acá y en ningún otro lado:

1. ¿Qué roles ven TODO el tenant para esta capacidad? Depende de la capacidad (la matriz
   2.2 no es uniforme: `configuracion` ve el log de auditoría pero no descarga evidencia),
   por eso se pasa explícito en `roles_con_todo`.
2. ¿Cuál es el universo de un supervisor? Siempre lo mismo, sea cual sea la capacidad:
   su propio legajo si tiene uno vinculado (`identidad.sujeto_id`) más los vehículos/
   equipos bajo su propia custodia vigente — el Supervisor también puede ser trabajador
   de campo y el rol no lo exime del cumplimiento documental —, más los sujetos con
   `asignacion_supervisor` vigente hacia él, más los vehículos/equipos bajo custodia
   vigente de esos sujetos (1.5 / 1.5 bis de documentacion-habilitante.md: la custodia
   es decisión del supervisor, y lo que custodia su gente es suyo de ver). El universo
   de un supervisor NUNCA es transitivo: si uno de sus supervisados es a su vez
   supervisor de terceros, esos terceros no entran — solo la asignación directa.
3. Un técnico se ve a sí mismo (`identidad.sujeto_id`) y a los vehículos/equipos bajo su
   custodia vigente (H-05; 1.5 / 1.5 bis: "mi vehículo/equipo asignado" es parte de su
   legajo compuesto). Nunca a otras personas.
4. Un usuario con roles Técnico + Supervisor acumula: legajo propio y sus recursos bajo
   custodia, más el universo de supervisión realmente asignado — nunca un universo
   ampliado ni transitivo por tener los dos roles.

Un supervisor sin asignaciones y sin legajo propio tiene universo vacío — nunca "todo":
el filtro vacío no abre el alcance.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.identidad import Identidad, Rol

ROLES_CON_TODO_LECTURA = (Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
ROLES_CON_TODO_DESCARGA = (Rol.RESPONSABLE_LEGAJOS,)

# `cambiar_custodia` cierra el período anterior (`estado='cerrado'`) en el mismo instante
# en que crea el siguiente, aunque el nuevo arranque en el futuro (transferencia
# programada) — así que `estado='vigente'` YA NO significa "vale hoy", significa "es el
# último asignado". El período efectivo HOY es el que cubre la fecha, esté `vigente` o
# recién `cerrado`: `desde <= hoy` y (`hasta` abierto o `hasta >= hoy`). Un período
# `corregido` (corregir_custodia) queda excluido siempre — es un error reemplazado, nunca
# la verdad de ningún día (auditoría externa hallazgo A-01, commit db400e6: antes de este
# fix, programar una transferencia futura le sacaba el acceso al custodio actual desde
# el momento en que se programaba, no desde que efectivamente empezaba la nueva).
CONDICION_CUSTODIA_EFECTIVA_HOY = (
    "p.estado IN ('vigente', 'cerrado') AND p.desde <= :hoy AND (p.hasta IS NULL OR p.hasta >= :hoy)"
)

_SQL_UNIVERSO = f"""
    WITH personas AS (
        SELECT sujeto_id FROM modulo1.asignacion_supervisor
        WHERE supervisor_usuario_id = CAST(:u AS uuid) AND estado = 'vigente' AND desde <= :hoy
    )
    SELECT sujeto_id FROM personas
    UNION
    SELECT c.recurso_id
    FROM modulo1.periodo_custodia p
    JOIN modulo1.custodia_recurso c ON c.custodia_id = p.custodia_id
    WHERE {CONDICION_CUSTODIA_EFECTIVA_HOY} AND p.custodio_id IN (SELECT sujeto_id FROM personas)
"""


def universo_del_supervisor(session: Session, identidad: Identidad, hoy: date) -> list[str]:
    filas = session.execute(text(_SQL_UNIVERSO), {"u": identidad.usuario_id, "hoy": hoy}).all()
    return [f[0] for f in filas]


def alcance_de_sujetos(
    session: Session,
    identidad: Identidad,
    hoy: date,
    roles_con_todo: tuple[Rol, ...] = ROLES_CON_TODO_LECTURA,
) -> list[str] | None:
    """None = sin filtro (ve todo el tenant); lista = solo esos sujeto_id."""
    if identidad.tiene_rol(*roles_con_todo):
        return None
    propio: list[str] = []
    if identidad.sujeto_id:
        propio = [identidad.sujeto_id] + recursos_bajo_custodia(session, identidad.sujeto_id, hoy)
    if identidad.tiene_rol(Rol.SUPERVISOR):
        # Acumula: legajo propio (si lo tiene) + universo de supervisión realmente
        # asignado, sin duplicar y sin transitividad (universo_del_supervisor ya no
        # sigue cadenas de supervisor a supervisor).
        return list(dict.fromkeys(propio + universo_del_supervisor(session, identidad, hoy)))
    if identidad.tiene_rol(Rol.TECNICO) and identidad.sujeto_id:
        return propio
    return []


def recursos_bajo_custodia(session: Session, custodio_id: str, hoy: date) -> list[str]:
    """Vehículos/equipos cuyo período de custodia EFECTIVO HOY (ver
    `CONDICION_CUSTODIA_EFECTIVA_HOY`) es de esta persona: ni un período que todavía no
    empezó (transferencia futura recién programada), ni uno que ya terminó."""
    return [f[0] for f in session.execute(text(
        f"SELECT c.recurso_id FROM modulo1.periodo_custodia p "
        f"JOIN modulo1.custodia_recurso c ON c.tenant_id = p.tenant_id AND c.custodia_id = p.custodia_id "
        f"WHERE {CONDICION_CUSTODIA_EFECTIVA_HOY} AND p.custodio_id = :cu ORDER BY c.recurso_id"),
        {"cu": custodio_id, "hoy": hoy}).all()]


def periodo_custodia_efectivo(session: Session, tenant_id: str, recurso_id: str, hoy: date) -> dict | None:
    """El período de custodia que cubre `hoy` para este recurso (vigente o recién cerrado
    por una transferencia futura todavía no iniciada), o None si nadie lo custodia hoy."""
    fila = session.execute(text(
        f"SELECT c.tipo_recurso, p.periodo_id::text AS periodo_id, p.custodio_id, p.desde, p.hasta "
        f"FROM modulo1.periodo_custodia p "
        f"JOIN modulo1.custodia_recurso c ON c.tenant_id = p.tenant_id AND c.custodia_id = p.custodia_id "
        f"WHERE p.tenant_id = :t AND c.recurso_id = :r AND {CONDICION_CUSTODIA_EFECTIVA_HOY}"),
        {"t": tenant_id, "r": recurso_id, "hoy": hoy}).mappings().first()
    return dict(fila) if fila is not None else None


def sujeto_en_alcance(
    session: Session,
    identidad: Identidad,
    sujeto_id: str,
    hoy: date,
    roles_con_todo: tuple[Rol, ...] = ROLES_CON_TODO_LECTURA,
) -> bool:
    alcance = alcance_de_sujetos(session, identidad, hoy, roles_con_todo)
    return alcance is None or sujeto_id in alcance


def filtro_decisiones_visibles(alcance: list[str] | None, alias: str = "e", param: str = "alcance") -> str:
    """Fragmento SQL (AND ...) que deja pasar solo las decisiones cuyos sujetos propuestos
    están TODOS en `alcance` (2.3 §3, regla cerrada A-04: si uno queda afuera, la decisión
    entera no existe para ese usuario). La empresa nunca es "propuesta", así que no
    interviene. `alcance=None` → sin filtro. El llamador debe bindear `param` como text[]."""
    if alcance is None:
        return ""
    return (
        f" AND NOT EXISTS (SELECT 1 FROM modulo1.evaluacion_sujeto_propuesto p "
        f"WHERE p.evaluacion_id = {alias}.referencia_evaluacion "
        f"AND NOT (p.sujeto_id = ANY(CAST(:{param} AS text[]))))"
    )


def decision_visible(session: Session, identidad: Identidad, referencia_evaluacion: str, hoy: date) -> bool:
    alcance = alcance_de_sujetos(session, identidad, hoy)
    fila = session.execute(
        text(
            "SELECT 1 FROM modulo1.evaluacion_habilitacion e WHERE e.referencia_evaluacion = CAST(:r AS uuid)"
            + filtro_decisiones_visibles(alcance)
        ),
        {"r": referencia_evaluacion, "alcance": list(alcance) if alcance is not None else None},
    ).first()
    return fila is not None
