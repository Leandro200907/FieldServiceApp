"""Comandos de Requisitos contra base real: definiciones, matriz (caso de oro 6.3 vía
HTTP), requisito particular, permisos e idempotencia."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.db import tenant_session

CMD = "/v1/comandos"


def _alta_def(cliente_api, tenant, nombre: str, categoria: str = "documento", tipo: str = "persona", **extra) -> str:
    body = {"nombre": nombre, "categoria": categoria, "tipo_sujeto_aplicable": tipo, **extra}
    r = cliente_api.post(f"{CMD}/dar_de_alta_definicion_de_requisito", json=body, headers=tenant.headers("configuracion"))
    assert r.status_code == 200, r.text
    return r.json()["requisito_definicion_id"]


def test_alta_definicion_respeta_induccion_requiere_locacion(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    h = t.headers("configuracion")
    sin_locacion = cliente_api.post(
        f"{CMD}/dar_de_alta_definicion_de_requisito",
        json={"nombre": "Inducción YPF", "categoria": "induccion", "tipo_sujeto_aplicable": "persona"},
        headers=h,
    )
    assert sin_locacion.status_code == 422 and sin_locacion.json()["error"]["codigo"] == "regla_de_dominio"

    con_locacion_documento = cliente_api.post(
        f"{CMD}/dar_de_alta_definicion_de_requisito",
        json={"nombre": "Apto", "categoria": "documento", "tipo_sujeto_aplicable": "persona", "locacion_id": str(uuid.uuid4())},
        headers=h,
    )
    assert con_locacion_documento.status_code == 422

    loc = str(uuid.uuid4())
    rid = _alta_def(cliente_api, t, "Inducción YPF", "induccion", locacion_id=loc, plazo_retencion_archivo_dias=365)
    with tenant_session(t.tenant_id) as s:
        fila = s.execute(
            text("SELECT categoria, locacion_id, activa, plazo_retencion_archivo FROM modulo1.definicion_requisito WHERE requisito_definicion_id = :r"),
            {"r": rid},
        ).first()
        assert fila[0] == "induccion" and str(fila[1]) == loc and fila[2] is True and fila[3].days == 365
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'DefinicionDeRequisitoDadaDeAlta'")).scalar() == 1

    repetida = cliente_api.post(
        f"{CMD}/dar_de_alta_definicion_de_requisito",
        json={"nombre": "Inducción YPF", "categoria": "induccion", "tipo_sujeto_aplicable": "persona", "locacion_id": loc},
        headers=h,
    )
    assert repetida.status_code == 409


def test_baja_definicion(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    rid = _alta_def(cliente_api, t, "Apto médico")
    r = cliente_api.post(f"{CMD}/dar_de_baja_definicion_de_requisito", json={"requisito_definicion_id": rid}, headers=t.headers("configuracion"))
    assert r.status_code == 200 and r.json()["eventos"] == ["DefinicionDeRequisitoDadaDeBaja"]
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT activa FROM modulo1.definicion_requisito WHERE requisito_definicion_id = :r"), {"r": rid}).scalar() is False
    otra_vez = cliente_api.post(f"{CMD}/dar_de_baja_definicion_de_requisito", json={"requisito_definicion_id": rid}, headers=t.headers("configuracion"))
    assert otra_vez.status_code == 409


def test_permisos_solo_configuracion_publica_matriz(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    rid = _alta_def(cliente_api, t, "Apto médico")
    body = {
        "cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4()),
        "vigente_desde": "2026-06-01",
        "lineas": [{"requisito_definicion_id": rid, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}],
    }
    for rol in ("responsable_legajos", "supervisor", "tecnico"):
        r = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json=body, headers=t.headers(rol))
        assert r.status_code == 403 and r.json()["error"]["codigo"] == "prohibido", rol
    sin_token = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json=body)
    assert sin_token.status_code == 401


def test_6_3_matriz_rechaza_pasado_y_autocierra_version_previa(cliente_api, tenant_de_prueba):
    """Caso de oro 6.3 por HTTP: v3 vigente desde 2026-06-01; una versión con
    vigente_desde 2026-05-15 se rechaza (409); una desde 2026-10-01 se acepta y deja
    a v3 con vigente_hasta = 2026-09-30, en la misma transacción."""
    t = tenant_de_prueba
    h = t.headers("configuracion")
    req_a = _alta_def(cliente_api, t, "Apto médico")
    req_b = _alta_def(cliente_api, t, "Trabajo en altura", "competencia")
    clave = {"cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4())}
    linea_a = {"requisito_definicion_id": req_a, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}
    linea_b = {"requisito_definicion_id": req_b, "clasificacion": "excepcionable", "bloqueante_durante_ejecucion": False}

    v1 = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json={**clave, "vigente_desde": "2026-06-01", "lineas": [linea_a]}, headers=h)
    assert v1.status_code == 200, v1.text
    assert v1.json()["version"] == 1 and v1.json()["version_anterior"] is None
    assert v1.json()["eventos"] == ["MatrizVersionPublicada"]

    en_el_pasado = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json={**clave, "vigente_desde": "2026-05-15", "lineas": [linea_a]}, headers=h)
    assert en_el_pasado.status_code == 409 and en_el_pasado.json()["error"]["codigo"] == "conflicto"
    mismo_dia = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json={**clave, "vigente_desde": "2026-06-01", "lineas": [linea_a]}, headers=h)
    assert mismo_dia.status_code == 409

    v2 = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json={**clave, "vigente_desde": "2026-10-01", "lineas": [linea_a, linea_b]}, headers=h)
    assert v2.status_code == 200, v2.text
    assert v2.json()["version"] == 2
    assert v2.json()["version_anterior"] == {"matriz_version_id": v1.json()["matriz_version_id"], "version": 1, "vigente_hasta": "2026-09-30"}

    with tenant_session(t.tenant_id) as s:
        versiones = s.execute(
            text(
                "SELECT version, vigente_desde::text, vigente_hasta::text FROM modulo1.matriz_requisitos "
                "WHERE cliente_id = :c ORDER BY version"
            ),
            {"c": clave["cliente_id"]},
        ).all()
        assert [tuple(v) for v in versiones] == [(1, "2026-06-01", "2026-09-30"), (2, "2026-10-01", None)]
        lineas = s.execute(
            text("SELECT count(*) FROM modulo1.linea_requisito WHERE matriz_version_id = :m"), {"m": v2.json()["matriz_version_id"]}
        ).scalar()
        assert lineas == 2
        assert s.execute(text("SELECT count(*) FROM modulo1.event_log WHERE tipo = 'MatrizVersionPublicada'")).scalar() == 2

    # Otra clave (otro cliente) arranca en v1 sin interferir.
    otro = cliente_api.post(
        f"{CMD}/publicar_version_de_matriz",
        json={**clave, "cliente_id": str(uuid.uuid4()), "vigente_desde": "2026-01-01", "lineas": [linea_a]}, headers=h,
    )
    assert otro.status_code == 200 and otro.json()["version"] == 1

    # Línea con definición dada de baja: rechazada.
    cliente_api.post(f"{CMD}/dar_de_baja_definicion_de_requisito", json={"requisito_definicion_id": req_b}, headers=h)
    con_baja = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json={**clave, "vigente_desde": "2026-11-01", "lineas": [linea_b]}, headers=h)
    assert con_baja.status_code == 422


def test_matriz_idempotency_key_repite_sin_duplicar(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    rid = _alta_def(cliente_api, t, "Apto médico")
    body = {
        "cliente_id": str(uuid.uuid4()), "locacion_id": str(uuid.uuid4()), "tipo_servicio_id": str(uuid.uuid4()),
        "vigente_desde": "2026-06-01",
        "lineas": [{"requisito_definicion_id": rid, "clasificacion": "bloqueante_duro", "bloqueante_durante_ejecucion": True}],
    }
    h = t.headers("configuracion", idempotency_key="pub-matriz-1")
    r1 = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json=body, headers=h)
    r2 = cliente_api.post(f"{CMD}/publicar_version_de_matriz", json=body, headers=h)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json() == r2.json()
    with tenant_session(t.tenant_id) as s:
        assert s.execute(text("SELECT count(*) FROM modulo1.matriz_requisitos")).scalar() == 1


def test_requisito_particular(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    rid = _alta_def(cliente_api, t, "Apto médico")
    body = {"commitment_id": "compromiso_OC-2026-1188", "requisito_definicion_id": rid, "clasificacion": "excepcionable", "bloqueante_durante_ejecucion": False}

    prohibido = cliente_api.post(f"{CMD}/cargar_requisito_particular", json=body, headers=t.headers("configuracion"))
    assert prohibido.status_code == 403

    r = cliente_api.post(f"{CMD}/cargar_requisito_particular", json=body, headers=t.headers("responsable_legajos"))
    assert r.status_code == 200, r.text
    assert r.json()["eventos"] == ["RequisitoParticularCargado"]
    with tenant_session(t.tenant_id) as s:
        fila = s.execute(
            text("SELECT clasificacion, bloqueante_durante_ejecucion FROM modulo1.requisito_particular WHERE requisito_particular_id = :p"),
            {"p": r.json()["requisito_particular_id"]},
        ).first()
        assert tuple(fila) == ("excepcionable", False)

    repetido = cliente_api.post(f"{CMD}/cargar_requisito_particular", json=body, headers=t.headers("responsable_legajos"))
    assert repetido.status_code == 409

    inexistente = cliente_api.post(
        f"{CMD}/cargar_requisito_particular", json={**body, "requisito_definicion_id": str(uuid.uuid4())}, headers=t.headers("responsable_legajos")
    )
    assert inexistente.status_code == 404
