"""Drive de solo lectura (anexo v1): escaneo manual o programado de UNA carpeta, extracción
de tipo/sujeto/fecha por confianza y bandeja de excepciones. Entra como `declarado`
(1.10) y NUNCA habilita por sí solo: el responsable confirma o rechaza como cualquier
propuesta.

Extracción v1 (DECISIONES §17): por el NOMBRE del archivo, sin leer el contenido (la
lectura completa es segunda etapa). Convención `<sujeto_id>__<requisito>__<AAAA-MM-DD>[__<AAAA-MM-DD>].pdf`:
- alta: sujeto existente + requisito único por nombre (ILIKE) aplicable al tipo de sujeto +
  fecha de vencimiento válida → se importa (documento declarado + archivo adjunto);
- media: sujeto y requisito resueltos pero sin fecha, o fecha ambigua → bandeja;
- baja: no se resuelve sujeto o requisito → bandeja.
Cada archivo se recuerda por (id externo, hash): re-escanear no duplica; un archivo
resuelto a mano desde la bandeja se importa con los datos que cargue el responsable.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.comun.paginacion import Pagina, envolver
from app.config import settings
from app.modules.drive.proveedor import ArchivoRemoto, ProveedorDeCarpeta, ProveedorNoDisponible
from app.storage.contrato import Storage

MIMES_ACEPTADOS = {"application/pdf", "image/jpeg", "image/png"}
_PATRON = re.compile(r"^(?P<sujeto>[^_]+(?:_[^_]+)*?)__(?P<requisito>[^_]+(?:_[^_]+)*?)__(?P<f1>\d{4}-\d{2}-\d{2})(?:__(?P<f2>\d{4}-\d{2}-\d{2}))?\.(?P<ext>pdf|jpe?g|png)$", re.I)


# --------------------------------------------------------------------------- configuración


def configuracion(session: Session, identidad: Identidad) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
    f = session.execute(text("SELECT habilitado, carpeta_id, intervalo_horas, ultimo_escaneo_en, ultimo_escaneo_resultado FROM modulo1.configuracion_drive WHERE tenant_id = :t"),
                        {"t": identidad.tenant_id}).mappings().first()
    base = dict(f) if f else {"habilitado": False, "carpeta_id": None, "intervalo_horas": None, "ultimo_escaneo_en": None, "ultimo_escaneo_resultado": None}
    pend = session.execute(text("SELECT count(*) FROM modulo1.archivo_drive WHERE tenant_id = :t AND estado = 'pendiente_revision'"), {"t": identidad.tenant_id}).scalar()
    return {**base, "proveedor": "google_drive", "pendientes_revision": int(pend or 0),
            "convencion_nombre": "<sujeto_id>__<requisito>__<AAAA-MM-DD vence>[__<AAAA-MM-DD desde>].pdf|jpg|png"}


def configurar(session: Session, identidad: Identidad, *, habilitado: bool, carpeta_id: str | None, intervalo_horas: int | None) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION)
    if habilitado and not carpeta_id:
        raise ErrorDeDominio("Para habilitar Drive hace falta carpeta_id", codigo="carpeta_requerida")
    t = identidad.tenant_id
    session.execute(text(
        "INSERT INTO modulo1.configuracion_drive (tenant_id, habilitado, carpeta_id, intervalo_horas, actualizado_por) VALUES (:t, :h, :c, :i, :u) "
        "ON CONFLICT (tenant_id) DO UPDATE SET habilitado = EXCLUDED.habilitado, carpeta_id = EXCLUDED.carpeta_id, intervalo_horas = EXCLUDED.intervalo_horas, "
        "actualizado_en = now(), actualizado_por = EXCLUDED.actualizado_por"),
        {"t": t, "h": habilitado, "c": carpeta_id, "i": intervalo_horas, "u": identidad.usuario_id})
    registrar_evento_interno(session, t, "DriveConfigurado", {"habilitado": habilitado, "intervalo_horas": intervalo_horas}, identidad.usuario_id)
    return {**configuracion(session, identidad), "eventos": ["DriveConfigurado"]}


# --------------------------------------------------------------------------- extracción


def _normalizar(texto: str) -> str:
    """Sin acentos, minúsculas, guiones bajos → espacios, espacios colapsados."""
    import unicodedata
    base = unicodedata.normalize("NFKD", texto.replace("_", " ")).encode("ascii", "ignore").decode()
    return " ".join(base.lower().split())



def extraer(session: Session, tenant_id: str, archivo: ArchivoRemoto) -> tuple[str, dict[str, Any], str | None]:
    """(confianza, extraccion, motivo)."""
    ext: dict[str, Any] = {"nombre": archivo.nombre}
    if archivo.mime and archivo.mime not in MIMES_ACEPTADOS:
        return "baja", ext, "tipo de archivo no aceptado"
    m = _PATRON.match(archivo.nombre.strip())
    if not m:
        return "baja", ext, "el nombre no sigue la convención"
    sujeto = session.execute(text("SELECT sujeto_id, tipo_sujeto FROM modulo1.legajo WHERE tenant_id = :t AND lower(sujeto_id) = lower(:s) AND dado_de_baja_en IS NULL"),
                             {"t": tenant_id, "s": m["sujeto"]}).mappings().first()
    if sujeto is None:
        ext["sujeto_buscado"] = m["sujeto"]
        return "baja", ext, "sujeto inexistente"
    ext["sujeto_id"] = sujeto["sujeto_id"]
    nombre_req = m["requisito"].replace("_", " ")
    clave = _normalizar(nombre_req)
    todas = session.execute(text("SELECT requisito_definicion_id::text, nombre FROM modulo1.definicion_requisito WHERE tenant_id = :t AND activa AND tipo_sujeto_aplicable = :ts ORDER BY nombre"),
                            {"t": tenant_id, "ts": sujeto["tipo_sujeto"]}).mappings().all()
    exactos = [c for c in todas if _normalizar(c["nombre"]) == clave]
    candidatos = exactos or [c for c in todas if clave in _normalizar(c["nombre"])]
    if len(candidatos) != 1:
        ext["requisito_buscado"] = nombre_req
        ext["candidatos"] = [c["nombre"] for c in candidatos][:5]
        return ("baja" if not candidatos else "media"), ext, ("requisito inexistente" if not candidatos else "requisito ambiguo")
    ext["requisito_definicion_id"] = candidatos[0]["requisito_definicion_id"]
    ext["requisito"] = candidatos[0]["nombre"]
    try:
        hasta = date.fromisoformat(m["f1"])
        desde = date.fromisoformat(m["f2"]) if m["f2"] else None
    except ValueError:
        return "media", ext, "fecha inválida"
    if desde and desde > hasta:
        return "media", ext, "fechas invertidas"
    ext["vigente_hasta"] = hasta.isoformat()
    ext["vigente_desde"] = (desde or date(hasta.year - 1, hasta.month, min(hasta.day, 28))).isoformat()
    return "alta", ext, None


# --------------------------------------------------------------------------- escaneo


def _importar(session: Session, identidad: Identidad, archivo: ArchivoRemoto, ext: dict[str, Any], proveedor: ProveedorDeCarpeta, storage: Storage,
              eventos: list[str]) -> str:
    """Documento declarado + archivo adjunto (misma transacción; el byte se escribe antes
    del commit y, si la transacción cae, queda huérfano pero nunca referenciado)."""
    from app.modules.legajos import esquemas as e
    from app.modules.legajos.servicio import _insertar_version_documento
    from app.storage.servicio import confirmar_subida, preparar_subida

    r = _insertar_version_documento(
        session, identidad, sujeto_id=ext["sujeto_id"], requisito_definicion_id=ext["requisito_definicion_id"],
        vigente_desde=date.fromisoformat(ext["vigente_desde"]), vigente_hasta=date.fromisoformat(ext["vigente_hasta"]), numero=None,
        origen="drive", estado_confirmacion="declarado", origen_propuesta=True, confianza_extraccion="alta", eventos=eventos,
    )
    contenido = proveedor.descargar(archivo.id_externo, settings.storage_max_bytes)
    ct = archivo.mime or "application/pdf"
    prep = preparar_subida(session, identidad, r["documento_id"], archivo.nombre, ct, storage=storage)
    storage.escribir(storage.clave_para(identidad.tenant_id, r["documento_id"], archivo.nombre), contenido)
    confirmar_subida(session, identidad, r["documento_id"], storage=storage)
    return r["documento_id"]


def escanear(session: Session, identidad: Identidad, proveedor: ProveedorDeCarpeta, storage: Storage, ahora: datetime | None = None) -> dict[str, Any]:
    """Un escaneo de la carpeta configurada: cada archivo nuevo (id, hash) se clasifica y
    o se importa (alta) o va a la bandeja (media/baja). Idempotente entre corridas."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    t = identidad.tenant_id
    cfg = session.execute(text("SELECT habilitado, carpeta_id FROM modulo1.configuracion_drive WHERE tenant_id = :t FOR UPDATE"), {"t": t}).mappings().first()
    if cfg is None or not cfg["habilitado"] or not cfg["carpeta_id"]:
        raise ErrorDeDominio("Drive no está habilitado para este tenant", codigo="drive_no_habilitado")
    try:
        archivos = proveedor.listar(cfg["carpeta_id"])
    except ProveedorNoDisponible as e:
        raise ErrorDeDominio("No se pudo leer la carpeta de Drive", {"detalle": str(e)[:200]}, codigo="drive_no_disponible") from e
    r = {"vistos": len(archivos), "nuevos": 0, "importados": 0, "bandeja": 0, "ya_vistos": 0}
    eventos: list[str] = []
    for a in archivos:
        ya = session.execute(text("SELECT 1 FROM modulo1.archivo_drive WHERE tenant_id = :t AND id_externo = :i AND hash_externo IS NOT DISTINCT FROM :h"),
                             {"t": t, "i": a.id_externo, "h": a.hash}).first()
        if ya:
            r["ya_vistos"] += 1
            continue
        r["nuevos"] += 1
        confianza, ext, motivo = extraer(session, t, a)
        documento_id = None
        estado = "pendiente_revision"
        if confianza == "alta":
            try:
                documento_id = _importar(session, identidad, a, ext, proveedor, storage, eventos)
                estado = "importado"
                r["importados"] += 1
            except ErrorDeDominio as err:      # p. ej. contradice un dato verificado, archivo grande: a la bandeja
                motivo, confianza = f"{err.codigo}: {err.mensaje}", "media"
        if estado != "importado":
            r["bandeja"] += 1
        session.execute(text(
            "INSERT INTO modulo1.archivo_drive (tenant_id, id_externo, nombre, mime, modificado_externo, hash_externo, estado, confianza, extraccion, motivo, documento_id) "
            "VALUES (:t, :i, :n, :m, :mod, :h, :e, :c, CAST(:x AS jsonb), :mo, :d)"),
            {"t": t, "i": a.id_externo, "n": a.nombre, "m": a.mime, "mod": a.modificado, "h": a.hash, "e": estado, "c": confianza,
             "x": json.dumps(ext, default=str, ensure_ascii=False), "mo": motivo, "d": documento_id})
    session.execute(text("UPDATE modulo1.configuracion_drive SET ultimo_escaneo_en = :ahora, ultimo_escaneo_resultado = CAST(:r AS jsonb) WHERE tenant_id = :t"),
                    {"ahora": ahora or datetime.now().astimezone(), "r": json.dumps(r), "t": t})
    registrar_evento_interno(session, t, "DriveEscaneado", r, identidad.usuario_id)
    return {**r, "eventos": eventos + ["DriveEscaneado"]}


