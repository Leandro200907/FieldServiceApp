"""Política de revaluación (A-07) — implementación declarativa de la tabla 7.2 de
especificacion.md y de 2.2 / 2.9 de modelo-dominio.md.

Regla única (2.2): "cambio en cualquier entrada del snapshot de una decisión vigente →
marcar la decisión afectada → HabilitacionRequiereRevaluacion". Este módulo es el ÚNICO
lugar donde se decide qué evento marca qué decisiones: `EVENTOS_FUENTE` mapea cada
evento fuente a su selector; todo lo que no está en el mapa no genera nada (negativos
de 7.2: DocumentoCargado, DocumentoRechazado, DocumentoSucedido, Acreditación/Inducción
registradas, LoteAplicado, LegajoCreado, Supervisor*, DefinicionDeRequisito*,
EvaluacionDeHabilitacionRealizada, TareaDeRegularizacionCreada, CustodiaCorregida,
ConstanciaReemplazada, Alerta*, ArchivoPurgado, Aviso*, CumplimientoEmpresa*).

Definiciones:
- DECISIÓN VIGENTE: la última decisión persistida de un commitment (ORDER BY creado_en
  DESC, secuencia DESC — `secuencia` desempata de forma determinista e inmutable;
  creado_en lo genera la base) con OC activa y vigencia_hasta >= hoy del tenant.
- MARCAR: abrir un `aviso_revaluacion` para esa referencia (uno abierto por evaluación,
  coalescing: si ya existe se suma la causa y NO se emite nada) y, al abrir, encolar UN
  `HabilitacionRequiereRevaluacion` con clave_dedup `hrr:{referencia}:{aviso_id}`.
  Nunca se crea una decisión nueva: "sólo el módulo 2 solicita y registra una decisión".
- IDEMPOTENCIA POR EVENTO CAUSAL: cada (tenant_id, evento_id) pasa por la política una
  sola vez (`politica_evento_procesado`, INSERT … ON CONFLICT DO NOTHING). Reprocesar un
  evento antiguo después de que una decisión nueva cerró el aviso no reabre nada.

Semántica para el consumidor (payload versionado, 7.1: aviso flaco): "esta decisión puede
estar desactualizada". `tipo_cambio = cancelacion` ⇒ invalidar. Nunca es una solicitud
de crear una decisión asignable.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.comun.eventos import encolar_outbox, registrar_evento_interno
from app.comun.reloj import ahora_utc, hoy_del_tenant

Afectada = dict[str, Any]  # {referencia_evaluacion, commitment_id, entidad_tipo, entidad_id, tipo_cambio?}
Selector = Callable[[Session, str, dict[str, Any], date], list[Afectada]]

# ------------------------------------------------------------------ decisiones vigentes

_SQL_VIGENTES = """
    WITH ultimas AS (
        SELECT DISTINCT ON (e.commitment_id) e.referencia_evaluacion, e.commitment_id, e.origen_sujetos,
               e.version_matriz->>'matriz_version_id' AS matriz_version_id, e.creado_en, e.secuencia
        FROM modulo1.evaluacion_habilitacion e
        WHERE e.tenant_id = :t {filtro_commitment}
        ORDER BY e.commitment_id, e.creado_en DESC, e.secuencia DESC
    )
    SELECT u.referencia_evaluacion, u.commitment_id
    FROM ultimas u
    JOIN modulo1.oc o ON o.tenant_id = :t AND o.clave_origen = u.commitment_id
    WHERE o.estado = 'activo' AND o.vigencia_hasta >= :hoy {filtro_extra}
    ORDER BY u.commitment_id
