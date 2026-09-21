"""Entrega de notificaciones: configuración por tenant, vinculación de Telegram, render y
handler idempotente (M-07: un efecto externo no se deshace con rollback).

Regla de entrega — **at-least-once, no "sin duplicados" a secas**: por cada (job, canal,
destinatario) hay a lo sumo una fila en `notificacion_envio`, y antes de llamar al
proveedor se consulta esa traza para no reenviar en un reintento normal (lease perdido,
job que falla más tarde). Pero el envío al proveedor y el commit de esa traza son DOS
transacciones separadas: si el proceso cae justo entre que `canal.enviar()` devuelve éxito
y ese commit, el reintento no ve la traza y reenvía de verdad — eso sí puede duplicar el
mensaje en el proveedor externo. `CanalMail` mitiga esto parcialmente con un `Message-ID`
determinístico (el proveedor de correo puede deduplicar por ese id, no está garantizado);
`CanalTelegram` no tiene ningún mecanismo de idempotencia en la Bot API, así que ahí la
ventana no está mitigada. Es una ventana angosta (un crash entre una llamada HTTP y un
INSERT) pero real; no se afirma "sin duplicados" sin esta salvedad.

Cuatro estados en `notificacion_envio.estado`:
- `enviado`: salió de verdad por mail o Telegram.
- `fallido`: el proveedor fue llamado y falló; el job reintenta con backoff.
- `sin_canal`: el tenant tiene algún canal habilitado, pero ESTE destinatario no tiene
  email ni `telegram_chat_id` vinculado — no hay ningún destino al que llamar. Antes se
  perdía en silencio (quedaba fuera del plan sin ninguna fila); ahora queda trazado, sin
  reintento automático (nada que reintentar hasta que alguien le cargue el dato de
  contacto), visible por `GET /v1/consultas/envios_notificacion`.
- `registrado_log`: NINGÚN canal está habilitado para el tenant; la notificación queda
  como constancia en el log del proceso (`CanalEnLog`), nunca como sustituto de una
  entrega real. Antes esto se guardaba como `enviado` con `canal='log'`, indistinguible de
  un envío real en cualquier conteo — ahora es un estado propio: una alerta que "solo
  quedó en el log" no debe contarse como entregada en producción.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.comun.paginacion import Pagina, envolver
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
    if tipo == "EvidenciaInvalida":
        return (f"Evidencia inválida: documento {payload.get('documento_id')}",
                f"El archivo del documento {payload.get('documento_id')} (sujeto {payload.get('sujeto_id')}) no pasó la "
                f"validación técnica: {payload.get('motivo')}. El dato sigue marcado como verificado, pero la evidencia "
                f"no se puede descargar hasta reemplazar el archivo o resolverlo.")
    if tipo == "ValidacionEvidenciaEstancada":
        return (f"URGENTE — validación de evidencia estancada (documento {payload.get('documento_id')})",
                f"El job de validación técnica del documento {payload.get('documento_id')} agotó {payload.get('intentos')} "
                f"intentos y quedó en dead-letter (job_id {payload.get('job_id')}). Revisar la causa: puede ser un problema "
                f"de storage, no del archivo en sí.")
    if tipo == "OutboxEstancado":
        return (f"URGENTE — Módulo 2 no se entera de un cambio ({payload.get('evento_tipo')})",
                f"El evento {payload.get('evento_id')} ({payload.get('evento_tipo')}) agotó {payload.get('intentos')} intentos de "
                f"publicación hacia Módulo 2 y quedó estancado — Módulo 2 NO se enteró de este cambio de cumplimiento. "
                f"Último error: {payload.get('error')}. Revisar la causa y reprocesar con "
                f"`scripts/administracion.py reprocesar-outbox --evento-id {payload.get('evento_id')}` una vez resuelta.")
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
    Lanza si algún envío falló (para que el job reintente con backoff); `sin_canal` NO
    lanza — no hay nada que un reintento del job pueda arreglar, sólo cargar el dato de
    contacto que falta (fuera del ciclo de vida de este job)."""
    with abrir_sesion(tenant_id) as s:
        destinatarios = _destinatarios(s, tenant_id, payload)
        mail_on, tg_on = _canales_habilitados(s, tenant_id)
    vacio = {"destinatarios": 0, "enviados": 0, "fallidos": 0, "omitidos": 0, "sin_canal": 0, "registrados_log": 0}
    if not destinatarios:
        return vacio
    asunto, texto = render(payload)
    algun_canal_habilitado = mail_on or tg_on
    plan: list[tuple[str, str, str]] = []  # (canal, destino, usuario_id) — se intenta un envío real
    sin_canal_ids: list[str] = []  # usuario_id sin ningún canal resoluble para él
    for d in destinatarios:
        uid = str(d["usuario_id"])
        tiene_canal = False
        if mail_on and d["email"]:
            plan.append(("mail", d["email"], uid))
            tiene_canal = True
        if tg_on and d["telegram_chat_id"]:
            plan.append(("telegram", d["telegram_chat_id"], uid))
            tiene_canal = True
        if not tiene_canal:
            if algun_canal_habilitado:
                # el tenant tiene canal(es) habilitados; a ESTE destinatario le falta el
                # dato de contacto (sin email o sin telegram_chat_id) — antes se perdía
                # en silencio, ahora queda trazado como `sin_canal`.
                sin_canal_ids.append(uid)
            else:
                # ningún canal habilitado para el tenant: constancia en el log, nunca
                # contada como entrega real (ver docstring del módulo).
                plan.append(("log", d["email"] or uid, uid))
    enviados = fallidos = omitidos = sin_canal = registrados_log = 0
    errores: list[str] = []

    for uid in sin_canal_ids:
        with abrir_sesion(tenant_id) as s:
            ya = s.execute(text("SELECT 1 FROM modulo1.notificacion_envio WHERE tenant_id = :t AND job_id = :j AND canal = 'sin_canal' AND destinatario = :d"),
                           {"t": tenant_id, "j": job_id, "d": uid}).first()
        if ya is not None:
            omitidos += 1
            continue
        with abrir_sesion(tenant_id) as s:
            s.execute(text(
                "INSERT INTO modulo1.notificacion_envio (tenant_id, job_id, canal, destinatario, usuario_id, estado, error) "
                "VALUES (:t, :j, 'sin_canal', :d, :u, 'sin_canal', :err) ON CONFLICT (tenant_id, job_id, canal, destinatario) DO UPDATE SET "
                "intentos = modulo1.notificacion_envio.intentos + 1"),
                {"t": tenant_id, "j": job_id, "d": uid, "u": uid, "err": "sin email ni telegram_chat_id vinculado para este destinatario"})
        sin_canal += 1

    for canal_nombre, destino, usuario_id in plan:
        with abrir_sesion(tenant_id) as s:
            ya = s.execute(text("SELECT estado FROM modulo1.notificacion_envio WHERE tenant_id = :t AND job_id = :j AND canal = :c AND destinatario = :d"),
                           {"t": tenant_id, "j": job_id, "c": canal_nombre, "d": destino}).scalar()
        if ya in ("enviado", "registrado_log"):
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
            error = None
            if canal_nombre == "log":
                estado = "registrado_log"
                registrados_log += 1
            else:
                estado = "enviado"
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
    return {"destinatarios": len(destinatarios), "enviados": enviados, "fallidos": fallidos, "omitidos": omitidos,
            "sin_canal": sin_canal, "registrados_log": registrados_log}


