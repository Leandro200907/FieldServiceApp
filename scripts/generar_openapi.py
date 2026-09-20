"""Genera `docs/openapi.json`: contrato OpenAPI canónico de la API para el frontend.

    .venv/Scripts/python scripts/generar_openapi.py            # escribe docs/openapi.json
    .venv/Scripts/python scripts/generar_openapi.py --check    # sale 1 si difiere del real

Canónico y estable: claves ordenadas, indentación fija, sin `servers` (hosts) ni datos del
entorno; `info.version` = VERSION del backend y `info.x-migracion-head` = MIGRACION_HEAD,
así el archivo corresponde exactamente al head y un cambio de contrato produce un diff
útil. Declara el esquema de seguridad Bearer y el envelope de error común. No necesita
base de datos ni variables de entorno secretas reales (la app se importa con lo que haya
en el entorno; sólo se lee la definición de rutas).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "docs" / "openapi.json"

ERROR_SCHEMA = {
    "title": "ErrorEnvelope",
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["codigo", "mensaje", "detalles", "request_id"],
            "properties": {
                "codigo": {"type": "string", "description": "Código estable (ver HANDOFF_FRONTEND.md §7)"},
                "mensaje": {"type": "string", "description": "Texto humano; puede cambiar"},
                "detalles": {"description": "Objeto, lista o null; nunca incluye el input recibido"},
                "request_id": {"type": "string", "description": "También en el header X-Request-ID"},
            },
        }
    },
}
RESPUESTAS_COMUNES = {
    "401": {"description": "No autenticado (sin token, vencido, usuario inexistente o inactivo)"},
    "403": {"description": "Rol insuficiente o fuera de alcance"},
    "404": {"description": "Recurso inexistente o no visible para el rol"},
    "409": {"description": "Conflicto de dominio, idempotencia o concurrencia"},
    "422": {"description": "Validación o regla de dominio"},
    "500": {"description": "Error interno; informar request_id"},
}
PUBLICAS = {"/v1/salud/vivo", "/v1/salud/listo", "/v1/auth/login", "/v1/auth/refresh", "/v1/storage/{firma}",
            "/v1/publico/paquete/{token}", "/v1/publico/paquete/{token}/qr.png"}


def _ordenar(obj):
    if isinstance(obj, dict):
        return {k: _ordenar(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_ordenar(x) for x in obj]
    return obj


def generar() -> dict:
    from app.main import app
    from app.version import MIGRACION_HEAD, VERSION

    doc = app.openapi()
    doc.pop("servers", None)
    doc["info"] = {
        "title": "Módulo 1 — Documentación habilitante",
        "version": VERSION,
        "x-migracion-head": MIGRACION_HEAD,
        "description": "Contrato HTTP del backend. Prefijo /v1. Ver docs/HANDOFF_FRONTEND.md.",
    }
    comp = doc.setdefault("components", {})
    comp.setdefault("securitySchemes", {})["bearerAuth"] = {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    comp.setdefault("schemas", {})["ErrorEnvelope"] = ERROR_SCHEMA
    error_ref = {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/ErrorEnvelope"}}}}
    for path, ops in doc["paths"].items():
        for op in ops.values():
            if path not in PUBLICAS:
                op["security"] = [{"bearerAuth": []}]
            respuestas = op.setdefault("responses", {})
            for codigo, desc in RESPUESTAS_COMUNES.items():
                if codigo == "401" and path in PUBLICAS:
                    continue
                respuestas.setdefault(codigo, {**desc, **error_ref})
            # 422 de FastAPI (HTTPValidationError) → nuestro envelope
            if "422" in respuestas:
                respuestas["422"] = {**RESPUESTAS_COMUNES["422"], **error_ref}
    comp["schemas"].pop("HTTPValidationError", None)
    comp["schemas"].pop("ValidationError", None)
    return _ordenar(doc)


def serializar(doc: dict) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    contenido = serializar(generar())
    if "--check" in argv:
        actual = DESTINO.read_text(encoding="utf-8") if DESTINO.exists() else ""
        if actual != contenido:
            print("docs/openapi.json desactualizado: regenerar con scripts/generar_openapi.py", file=sys.stderr)
            return 1
        print("docs/openapi.json al día")
        return 0
    DESTINO.write_text(contenido, encoding="utf-8")
    doc = json.loads(contenido)
    print(f"{DESTINO.relative_to(RAIZ)}: {sum(len(o) for o in doc['paths'].values())} operaciones, head {doc['info']['x-migracion-head']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
