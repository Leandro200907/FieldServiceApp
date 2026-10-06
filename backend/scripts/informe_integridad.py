"""Informe de integridad de demo (solo lectura: SELECT + inspección de storage).

Uso:
  python -m scripts.informe_integridad --tenant-slug patagonia-demo

No escribe en la base ni en storage. Aborta si DATABASE_URL no apunta a una base *_demo.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import text

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ_BACKEND))

from app.config import settings  # noqa: E402
from app.db import platform_session, tenant_session  # noqa: E402
from app.storage import obtener_storage  # noqa: E402


@dataclass
class Control:
    numero: int
    nombre: str
    resultado: str  # OK | observación
    cantidad: int = 0
    detalle: str = ""
    ejemplos: list[Any] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)


def _nombre_base(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    return (parsed.path or "").lstrip("/").split("?")[0]


def exigir_base_demo() -> str:
    nombre = _nombre_base(settings.database_url)
    if not nombre.endswith("_demo"):
        print(f"Aborto: DATABASE_URL debe apuntar a una base *_demo (actual: {nombre})", file=sys.stderr)
        raise SystemExit(2)
    return nombre


def resolver_tenant(slug: str) -> tuple[str, str]:
    with platform_session() as s:
        tenant_id = s.execute(
            text("SELECT modulo1.resolver_tenant_por_slug(:slug)"),
            {"slug": slug},
        ).scalar()
    if tenant_id is None:
        print(f"Tenant inexistente: {slug}", file=sys.stderr)
        raise SystemExit(2)
    return str(tenant_id), slug


def _ok(control: Control) -> Control:
    if control.cantidad == 0 and control.resultado != "OK":
        control.resultado = "OK"
    elif control.cantidad > 0 and control.resultado == "OK":
        control.resultado = "observación"
    return control


def control_archivos(s, tenant_id: str, storage) -> Control:
    filas = s.execute(
        text(
            """
            SELECT documento_id::text, clave_storage, checksum_archivo, archivo_bytes,
                   archivo_estado, archivo_validacion, creado_en
            FROM modulo1.documento
            WHERE tenant_id = :t
              AND archivo_estado NOT IN ('sin_archivo', 'purgado')
              AND clave_storage IS NOT NULL
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    dist = Counter(str(r["archivo_validacion"]) for r in filas)
    ahora = datetime.now(timezone.utc)
    pendientes_viejas: list[dict[str, Any]] = []
    incoherentes: list[dict[str, Any]] = []

    for r in filas:
        clave = str(r["clave_storage"])
        info = storage.inspeccionar(clave)
        doc_id = r["documento_id"]
        esperado_ck = (r["checksum_archivo"] or "").lower()
        esperado_bytes = r["archivo_bytes"]

        problemas: list[str] = []
        if info is None:
            problemas.append("ausente_en_storage")
        else:
            if esperado_bytes is not None and info.bytes != int(esperado_bytes):
                problemas.append(f"bytes_db={esperado_bytes}_storage={info.bytes}")
            if esperado_ck and info.checksum_sha256.lower() != esperado_ck:
                problemas.append("sha256_distinto")

        if problemas:
            incoherentes.append({"documento_id": doc_id, "clave_storage": clave, "problemas": problemas})

        if (
            r["archivo_estado"] == "confirmado"
            and r["archivo_validacion"] == "pendiente"
            and r["creado_en"] is not None
        ):
            creado = r["creado_en"]
            if creado.tzinfo is None:
                creado = creado.replace(tzinfo=timezone.utc)
            if ahora - creado > timedelta(hours=1):
                pendientes_viejas.append(
                    {"documento_id": doc_id, "creado_en": creado.isoformat(), "clave_storage": clave}
                )

    cantidad = len(incoherentes) + len(pendientes_viejas)
    detalle = (
        f"documentos_con_archivo={len(filas)}; "
        f"archivo_validacion={dict(dist)}; "
        f"incoherencias_storage={len(incoherentes)}; "
        f"pendiente_validacion_mas_1h={len(pendientes_viejas)}"
    )
    ejemplos = (incoherentes[:3] + pendientes_viejas[: max(0, 5 - min(3, len(incoherentes)))])[:5]
    c = Control(1, "Archivos (storage vs BD + validación)", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos)
    c.extra = {"distribucion_archivo_validacion": dict(dist)}
    return _ok(c)