# --------------------------------------------------------------------------- consulta operativa


def envios(session: Session, identidad: Identidad, p: Pagina, estado: str | None = None, job_id: int | None = None) -> dict[str, Any]:
    """Traza de entregas para seguimiento operativo (Fase 2 punto 1): por defecto sólo lo
    que necesita acción humana (`sin_canal`, `fallido`), para no inundar la vista con
    envíos exitosos. `estado='todos'` trae todo, incluido `registrado_log` — que sigue sin
    contarse como entrega real en ningún resumen, sólo se ve acá si se pide explícito."""
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
    tenant_id = identidad.tenant_id
    params: dict[str, Any] = {"t": tenant_id}
    cond = ""
    if job_id is not None:
        cond += " AND n.job_id = :j"
        params["j"] = job_id
    if estado == "todos":
        pass
    elif not estado or estado == "accion_requerida":
        cond += " AND n.estado IN ('sin_canal', 'fallido')"
    else:
        cond += " AND n.estado = :e"
        params["e"] = estado
    sql_base = (
        "SELECT n.envio_id, n.job_id, n.canal, n.destinatario, n.usuario_id, u.email, u.nombre, "
        "n.estado, n.proveedor_ref, n.error, n.intentos, n.creado_en "
        "FROM modulo1.notificacion_envio n LEFT JOIN modulo1.usuario u ON u.tenant_id = n.tenant_id AND u.usuario_id = n.usuario_id "
        "WHERE n.tenant_id = :t"
    )
    total = session.execute(text(f"SELECT count(*) FROM ({sql_base}{cond}) x"), params).scalar()
    filas = session.execute(text(f"{sql_base}{cond} ORDER BY n.creado_en DESC OFFSET :off LIMIT :lim"),
                            {**params, "off": p.offset, "lim": p.limit}).mappings().all()
    return envolver([{k: (str(v) if hasattr(v, "hex") else v) for k, v in dict(f).items()} for f in filas], int(total or 0), p)
