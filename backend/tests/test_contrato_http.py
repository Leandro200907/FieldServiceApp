"""Bordes HTTP comunes: envelope uniforme y consultas nunca cacheables."""


def test_404_y_405_respetan_el_envelope(cliente_api):
    no_encontrado = cliente_api.get("/v1/ruta-que-no-existe")
    assert no_encontrado.status_code == 404
    assert no_encontrado.json()["error"]["codigo"] == "no_encontrado"
    assert set(no_encontrado.json()["error"]) == {"codigo", "mensaje", "detalles", "request_id"}

    metodo = cliente_api.post("/v1/salud/vivo")
    assert metodo.status_code == 405
    assert metodo.json()["error"]["codigo"] == "metodo_no_permitido"


def test_consultas_no_se_guardan_en_cache(cliente_api, tenant_de_prueba):
    respuesta = cliente_api.get(
        "/v1/consultas/propuestas_pendientes",
        headers=tenant_de_prueba.headers("responsable_legajos"),
    )
    assert respuesta.status_code == 200
    assert respuesta.headers["Cache-Control"] == "no-store"


def test_documentacion_interactiva_no_esta_publica_por_defecto(cliente_api):
    assert cliente_api.get("/docs").status_code == 404
    assert cliente_api.get("/redoc").status_code == 404
