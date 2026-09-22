"""Motor de quiebres de la proyección documental — función pura, sin I/O (mismo estándar
que `app/core/evaluacion.py`: value objects puros, sin ORM, sin reloj del sistema).

Implementa docs/PROYECCION_DOCUMENTAL.md, puntos 5 a 8. Reutiliza
`evaluar_documento_en_periodo` TAL CUAL — evaluar la cobertura de un candidato en UN día
puntual es evaluarlo en un "período" de un solo día (`periodo_desde == periodo_hasta ==
ese día`), sin reabrir el motor. Deliberadamente NO reutiliza `excepcion_tiene_efecto` ni
`resolver_constancia_aplicable` (punto 1 del documento no las lista entre lo reutilizado):
la proyección mira cobertura documental cruda, no decisiones con excepción/constancia —
esas viven en `proyeccion_documental?commitment_id=…` mismo día vía el motor completo si
en algún momento se decide ampliar, pero HOY el diseño es deliberadamente más simple.

Vocabulario cerrado: `ESTADO_INTERVALO` son los 3 valores que puede tener un intervalo en
sí mismo (punto 6 del documento); el cálculo del resumen (punto 7) vive en
`app/modules/proyeccion/servicio.py`, que es quien conoce la OC y decide cuál es el
"primer intervalo".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from app.core.evaluacion import evaluar_documento_en_periodo
from app.core.tipos import Documento, Veredicto

EstadoIntervalo = Literal["bloqueo_confirmado", "requiere_revision", "sin_riesgos_detectados"]

# `peor()` entre los 3 valores de intervalo — mismo patrón que `ORDEN_VEREDICTO` de
# `app/core/orquestacion.py`, extendido a este vocabulario.
_ORDEN_ESTADO_INTERVALO: dict[EstadoIntervalo, int] = {
    "sin_riesgos_detectados": 0,
    "requiere_revision": 1,
    "bloqueo_confirmado": 2,
}


@dataclass(frozen=True)
class Candidato:
    sujeto_id: str
    tipo_sujeto: str


@dataclass(frozen=True)
class CausaTipo:
    """Motivo de por qué un tipo exigido no tiene cobertura completa en un intervalo."""
    tipo_sujeto: str
    requisito_definicion_id: str | None
    motivo: str
    sujetos_que_pierden_cobertura: list[str] = field(default_factory=list)
    sujetos_que_mantienen_cobertura: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Intervalo:
    desde: date
    hasta: date
    estado: EstadoIntervalo
    capacidad_documental_potencial: dict[str, int]
    causas: list[CausaTipo] = field(default_factory=list)


def _cubre_en_dia(documento: Documento | None, dia: date) -> tuple[bool, bool]:
    """(cubre, es_por_revision). `evaluar_documento_en_periodo` con un período de un solo
    día colapsa a HABILITADO o NO_HABILITADO — `vence_durante_el_trabajo` no puede darse
    porque `periodo_desde == periodo_hasta`."""
    if documento is None:
        return False, False
    vr = evaluar_documento_en_periodo(documento, dia, dia)
    if vr.veredicto == Veredicto.HABILITADO:
        return True, False
    if vr.veredicto == Veredicto.REQUIERE_REVISION:
        return False, True
    return False, False


def puntos_de_quiebre(
    evidencias: dict[tuple[str, str], Documento], desde: date, hasta: date
) -> list[date]:
    """Fechas donde el resultado de ALGÚN (candidato, requisito) puede cambiar, dentro de
    `[desde, hasta]` — punto 8: `vigente_hasta + 1` de cada evidencia en juego. Siempre
    incluye `desde` y `hasta + 1` (límite, no se evalúa) como extremos del rango."""
    puntos = {desde, hasta + timedelta(days=1)}
    for doc in evidencias.values():
        if doc.vigente_hasta is not None:
            quiebre = doc.vigente_hasta + timedelta(days=1)
            if desde < quiebre <= hasta:
                puntos.add(quiebre)
    return sorted(puntos)


def calcular_intervalos(
    candidatos: list[Candidato],
    requisitos_por_tipo: dict[str, list[str]],
    requisito_nombre: dict[str, str],
    evidencias: dict[tuple[str, str], Documento],
    desde: date,
    hasta: date,
) -> list[Intervalo]:
    """Un `Intervalo` por tramo constante entre dos puntos de quiebre consecutivos.
    `requisitos_por_tipo`: {tipo_sujeto: [requisito_definicion_id, …]} — los tipos
    exigidos por la matriz/requisito particular (punto 1: fijos para toda la OC, nunca
    cambian día a día). `evidencias`: {(sujeto_id, requisito_definicion_id): Documento}."""
    quiebres = puntos_de_quiebre(evidencias, desde, hasta)
    intervalos: list[Intervalo] = []
    for i in range(len(quiebres) - 1):
        i_desde = quiebres[i]
        i_hasta = quiebres[i + 1] - timedelta(days=1)
        capacidad: dict[str, int] = {}
        causas: list[CausaTipo] = []
        estado: EstadoIntervalo = "sin_riesgos_detectados"
        for tipo, requisitos in requisitos_por_tipo.items():
            cubren: list[str] = []
            pierden_por_revision: list[str] = []
            pierden_sin_revision: list[str] = []
            # cuántos candidatos de este tipo fallan cada requisito — el más fallado es
            # el que se cita en la causa (representativo, no necesariamente el único).
            fallas_por_requisito: dict[str, int] = {r: 0 for r in requisitos}
            revision_por_requisito: dict[str, bool] = {r: False for r in requisitos}
            for c in (c for c in candidatos if c.tipo_sujeto == tipo):
                cubre_todos = True
                alguna_revision = False
                for req_id in requisitos:
                    ok, es_revision = _cubre_en_dia(evidencias.get((c.sujeto_id, req_id)), i_desde)
                    if not ok:
                        cubre_todos = False
                        fallas_por_requisito[req_id] += 1
                        if es_revision:
                            alguna_revision = True
                            revision_por_requisito[req_id] = True
                if cubre_todos:
                    cubren.append(c.sujeto_id)
                elif alguna_revision:
                    pierden_por_revision.append(c.sujeto_id)
                else:
                    pierden_sin_revision.append(c.sujeto_id)
            capacidad[tipo] = len(cubren)
            if cubren:
                continue  # tipo cubierto este intervalo: sin causa que explicar
            # requisito representativo: el más fallado (empate → el primero en orden de matriz).
            req_representativo = max(requisitos, key=lambda r: fallas_por_requisito[r]) if requisitos else None
            if pierden_por_revision:
                estado = max(estado, "requiere_revision", key=lambda e: _ORDEN_ESTADO_INTERVALO[e])
                causas.append(CausaTipo(
                    tipo_sujeto=tipo, requisito_definicion_id=req_representativo,
                    motivo=(f"{requisito_nombre.get(req_representativo, req_representativo)}: "
                            f"depende de un documento que requiere revisión, no se cuenta como cobertura real"),
                    sujetos_que_pierden_cobertura=sorted(pierden_por_revision),
                    sujetos_que_mantienen_cobertura=[],
                ))
            else:
                estado = "bloqueo_confirmado"
                causas.append(CausaTipo(
                    tipo_sujeto=tipo, requisito_definicion_id=req_representativo,
                    motivo=(f"{requisito_nombre.get(req_representativo, req_representativo)}: "
                            f"ningún candidato de tipo {tipo} lo cubre en este tramo"),
                    sujetos_que_pierden_cobertura=sorted(pierden_sin_revision),
                    sujetos_que_mantienen_cobertura=[],
                ))
        intervalos.append(Intervalo(
            desde=i_desde, hasta=i_hasta, estado=estado,
            capacidad_documental_potencial=capacidad, causas=causas,
        ))
    return intervalos
