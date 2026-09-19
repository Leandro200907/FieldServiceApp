"""`docs/openapi.json` es el contrato versionado: tiene que coincidir byte a byte con lo
que genera la app (canónico), corresponder al head actual, cubrir las 47 operaciones,
declarar autenticación y errores, y no llevar hosts ni rutas internas."""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.version import MIGRACION_HEAD, VERSION
from scripts import generar_openapi

RAIZ = Path(__file__).resolve().parents[1]
ARCHIVO = RAIZ / "docs" / "openapi.json"


def test_openapi_json_coincide_con_la_app():
    assert ARCHIVO.read_text(encoding="utf-8") == generar_openapi.serializar(generar_openapi.generar()), \
        "docs/openapi.json desactualizado: regenerar con scripts/generar_openapi.py"


def test_openapi_json_head_operaciones_seguridad_y_errores(cliente_api):
    doc = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    assert doc["info"]["x-migracion-head"] == MIGRACION_HEAD and doc["info"]["version"] == VERSION
    real = cliente_api.get("/openapi.json").json()["paths"]
    assert {(p, m) for p, ops in doc["paths"].items() for m in ops} == {(p, m) for p, ops in real.items() for m in ops}
    assert sum(len(ops) for ops in doc["paths"].values()) == 47
    assert doc["components"]["securitySchemes"]["bearerAuth"] == {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    assert "ErrorEnvelope" in doc["components"]["schemas"] and "HTTPValidationError" not in doc["components"]["schemas"]
    for path, ops in doc["paths"].items():
        for op in ops.values():
            publica = path in generar_openapi.PUBLICAS
            assert (op.get("security") == [{"bearerAuth": []}]) is not publica, path
            for codigo in ("403", "404", "409", "422", "500"):
                assert op["responses"][codigo]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/ErrorEnvelope"}, (path, codigo)
            assert ("401" in op["responses"]) is not publica


def test_openapi_json_sin_hosts_ni_rutas_internas_y_canonico():
    texto = ARCHIVO.read_text(encoding="utf-8")
    assert "servers" not in json.loads(texto)
    assert not re.search(r"localhost|127\.0\.0\.1|postgresql|https?://|[A-Za-z]:\\|/Users/|secret", texto, re.I)
    assert texto == json.dumps(json.loads(texto), ensure_ascii=False, indent=2, sort_keys=True) + "\n"   # canónico
