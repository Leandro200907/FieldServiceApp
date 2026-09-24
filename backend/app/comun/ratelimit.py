"""Rate limiter genérico en memoria — extraído de `app/modules/paquete/servicio.py`
(reauditoría Fase 2 punto 3) para que otros endpoints sin protección propia (hallazgo
B-02, auditoría externa 2026-09-22: `POST /v1/auth/login` no tenía ninguna) puedan
reusarlo sin duplicar la clase ni depender de un módulo de negocio ajeno.
"""
from __future__ import annotations

import threading
import time


class RateLimiter:
    """Ventana deslizante simple en memoria: `max_por_minuto` por clave. Con cota de
    memoria: sin esto, muchas claves distintas de un solo uso (por ejemplo, un atacante
    probando credenciales u orígenes al voleo) hacían crecer el diccionario para
    siempre — nada purgaba una clave que ya no se volvía a consultar. Cada llamada cuenta
    para un barrido periódico que saca las claves sin actividad en la ventana.

    Una sola instancia de proceso: con más de un worker/réplica, el límite real hay que
    ponerlo en el proxy o en un almacén compartido (Redis) — esto no alcanza por sí solo."""

    def __init__(self, max_por_minuto: int = 30, max_claves: int = 5000, cada: int = 1000):
        self.max = max_por_minuto
        self.max_claves = max_claves
        self._cada = cada
        self._golpes: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._llamadas = 0

    def permitir(self, clave: str, ahora: float | None = None) -> bool:
        t = ahora if ahora is not None else time.monotonic()
        with self._lock:
            self._llamadas += 1
            if self._llamadas >= self._cada or len(self._golpes) > self.max_claves:
                self._barrer(t)
                self._llamadas = 0
            lista = [x for x in self._golpes.get(clave, []) if t - x < 60]
            if len(lista) >= self.max:
                self._golpes[clave] = lista
                return False
            lista.append(t)
            self._golpes[clave] = lista
            return True

    def _barrer(self, t: float) -> None:
        vacias = [c for c, xs in self._golpes.items() if not any(t - x < 60 for x in xs)]
        for c in vacias:
            del self._golpes[c]
