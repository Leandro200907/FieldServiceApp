"""Estado interno versus la última versión conocida por cada operadora."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.comun.reloj import zona_horaria_del_tenant

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.alcance import alcance_de_sujetos
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.comun.paginacion import Pagina, envolver
from app.comun.reloj import hoy_del_tenant
from app.worker.cola import encolar


def _notificar(session: Session, tenant_id: str, alerta: dict[str, Any]) -> None:
    base = {
        "tipo": "DocumentoOperadoraDesactualizado",
        "prioridad": "alta",
        "alerta_id": str(alerta["alerta_id"]),
        "operadora": alerta["operadora"],
        "sujeto_id": alerta["sujeto_id"],
        "requisito": alerta["requisito"],
        "estado": alerta["estado"],
        "motivo": alerta["motivo"],
    }
    encolar(session, "notificaciones", {**base, "destinatario_rol": "responsable_legajos"}, tenant_id=tenant_id)
    supervisores = session.execute(text(
        "SELECT supervisor_usuario_id FROM modulo1.asignacion_supervisor "
        "WHERE tenant_id = :t AND sujeto_id = :s AND estado = 'vigente'"
    ), {"t": tenant_id, "s": alerta["sujeto_id"]}).scalars().all()
    for supervisor_id in supervisores:
        encolar(session, "notificaciones", {
            **base, "destinatario_rol": "supervisor", "destinatario_usuario_id": str(supervisor_id),
        }, tenant_id=tenant_id)


def _datos_alerta(session: Session, tenant_id: str, alerta_id: str) -> dict[str, Any]:
    fila = session.execute(text("""
        SELECT a.alerta_id, a.sujeto_id, a.estado, a.motivo, o.nombre AS operadora,
               COALESCE(r.nombre, a.requisito_definicion_id::text) AS requisito
        FROM modulo1.alerta_actualizacion_operadora a
        JOIN modulo1.operadora_documental o ON o.tenant_id = a.tenant_id AND o.operadora_id = a.operadora_id
        LEFT JOIN modulo1.definicion_requisito r ON r.tenant_id = a.tenant_id AND r.requisito_definicion_id = a.requisito_definicion_id
        WHERE a.tenant_id = :t AND a.alerta_id = :a
    """), {"t": tenant_id, "a": alerta_id}).mappings().one()
    return dict(fila)


def reconciliar(session: Session, identidad: Identidad, *, operadora_id: str, sujeto_id: str,
                requisito_definicion_id: str) -> dict[str, Any] | None:
    """Abre/actualiza/cierra una alerta para la versión interna vigente."""
    t = identidad.tenant_id
    vigente = session.execute(text(
        "SELECT documento_id FROM modulo1.documento WHERE tenant_id = :t AND sujeto_id = :s "
        "AND requisito_definicion_id = :r AND estado_version = 'vigente'"
    ), {"t": t, "s": sujeto_id, "r": requisito_definicion_id}).scalar()
    if vigente is None:
        return None

    entrega_actual = session.execute(text("""
        SELECT documento_id, estado FROM modulo1.entrega_documento_operadora
        WHERE tenant_id = :t AND operadora_id = :o AND documento_id = :d
    """), {"t": t, "o": operadora_id, "d": str(vigente)}).mappings().first()
    ultimo = session.execute(text("""
        SELECT documento_id, estado FROM modulo1.entrega_documento_operadora
        WHERE tenant_id = :t AND operadora_id = :o AND sujeto_id = :s AND requisito_definicion_id = :r
        ORDER BY actualizado_en DESC, creado_en DESC LIMIT 1
    """), {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id}).mappings().first()

    if entrega_actual and entrega_actual["estado"] == "aceptado":
        session.execute(text("""
            UPDATE modulo1.alerta_actualizacion_operadora
            SET estado = 'resuelta', resuelta_en = now(), actualizada_en = now(), motivo = 'La operadora aceptó la versión interna vigente.'
            WHERE tenant_id = :t AND operadora_id = :o AND sujeto_id = :s
              AND requisito_definicion_id = :r AND estado <> 'resuelta'
        """), {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id})
        return None

    if entrega_actual and entrega_actual["estado"] == "rechazado":
        estado, motivo = "rechazado", "La operadora rechazó la versión interna vigente."
    elif entrega_actual:
        estado, motivo = "pendiente_aceptacion", "La versión interna vigente fue enviada/exportada y aún no fue aceptada."
    else:
        estado, motivo = "pendiente_envio", "La operadora no recibió la versión interna vigente."

    session.execute(text("""
        UPDATE modulo1.alerta_actualizacion_operadora SET estado = 'resuelta', resuelta_en = now(), actualizada_en = now(),
               motivo = 'Reemplazada por una versión interna posterior.'
        WHERE tenant_id = :t AND operadora_id = :o AND sujeto_id = :s AND requisito_definicion_id = :r
          AND documento_vigente_id <> :d AND estado <> 'resuelta'
    """), {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id, "d": str(vigente)})

    anterior = session.execute(text("""
        SELECT alerta_id, estado FROM modulo1.alerta_actualizacion_operadora
        WHERE tenant_id = :t AND operadora_id = :o AND sujeto_id = :s
          AND requisito_definicion_id = :r AND documento_vigente_id = :d
        FOR UPDATE
    """), {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id, "d": str(vigente)}).mappings().first()
    fila = session.execute(text("""
        INSERT INTO modulo1.alerta_actualizacion_operadora
            (tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_vigente_id,
             ultimo_documento_operadora_id, estado, motivo)
        VALUES (:t, :o, :s, :r, :d, :u, :e, :m)
        ON CONFLICT (tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_vigente_id)
        DO UPDATE SET ultimo_documento_operadora_id = EXCLUDED.ultimo_documento_operadora_id,
                      estado = EXCLUDED.estado, motivo = EXCLUDED.motivo, actualizada_en = now(), resuelta_en = NULL
        RETURNING alerta_id
    """), {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id,
             "d": str(vigente), "u": str(ultimo["documento_id"]) if ultimo else None, "e": estado, "m": motivo}).scalar_one()
    if anterior is None or anterior["estado"] != estado:
        datos = _datos_alerta(session, t, str(fila))
        _notificar(session, t, datos)
        registrar_evento_interno(session, t, "ActualizacionOperadoraRequerida", datos, identidad.usuario_id)
    return _datos_alerta(session, t, str(fila))


def al_registrar_nueva_version(session: Session, identidad: Identidad, *, sujeto_id: str,
                               requisito_definicion_id: str) -> None:
    operadoras = session.execute(text(
        "SELECT operadora_id FROM modulo1.operadora_legajo WHERE tenant_id = :t AND sujeto_id = :s"
    ), {"t": identidad.tenant_id, "s": sujeto_id}).scalars().all()
    for operadora_id in operadoras:
        reconciliar(session, identidad, operadora_id=str(operadora_id), sujeto_id=sujeto_id,
                    requisito_definicion_id=requisito_definicion_id)


def registrar_estado(session: Session, identidad: Identidad, *, operadora: str, sujeto_id: str,
                     documento_id: str, estado: str, exportado_en: datetime | None = None,
                     enviado_en: datetime | None = None, aceptado_en: datetime | None = None,
                     rechazado_en: datetime | None = None, fuente_archivo: str | None = None,
                     fuente_hoja: str | None = None, fuente_fila: int | None = None,
                     observacion: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    doc = session.execute(text("""
        SELECT sujeto_id, requisito_definicion_id FROM modulo1.documento
        WHERE tenant_id = :t AND documento_id = :d
    """), {"t": t, "d": documento_id}).mappings().first()
    if doc is None:
        raise NoEncontrado("Documento inexistente", {"documento_id": documento_id})
    if doc["sujeto_id"] != sujeto_id:
        raise Prohibido("El documento no pertenece al legajo indicado")
    operadora_id = session.execute(text("""
        INSERT INTO modulo1.operadora_documental (tenant_id, nombre) VALUES (:t, :n)
        ON CONFLICT (tenant_id, lower(nombre)) DO UPDATE SET nombre = EXCLUDED.nombre, activa = true
        RETURNING operadora_id
    """), {"t": t, "n": operadora.strip()}).scalar_one()
    session.execute(text("""
        INSERT INTO modulo1.operadora_legajo (tenant_id, operadora_id, sujeto_id, fuente)
        VALUES (:t, :o, :s, 'planilla') ON CONFLICT DO NOTHING
    """), {"t": t, "o": str(operadora_id), "s": sujeto_id})
    session.execute(text("""
        INSERT INTO modulo1.entrega_documento_operadora
            (tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_id, estado,
             exportado_en, enviado_en, aceptado_en, rechazado_en, fuente_archivo, fuente_hoja,
             fuente_fila, observacion, actualizado_por)
        VALUES (:t, :o, :s, :r, :d, :e, :ex, :en, :ac, :re, :fa, :fh, :ff, :obs, :u)
        ON CONFLICT (tenant_id, operadora_id, documento_id) DO UPDATE SET
            estado = EXCLUDED.estado, exportado_en = COALESCE(EXCLUDED.exportado_en, modulo1.entrega_documento_operadora.exportado_en),
            enviado_en = COALESCE(EXCLUDED.enviado_en, modulo1.entrega_documento_operadora.enviado_en),
            aceptado_en = COALESCE(EXCLUDED.aceptado_en, modulo1.entrega_documento_operadora.aceptado_en),
            rechazado_en = COALESCE(EXCLUDED.rechazado_en, modulo1.entrega_documento_operadora.rechazado_en),
            fuente_archivo = COALESCE(EXCLUDED.fuente_archivo, modulo1.entrega_documento_operadora.fuente_archivo),
            fuente_hoja = COALESCE(EXCLUDED.fuente_hoja, modulo1.entrega_documento_operadora.fuente_hoja),
            fuente_fila = COALESCE(EXCLUDED.fuente_fila, modulo1.entrega_documento_operadora.fuente_fila),
            observacion = EXCLUDED.observacion, actualizado_por = EXCLUDED.actualizado_por, actualizado_en = now()
    """), {"t": t, "o": str(operadora_id), "s": sujeto_id, "r": str(doc["requisito_definicion_id"]),
             "d": documento_id, "e": estado, "ex": exportado_en, "en": enviado_en,
             "ac": aceptado_en, "re": rechazado_en, "fa": fuente_archivo, "fh": fuente_hoja,
             "ff": fuente_fila, "obs": observacion, "u": identidad.usuario_id})
    registrar_evento_interno(session, t, "EstadoDocumentoOperadoraRegistrado", {
        "operadora_id": str(operadora_id), "operadora": operadora, "sujeto_id": sujeto_id,
        "documento_id": documento_id, "estado": estado, "fuente_archivo": fuente_archivo,
        "fuente_hoja": fuente_hoja, "fuente_fila": fuente_fila,
    }, identidad.usuario_id)
    alerta = reconciliar(session, identidad, operadora_id=str(operadora_id), sujeto_id=sujeto_id,
                        requisito_definicion_id=str(doc["requisito_definicion_id"]))
    return {"operadora_id": str(operadora_id), "documento_id": documento_id, "estado": estado,
            "alerta": alerta, "eventos": ["EstadoDocumentoOperadoraRegistrado"]}


def _resolver_documento_planilla(session: Session, identidad: Identidad, fila: dict[str, Any]) -> tuple[str, str]:
    t = identidad.tenant_id
    sujeto_id = str(fila.get("sujeto_id") or "").strip()
    tipo_sujeto = str(fila.get("tipo_sujeto") or "").strip().lower()
    identificador = str(fila.get("identificador_sujeto") or "").strip()
    if tipo_sujeto not in {"empresa", "persona", "vehiculo", "equipo"}:
        raise ErrorDeDominio("Tipo de sujeto inválido", {"tipo_sujeto": tipo_sujeto})
    if not identificador:
        raise ErrorDeDominio("Falta el identificador del sujeto")
    sujetos = session.execute(text("""
        SELECT sujeto_id FROM modulo1.legajo
        WHERE tenant_id = :t AND tipo_sujeto = :tipo
          AND lower(trim(identificador_natural)) = lower(trim(:ident))
          AND dado_de_baja_en IS NULL
    """), {"t": t, "tipo": tipo_sujeto, "ident": identificador}).scalars().all()
    if sujeto_id:
        if sujeto_id not in {str(s) for s in sujetos}:
            raise ErrorDeDominio("El Sujeto ID no coincide con el tipo e identificador informados")
    elif len(sujetos) == 1:
        sujeto_id = str(sujetos[0])
    elif not sujetos:
        raise NoEncontrado("No existe un legajo activo para el sujeto informado")
    else:
        raise ErrorDeDominio("El sujeto es ambiguo; complete Sujeto ID")

    documento_id = str(fila.get("documento_id") or "").strip()
    if documento_id:
        try:
            uuid.UUID(documento_id)
        except ValueError as exc:
            raise ErrorDeDominio("Documento ID inválido", {"documento_id": documento_id}) from exc
    requisito_id = str(fila.get("requisito_id") or "").strip()
    tipo_documento = str(fila.get("tipo_documento") or "").strip()
    if not tipo_documento:
        raise ErrorDeDominio("Falta el tipo de documento")
    parametros: dict[str, Any] = {"t": t, "s": sujeto_id, "nombre": tipo_documento}
    condiciones = [
        "d.tenant_id = :t", "d.sujeto_id = :s", "d.estado_version = 'vigente'",
        "lower(trim(r.nombre)) = lower(trim(:nombre))",
    ]
    if documento_id:
        parametros["d"] = documento_id; condiciones.append("d.documento_id = :d")
    if requisito_id:
        try:
            uuid.UUID(requisito_id)
        except ValueError as exc:
            raise ErrorDeDominio("Requisito ID inválido", {"requisito_id": requisito_id}) from exc
        parametros["r"] = requisito_id
        condiciones.append("d.requisito_definicion_id = :r")
    if fila.get("fecha_emision") is not None:
        parametros["desde"] = fila["fecha_emision"]; condiciones.append("d.vigente_desde = :desde")
    if fila.get("fecha_vencimiento") is not None:
        parametros["hasta"] = fila["fecha_vencimiento"]; condiciones.append("d.vigente_hasta = :hasta")
    documentos = session.execute(text(f"""
        SELECT d.documento_id FROM modulo1.documento d
        JOIN modulo1.definicion_requisito r
          ON r.tenant_id = d.tenant_id AND r.requisito_definicion_id = d.requisito_definicion_id
        WHERE {' AND '.join(condiciones)}
    """), parametros).scalars().all()
    if not documentos:
        raise NoEncontrado("No se encontró la versión documental vigente indicada por la fila")
    if len(documentos) > 1:
        raise ErrorDeDominio("El documento es ambiguo; complete Documento ID o Requisito ID")
    return sujeto_id, str(documentos[0])


def _instante_en_zona_tenant(session: Session, tenant_id: str, valor: datetime | None) -> datetime | None:
    if valor is None:
        return None
    tz = ZoneInfo(zona_horaria_del_tenant(session, tenant_id))
    if valor.tzinfo is None:
        return valor.replace(tzinfo=tz)
    return valor.astimezone(tz)


def importar_filas(session: Session, identidad: Identidad, *, archivo: str, hoja: str,
                   filas: list[dict[str, Any]], errores_lectura: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Importa filas de forma parcial: una fila inválida no revierte las correctas."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    resultados: list[dict[str, Any]] = []
    errores: list[dict[str, Any]] = list(errores_lectura or [])
    t = identidad.tenant_id
    for fila in filas:
        numero = int(fila["fila"])
        try:
            with session.begin_nested():
                estado = str(fila.get("estado") or "").strip().lower()
                if estado not in {"exportado", "enviado", "aceptado", "rechazado"}:
                    raise ErrorDeDominio("Estado inválido", {"estado": estado})
                if estado == "exportado" and fila.get("fecha_exportacion") is None:
                    raise ErrorDeDominio("El estado exportado requiere Fecha de exportación")
                if estado in {"enviado", "aceptado", "rechazado"} and fila.get("fecha_presentacion") is None:
                    raise ErrorDeDominio("El estado requiere Fecha de presentación")
                if estado in {"aceptado", "rechazado"} and fila.get("fecha_respuesta") is None:
                    raise ErrorDeDominio("El estado requiere Fecha de respuesta")
                sujeto_id, documento_id = _resolver_documento_planilla(session, identidad, fila)
                respuesta = registrar_estado(
                    session, identidad, operadora=str(fila.get("operadora") or "").strip(),
                    sujeto_id=sujeto_id, documento_id=documento_id, estado=estado,
                    exportado_en=_instante_en_zona_tenant(session, t, fila.get("fecha_exportacion")),
                    enviado_en=_instante_en_zona_tenant(session, t, fila.get("fecha_presentacion")),
                    aceptado_en=_instante_en_zona_tenant(session, t, fila.get("fecha_respuesta") if estado == "aceptado" else None),
                    rechazado_en=_instante_en_zona_tenant(session, t, fila.get("fecha_respuesta") if estado == "rechazado" else None),
                    fuente_archivo=archivo, fuente_hoja=hoja, fuente_fila=numero,
                    observacion=str(fila.get("observacion") or "").strip() or None,
                )
                resultados.append({"fila": numero, "documento_id": documento_id,
                                   "operadora_id": respuesta["operadora_id"], "estado": estado})
        except (ErrorDeDominio, NoEncontrado) as exc:
            errores.append({"fila": numero, "codigo": exc.codigo, "mensaje": exc.mensaje,
                            "detalles": exc.detalles})
        except DBAPIError as exc:
            errores.append({"fila": numero, "codigo": "dato_invalido", "mensaje": "Identificador con formato inválido",
                            "detalles": {"causa": str(exc.orig) if exc.orig else None}})
    registrar_evento_interno(session, identidad.tenant_id, "PlanillaOperadorasImportada", {
        "archivo": archivo, "hoja": hoja, "filas_totales": len(filas),
        "filas_aceptadas": len(resultados), "filas_rechazadas": len(errores),
    }, identidad.usuario_id)
    total_filas = len(filas) + len(errores_lectura or [])
    return {"archivo": archivo, "hoja": hoja, "filas_totales": total_filas,
            "filas_aceptadas": len(resultados), "filas_rechazadas": len(errores),
            "resultados": resultados, "errores": errores,
            "eventos": ["PlanillaOperadorasImportada"]}


def alertas(session: Session, identidad: Identidad, p: Pagina, *, sujeto_id: str | None = None,
            estado: str | None = None) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    alcance = alcance_de_sujetos(session, identidad, hoy_del_tenant(session, identidad.tenant_id))
    params: dict[str, Any] = {"t": identidad.tenant_id}
    cond = ["a.tenant_id = :t", "a.estado <> 'resuelta'"]
    if alcance is not None:
        params["alcance"] = list(alcance); cond.append("a.sujeto_id = ANY(CAST(:alcance AS text[]))")
    if sujeto_id:
        params["s"] = sujeto_id; cond.append("a.sujeto_id = :s")
    if estado:
        params["e"] = estado; cond.append("a.estado = :e")
    desde = " AND ".join(cond)
    total = session.execute(text(f"SELECT count(*) FROM modulo1.alerta_actualizacion_operadora a WHERE {desde}"), params).scalar()
    filas = session.execute(text(f"""
        SELECT a.alerta_id, a.sujeto_id, l.identificador_natural, a.requisito_definicion_id,
               COALESCE(r.nombre, a.requisito_definicion_id::text) AS requisito, o.operadora_id,
               o.nombre AS operadora, a.documento_vigente_id, a.ultimo_documento_operadora_id,
               a.estado, a.motivo, a.abierta_en, a.actualizada_en
        FROM modulo1.alerta_actualizacion_operadora a
        JOIN modulo1.operadora_documental o ON o.tenant_id = a.tenant_id AND o.operadora_id = a.operadora_id
        JOIN modulo1.legajo l ON l.tenant_id = a.tenant_id AND l.sujeto_id = a.sujeto_id
        LEFT JOIN modulo1.definicion_requisito r ON r.tenant_id = a.tenant_id AND r.requisito_definicion_id = a.requisito_definicion_id
        WHERE {desde} ORDER BY a.actualizada_en DESC OFFSET :off LIMIT :lim
    """), {**params, "off": p.offset, "lim": p.limit}).mappings().all()
    return envolver([{k: str(v) if k.endswith("_id") and v is not None else v for k, v in dict(f).items()} for f in filas], int(total or 0), p)