def escaneo_programado_pendiente(session: Session, tenant_id: str, ahora: datetime) -> bool:
    cfg = session.execute(text("SELECT habilitado, carpeta_id, intervalo_horas, ultimo_escaneo_en FROM modulo1.configuracion_drive WHERE tenant_id = :t"),
                          {"t": tenant_id}).mappings().first()
    if not cfg or not cfg["habilitado"] or not cfg["carpeta_id"] or not cfg["intervalo_horas"]:
        return False
    if cfg["ultimo_escaneo_en"] is None:
        return True
    return (ahora - cfg["ultimo_escaneo_en"]).total_seconds() >= cfg["intervalo_horas"] * 3600


# --------------------------------------------------------------------------- bandeja de excepciones


def bandeja(session: Session, identidad: Identidad, p: Pagina, estado: str | None = "pendiente_revision") -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.CONFIGURACION)
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = ""
    if estado:
        cond = " AND estado = :e"
        params["e"] = estado
    total = session.execute(text(f"SELECT count(*) FROM modulo1.archivo_drive WHERE tenant_id = :t{cond}"), params).scalar()
    filas = [{**dict(f), "archivo_drive_id": str(f["archivo_drive_id"]), "documento_id": str(f["documento_id"]) if f["documento_id"] else None}
             for f in session.execute(text(f"SELECT archivo_drive_id, id_externo, nombre, mime, modificado_externo, visto_en, estado, confianza, extraccion, motivo, documento_id, "
                                           f"resuelto_por, resuelto_en FROM modulo1.archivo_drive WHERE tenant_id = :t{cond} ORDER BY visto_en DESC OFFSET :off LIMIT :lim"),
                                      {**params, "off": p.offset, "lim": p.limit}).mappings()]
    return envolver(filas, int(total or 0), p)


