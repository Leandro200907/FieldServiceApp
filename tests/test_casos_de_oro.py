"""Los 5 casos de oro de modulo1-especificacion.md, sección 6 — con los mismos IDs y
fechas que documenta la especificación, para que quede trazable uno a uno.

El motor no se considera correcto si no pasa estos cinco. Cualquier cambio futuro al
motor debe seguir pasándolos sin modificarlos (son la especificación ejecutable, no un
test más).
"""
from datetime import date, datetime, timezone

from app.core.evaluacion import (
    esta_vigente_en_fecha_civil,
    evaluar_documento_en_periodo,
    excepcion_tiene_efecto,
    resolver_constancia_aplicable,
    validar_nueva_version_matriz,
)
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
)


def test_6_1_borde_inclusive_de_vigente_hasta():
    documento = Documento(
        documento_id="doc_apto_medico_0042",
        sujeto_id="persona_0042",
        requisito_definicion_id="req_apto_medico",
        vigente_desde=date(2026, 3, 1),
        vigente_hasta=date(2026, 9, 15),
        estado_confirmacion=EstadoConfirmacion.VERIFICADO,
        estado_version=EstadoVersionDocumento.VIGENTE,
    )

    resultado_dia_limite = evaluar_documento_en_periodo(documento, periodo_desde=date(2026, 9, 15))
    assert resultado_dia_limite.veredicto == Veredicto.HABILITADO

    resultado_dia_siguiente = evaluar_documento_en_periodo(documento, periodo_desde=date(2026, 9, 16))
    assert resultado_dia_siguiente.veredicto == Veredicto.NO_HABILITADO


def test_6_2_constancia_general_anulada_por_especifica_terminal():
    const_001_general = Constancia(
        constancia_id="const_001",
        sujeto_id="persona_0042",
        requisito_definicion_id="req_induccion_yacimiento",
        cliente_id="cliente_ypf",
        estado=EstadoConstancia.VIGENTE,
        commitment_id=None,
        vigencia=date(2026, 12, 31),
    )
    const_002_especifica_revocada = Constancia(
        constancia_id="const_002",
        sujeto_id="persona_0042",
        requisito_definicion_id="req_induccion_yacimiento",
        cliente_id="cliente_ypf",
        estado=EstadoConstancia.REVOCADA,
        commitment_id="compromiso_OC-2026-1188",
    )
    constancias = [const_001_general, const_002_especifica_revocada]

    aplicable, nota = resolver_constancia_aplicable(
        constancias,
        sujeto_id="persona_0042",
        requisito_definicion_id="req_induccion_yacimiento",
        cliente_id="cliente_ypf",
        commitment_id="compromiso_OC-2026-1188",
    )
    assert aplicable is None
    assert nota is not None
    assert "const_001" in nota and "const_002" in nota and "revocada" in nota

    # Cualquier otro commitment_id del mismo sujeto+cliente: la general sigue cubriendo,
    # sin efecto cascada de la anulación.
    aplicable_otra_ot, nota_otra_ot = resolver_constancia_aplicable(
        constancias,
        sujeto_id="persona_0042",
        requisito_definicion_id="req_induccion_yacimiento",
        cliente_id="cliente_ypf",
        commitment_id="compromiso_OC-2026-1250",
    )
    assert aplicable_otra_ot is not None and aplicable_otra_ot.constancia_id == "const_001"
    assert nota_otra_ot is None


def test_6_3_rechazo_de_version_de_matriz_insertada_en_el_pasado():
    vigente_desde_v3 = date(2026, 6, 1)

    aceptada_en_el_pasado, _ = validar_nueva_version_matriz(
        vigente_desde_actual=vigente_desde_v3, vigente_desde_nueva=date(2026, 5, 15)
    )
    assert aceptada_en_el_pasado is False

    aceptada_hacia_adelante, nuevo_vigente_hasta_v3 = validar_nueva_version_matriz(
        vigente_desde_actual=vigente_desde_v3, vigente_desde_nueva=date(2026, 10, 1)
    )
    assert aceptada_hacia_adelante is True
    assert nuevo_vigente_hasta_v3 == date(2026, 9, 30)


def test_6_4_borde_de_dia_con_tenant_zona_horaria():
    vigente_hasta = date(2026, 9, 15)
    ahora_utc = datetime(2026, 9, 16, 2, 30, 0, tzinfo=timezone.utc)

    assert esta_vigente_en_fecha_civil(vigente_hasta, ahora_utc, "America/Argentina/Buenos_Aires") is True


def test_6_5_excepcion_deja_de_aplicar_por_reclasificacion_de_matriz():
    excepcion = Excepcion(
        excepcion_id="excepcion_5001",
        sujeto_id="persona_0042",
        requisito_definicion_id="req_trabajo_altura",
        commitment_id="compromiso_OC-2026-1188",
        vigencia=date(2026, 9, 30),
        estado=EstadoExcepcion.OTORGADA,
    )

    # matriz_v10: excepcionable — la excepción tiene efecto.
    assert excepcion_tiene_efecto(excepcion, Clasificacion.EXCEPCIONABLE) is True

    # matriz_v11: reclasificado a bloqueante_duro — deja de tener efecto, pero la
    # excepción en sí NO cambia de estado (eso lo verifica quien orquesta, no esta
    # función: la función es pura y no muta nada).
    assert excepcion_tiene_efecto(excepcion, Clasificacion.BLOQUEANTE_DURO) is False
    assert excepcion.estado == EstadoExcepcion.OTORGADA
    assert excepcion.vigencia == date(2026, 9, 30)