"""


def _vigentes(
    session: Session, tenant_id: str, hoy: date, *, filtro_extra: str = "", filtro_commitment: str = "",
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sql = _SQL_VIGENTES.format(filtro_extra=filtro_extra, filtro_commitment=filtro_commitment)
    return [dict(f) for f in session.execute(text(sql), {"t": tenant_id, "hoy": hoy, **(params or {})}).mappings()]


_PROPONE = (
    " AND EXISTS (SELECT 1 FROM modulo1.evaluacion_sujeto_propuesto p "
    "WHERE p.tenant_id = :t AND p.evaluacion_id = u.referencia_evaluacion AND p.sujeto_id = ANY(CAST(:sujetos AS text[])))"
)


def _es_empresa(session: Session, tenant_id: str, sujeto_id: str) -> bool:
    return session.execute(
        text("SELECT tipo_sujeto = 'empresa' FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s"),
        {"t": tenant_id, "s": sujeto_id},
    ).scalar() is True


def _por_sujetos(session, tenant_id, hoy, sujetos: list[str], entidad_tipo: str, entidad_id: str) -> list[Afectada]:
    if not sujetos:
        return []
    if any(_es_empresa(session, tenant_id, s) for s in sujetos):
        filas = _vigentes(session, tenant_id, hoy)  # la empresa es entrada de TODAS las decisiones (1.8)
    else:
        filas = _vigentes(session, tenant_id, hoy, filtro_extra=_PROPONE, params={"sujetos": sujetos})
    return [{**f, "entidad_tipo": entidad_tipo, "entidad_id": entidad_id} for f in filas]


# ------------------------------------------------------------------ selectores (una fila por evento de 7.2)

def _sel_documento_verificado(session, t, p, hoy):
    afectadas = _por_sujetos(session, t, hoy, [p["sujeto_id"]], "documento", str(p["documento_id"]))
    if _es_empresa(session, t, p["sujeto_id"]):
        from app.core.incumplimiento_empresa import reevaluar_causas

        reevaluar_causas(session, t, hoy)
    return afectadas


def _sel_lote_revertido(session, t, p, hoy):
    docs = [str(d) for d in p.get("documentos_revertidos", [])]
    if not docs:
        return []
    sujetos = [str(x) for x in session.execute(
        text("SELECT DISTINCT sujeto_id FROM modulo1.documento WHERE tenant_id = :t AND documento_id = ANY(CAST(:d AS uuid[]))"),
        {"t": t, "d": docs},
    ).scalars()]
    return _por_sujetos(session, t, hoy, sujetos, "lote_importacion", str(p["lote_id"]))


def _sel_legajo_baja(session, t, p, hoy):
    return _por_sujetos(session, t, hoy, [p["sujeto_id"]], "legajo", str(p["sujeto_id"]))


def _sel_matriz_publicada(session, t, p, hoy):
    anterior = p.get("version_anterior_id")
    if not anterior:
        return []
    filas = _vigentes(session, t, hoy, filtro_extra=" AND u.matriz_version_id = :mv", params={"mv": str(anterior)})
    return [{**f, "entidad_tipo": "matriz_requisitos", "entidad_id": str(p["matriz_version_id"])} for f in filas]


def _sel_requisito_particular(session, t, p, hoy):
    filas = _vigentes(session, t, hoy, filtro_commitment=" AND e.commitment_id = :c", params={"c": p["commitment_id"]})
    return [{**f, "entidad_tipo": "requisito_particular", "entidad_id": str(p["requisito_particular_id"])} for f in filas]


def _sel_excepcion(session, t, p, hoy):
    exc = session.execute(
        text("SELECT x.referencia_evaluacion, x.sujeto_id, x.commitment_id, "
             "       EXISTS (SELECT 1 FROM modulo1.evaluacion_habilitacion e WHERE e.tenant_id = :t "
             "               AND e.referencia_evaluacion = x.referencia_evaluacion) AS decision_existe "
             "FROM modulo1.excepcion x WHERE x.tenant_id = :t AND x.excepcion_id = :e"),
        {"t": t, "e": str(p["excepcion_id"])},
    ).mappings().first()
    if exc is None:
        return []
    out = {}
    if exc["decision_existe"]:  # la decisión citada por la excepción, si existe
        out[str(exc["referencia_evaluacion"])] = {"referencia_evaluacion": str(exc["referencia_evaluacion"]), "commitment_id": exc["commitment_id"]}
    for f in _vigentes(session, t, hoy, filtro_commitment=" AND e.commitment_id = :c", filtro_extra=_PROPONE,
                       params={"c": exc["commitment_id"], "sujetos": [exc["sujeto_id"]]}):
        out[str(f["referencia_evaluacion"])] = f
    return [{**f, "entidad_tipo": "excepcion", "entidad_id": str(p["excepcion_id"])} for f in out.values()]


def _sel_constancia(session, t, p, hoy):
    c = session.execute(
        text("SELECT sujeto_id, cliente_id, commitment_id FROM modulo1.constancia_cliente WHERE tenant_id = :t AND constancia_id = :c"),
        {"t": t, "c": str(p["constancia_id"])},
    ).mappings().first()
    if c is None:
        return []
    if c["commitment_id"]:
        filas = _vigentes(session, t, hoy, filtro_commitment=" AND e.commitment_id = :c", filtro_extra=_PROPONE,
                          params={"c": c["commitment_id"], "sujetos": [c["sujeto_id"]]})
    else:
        filas = _vigentes(session, t, hoy, filtro_extra=" AND o.cliente_id = :cli" + _PROPONE,
                          params={"cli": str(c["cliente_id"]), "sujetos": [c["sujeto_id"]]})
    return [{**f, "entidad_tipo": "constancia_cliente", "entidad_id": str(p["constancia_id"])} for f in filas]


def _sel_custodia_cambiada(session, t, p, hoy):
    # Condicional (7.2): solo decisiones evaluadas con custodia por defecto que usaban el recurso.
    filas = _vigentes(session, t, hoy, filtro_extra=" AND u.origen_sujetos = 'custodia_por_defecto'" + _PROPONE,
                      params={"sujetos": [str(p["recurso_id"])]})
    return [{**f, "entidad_tipo": "periodo_custodia", "entidad_id": str(p.get("periodo_id_nuevo") or p["recurso_id"])} for f in filas]


def _sel_compromiso(tipo_cambio: str) -> Selector:
    def sel(session, t, p, hoy):
        # Referencias capturadas por el productor ANTES del cambio: no se busca OC activa.
        return [
            {"referencia_evaluacion": str(r), "commitment_id": p["commitment_id"], "entidad_tipo": "oc",
             "entidad_id": str(p["oc_id"]), "tipo_cambio": tipo_cambio}
            for r in p.get("referencias_afectadas", [])
        ]
    return sel


EVENTOS_FUENTE: dict[str, Selector] = {
    "DocumentoVerificado": _sel_documento_verificado,
    "DocumentoVencido": _sel_documento_verificado,  # 3.4: un vencimiento es cambio de entrada del snapshot
    "EvidenciaInvalidaPostVerificacion": _sel_documento_verificado,  # Fase 2 punto 2 (caso B): un archivo
    # ya verificado que resulta técnicamente inválido es cambio de entrada del snapshot, igual que un vencimiento
    "LoteRevertido": _sel_lote_revertido,
    "LegajoDadoDeBaja": _sel_legajo_baja,
    "MatrizVersionPublicada": _sel_matriz_publicada,
    "RequisitoParticularCargado": _sel_requisito_particular,
    "ExcepcionOtorgada": _sel_excepcion,
    "ExcepcionRevocada": _sel_excepcion,
    "ExcepcionRegularizada": _sel_excepcion,
    "ExcepcionVencida": _sel_excepcion,
    "ConstanciaRegistrada": _sel_constancia,
    "ConstanciaRevocada": _sel_constancia,
    "ConstanciaVencida": _sel_constancia,
    "CustodiaCambiada": _sel_custodia_cambiada,
    "CompromisoModificado": _sel_compromiso("modificacion"),
    "CompromisoCancelado": _sel_compromiso("cancelacion"),
}

# Eventos que la política PRODUCE: registrados por `registrar_evento_interno`, jamás fuente.
EVENTOS_PRODUCIDOS = {"AvisoDeRevaluacionAbierto", "AvisoDeRevaluacionCerrado",
                      "CumplimientoEmpresaAfectado", "CumplimientoEmpresaRegularizado"}
assert not (set(EVENTOS_FUENTE) & EVENTOS_PRODUCIDOS)


# ------------------------------------------------------------------ marcar

def abrir_o_sumar_aviso(
    session: Session, tenant_id: str, referencia: str, commitment_id: str, evento_id: str, tipo_evento: str,
    entidad_tipo: str, entidad_id: str, *, emitir_outbox: bool = True, tipo_cambio: str | None = None,
) -> tuple[str, bool]:
    """Devuelve (aviso_id, abierto_ahora). Coalescing concurrente seguro: INSERT contra el
    único parcial 'un aviso abierto por evaluación' con ON CONFLICT DO NOTHING; la causa
    también con ON CONFLICT (aviso, evento_id) DO NOTHING."""
    fila = session.execute(
        text(
            "INSERT INTO modulo1.aviso_revaluacion (tenant_id, referencia_evaluacion, commitment_id) VALUES (:t, :r, :c) "
            "ON CONFLICT (tenant_id, referencia_evaluacion) WHERE estado = 'abierto' DO NOTHING RETURNING aviso_id"
        ),
        {"t": tenant_id, "r": referencia, "c": commitment_id},
    ).first()
    abierto_ahora = fila is not None
    aviso_id = str(fila[0]) if fila else str(session.execute(
        text("SELECT aviso_id FROM modulo1.aviso_revaluacion WHERE tenant_id = :t AND referencia_evaluacion = :r AND estado = 'abierto'"),
        {"t": tenant_id, "r": referencia},
    ).scalar())
    session.execute(
        text(
            "INSERT INTO modulo1.aviso_revaluacion_causa (tenant_id, aviso_id, evento_id, tipo_evento, entidad_tipo, entidad_id) "
            "VALUES (:t, :a, :e, :tipo, :et, :ei) ON CONFLICT (tenant_id, aviso_id, evento_id) DO NOTHING"
        ),
        {"t": tenant_id, "a": aviso_id, "e": evento_id, "tipo": tipo_evento, "et": entidad_tipo, "ei": entidad_id},
    )
    if abierto_ahora:
        causal = {"evento_id": evento_id, "tipo": tipo_evento, "entidad": entidad_tipo, "id": entidad_id}
        registrar_evento_interno(
            session, tenant_id, "AvisoDeRevaluacionAbierto",
            {"aviso_id": aviso_id, "referencia_evaluacion": referencia, "commitment_id": commitment_id, "evento_causal": causal},
            usuario_id=None,
        )
        if emitir_outbox:
            payload = {
                "referencia_evaluacion": referencia, "commitment_id": commitment_id, "aviso_id": aviso_id,
                "evento_causal": causal, "emitido_en": ahora_utc().isoformat(),
            }
            if tipo_cambio:
                payload["tipo_cambio"] = tipo_cambio
            encolar_outbox(session, tenant_id, "HabilitacionRequiereRevaluacion", payload,
                           clave_dedup=f"hrr:{referencia}:{aviso_id}")
    return aviso_id, abierto_ahora


def aplicar_politica(session: Session, tenant_id: str, evento_id: str, tipo: str, payload: dict[str, Any]) -> list[str]:
    """Punto de entrada del despachador. Devuelve los aviso_id tocados (abiertos o sumados)."""
    selector = EVENTOS_FUENTE.get(tipo)
    if selector is None:
        return []
    procesado = session.execute(
        text("INSERT INTO modulo1.politica_evento_procesado (tenant_id, evento_id, tipo) VALUES (:t, :e, :tipo) "
             "ON CONFLICT (tenant_id, evento_id) DO NOTHING RETURNING evento_id"),
        {"t": tenant_id, "e": evento_id, "tipo": tipo},
    ).first()
    if procesado is None:
        return []  # ya procesado: un evento causal nunca marca dos veces
    hoy = hoy_del_tenant(session, tenant_id)
    tocados: list[str] = []
    for a in selector(session, tenant_id, payload, hoy):
        aviso_id, _ = abrir_o_sumar_aviso(
            session, tenant_id, a["referencia_evaluacion"], a["commitment_id"], evento_id, tipo,
            a["entidad_tipo"], a["entidad_id"], tipo_cambio=a.get("tipo_cambio"),
        )
        tocados.append(aviso_id)
    return tocados


def cerrar_avisos_por_decision_nueva(session: Session, tenant_id: str, commitment_id: str, referencia_nueva: str) -> list[str]:
    """Al persistir una decisión nueva de un commitment se cierran los avisos abiertos de
    sus decisiones anteriores (mismo commitment, nunca de otra OC), en la misma transacción,
    registrando `AvisoDeRevaluacionCerrado` por la vía interna."""
    filas = session.execute(
        text(
            "UPDATE modulo1.aviso_revaluacion SET estado = 'cerrado', cerrado_en = now(), cerrado_por_referencia = :n "
            "WHERE tenant_id = :t AND commitment_id = :c AND estado = 'abierto' AND referencia_evaluacion <> :n "
            "RETURNING aviso_id, referencia_evaluacion"
        ),
        {"t": tenant_id, "c": commitment_id, "n": referencia_nueva},
    ).all()
    cerrados = []
    for aviso_id, ref in filas:
        registrar_evento_interno(
            session, tenant_id, "AvisoDeRevaluacionCerrado",
            {"aviso_id": str(aviso_id), "referencia_evaluacion": str(ref), "commitment_id": commitment_id,
             "cerrado_por_referencia": referencia_nueva},
            usuario_id=None,
        )
        cerrados.append(str(aviso_id))
    return cerrados


def ultima_decision(session: Session, tenant_id: str, commitment_id: str) -> str | None:
    """Referencia de la última decisión de un commitment (creado_en DESC, secuencia DESC),
    sin exigir OC activa: la usan los productores de cambios de compromiso para capturar
    la referencia afectada ANTES de modificar o cancelar la OC."""
    return session.execute(
        text("SELECT referencia_evaluacion FROM modulo1.evaluacion_habilitacion WHERE tenant_id = :t AND commitment_id = :c "
             "ORDER BY creado_en DESC, secuencia DESC LIMIT 1"),
        {"t": tenant_id, "c": commitment_id},
    ).scalar()