def resolver(session: Session, identidad: Identidad, proveedor: ProveedorDeCarpeta, storage: Storage, *, archivo_drive_id: str, sujeto_id: str,
             requisito_definicion_id: str, vigente_desde: date, vigente_hasta: date) -> dict[str, Any]:
    """El responsable completa a mano lo que la extracción no pudo: importa el archivo como
    documento declarado con los datos indicados."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    f = session.execute(text("SELECT id_externo, nombre, mime, estado, hash_externo FROM modulo1.archivo_drive WHERE tenant_id = :t AND archivo_drive_id = :a FOR UPDATE"),
                        {"t": t, "a": archivo_drive_id}).mappings().first()
    if f is None:
        raise NoEncontrado("Archivo de Drive inexistente", {"archivo_drive_id": archivo_drive_id})
    if f["estado"] != "pendiente_revision":
        raise Conflicto("El archivo ya fue resuelto", {"estado": f["estado"]})
    eventos: list[str] = []
    archivo = ArchivoRemoto(f["id_externo"], f["nombre"], f["mime"], None, f["hash_externo"], None)
    ext = {"sujeto_id": sujeto_id, "requisito_definicion_id": requisito_definicion_id, "vigente_desde": vigente_desde.isoformat(), "vigente_hasta": vigente_hasta.isoformat()}
    documento_id = _importar(session, identidad, archivo, ext, proveedor, storage, eventos)
    session.execute(text("UPDATE modulo1.archivo_drive SET estado = 'importado', documento_id = :d, resuelto_por = :u, resuelto_en = now(), "
                         "extraccion = extraccion || CAST(:x AS jsonb) WHERE tenant_id = :t AND archivo_drive_id = :a"),
                    {"d": documento_id, "u": identidad.usuario_id, "x": json.dumps({"resuelto_a_mano": ext}), "t": t, "a": archivo_drive_id})
    return {"archivo_drive_id": archivo_drive_id, "documento_id": documento_id, "eventos": eventos}


def descartar(session: Session, identidad: Identidad, *, archivo_drive_id: str, motivo: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    n = session.execute(text("UPDATE modulo1.archivo_drive SET estado = 'descartado', motivo = COALESCE(:m, motivo), resuelto_por = :u, resuelto_en = now() "
                             "WHERE tenant_id = :t AND archivo_drive_id = :a AND estado = 'pendiente_revision' RETURNING archivo_drive_id"),
                        {"m": motivo, "u": identidad.usuario_id, "t": t, "a": archivo_drive_id}).rowcount
    if n != 1:
        raise NoEncontrado("Archivo de Drive inexistente o ya resuelto", {"archivo_drive_id": archivo_drive_id})
    return {"archivo_drive_id": archivo_drive_id, "eventos": []}
