"""Motor de quiebres de la proyección documental — función pura, sin I/O (mismo estándar
que `app/core/evaluacion.py`: value objects puros, sin ORM, sin reloj del sistema).

Implementa docs/PROYECCION_DOCUMENTAL.md, puntos 5 a 8 y 15bis. Reutiliza
`evaluar_documento_en_periodo` TAL CUAL — evaluar la cobertura de un candidato en UN día
puntual es evaluarlo en un "período" de un solo día (`periodo_desde == periodo_hasta ==
ese día`), sin reabrir el motor. También reutiliza `excepcion_tiene_efecto` y
`resolver_constancia_aplicable` (hallazgo B-02, auditoría externa 2026-09-22: el diseño
§8 siempre las listó como quiebres; el código anterior las excluía "a propósito", lo que
contradecía el propio diseño y podía dar `bloqueo_confirmado` en un día donde
`cobertura_oc` — que sí las usa — daría habilitado). Constancias/excepciones son
parámetros opcionales (default vacío): con evidencia sola, el resultado es idéntico al
motor anterior — ver `tests/test_motor_proyeccion.py`.

Vocabulario cerrado: `ESTADO_INTERVALO` son los 3 valores que puede tener un intervalo en
sí mismo (punto 6 del documento); el cálculo del resumen (punto 7) vive en
`app/modules/proyeccion/servicio.py`, que es quien conoce la OC y decide cuál es el
"primer intervalo".
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from typing import Literal

from app.core.evaluacion import evaluar_documento_en_periodo, excepcion_tiene_efecto, resolver_constancia_aplicable
from app.core.orquestacion import VEREDICTOS_EXCEPCIONABLES
from app.core.tipos import Clasificacion, Constancia, Documento, EstadoConstancia, Excepcion, Veredicto

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


def _constancia_efectiva_en(c: Constancia, dia: date) -> Constancia:
    """Espejo, por día puntual, de la degradación VIGENTE→VENCIDA que
    `app/core/orquestacion.py::cargar_constancias` hace relativa a `hoy` — acá relativa al
    día que se está evaluando, porque la proyección recorre un rango, no un solo `hoy`."""
    if c.estado == EstadoConstancia.VIGENTE and c.vigencia is not None and c.vigencia < dia:
        return replace(c, estado=EstadoConstancia.VENCIDA)
    return c


def _asignable_en_dia(
    documento: Documento | None, dia: date, *,
    clasificacion: Clasificacion | None,
    constancias_del_par: list[Constancia],
    excepcion: Excepcion | None,
    sujeto_id: str, req_id: str, cliente_id: str, commitment_id: str,
) -> tuple[bool, bool]:
    """(asignable, pierde_por_revision) — espejo de `_evaluar_requisito`
    (`app/core/orquestacion.py`) para UN día puntual. `vence_durante_el_trabajo` no puede
    darse porque `periodo_desde == periodo_hasta` (igual que antes de B-02)."""
    if documento is None:
        veredicto = Veredicto.NO_HABILITADO
    else:
        veredicto = evaluar_documento_en_periodo(documento, dia, dia).veredicto

    # Constancias del cliente: solo cubren requisitos bloqueante_duro (4.5 de
    # especificacion.md) — mismo orden que `_evaluar_requisito`: se chequean primero,
    # sin importar si el veredicto crudo es NO_HABILITADO o REQUIERE_REVISION.
    if constancias_del_par:
        efectivas = [_constancia_efectiva_en(c, dia) for c in constancias_del_par]
        aplicable, _nota = resolver_constancia_aplicable(efectivas, sujeto_id, req_id, cliente_id, commitment_id)
        if aplicable is not None and veredicto != Veredicto.HABILITADO and clasificacion == Clasificacion.BLOQUEANTE_DURO:
            veredicto = Veredicto.HABILITADO

    # Excepciones: nunca vuelven verde (nunca cambian `veredicto`), solo habilitan
    # `asignable` — mismo criterio que `_evaluar_requisito`/`asignable`.
    bajo_excepcion = False
    if excepcion is not None and veredicto in VEREDICTOS_EXCEPCIONABLES:
        vigente_ese_dia = excepcion.vigencia is None or excepcion.vigencia >= dia
        if vigente_ese_dia and excepcion_tiene_efecto(excepcion, clasificacion):
            bajo_excepcion = True

    asignable = veredicto == Veredicto.HABILITADO or bajo_excepcion
    pierde_por_revision = veredicto == Veredicto.REQUIERE_REVISION and not asignable
    return asignable, pierde_por_revision


def puntos_de_quiebre(
    evidencias: dict[tuple[str, str], Documento], desde: date, hasta: date, *,
    constancias: dict[tuple[str, str], list[Constancia]] | None = None,
    excepciones: dict[tuple[str, str], Excepcion] | None = None,
) -> list[date]:
    """Fechas donde el resultado de ALGÚN (candidato, requisito) puede cambiar, dentro de
    `[desde, hasta]` — punto 8: `vigente_hasta + 1` de cada evidencia en juego,
    `vigente_desde` de cada evidencia que arranca a mitad del rango (hallazgo B-01: el
    diseño nunca lo listó explícito, pero `evaluar_documento_en_periodo` sí rechaza
    `periodo_desde < vigente_desde` — sin este punto, un alta a mitad de ventana se
    evaluaba con la fecha de inicio del tramo y quedaba roja aunque después cubriera), y
    `vigencia + 1` de cada excepción/constancia con vigencia acotada en juego (B-02).
    Siempre incluye `desde` y `hasta + 1` (límite, no se evalúa) como extremos del rango."""
    puntos = {desde, hasta + timedelta(days=1)}
    for doc in evidencias.values():
        if doc.vigente_hasta is not None:
            quiebre = doc.vigente_hasta + timedelta(days=1)
            if desde < quiebre <= hasta:
                puntos.add(quiebre)
        if desde < doc.vigente_desde <= hasta:
            puntos.add(doc.vigente_desde)
    for lista in (constancias or {}).values():
        for c in lista:
            if c.vigencia is not None:
                quiebre = c.vigencia + timedelta(days=1)
                if desde < quiebre <= hasta:
                    puntos.add(quiebre)
    for e in (excepciones or {}).values():
        if e.vigencia is not None:
            quiebre = e.vigencia + timedelta(days=1)
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
    *,
    clasificaciones: dict[str, str] | None = None,
    constancias: dict[tuple[str, str], list[Constancia]] | None = None,
    excepciones: dict[tuple[str, str], Excepcion] | None = None,
    cliente_id: str = "",
    commitment_id: str = "",
) -> list[Intervalo]:
    """Un `Intervalo` por tramo constante entre dos puntos de quiebre consecutivos.
    `requisitos_por_tipo`: {tipo_sujeto: [requisito_definicion_id, …]} — los tipos
    exigidos por la matriz/requisito particular (punto 1: fijos para toda la OC, nunca
    cambian día a día). `evidencias`: {(sujeto_id, requisito_definicion_id): Documento}.
    `clasificaciones`/`constancias`/`excepciones` son opcionales (B-02): sin ellos, el
    resultado es idéntico al motor sólo-evidencia anterior."""
    clasificaciones = clasificaciones or {}
    constancias = constancias or {}
    excepciones = excepciones or {}
    quiebres = puntos_de_quiebre(evidencias, desde, hasta, constancias=constancias, excepciones=excepciones)
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
                    ok, es_revision = _asignable_en_dia(
                        evidencias.get((c.sujeto_id, req_id)), i_desde,
                        clasificacion=clasificaciones.get(req_id),
                        constancias_del_par=constancias.get((c.sujeto_id, req_id), []),
                        excepcion=excepciones.get((c.sujeto_id, req_id)),
                        sujeto_id=c.sujeto_id, req_id=req_id,
                        cliente_id=cliente_id, commitment_id=commitment_id,
                    )
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
