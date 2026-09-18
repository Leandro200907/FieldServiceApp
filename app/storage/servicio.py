"""Casos de uso sobre archivos de evidencia: preparar subida, confirmar subida y firmar
descarga (A-02 de la auditoría).

Todo opera dentro de una `tenant_session` (RLS garantiza que el documento sea del tenant)
y, además, cada paso verifica en servidor que la clave del archivo pertenezca a ESTE
tenant y a ESTE documento — nunca se confía en una clave persistida sin re-derivarla.
La URL devuelta es efímera: se deriva acá y no se guarda.

Ciclo del archivo (columna `documento.archivo_estado`, migración 0005):
    sin_archivo → subida_pendiente → confirmado → purga_pendiente → purgado
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.alcance import ROLES_CON_TODO_DESCARGA, sujeto_en_alcance
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.config import settings
from app.storage.contrato import Storage

CONTENT_TYPES_PERMITIDOS = {"application/pdf", "image/jpeg", "image/png", "image/webp"}


def _storage_por_defecto() -> Storage:
    from app.storage import obtener_storage

    return obtener_storage()


def _documento(session: Session, documento_id: str, *, bloquear: bool = False) -> dict[str, Any]:
    fila = session.execute(
        text(
            "SELECT documento_id, tenant_id, sujeto_id, origen_propuesta, clave_storage, archivo_estado, "
            "checksum_archivo, archivo_bytes FROM modulo1.documento WHERE documento_id = :d"
            + (" FOR UPDATE" if bloquear else "")
        ),
        {"d": documento_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Documento inexistente", {"documento_id": documento_id})
    return dict(fila)


def _exigir_clave_del_documento(doc: dict[str, Any], tenant_id: str) -> str:
    """La clave persistida tiene que ser exactamente `tenant/documento/...`. Es la misma
    regla que impone `ck_archivo_clave_del_documento` en la base; se repite acá para que
    el servicio no dependa de que la fila sea consistente (defensa en profundidad)."""
    clave = doc["clave_storage"]
    prefijo = f"{tenant_id}/{doc['documento_id']}/"
    if not clave or str(doc["tenant_id"]) != str(tenant_id) or not str(clave).startswith(prefijo):
        raise Prohibido(
            "La clave de storage no corresponde a este tenant y documento",
            {"documento_id": str(doc["documento_id"])},
        )
    return str(clave)


def _autorizar_escritura(identidad: Identidad, doc: dict[str, Any]) -> None:
    """Quién puede adjuntar evidencia: el responsable de legajos (CargarDocumento) o el
    técnico sobre su propia propuesta (ProponerDocumento) — matriz 2.2."""
    if identidad.tiene_rol(Rol.RESPONSABLE_LEGAJOS):
        return
    if identidad.tiene_rol(Rol.TECNICO) and doc["origen_propuesta"] and identidad.sujeto_id == doc["sujeto_id"]:
        return
    raise Prohibido("El usuario no puede adjuntar evidencia a este documento", {"documento_id": str(doc["documento_id"])})


def preparar_subida(
    session: Session,
    identidad: Identidad,
    documento_id: str,
    nombre_archivo: str,
    content_type: str,
    expira_seg: int = 300,
    storage: Storage | None = None,
) -> dict[str, Any]:
    """Deriva la clave EN SERVIDOR, la persiste con estado `subida_pendiente` y devuelve
    la URL PUT firmada (Content-Type y tamaño máximo viajan en la firma). Volver a llamar
    regenera la URL; una vez `confirmado` no se re-prepara (inmutabilidad de la versión)."""
    storage = storage or _storage_por_defecto()
    if content_type not in CONTENT_TYPES_PERMITIDOS:
        raise ErrorDeDominio("Content-Type no permitido para evidencia", {"content_type": content_type,
                             "permitidos": sorted(CONTENT_TYPES_PERMITIDOS)})
    doc = _documento(session, documento_id, bloquear=True)
    _autorizar_escritura(identidad, doc)
    if doc["archivo_estado"] not in ("sin_archivo", "subida_pendiente"):
        raise Conflicto("El documento ya tiene archivo (o está en purga)", {"archivo_estado": doc["archivo_estado"]})
    clave = storage.clave_para(str(identidad.tenant_id), str(documento_id), nombre_archivo)
    session.execute(
        text(
            "UPDATE modulo1.documento SET clave_storage = :c, archivo_estado = 'subida_pendiente', "
            "archivo_content_type = :ct, checksum_archivo = NULL, archivo_bytes = NULL WHERE documento_id = :d"
        ),
        {"c": clave, "ct": content_type, "d": documento_id},
    )
    url = storage.url_prefirmada_put(clave, content_type, expira_seg, settings.storage_max_bytes)
    return {"documento_id": str(documento_id), "url_subida": url, "content_type": content_type,
            "max_bytes": settings.storage_max_bytes, "expira_en_seg": expira_seg}


def confirmar_subida(
    session: Session, identidad: Identidad, documento_id: str, storage: Storage | None = None
) -> dict[str, Any]:
    """Cierra la subida: comprueba que el archivo exista en la clave derivada para este
    tenant+documento y calcula checksum y tamaño DESDE EL ARCHIVO REAL. Nada declarado
    por el cliente entra a la base."""
    storage = storage or _storage_por_defecto()
    doc = _documento(session, documento_id, bloquear=True)
    _autorizar_escritura(identidad, doc)
    if doc["archivo_estado"] == "confirmado":
        return {"documento_id": str(documento_id), "checksum_sha256": doc["checksum_archivo"],
                "bytes": doc["archivo_bytes"], "ya_confirmado": True}
    if doc["archivo_estado"] != "subida_pendiente":
        raise Conflicto("No hay una subida pendiente para este documento", {"archivo_estado": doc["archivo_estado"]})
    clave = _exigir_clave_del_documento(doc, identidad.tenant_id)
    info = storage.inspeccionar(clave)
    if info is None:
        raise ErrorDeDominio("El archivo todavía no fue subido", {"documento_id": str(documento_id)}, codigo="archivo_ausente")
    if info.bytes <= 0 or info.bytes > settings.storage_max_bytes:
        raise ErrorDeDominio("Tamaño de archivo inválido", {"bytes": info.bytes, "max": settings.storage_max_bytes})
    session.execute(
        text(
            "UPDATE modulo1.documento SET archivo_estado = 'confirmado', checksum_archivo = :ck, archivo_bytes = :b "
            "WHERE documento_id = :d"
        ),
        {"ck": info.checksum_sha256, "b": info.bytes, "d": documento_id},
    )
    registrar_evento(
        session, identidad.tenant_id, "EvidenciaAdjuntada",
        {"documento_id": str(documento_id), "checksum_sha256": info.checksum_sha256, "bytes": info.bytes},
        identidad.usuario_id,
    )
    return {"documento_id": str(documento_id), "checksum_sha256": info.checksum_sha256, "bytes": info.bytes,
            "eventos": ["EvidenciaAdjuntada"]}


def _autorizar_descarga(session: Session, identidad: Identidad, sujeto_id: str) -> None:
    """Matriz 2.2 para DescargarArchivoDeEvidencia: responsable_legajos todo; técnico solo
    su propio legajo; supervisor su universo. El universo se resuelve en
    `app.auth.alcance` (única fuente de verdad), acá solo se fija qué roles ven todo."""
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    if sujeto_en_alcance(session, identidad, sujeto_id, hoy, roles_con_todo=ROLES_CON_TODO_DESCARGA):
        return
    raise Prohibido("El usuario no puede descargar la evidencia de este sujeto", {"sujeto_id": sujeto_id})


def firmar_descarga(
    session: Session,
    identidad: Identidad,
    documento_id: str,
    expira_seg: int = 300,
    storage: Storage | None = None,
) -> str:
    """Solo documentos con archivo `confirmado`, cuya clave pertenezca a este tenant y a
    este documento. Autoriza por rol/universo, audita (DescargarArchivoDeEvidencia) y
    devuelve la URL GET efímera."""
    storage = storage or _storage_por_defecto()
    doc = _documento(session, documento_id)
    if doc["archivo_estado"] != "confirmado":
        raise ErrorDeDominio(
            "El documento no tiene archivo de evidencia confirmado",
            {"documento_id": str(documento_id), "archivo_estado": doc["archivo_estado"]},
            codigo="sin_archivo",
        )
    clave = _exigir_clave_del_documento(doc, identidad.tenant_id)
    _autorizar_descarga(session, identidad, doc["sujeto_id"])
    expira_en = ahora_utc() + timedelta(seconds=expira_seg)
    registrar_evento(
        session,
        identidad.tenant_id,
        "DescargarArchivoDeEvidencia",
        {"documento_id": str(documento_id), "clave_storage": clave, "expira_en": expira_en.isoformat()},
        identidad.usuario_id,
    )
    return storage.url_prefirmada_get(clave, expira_seg)
