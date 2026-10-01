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
    GLOBAL_A_DEMO,
    LOCACIONES_POR_OPERADORA,
    OPERADORAS,
    REQUISITOS_LOCALES,
    TIPOS_SERVICIO,
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
    saltados: list[str] = field(default_factory=list)
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
                leg_esq.AltaDeSujeto(tipo_sujeto="persona", identificador_natural=f"DNI demo {n}", sujeto_id=sid),
            )
        extra = f"persona_{est.spec.slug.replace('-', '_')}_baja"
        est.sujetos["tecnico_baja"] = extra
        legajos.alta_de_sujeto(
            s, idn, leg_esq.AltaDeSujeto(tipo_sujeto="persona", identificador_natural="Técnico dado de baja", sujeto_id=extra)
        )
        legajos.baja_de_sujeto(s, idn, leg_esq.BajaDeSujeto(sujeto_id=extra))
        for i, pat in enumerate(("AB100DE", "CD200FG"), 1):
            vid = f"vehiculo_{est.spec.slug.replace('-', '_')}_{i}"
            est.sujetos[f"vehiculo{i}"] = vid
            legajos.alta_de_sujeto(s, idn, leg_esq.AltaDeSujeto(tipo_sujeto="vehiculo", identificador_natural=pat, sujeto_id=vid))
        eq = f"equipo_{est.spec.slug.replace('-', '_')}_1"
        est.sujetos["equipo1"] = eq
        legajos.alta_de_sujeto(s, idn, leg_esq.AltaDeSujeto(tipo_sujeto="equipo", identificador_natural="WINCH-DEMO-01", sujeto_id=eq))
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
    mapa = [
        ("Apto médico", "vigente", v1, v2),
        ("Licencia de conducir", "por_vencer", pv1, pv2),
        ("Constancia ART", "vencido", ve1, ve2),
        ("Apto médico", "suceder", v1, v2),
    ]
    with tenant_session(est.tenant_id) as s:
        for n in (1, 2, 3):
            suj = est.sujetos[f"tecnico{n}"]
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
        _cargar_doc(s, idn, est.sujetos["equipo1"], "Certificación de equipo", est, ve1, ve2)
        _cargar_doc(s, idn, est.sujetos["empresa"], "ART empresa", est, v1, v2)
        _cargar_doc(s, idn, est.sujetos["empresa"], "Seguro de responsabilidad civil", est, ve1, ve2)


