"""Canales de notificación (anexo de arquitectura de documentacion-habilitante: el motor
entrega alertas ya resueltas a través de una interfaz común; agregar o sacar un canal es
agregar o sacar un adaptador). v1: mail (SMTP) y Telegram (bot propio). WhatsApp queda
DISEÑADO (misma interfaz) pero no construido hasta el primer piloto.

Contrato `Canal.enviar(destino, asunto, texto, clave_idempotencia) -> str` (referencia del
proveedor). Los proveedores reales sólo se configuran por variables de entorno de la
plataforma (nunca en la base ni en el código): SMTP_HOST/PORT/USER/PASSWORD/FROM,
TELEGRAM_BOT_TOKEN. Sin configuración → el canal no está disponible y el handler lo
registra como fallido para ese destinatario (visible en `notificacion_envio`).
"""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Protocol

import httpx


class CanalNoDisponible(Exception):
    """El canal no está configurado en esta plataforma (falta la variable de entorno)."""


class Canal(Protocol):
    nombre: str

    def enviar(self, destino: str, asunto: str, texto: str, clave_idempotencia: str) -> str: ...


class CanalMail:
    nombre = "mail"

    def __init__(self, host: str | None = None, puerto: int | None = None, usuario: str | None = None,
                 password: str | None = None, remitente: str | None = None, starttls: bool = True):
        self.host = host or os.environ.get("SMTP_HOST")
        self.puerto = puerto or int(os.environ.get("SMTP_PORT", "587"))
        self.usuario = usuario or os.environ.get("SMTP_USER")
        self.password = password or os.environ.get("SMTP_PASSWORD")
        self.remitente = remitente or os.environ.get("SMTP_FROM")
        self.starttls = starttls

    def enviar(self, destino: str, asunto: str, texto: str, clave_idempotencia: str) -> str:
        if not self.host or not self.remitente:
            raise CanalNoDisponible("mail: falta SMTP_HOST / SMTP_FROM")
        msg = EmailMessage()
        msg["From"] = self.remitente
        msg["To"] = destino
        msg["Subject"] = asunto
        msg["Message-ID"] = f"<{clave_idempotencia}@modulo1>"   # el mismo mensaje reintentado lleva el mismo id
        msg.set_content(texto)
        with smtplib.SMTP(self.host, self.puerto, timeout=20) as smtp:
            if self.starttls:
                smtp.starttls()
            if self.usuario and self.password:
                smtp.login(self.usuario, self.password)
            smtp.send_message(msg)
        return msg["Message-ID"]


class CanalTelegram:
    nombre = "telegram"

    def __init__(self, token: str | None = None, base_url: str = "https://api.telegram.org", cliente: httpx.Client | None = None):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.base_url = base_url.rstrip("/")
        self._cliente = cliente

    def enviar(self, destino: str, asunto: str, texto: str, clave_idempotencia: str) -> str:
        if not self.token:
            raise CanalNoDisponible("telegram: falta TELEGRAM_BOT_TOKEN")
        cliente = self._cliente or httpx.Client(timeout=20)
        r = cliente.post(f"{self.base_url}/bot{self.token}/sendMessage",
                         json={"chat_id": destino, "text": f"{asunto}\n\n{texto}", "disable_web_page_preview": True})
        r.raise_for_status()
        datos = r.json()
        if not datos.get("ok"):
            raise RuntimeError(f"telegram: {datos.get('description', 'respuesta no ok')}")
        return str(datos["result"]["message_id"])


class CanalEnLog:
    """Sin canal externo (desarrollo / tests): deja constancia y devuelve una referencia."""
    nombre = "log"

    def __init__(self):
        import logging
        self._log = logging.getLogger("modulo1.notificaciones")

    def enviar(self, destino: str, asunto: str, texto: str, clave_idempotencia: str) -> str:
        self._log.warning("notificación (sin canal externo) → %s: %s", destino, asunto)
        return clave_idempotencia


@dataclass
class CanalFalso:
    """Para tests: registra envíos; puede fallar N veces para probar reintentos."""
    nombre: str = "mail"
    enviados: list[dict] = field(default_factory=list)
    fallar_veces: int = 0

    def enviar(self, destino: str, asunto: str, texto: str, clave_idempotencia: str) -> str:
        if self.fallar_veces > 0:
            self.fallar_veces -= 1
            raise RuntimeError("proveedor caído")
        self.enviados.append({"destino": destino, "asunto": asunto, "texto": texto, "clave": clave_idempotencia})
        return f"{self.nombre}-{len(self.enviados)}"


def canales_de_plataforma() -> dict[str, Canal]:
    """Adaptadores reales según el entorno de la plataforma."""
    return {"mail": CanalMail(), "telegram": CanalTelegram()}
