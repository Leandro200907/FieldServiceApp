"""Entrega de notificaciones: configuración por tenant, vinculación de Telegram, render y
handler idempotente (M-07: un efecto externo no se deshace con rollback).

Regla de entrega (at-least-once sin duplicados): por cada (job, canal, destinatario) hay a
lo sumo una fila `enviado` en `notificacion_envio`; antes de llamar al proveedor se
consulta esa traza y después del envío se registra EN SU PROPIA TRANSACCIÓN (commit
inmediato) — si el lease se pierde o el job falla más tarde, el reintento no reenvía. Los
fallos quedan como `fallido` (con error saneado) y el job reintenta con backoff; el
mensaje se considera entregado cuando todos los destinatarios resolubles tienen `enviado`.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.modules.notificaciones.canales import Canal, CanalEnLog, CanalNoDisponible
from app.worker.cola import sanear_error

# --------------------------------------------------------------------------- configuración


def configuracion_canales(session: Session, identidad: Identidad) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
    fila = session.execute(text("SELECT mail_habilitado, telegram_habilitado, remitente_nombre, actualizado_en FROM modulo1.configuracion_canales WHERE tenant_id = :t"),
                           {"t": identidad.tenant_id}).mappings().first()
    base = dict(fila) if fila else {"mail_habilitado": False, "telegram_habilitado": False, "remitente_nombre": None, "actualizado_en": None}
    vinculados = session.execute(text("SELECT count(*) FROM modulo1.usuario WHERE tenant_id = :t AND telegram_chat_id IS NOT NULL AND activo"),
                                 {"t": identidad.tenant_id}).scalar()
    return {**base, "usuarios_con_telegram": int(vinculados or 0), "whatsapp": "disenado_no_activo"}


def configurar_canales(session: Session, identidad: Identidad, *, mail_habilitado: bool, telegram_habilitado: bool, remitente_nombre: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION)
    t = identidad.tenant_id
    session.execute(text(
        "INSERT INTO modulo1.configuracion_canales (tenant_id, mail_habilitado, telegram_habilitado, remitente_nombre, actualizado_por) "
        "VALUES (:t, :m, :tg, :r, :u) ON CONFLICT (tenant_id) DO UPDATE SET mail_habilitado = EXCLUDED.mail_habilitado, "
        "telegram_habilitado = EXCLUDED.telegram_habilitado, remitente_nombre = EXCLUDED.remitente_nombre, actualizado_en = now(), actualizado_por = EXCLUDED.actualizado_por"),
        {"t": t, "m": mail_habilitado, "tg": telegram_habilitado, "r": remitente_nombre, "u": identidad.usuario_id})
    registrar_evento_interno(session, t, "CanalesDeNotificacionConfigurados", {"mail_habilitado": mail_habilitado, "telegram_habilitado": telegram_habilitado}, identidad.usuario_id)
    return {**configuracion_canales(session, identidad), "eventos": ["CanalesDeNotificacionConfigurados"]}


def vincular_telegram(session: Session, identidad: Identidad, *, usuario_id: str, chat_id: str | None) -> dict[str, Any]:
    """`chat_id` lo obtiene el usuario escribiéndole al bot; configuración lo vincula.
    `chat_id` nulo desvincula."""
    identidad.exigir_rol(Rol.CONFIGURACION)
    t = identidad.tenant_id
    if chat_id is not None and (not chat_id.lstrip("-").isdigit() or len(chat_id) > 32):
        raise ErrorDeDominio("chat_id de Telegram inválido", codigo="telegram_chat_id_invalido")
    fila = session.execute(text("UPDATE modulo1.usuario SET telegram_chat_id = :c WHERE tenant_id = :t AND usuario_id = :u RETURNING email"),
                           {"c": chat_id, "t": t, "u": usuario_id}).first()
    if fila is None:
        raise NoEncontrado("Usuario inexistente", {"usuario_id": usuario_id})
    registrar_evento_interno(session, t, "TelegramVinculado", {"usuario_id": usuario_id, "vinculado": chat_id is not None}, identidad.usuario_id)
    return {"usuario_id": usuario_id, "telegram_vinculado": chat_id is not None, "eventos": ["TelegramVinculado"]}


# --------------------------------------------------------------------------- render


def render(payload: dict[str, Any]) -> tuple[str, str]:
    """(asunto, texto) en castellano llano para cualquier canal."""
    tipo = payload.get("tipo")
    if tipo == "AlertasDeVencimiento":
        alertas = payload.get("alertas", [])
        prioridad = "URGENTE — " if payload.get("prioridad") == "alta" else ""
        asunto = f"{prioridad}{len(alertas)} vencimiento(s) documental(es)"
        lineas = [f"- {a['sujeto_id']} ({a['tipo_sujeto']}): {a['requisito']} — vence {a['vigente_hasta']} — etapa {a['etapa']}"
                  + (" [bajo excepción]" if a.get("bajo_excepcion") else "") for a in alertas]
        return asunto, "Alertas de vencimiento:\n" + "\n".join(lineas)
    if tipo == "PlantillaGlobalActualizada":
        return (f"Plantilla de industria actualizada: {payload.get('nombre')}",
                f"La plataforma publicó la versión {payload.get('version_nueva')} de '{payload.get('nombre')}' ({payload.get('plantilla_tipo')}). "
                f"Su copia local usa la versión {payload.get('copiada_de_version')}. Revise la comparación y decida si la trae; nada se actualiza solo.")
    if tipo == "OcSinMatriz":
        return (f"OC sin matriz de requisitos: {payload.get('clave_origen')}",
                f"La OC {payload.get('clave_origen')} no tiene matriz vigente para su cliente / locación / tipo de servicio. Publique una matriz o copie una plantilla.")
    return (f"Notificación {tipo}", "\n".join(f"{k}: {v}" for k, v in payload.items() if k != "tipo"))


# --------------------------------------------------------------------------- destinatarios y entrega


def _destinatarios(session: Session, tenant_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Usuarios concretos: `destinatario_usuario_id` si viene; si no, todos los activos del rol."""
    if payload.get("destinatario_usuario_id"):
        filas = session.execute(text("SELECT usuario_id, email, telegram_chat_id FROM modulo1.usuario WHERE tenant_id = :t AND usuario_id = :u AND activo"),
                                {"t": tenant_id, "u": payload["destinatario_usuario_id"]}).mappings().all()
    else:
        filas = session.execute(text("SELECT usuario_id, email, telegram_chat_id FROM modulo1.usuario WHERE tenant_id = :t AND activo AND :r = ANY(roles) ORDER BY email"),
                                {"t": tenant_id, "r": payload.get("destinatario_rol", "responsable_legajos")}).mappings().all()
    return [dict(f) for f in filas]


