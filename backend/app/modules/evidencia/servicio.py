"""Validación técnica de evidencia (reauditoría Fase 2 punto 2, migración 0021).

Job asincrónico `validacion_evidencia`, producido por `app/storage/servicio.py::confirmar_subida`:
verifica ÚNICAMENTE integridad técnica del archivo real — formato reconocible, tipo de
contenido real coincide con el declarado, un PDF se puede abrir (no corrupto), escaneo de
malware si hay un proveedor configurado (hoy: ninguno, `no_configurado` siempre, nunca se
afirma "limpio" sin haber escaneado de verdad). NUNCA decide negocio: no toca
`estado_confirmacion` por sí sola (arquitectura-tecnica.md §8.5 — esa sigue siendo una
decisión humana).

Fencing por token: cada ciclo de subida real (confirmar_subida, un reemplazo, o una
invalidación manual) regenera `documento.archivo_validacion_token`. El handler sólo
consolida su resultado con un `UPDATE ... WHERE archivo_validacion_token = :token`; si no
coincide (el archivo se reemplazó o alguien invalidó a mano mientras el job estaba en
vuelo), el `UPDATE` no toca ninguna fila y el job termina sin efecto — nunca pisa un
archivo más nuevo.

Dos casos al resultar inválido (según en qué estaba `estado_confirmacion` en el momento):
- CASO A (`declarado`, propuesta vigente): falla definitiva → mismo camino que
  `RechazarPropuesta`/`DocumentoRechazado` (restaura la versión anterior). Es exactamente
  lo que ya pedía arquitectura-tecnica.md: "no se inventa un estado nuevo del Documento".
- CASO B (`verificado` / `confirmado_en_fuente`): NUNCA se toca `estado_confirmacion` —
  se marca `archivo_validacion='invalido'` (que además bloquea la descarga, ver
  `storage/servicio.py::firmar_descarga`), se notifica a responsable_legajos y se dispara
  la MISMA política de revaluación que ya existe para un documento vencido
  (`EvidenciaInvalidaPostVerificacion` en `app.core.revaluacion.EVENTOS_FUENTE`, mismo
  selector que `DocumentoVencido`) — nunca un mecanismo nuevo.

Recuperación manual: `preparar_subida` permite reemplazar un archivo `invalido`;
`invalidar_evidencia_verificada` (Responsable_legajos) invalida a mano un documento ya
verificado que el chequeo automático no haya podido detectar."""
from __future__ import annotations

import io
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento, registrar_evento_interno
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import ahora_utc

log = logging.getLogger("modulo1.evidencia")

CONTENT_TYPES_PERMITIDOS = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
ESTADOS_VERIFICADOS = ("verificado", "confirmado_en_fuente")


def _storage_por_defecto():
    from app.storage import obtener_storage

    return obtener_storage()


# --------------------------------------------------------------------------- verificación técnica pura


def _tipo_detectado(contenido: bytes) -> str | None:
    """Magic bytes — nunca confía en la extensión ni en el Content-Type declarado."""
    if contenido.startswith(b"%PDF-"):
        return "application/pdf"
    if contenido.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp"
    return None


def _escanear_malware(contenido: bytes) -> str:
    """Puerto de antivirus. Sin proveedor real conectado a esta plataforma: SIEMPRE
    `no_configurado` — nunca `limpio` sin haber escaneado de verdad. El día que se
    conecte un scanner real, este es el único lugar a cambiar."""
    return "no_configurado"


def verificar_archivo(contenido: bytes, content_type_declarado: str | None) -> tuple[bool, str | None, dict[str, Any]]:
    """(valido, motivo, detalles) — función pura sobre bytes ya leídos, sin I/O. Un
    archivo malo NUNCA lanza acá: el resultado inválido ES la respuesta correcta; sólo el
    llamador decide si algo (storage caído, etc.) fue un problema de infraestructura."""
    detalles: dict[str, Any] = {
        "content_type_declarado": content_type_declarado,
        "scan_estado": _escanear_malware(contenido),
    }
    detectado = _tipo_detectado(contenido)
    detalles["content_type_detectado"] = detectado
    if detectado is None:
        return False, "el archivo no tiene un formato reconocible (PDF/JPEG/PNG/WEBP)", detalles
    if content_type_declarado and detectado != content_type_declarado:
        return False, f"el contenido real ({detectado}) no coincide con el tipo declarado ({content_type_declarado})", detalles
    if detectado == "application/pdf":
        try:
            from pypdf import PdfReader

            lector = PdfReader(io.BytesIO(contenido))
            detalles["paginas"] = len(lector.pages)
        except Exception as exc:  # noqa: BLE001 — cualquier falla de parseo = PDF corrupto
            return False, f"PDF corrupto o ilegible: {exc}", detalles
    return True, None, detalles


