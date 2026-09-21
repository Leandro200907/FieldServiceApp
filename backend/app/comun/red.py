"""Origen real de un request detrás de un proxy — reauditoría Fase 2 punto 3.

`request.client.host` es la conexión TCP inmediata: sin proxy, es el cliente real; detrás
de un reverse-proxy o load balancer (el caso normal en cualquier despliegue), es SIEMPRE
la IP del proxy, nunca la del visitante. La corrección obvia (leer `X-Forwarded-For`) es
insegura sin matices: ese header lo pone el cliente igual que cualquier otro — sin una
lista explícita de qué proxy intermedio es confiable, cualquiera puede mandar
`X-Forwarded-For: lo-que-quiera` y falsificar su origen para saltarse el rate limit por IP.

Regla: sólo se lee `X-Forwarded-For` cuando la conexión INMEDIATA (`request.client.host`)
viene de un proxy de la lista `proxies_confiables` (IPs/CIDRs); en ese caso se toma el
primer salto del header (el más cercano al cliente original, asumiendo un único proxy
confiable inmediato — con una cadena de varios proxies confiables habría que revisar esta
regla). Si la conexión inmediata NO es un proxy conocido, se usa esa IP directo y el
header se ignora por completo — nunca se confía en él "porque está presente".
"""
from __future__ import annotations

from ipaddress import ip_address, ip_network
from typing import Iterable


def _parsear_redes(csv: str) -> list:
    redes = []
    for trozo in csv.split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        try:
            redes.append(ip_network(trozo, strict=False))
        except ValueError:
            continue  # entrada de configuración inválida: se ignora, nunca rompe el arranque
    return redes


def _es_confiable(ip_texto: str, redes: Iterable) -> bool:
    try:
        ip = ip_address(ip_texto)
    except ValueError:
        return False
    return any(ip in red for red in redes)


def origen_real(peer_host: str | None, x_forwarded_for: str | None, proxies_confiables_csv: str) -> str:
    """`peer_host`: `request.client.host`. Nunca lanza; `"?"` si no hay nada usable."""
    peer = peer_host or "?"
    redes = _parsear_redes(proxies_confiables_csv)
    if not redes or not _es_confiable(peer, redes):
        return peer
    if not x_forwarded_for:
        return peer
    primero = x_forwarded_for.split(",")[0].strip()
    return primero or peer
