"""Exportación / entrega de legajo (capacidad del responsable en 9.1): el legajo completo
de un sujeto en JSON o CSV, con traza `LegajoExportado` (1.11: traza de descargas). Sin
archivos binarios (van por URL firmada); sí referencias y checksums.
"""
from __future__ import annotations

import csv
import io
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento_interno
from app.comun.reloj import hoy_del_tenant

_SECCIONES = {
    "documentos": ("SELECT d.documento_id, d.requisito_definicion_id, d.version, d.vigente_desde, d.vigente_hasta, d.estado_version, d.estado_confirmacion, d.origen, "
                   "d.origen_propuesta, d.numero, d.lote_id, d.archivo_estado, d.checksum_archivo, d.archivo_bytes, d.creado_en FROM modulo1.documento d "
                   "JOIN modulo1.definicion_requisito r ON r.tenant_id=d.tenant_id AND r.requisito_definicion_id=d.requisito_definicion_id "
                   "WHERE d.tenant_id = :t AND d.sujeto_id = :s ORDER BY d.requisito_definicion_id, d.version"),
    "acreditaciones": ("SELECT d.documento_id AS acreditacion_id, d.requisito_definicion_id, d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, "
                       "ARRAY(SELECT ds.soporte_documento_id FROM modulo1.documento_soporte ds WHERE ds.tenant_id=d.tenant_id AND ds.documento_id=d.documento_id) AS evidencias, d.creado_en "
                       "FROM modulo1.documento d JOIN modulo1.definicion_requisito r ON r.tenant_id=d.tenant_id AND r.requisito_definicion_id=d.requisito_definicion_id "
                       "WHERE d.tenant_id=:t AND d.sujeto_id=:s AND r.categoria='competencia' ORDER BY d.creado_en"),
    "inducciones": ("SELECT d.documento_id AS induccion_id, d.requisito_definicion_id, d.locacion_id, d.vigente_desde, d.vigente_hasta, d.estado_confirmacion, "
                    "(SELECT ds.soporte_documento_id FROM modulo1.documento_soporte ds WHERE ds.tenant_id=d.tenant_id AND ds.documento_id=d.documento_id LIMIT 1) AS evidencia, d.creado_en "
                    "FROM modulo1.documento d JOIN modulo1.definicion_requisito r ON r.tenant_id=d.tenant_id AND r.requisito_definicion_id=d.requisito_definicion_id "
                    "WHERE d.tenant_id=:t AND d.sujeto_id=:s AND r.categoria='induccion' ORDER BY d.creado_en"),
    "excepciones": ("SELECT excepcion_id, referencia_evaluacion, requisito_definicion_id, commitment_id, estado, otorgada_por, motivo, vigencia, creado_en "
                    "FROM modulo1.excepcion WHERE tenant_id = :t AND sujeto_id = :s ORDER BY creado_en"),
    "constancias": ("SELECT constancia_id, requisito_definicion_id, cliente_id, commitment_id, estado, emisor, vigencia, creado_en "
                    "FROM modulo1.constancia_cliente WHERE tenant_id = :t AND sujeto_id = :s ORDER BY creado_en"),
    "custodias": ("SELECT p.periodo_id, c.recurso_id, c.tipo_recurso, p.custodio_id, p.desde, p.hasta, p.estado FROM modulo1.periodo_custodia p "
                  "JOIN modulo1.custodia_recurso c ON c.tenant_id = p.tenant_id AND c.custodia_id = p.custodia_id "
                  "WHERE p.tenant_id = :t AND (c.recurso_id = :s OR p.custodio_id = :s) ORDER BY p.desde"),
    "alertas": ("SELECT alerta_id, fuente_tipo, fuente_id, requisito_definicion_id, vigente_hasta, etapa, estado, bajo_excepcion, resuelta_motivo, abierta_en "
                "FROM modulo1.alerta_vencimiento WHERE tenant_id = :t AND sujeto_id = :s ORDER BY abierta_en"),
    "supervision": ("SELECT asignacion_id, supervisor_usuario_id, desde, hasta, estado FROM modulo1.asignacion_supervisor WHERE tenant_id = :t AND sujeto_id = :s ORDER BY desde"),
}


def _plano(v: Any) -> Any:
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "hex") and not isinstance(v, (bytes, int)):
        return str(v)
    if isinstance(v, list):
        return [_plano(x) for x in v]
    return v


def exportar(session: Session, identidad: Identidad, sujeto_id: str, formato: str = "json") -> tuple[str, bytes, str]:
    """(content_type, contenido, nombre_archivo)."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    legajo = session.execute(text("SELECT sujeto_id, tipo_sujeto, identificador_natural, dado_de_baja_en, creado_en FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s"),
                             {"t": t, "s": sujeto_id}).mappings().first()
    if legajo is None:
        raise NoEncontrado("Legajo inexistente", {"sujeto_id": sujeto_id})
    nombres = dict(session.execute(text("SELECT requisito_definicion_id::text, nombre FROM modulo1.definicion_requisito WHERE tenant_id = :t"), {"t": t}).all())
    datos: dict[str, Any] = {"exportado_en": hoy_del_tenant(session, t).isoformat(), "exportado_por": identidad.usuario_id,
                             "legajo": {k: _plano(v) for k, v in dict(legajo).items()}}
    for seccion, sql in _SECCIONES.items():
        filas = []
        for f in session.execute(text(sql), {"t": t, "s": sujeto_id}).mappings():
            d = {k: _plano(v) for k, v in dict(f).items()}
            if "requisito_definicion_id" in d and d["requisito_definicion_id"]:
                d["requisito"] = nombres.get(d["requisito_definicion_id"])
            filas.append(d)
        datos[seccion] = filas
    registrar_evento_interno(session, t, "LegajoExportado", {"sujeto_id": sujeto_id, "formato": formato, "secciones": {k: len(v) for k, v in datos.items() if isinstance(v, list)}},
                             identidad.usuario_id)
    nombre = f"legajo_{sujeto_id}_{datos['exportado_en']}"
    if formato == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["seccion", "campo", "valor", "fila"])
        for k, v in datos["legajo"].items():
            w.writerow(["legajo", k, v, 0])
        for seccion, filas in datos.items():
            if not isinstance(filas, list):
                continue
            for i, fila in enumerate(filas):
                for k, v in fila.items():
                    w.writerow([seccion, k, v if not isinstance(v, list) else ";".join(map(str, v)), i])
        return "text/csv; charset=utf-8", buf.getvalue().encode("utf-8"), nombre + ".csv"
    import json
    return "application/json", json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8"), nombre + ".json"

