"""Value objects puros del motor de evaluación.

Sin ORM, sin I/O, sin timezone del sistema operativo implícita en ningún lado — todo lo
que el motor necesita entra como parámetro. Es la frontera ya cerrada en
modulo1-arquitectura-tecnica.md (8.1 y transversalmente en todo el paso 8): "el motor de
evaluación es una librería pura sin entrada/salida".

Los nombres de campo y los valores de enum son los cerrados en modulo1-especificacion.md,
sección 2 (Documento), 4.1 (Evaluación de habilitación), 4.4 (Excepción), 4.5 (Constancia
del cliente), 3.2-3.3 (Matriz de requisitos / Línea de requisito) — no se inventó
vocabulario nuevo acá.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class EstadoConfirmacion(str, Enum):
    DECLARADO = "declarado"
    VERIFICADO = "verificado"
    CONFIRMADO_EN_FUENTE = "confirmado_en_fuente"


class EstadoVersionDocumento(str, Enum):
    VIGENTE = "vigente"
    SUCEDIDA = "sucedida"
    REVERTIDA_POR_LOTE = "revertida_por_lote"
    RECHAZADA = "rechazada"


class Clasificacion(str, Enum):
    BLOQUEANTE_DURO = "bloqueante_duro"
    EXCEPCIONABLE = "excepcionable"


class EstadoConstancia(str, Enum):
    VIGENTE = "vigente"
    VENCIDA = "vencida"
    REVOCADA = "revocada"
    REEMPLAZADA = "reemplazada"


class EstadoExcepcion(str, Enum):
    OTORGADA = "otorgada"
    REVOCADA = "revocada"
    REGULARIZADA = "regularizada"
    VENCIDA = "vencida"


class Veredicto(str, Enum):
    """4 valores — nunca 3. `requiere_revision` es transversal: el dato en sí no es
    confiable, así que no se decide en firme (1.9 de modulo1-documentacion-habilitante.md;
    4.1 de especificacion.md)."""

    HABILITADO = "habilitado"
    VENCE_DURANTE_EL_TRABAJO = "vence_durante_el_trabajo"
    NO_HABILITADO = "no_habilitado"
    REQUIERE_REVISION = "requiere_revision"


class ResultadoDecision(str, Enum):
    PUEDE_ASIGNARSE = "puede_asignarse"
    PUEDE_ASIGNARSE_BAJO_EXCEPCION = "puede_asignarse_bajo_excepcion"
    NO_PUEDE_ASIGNARSE = "no_puede_asignarse"


@dataclass(frozen=True)
class Documento:
    """Un requisito de categoría `documento`, para un sujeto — 2.2 de especificacion.md.

    Deliberadamente no lleva `numero`, `archivo_adjunto`, ni metadata de pipeline
    (`origen`, `confianza_extraccion`): el motor no las consulta (1.10 de
    documentacion-habilitante.md — "el motor solo ve el nivel de confianza, nunca cómo
    se llegó a él", y ni siquiera eso entra acá salvo vía `estado_confirmacion`).
    """

    documento_id: str
    sujeto_id: str
    requisito_definicion_id: str
    vigente_desde: date
    vigente_hasta: date
    estado_confirmacion: EstadoConfirmacion
    estado_version: EstadoVersionDocumento


@dataclass(frozen=True)
class LineaRequisito:
    """3.3 de especificacion.md — value object dentro de una versión de Matriz."""

    requisito_definicion_id: str
    clasificacion: Clasificacion
    bloqueante_durante_ejecucion: bool


@dataclass(frozen=True)
class Constancia:
    """4.5 de especificacion.md."""

    constancia_id: str
    sujeto_id: str
    requisito_definicion_id: str
    cliente_id: str
    estado: EstadoConstancia
    commitment_id: str | None = None  # None = general, aplica a todos los compromisos del cliente
    vigencia: date | None = None  # None = "hasta reemplazo"


@dataclass(frozen=True)
class Excepcion:
    """4.4 de especificacion.md."""

    excepcion_id: str
    sujeto_id: str
    requisito_definicion_id: str
    commitment_id: str
    vigencia: date | None  # None = "hasta regularizar"
    estado: EstadoExcepcion


@dataclass(frozen=True)
class VeredictoRequisito:
    """Resultado de evaluar un (sujeto, requisito) puntual — la pieza atómica que
    compone `por_sujeto[]` de Evaluación de habilitación (4.1 de especificacion.md).
    """

    requisito_definicion_id: str
    veredicto: Veredicto
    motivo: str | None = None
    excepcion_aplicable_pero_sin_efecto: bool = False
    anulacion_detectada: str | None = None