# --------------------------------------------------------------------------- despacho caso A / caso B


def _rechazar_por_validacion_fallida(session: Session, tenant_id: str, documento_id: str, motivo: str, doc: dict[str, Any]) -> None:
    """Caso A: reutiliza EXACTAMENTE el camino de RechazarPropuesta (arquitectura-tecnica.md
    §8.5: "no se inventa un estado nuevo del Documento")."""
    from app.modules.legajos.servicio import _restaurar_sucedido

    session.execute(text("UPDATE modulo1.documento SET estado_version = 'rechazada' WHERE tenant_id = :t AND documento_id = :d"),
                    {"t": tenant_id, "d": documento_id})
    restaurado = _restaurar_sucedido(session, tenant_id, doc["sucede_a"])
    registrar_evento(
        session, tenant_id, "DocumentoRechazado",
        {"documento_id": documento_id, "sujeto_id": doc["sujeto_id"],
         "requisito_definicion_id": str(doc["requisito_definicion_id"]) if doc["requisito_definicion_id"] else None,
         "motivo": f"validación técnica del archivo: {motivo}", "restaurado_documento_id": restaurado},
        None,
    )


def _notificar_y_revaluar(session: Session, tenant_id: str, documento_id: str, motivo: str, doc: dict[str, Any], usuario_id: str | None) -> None:
    """Caso B: NUNCA toca estado_confirmacion. Notifica a responsable_legajos y dispara
    la misma política de revaluación que un documento vencido (mismo selector, ver
    app.core.revaluacion.EVENTOS_FUENTE)."""
    from app.worker.cola import encolar

    req_id = str(doc["requisito_definicion_id"]) if doc["requisito_definicion_id"] else None
    encolar(session, "notificaciones", {
        "tipo": "EvidenciaInvalida", "destinatario_rol": "responsable_legajos",
        "documento_id": documento_id, "sujeto_id": doc["sujeto_id"], "requisito_definicion_id": req_id, "motivo": motivo,
    }, tenant_id=tenant_id, disponible_en=ahora_utc())
    registrar_evento(
        session, tenant_id, "EvidenciaInvalidaPostVerificacion",
        {"documento_id": documento_id, "sujeto_id": doc["sujeto_id"], "requisito_definicion_id": req_id, "motivo": motivo},
        usuario_id,
    )


def _despachar_invalidez(session: Session, tenant_id: str, documento_id: str, motivo: str, doc: dict[str, Any], usuario_id: str | None = None) -> None:
    if doc["estado_confirmacion"] == "declarado" and doc["origen_propuesta"] and doc["estado_version"] == "vigente":
        _rechazar_por_validacion_fallida(session, tenant_id, documento_id, motivo, doc)
    elif doc["estado_confirmacion"] in ESTADOS_VERIFICADOS:
        _notificar_y_revaluar(session, tenant_id, documento_id, motivo, doc, usuario_id)
    # Ni propuesta vigente ni verificado (p. ej. ya sucedida/rechazada por otra vía
    # mientras el job estaba en vuelo): la traza EvidenciaInvalida ya quedó escrita, no
    # hay ninguna otra acción de dominio pendiente.


