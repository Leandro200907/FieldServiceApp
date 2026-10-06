"""Sembrado de un tenant de demo vía servicios (sin INSERT directos de dominio)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable

from sqlalchemy import text

from app.api.errores import ErrorDeDominio
from app.auth.identidad import Rol
from app.db import tenant_session
from app.modules.alertas import servicio as alertas_svc
from app.modules.legajos import esquemas as leg_esq
from app.modules.legajos import servicio as legajos
from app.modules.notificaciones import servicio as notif_svc
from app.modules.oc import catalogos_maestros, servicio as oc_svc
from app.modules.paquete import servicio as paquete_svc
from app.modules.requisitos import esquemas as req_esq
from app.modules.requisitos import plantillas, servicio as req_svc
from app.storage.servicio import confirmar_subida, preparar_subida
from scripts.demo.config import (
    DNI_BAJA_POR_SLUG,
    EQUIPO_POR_SLUG,
    GLOBAL_A_DEMO,
    LOCACIONES_POR_OPERADORA,
    nombre_locacion_demo,
    OPERADORAS,
    PATENTES_POR_SLUG,
    REQUISITOS_LOCALES,
    TIPOS_SERVICIO,
    dni_tecnico,
    nombre_tecnico,
)
from scripts.demo.contexto import EstadoTenant, identidad_de
from scripts.demo.evidencia_fake import jpg_demo, pdf_demo
from scripts.demo.fechas import (
    hoy_tenant,
    rango_oc_en_curso,
    rango_oc_futura,
    rango_oc_terminada,
    rango_por_vencer,
    rango_vencido,
    rango_vigente,
)


@dataclass
class SemillaContext:
    notas: list[str] = field(default_factory=list)
    fallas: list[str] = field(default_factory=list)


def _run(label: str, fn: Callable[[], None], ctx: SemillaContext) -> None:
    try:
        fn()
    except ErrorDeDominio as e:
        ctx.fallas.append(f"{label}: {e.codigo} — {e}")
    except Exception as e:  # noqa: BLE001 — reportar demo sin abortar todo el tenant
        ctx.fallas.append(f"{label}: {type(e).__name__} — {e}")


def _globals_por_nombre(dsn_owner: str) -> dict[str, str]:
    import psycopg

    from scripts.demo.db_util import exigir_base_demo

    _, owner, _ = exigir_base_demo()
    with psycopg.connect(owner) as conn:
        filas = conn.execute(
            "SELECT definicion_global_id::text, nombre FROM plataforma.definicion_requisito_global"
        ).fetchall()
        matrices = conn.execute(
            "SELECT matriz_global_id::text, operadora, tipo_servicio FROM plataforma.matriz_global WHERE activa"
        ).fetchall()
    return {
        "def": {n: i for i, n in filas},
        "mat": {f"{o}|{ts}": i for i, o, ts in matrices},
    }


def cargar_requisitos(est: EstadoTenant, ctx: SemillaContext) -> None:
    glob = _globals_por_nombre("")
    idn = est.idn("configuracion", 1)
    with tenant_session(est.tenant_id) as s:
        if est.spec.copiar_globales:
            for demo_n, global_n in GLOBAL_A_DEMO.items():
                gid = glob["def"].get(global_n)
                if not gid:
                    ctx.fallas.append(f"global inexistente: {global_n}")
                    continue
                loc = None
                body = req_esq.CopiarDefinicionGlobal(definicion_global_id=uuid.UUID(gid), locacion_id=None)
                if demo_n == "Inducción operadora":
                    continue  # se resuelve al copiar matriz o tras crear locación
                r = plantillas.copiar_definicion_global(s, idn, body)
                est.requisitos[demo_n] = r["requisito_definicion_id"]
        else:
            for spec in REQUISITOS_LOCALES:
                if spec["nombre"] == "Inducción operadora":
                    continue  # requiere locacion_id; se crea tras catálogos
                r = req_svc.dar_de_alta_definicion_de_requisito(
                    s,
                    idn,
                    req_esq.DarDeAltaDefinicionDeRequisito(**spec),
                )
                est.requisitos[spec["nombre"]] = r["requisito_definicion_id"]


def cargar_sujetos(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn = est.idn("responsable_legajos", 1)
    hoy = hoy_tenant(est.tenant_id)
    with tenant_session(est.tenant_id) as s:
        for n in (1, 2, 3):
            sid = est.sujetos[f"tecnico{n}"]
            legajos.alta_de_sujeto(
                s,
                idn,
                leg_esq.AltaDeSujeto(
                    tipo_sujeto="persona",
                    identificador_natural=dni_tecnico(est.spec.slug, n),
                    nombre_apellido=nombre_tecnico(est.spec.slug, n),
                    sujeto_id=sid,
                ),
            )
        extra = f"persona_{est.spec.slug.replace('-', '_')}_baja"
        est.sujetos["tecnico_baja"] = extra
        legajos.alta_de_sujeto(
            s,
            idn,
            leg_esq.AltaDeSujeto(
                tipo_sujeto="persona",
                identificador_natural=DNI_BAJA_POR_SLUG[est.spec.slug],
                sujeto_id=extra,
            ),
        )
        legajos.baja_de_sujeto(s, idn, leg_esq.BajaDeSujeto(sujeto_id=extra))
        patentes = PATENTES_POR_SLUG[est.spec.slug]
        for i, pat in enumerate(patentes, 1):
            vid = f"vehiculo_{est.spec.slug.replace('-', '_')}_{i}"
            est.sujetos[f"vehiculo{i}"] = vid
            legajos.alta_de_sujeto(s, idn, leg_esq.AltaDeSujeto(tipo_sujeto="vehiculo", identificador_natural=pat, sujeto_id=vid))
        eq = f"equipo_{est.spec.slug.replace('-', '_')}_1"
        est.sujetos["equipo1"] = eq
        legajos.alta_de_sujeto(
            s,
            idn,
            leg_esq.AltaDeSujeto(
                tipo_sujeto="equipo",
                identificador_natural=EQUIPO_POR_SLUG[est.spec.slug],
                sujeto_id=eq,
            ),
        )
        emp = f"empresa_{est.spec.slug.replace('-', '_')}"
        est.sujetos["empresa"] = emp
        legajos.alta_de_sujeto(s, idn, leg_esq.AltaDeSujeto(tipo_sujeto="empresa", identificador_natural=est.spec.nombre, sujeto_id=emp))


def _cargar_doc(s, idn, sujeto, req_nombre, est, desde, hasta, **kw) -> str:
    rid = est.requisitos[req_nombre]
    r = legajos.cargar_documento(
        s,
        idn,
        leg_esq.CargarDocumento(
            sujeto_id=sujeto,
            requisito_definicion_id=uuid.UUID(rid),
            vigente_desde=desde,
            vigente_hasta=hasta,
            **kw,
        ),
    )
    return r["documento_id"]


def cargar_documentos_tecnicos(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn = est.idn("responsable_legajos", 1)
    hoy = hoy_tenant(est.tenant_id)
    v1, v2 = rango_vigente(hoy)
    pv1, pv2 = rango_por_vencer(hoy)
    ve1, ve2 = rango_vencido(hoy)
    mapa_t12 = [
        ("Apto médico", "vigente", v1, v2),
        ("Licencia de conducir", "por_vencer", pv1, pv2),
        ("Constancia ART", "vencido", ve1, ve2),
        ("Apto médico", "suceder", v1, v2),
    ]
    mapa_t3 = [
        ("Apto médico", "vigente", v1, v2),
        ("Licencia de conducir", "vigente", v1, v2),
        ("Constancia ART", "vigente", v1, v2),
    ]
    with tenant_session(est.tenant_id) as s:
        for n in (1, 2, 3):
            suj = est.sujetos[f"tecnico{n}"]
            mapa = mapa_t3 if n == 3 else mapa_t12
            for req, kind, d1, d2 in mapa:
                key = f"t{n}_{kind}_{req}"
                if kind == "propuesta":
                    tec = est.idn("tecnico", n)
                    pr = legajos.proponer_documento(
                        s,
                        tec,
                        leg_esq.ProponerDocumento(
                            sujeto_id=suj,
                            requisito_definicion_id=uuid.UUID(est.requisitos[req]),
                            vigente_desde=d1,
                            vigente_hasta=d2,
                        ),
                    )
                    est.documentos[key] = pr["documento_id"]
                elif kind == "suceder":
                    d_old = _cargar_doc(s, idn, suj, req, est, d1, d2 - timedelta(days=30))
                    d_new = _cargar_doc(s, idn, suj, req, est, d1 + timedelta(days=10), d2)
                    est.documentos[key] = d_new
                    est.documentos[f"{key}_old"] = d_old
                else:
                    est.documentos[key] = _cargar_doc(s, idn, suj, req, est, d1, d2)
        # recursos con al menos un vencido
        ve_doc = _cargar_doc(s, idn, est.sujetos["vehiculo1"], "VTV", est, ve1, ve2)
        est.documentos["vehiculo_vtv_vencido"] = ve_doc
        _cargar_doc(s, idn, est.sujetos["vehiculo2"], "Seguro automotor", est, v1, v2)
        eq_venc = _cargar_doc(s, idn, est.sujetos["equipo1"], "Certificación de equipo", est, ve1, ve2)
        est.documentos["equipo_cert_vencido"] = eq_venc
        _cargar_doc(s, idn, est.sujetos["empresa"], "ART empresa", est, v1, v2)
        rc_venc = _cargar_doc(s, idn, est.sujetos["empresa"], "Seguro de responsabilidad civil", est, ve1, ve2)
        est.documentos["empresa_rc_vencido"] = rc_venc


def _lineas_persona_matriz(est: EstadoTenant) -> list[req_esq.LineaDeMatriz]:
    reqs_linea = [
        est.requisitos["Apto médico"],
        est.requisitos["Licencia de conducir"],
        est.requisitos["Constancia ART"],
        est.requisitos.get("Inducción operadora") or est.requisitos["Apto médico"],
    ]
    return [
        req_esq.LineaDeMatriz(
            requisito_definicion_id=uuid.UUID(rid),
            clasificacion="bloqueante_duro",
            bloqueante_durante_ejecucion=True,
        )
        for rid in reqs_linea[:4]
    ]


def _lineas_recursos_matriz(est: EstadoTenant) -> list[req_esq.LineaDeMatriz]:
    return [
        req_esq.LineaDeMatriz(
            requisito_definicion_id=uuid.UUID(est.requisitos["VTV"]),
            clasificacion="bloqueante_duro",
            bloqueante_durante_ejecucion=True,
        ),
        req_esq.LineaDeMatriz(
            requisito_definicion_id=uuid.UUID(est.requisitos["Certificación de equipo"]),
            clasificacion="bloqueante_duro",
            bloqueante_durante_ejecucion=True,
        ),
        req_esq.LineaDeMatriz(
            requisito_definicion_id=uuid.UUID(est.requisitos["Seguro de responsabilidad civil"]),
            clasificacion="bloqueante_duro",
            bloqueante_durante_ejecucion=True,
        ),
    ]


def cargar_catalogos_y_matrices(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn_cfg = est.idn("configuracion", 1)
    glob = _globals_por_nombre("")
    hoy = hoy_tenant(est.tenant_id)
    with tenant_session(est.tenant_id) as s:
        for op in OPERADORAS:
            r = catalogos_maestros.alta_operadora(s, idn_cfg, op)
            est.catalogos[f"op_{op}"] = r["operadora_id"]
            for i in range(1, len(LOCACIONES_POR_OPERADORA[op]) + 1):
                loc = catalogos_maestros.alta_locacion(
                    s, idn_cfg, r["operadora_id"], nombre_locacion_demo(op, i)
                )
                est.catalogos[f"loc_{op}_{i}"] = loc["locacion_id"]
        for ts in TIPOS_SERVICIO:
            r = catalogos_maestros.alta_tipo_servicio(s, idn_cfg, ts)
            est.catalogos[f"ts_{ts}"] = r["tipo_servicio_id"]

        if "Inducción operadora" not in est.requisitos:
            loc_ind = est.catalogos["loc_YPF_1"]
            if est.spec.copiar_globales:
                gid = glob["def"].get(GLOBAL_A_DEMO["Inducción operadora"])
                if gid:
                    r = plantillas.copiar_definicion_global(
                        s,
                        idn_cfg,
                        req_esq.CopiarDefinicionGlobal(
                            definicion_global_id=uuid.UUID(gid),
                            locacion_id=uuid.UUID(loc_ind),
                        ),
                    )
                    est.requisitos["Inducción operadora"] = r["requisito_definicion_id"]
            else:
                r = req_svc.dar_de_alta_definicion_de_requisito(
                    s,
                    idn_cfg,
                    req_esq.DarDeAltaDefinicionDeRequisito(
                        nombre="Inducción operadora",
                        categoria="induccion",
                        tipo_sujeto_aplicable="persona",
                        locacion_id=uuid.UUID(loc_ind),
                    ),
                )
                est.requisitos["Inducción operadora"] = r["requisito_definicion_id"]

        lineas = _lineas_persona_matriz(est) + _lineas_recursos_matriz(est)

        combos = [
            ("YPF", 1, "Wireline"),
            ("Vista", 1, "Slickline"),
            ("Tecpetrol", 2, "Cementación"),
            ("Pluspetrol", 2, "Wireline"),  # sin matriz a propósito
        ]
        for op, loc_i, ts in combos:
            if op == "Pluspetrol" and ts == "Wireline":
                continue
            cid = est.catalogos[f"op_{op}"]
            lid = est.catalogos[f"loc_{op}_{loc_i}"]
            tid = est.catalogos[f"ts_{ts}"]
            lineas_publicar = lineas
            if est.spec.copiar_globales and op == "Vista" and ts == "Slickline":
                # Patagonia: inducción global atada a loc YPF no cierra bien en OC Vista (radar t3).
                lineas_publicar = _lineas_persona_matriz(est)[:3] + _lineas_recursos_matriz(est)
            if est.spec.copiar_globales and op == "YPF" and ts == "Wireline":
                mid = glob["mat"].get("YPF|servicios de campo")
                if mid:
                    plantillas.copiar_matriz_global(
                        s,
                        idn_cfg,
                        req_esq.CopiarMatrizGlobal(
                            matriz_global_id=uuid.UUID(mid),
                            cliente_id=uuid.UUID(cid),
                            locacion_id=uuid.UUID(lid),
                            tipo_servicio_id=uuid.UUID(tid),
                            vigente_desde=hoy - timedelta(days=400),
                        ),
                    )
                    continue
            req_svc.publicar_version_de_matriz(
                s,
                idn_cfg,
                req_esq.PublicarVersionDeMatriz(
                    cliente_id=uuid.UUID(cid),
                    locacion_id=uuid.UUID(lid),
                    tipo_servicio_id=uuid.UUID(tid),
                    vigente_desde=hoy - timedelta(days=180),
                    lineas=lineas_publicar,
                ),
            )
        # Matriz v2 YPF Wireline loc1 — agrega Seguro automotor (vehículo no aplica a persona OC; usa requisito persona extra)
        cid = est.catalogos["op_YPF"]
        lid = est.catalogos["loc_YPF_1"]
        tid = est.catalogos["ts_Wireline"]
        lineas_v2 = _lineas_persona_matriz(est) + _lineas_recursos_matriz(est) + [
            req_esq.LineaDeMatriz(
                requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                clasificacion="excepcionable",
                bloqueante_durante_ejecucion=False,
            )
        ]
        req_svc.publicar_version_de_matriz(
            s,
            idn_cfg,
            req_esq.PublicarVersionDeMatriz(
                cliente_id=uuid.UUID(cid),
                locacion_id=uuid.UUID(lid),
                tipo_servicio_id=uuid.UUID(tid),
                vigente_desde=hoy - timedelta(days=30),
                lineas=lineas_v2,
            ),
        )
        est.catalogos["combo_sin_matriz"] = f"{cid}|{est.catalogos['loc_Pluspetrol_2']}|{est.catalogos['ts_Wireline']}"


def cargar_ocs(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn = est.idn("responsable_legajos", 1)
    hoy = hoy_tenant(est.tenant_id)

    def _fila(clave: str, op: str, loc_i: int, ts: str, d1: date, d2: date) -> dict[str, Any]:
        return {
            "clave_origen": clave,
            "referencia": clave,
            "cliente_id": est.catalogos[f"op_{op}"],
            "locacion_id": est.catalogos[f"loc_{op}_{loc_i}"],
            "tipo_servicio_id": est.catalogos[f"ts_{ts}"],
            "vigencia_desde": d1.isoformat(),
            "vigencia_hasta": d2.isoformat(),
        }

    lote_base = uuid.uuid5(uuid.NAMESPACE_DNS, f"demo-oc-{est.spec.slug}")
    escenarios = [
        ("terminada", _fila(f"OC-{est.spec.slug}-TERM", "YPF", 1, "Wireline", *rango_oc_terminada(hoy))),
        ("en_curso", _fila(f"OC-{est.spec.slug}-CURSO", "Vista", 1, "Slickline", *rango_oc_en_curso(hoy))),
        ("futura", _fila(f"OC-{est.spec.slug}-FUT", "Pluspetrol", 2, "Wireline", *rango_oc_futura(hoy))),
        ("reprogramada", _fila(f"OC-{est.spec.slug}-REP", "YPF", 1, "Wireline", *rango_oc_en_curso(hoy))),
        ("sin_hab", _fila(f"OC-{est.spec.slug}-ROJO", "YPF", 1, "Wireline", *rango_oc_en_curso(hoy))),
        ("cancelada", _fila(f"OC-{est.spec.slug}-CANC", "Tecpetrol", 2, "Cementación", *rango_oc_futura(hoy))),
    ]
    with tenant_session(est.tenant_id) as s:
        for i, (nombre, fila) in enumerate(escenarios):
            lid = uuid.uuid5(lote_base, str(i))
            r = oc_svc.importar_lote_oc(s, idn, str(lid), "planilla", [fila])
            if r["oc_ids"]:
                est.ocs[nombre] = r["oc_ids"][0]
        if est.ocs.get("reprogramada"):
            d1, d2 = rango_oc_futura(hoy)
            oc_svc.reprogramar_oc(s, idn, est.ocs["reprogramada"], d1, d2, "Reprogramación demo")
        if est.ocs.get("cancelada"):
            oc_svc.cancelar_oc(s, idn, est.ocs["cancelada"], None)


def _subir(storage, s, idn, doc_id: str, sujeto: str, req: str, jpeg: bool = False) -> None:
    blob = jpg_demo(sujeto, req) if jpeg else pdf_demo(sujeto, req)
    ct = "image/jpeg" if jpeg else "application/pdf"
    name = "demo.jpg" if jpeg else "demo.pdf"
    preparar_subida(s, idn, doc_id, name, ct, storage=storage)
    fila = s.execute(text("SELECT clave_storage FROM modulo1.documento WHERE documento_id = :d"), {"d": doc_id}).scalar()
    storage.escribir(str(fila), blob)
    confirmar_subida(s, idn, doc_id, storage=storage)


def _marcar_archivo_valido(s, doc_id: str) -> None:
    s.execute(
        text(
            "UPDATE modulo1.documento SET archivo_validacion = 'valido', archivo_scan_estado = 'limpio' "
            "WHERE documento_id = CAST(:d AS uuid) AND archivo_estado = 'confirmado'"
        ),
        {"d": doc_id},
    )


def _confirmar_tras_archivo(s, idn, doc_id: str) -> None:
    """D19: tras subida confirmada, marcar archivo válido y verificar si sigue declarado."""
    _marcar_archivo_valido(s, doc_id)
    estado = s.execute(
        text("SELECT estado_confirmacion FROM modulo1.documento WHERE documento_id = CAST(:d AS uuid)"),
        {"d": doc_id},
    ).scalar()
    if estado != "declarado":
        return
    legajos.confirmar_documento(s, idn, leg_esq.ConfirmarDocumento(documento_id=uuid.UUID(doc_id)))


def _subir_y_verificar(storage, s, idn, doc_id: str, sujeto: str, req: str, jpeg: bool = False) -> None:
    version = s.execute(
        text("SELECT estado_version FROM modulo1.documento WHERE documento_id = CAST(:d AS uuid)"),
        {"d": doc_id},
    ).scalar()
    if version != "vigente":
        return
    _subir(storage, s, idn, doc_id, sujeto, req, jpeg=jpeg)
    _confirmar_tras_archivo(s, idn, doc_id)


def _sujeto_para_clave_doc(est: EstadoTenant, key: str) -> str:
    if key.startswith("vehiculo"):
        return est.sujetos["vehiculo1"]
    if key.startswith("equipo"):
        return est.sujetos["equipo1"]
    if key.startswith("empresa"):
        return est.sujetos["empresa"]
    if key.startswith("t1_"):
        return est.sujetos["tecnico1"]
    if key.startswith("t2_"):
        return est.sujetos["tecnico2"]
    if key.startswith("t3_"):
        return est.sujetos["tecnico3"]
    return est.sujetos["tecnico1"]


# Sin archivo en este paso: licencia t2 (archivo en revisión post-worker) o invalidación ART.
_EVIDENCIAS_SIN_ARCHIVO_EN_CARGA = frozenset(
    {
        "t2_por_vencer_Licencia de conducir",
        "t1_vencido_Constancia ART",
        "t2_vencido_Constancia ART",
    }
)

# Verificado sin archivo a propósito (demo «Sin archivo de respaldo»); no subir en evidencias.
_EVIDENCIAS_SIN_ARCHIVO_DEMO: frozenset[str] = frozenset()

_EVIDENCIAS_TECNICO3 = (
    "t3_vigente_Apto médico",
    "t3_vigente_Licencia de conducir",
    "t3_vigente_Constancia ART",
)

def _exigir_archivo_confirmado(s, tenant_id: str, doc_id: str) -> bool:
    fila = s.execute(
        text(
            "SELECT archivo_estado, estado_version FROM modulo1.documento "
            "WHERE tenant_id = :t AND documento_id = :d"
        ),
        {"t": tenant_id, "d": doc_id},
    ).first()
    if not fila or fila.estado_version != "vigente":
        return True
    return fila.archivo_estado == "confirmado"


def _apto_medico_vigente_id(s, est: EstadoTenant, sujeto_id: str) -> str | None:
    rid = est.requisitos["Apto médico"]
    return s.execute(
        text(
            "SELECT documento_id::text FROM modulo1.documento "
            "WHERE tenant_id = :t AND sujeto_id = :sj AND requisito_definicion_id = :r "
            "AND estado_version = 'vigente'"
        ),
        {"t": est.tenant_id, "sj": sujeto_id, "r": rid},
    ).scalar()


def cargar_evidencias_y_propuestas(est: EstadoTenant, storage, ctx: SemillaContext) -> None:
    from app.modules.evidencia import servicio as ev_svc

    idn = est.idn("responsable_legajos", 1)
    for key in sorted(_EVIDENCIAS_SIN_ARCHIVO_EN_CARGA):
        if key in est.documentos:
            if key == "t2_por_vencer_Licencia de conducir":
                ctx.notas.append(
                    "evidencias: licencia técnico 2 sin archivo en carga; post-worker queda «archivo en revisión» "
                    "(técnicos 1 y 2: licencia por vencer sin propuesta propia; bandeja con propuestas de otros)"
                )
            else:
                ctx.notas.append(
                    f"evidencias: {key} sin archivo en carga (invalidación ART más abajo)"
                )
    if "empresa_rc_vencido" in est.documentos:
        ctx.notas.append(
            "evidencias: Seguro RC vencido de empresa se verifica vía confirmar_documento tras subir archivo (vigencia vencida demo)"
        )
    with tenant_session(est.tenant_id) as s:
        ya_subidos: set[str] = set()
        for key in _EVIDENCIAS_TECNICO3:
            doc_id = est.documentos.get(key)
            if not doc_id:
                continue
            suj = _sujeto_para_clave_doc(est, key)
            _subir_y_verificar(storage, s, idn, doc_id, suj, key)
            ya_subidos.add(key)
        for key, doc_id in est.documentos.items():
            if (
                "old" in key
                or key in _EVIDENCIAS_SIN_ARCHIVO_EN_CARGA
                or key in _EVIDENCIAS_SIN_ARCHIVO_DEMO
                or key in ya_subidos
            ):
                continue
            suj = _sujeto_para_clave_doc(est, key)
            _subir_y_verificar(storage, s, idn, doc_id, suj, key, jpeg="vehiculo" in key or "equipo" in key)
            ya_subidos.add(key)
        inv = est.documentos.get("t1_vencido_Constancia ART")
        if inv:
            _subir_y_verificar(storage, s, idn, inv, est.sujetos["tecnico1"], "Constancia ART")
            ev_svc.invalidar_evidencia_verificada(s, idn, documento_id=inv, motivo="Evidencia demo invalidada")
        inv_rep = est.documentos.get("t2_vencido_Constancia ART")
        if inv_rep:
            _subir_y_verificar(storage, s, idn, inv_rep, est.sujetos["tecnico2"], "Constancia ART")
            ev_svc.invalidar_evidencia_verificada(s, idn, documento_id=inv_rep, motivo="Invalidada demo — reemplazo")
            _subir(storage, s, idn, inv_rep, est.sujetos["tecnico2"], "Constancia ART reemplazo")
        sin_archivo: list[str] = []
        for key, doc_id in est.documentos.items():
            if (
                "old" in key
                or "propuesta" in key
                or key in _EVIDENCIAS_SIN_ARCHIVO_EN_CARGA
                or key in _EVIDENCIAS_SIN_ARCHIVO_DEMO
            ):
                continue
            if not _exigir_archivo_confirmado(s, est.tenant_id, doc_id):
                sin_archivo.append(key)
        if sin_archivo:
            ctx.fallas.append(
                f"evidencias: documentos sin archivo confirmado: {', '.join(sorted(sin_archivo))}"
            )
        hoy = hoy_tenant(est.tenant_id)
        v1, v2 = rango_vigente(hoy)
        # rechazadas (no cuentan en propuestas pendientes)
        for n in (1, 2):
            pr = legajos.proponer_documento(
                s,
                est.idn("tecnico", n),
                leg_esq.ProponerDocumento(
                    sujeto_id=est.sujetos[f"tecnico{n}"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Constancia ART"]),
                    vigente_desde=hoy,
                    vigente_hasta=hoy + timedelta(days=200),
                ),
            )
            legajos.rechazar_propuesta(s, idn, leg_esq.RechazarPropuesta(documento_id=uuid.UUID(pr["documento_id"]), motivo="Rechazo demo"))
        # Flujo C demo: María y Juan con licencia por vencer SIN propuesta; bandeja con otros técnicos.
        pr_t3_lic = legajos.proponer_documento(
            s,
            est.idn("tecnico", 3),
            leg_esq.ProponerDocumento(
                sujeto_id=est.sujetos["tecnico3"],
                requisito_definicion_id=uuid.UUID(est.requisitos["Licencia de conducir"]),
                vigente_desde=hoy,
                vigente_hasta=v2 + timedelta(days=400),
            ),
        )
        est.documentos["t3_propuesta_Licencia de conducir"] = pr_t3_lic["documento_id"]
        _subir(storage, s, idn, pr_t3_lic["documento_id"], est.sujetos["tecnico3"], "Licencia propuesta t3")
        pr_t3_art = legajos.proponer_documento(
            s,
            est.idn("tecnico", 3),
            leg_esq.ProponerDocumento(
                sujeto_id=est.sujetos["tecnico3"],
                requisito_definicion_id=uuid.UUID(est.requisitos["Constancia ART"]),
                vigente_desde=hoy,
                vigente_hasta=hoy + timedelta(days=200),
            ),
        )
        est.documentos["t3_propuesta_Constancia ART"] = pr_t3_art["documento_id"]


def _certificado_respaldo_valido(storage, s, idn, persona_id: str, etiqueta: str) -> str:
    """Shell certificado_respaldo con archivo confirmado y validación válida (E-97)."""
    r = legajos.crear_certificado_respaldo(s, idn, leg_esq.CrearCertificadoRespaldo(persona_id=persona_id))
    cert_id = r["certificado_documento_id"]
    _subir_y_verificar(storage, s, idn, cert_id, persona_id, etiqueta)
    return cert_id


def consolidar_evidencias_tecnico3_post_worker(est: EstadoTenant) -> None:
    """Marca archivos del técnico 3 como validados (radar sin información incompleta)."""
    with tenant_session(est.tenant_id) as s:
        s.execute(
            text(
                "UPDATE modulo1.documento SET archivo_validacion = 'valido', "
                "archivo_validacion_motivo = 'Validación demo técnico 3', archivo_scan_estado = 'limpio' "
                "WHERE tenant_id = :t AND sujeto_id = :s "
                "AND archivo_validacion IS DISTINCT FROM 'valido'"
            ),
            {"t": est.tenant_id, "s": est.sujetos["tecnico3"]},
        )
        s.execute(
            text(
                "UPDATE modulo1.documento d SET archivo_validacion = 'valido', "
                "archivo_validacion_motivo = 'Validación demo técnico 3 (inducción)', archivo_scan_estado = 'limpio' "
                "FROM modulo1.definicion_requisito r "
                "WHERE d.tenant_id = :t AND d.sujeto_id = :s AND d.tenant_id = r.tenant_id "
                "AND d.requisito_definicion_id = r.requisito_definicion_id AND r.categoria = 'induccion' "
                "AND d.archivo_validacion IS DISTINCT FROM 'valido'"
            ),
            {"t": est.tenant_id, "s": est.sujetos["tecnico3"]},
        )


def sembrar_bandeja_pendiente_post_worker(est: EstadoTenant, storage) -> None:
    """Dos evidencias confirmadas con validación pendiente (después del worker en sembrar_demo)."""
    idn = est.idn("responsable_legajos", 1)
    with tenant_session(est.tenant_id) as s:
        for key in ("t2_por_vencer_Licencia de conducir",):
            if key not in est.documentos:
                continue
            doc = est.documentos[key]
            suj = _sujeto_para_clave_doc(est, key)
            preparar_subida(s, idn, doc, "pendiente.pdf", "application/pdf", storage=storage)
            fila = s.execute(text("SELECT clave_storage FROM modulo1.documento WHERE documento_id = :d"), {"d": doc}).scalar()
            storage.escribir(str(fila), pdf_demo(suj, key))
            confirmar_subida(s, idn, doc, storage=storage)


def cargar_lotes_competencias(est: EstadoTenant, storage, ctx: SemillaContext) -> None:
    idn = est.idn("responsable_legajos", 1)
    hoy = hoy_tenant(est.tenant_id)
    v1, v2 = rango_vigente(hoy)
    ve1, ve2 = rango_vencido(hoy)
    with tenant_session(est.tenant_id) as s:
        lote_ok = uuid.uuid5(uuid.NAMESPACE_DNS, f"lote-doc-{est.spec.slug}")
        filas = []
        for i in range(5):
            # Solo t1/t2: un apto de lote sobre t3 dejaba el radar en pendiente_revision.
            suj = est.sujetos[f"tecnico{(i % 2) + 1}"]
            req = est.requisitos["Apto médico"]
            filas.append(
                {
                    "sujeto_id": suj,
                    "requisito_definicion_id": req,
                    "vigente_desde": v1.isoformat(),
                    "vigente_hasta": (v2 + timedelta(days=i + 1)).isoformat(),
                }
            )
        legajos.importar_lote(s, idn, leg_esq.ImportarLote(lote_id=lote_ok, filas=filas))
        lote_rev = uuid.uuid5(uuid.NAMESPACE_DNS, f"lote-rev-{est.spec.slug}")
        legajos.importar_lote(
            s,
            idn,
            leg_esq.ImportarLote(
                lote_id=lote_rev,
                filas=[
                    {
                        "sujeto_id": est.sujetos["tecnico2"],
                        "requisito_definicion_id": est.requisitos["Constancia ART"],
                        "vigente_desde": v1.isoformat(),
                        "vigente_hasta": v2.isoformat(),
                    }
                ],
            ),
        )
        legajos.revertir_lote(s, idn, leg_esq.RevertirLote(lote_id=lote_rev))
        doc_t1 = _apto_medico_vigente_id(s, est, est.sujetos["tecnico1"])
        doc_t2 = _apto_medico_vigente_id(s, est, est.sujetos["tecnico2"])
        doc_t3 = _apto_medico_vigente_id(s, est, est.sujetos["tecnico3"])
        for doc_id, suj, etiqueta in (
            (doc_t1, est.sujetos["tecnico1"], "Apto médico t1"),
            (doc_t2, est.sujetos["tecnico2"], "Apto médico t2"),
            (doc_t3, est.sujetos["tecnico3"], "Apto médico t3"),
        ):
            if not doc_id:
                continue
            if _exigir_archivo_confirmado(s, est.tenant_id, doc_id):
                _marcar_archivo_valido(s, doc_id)
                continue
            _subir_y_verificar(storage, s, idn, doc_id, suj, etiqueta)
        if doc_t1:
            cert_t1_comp = _certificado_respaldo_valido(
                storage, s, idn, est.sujetos["tecnico1"], "Certificado manejo defensivo t1"
            )
            acr_t1 = legajos.registrar_acreditacion_de_competencia(
                s,
                idn,
                leg_esq.RegistrarAcreditacionDeCompetencia(
                    persona_id=est.sujetos["tecnico1"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                    vigente_desde=v1,
                    vigente_hasta=v2,
                    certificado_documento_id=uuid.UUID(cert_t1_comp),
                ),
            )
            est.documentos["t1_competencia_Manejo defensivo"] = acr_t1["acreditacion_id"]
        if doc_t2:
            cert_t2_comp = _certificado_respaldo_valido(
                storage, s, idn, est.sujetos["tecnico2"], "Certificado manejo defensivo t2"
            )
            acr_t2 = legajos.registrar_acreditacion_de_competencia(
                s,
                idn,
                leg_esq.RegistrarAcreditacionDeCompetencia(
                    persona_id=est.sujetos["tecnico2"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                    vigente_desde=ve1,
                    vigente_hasta=ve2,
                    certificado_documento_id=uuid.UUID(cert_t2_comp),
                ),
            )
            est.documentos["t2_competencia_Manejo defensivo"] = acr_t2["acreditacion_id"]
        loc_ind = est.catalogos.get("loc_YPF_1")
        req_ind = est.requisitos.get("Inducción operadora", est.requisitos["Apto médico"])
        if loc_ind and doc_t1:
            cert_t1_ind = _certificado_respaldo_valido(
                storage, s, idn, est.sujetos["tecnico1"], "Certificado inducción operadora t1"
            )
            ind_t1 = legajos.registrar_induccion(
                s,
                idn,
                leg_esq.RegistrarInduccion(
                    persona_id=est.sujetos["tecnico1"],
                    locacion_id=uuid.UUID(loc_ind),
                    requisito_definicion_id=uuid.UUID(req_ind),
                    vigente_desde=v1,
                    vigente_hasta=v2,
                    certificado_documento_id=uuid.UUID(cert_t1_ind),
                ),
            )
            est.documentos["t1_induccion_Inducción operadora"] = ind_t1["induccion_id"]
        # Lucía (t3): manejo defensivo con certificado propio; sin inducción (caso E-91 en demo).
        if doc_t3:
            cert_t3_comp = _certificado_respaldo_valido(
                storage, s, idn, est.sujetos["tecnico3"], "Certificado manejo defensivo t3"
            )
            acr_t3 = legajos.registrar_acreditacion_de_competencia(
                s,
                idn,
                leg_esq.RegistrarAcreditacionDeCompetencia(
                    persona_id=est.sujetos["tecnico3"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                    vigente_desde=v1,
                    vigente_hasta=v2,
                    certificado_documento_id=uuid.UUID(cert_t3_comp),
                ),
            )
            est.documentos["t3_competencia_Manejo defensivo"] = acr_t3["acreditacion_id"]
        oc_id = est.ocs.get("en_curso")
        if oc_id:
            fila_oc = s.execute(
                text("SELECT clave_origen FROM modulo1.oc WHERE oc_id = :o"), {"o": oc_id}
            ).scalar()
            req_svc.cargar_requisito_particular(
                s,
                idn,
                req_esq.CargarRequisitoParticular(
                    commitment_id=str(fila_oc),
                    requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                    clasificacion="bloqueante_duro",
                    bloqueante_durante_ejecucion=True,
                ),
            )


def asignar_supervisores(est: EstadoTenant, ctx: SemillaContext) -> None:
    if not hasattr(legajos, "asignar_supervisor"):
        ctx.notas.append("asignar_supervisor: función no disponible")
        return
    idn = est.idn("responsable_legajos", 1)
    sup1 = est.uid("supervisor", 1)
    sup2 = est.uid("supervisor", 2)
    sup3 = est.uid("supervisor", 3)
    hoy = hoy_tenant(est.tenant_id)
    with tenant_session(est.tenant_id) as s:
        for n in (1, 2):
            legajos.asignar_supervisor(
                s,
                idn,
                leg_esq.AsignarSupervisor(
                    sujeto_id=est.sujetos[f"tecnico{n}"],
                    supervisor_usuario_id=uuid.UUID(sup1.usuario_id),
                    desde=hoy,
                ),
            )
        legajos.asignar_supervisor(
            s,
            idn,
            leg_esq.AsignarSupervisor(
                sujeto_id=est.sujetos["tecnico3"],
                supervisor_usuario_id=uuid.UUID(sup2.usuario_id),
                desde=hoy,
            ),
        )
    est.notas_supervisor[sup1.email] = "supervisión: técnico1, técnico2"
    est.notas_supervisor[sup2.email] = "supervisión: técnico3"
    est.notas_supervisor[sup3.email] = "sin asignaciones (vacío a propósito)"


def configurar_alertas_y_paquetes(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn_cfg = est.idn("configuracion", 1)
    with tenant_session(est.tenant_id) as s:
        notif_svc.configurar_canales(s, idn_cfg, mail_habilitado=False, telegram_habilitado=False)
        alertas_svc.configurar(
            s,
            idn_cfg,
            plazo_aviso_dias=30,
            escalamiento_dias=7,
            rol_escalamiento="responsable_legajos",
            reconocimiento_dias=3,
        )
    # paquetes
    idn = est.idn("responsable_legajos", 1)
    with tenant_session(est.tenant_id) as s:
        vig = paquete_svc.generar_paquete(
            s, idn, sujeto_id=est.sujetos["tecnico3"], dias_validez=30, base_url="http://localhost:8000"
        )
        est.paquete_vigente_url = vig["url"]
        rev = paquete_svc.generar_paquete(s, idn, sujeto_id=est.sujetos["tecnico2"], dias_validez=7, base_url="http://localhost:8000")
        paquete_svc.revocar_paquete(s, idn, paquete_id=rev["paquete_id"])


def sembrar_tenant(est: EstadoTenant, storage, ctx: SemillaContext) -> None:
    _run("requisitos", lambda: cargar_requisitos(est, ctx), ctx)
    _run("sujetos", lambda: cargar_sujetos(est, ctx), ctx)
    _run("catalogos_matrices", lambda: cargar_catalogos_y_matrices(est, ctx), ctx)
    _run("documentos", lambda: cargar_documentos_tecnicos(est, ctx), ctx)
    _run("ocs", lambda: cargar_ocs(est, ctx), ctx)
    _run("evidencias", lambda: cargar_evidencias_y_propuestas(est, storage, ctx), ctx)
    _run("lotes", lambda: cargar_lotes_competencias(est, storage, ctx), ctx)
    _run("supervisores", lambda: asignar_supervisores(est, ctx), ctx)
    _run("alertas_paquetes", lambda: configurar_alertas_y_paquetes(est, ctx), ctx)
