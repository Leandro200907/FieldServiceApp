"""Paginación offset/limit (9.6) para GET /consultas/*."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Query


@dataclass(frozen=True)
class Pagina:
    offset: int
    limit: int


def pagina(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)) -> Pagina:
    return Pagina(offset=offset, limit=limit)


def envolver(items: list[Any], total: int, p: Pagina) -> dict[str, Any]:
    return {"items": items, "total": total, "offset": p.offset, "limit": p.limit}