def _marcar_resultado(session: Session, tenant_id: str, documento_id: str, token: str, valido: bool, motivo: str | None, detalles: dict[str, Any]) -> None:
    """Fencing: el UPDATE sólo toca la fila si el token todavía coincide con el que tenía
    este job — si no, `RETURNING` no devuelve nada y el resto es un no-op silencioso (el
    archivo ya se reemplazó o se invalidó a mano; el resultado de este job ya no aplica)."""
    estado = "valido" if valido else "invalido"
    fila = session.execute(
        text(
            "UPDATE modulo1.documento SET archivo_validacion = :e, archivo_validacion_motivo = :m, "
            "archivo_validacion_en = now(), archivo_scan_estado = :sc "
            "WHERE tenant_id = :t AND documento_id = :d AND archivo_validacion_token = :tok "
            "RETURNING sujeto_id, requisito_definicion_id, estado_confirmacion, estado_version, origen_propuesta, sucede_a"
        ),
        {"e": estado, "m": motivo, "sc": detalles.get("scan_estado"), "t": tenant_id, "d": documento_id, "tok": token},
    ).mappings().first()
    if fila is None:
        log.info("validacion_evidencia: documento %s ya no tiene el token esperado — resultado descartado (archivo reemplazado/invalidado)", documento_id)
        return
    if valido:
        registrar_evento_interno(session, tenant_id, "EvidenciaValidada", {"documento_id": documento_id, **detalles}, None)
        return
    registrar_evento_interno(session, tenant_id, "EvidenciaInvalida", {"documento_id": documento_id, "motivo": motivo, **detalles}, None)
    _despachar_invalidez(session, tenant_id, documento_id, motivo or "sin motivo", dict(fila))


# --------------------------------------------------------------------------- handler de la cola


def procesar(session: Session, job: Any, contexto: dict[str, Any]) -> None:
    """Handler de `validacion_evidencia`. `JobNoProcesable` = falla definitiva (nunca se
    va a resolver reintentando: documento inexistente, sin archivo que validar, archivo
    ausente en storage). Cualquier otra excepción = transitoria (storage momentáneamente
    inaccesible, red, etc.) y reintenta con el backoff genérico del worker."""
    from app.worker.main import JobNoProcesable

    payload = job.payload if isinstance(job.payload, dict) else {}
    documento_id = payload.get("documento_id")
    token = payload.get("token")
    tenant_id = job.tenant_id
    if not tenant_id:
        raise JobNoProcesable("validacion_evidencia sin tenant")
    if not documento_id or not token:
        raise JobNoProcesable("validacion_evidencia sin documento_id/token en el payload")

    doc = session.execute(
        text("SELECT archivo_estado, archivo_validacion_token, clave_storage, archivo_content_type "
             "FROM modulo1.documento WHERE tenant_id = :t AND documento_id = :d FOR UPDATE"),
        {"t": tenant_id, "d": documento_id},
    ).mappings().first()
    if doc is None:
        raise JobNoProcesable(f"documento {documento_id} inexistente")
    if str(doc["archivo_validacion_token"]) != str(token):
        log.info("validacion_evidencia: job %s obsoleto para documento %s (token no coincide) — no-op", job.id, documento_id)
        return
    if doc["archivo_estado"] != "confirmado":
        raise JobNoProcesable(f"documento {documento_id}: archivo_estado={doc['archivo_estado']}, nada que validar")

    storage = contexto.get("storage") or _storage_por_defecto()
    try:
        contenido = storage.leer(doc["clave_storage"])
    except FileNotFoundError as exc:
        raise JobNoProcesable(f"documento {documento_id}: archivo ausente en storage") from exc
    # cualquier otra excepción de storage.leer (red, permisos, storage caído) es
    # TRANSITORIA: se deja propagar tal cual, sin envolver en JobNoProcesable, para que
    # el worker reintente con su backoff genérico.

    valido, motivo, detalles = verificar_archivo(contenido, doc["archivo_content_type"])
    _marcar_resultado(session, tenant_id, documento_id, token, valido, motivo, detalles)


def alertar_dead_letter(session: Session, tenant_id: str, job: Any) -> None:
    """Dead-letter de validacion_evidencia visible y notificado (nunca silencioso) —
    llamado desde app/worker/main.py cuando el job agota los reintentos."""
    from app.worker.cola import encolar

    payload = job.payload if isinstance(job.payload, dict) else {}
    encolar(session, "notificaciones", {
        "tipo": "ValidacionEvidenciaEstancada", "destinatario_rol": "configuracion",
        "documento_id": payload.get("documento_id"), "job_id": job.id, "intentos": job.intentos,
    }, tenant_id=tenant_id, disponible_en=ahora_utc())


