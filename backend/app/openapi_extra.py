"""Enriquecimiento del esquema OpenAPI (9.6): envelope de error común, esquema de
seguridad Bearer y respuestas comunes por operación.

Vive en un solo lugar y lo usan TANTO `app/main.py` (el `/openapi.json` que la API
realmente sirve) COMO `scripts/generar_openapi.py` (el archivo canónico versionado) —
así los dos son, por construcción, el mismo esquema, y no dos copias que se puedan
desincronizar (auditoría externa, hallazgo 3: antes el enriquecimiento vivía solo en el
script y nunca se aplicaba a la app en vivo).

`SIN_SECURITY`: rutas sin bearer obligatorio — el permiso de `/v1/storage/{firma}` es la
firma de la URL, no el token, así que el bearer ahí es opcional (para el chequeo extra de
que un token, si se manda, sea del mismo tenant que la firma); FastAPI igual les pone
`security` automáticamente por depender de un `HTTPBearer(auto_error=False)`, así que acá
se limpia explícito (hallazgo 3). `SIN_401` es un subconjunto MÁS CHICO de `SIN_SECURITY`:
login, refresh y storage no EXIGEN bearer, pero sí pueden devolver 401 genuino si se manda
uno inválido — login/refresh por credenciales/refresh token inválidos, storage porque
`_exigir_tenant_del_token` llama `validar_access_token()` sobre el bearer SI VINO, y eso
puede lanzar `NoAutenticado` (token vencido/malformado) aunque nunca lo exija (auditoría
externa, informe AUDITORIA_DB400E6 hallazgo A-03: "bearer opcional" es "ausente está bien",
no "presente pero inválido está bien" — son cosas distintas y hay que documentar el 401
igual). Separar estas tres de las rutas VERDADERAMENTE públicas (salud, paquete público,
donde no hay ningún bearer que revisar y 401 es sencillamente imposible) es el hallazgo 4."""
from __future__ import annotations

from app.version import MIGRACION_HEAD, VERSION

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
SIN_SECURITY = {"/v1/salud/vivo", "/v1/salud/listo", "/v1/auth/login", "/v1/auth/refresh", "/v1/storage/{firma}",
                "/v1/publico/paquete/{token}", "/v1/publico/paquete/{token}/qr.png"}
# Verdaderamente públicas: ni bearer ni la posibilidad de un 401 por token inválido
# (a diferencia de storage, no leen Authorization en absoluto).
SIN_401 = {"/v1/salud/vivo", "/v1/salud/listo", "/v1/publico/paquete/{token}", "/v1/publico/paquete/{token}/qr.png"}


def enriquecer(doc: dict) -> dict:
    """Muta `doc` (el esquema que FastAPI arma solo, vía `app.openapi()`) in place y lo
    devuelve. Idempotente: aplicarlo dos veces da el mismo resultado."""
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
            op["security"] = [] if path in SIN_SECURITY else [{"bearerAuth": []}]
            respuestas = op.setdefault("responses", {})
            for codigo, desc in RESPUESTAS_COMUNES.items():
                if codigo == "401" and path in SIN_401:
                    continue
                respuestas.setdefault(codigo, {**desc, **error_ref})
            # 422 de FastAPI (HTTPValidationError) → nuestro envelope
            if "422" in respuestas:
                respuestas["422"] = {**RESPUESTAS_COMUNES["422"], **error_ref}
    comp["schemas"].pop("HTTPValidationError", None)
    comp["schemas"].pop("ValidationError", None)
    return doc
