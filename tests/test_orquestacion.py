"""Casos de oro 6.1, 6.2, 6.4 y 6.5 reproducidos END-TO-END sobre la base real:
legajo + definición + matriz + OC + documento/constancia/excepción insertados por SQL
→ `evaluar_compromiso` → veredicto y resultado esperados, con la fila persistida en
`evaluacion_habilitacion` y el evento registrado.

Los helpers `insertar_*` los reutiliza tests/test_comandos_operacion.py.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.core.orquestacion import clasificacion_vigente, evaluar_compromiso
from app.core.tipos import Clasificacion

# Un instante fijo: 2026-09-18 15:00 UTC → hoy = 2026-09-18 en Buenos Aires.
AHORA = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)
HOY = date(2026, 9, 18)


# --------------------------------------------------------------------------- helpers SQL


def insertar_legajo(s, tenant_id: str, sujeto_id: str, tipo_sujeto: str) -> None:
    s.execute(
        text(
            "INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) "
            "VALUES (:t, :s, :tipo, :nat)"
        ),
        {"t": tenant_id, "s": sujeto_id, "tipo": tipo_sujeto, "nat": f"nat-{sujeto_id}"},
    )


def insertar_definicion(s, tenant_id: str, nombre: str, tipo_sujeto: str, categoria: str = "documento") -> str:
    return str(
        s.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                "VALUES (:t, :n, :c, :ts) RETURNING requisito_definicion_id"
            ),
            {"t": tenant_id, "n": nombre, "c": categoria, "ts": tipo_sujeto},
        ).scalar()
    )


def insertar_matriz(
    s,
    tenant_id: str,
    clave: dict,
    lineas: dict[str, str],
    version: int = 1,
    vigente_desde: date = date(2026, 1, 1),
    vigente_hasta: date | None = None,
) -> str:
    """`lineas` = {requisito_definicion_id: clasificacion}."""
    matriz_id = str(
        s.execute(
            text(
                "INSERT INTO modulo1.matriz_requisitos (tenant_id, cliente_id, locacion_id, tipo_servicio_id, version, "
                " vigente_desde, vigente_hasta) VALUES (:t, :c, :l, :ts, :v, :d, :h) RETURNING matriz_version_id"
            ),
            {"t": tenant_id, "v": version, "d": vigente_desde, "h": vigente_hasta, **clave},
        ).scalar()
    )
    for req_id, clasificacion in lineas.items():
        s.execute(
            text(
                "INSERT INTO modulo1.linea_requisito (matriz_version_id, requisito_definicion_id, tenant_id, "
                " clasificacion, bloqueante_durante_ejecucion) VALUES (:m, :r, :t, :cl, true)"
            ),
            {"m": matriz_id, "r": req_id, "t": tenant_id, "cl": clasificacion},
        )
    return matriz_id


def insertar_oc(s, tenant_id: str, commitment_id: str, clave: dict, desde: date, hasta: date) -> None:
    s.execute(
        text(
            "INSERT INTO modulo1.oc (tenant_id, clave_origen, cliente_id, locacion_id, tipo_servicio_id, "
            " vigencia_desde, vigencia_hasta) VALUES (:t, :co, :c, :l, :ts, :d, :h)"
        ),
        {"t": tenant_id, "co": commitment_id, "d": desde, "h": hasta, **clave},
    )


def insertar_documento(
    s, tenant_id: str, sujeto_id: str, req_id: str, desde: date, hasta: date, confirmacion: str = "verificado"
) -> str:
    return str(
        s.execute(
            text(
                "INSERT INTO modulo1.documento (tenant_id, sujeto_id, requisito_definicion_id, vigente_desde, "
                " vigente_hasta, estado_confirmacion, origen) VALUES (:t, :s, :r, :d, :h, :ec, 'carga_manual') "
                "RETURNING documento_id"
            ),
            {"t": tenant_id, "s": sujeto_id, "r": req_id, "d": desde, "h": hasta, "ec": confirmacion},
        ).scalar()
    )


def insertar_constancia(
    s, tenant_id: str, sujeto_id: str, req_id: str, cliente_id: str, commitment_id: str | None,
    estado: str = "vigente", vigencia: date | None = None,
) -> str:
    return str(
        s.execute(
            text(
                "INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, "
                " commitment_id, registrada_por, evidencia, vigencia, estado) "
                "VALUES (:t, :s, :r, :c, :cm, 'test', 'nota del cliente', :v, :e) RETURNING constancia_id"
            ),
            {"t": tenant_id, "s": sujeto_id, "r": req_id, "c": cliente_id, "cm": commitment_id, "v": vigencia, "e": estado},
        ).scalar()
    )


def insertar_excepcion(
    s, tenant_id: str, referencia_evaluacion: str, sujeto_id: str, req_id: str, commitment_id: str,
    vigencia: date | None = None,
) -> str:
    return str(
        s.execute(
            text(
                "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, "
                " commitment_id, otorgada_por, motivo, vigencia) "
                "VALUES (:t, :e, :s, :r, :c, 'test', 'motivo de prueba', :v) RETURNING excepcion_id"
            ),
            {"t": tenant_id, "e": referencia_evaluacion, "s": sujeto_id, "r": req_id, "c": commitment_id, "v": vigencia},
        ).scalar()
    )


def clave_de_matriz() -> dict:
    return {"c": str(uuid.uuid4()), "l": str(uuid.uuid4()), "ts": str(uuid.uuid4())}


def requisitos_de(resultado: dict, sujeto_id: str) -> dict[str, dict]:
    sujeto = next(p for p in resultado["por_sujeto"] if p["sujeto_id"] == sujeto_id)
    return {r["requisito_definicion_id"]: r for r in sujeto["requisitos"]}


def contar_eventos(s, tipo: str) -> int:
    return s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = :tipo"), {"tipo": tipo}).scalar()


# --------------------------------------------------------------------------- escenario base


def armar_escenario(s, tenant_id: str, clasificacion_persona: str = "bloqueante_duro") -> dict:
    """Empresa habilitada + una persona con un requisito `req_apto_medico`. Sin documento
    para la persona; cada test agrega lo que necesita."""
    clave = clave_de_matriz()
    insertar_legajo(s, tenant_id, "empresa_0001", "empresa")
    insertar_legajo(s, tenant_id, "persona_0042", "persona")
    req_empresa = insertar_definicion(s, tenant_id, "ART vigente", "empresa")
    req_apto = insertar_definicion(s, tenant_id, "Apto médico", "persona")
    matriz_id = insertar_matriz(s, tenant_id, clave, {req_empresa: "bloqueante_duro", req_apto: clasificacion_persona})
    insertar_documento(s, tenant_id, "empresa_0001", req_empresa, date(2026, 1, 1), date(2026, 12, 31))
    return {"clave": clave, "cliente_id": clave["c"], "req_empresa": req_empresa, "req_apto": req_apto, "matriz_id": matriz_id}


@pytest.fixture
def sesion(tenant_de_prueba):
    from app.db import tenant_session

    with tenant_session(tenant_de_prueba.tenant_id) as s:
        yield s


# --------------------------------------------------------------------------- casos de oro


def test_6_1_borde_inclusive_de_vigente_hasta_end_to_end(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t)
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 3, 1), date(2026, 9, 15))
    insertar_oc(sesion, t, "OC-dia-limite", esc["clave"], date(2026, 9, 15), date(2026, 9, 15))
    insertar_oc(sesion, t, "OC-dia-siguiente", esc["clave"], date(2026, 9, 16), date(2026, 9, 16))

    limite = evaluar_compromiso(sesion, t, "OC-dia-limite", AHORA, "usuario-test")
    assert limite["veredicto_de_cumplimiento"] == "habilitado"
    assert limite["resultado_de_decision"] == "puede_asignarse"
    assert limite["referencia_evaluacion"]

    siguiente = evaluar_compromiso(sesion, t, "OC-dia-siguiente", AHORA, "usuario-test")
    assert siguiente["veredicto_de_cumplimiento"] == "no_habilitado"
    assert siguiente["resultado_de_decision"] == "no_puede_asignarse"
    req = requisitos_de(siguiente, "persona_0042")[esc["req_apto"]]
    assert req["veredicto"] == "no_habilitado" and "vencido al ingreso" in req["motivo"]
    assert any(f["requisito_definicion_id"] == esc["req_apto"] for f in siguiente["requisitos_faltantes"])

    # Persistencia + evento, en la misma transacción.
    filas = sesion.execute(text("SELECT count(*) FROM modulo1.evaluacion_habilitacion")).scalar()
    assert filas == 2
    assert contar_eventos(sesion, "EvaluacionDeHabilitacionRealizada") == 2
    snapshot = sesion.execute(
        text("SELECT snapshot FROM modulo1.evaluacion_habilitacion WHERE referencia_evaluacion = :r"),
        {"r": limite["referencia_evaluacion"]},
    ).scalar()
    assert snapshot["hoy"] == "2026-09-18" and snapshot["zona_horaria"] == "America/Argentina/Buenos_Aires"
    assert limite["version_matriz"] == {"matriz_version_id": esc["matriz_id"], "version": 1}


def test_6_2_constancia_general_anulada_por_especifica_terminal(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t)  # req_apto bloqueante_duro, sin documento
    insertar_oc(sesion, t, "OC-2026-1188", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    insertar_oc(sesion, t, "OC-2026-1250", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    general = insertar_constancia(sesion, t, "persona_0042", esc["req_apto"], esc["cliente_id"], None, vigencia=date(2026, 12, 31))
    especifica = insertar_constancia(sesion, t, "persona_0042", esc["req_apto"], esc["cliente_id"], "OC-2026-1188", estado="revocada")

    anulada = evaluar_compromiso(sesion, t, "OC-2026-1188", AHORA, None)
    assert anulada["veredicto_de_cumplimiento"] == "no_habilitado"
    req = requisitos_de(anulada, "persona_0042")[esc["req_apto"]]
    assert req["constancia_id"] is None
    assert general in req["anulacion_detectada"] and especifica in req["anulacion_detectada"] and "revocada" in req["anulacion_detectada"]

    # Otro compromiso del mismo cliente: la general sigue cubriendo, sin cascada.
    cubierta = evaluar_compromiso(sesion, t, "OC-2026-1250", AHORA, None)
    assert cubierta["veredicto_de_cumplimiento"] == "habilitado"
    assert cubierta["resultado_de_decision"] == "puede_asignarse"
    req = requisitos_de(cubierta, "persona_0042")[esc["req_apto"]]
    assert req["constancia_id"] == general and req["motivo"] == f"cubierto por constancia {general}"


def test_constancia_no_cubre_requisito_excepcionable(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, clasificacion_persona="excepcionable")
    insertar_oc(sesion, t, "OC-exc", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    insertar_constancia(sesion, t, "persona_0042", esc["req_apto"], esc["cliente_id"], None)
    r = evaluar_compromiso(sesion, t, "OC-exc", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "no_habilitado"
    assert requisitos_de(r, "persona_0042")[esc["req_apto"]]["constancia_id"] is None


def test_6_4_borde_de_dia_con_zona_horaria_del_tenant(tenant_de_prueba, sesion):
    """02:30Z del 16/9 todavía es 15/9 en Buenos Aires: la matriz que cierra el 15/9
    sigue vigente y el documento que vence el 15/9 sigue habilitado."""
    t = tenant_de_prueba.tenant_id
    sesion.execute(
        text("UPDATE modulo1.tenant SET zona_horaria = 'America/Argentina/Buenos_Aires' WHERE tenant_id = :t"), {"t": t}
    )
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req = insertar_definicion(sesion, t, "Apto médico", "persona")
    insertar_matriz(sesion, t, clave, {req: "bloqueante_duro"}, vigente_desde=date(2026, 1, 1), vigente_hasta=date(2026, 9, 15))
    insertar_documento(sesion, t, "persona_0042", req, date(2026, 3, 1), date(2026, 9, 15))
    insertar_oc(sesion, t, "OC-borde", clave, date(2026, 9, 15), date(2026, 9, 15))

    ahora = datetime(2026, 9, 16, 2, 30, 0, tzinfo=timezone.utc)
    r = evaluar_compromiso(sesion, t, "OC-borde", ahora, None)
    assert r["snapshot"]["hoy"] == "2026-09-15"
    assert r["veredicto_de_cumplimiento"] == "habilitado"
    assert r["resultado_de_decision"] == "puede_asignarse"

    # Con la fecha UTC (16/9) la matriz ya no estaría vigente: eso es lo que NO tiene que pasar.
    with pytest.raises(ErrorDeDominio):
        evaluar_compromiso(sesion, t, "OC-borde", datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc), None)


def test_6_5_excepcion_deja_de_aplicar_por_reclasificacion_y_ck_nunca_verde(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, clasificacion_persona="excepcionable")
    insertar_oc(sesion, t, "OC-2026-1188", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))

    base = evaluar_compromiso(sesion, t, "OC-2026-1188", AHORA, None)
    assert base["resultado_de_decision"] == "no_puede_asignarse"
    assert clasificacion_vigente(sesion, t, "OC-2026-1188", esc["req_apto"]) == Clasificacion.EXCEPCIONABLE

    excepcion_id = insertar_excepcion(
        sesion, t, base["referencia_evaluacion"], "persona_0042", esc["req_apto"], "OC-2026-1188", vigencia=date(2026, 9, 30)
    )

    # matriz v1 excepcionable: la excepción tiene efecto, pero NUNCA vuelve verde (ck_excepcion_nunca_verde).
    bajo = evaluar_compromiso(sesion, t, "OC-2026-1188", AHORA, None)
    assert bajo["veredicto_de_cumplimiento"] == "no_habilitado"
    assert bajo["resultado_de_decision"] == "puede_asignarse_bajo_excepcion"
    req = requisitos_de(bajo, "persona_0042")[esc["req_apto"]]
    assert req["bajo_excepcion"] is True and req["excepcion_id"] == excepcion_id
    assert req["excepcion_aplicable_pero_sin_efecto"] is False
    fila = sesion.execute(
        text("SELECT veredicto_de_cumplimiento, resultado_de_decision FROM modulo1.evaluacion_habilitacion WHERE referencia_evaluacion = :r"),
        {"r": bajo["referencia_evaluacion"]},
    ).first()
    assert tuple(fila) == ("no_habilitado", "puede_asignarse_bajo_excepcion")

    # matriz v2 (hoy en adelante) reclasifica a bloqueante_duro: v1 se cierra el día previo.
    sesion.execute(
        text("UPDATE modulo1.matriz_requisitos SET vigente_hasta = :h WHERE matriz_version_id = :m"),
        {"h": date(2026, 9, 17), "m": esc["matriz_id"]},
    )
    insertar_matriz(
        sesion, t, esc["clave"], {esc["req_empresa"]: "bloqueante_duro", esc["req_apto"]: "bloqueante_duro"},
        version=2, vigente_desde=HOY,
    )
    assert clasificacion_vigente(sesion, t, "OC-2026-1188", esc["req_apto"]) == Clasificacion.BLOQUEANTE_DURO

    sin_efecto = evaluar_compromiso(sesion, t, "OC-2026-1188", AHORA, None)
    assert sin_efecto["veredicto_de_cumplimiento"] == "no_habilitado"
    assert sin_efecto["resultado_de_decision"] == "no_puede_asignarse"
    req = requisitos_de(sin_efecto, "persona_0042")[esc["req_apto"]]
    assert req["bajo_excepcion"] is False and req["excepcion_aplicable_pero_sin_efecto"] is True
    assert sin_efecto["version_matriz"]["version"] == 2

    # La excepción en sí no cambió de estado.
    estado = sesion.execute(text("SELECT estado FROM modulo1.excepcion WHERE excepcion_id = :e"), {"e": excepcion_id}).scalar()
    assert estado == "otorgada"


# --------------------------------------------------------------------------- otros bordes


def test_requisito_particular_manda_sobre_la_matriz(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t, clasificacion_persona="bloqueante_duro")
    insertar_oc(sesion, t, "OC-part", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    sesion.execute(
        text(
            "INSERT INTO modulo1.requisito_particular (tenant_id, commitment_id, requisito_definicion_id, clasificacion, "
            " bloqueante_durante_ejecucion) VALUES (:t, 'OC-part', :r, 'excepcionable', false)"
        ),
        {"t": t, "r": esc["req_apto"]},
    )
    assert clasificacion_vigente(sesion, t, "OC-part", esc["req_apto"]) == Clasificacion.EXCEPCIONABLE
    r = evaluar_compromiso(sesion, t, "OC-part", AHORA, None)
    req = requisitos_de(r, "persona_0042")[esc["req_apto"]]
    assert req["clasificacion"] == "excepcionable" and req["origen_clasificacion"] == "particular"


def test_empresa_no_habilitada_bloquea_aunque_el_recurso_este_bien(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t)
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 12, 31))
    sesion.execute(text("UPDATE modulo1.documento SET estado_version = 'sucedida' WHERE sujeto_id = 'empresa_0001'"))
    insertar_oc(sesion, t, "OC-emp", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-emp", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "no_habilitado"
    assert r["resultado_de_decision"] == "no_puede_asignarse"
    assert requisitos_de(r, "empresa_0001")[esc["req_empresa"]]["motivo"] == "sin documento"
    assert requisitos_de(r, "persona_0042")[esc["req_apto"]]["veredicto"] == "habilitado"


def test_basta_con_un_recurso_habilitado_por_tipo(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t)
    insertar_legajo(sesion, t, "persona_0099", "persona")  # sin documento
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 12, 31))
    insertar_oc(sesion, t, "OC-dos", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-dos", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "habilitado"
    assert r["snapshot"]["cobertura_por_tipo"]["persona"] == "persona_0042"
    assert {p["sujeto_id"]: p["veredicto"] for p in r["por_sujeto"] if p["tipo_sujeto"] == "persona"} == {
        "persona_0042": "habilitado", "persona_0099": "no_habilitado",
    }


def test_declarado_es_requiere_revision_y_no_puede_asignarse(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    esc = armar_escenario(sesion, t)
    insertar_documento(sesion, t, "persona_0042", esc["req_apto"], date(2026, 1, 1), date(2026, 12, 31), confirmacion="declarado")
    insertar_oc(sesion, t, "OC-decl", esc["clave"], date(2026, 10, 1), date(2026, 10, 5))
    r = evaluar_compromiso(sesion, t, "OC-decl", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "requiere_revision"
    assert r["resultado_de_decision"] == "no_puede_asignarse"


def test_competencia_se_lee_de_acreditacion(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    clave = clave_de_matriz()
    insertar_legajo(sesion, t, "persona_0042", "persona")
    req = insertar_definicion(sesion, t, "Trabajo en altura", "persona", categoria="competencia")
    insertar_matriz(sesion, t, clave, {req: "bloqueante_duro"})
    insertar_oc(sesion, t, "OC-comp", clave, date(2026, 10, 1), date(2026, 10, 5))
    evidencia = insertar_documento(sesion, t, "persona_0042", req, date(2026, 1, 1), date(2026, 1, 31))  # no cuenta: es acreditación
    sesion.execute(text("UPDATE modulo1.documento SET requisito_definicion_id = NULL WHERE documento_id = :d"), {"d": evidencia})
    for desde, hasta in ((date(2025, 1, 1), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 12, 31))):
        sesion.execute(
            text(
                "INSERT INTO modulo1.acreditacion_competencia (tenant_id, persona_id, requisito_definicion_id, vigente_desde, "
                " vigente_hasta, estado_confirmacion, evidencias) VALUES (:t, 'persona_0042', :r, :d, :h, 'verificado', :ev)"
            ),
            {"t": t, "r": req, "d": desde, "h": hasta, "ev": [uuid.UUID(evidencia)]},
        )
    r = evaluar_compromiso(sesion, t, "OC-comp", AHORA, None)
    assert r["veredicto_de_cumplimiento"] == "habilitado"


def test_sin_oc_y_sin_matriz(tenant_de_prueba, sesion):
    t = tenant_de_prueba.tenant_id
    with pytest.raises(NoEncontrado):
        evaluar_compromiso(sesion, t, "no-existe", AHORA, None)
    insertar_oc(sesion, t, "OC-sin-matriz", clave_de_matriz(), date(2026, 10, 1), date(2026, 10, 5))
    with pytest.raises(ErrorDeDominio, match="sin matriz vigente"):
        evaluar_compromiso(sesion, t, "OC-sin-matriz", AHORA, None)
