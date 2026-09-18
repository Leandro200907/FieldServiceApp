"""Motor de evaluación de habilitación — función pura, sin I/O.

Implementa los mecanismos ya cerrados como casos de oro en modulo1-especificacion.md,
sección 6. Cada función de acá corresponde 1:1 a un caso de oro y está pensada para
poder probarse de forma aislada (ver tests/test_casos_de_oro.py) antes de componerse
en la orquestación completa (que evalúa empresa + todos los recursos propuestos —
1.8 y 1.9 de modulo1-documentacion-habilitante.md, 4.1 de especificacion.md — y que
todavía no está implementada acá; ver README, tabla de estado de avance).

Regla de fondo que gobierna todo el archivo (0.3 y 4.1 de especificacion.md): ninguna
fecha se compara nunca contra "hoy" del sistema operativo ni contra una zona horaria
implícita. Toda comparación temporal recibe explícitamente la fecha o el instante y,
cuando corresponde, la zona horaria a usar.
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.tipos import (
    Clasificacion,
    Constancia,
    Documento,
    EstadoConfirmacion,
    EstadoConstancia,
    EstadoExcepcion,
    EstadoVersionDocumento,
    Excepcion,
    Veredicto,
    VeredictoRequisito,
)


def evaluar_documento_en_periodo(
    documento: Documento,
    periodo_desde: date,
    periodo_hasta: date | None = None,
) -> VeredictoRequisito:
    """Caso de oro 6.1 (borde inclusive de `vigente_hasta`) + la tabla de estados de
    1.9 de modulo1-documentacion-habilitante.md.

    `vigente_hasta` es inclusive: un período que termina exactamente ese día todavía
    cuenta como cubierto.
    """
    periodo_hasta = periodo_hasta or periodo_desde
    req_id = documento.requisito_definicion_id

    if documento.estado_version != EstadoVersionDocumento.VIGENTE:
        return VeredictoRequisito(
            requisito_definicion_id=req_id,
            veredicto=Veredicto.NO_HABILITADO,
            motivo=f"sin documento vigente para {req_id} (estado_version={documento.estado_version.value})",
        )

    if documento.estado_confirmacion == EstadoConfirmacion.DECLARADO:
        return VeredictoRequisito(
            requisito_definicion_id=req_id,
            veredicto=Veredicto.REQUIERE_REVISION,
            motivo=f"{req_id}: dato solo declarado, sin confirmar — no alcanza para probar habilitación (1.10)",
        )

    if periodo_desde < documento.vigente_desde:
        return VeredictoRequisito(
            requisito_definicion_id=req_id,
            veredicto=Veredicto.NO_HABILITADO,
            motivo=f"{req_id}: todavía no vigente al inicio del período (vigente_desde={documento.vigente_desde})",
        )

    if periodo_desde > documento.vigente_hasta:
        return VeredictoRequisito(
            requisito_definicion_id=req_id,
            veredicto=Veredicto.NO_HABILITADO,
            motivo=f"{req_id}: vencido al ingreso (vigente_hasta={documento.vigente_hasta})",
        )

    if periodo_hasta > documento.vigente_hasta:
        return VeredictoRequisito(
            requisito_definicion_id=req_id,
            veredicto=Veredicto.VENCE_DURANTE_EL_TRABAJO,
            motivo=f"{req_id}: vigente al ingreso, vence el {documento.vigente_hasta} antes de terminar el período",
        )

    return VeredictoRequisito(requisito_definicion_id=req_id, veredicto=Veredicto.HABILITADO)


def esta_vigente_en_fecha_civil(vigente_hasta: date, ahora_utc: datetime, zona_horaria: str) -> bool:
    """Caso de oro 6.4 (borde de día con `tenant.zona_horaria`).

    `ahora_utc` debe ser timezone-aware en UTC. La comparación se hace contra la fecha
    civil resultante de convertir ese instante a `zona_horaria` — nunca contra la fecha
    UTC del servidor, que puede diferir en varias horas del día calendario real del tenant.
    """
    if ahora_utc.tzinfo is None:
        raise ValueError("ahora_utc debe ser timezone-aware (UTC)")
    hoy_local = ahora_utc.astimezone(ZoneInfo(zona_horaria)).date()
    return hoy_local <= vigente_hasta


def resolver_constancia_aplicable(
    constancias: list[Constancia],
    sujeto_id: str,
    requisito_definicion_id: str,
    cliente_id: str,
    commitment_id: str,
) -> tuple[Constancia | None, str | None]:
    """Caso de oro 6.2 (constancia general vigente anulada por una específica terminal).

    Devuelve la Constancia que efectivamente aplica a este `commitment_id` (o None si
    ninguna aplica) y, si corresponde, una nota de anulación para que la explicación de
    la evaluación no se limite a "requisito no cubierto" sin decir por qué.

    Regla (4.1 de especificacion.md): si existe una Constancia ESPECÍFICA de este
    commitment_id en estado terminal (revocada/vencida/reemplazada), esa específica
    anula — solo para este commitment_id — cualquier Constancia general vigente del
    mismo sujeto+requisito+cliente. Fuera de este commitment_id puntual, la general
    sigue vigente sin verse afectada (sin efecto cascada).
    """
    candidatas = [
        c
        for c in constancias
        if c.sujeto_id == sujeto_id
        and c.requisito_definicion_id == requisito_definicion_id
        and c.cliente_id == cliente_id
    ]

    especifica_de_esta_ot = next((c for c in candidatas if c.commitment_id == commitment_id), None)
    general = next((c for c in candidatas if c.commitment_id is None and c.estado == EstadoConstancia.VIGENTE), None)

    ESTADOS_TERMINALES = {EstadoConstancia.REVOCADA, EstadoConstancia.VENCIDA, EstadoConstancia.REEMPLAZADA}

    if especifica_de_esta_ot is not None:
        if especifica_de_esta_ot.estado == EstadoConstancia.VIGENTE:
            return especifica_de_esta_ot, None
        if especifica_de_esta_ot.estado in ESTADOS_TERMINALES and general is not None:
            nota = (
                f"existe Constancia general vigente ({general.constancia_id}), pero fue anulada para este "
                f"compromiso por la Constancia específica {especifica_de_esta_ot.constancia_id}, "
                f"en estado {especifica_de_esta_ot.estado.value}"
            )
            return None, nota
        # específica terminal y sin general de respaldo: sencillamente no hay constancia aplicable
        return None, None

    if general is not None:
        return general, None

    return None, None


def validar_nueva_version_matriz(
    vigente_desde_actual: date, vigente_desde_nueva: date
) -> tuple[bool, date | None]:
    """Caso de oro 6.3 (rechazo de versión de Matriz insertada en el pasado) — 3.2 de
    especificacion.md.

    Devuelve (aceptada, nuevo_vigente_hasta_de_la_version_actual). Si se acepta, la
    versión actual se cierra automáticamente el día previo al `vigente_desde` de la
    nueva — en la misma operación atómica que la crea (responsabilidad de quien llama
    a esta función junto con la escritura real, no de esta función pura).
    """
    if vigente_desde_nueva <= vigente_desde_actual:
        return False, None
    from datetime import timedelta

    nuevo_vigente_hasta = vigente_desde_nueva - timedelta(days=1)
    return True, nuevo_vigente_hasta


def excepcion_tiene_efecto(excepcion: Excepcion, clasificacion_vigente_del_requisito: Clasificacion) -> bool:
    """Caso de oro 6.5 (excepción que deja de aplicar por reclasificación de Matriz).

    La Excepción no cambia de estado cuando la Matriz reclasifica su requisito a
    `bloqueante_duro` — sigue `otorgada`, como registro fiel de bajo qué clasificación
    se concedió — pero deja de producir `puede_asignarse_bajo_excepcion` en las
    evaluaciones siguientes. Por eso esta función no muta la Excepción: solo informa
    si, HOY, con la clasificación vigente, todavía tiene efecto.
    """
    if excepcion.estado != EstadoExcepcion.OTORGADA:
        return False
    return clasificacion_vigente_del_requisito == Clasificacion.EXCEPCIONABLE