def _canales_habilitados(session: Session, tenant_id: str) -> tuple[bool, bool]:
    fila = session.execute(text("SELECT mail_habilitado, telegram_habilitado FROM modulo1.configuracion_canales WHERE tenant_id = :t"), {"t": tenant_id}).first()
    return (bool(fila[0]), bool(fila[1])) if fila else (False, False)


def entregar(job_id: int, tenant_id: str, payload: dict[str, Any], canales: dict[str, Canal], abrir_sesion: Callable[[str], Any]) -> dict[str, int]:
    """Handler de la cola `notificaciones`. Recibe `abrir_sesion` (tenant_session) porque
    cada envío confirma su traza en una transacción propia — ver docstring del módulo.
    Lanza si algún envío falló (para que el job reintente con backoff)."""
    with abrir_sesion(tenant_id) as s:
        destinatarios = _destinatarios(s, tenant_id, payload)
        mail_on, tg_on = _canales_habilitados(s, tenant_id)
    if not destinatarios:
        return {"destinatarios": 0, "enviados": 0, "fallidos": 0, "omitidos": 0}
    asunto, texto = render(payload)
    plan: list[tuple[str, str, str]] = []  # (canal, destino, usuario_id)
    for d in destinatarios:
        if mail_on and d["email"]:
            plan.append(("mail", d["email"], str(d["usuario_id"])))
        if tg_on and d["telegram_chat_id"]:
            plan.append(("telegram", d["telegram_chat_id"], str(d["usuario_id"])))
    if not plan:
        # sin canal externo habilitado: constancia en el log (CanalEnLog), una vez
        plan = [("log", d["email"] or str(d["usuario_id"]), str(d["usuario_id"])) for d in destinatarios]
    enviados = fallidos = omitidos = 0
    errores: list[str] = []
    for canal_nombre, destino, usuario_id in plan:
        with abrir_sesion(tenant_id) as s:
            ya = s.execute(text("SELECT estado FROM modulo1.notificacion_envio WHERE tenant_id = :t AND job_id = :j AND canal = :c AND destinatario = :d"),
                           {"t": tenant_id, "j": job_id, "c": canal_nombre, "d": destino}).scalar()
        if ya == "enviado":
            omitidos += 1
            continue
        clave = hashlib.sha256(f"{tenant_id}:{job_id}:{canal_nombre}:{destino}".encode()).hexdigest()[:32]
        canal = canales.get(canal_nombre)
        if canal is None and canal_nombre == "log":
            canal = CanalEnLog()
        try:
            if canal is None:
                raise CanalNoDisponible(f"canal {canal_nombre} no configurado")
            ref = canal.enviar(destino, asunto, texto, clave)
            estado, error = "enviado", None
            enviados += 1
        except Exception as e:  # noqa: BLE001
            ref, estado, error = None, "fallido", sanear_error(e)
            fallidos += 1
            errores.append(f"{canal_nombre}:{error}")
        with abrir_sesion(tenant_id) as s:  # traza confirmada de inmediato, pase lo que pase después
            s.execute(text(
                "INSERT INTO modulo1.notificacion_envio (tenant_id, job_id, canal, destinatario, usuario_id, estado, proveedor_ref, error) "
                "VALUES (:t, :j, :c, :d, :u, :e, :ref, :err) ON CONFLICT (tenant_id, job_id, canal, destinatario) DO UPDATE SET "
                "estado = EXCLUDED.estado, proveedor_ref = EXCLUDED.proveedor_ref, error = EXCLUDED.error, intentos = modulo1.notificacion_envio.intentos + 1"),
                {"t": tenant_id, "j": job_id, "c": canal_nombre, "d": destino, "u": usuario_id, "e": estado, "ref": ref, "err": error})
    if fallidos:
        raise RuntimeError(f"{fallidos} envío(s) fallido(s): " + "; ".join(errores)[:300])
    return {"destinatarios": len(destinatarios), "enviados": enviados, "fallidos": fallidos, "omitidos": omitidos}
