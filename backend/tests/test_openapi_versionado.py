"""`docs/openapi.json` es el contrato versionado: tiene que coincidir byte a byte con lo
que genera la app (canónico), corresponder al head actual, cubrir todas las operaciones,
declarar autenticación y errores, y no llevar hosts ni rutas internas.

Auditoría externa (hallazgos 3+4): el enriquecimiento (envelope de error, esquema de
seguridad, respuestas comunes) vivía SOLO en `scripts/generar_openapi.py`, nunca se
aplicaba a la app real — el `/openapi.json` que sirve la API en producción no tenía nada
de esto. Además, `/v1/storage/{firma}` (bearer opcional, nunca 401) quedaba con el
`security` que FastAPI arma automáticamente por tener un `Depends(HTTPBearer(...))`
aunque sea `auto_error=False`, y `/v1/auth/login`/`refresh` (sin bearer, pero con 401
genuino por credenciales inválidas) perdían la documentación del 401 por estar en la
misma lista que las rutas realmente públicas."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.openapi_extra import SIN_401, SIN_SECURITY
from app.version import MIGRACION_HEAD, VERSION
from scripts import generar_openapi

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO = RAIZ / "docs" / "openapi.json"


def test_openapi_json_coincide_con_la_app():
    assert ARCHIVO.read_text(encoding="utf-8") == generar_openapi.serializar(generar_openapi.generar()), \
        "docs/openapi.json desactualizado: regenerar con scripts/generar_openapi.py"


def test_openapi_json_es_identico_al_que_sirve_la_app_en_vivo(cliente_api):
    """No solo el mismo conjunto de (path, método): el JSON completo, campo por campo —
    security, responses, schemas — tiene que ser el mismo documento."""
    archivo = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    vivo = cliente_api.get("/openapi.json").json()
    assert vivo == archivo


def test_openapi_json_head_operaciones_seguridad_y_errores(cliente_api):
    doc = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    assert doc["info"]["x-migracion-head"] == MIGRACION_HEAD and doc["info"]["version"] == VERSION
    real = cliente_api.get("/openapi.json").json()["paths"]
    assert {(p, m) for p, ops in doc["paths"].items() for m in ops} == {(p, m) for p, ops in real.items() for m in ops}
    assert doc["components"]["securitySchemes"]["bearerAuth"] == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    assert "ErrorEnvelope" in doc["components"]["schemas"] and "HTTPValidationError" not in doc["components"]["schemas"]
    for path, ops in doc["paths"].items():
        for op in ops.values():
            sin_seguridad = path in SIN_SECURITY
            # Nunca el nombre que FastAPI arma solo ("HTTPBearer"): o bien limpio ([])
            # para las rutas sin bearer obligatorio, o bien el esquema declarado (bearerAuth).
            assert op.get("security") == ([] if sin_seguridad else [{"bearerAuth": []}]), path
            for codigo in ("403", "404", "409", "422", "500"):
                assert op["responses"][codigo]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}, (path, codigo)
            assert ("401" in op["responses"]) is not (path in SIN_401), path


def test_login_y_refresh_documentan_401_pero_no_exigen_bearer():
    doc = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    for path in ("/v1/auth/login", "/v1/auth/refresh"):
        op = doc["paths"][path]["post"]
        assert op["security"] == []
        assert op["responses"]["401"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_storage_firmado_no_exige_bearer_pero_documenta_401_si_se_manda_uno_invalido():
    """Auditoría externa (AUDITORIA_DB400E6, hallazgo A-03): el bearer es opcional —
    `security == []` — pero SI se manda uno inválido, `_exigir_tenant_del_token` sí puede
    lanzar 401. "Opcional" es "ausente está bien", no "cualquier valor está bien"."""
    doc = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    for metodo in ("put", "get"):
        op = doc["paths"]["/v1/storage/{firma}"][metodo]
        assert op["security"] == []
        assert op["responses"]["401"]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}


def test_openapi_json_sin_hosts_ni_rutas_internas_y_canonico():
    texto = ARCHIVO.read_text(encoding="utf-8")
    assert "servers" not in json.loads(texto)
    assert not re.search(r"localhost|127\.0\.0\.1|postgresql|https?://|[A-Za-z]:\\|/Users/|secret", texto, re.I)
    assert texto == json.dumps(json.loads(texto), ensure_ascii=False, indent=2, sort_keys=True) + "\n"   # canónico