def cargar_catalogos_y_matrices(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn_cfg = est.idn("configuracion", 1)
    glob = _globals_por_nombre("")
    hoy = hoy_tenant(est.tenant_id)
    with tenant_session(est.tenant_id) as s:
        for op in OPERADORAS:
            r = catalogos_maestros.alta_operadora(s, idn_cfg, op)
            est.catalogos[f"op_{op}"] = r["operadora_id"]
            for i in range(1, LOCACIONES_POR_OPERADORA + 1):
                loc = catalogos_maestros.alta_locacion(s, idn_cfg, r["operadora_id"], f"{op} — Locación {i}")
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

        reqs_linea = [
            est.requisitos["Apto médico"],
            est.requisitos["Licencia de conducir"],
            est.requisitos["Constancia ART"],
            est.requisitos.get("Inducción operadora") or est.requisitos["Apto médico"],
        ]
        lineas = [
            req_esq.LineaDeMatriz(
                requisito_definicion_id=uuid.UUID(rid),
                clasificacion="bloqueante_duro",
                bloqueante_durante_ejecucion=True,
            )
            for rid in reqs_linea[:4]
        ]

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
                    lineas=lineas,
                ),
            )
        # Matriz v2 YPF Wireline loc1 — agrega Seguro automotor (vehículo no aplica a persona OC; usa requisito persona extra)
        cid = est.catalogos["op_YPF"]
        lid = est.catalogos["loc_YPF_1"]
        tid = est.catalogos["ts_Wireline"]
        lineas_v2 = lineas + [
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


def _sujeto_para_clave_doc(est: EstadoTenant, key: str) -> str:
    if key.startswith("vehiculo"):
        return est.sujetos["vehiculo1"]
    if key.startswith("t1_"):
        return est.sujetos["tecnico1"]
    if key.startswith("t2_"):
        return est.sujetos["tecnico2"]
    if key.startswith("t3_"):
        return est.sujetos["tecnico3"]
    return est.sujetos["tecnico1"]


# Un solo flujo preparar → PUT → confirmar por documento (sin re-subir el mismo doc).
_EVIDENCIAS_RESERVADAS = frozenset(
    {
        "t1_vigente_Apto médico",
        "t2_vigente_Apto médico",
        "t1_vencido_Constancia ART",
        "t2_vencido_Constancia ART",
    }
)


def cargar_evidencias_y_propuestas(est: EstadoTenant, storage, ctx: SemillaContext) -> None:
    from app.modules.evidencia import servicio as ev_svc

    idn = est.idn("responsable_legajos", 1)
    with tenant_session(est.tenant_id) as s:
        subidos = 0
        for key, doc_id in est.documentos.items():
            if "old" in key or key in _EVIDENCIAS_RESERVADAS:
                continue
            if subidos >= 6:
                break
            suj = _sujeto_para_clave_doc(est, key)
            _subir(storage, s, idn, doc_id, suj, key, jpeg="vehiculo" in key)
            subidos += 1
        inv = est.documentos.get("t1_vencido_Constancia ART")
        if inv:
            _subir(storage, s, idn, inv, est.sujetos["tecnico1"], "Constancia ART")
            ev_svc.invalidar_evidencia_verificada(s, idn, documento_id=inv, motivo="Evidencia demo invalidada")
        inv_rep = est.documentos.get("t2_vencido_Constancia ART")
        if inv_rep:
            _subir(storage, s, idn, inv_rep, est.sujetos["tecnico2"], "Constancia ART")
            ev_svc.invalidar_evidencia_verificada(s, idn, documento_id=inv_rep, motivo="Invalidada demo — reemplazo")
            _subir(storage, s, idn, inv_rep, est.sujetos["tecnico2"], "Constancia ART reemplazo")
        # propuesta desde lote (declarado)
        lote_prop = uuid.uuid5(uuid.NAMESPACE_DNS, f"prop-lote-{est.spec.slug}")
        legajos.importar_lote(
            s,
            idn,
            leg_esq.ImportarLote(
                lote_id=lote_prop,
                filas=[
                    {
                        "sujeto_id": est.sujetos["tecnico2"],
                        "requisito_definicion_id": est.requisitos["Inducción operadora"],
                        "vigente_desde": hoy_tenant(est.tenant_id).isoformat(),
                        "vigente_hasta": (hoy_tenant(est.tenant_id) + timedelta(days=300)).isoformat(),
                        "estado_confirmacion": "declarado",
                    }
                ],
            ),
        )
        # rechazadas
        for n in (1, 2):
            pr = legajos.proponer_documento(
                s,
                est.idn("tecnico", n),
                leg_esq.ProponerDocumento(
                    sujeto_id=est.sujetos[f"tecnico{n}"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Licencia de conducir"]),
                    vigente_desde=hoy_tenant(est.tenant_id),
                    vigente_hasta=hoy_tenant(est.tenant_id) + timedelta(days=200),
                ),
            )
            legajos.rechazar_propuesta(s, idn, leg_esq.RechazarPropuesta(documento_id=uuid.UUID(pr["documento_id"]), motivo="Rechazo demo"))


def sembrar_bandeja_pendiente_post_worker(est: EstadoTenant, storage) -> None:
    """Dos evidencias confirmadas con validación pendiente (después del worker en sembrar_demo)."""
    idn = est.idn("responsable_legajos", 1)
    with tenant_session(est.tenant_id) as s:
        for key in ("t1_vigente_Apto médico", "t2_vigente_Apto médico"):
            if key not in est.documentos:
                continue
            doc = est.documentos[key]
            suj = _sujeto_para_clave_doc(est, key)
            preparar_subida(s, idn, doc, "pendiente.pdf", "application/pdf", storage=storage)
            fila = s.execute(text("SELECT clave_storage FROM modulo1.documento WHERE documento_id = :d"), {"d": doc}).scalar()
            storage.escribir(str(fila), pdf_demo(suj, key))
            confirmar_subida(s, idn, doc, storage=storage)


def cargar_lotes_competencias(est: EstadoTenant, ctx: SemillaContext) -> None:
    idn = est.idn("responsable_legajos", 1)
    hoy = hoy_tenant(est.tenant_id)
    v1, v2 = rango_vigente(hoy)
    ve1, ve2 = rango_vencido(hoy)
    with tenant_session(est.tenant_id) as s:
        lote_ok = uuid.uuid5(uuid.NAMESPACE_DNS, f"lote-doc-{est.spec.slug}")
        filas = []
        for i in range(5):
            suj = est.sujetos[f"tecnico{(i % 3) + 1}"]
            req = est.requisitos["Apto médico"]
            filas.append(
                {
                    "sujeto_id": suj,
                    "requisito_definicion_id": req,
                    "vigente_desde": v1.isoformat(),
                    "vigente_hasta": (v2 + timedelta(days=i)).isoformat(),
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
        doc_t1 = est.documentos.get("t1_vigente_Apto médico")
        doc_t2 = est.documentos.get("t2_vigente_Apto médico")
        doc_t3 = est.documentos.get("t3_vigente_Apto médico")
        if doc_t1:
            legajos.registrar_acreditacion_de_competencia(
                s,
                idn,
                leg_esq.RegistrarAcreditacionDeCompetencia(
                    persona_id=est.sujetos["tecnico1"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                    vigente_desde=v1,
                    vigente_hasta=v2,
                    evidencias=[uuid.UUID(doc_t1)],
                ),
            )
        if doc_t2:
            legajos.registrar_acreditacion_de_competencia(
                s,
                idn,
                leg_esq.RegistrarAcreditacionDeCompetencia(
                    persona_id=est.sujetos["tecnico2"],
                    requisito_definicion_id=uuid.UUID(est.requisitos["Curso de manejo defensivo"]),
                    vigente_desde=ve1,
                    vigente_hasta=ve2,
                    evidencias=[uuid.UUID(doc_t2)],
                ),
            )
        loc_ind = est.catalogos.get("loc_YPF_1")
        req_ind = est.requisitos.get("Inducción operadora", est.requisitos["Apto médico"])
        if loc_ind and doc_t1:
            legajos.registrar_induccion(
                s,
                idn,
                leg_esq.RegistrarInduccion(
                    persona_id=est.sujetos["tecnico1"],
                    locacion_id=uuid.UUID(loc_ind),
                    requisito_definicion_id=uuid.UUID(req_ind),
                    vigente_desde=v1,
                    vigente_hasta=v2,
                    evidencia=uuid.UUID(doc_t1),
                ),
            )
        if loc_ind and doc_t3:
            legajos.registrar_induccion(
                s,
                idn,
                leg_esq.RegistrarInduccion(
                    persona_id=est.sujetos["tecnico3"],
                    locacion_id=uuid.UUID(loc_ind),
                    requisito_definicion_id=uuid.UUID(req_ind),
                    vigente_desde=ve1,
                    vigente_hasta=ve2,
                    evidencia=uuid.UUID(doc_t3),
                ),
            )
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
        ctx.saltados.append("asignar_supervisor: función no disponible")
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
    _run("lotes", lambda: cargar_lotes_competencias(est, ctx), ctx)
    _run("supervisores", lambda: asignar_supervisores(est, ctx), ctx)
    _run("alertas_paquetes", lambda: configurar_alertas_y_paquetes(est, ctx), ctx)