# --------------------------------------------------------------------------- comando manual (Responsable-only)


def invalidar_evidencia_verificada(session: Session, identidad: Identidad, *, documento_id: str, motivo: str) -> dict[str, Any]:
    """Recuperación manual, Responsable_legajos: invalida a mano un documento YA
    verificado cuyo archivo el chequeo automático no detectó (o cuya validación técnica ya
    corrió y dio válida, pero un humano encuentra un problema que el chequeo no cubre —
    igual de válido). Regenera el token: cualquier job en vuelo con el token viejo queda
    automáticamente sin efecto (mismo fencing que un reemplazo de archivo)."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    tenant_id = identidad.tenant_id
    doc = session.execute(
        text("SELECT sujeto_id, requisito_definicion_id, estado_confirmacion, estado_version, archivo_estado "
             "FROM modulo1.documento WHERE tenant_id = :t AND documento_id = :d FOR UPDATE"),
        {"t": tenant_id, "d": documento_id},
    ).mappings().first()
    if doc is None:
        raise NoEncontrado("Documento inexistente", {"documento_id": documento_id})
    if doc["estado_confirmacion"] == "declarado":
        # Antes que el chequeo de archivo: aplica igual si nunca se llegó a adjuntar uno.
        raise ErrorDeDominio("El documento está declarado, todavía no verificado: usar RechazarPropuesta",
                             {"documento_id": documento_id}, codigo="usar_rechazar_propuesta")
    if doc["archivo_estado"] != "confirmado":
        raise ErrorDeDominio("El documento no tiene archivo adjunto confirmado para invalidar",
                             {"documento_id": documento_id, "archivo_estado": doc["archivo_estado"]}, codigo="sin_archivo")

    nuevo_token = str(uuid.uuid4())
    session.execute(
        text("UPDATE modulo1.documento SET archivo_validacion = 'invalido', "
             "archivo_validacion_motivo = :m, archivo_validacion_en = now(), archivo_validacion_token = :tok "
             "WHERE tenant_id = :t AND documento_id = :d"),
        {"m": f"invalidado manualmente por responsable_legajos: {motivo}", "tok": nuevo_token, "t": tenant_id, "d": documento_id},
    )
    registrar_evento_interno(session, tenant_id, "EvidenciaInvalida",
                             {"documento_id": documento_id, "motivo": motivo, "manual": True}, identidad.usuario_id)
    _notificar_y_revaluar(session, tenant_id, documento_id, motivo, dict(doc), identidad.usuario_id)
    return {"documento_id": documento_id, "eventos": ["EvidenciaInvalida", "EvidenciaInvalidaPostVerificacion"]}


# --------------------------------------------------------------------------- consulta / bandeja


def bandeja(session: Session, identidad: Identidad, p: Pagina, estado: str | None = None) -> dict[str, Any]:
    """Documentos con archivo adjunto cuya validación necesita atención. Por defecto
    (`estado` sin pasar, o `accion_requerida`): `pendiente` (esperando el job) e
    `invalido` (necesita reemplazo o ya se resolvió). `estado=todos` trae también los
    `valido`."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    tenant_id = identidad.tenant_id
    params: dict[str, Any] = {"t": tenant_id}
    cond = " AND archivo_estado = 'confirmado'"
    if estado == "todos":
        pass
    elif not estado or estado == "accion_requerida":
        cond += " AND archivo_validacion IN ('pendiente', 'invalido')"
    else:
        cond += " AND archivo_validacion = :e"
        params["e"] = estado
    sql = (
        "SELECT documento_id, sujeto_id, requisito_definicion_id, estado_confirmacion, archivo_validacion, "
        "archivo_validacion_motivo, archivo_validacion_en, archivo_scan_estado, creado_en "
        "FROM modulo1.documento WHERE tenant_id = :t"
    )
    total = session.execute(text(f"SELECT count(*) FROM ({sql}{cond}) x"), params).scalar()
    filas = session.execute(
        text(f"{sql}{cond} ORDER BY archivo_validacion_en DESC NULLS FIRST, creado_en DESC OFFSET :off LIMIT :lim"),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    return envolver([{k: (str(v) if hasattr(v, "hex") else v) for k, v in dict(f).items()} for f in filas], int(total or 0), p)
