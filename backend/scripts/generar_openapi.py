"""Genera `docs/openapi.json`: contrato OpenAPI canónico de la API para el frontend.

    .venv/Scripts/python scripts/generar_openapi.py            # escribe docs/openapi.json
    .venv/Scripts/python scripts/generar_openapi.py --check    # sale 1 si difiere del real

Canónico y estable: claves ordenadas, indentación fija, sin `servers` (hosts) ni datos del
entorno. El enriquecimiento (seguridad, envelope de error, respuestas comunes) vive en
`app/openapi_extra.py` y lo aplica la app misma al importarse (`app/main.py`) — este
script solo pide `app.openapi()` (ya enriquecido, idéntico al que sirve `/openapi.json`
en vivo) y lo ordena para el archivo. No necesita base de datos ni variables de entorno
secretas reales (la app se importa con lo que haya en el entorno; sólo se lee la
definición de rutas).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "docs" / "openapi.json"


def _ordenar(obj):
    if isinstance(obj, dict):
        return {k: _ordenar(obj[k]) for k in sorted(obj)}
    if isinstance(obj, list):
        return [_ordenar(x) for x in obj]
    return obj


def generar() -> dict:
    from app.main import app

    return _ordenar(app.openapi())


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
