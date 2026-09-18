"""Casos de uso sobre archivos: preparar subida y firmar descarga.

Ambos operan dentro de una `tenant_session` (RLS garantiza que el documento sea del
tenant). La URL devuelta es efímera: se deriva acá y no se guarda.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.alcance import ROLES_CON_TODO_DESCARGA, sujeto_en_alcance
from app.auth.identidad import Identidad
from app.comun.eventos import registrar_evento
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.storage.contrato import Storage


def _storage_por_defecto() -> Storage:
    from app.storage import obtener_storage

    return obtener_storage()


def preparar_subida(
    session: Session,
    tenant_id: str,
    usuario_id: str,
    documento_id: str,
    nombre_archivo: str,
    content_type: str,
    expira_seg: int = 300,
    storage: Storage | None = None,
) -> str:
    """Genera la clave estable, la guarda en `documento.clave_storage` y devuelve la URL
    PUT prefirmada. Volver a llamar regenera la URL con la misma clave."""
    storage = storage or _storage_por_defecto()
    fila = session.execute(
        text("SELECT documento_id FROM modulo1.documento WHERE documento_id = :d FOR UPDATE"),
        {"d": documento_id},
    ).first()
    if fila is None:
        raise NoEncontrado("Documento inexistente", {"documento_id": documento_id})
    clave = storage.clave_para(str(tenant_id), str(documento_id), nombre_archivo)
    session.execute(
        text("UPDATE modulo1.documento SET clave_storage = :c WHERE documento_id = :d"),
        {"c": clave, "d": documento_id},
    )
    return storage.url_prefirmada_put(clave, content_type, expira_seg)


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
    tenant_id: str,
    usuario_id: str,
    documento_id: str,
    expira_seg: int = 300,
    storage: Storage | None = None,
    identidad: Identidad | None = None,
) -> str:
    """Verifica que el documento sea del tenant (RLS) y tenga archivo, audita la firma
    con el evento DescargarArchivoDeEvidencia y devuelve la URL GET efímera. Si se pasa
    `identidad`, además aplica la matriz de permisos por rol/universo."""
    storage = storage or _storage_por_defecto()
    fila = session.execute(
        text("SELECT clave_storage, sujeto_id FROM modulo1.documento WHERE documento_id = :d"),
        {"d": documento_id},
    ).first()
    if fila is None:
        raise NoEncontrado("Documento inexistente", {"documento_id": documento_id})
    clave, sujeto_id = fila
    if not clave:
        raise ErrorDeDominio(
            "El documento no tiene archivo de evidencia", {"documento_id": documento_id}, codigo="sin_archivo"
        )
    if identidad is not None:
        _autorizar_descarga(session, identidad, sujeto_id)
    expira_en = ahora_utc() + timedelta(seconds=expira_seg)
    registrar_evento(
        session,
        tenant_id,
        "DescargarArchivoDeEvidencia",
        {"documento_id": str(documento_id), "clave_storage": clave, "expira_en": expira_en.isoformat()},
        usuario_id,
    )
    return storage.url_prefirmada_get(clave, expira_seg)