def control_huerfanos(s, tenant_id: str, storage, tenant_prefix: Path) -> Control:
    claves_db = {
        str(r[0])
        for r in s.execute(
            text("SELECT clave_storage FROM modulo1.documento WHERE tenant_id = :t AND clave_storage IS NOT NULL"),
            {"t": tenant_id},
        ).all()
    }

    huerfanos_storage: list[str] = []
    if tenant_prefix.is_dir():
        for path in tenant_prefix.rglob("*"):
            if path.is_file():
                rel = path.relative_to(Path(settings.storage_local_dir).resolve()).as_posix()
                if rel not in claves_db:
                    huerfanos_storage.append(rel)

    cert_sin_soporte = s.execute(
        text(
            """
            SELECT d.documento_id::text, d.sujeto_id, d.origen
            FROM modulo1.documento d
            WHERE d.tenant_id = :t AND d.origen = 'certificado_respaldo'
              AND NOT EXISTS (
                SELECT 1 FROM modulo1.documento_soporte ds
                WHERE ds.tenant_id = d.tenant_id AND ds.soporte_documento_id = d.documento_id
              )
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    docs_sin_sujeto = s.execute(
        text(
            """
            SELECT d.documento_id::text, d.sujeto_id
            FROM modulo1.documento d
            LEFT JOIN modulo1.legajo l ON l.tenant_id = d.tenant_id AND l.sujeto_id = d.sujeto_id
            WHERE d.tenant_id = :t AND l.legajo_id IS NULL
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    cantidad = len(huerfanos_storage) + len(cert_sin_soporte) + len(docs_sin_sujeto)
    detalle = (
        f"storage_huerfanos={len(huerfanos_storage)}; "
        f"certificado_respaldo_sin_documento_soporte={len(cert_sin_soporte)}; "
        f"documentos_sin_legajo={len(docs_sin_sujeto)}"
    )
    ejemplos: list[Any] = []
    ejemplos.extend([{"tipo": "storage_huerfano", "clave": k} for k in huerfanos_storage[:2]])
    ejemplos.extend([{"tipo": "cert_sin_soporte", **dict(r)} for r in cert_sin_soporte[:2]])
    ejemplos.extend([{"tipo": "doc_sin_sujeto", **dict(r)} for r in docs_sin_sujeto[:2]])
    return _ok(Control(2, "Huérfanos", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos[:5]))


def control_versiones(s, tenant_id: str) -> Control:
    multiples_vigentes = s.execute(
        text(
            """
            SELECT sujeto_id, requisito_definicion_id::text, count(*) AS n
            FROM modulo1.documento
            WHERE tenant_id = :t AND estado_version = 'vigente' AND requisito_definicion_id IS NOT NULL
            GROUP BY sujeto_id, requisito_definicion_id
            HAVING count(*) > 1
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    propuestas = s.execute(
        text(
            """
            SELECT documento_id::text, sujeto_id, requisito_definicion_id::text, creado_en
            FROM modulo1.documento
            WHERE tenant_id = :t AND estado_version = 'propuesta' AND estado_confirmacion = 'declarado'
            ORDER BY creado_en ASC
            """
        ),
        {"t": tenant_id},
    ).mappings().all()
    ahora = datetime.now(timezone.utc)
    antiguas = []
    for p in propuestas:
        c = p["creado_en"]
        if c and c.tzinfo is None:
            c = c.replace(tzinfo=timezone.utc)
        if c and ahora - c > timedelta(days=7):
            antiguas.append({**dict(p), "creado_en": c.isoformat(), "dias": round((ahora - c).total_seconds / 86400, 1)})

    cantidad = len(multiples_vigentes) + len(antiguas)
    detalle = f"multiples_vigentes={len(multiples_vigentes)}; propuestas_pendientes={len(propuestas)}; propuestas_antiguas_7d={len(antiguas)}"
    ejemplos: list[Any] = [dict(m) for m in multiples_vigentes[:3]]
    ejemplos.extend(list(antiguas)[: max(0, 5 - len(ejemplos))])
    return _ok(Control(3, "Versiones documentales", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos[:5]))


def control_matrices(s, tenant_id: str) -> Control:
    superpuestas = s.execute(
        text(
            """
            SELECT a.cliente_id::text AS cliente_id, a.locacion_id::text AS locacion_id,
                   a.tipo_servicio_id::text AS tipo_servicio_id,
                   a.matriz_version_id::text AS v1, b.matriz_version_id::text AS v2,
                   a.vigente_desde AS d1_desde, a.vigente_hasta AS d1_hasta,
                   b.vigente_desde AS d2_desde, b.vigente_hasta AS d2_hasta
            FROM modulo1.matriz_requisitos a
            JOIN modulo1.matriz_requisitos b
              ON a.tenant_id = b.tenant_id
             AND a.cliente_id = b.cliente_id
             AND a.locacion_id = b.locacion_id
             AND a.tipo_servicio_id = b.tipo_servicio_id
             AND a.matriz_version_id < b.matriz_version_id
            WHERE a.tenant_id = :t
              AND a.vigente_desde <= COALESCE(b.vigente_hasta, DATE '9999-12-31')
              AND b.vigente_desde <= COALESCE(a.vigente_hasta, DATE '9999-12-31')
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    oc_sin_matriz = s.execute(
        text(
            """
            SELECT o.oc_id::text, o.clave_origen, o.vigencia_desde, o.vigencia_hasta,
                   o.cliente_id::text, o.locacion_id::text, o.tipo_servicio_id::text
            FROM modulo1.oc o
            WHERE o.tenant_id = :t AND o.estado = 'activo'
              AND NOT EXISTS (
                SELECT 1 FROM modulo1.matriz_requisitos m
                WHERE m.tenant_id = o.tenant_id
                  AND m.cliente_id = o.cliente_id
                  AND m.locacion_id = o.locacion_id
                  AND m.tipo_servicio_id = o.tipo_servicio_id
                  AND m.vigente_desde <= o.vigencia_desde
                  AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= o.vigencia_desde)
              )
            ORDER BY o.vigencia_desde, o.clave_origen
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    cantidad = len(superpuestas) + len(oc_sin_matriz)
    detalle = f"pares_matrices_superpuestas={len(superpuestas)}; oc_activas_sin_matriz_al_ingreso={len(oc_sin_matriz)}"
    ejemplos: list[Any] = [dict(x) for x in superpuestas[:2]]
    ejemplos.extend([dict(x) for x in oc_sin_matriz[: max(0, 5 - len(ejemplos))]])
    c = Control(4, "Matrices y cobertura OC", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos[:5])
    c.extra = {"lista_oc_sin_matriz": [r["clave_origen"] for r in oc_sin_matriz]}
    return _ok(c)


def control_oc(s, tenant_id: str) -> Control:
    vigencia_invertida = s.execute(
        text(
            """
            SELECT oc_id::text, clave_origen, vigencia_desde, vigencia_hasta
            FROM modulo1.oc
            WHERE tenant_id = :t AND vigencia_desde > vigencia_hasta
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    claves_dup = s.execute(
        text(
            """
            SELECT clave_origen, count(*) AS n
            FROM modulo1.oc
            WHERE tenant_id = :t
            GROUP BY clave_origen
            HAVING count(*) > 1
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    reprogramaciones = s.execute(
        text(
            """
            SELECT o.oc_id::text, o.clave_origen, o.origen_oc,
                   e.evento_id::text, e.payload
            FROM modulo1.oc o
            JOIN modulo1.event_log e ON e.tenant_id = o.tenant_id
              AND e.tipo = 'CompromisoModificado'
              AND e.payload->>'oc_id' = o.oc_id::text
            WHERE o.tenant_id = :t
              AND e.payload->'campos_modificados' ?| ARRAY['vigencia_desde', 'vigencia_hasta']
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    rep_fallas: list[dict[str, Any]] = []
    for r in reprogramaciones:
        payload = r["payload"] if isinstance(r["payload"], dict) else json.loads(r["payload"])
        commitment_evento = payload.get("commitment_id")
        problemas = []
        if commitment_evento != r["clave_origen"]:
            problemas.append("commitment_id_distinto_a_clave_origen")
        if payload.get("origen") == "manual" and r["origen_oc"] not in ("manual", "modulo2"):
            problemas.append(f"origen_oc={r['origen_oc']}_tras_reprogramacion_manual")
        if not payload.get("anterior") or not payload.get("nuevo"):
            problemas.append("falta_anterior_o_nuevo_en_evento")
        if problemas:
            rep_fallas.append(
                {
                    "oc_id": r["oc_id"],
                    "clave_origen": r["clave_origen"],
                    "evento_id": r["evento_id"],
                    "problemas": problemas,
                }
            )

    cantidad = len(vigencia_invertida) + len(claves_dup) + len(rep_fallas)
    detalle = (
        f"vigencia_invertida={len(vigencia_invertida)}; claves_duplicadas={len(claves_dup)}; "
        f"reprogramaciones_inconsistentes_E82={len(rep_fallas)} (total_eventos_vigencia={len(reprogramaciones)})"
    )
    ejemplos: list[Any] = [dict(x) for x in vigencia_invertida[:2]]
    ejemplos.extend([dict(x) for x in claves_dup[:2]])
    ejemplos.extend(rep_fallas[: max(0, 5 - len(ejemplos))])
    return _ok(Control(5, "OC (vigencia, claves, reprogramación E-82)", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos[:5]))


def control_eventos(s, tenant_id: str) -> Control:
    sin_verificar = s.execute(
        text(
            """
            SELECT d.documento_id::text, d.estado_confirmacion
            FROM modulo1.documento d
            WHERE d.tenant_id = :t
              AND d.estado_confirmacion IN ('verificado', 'confirmado_en_fuente')
              AND NOT EXISTS (
                SELECT 1 FROM modulo1.event_log e
                WHERE e.tenant_id = d.tenant_id AND e.tipo = 'DocumentoVerificado'
                  AND e.payload->>'documento_id' = d.documento_id::text
              )
            LIMIT 5000
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    sin_rechazo = s.execute(
        text(
            """
            SELECT d.documento_id::text, d.sujeto_id
            FROM modulo1.documento d
            WHERE d.tenant_id = :t AND d.estado_version = 'rechazada' AND d.origen_propuesta
              AND NOT EXISTS (
                SELECT 1 FROM modulo1.event_log e
                WHERE e.tenant_id = d.tenant_id AND e.tipo = 'DocumentoRechazado'
                  AND e.payload->>'documento_id' = d.documento_id::text
              )
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    sin_carga = s.execute(
        text(
            """
            SELECT d.documento_id::text, d.origen
            FROM modulo1.documento d
            WHERE d.tenant_id = :t
              AND NOT EXISTS (
                SELECT 1 FROM modulo1.event_log e
                WHERE e.tenant_id = d.tenant_id AND e.tipo = 'DocumentoCargado'
                  AND e.payload->>'documento_id' = d.documento_id::text
              )
            LIMIT 5000
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    mov_sin_evento = s.execute(
        text(
            """
            SELECT m.movimiento_id::text, m.documento_id::text, m.estado, m.paso_en
            FROM modulo1.movimiento_entrega_operadora m
            WHERE m.tenant_id = :t
              AND NOT EXISTS (
                SELECT 1 FROM modulo1.event_log e
                WHERE e.tenant_id = m.tenant_id
                  AND e.tipo = 'EstadoDocumentoOperadoraRegistrado'
                  AND e.payload->>'documento_id' = m.documento_id::text
                  AND e.payload->>'estado' = m.estado
                  AND e.ocurrido_en BETWEEN m.paso_en - interval '2 seconds' AND m.paso_en + interval '2 seconds'
              )
            LIMIT 2000
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    outbox_pendiente = s.execute(
        text(
            """
            SELECT count(*) FROM modulo1.outbox_events
            WHERE tenant_id = :t AND procesado_en IS NULL
            """
        ),
        {"t": tenant_id},
    ).scalar()
    outbox_estancado = s.execute(
        text(
            """
            SELECT count(*) FROM modulo1.outbox_events
            WHERE tenant_id = :t AND estancado_en IS NOT NULL
            """
        ),
        {"t": tenant_id},
    ).scalar()

    cantidad = len(sin_verificar) + len(sin_rechazo) + len(sin_carga) + len(mov_sin_evento) + int(outbox_pendiente or 0) + int(
        outbox_estancado or 0
    )
    detalle = (
        f"confirmados_sin_DocumentoVerificado={len(sin_verificar)}; "
        f"rechazos_sin_DocumentoRechazado={len(sin_rechazo)}; "
        f"documentos_sin_DocumentoCargado={len(sin_carga)}; "
        f"mov_operadora_sin_evento={len(mov_sin_evento)}; "
        f"outbox_pendiente={outbox_pendiente}; outbox_estancado={outbox_estancado}"
    )
    ejemplos: list[Any] = []
    ejemplos.extend([{"tipo": "sin_verificado", **dict(x)} for x in sin_verificar[:2]])
    ejemplos.extend([{"tipo": "sin_rechazo", **dict(x)} for x in sin_rechazo[:2]])
    ejemplos.extend([{"tipo": "sin_carga", **dict(x)} for x in sin_carga[:1]])
    if outbox_pendiente:
        filas_ob = s.execute(
            text(
                "SELECT evento_id::text, tipo, intentos, creado_en FROM modulo1.outbox_events "
                "WHERE tenant_id = :t AND procesado_en IS NULL ORDER BY creado_en LIMIT 3"
            ),
            {"t": tenant_id},
        ).mappings().all()
        ejemplos.extend([{"tipo": "outbox_pendiente", **dict(f)} for f in filas_ob])
    c = Control(6, "Eventos de auditoría y outbox", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos[:5])
    c.extra = {"outbox_pendiente": int(outbox_pendiente or 0), "outbox_estancado": int(outbox_estancado or 0)}
    return _ok(c)


def control_aislamiento(s, tenant_id: str) -> Control:
    prefijo_malo = s.execute(
        text(
            """
            SELECT documento_id::text, clave_storage
            FROM modulo1.documento
            WHERE tenant_id = :t AND clave_storage IS NOT NULL
              AND NOT clave_storage LIKE (:t || '/%')
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    soporte_cruzado = s.execute(
        text(
            """
            SELECT ds.documento_id::text, ds.soporte_documento_id::text
            FROM modulo1.documento_soporte ds
            JOIN modulo1.documento padre ON padre.tenant_id = ds.tenant_id AND padre.documento_id = ds.documento_id
            LEFT JOIN modulo1.documento sop ON sop.documento_id = ds.soporte_documento_id AND sop.tenant_id = ds.tenant_id
            WHERE ds.tenant_id = :t AND (sop.documento_id IS NULL OR sop.tenant_id <> ds.tenant_id)
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    oc_catalogo = s.execute(
        text(
            """
            SELECT o.oc_id::text, o.clave_origen, o.cliente_id::text
            FROM modulo1.oc o
            LEFT JOIN modulo1.operadora_documental op ON op.tenant_id = o.tenant_id AND op.operadora_id = o.cliente_id
            WHERE o.tenant_id = :t AND op.operadora_id IS NULL
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    matriz_loc = s.execute(
        text(
            """
            SELECT m.matriz_version_id::text, m.cliente_id::text, m.locacion_id::text
            FROM modulo1.matriz_requisitos m
            LEFT JOIN modulo1.locacion_oc l ON l.tenant_id = m.tenant_id AND l.locacion_id = m.locacion_id
            WHERE m.tenant_id = :t AND (l.locacion_id IS NULL OR l.operadora_id <> m.cliente_id)
            """
        ),
        {"t": tenant_id},
    ).mappings().all()

    cantidad = len(prefijo_malo) + len(soporte_cruzado) + len(oc_catalogo) + len(matriz_loc)
    detalle = (
        f"clave_storage_fuera_de_tenant={len(prefijo_malo)}; "
        f"documento_soporte_huérfano/cruzado={len(soporte_cruzado)}; "
        f"oc_cliente_inexistente={len(oc_catalogo)}; matriz_locacion_incoherente={len(matriz_loc)}"
    )
    ejemplos: list[Any] = [dict(x) for x in prefijo_malo[:2]]
    ejemplos.extend([dict(x) for x in soporte_cruzado[:2]])
    ejemplos.extend([dict(x) for x in oc_catalogo[:1]])
    return _ok(Control(7, "Aislamiento / coherencia intra-tenant", "OK" if cantidad == 0 else "observación", cantidad, detalle, ejemplos[:5]))


def ejecutar(slug: str) -> list[Control]:
    base = exigir_base_demo()
    tenant_id, slug_res = resolver_tenant(slug)
    storage = obtener_storage()
    tenant_prefix = Path(settings.storage_local_dir).resolve() / tenant_id

    controles: list[Control] = []
    with tenant_session(tenant_id) as s:
        controles.append(control_archivos(s, tenant_id, storage))
        controles.append(control_huerfanos(s, tenant_id, storage, tenant_prefix))
        controles.append(control_versiones(s, tenant_id))
        controles.append(control_matrices(s, tenant_id))
        controles.append(control_oc(s, tenant_id))
        controles.append(control_eventos(s, tenant_id))
        controles.append(control_aislamiento(s, tenant_id))

    print(f"Base: {base} | Tenant: {slug_res} ({tenant_id})")
    print(f"Storage: {Path(settings.storage_local_dir).resolve()}")
    return controles


def imprimir(controles: list[Control]) -> None:
    print("\n=== Informe de integridad ===")
    print(f"{'#':<3} {'Control':<42} {'Resultado':<12} {'Cant.':<6} Detalle")
    print("-" * 120)
    for c in controles:
        print(f"{c.numero:<3} {c.nombre:<42} {c.resultado:<12} {c.cantidad:<6} {c.detalle}")
        if c.ejemplos:
            for ej in c.ejemplos[:5]:
                print(f"    · {json.dumps(ej, ensure_ascii=False, default=str)}")
    print("\n=== JSON ===")
    print(
        json.dumps(
            [
                {
                    "numero": c.numero,
                    "nombre": c.nombre,
                    "resultado": c.resultado,
                    "cantidad": c.cantidad,
                    "detalle": c.detalle,
                    "ejemplos": c.ejemplos[:5],
                    "extra": c.extra,
                }
                for c in controles
            ],
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Informe de integridad demo (solo lectura)")
    p.add_argument("--tenant-slug", required=True, help="Slug del tenant a auditar")
    args = p.parse_args(argv)
    controles = ejecutar(args.tenant_slug)
    imprimir(controles)
    return 1 if any(c.resultado == "observación" for c in controles) else 0


if __name__ == "__main__":
    raise SystemExit(main())
