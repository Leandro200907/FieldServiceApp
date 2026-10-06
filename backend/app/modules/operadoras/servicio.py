"""Estado interno versus la última versión conocida por cada operadora."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.comun.reloj import ahora_utc, hoy_del_tenant, zona_horaria_del_tenant

from app.api.errores import ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.alcance import alcance_de_sujetos
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.comun.paginacion import Pagina, envolver
from app.modules.oc.catalogos_maestros import resolver_operadora
from app.comun.importacion_filas import ordenar_por_fila
from app.modules.operadoras.esquemas import validar_campos_planilla
from app.worker.cola import encolar


def _operadora_desde_catalogo(session: Session, tenant_id: str, nombre: str) -> str:
    nombre = nombre.strip()
    if not nombre:
        raise ErrorDeDominio("La operadora es obligatoria", codigo="fila_invalida")
    operadora_id, err = resolver_operadora(session, tenant_id, nombre)
    if operadora_id:
        return operadora_id
    mensaje = f"La operadora '{nombre}' no está en el catálogo"
    sugerencia = None
    if err:
        coincidencia = re.search(r"¿quisiste decir ([^?]+)\?", err)
        if coincidencia:
            sugerencia = coincidencia.group(1).strip().rstrip("?")
            primer = sugerencia.split(",")[0].strip()
            mensaje = f"{mensaje}. ¿Quisiste decir {primer}?"
    raise ErrorDeDominio(mensaje, {"operadora": nombre, "sugerencia": sugerencia}, codigo="operadora_inexistente")


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


_CAMPO_FECHA_ENTREGA = {
    "exportado": "exportado_en",
    "enviado": "enviado_en",
    "aceptado": "aceptado_en",
    "rechazado": "rechazado_en",
}


def _instante_paso(
    estado: str,
    *,
    exportado_en: datetime | None,
    enviado_en: datetime | None,
    aceptado_en: datetime | None,
    rechazado_en: datetime | None,
) -> datetime:
    por_estado = {
        "exportado": exportado_en,
        "enviado": enviado_en,
        "aceptado": aceptado_en,
        "rechazado": rechazado_en,
    }
    valor = por_estado.get(estado)
    if valor is not None:
        return valor
    return ahora_utc()


def _entrega_sin_cambios(
    actual: dict[str, Any] | None,
    *,
    estado: str,
    exportado_en: datetime | None,
    enviado_en: datetime | None,
    aceptado_en: datetime | None,
    rechazado_en: datetime | None,
    observacion: str | None,
) -> bool:
    if actual is None:
        return False
    if str(actual.get("estado") or "") != estado:
        return False
    if (actual.get("observacion") or None) != (observacion or None):
        return False
    pares = (
        ("exportado_en", exportado_en),
        ("enviado_en", enviado_en),
        ("aceptado_en", aceptado_en),
        ("rechazado_en", rechazado_en),
    )
    for campo, nuevo in pares:
        if actual.get(campo) != nuevo:
            return False
    return True


def _movimiento_historial_duplicado(
    session: Session,
    tenant_id: str,
    *,
    operadora_id: str,
    documento_id: str,
    estado: str,
    paso_en: datetime,
) -> bool:
    """E-29: idempotencia por historial (mismo doc, operadora, estado y fecha del paso)."""
    return (
        session.execute(
            text(
                """
                SELECT 1 FROM modulo1.movimiento_entrega_operadora
                WHERE tenant_id = :t AND operadora_id = :o AND documento_id = :d
                  AND estado = :e AND paso_en = :p
                LIMIT 1
                """
            ),
            {
                "t": tenant_id,
                "o": operadora_id,
                "d": documento_id,
                "e": estado,
                "p": paso_en,
            },
        ).scalar()
        is not None
    )


def _movimiento_planilla_duplicado(
    session: Session,
    tenant_id: str,
    *,
    operadora_id: str,
    documento_id: str,
    estado: str,
    fuente_archivo: str | None,
    fuente_hoja: str | None,
    fuente_fila: int | None,
) -> bool:
    if not fuente_archivo or fuente_fila is None:
        return False
    return (
        session.execute(
            text(
                """
                SELECT 1 FROM modulo1.movimiento_entrega_operadora
                WHERE tenant_id = :t AND operadora_id = :o AND documento_id = :d AND estado = :e
                  AND fuente_archivo = :fa AND fuente_hoja IS NOT DISTINCT FROM :fh AND fuente_fila = :ff
                LIMIT 1
                """
            ),
            {
                "t": tenant_id,
                "o": operadora_id,
                "d": documento_id,
                "e": estado,
                "fa": fuente_archivo,
                "fh": fuente_hoja,
                "ff": fuente_fila,
            },
        ).scalar()
        is not None
    )


def _texto_paso_en(
    estado: str,
    entrega: dict[str, Any] | None,
    paso_en: datetime,
    tz: ZoneInfo,
) -> str:
    """E-30: sin timestamp de dominio → «fecha no informada»."""
    if entrega is not None:
        campo = _CAMPO_FECHA_ENTREGA.get(estado)
        if campo and entrega.get(campo) is None:
            return "fecha no informada"
    if isinstance(paso_en, datetime):
        return paso_en.astimezone(tz).isoformat()
    return str(paso_en)


def _registrar_movimiento(
    session: Session,
    tenant_id: str,
    *,
    operadora_id: str,
    sujeto_id: str,
    requisito_definicion_id: str,
    documento_id: str,
    estado: str,
    paso_en: datetime,
    observacion: str | None,
    registrado_por: str,
    fuente_archivo: str | None,
    fuente_hoja: str | None,
    fuente_fila: int | None,
) -> None:
    origen = "planilla" if fuente_archivo else "manual"
    session.execute(
        text("""
            INSERT INTO modulo1.movimiento_entrega_operadora (
                tenant_id, operadora_id, sujeto_id, requisito_definicion_id, documento_id,
                estado, paso_en, observacion, registrado_por, origen,
                fuente_archivo, fuente_hoja, fuente_fila
            ) VALUES (
                :t, :o, :s, :r, :d, :e, :p, :obs, :u, :origen, :fa, :fh, :ff
            )
        """),
        {
            "t": tenant_id,
            "o": operadora_id,
            "s": sujeto_id,
            "r": requisito_definicion_id,
            "d": documento_id,
            "e": estado,
            "p": paso_en,
            "obs": observacion,
            "u": registrado_por,
            "origen": origen,
            "fa": fuente_archivo,
            "fh": fuente_hoja,
            "ff": fuente_fila,
        },
    )


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
                     observacion: str | None = None, operadora_id: str | None = None) -> dict[str, Any]:
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
    if operadora_id is None:
        operadora_id = session.execute(text("""
            INSERT INTO modulo1.operadora_documental (tenant_id, nombre) VALUES (:t, :n)
            ON CONFLICT (tenant_id, lower(nombre)) DO UPDATE SET nombre = EXCLUDED.nombre, activa = true
            RETURNING operadora_id
        """), {"t": t, "n": operadora.strip()}).scalar_one()
    elif session.execute(
        text("SELECT 1 FROM modulo1.operadora_documental WHERE tenant_id = :t AND operadora_id = CAST(:o AS uuid)"),
        {"t": t, "o": operadora_id},
    ).scalar() is None:
        raise NoEncontrado("Operadora inexistente en el catálogo", {"operadora_id": operadora_id})
    entrega_prev = session.execute(
        text(
            """
            SELECT estado, exportado_en, enviado_en, aceptado_en, rechazado_en, observacion
            FROM modulo1.entrega_documento_operadora
            WHERE tenant_id = :t AND operadora_id = :o AND documento_id = :d
            """
        ),
        {"t": t, "o": str(operadora_id), "d": documento_id},
    ).mappings().first()
    sin_cambios = _entrega_sin_cambios(
        dict(entrega_prev) if entrega_prev else None,
        estado=estado,
        exportado_en=exportado_en,
        enviado_en=enviado_en,
        aceptado_en=aceptado_en,
        rechazado_en=rechazado_en,
        observacion=observacion,
    )
    paso_en = _instante_paso(
        estado,
        exportado_en=exportado_en,
        enviado_en=enviado_en,
        aceptado_en=aceptado_en,
        rechazado_en=rechazado_en,
    )
    movimiento_duplicado = _movimiento_planilla_duplicado(
        session,
        t,
        operadora_id=str(operadora_id),
        documento_id=documento_id,
        estado=estado,
        fuente_archivo=fuente_archivo,
        fuente_hoja=fuente_hoja,
        fuente_fila=fuente_fila,
    )
    historial_duplicado = _movimiento_historial_duplicado(
        session,
        t,
        operadora_id=str(operadora_id),
        documento_id=documento_id,
        estado=estado,
        paso_en=paso_en,
    )
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
    omitir_movimiento = historial_duplicado or (
        sin_cambios and (movimiento_duplicado or fuente_archivo is None)
    )
    if not omitir_movimiento:
        _registrar_movimiento(
            session,
            t,
            operadora_id=str(operadora_id),
            sujeto_id=sujeto_id,
            requisito_definicion_id=str(doc["requisito_definicion_id"]),
            documento_id=documento_id,
            estado=estado,
            paso_en=paso_en,
            observacion=observacion,
            registrado_por=identidad.usuario_id,
            fuente_archivo=fuente_archivo,
            fuente_hoja=fuente_hoja,
            fuente_fila=fuente_fila,
        )
    if not sin_cambios:
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
                validar_campos_planilla(fila)
                estado = str(fila.get("estado") or "").strip().lower()
                if estado not in {"exportado", "enviado", "aceptado", "rechazado"}:
                    raise ErrorDeDominio(
                        f"Fila {numero}, Estado: '{estado or ''}' no es válido "
                        f"(valores aceptados: exportado, enviado, aceptado, rechazado)",
                        {"estado": estado},
                        codigo="estado_invalido",
                    )
                if estado == "exportado" and fila.get("fecha_exportacion") is None:
                    raise ErrorDeDominio("El estado exportado requiere Fecha de exportación")
                if estado in {"enviado", "aceptado", "rechazado"} and fila.get("fecha_presentacion") is None:
                    raise ErrorDeDominio("El estado requiere Fecha de presentación")
                if estado in {"aceptado", "rechazado"} and fila.get("fecha_respuesta") is None:
                    raise ErrorDeDominio("El estado requiere Fecha de respuesta")
                sujeto_id, documento_id = _resolver_documento_planilla(session, identidad, fila)
                operadora_nombre = str(fila.get("operadora") or "").strip()
                operadora_id = _operadora_desde_catalogo(session, t, operadora_nombre)
                respuesta = registrar_estado(
                    session, identidad, operadora=operadora_nombre, operadora_id=operadora_id,
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
    errores = ordenar_por_fila(errores)
    total_filas = len(filas) + len(errores_lectura or [])
    registrar_evento_interno(session, identidad.tenant_id, "PlanillaOperadorasImportada", {
        "archivo": archivo, "hoja": hoja, "filas_totales": total_filas,
        "filas_aceptadas": len(resultados), "filas_rechazadas": len(errores),
    }, identidad.usuario_id)
    from app.modules.operadoras.router import ImportarPlanillaOperadorasResponse

    payload = {"archivo": archivo, "hoja": hoja, "filas_totales": total_filas,
               "filas_aceptadas": len(resultados), "filas_rechazadas": len(errores),
               "resultados": resultados, "errores": errores,
               "eventos": ["PlanillaOperadorasImportada"]}
    ImportarPlanillaOperadorasResponse.model_validate(payload)
    return payload


def _exigir_sujeto_en_alcance(session: Session, identidad: Identidad, sujeto_id: str) -> None:
    alcance = alcance_de_sujetos(session, identidad, hoy_del_tenant(session, identidad.tenant_id))
    if alcance is not None and sujeto_id not in alcance:
        raise Prohibido("Recurso fuera del alcance del supervisor")


def historial_operadora(
    session: Session,
    identidad: Identidad,
    *,
    operadora_id: str,
    sujeto_id: str,
    requisito_definicion_id: str,
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    _exigir_sujeto_en_alcance(session, identidad, sujeto_id)
    t = identidad.tenant_id
    tz = ZoneInfo(zona_horaria_del_tenant(session, t))
    entregas = {
        str(f["documento_id"]): dict(f)
        for f in session.execute(
            text(
                """
                SELECT documento_id::text, exportado_en, enviado_en, aceptado_en, rechazado_en
                FROM modulo1.entrega_documento_operadora
                WHERE tenant_id = :t AND operadora_id = :o AND sujeto_id = :s
                  AND requisito_definicion_id = :r
                """
            ),
            {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id},
        ).mappings().all()
    }
    filas = session.execute(
        text("""
            SELECT m.documento_id, m.estado, m.paso_en, m.observacion, m.registrado_por, m.origen,
                   m.fuente_archivo, m.fuente_hoja, m.fuente_fila,
                   d.vigente_desde, d.vigente_hasta,
                   COALESCE(u.nombre, m.registrado_por) AS registrado_nombre
            FROM modulo1.movimiento_entrega_operadora m
            JOIN modulo1.documento d
              ON d.tenant_id = m.tenant_id AND d.documento_id = m.documento_id
            LEFT JOIN modulo1.usuario u
              ON u.tenant_id = m.tenant_id AND u.usuario_id::text = m.registrado_por
            WHERE m.tenant_id = :t AND m.operadora_id = :o AND m.sujeto_id = :s
              AND m.requisito_definicion_id = :r
            ORDER BY d.vigente_desde DESC, m.paso_en ASC, m.creado_en ASC
        """),
        {"t": t, "o": operadora_id, "s": sujeto_id, "r": requisito_definicion_id},
    ).mappings().all()
    versiones: dict[str, dict[str, Any]] = {}
    orden: list[str] = []
    for fila in filas:
        doc_id = str(fila["documento_id"])
        if doc_id not in versiones:
            versiones[doc_id] = {
                "documento_id": doc_id,
                "vigente_desde": str(fila["vigente_desde"]),
                "vigente_hasta": str(fila["vigente_hasta"]),
                "pasos": [],
            }
            orden.append(doc_id)
        paso_en_raw = fila["paso_en"]
        entrega = entregas.get(doc_id)
        paso_en = _texto_paso_en(str(fila["estado"]), entrega, paso_en_raw, tz)
        versiones[doc_id]["pasos"].append({
            "estado": fila["estado"],
            "paso_en": paso_en,
            "observacion": fila["observacion"],
            "registrado_por": fila["registrado_por"],
            "registrado_nombre": fila["registrado_nombre"],
            "origen": fila["origen"],
            "fuente_archivo": fila["fuente_archivo"],
            "fuente_hoja": fila["fuente_hoja"],
            "fuente_fila": fila["fuente_fila"],
        })
    return {
        "operadora_id": operadora_id,
        "sujeto_id": sujeto_id,
        "requisito_definicion_id": requisito_definicion_id,
        "versiones": [versiones[doc_id] for doc_id in orden],
    }


def listar_espejo_operadora(
    session: Session,
    identidad: Identidad,
    p: Pagina,
    *,
    operadora_id: list[str] | None = None,
    requisito_definicion_id: list[str] | None = None,
    tipo_sujeto: str | None = None,
    q: str | None = None,
    estado_operadora: list[str] | None = None,
    movimiento_desde: date | None = None,
    movimiento_hasta: date | None = None,
    mes: str | None = None,
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS, Rol.SUPERVISOR)
    t = identidad.tenant_id
    alcance = alcance_de_sujetos(session, identidad, hoy_del_tenant(session, t))
    params: dict[str, Any] = {"t": t}
    cond_alertas = ["a.tenant_id = :t", "a.estado <> 'resuelta'"]
    cond_al_dia = ["e.tenant_id = :t", "e.estado = 'aceptado'"]
    if alcance is not None:
        params["alcance"] = list(alcance)
        cond_alertas.append("a.sujeto_id = ANY(CAST(:alcance AS text[]))")
        cond_al_dia.append("e.sujeto_id = ANY(CAST(:alcance AS text[]))")
    if operadora_id:
        params["operadoras"] = operadora_id
        cond_alertas.append("a.operadora_id = ANY(CAST(:operadoras AS uuid[]))")
        cond_al_dia.append("e.operadora_id = ANY(CAST(:operadoras AS uuid[]))")
    if requisito_definicion_id:
        params["requisitos"] = requisito_definicion_id
        cond_alertas.append("a.requisito_definicion_id = ANY(CAST(:requisitos AS uuid[]))")
        cond_al_dia.append("e.requisito_definicion_id = ANY(CAST(:requisitos AS uuid[]))")
    if tipo_sujeto:
        params["tipo_sujeto"] = tipo_sujeto
        cond_alertas.append("l.tipo_sujeto = :tipo_sujeto")
        cond_al_dia.append("l.tipo_sujeto = :tipo_sujeto")
    if q:
        params["q"] = f"%{q.strip()}%"
        cond_alertas.append(
            "(l.identificador_natural ILIKE :q OR l.sujeto_id ILIKE :q OR l.nombre_apellido ILIKE :q)"
        )
        cond_al_dia.append(
            "(l.identificador_natural ILIKE :q OR l.sujeto_id ILIKE :q OR l.nombre_apellido ILIKE :q)"
        )
    if estado_operadora:
        alerta_est = [e for e in estado_operadora if e != "al_dia"]
        if alerta_est:
            params["estados_espejo"] = alerta_est
    cond_al_dia.extend([
        "EXISTS (SELECT 1 FROM modulo1.documento d WHERE d.tenant_id = e.tenant_id "
        "AND d.sujeto_id = e.sujeto_id AND d.requisito_definicion_id = e.requisito_definicion_id "
        "AND d.estado_version = 'vigente' AND d.documento_id = e.documento_id)",
        "NOT EXISTS (SELECT 1 FROM modulo1.alerta_actualizacion_operadora ax "
        "WHERE ax.tenant_id = e.tenant_id AND ax.operadora_id = e.operadora_id "
        "AND ax.sujeto_id = e.sujeto_id AND ax.requisito_definicion_id = e.requisito_definicion_id "
        "AND ax.estado <> 'resuelta')",
    ])

    if mes:
        params["mes"] = mes
        filtro_fecha = "date_trunc('month', ultimo_movimiento_en) = CAST(:mes || '-01' AS date)"
    elif movimiento_desde or movimiento_hasta:
        filtros_f: list[str] = []
        if movimiento_desde:
            params["mov_desde"] = movimiento_desde
            filtros_f.append("ultimo_movimiento_en::date >= :mov_desde")
        if movimiento_hasta:
            params["mov_hasta"] = movimiento_hasta
            filtros_f.append("ultimo_movimiento_en::date <= :mov_hasta")
        filtro_fecha = " AND ".join(filtros_f)
    else:
        filtro_fecha = "TRUE"

    sql = _construir_espejo_sql(cond_alertas, cond_al_dia, estado_operadora, filtro_fecha)
    total = session.execute(text(f"SELECT count(*) FROM ({sql}) sub"), params).scalar()
    filas = session.execute(
        text(f"{sql} ORDER BY ultimo_movimiento_en DESC OFFSET :off LIMIT :lim"),
        {**params, "off": p.offset, "lim": p.limit},
    ).mappings().all()
    items = []
    for fila in filas:
        item = {k: str(v) if k.endswith("_id") and v is not None else v for k, v in dict(fila).items()}
        items.append(item)
    return envolver(items, int(total or 0), p)


def _construir_espejo_sql(
    cond_alertas: list[str],
    cond_al_dia: list[str],
    estado_operadora: list[str] | None,
    filtro_fecha: str,
) -> str:
    alertas_where = " AND ".join(cond_alertas)
    base_alertas = f"""
        SELECT a.alerta_id, a.sujeto_id, l.identificador_natural, l.nombre_apellido, l.tipo_sujeto,
               a.requisito_definicion_id, COALESCE(r.nombre, a.requisito_definicion_id::text) AS requisito,
               o.operadora_id, o.nombre AS operadora, a.documento_vigente_id,
               a.ultimo_documento_operadora_id, a.estado AS estado_operadora, a.motivo,
               COALESCE(
                   (SELECT max(m.paso_en) FROM modulo1.movimiento_entrega_operadora m
                    WHERE m.tenant_id = a.tenant_id AND m.operadora_id = a.operadora_id
                      AND m.sujeto_id = a.sujeto_id AND m.requisito_definicion_id = a.requisito_definicion_id),
                   a.actualizada_en
               ) AS ultimo_movimiento_en
        FROM modulo1.alerta_actualizacion_operadora a
        JOIN modulo1.operadora_documental o ON o.tenant_id = a.tenant_id AND o.operadora_id = a.operadora_id
        JOIN modulo1.legajo l ON l.tenant_id = a.tenant_id AND l.sujeto_id = a.sujeto_id
        LEFT JOIN modulo1.definicion_requisito r
          ON r.tenant_id = a.tenant_id AND r.requisito_definicion_id = a.requisito_definicion_id
        WHERE {alertas_where}
    """
    partes: list[str] = []
    incluir_alertas = not estado_operadora or any(e != "al_dia" for e in estado_operadora)
    if incluir_alertas:
        fila = base_alertas
        if estado_operadora and any(e != "al_dia" for e in estado_operadora):
            fila = f"{base_alertas} AND a.estado = ANY(CAST(:estados_espejo AS text[]))"
        elif estado_operadora == ["al_dia"]:
            fila = ""
        if fila:
            partes.append(fila)
    if estado_operadora and "al_dia" in estado_operadora:
        al_dia_where = " AND ".join(cond_al_dia)
        partes.append(f"""
            SELECT NULL::uuid AS alerta_id, e.sujeto_id, l.identificador_natural, l.nombre_apellido, l.tipo_sujeto,
                   e.requisito_definicion_id, COALESCE(r.nombre, e.requisito_definicion_id::text) AS requisito,
                   o.operadora_id, o.nombre AS operadora, d.documento_id AS documento_vigente_id,
                   e.documento_id AS ultimo_documento_operadora_id, 'al_dia' AS estado_operadora,
                   'La operadora aceptó la versión vigente.' AS motivo,
                   COALESCE(
                       (SELECT max(m.paso_en) FROM modulo1.movimiento_entrega_operadora m
                        WHERE m.tenant_id = e.tenant_id AND m.documento_id = e.documento_id),
                       e.actualizado_en
                   ) AS ultimo_movimiento_en
            FROM modulo1.entrega_documento_operadora e
            JOIN modulo1.operadora_documental o ON o.tenant_id = e.tenant_id AND o.operadora_id = e.operadora_id
            JOIN modulo1.legajo l ON l.tenant_id = e.tenant_id AND l.sujeto_id = e.sujeto_id
            JOIN modulo1.documento d ON d.tenant_id = e.tenant_id AND d.documento_id = e.documento_id
              AND d.sujeto_id = e.sujeto_id AND d.requisito_definicion_id = e.requisito_definicion_id
              AND d.estado_version = 'vigente' AND d.documento_id = e.documento_id
            LEFT JOIN modulo1.definicion_requisito r
              ON r.tenant_id = e.tenant_id AND r.requisito_definicion_id = e.requisito_definicion_id
            WHERE {al_dia_where}
        """)
    union = partes[0] if len(partes) == 1 else " UNION ALL ".join(partes)
    return f"SELECT * FROM ({union}) espejo WHERE {filtro_fecha}"


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

