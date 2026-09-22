"""Paquete de entrega con link público firmado y QR por entidad (anexo "Alcance de la v1":
"abre un endpoint público nuevo sobre datos personales — firma con vencimiento, rate
limiting, no enumerable").

- El token es aleatorio (256 bits, urlsafe) + HMAC con secreto propio, `PAQUETE_SECRET`
  (reauditoría Fase 2 punto 3: **obligatorio** con `ENTORNO=produccion` — ver `_secreto()`;
  en desarrollo, sin configurar, se deriva de JWT_SECRET con dominio propio, sólo para no
  exigir un secreto más en un arranque local). En la base sólo se guarda el hash del
  token → ni enumerable ni recuperable desde un dump.
- Vencimiento obligatorio (1–90 días), revocación explícita, traza de accesos.
- Minimización (1.11): el paquete muestra el ESTADO de cumplimiento (requisito, vigencia,
  estado), nunca archivos ni datos personales más allá del identificador natural.
- Rate limiting: por token y por origen, en proceso (`RateLimiter`), con cota de memoria
  propia (punto 3) — sigue siendo de una sola instancia; con más de una, el límite real
  hay que ponerlo en el proxy o en un almacén compartido (Redis), esto no alcanza. El
  "origen" nunca es `X-Forwarded-For` a ciegas — ver `app/comun/red.py`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.alcance import sujeto_en_alcance
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.config import es_produccion, settings


class PaqueteSecretoFaltante(RuntimeError):
    """ENTORNO=produccion sin PAQUETE_SECRET: nunca arranca con un secreto derivado del
    JWT_SECRET en producción (un JWT_SECRET filtrado no debe además dar el de paquetes)."""


def _secreto() -> bytes:
    propio = os.environ.get("PAQUETE_SECRET")
    if propio:
        return propio.encode()
    if es_produccion():
        raise PaqueteSecretoFaltante(
            "Falta PAQUETE_SECRET (obligatorio con ENTORNO=produccion): un secreto derivado "
            "de JWT_SECRET amplía el radio de una filtración de JWT_SECRET a los paquetes públicos."
        )
    return f"paquete:{settings.jwt_secret}".encode()


def _firmar(aleatorio: str) -> str:
    mac = hmac.new(_secreto(), aleatorio.encode(), hashlib.sha256).digest()[:16]
    return f"{aleatorio}.{base64.urlsafe_b64encode(mac).decode().rstrip('=')}"


def verificar_token(token: str) -> str | None:
    """Devuelve el hash del token si la firma es válida; None si no (sin tocar la base)."""
    if not token or "." not in token or len(token) > 200:
        return None
    aleatorio, _ = token.split(".", 1)
    esperado = _firmar(aleatorio)
    if not hmac.compare_digest(esperado, token):
        return None
    return hashlib.sha256(token.encode()).hexdigest()


class RateLimiter:
    """Ventana deslizante simple en memoria: `max_por_minuto` por clave. Con cota de
    memoria (punto 3 de la reauditoría): sin esto, muchas claves distintas de un solo uso
    (por ejemplo, un atacante probando tokens al voleo) hacían crecer el diccionario para
    siempre — nada purgaba una clave que ya no se volvía a consultar. Cada llamada cuenta
    para un barrido periódico que saca las claves sin actividad en la ventana."""

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


limiter = RateLimiter()


# --------------------------------------------------------------------------- comandos


def generar_paquete(session: Session, identidad: Identidad, *, sujeto_id: str, dias_validez: int = 30, base_url: str = "") -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    if not 1 <= dias_validez <= 90:
        raise ErrorDeDominio("dias_validez debe estar entre 1 y 90", {"dias_validez": dias_validez})
    legajo = session.execute(text("SELECT tipo_sujeto, dado_de_baja_en FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s"),
                             {"t": t, "s": sujeto_id}).mappings().first()
    if legajo is None or legajo["dado_de_baja_en"] is not None:
        raise NoEncontrado("Legajo inexistente o dado de baja", {"sujeto_id": sujeto_id})
    token = _firmar(secrets.token_urlsafe(32))
    expira = ahora_utc() + timedelta(days=dias_validez)
    paquete_id = session.execute(text(
        "INSERT INTO modulo1.paquete_entrega (tenant_id, token_hash, sujeto_id, creado_por, expira_en) VALUES (:t, :h, :s, :u, :e) RETURNING paquete_id"),
        {"t": t, "h": hashlib.sha256(token.encode()).hexdigest(), "s": sujeto_id, "u": identidad.usuario_id, "e": expira}).scalar()
    registrar_evento_interno(session, t, "PaqueteDeEntregaGenerado", {"paquete_id": str(paquete_id), "sujeto_id": sujeto_id, "expira_en": expira}, identidad.usuario_id)
    url = f"{base_url.rstrip('/')}/v1/publico/paquete/{token}"
    return {"paquete_id": str(paquete_id), "sujeto_id": sujeto_id, "url": url, "url_qr": url + "/qr.png", "expira_en": expira.isoformat(),
            "eventos": ["PaqueteDeEntregaGenerado"]}


def revocar_paquete(session: Session, identidad: Identidad, *, paquete_id: str) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    fila = session.execute(text("SELECT revocado_en FROM modulo1.paquete_entrega WHERE tenant_id = :t AND paquete_id = :p FOR UPDATE"), {"t": t, "p": paquete_id}).first()
    if fila is None:
        raise NoEncontrado("Paquete inexistente", {"paquete_id": paquete_id})
    if fila[0] is not None:
        raise Conflicto("El paquete ya está revocado", {"paquete_id": paquete_id})
    session.execute(text("UPDATE modulo1.paquete_entrega SET revocado_en = now() WHERE tenant_id = :t AND paquete_id = :p"), {"t": t, "p": paquete_id})
    registrar_evento_interno(session, t, "PaqueteDeEntregaRevocado", {"paquete_id": paquete_id}, identidad.usuario_id)
    return {"paquete_id": paquete_id, "eventos": ["PaqueteDeEntregaRevocado"]}


def paquetes(session: Session, identidad: Identidad, sujeto_id: str | None = None) -> list[dict[str, Any]]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    cond = " AND sujeto_id = :s" if sujeto_id else ""
    return [{**dict(f), "paquete_id": str(f["paquete_id"]), "vigente": f["revocado_en"] is None and f["expira_en"] > ahora_utc()} for f in session.execute(text(
        f"SELECT paquete_id, sujeto_id, creado_por, expira_en, revocado_en, accesos, ultimo_acceso_en, creado_en FROM modulo1.paquete_entrega "
        f"WHERE tenant_id = :t{cond} ORDER BY creado_en DESC"), {"t": identidad.tenant_id, "s": sujeto_id}).mappings()]


# --------------------------------------------------------------------------- vista pública


def vista_publica(session: Session, tenant_id: str, token_hash: str, origen: str | None) -> dict[str, Any]:
    """Contenido del paquete para quien tiene el link: estado de cumplimiento del sujeto,
    sin archivos. Registra el acceso."""
    p = session.execute(text("SELECT paquete_id, sujeto_id, expira_en, revocado_en FROM modulo1.paquete_entrega WHERE tenant_id = :t AND token_hash = :h FOR UPDATE"),
                        {"t": tenant_id, "h": token_hash}).mappings().first()
    if p is None or p["revocado_en"] is not None or p["expira_en"] <= ahora_utc():
        raise NoEncontrado("Paquete inexistente o vencido")
    hoy = hoy_del_tenant(session, tenant_id)
    legajo = session.execute(text("SELECT sujeto_id, tipo_sujeto, identificador_natural FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s"),
                             {"t": tenant_id, "s": p["sujeto_id"]}).mappings().one()
    tenant = session.execute(text("SELECT nombre FROM modulo1.tenant WHERE tenant_id = :t"), {"t": tenant_id}).scalar()
    filas = session.execute(text(
        "SELECT r.nombre AS requisito, r.categoria, x.vigente_hasta, x.estado_confirmacion FROM ("
        "  SELECT requisito_definicion_id, vigente_hasta, estado_confirmacion FROM modulo1.documento WHERE tenant_id = :t AND sujeto_id = :s AND estado_version = 'vigente' "
        "  UNION ALL SELECT requisito_definicion_id, vigente_hasta, estado_confirmacion FROM modulo1.acreditacion_competencia WHERE tenant_id = :t AND persona_id = :s "
        "  UNION ALL SELECT requisito_definicion_id, vigente_hasta, estado_confirmacion FROM modulo1.induccion WHERE tenant_id = :t AND persona_id = :s) x "
        "JOIN modulo1.definicion_requisito r ON r.tenant_id = :t AND r.requisito_definicion_id = x.requisito_definicion_id ORDER BY r.nombre"),
        {"t": tenant_id, "s": p["sujeto_id"]}).mappings().all()
    requisitos = [{"requisito": f["requisito"], "categoria": f["categoria"], "vigente_hasta": f["vigente_hasta"].isoformat(),
                   "estado": "vencido" if f["vigente_hasta"] < hoy else ("vigente" if f["estado_confirmacion"] != "declarado" else "declarado_sin_verificar")} for f in filas]
    session.execute(text("UPDATE modulo1.paquete_entrega SET accesos = accesos + 1, ultimo_acceso_en = now() WHERE tenant_id = :t AND paquete_id = :p"),
                    {"t": tenant_id, "p": str(p["paquete_id"])})
    session.execute(text("INSERT INTO modulo1.paquete_acceso (tenant_id, paquete_id, origen_hash) VALUES (:t, :p, :o)"),
                    {"t": tenant_id, "p": str(p["paquete_id"]), "o": hashlib.sha256(origen.encode()).hexdigest()[:16] if origen else None})
    return {"empresa": tenant, "sujeto": {"sujeto_id": legajo["sujeto_id"], "tipo_sujeto": legajo["tipo_sujeto"], "identificador": legajo["identificador_natural"]},
            "fecha": hoy.isoformat(), "expira_en": p["expira_en"].isoformat(), "requisitos": requisitos,
            "resumen": {"vigentes": sum(1 for r in requisitos if r["estado"] == "vigente"), "vencidos": sum(1 for r in requisitos if r["estado"] == "vencido"),
                        "sin_verificar": sum(1 for r in requisitos if r["estado"] == "declarado_sin_verificar")}}


def qr_png(url: str) -> bytes:
    import io

    import segno

    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=6, border=2)
    return buf.getvalue()
