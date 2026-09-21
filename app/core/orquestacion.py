"""Orquestación de la evaluación de habilitación de un compromiso (OC) — 4.1 de
especificacion.md, 1.8/1.9 de documentacion-habilitante.md.

Compone el motor puro (`app/core/evaluacion.py`) con la base: lee OC, matriz vigente,
legajos, documentos/acreditaciones/inducciones, constancias y excepciones; evalúa en dos
pasos (empresa en su conjunto, después cada tipo de recurso exigido sujeto por sujeto);
persiste una fila en `evaluacion_habilitacion` con snapshot completo y registra el evento
`EvaluacionDeHabilitacionRealizada`.

Reglas que gobiernan el archivo:
- "hoy" sale SOLO de `hoy_del_tenant` (0.3 de especificacion.md, caso de oro 6.4).
- El motor puro no se toca: acá se lo alimenta y se agregan sus veredictos.
- Una Excepción nunca vuelve verde (`ck_excepcion_nunca_verde`): solo cambia el
  `resultado_de_decision`, jamás el `veredicto_de_cumplimiento`.

La firma de `evaluar_compromiso` es contrato con Consultas y Worker — no cambiarla.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import ErrorDeDominio, NoEncontrado
from app.comun.eventos import registrar_evento
from app.comun.reloj import hoy_del_tenant, zona_horaria_del_tenant
from app.core.evaluacion import (
    evaluar_documento_en_periodo,
    excepcion_tiene_efecto,
    resolver_constancia_aplicable,
)
from app.core.tipos import (
    Clasificacion,
    Constancia,
    Documento,
    EstadoConfirmacion,
    EstadoConstancia,
    EstadoExcepcion,
    EstadoVersionDocumento,
    Excepcion,
    ResultadoDecision,
    Veredicto,
    VeredictoRequisito,
)

# Orden de severidad: habilitado < vence_durante_el_trabajo < requiere_revision < no_habilitado.
ORDEN_VEREDICTO: dict[Veredicto, int] = {
    Veredicto.HABILITADO: 0,
    Veredicto.VENCE_DURANTE_EL_TRABAJO: 1,
    Veredicto.REQUIERE_REVISION: 2,
    Veredicto.NO_HABILITADO: 3,
}

TIPOS_RECURSO = ("persona", "vehiculo", "equipo")
VEREDICTOS_EXCEPCIONABLES = {Veredicto.NO_HABILITADO, Veredicto.VENCE_DURANTE_EL_TRABAJO}


def peor(veredictos: list[Veredicto]) -> Veredicto:
    return max(veredictos, key=lambda v: ORDEN_VEREDICTO[v]) if veredictos else Veredicto.HABILITADO


# --------------------------------------------------------------------------- lecturas


def buscar_oc(session: Session, tenant_id: str, commitment_id: str) -> dict[str, Any] | None:
    fila = session.execute(
        text(
            "SELECT oc_id, clave_origen, referencia, cliente_id, locacion_id, tipo_servicio_id, "
            "vigencia_desde, vigencia_hasta, estado "
            "FROM modulo1.oc WHERE tenant_id = :t AND clave_origen = :c"
        ),
        {"t": tenant_id, "c": commitment_id},
    ).mappings().first()
    return dict(fila) if fila else None


def matriz_vigente(
    session: Session, tenant_id: str, cliente_id: str, locacion_id: str, tipo_servicio_id: str, hoy: date
) -> dict[str, Any] | None:
    """Versión de matriz vigente en `hoy` para la clave (cliente, locación, tipo de
    servicio). `vigente_hasta` es inclusive; NULL = abierta."""
    fila = session.execute(
        text(
            "SELECT matriz_version_id, version, vigente_desde, vigente_hasta "
            "FROM modulo1.matriz_requisitos "
            "WHERE tenant_id = :t AND cliente_id = :c AND locacion_id = :l AND tipo_servicio_id = :ts "
            "  AND vigente_desde <= :hoy AND (vigente_hasta IS NULL OR vigente_hasta >= :hoy) "
            "ORDER BY vigente_desde DESC, version DESC LIMIT 1"
        ),
        {"t": tenant_id, "c": str(cliente_id), "l": str(locacion_id), "ts": str(tipo_servicio_id), "hoy": hoy},
    ).mappings().first()
    return dict(fila) if fila else None


def lineas_efectivas(
    session: Session, tenant_id: str, commitment_id: str, matriz_version_id: str
) -> dict[str, dict[str, Any]]:
    """Líneas de la matriz sobreescritas/complementadas por los requisitos particulares
    del compromiso (el particular manda si coincide requisito). Devuelve
    {requisito_definicion_id: {clasificacion, bloqueante_durante_ejecucion, origen}}."""
    lineas: dict[str, dict[str, Any]] = {}
    for fila in session.execute(
        text(
            "SELECT requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion "
            "FROM modulo1.linea_requisito WHERE tenant_id = :t AND matriz_version_id = :m"
        ),
        {"t": tenant_id, "m": str(matriz_version_id)},
    ).mappings():
        lineas[str(fila["requisito_definicion_id"])] = {
            "clasificacion": fila["clasificacion"],
            "bloqueante_durante_ejecucion": fila["bloqueante_durante_ejecucion"],
            "origen": "matriz",
        }
    for fila in session.execute(
        text(
            "SELECT requisito_particular_id, requisito_definicion_id, clasificacion, bloqueante_durante_ejecucion "
            "FROM modulo1.requisito_particular WHERE tenant_id = :t AND commitment_id = :c"
        ),
        {"t": tenant_id, "c": commitment_id},
    ).mappings():
        lineas[str(fila["requisito_definicion_id"])] = {
            "clasificacion": fila["clasificacion"],
            "bloqueante_durante_ejecucion": fila["bloqueante_durante_ejecucion"],
            "origen": "particular",
            "requisito_particular_id": str(fila["requisito_particular_id"]),
        }
    return lineas


def clasificacion_vigente(
    session: Session, tenant_id: str, commitment_id: str, requisito_definicion_id: str
) -> Clasificacion | None:
    """Clasificación que rige para un requisito en un compromiso: el requisito particular
    del commitment si existe; si no, la línea de la matriz vigente **al día de ingreso**
    de la OC (`vigencia_desde`) — regla temporal de 4.1 de especificacion.md: la versión
    de matriz que aplica es la vigente a `periodo_desde`, nunca la de la fecha en que
    corre el cálculo. None si no hay OC, no hay matriz vigente o no exige ese requisito."""
    particular = session.execute(
        text(
            "SELECT clasificacion FROM modulo1.requisito_particular "
            "WHERE tenant_id = :t AND commitment_id = :c AND requisito_definicion_id = :r"
        ),
        {"t": tenant_id, "c": commitment_id, "r": str(requisito_definicion_id)},
    ).scalar()
    if particular:
        return Clasificacion(particular)
    oc = buscar_oc(session, tenant_id, commitment_id)
    if oc is None:
        return None
    matriz = matriz_vigente(
        session, tenant_id, oc["cliente_id"], oc["locacion_id"], oc["tipo_servicio_id"], oc["vigencia_desde"]
    )
    if matriz is None:
        return None
    linea = session.execute(
        text(
            "SELECT clasificacion FROM modulo1.linea_requisito "
            "WHERE tenant_id = :t AND matriz_version_id = :m AND requisito_definicion_id = :r"
        ),
        {"t": tenant_id, "m": str(matriz["matriz_version_id"]), "r": str(requisito_definicion_id)},
    ).scalar()
    return Clasificacion(linea) if linea else None


def _definiciones(session: Session, tenant_id: str, requisito_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not requisito_ids:
        return {}
    filas = session.execute(
        text(
            "SELECT requisito_definicion_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id, activa "
            "FROM modulo1.definicion_requisito "
            "WHERE tenant_id = :t AND requisito_definicion_id = ANY(CAST(:ids AS uuid[]))"
        ),
        {"t": tenant_id, "ids": requisito_ids},
    ).mappings()
    return {str(f["requisito_definicion_id"]): dict(f) for f in filas}


def _sujetos_activos(session: Session, tenant_id: str, tipos: list[str]) -> list[dict[str, Any]]:
    if not tipos:
        return []
    filas = session.execute(
        text(
            "SELECT sujeto_id, tipo_sujeto, creado_en FROM modulo1.legajo "
            "WHERE tenant_id = :t AND dado_de_baja_en IS NULL AND tipo_sujeto = ANY(:tipos) "
            "ORDER BY creado_en, sujeto_id"
        ),
        {"t": tenant_id, "tipos": tipos},
    ).mappings()
    return [dict(f) for f in filas]


def _cargar_evidencias(
    session: Session, tenant_id: str, definiciones: dict[str, dict[str, Any]]
) -> dict[tuple[str, str], Documento]:
    """Mapa (sujeto_id, requisito_definicion_id) → Documento del motor, según categoría:
    `documento` → tabla documento (estado_version=vigente; único por índice);
    `competencia` → acreditacion_competencia (la de vigente_hasta mayor);
    `induccion` → induccion (la de vigente_hasta mayor).
    Acreditaciones e inducciones no versionan, así que entran siempre como `vigente`."""
    evidencias: dict[tuple[str, str], Documento] = {}
    por_categoria: dict[str, list[str]] = {"documento": [], "competencia": [], "induccion": []}
    for req_id, d in definiciones.items():
        por_categoria.setdefault(d["categoria"], []).append(req_id)

    def _doc(fila: Any, id_col: str, sujeto_col: str, archivo_requiere_revision: bool = False) -> Documento:
        return Documento(
            documento_id=str(fila[id_col]),
            sujeto_id=str(fila[sujeto_col]),
            requisito_definicion_id=str(fila["requisito_definicion_id"]),
            vigente_desde=fila["vigente_desde"],
            vigente_hasta=fila["vigente_hasta"],
            estado_confirmacion=EstadoConfirmacion(fila["estado_confirmacion"]),
            estado_version=EstadoVersionDocumento.VIGENTE,
            archivo_requiere_revision=archivo_requiere_revision,
        )

    if por_categoria["documento"]:
        for fila in session.execute(
            text(
                "SELECT documento_id, sujeto_id, requisito_definicion_id, vigente_desde, vigente_hasta, "
                "estado_confirmacion, archivo_estado, archivo_validacion FROM modulo1.documento "
                "WHERE tenant_id = :t AND estado_version = 'vigente' "
                "  AND requisito_definicion_id = ANY(CAST(:ids AS uuid[]))"
            ),
            {"t": tenant_id, "ids": por_categoria["documento"]},
        ).mappings():
            # Sólo cuenta si hay un archivo real adjunto (reauditoría Fase 2 punto 2):
            # acreditación/inducción no tienen esta columna y nunca activan el gate.
            requiere = fila["archivo_estado"] == "confirmado" and fila["archivo_validacion"] != "valido"
            evidencias[(str(fila["sujeto_id"]), str(fila["requisito_definicion_id"]))] = _doc(
                fila, "documento_id", "sujeto_id", requiere
            )
    if por_categoria["competencia"]:
        for fila in session.execute(
            text(
                "SELECT DISTINCT ON (persona_id, requisito_definicion_id) acreditacion_id, persona_id, "
                "requisito_definicion_id, vigente_desde, vigente_hasta, estado_confirmacion "
                "FROM modulo1.acreditacion_competencia "
                "WHERE tenant_id = :t AND requisito_definicion_id = ANY(CAST(:ids AS uuid[])) "
                "ORDER BY persona_id, requisito_definicion_id, vigente_hasta DESC, creado_en DESC"
            ),
            {"t": tenant_id, "ids": por_categoria["competencia"]},
        ).mappings():
            evidencias[(str(fila["persona_id"]), str(fila["requisito_definicion_id"]))] = _doc(
                fila, "acreditacion_id", "persona_id"
            )
    if por_categoria["induccion"]:
        for fila in session.execute(
            text(
                "SELECT DISTINCT ON (persona_id, requisito_definicion_id) induccion_id, persona_id, "
                "requisito_definicion_id, vigente_desde, vigente_hasta, estado_confirmacion "
                "FROM modulo1.induccion "
                "WHERE tenant_id = :t AND requisito_definicion_id = ANY(CAST(:ids AS uuid[])) "
                "ORDER BY persona_id, requisito_definicion_id, vigente_hasta DESC, creado_en DESC"
            ),
            {"t": tenant_id, "ids": por_categoria["induccion"]},
        ).mappings():
            evidencias[(str(fila["persona_id"]), str(fila["requisito_definicion_id"]))] = _doc(
                fila, "induccion_id", "persona_id"
            )
    return evidencias


def _cargar_constancias(
    session: Session, tenant_id: str, cliente_id: str, hoy: date
) -> dict[tuple[str, str], list[Constancia]]:
    """Todas las constancias del cliente, agrupadas por (sujeto, requisito). Una
    `vigente` con `vigencia` ya pasada se lee como `vencida` (el worker la marcará
    después; el motor no puede esperar a eso para decidir bien)."""
    por_clave: dict[tuple[str, str], list[Constancia]] = {}
    for fila in session.execute(
        text(
            "SELECT constancia_id, sujeto_id, requisito_definicion_id, cliente_id, commitment_id, vigencia, estado "
            "FROM modulo1.constancia_cliente WHERE tenant_id = :t AND cliente_id = :c"
        ),
        {"t": tenant_id, "c": str(cliente_id)},
    ).mappings():
        estado = EstadoConstancia(fila["estado"])
        if estado == EstadoConstancia.VIGENTE and fila["vigencia"] is not None and fila["vigencia"] < hoy:
            estado = EstadoConstancia.VENCIDA
        c = Constancia(
            constancia_id=str(fila["constancia_id"]),
            sujeto_id=str(fila["sujeto_id"]),
            requisito_definicion_id=str(fila["requisito_definicion_id"]),
            cliente_id=str(fila["cliente_id"]),
            estado=estado,
            commitment_id=fila["commitment_id"],
            vigencia=fila["vigencia"],
        )
        por_clave.setdefault((c.sujeto_id, c.requisito_definicion_id), []).append(c)
    return por_clave


def _cargar_excepciones(
    session: Session, tenant_id: str, commitment_id: str, hoy: date
) -> dict[tuple[str, str], Excepcion]:
    """Excepciones `otorgada` del compromiso por (sujeto, requisito). Una otorgada con
    `vigencia` ya pasada no cuenta (el worker la marcará `vencida`)."""
    por_clave: dict[tuple[str, str], Excepcion] = {}
    for fila in session.execute(
        text(
            "SELECT excepcion_id, sujeto_id, requisito_definicion_id, commitment_id, vigencia, estado "
            "FROM modulo1.excepcion WHERE tenant_id = :t AND commitment_id = :c AND estado = 'otorgada' "
            "ORDER BY creado_en"
        ),
        {"t": tenant_id, "c": commitment_id},
    ).mappings():
        if fila["vigencia"] is not None and fila["vigencia"] < hoy:
            continue
        e = Excepcion(
            excepcion_id=str(fila["excepcion_id"]),
            sujeto_id=str(fila["sujeto_id"]),
            requisito_definicion_id=str(fila["requisito_definicion_id"]),
            commitment_id=fila["commitment_id"],
            vigencia=fila["vigencia"],
            estado=EstadoExcepcion(fila["estado"]),
        )
        por_clave[(e.sujeto_id, e.requisito_definicion_id)] = e
    return por_clave


# --------------------------------------------------------------------------- evaluación


class _Contexto:
    """Todo lo que la evaluación de un (sujeto, requisito) necesita, ya cargado en
    memoria: una sola pasada de lecturas por evaluación, no una por sujeto."""

    def __init__(
        self,
        oc: dict[str, Any],
        commitment_id: str,
        lineas: dict[str, dict[str, Any]],
        definiciones: dict[str, dict[str, Any]],
        evidencias: dict[tuple[str, str], Documento],
        constancias: dict[tuple[str, str], list[Constancia]],
        excepciones: dict[tuple[str, str], Excepcion],
    ):
        self.oc = oc
        self.commitment_id = commitment_id
        self.lineas = lineas
        self.definiciones = definiciones
        self.evidencias = evidencias
        self.constancias = constancias
        self.excepciones = excepciones


def _evaluar_requisito(ctx: _Contexto, sujeto_id: str, req_id: str) -> dict[str, Any]:
    linea = ctx.lineas[req_id]
    clasificacion = Clasificacion(linea["clasificacion"])
    definicion = ctx.definiciones.get(req_id, {})

    documento = ctx.evidencias.get((sujeto_id, req_id))
    if documento is None:
        vr = VeredictoRequisito(requisito_definicion_id=req_id, veredicto=Veredicto.NO_HABILITADO, motivo="sin documento")
    else:
        vr = evaluar_documento_en_periodo(documento, ctx.oc["vigencia_desde"], ctx.oc["vigencia_hasta"])

    r: dict[str, Any] = asdict(vr)
    r["veredicto"] = vr.veredicto.value
    r.update(
        {
            "nombre": definicion.get("nombre"),
            "categoria": definicion.get("categoria"),
            "clasificacion": clasificacion.value,
            "origen_clasificacion": linea["origen"],
            "bloqueante_durante_ejecucion": linea["bloqueante_durante_ejecucion"],
            "documento_id": documento.documento_id if documento else None,
            "constancia_id": None,
            "excepcion_id": None,
            "bajo_excepcion": False,
            "asignable": False,
        }
    )

    # Constancias del cliente: solo cubren requisitos bloqueante_duro (4.5 de especificacion.md).
    aplicable, nota = resolver_constancia_aplicable(
        ctx.constancias.get((sujeto_id, req_id), []),
        sujeto_id=sujeto_id,
        requisito_definicion_id=req_id,
        cliente_id=str(ctx.oc["cliente_id"]),
        commitment_id=ctx.commitment_id,
    )
    if nota:
        r["anulacion_detectada"] = nota
    if aplicable is not None and vr.veredicto != Veredicto.HABILITADO and clasificacion == Clasificacion.BLOQUEANTE_DURO:
        r["veredicto"] = Veredicto.HABILITADO.value
        r["motivo"] = f"cubierto por constancia {aplicable.constancia_id}"
        r["constancia_id"] = aplicable.constancia_id

    # Excepciones: nunca vuelven verde, solo marcan `bajo_excepcion` (4.4; caso de oro 6.5).
    if Veredicto(r["veredicto"]) in VEREDICTOS_EXCEPCIONABLES:
        excepcion = ctx.excepciones.get((sujeto_id, req_id))
        if excepcion is not None:
            if excepcion_tiene_efecto(excepcion, clasificacion):
                r["bajo_excepcion"] = True
                r["excepcion_id"] = excepcion.excepcion_id
                r["motivo"] = f"{r['motivo']} (bajo excepción {excepcion.excepcion_id})"
            else:
                r["excepcion_aplicable_pero_sin_efecto"] = True
                r["excepcion_id"] = excepcion.excepcion_id
                r["motivo"] = (
                    f"{r['motivo']} (excepción {excepcion.excepcion_id} sin efecto: requisito reclasificado "
                    f"a {clasificacion.value})"
                )

    # Asignabilidad del requisito (1.9 de documentacion-habilitante.md): `habilitado` deja
    # asignar; `vence_durante_el_trabajo` "avisa siempre; bloquea solo si el requisito está
    # marcado bloqueante_durante_ejecucion"; lo demás solo pasa bajo excepción con efecto.
    # El veredicto NO cambia por esto — la asignabilidad es una lectura sobre él.
    veredicto_final = Veredicto(r["veredicto"])
    if veredicto_final == Veredicto.HABILITADO:
        r["asignable"] = True
    elif veredicto_final == Veredicto.VENCE_DURANTE_EL_TRABAJO and not linea["bloqueante_durante_ejecucion"]:
        r["asignable"] = True
        r["motivo"] = f"{r['motivo']} (avisa, no bloquea: no es bloqueante_durante_ejecucion)"
    else:
        r["asignable"] = bool(r["bajo_excepcion"])
    return r


def _evaluar_sujeto(ctx: _Contexto, sujeto_id: str, tipo_sujeto: str, requisitos: list[str]) -> dict[str, Any]:
    evaluados = [_evaluar_requisito(ctx, sujeto_id, req_id) for req_id in requisitos]
    veredicto = peor([Veredicto(e["veredicto"]) for e in evaluados])
    asignable = all(e["asignable"] for e in evaluados)
    return {
        "sujeto_id": sujeto_id,
        "tipo_sujeto": tipo_sujeto,
        "veredicto": veredicto.value,
        # Un sujeto se asigna solo si CADA requisito es asignable (1.12: "cumpla todos los
        # requisitos que le aplican"; nunca se compone entre legajos parciales).
        "asignable": asignable,
        # True cuando es asignable y al menos un requisito depende de una excepción con
        # efecto: la OT queda "asignada bajo excepción" (1.6).
        "bajo_excepcion": asignable and any(e["bajo_excepcion"] for e in evaluados),
        "requisitos": evaluados,
    }


def _clave_mejor_sujeto(s: dict[str, Any]) -> tuple[int, int]:
    """Entre sujetos del mismo tipo, el que cubre mejor la OC (1.12: basta con que exista
    UN legajo del tipo que cumpla). Primero por asignabilidad — asignable por sí mismo,
    después asignable solo bajo excepción, después no asignable — y recién dentro de
    cada clase por menor severidad. Así un sujeto `no_habilitado` bajo excepción con
    efecto cubre la OC por delante de uno `vence_durante_el_trabajo` bloqueante, y un
    representante no asignable es siempre el menos grave (para el motivo explicable)."""
    if s["asignable"] and not s["bajo_excepcion"]:
        clase = 0
    elif s["asignable"]:
        clase = 1
    else:
        clase = 2
    return (clase, ORDEN_VEREDICTO[Veredicto(s["veredicto"])])


def _jsonable(valor: Any) -> Any:
    return json.loads(json.dumps(valor, default=str, ensure_ascii=False))


MODO_CONSULTA = "consulta"
MODO_DECISION = "decision"


def _evaluar(
    session: Session,
    tenant_id: str,
    commitment_id: str,
    ahora_utc: datetime,
    *,
    modo: str,
    candidatos: list[str] | None = None,
    sujetos_propuestos: list[dict[str, Any]] | None = None,
) -> dict:
    """Cálculo común a los dos modos (2.1 de modelo-dominio: "es la misma evaluación;
    cambia sólo si la envuelve una decisión"). NO persiste ni emite nada.

    - modo consulta (barrido / cobertura): candidatos = legajos activos del tenant, o
      solo los `candidatos` dados (universo de quien consulta). Cubre cada tipo exigido
      con el mejor candidato asignable (1.12).
    - modo decisión: evalúa EXCLUSIVAMENTE `sujetos_propuestos` (ya validados por quien
      llama). Cada propuesto es representante: se asigna la cuadrilla entera, así que
      todos deben ser asignables y cada tipo exigido debe estar presente entre ellos.
    La empresa se evalúa siempre en ambos modos (1.8) y no forma parte de los propuestos.
    """
    oc = buscar_oc(session, tenant_id, commitment_id)
    if oc is None:
        raise NoEncontrado("Compromiso inexistente", {"commitment_id": commitment_id})

    hoy = hoy_del_tenant(session, tenant_id, ahora_utc)
    zona_horaria = zona_horaria_del_tenant(session, tenant_id)

    # `version_matriz` es la vigente a `periodo_desde` (día de ingreso), no la de hoy
    # (4.1 de especificacion.md, regla temporal). `hoy` solo decide vencimientos de
    # constancias/excepciones, que son hechos del presente, no del período evaluado.
    periodo_desde: date = oc["vigencia_desde"]
    matriz = matriz_vigente(
        session, tenant_id, oc["cliente_id"], oc["locacion_id"], oc["tipo_servicio_id"], periodo_desde
    )
    if matriz is None:
        raise ErrorDeDominio(
            "sin matriz vigente al día de ingreso de la OC para su cliente, locación y tipo de servicio",
            {"commitment_id": commitment_id, "periodo_desde": str(periodo_desde)},
            codigo="sin_matriz_vigente",
        )
    lineas = lineas_efectivas(session, tenant_id, commitment_id, str(matriz["matriz_version_id"]))
    if not lineas:
        raise ErrorDeDominio("la matriz vigente no tiene líneas de requisito", {"matriz_version_id": str(matriz["matriz_version_id"])})

    definiciones = _definiciones(session, tenant_id, list(lineas))
    faltantes_definicion = [r for r in lineas if r not in definiciones]
    if faltantes_definicion:
        raise ErrorDeDominio("líneas de matriz apuntan a definiciones de requisito inexistentes", {"requisitos": faltantes_definicion})

    # Requisitos por tipo de sujeto (los tipos exigidos son los presentes en las líneas).
    requisitos_por_tipo: dict[str, list[str]] = {}
    for req_id in lineas:
        requisitos_por_tipo.setdefault(definiciones[req_id]["tipo_sujeto_aplicable"], []).append(req_id)
    tipos_recurso = [t for t in TIPOS_RECURSO if t in requisitos_por_tipo]

    ctx = _Contexto(
        oc=oc,
        commitment_id=commitment_id,
        lineas=lineas,
        definiciones=definiciones,
        evidencias=_cargar_evidencias(session, tenant_id, definiciones),
        constancias=_cargar_constancias(session, tenant_id, str(oc["cliente_id"]), hoy),
        excepciones=_cargar_excepciones(session, tenant_id, commitment_id, hoy),
    )

    por_sujeto: list[dict[str, Any]] = []
    representantes: list[dict[str, Any]] = []  # empresa + mejor sujeto por tipo exigido
    cobertura_por_tipo: dict[str, str | None] = {}
    requisitos_faltantes: list[dict[str, Any]] = []
    empresa_sin_evaluar = False

    # Paso 1 — empresa en su conjunto.
    if "empresa" in requisitos_por_tipo:
        empresas = _sujetos_activos(session, tenant_id, ["empresa"])
        if empresas:
            empresa = _evaluar_sujeto(ctx, str(empresas[0]["sujeto_id"]), "empresa", requisitos_por_tipo["empresa"])
            empresa["representante"] = True
            por_sujeto.append(empresa)
            representantes.append(empresa)
            cobertura_por_tipo["empresa"] = empresa["sujeto_id"]
        else:
            # La empresa es *siempre evaluada* (1.8): si la matriz le exige requisitos y no
            # hay legajo de empresa, no hay evidencia alguna → no_habilitado. Queda anotado
            # en snapshot para el motivo explicable; nunca se omite del veredicto.
            empresa_sin_evaluar = True
            cobertura_por_tipo["empresa"] = None
            for req_id in requisitos_por_tipo["empresa"]:
                requisitos_faltantes.append(
                    {"tipo_sujeto": "empresa", "sujeto_id": None, "requisito_definicion_id": req_id,
                     "nombre": definiciones[req_id]["nombre"], "veredicto": Veredicto.NO_HABILITADO.value,
                     "motivo": "sin legajo de empresa: no hay evidencia que evaluar", "bajo_excepcion": False}
                )

    # Paso 2 — recursos. Consulta: candidatos (todo el tenant o el universo dado), mejor
    # por tipo. Decisión: exactamente los propuestos, todos representantes.
    if modo == MODO_DECISION:
        sujetos = list(sujetos_propuestos or [])
    else:
        sujetos = _sujetos_activos(session, tenant_id, tipos_recurso)
        if candidatos is not None:
            permitidos = set(candidatos)
            sujetos = [x for x in sujetos if str(x["sujeto_id"]) in permitidos]
    tipo_sin_sujetos: list[str] = []
    for tipo in tipos_recurso:
        evaluados = [
            _evaluar_sujeto(ctx, str(x["sujeto_id"]), tipo, requisitos_por_tipo[tipo])
            for x in sujetos
            if x["tipo_sujeto"] == tipo
        ]
        if not evaluados:
            tipo_sin_sujetos.append(tipo)
            cobertura_por_tipo[tipo] = None
            requisitos_faltantes.append(
                {"tipo_sujeto": tipo, "sujeto_id": None, "requisito_definicion_id": None,
                 "veredicto": Veredicto.NO_HABILITADO.value,
                 "motivo": (f"ningún sujeto propuesto de tipo {tipo}" if modo == MODO_DECISION
                            else f"sin candidatos de tipo {tipo}"),
                 "bajo_excepcion": False}
            )
            continue
        if modo == MODO_DECISION:
            for e in evaluados:
                e["representante"] = True
            representantes.extend(evaluados)
            cobertura_por_tipo[tipo] = [e["sujeto_id"] for e in evaluados]
        else:
            mejor = min(evaluados, key=_clave_mejor_sujeto)
            mejor["representante"] = True
            for e in evaluados:
                e.setdefault("representante", False)
            representantes.append(mejor)
            cobertura_por_tipo[tipo] = mejor["sujeto_id"]
        por_sujeto.extend(evaluados)
    # Propuestos de un tipo que la matriz no exige: se informan igual (evaluados sin
    # requisitos → habilitado), para que la decisión refleje la cuadrilla completa.
    if modo == MODO_DECISION:
        for x in sujetos:
            if x["tipo_sujeto"] not in requisitos_por_tipo:
                e = _evaluar_sujeto(ctx, str(x["sujeto_id"]), x["tipo_sujeto"], [])
                e["representante"] = True
                por_sujeto.append(e)
                representantes.append(e)

    # Agregación: peor entre empresa y el mejor sujeto de cada tipo exigido.
    veredictos_globales = [Veredicto(r["veredicto"]) for r in representantes]
    if tipo_sin_sujetos or empresa_sin_evaluar:
        veredictos_globales.append(Veredicto.NO_HABILITADO)
    veredicto_global = peor(veredictos_globales)

    for rep in representantes:
        for e in rep["requisitos"]:
            if e["veredicto"] != Veredicto.HABILITADO.value:
                requisitos_faltantes.append(
                    {
                        "tipo_sujeto": rep["tipo_sujeto"],
                        "sujeto_id": rep["sujeto_id"],
                        "requisito_definicion_id": e["requisito_definicion_id"],
                        "nombre": e["nombre"],
                        "veredicto": e["veredicto"],
                        "motivo": e["motivo"],
                        "bajo_excepcion": e["bajo_excepcion"],
                    }
                )

    # Decisión (4.1): se asigna solo si la empresa y un representante de cada tipo exigido
    # son asignables. Si alguno depende de una excepción → bajo_excepcion, y en ese caso
    # el veredicto global nunca es `habilitado` (ck_excepcion_nunca_verde). El veredicto
    # global es siempre el peor de los representantes: nunca más favorable que ellos.
    todos_asignables = (
        not tipo_sin_sujetos and not empresa_sin_evaluar and all(r["asignable"] for r in representantes)
    )
    if not todos_asignables:
        resultado = ResultadoDecision.NO_PUEDE_ASIGNARSE
    elif any(r["bajo_excepcion"] for r in representantes):
        resultado = ResultadoDecision.PUEDE_ASIGNARSE_BAJO_EXCEPCION
    else:
        resultado = ResultadoDecision.PUEDE_ASIGNARSE

    # ck_excepcion_nunca_verde, verificado acá antes de tocar la base.
    assert resultado != ResultadoDecision.PUEDE_ASIGNARSE_BAJO_EXCEPCION or veredicto_global in VEREDICTOS_EXCEPCIONABLES

    version_matriz = {"matriz_version_id": str(matriz["matriz_version_id"]), "version": matriz["version"]}
    snapshot = _jsonable(
        {
            "commitment_id": commitment_id,
            "oc": oc,
            "hoy": hoy,
            "periodo_desde": periodo_desde,
            "ahora_utc": ahora_utc,
            "zona_horaria": zona_horaria,
            "matriz": matriz,
            "lineas": [{"requisito_definicion_id": k, **v, **{
                "nombre": definiciones[k]["nombre"],
                "categoria": definiciones[k]["categoria"],
                "tipo_sujeto_aplicable": definiciones[k]["tipo_sujeto_aplicable"],
            }} for k, v in lineas.items()],
            "tipos_exigidos": list(requisitos_por_tipo),
            "empresa_sin_evaluar": empresa_sin_evaluar,
            "cobertura_por_tipo": cobertura_por_tipo,
            "sujetos_evaluados": len(por_sujeto),
        }
    )
    return {
        "commitment_id": commitment_id,
        "modo": modo,
        "veredicto_de_cumplimiento": veredicto_global.value,
        "resultado_de_decision": resultado.value,
        "por_sujeto": _jsonable(por_sujeto),
        "requisitos_faltantes": _jsonable(requisitos_faltantes),
        "version_matriz": version_matriz,
        "snapshot": snapshot,
    }


def cobertura_de_oc(
    session: Session,
    tenant_id: str,
    commitment_id: str,
    ahora_utc: datetime,
    candidatos: list[str] | None = None,
) -> dict:
    """Barrido en MODO CONSULTA (2.1: "no persiste, no crea tareas, no emite eventos").
    `candidatos=None` → todos los legajos activos del tenant (responsable de legajos);
    lista → solo esos sujetos (universo del supervisor, A-04). Nunca reutiliza una
    decisión persistida ni devuelve sujetos fuera de `candidatos`."""
    r = _evaluar(session, tenant_id, commitment_id, ahora_utc, modo=MODO_CONSULTA, candidatos=candidatos)
    r["snapshot"]["candidatos"] = None if candidatos is None else sorted(candidatos)
    return r


def evaluar_compromiso(
    session: Session,
    tenant_id: str,
    commitment_id: str,
    ahora_utc: datetime,
    usuario_id: str | None = None,
    candidatos: list[str] | None = None,
) -> dict:
    """Nombre histórico del barrido en MODO CONSULTA. `usuario_id` se acepta por
    compatibilidad y se ignora: una consulta no persiste ni audita nada."""
    return cobertura_de_oc(session, tenant_id, commitment_id, ahora_utc, candidatos)


def _validar_sujetos_propuestos(session: Session, tenant_id: str, sujetos_propuestos: list[str]) -> list[dict[str, Any]]:
    """Duplicados, vacíos, inexistentes (o de otro tenant: RLS los hace inexistentes),
    dados de baja o de tipo empresa → error antes de calcular nada."""
    if not sujetos_propuestos:
        raise ErrorDeDominio("Hay que proponer al menos un sujeto", codigo="sin_sujetos_propuestos")
    duplicados = sorted({x for x in sujetos_propuestos if sujetos_propuestos.count(x) > 1})
    if duplicados:
        raise ErrorDeDominio("Sujetos propuestos duplicados", {"sujetos": duplicados}, codigo="sujetos_duplicados")
    filas = session.execute(
        text(
            "SELECT sujeto_id, tipo_sujeto, dado_de_baja_en FROM modulo1.legajo "
            "WHERE tenant_id = :t AND sujeto_id = ANY(CAST(:ids AS text[]))"
        ),
        {"t": tenant_id, "ids": list(sujetos_propuestos)},
    ).mappings().all()
    por_id = {str(f["sujeto_id"]): dict(f) for f in filas}
    inexistentes = [x for x in sujetos_propuestos if x not in por_id]
    if inexistentes:
        raise NoEncontrado("Sujetos propuestos inexistentes", {"sujetos": inexistentes})
    inactivos = [x for x in sujetos_propuestos if por_id[x]["dado_de_baja_en"] is not None]
    if inactivos:
        raise ErrorDeDominio("Sujetos propuestos dados de baja", {"sujetos": inactivos}, codigo="sujetos_inactivos")
    empresas = [x for x in sujetos_propuestos if por_id[x]["tipo_sujeto"] == "empresa"]
    if empresas:
        raise ErrorDeDominio("La empresa se evalúa siempre; no se propone", {"sujetos": empresas}, codigo="empresa_no_se_propone")
    return [por_id[x] for x in sujetos_propuestos]


ORIGENES_SUJETOS = ("explicito", "custodia_por_defecto")


def decidir_habilitacion(
    session: Session,
    tenant_id: str,
    commitment_id: str,
    sujetos_propuestos: list[str],
    ahora_utc: datetime,
    usuario_id: str | None,
    *,
    origen_sujetos: str = "explicito",
) -> dict:
    """MODO DECISIÓN (2.1 / 4.1): evalúa exclusivamente los sujetos propuestos y, en la
    misma transacción, persiste el snapshot, la relación normalizada
    `evaluacion_sujeto_propuesto` y el evento EvaluacionDeHabilitacionRealizada.
    La autorización (solo responsable de legajos) la hace el servicio que llama."""
    if origen_sujetos not in ORIGENES_SUJETOS:
        raise ValueError(f"origen_sujetos inválido: {origen_sujetos}")
    propuestos = _validar_sujetos_propuestos(session, tenant_id, sujetos_propuestos)
    r = _evaluar(session, tenant_id, commitment_id, ahora_utc, modo=MODO_DECISION, sujetos_propuestos=propuestos)
    r["snapshot"]["sujetos_propuestos"] = list(sujetos_propuestos)
    # `origen_sujetos` lo fija SIEMPRE el servidor (7.2 CustodiaCambiada es condicional a él):
    # el endpoint público solo produce 'explicito'; una pantalla que derive la custodia
    # vigente pasará 'custodia_por_defecto' desde su propio servicio, nunca desde el body.
    r["snapshot"]["origen_sujetos"] = origen_sujetos

    fila = session.execute(
        text(
            "INSERT INTO modulo1.evaluacion_habilitacion "
            "(tenant_id, commitment_id, veredicto_de_cumplimiento, resultado_de_decision, por_sujeto, "
            " requisitos_faltantes, version_matriz, snapshot, origen_sujetos) "
            "VALUES (:t, :c, :v, :r, CAST(:ps AS jsonb), CAST(:rf AS jsonb), CAST(:vm AS jsonb), CAST(:sn AS jsonb), :orig) "
            "RETURNING referencia_evaluacion, creado_en"
        ),
        {
            "t": tenant_id,
            "c": commitment_id,
            "v": r["veredicto_de_cumplimiento"],
            "r": r["resultado_de_decision"],
            "ps": json.dumps(r["por_sujeto"], ensure_ascii=False),
            "rf": json.dumps(r["requisitos_faltantes"], ensure_ascii=False),
            "vm": json.dumps(r["version_matriz"]),
            "sn": json.dumps(r["snapshot"], ensure_ascii=False),
            "orig": origen_sujetos,
        },
    ).first()
    referencia = str(fila[0])
    for x in propuestos:
        session.execute(
            text(
                "INSERT INTO modulo1.evaluacion_sujeto_propuesto (tenant_id, evaluacion_id, sujeto_id, tipo_sujeto_al_proponer) "
                "VALUES (:t, :e, :sj, :tipo)"
            ),
            {"t": tenant_id, "e": referencia, "sj": str(x["sujeto_id"]), "tipo": x["tipo_sujeto"]},
        )

    registrar_evento(
        session,
        tenant_id,
        "EvaluacionDeHabilitacionRealizada",
        {
            "referencia_evaluacion": referencia,
            "commitment_id": commitment_id,
            "veredicto": r["veredicto_de_cumplimiento"],
            "resultado": r["resultado_de_decision"],
            "sujetos_propuestos": list(sujetos_propuestos),
        },
        usuario_id,
    )

    # 7.2 EvaluacionDeHabilitacionRealizada: cierra los avisos abiertos de decisiones
    # anteriores del MISMO commitment (nunca de otra OC), en esta misma transacción.
    from app.core.revaluacion import cerrar_avisos_por_decision_nueva

    avisos_cerrados = cerrar_avisos_por_decision_nueva(session, tenant_id, commitment_id, referencia)

    return {
        "referencia_evaluacion": referencia,
        "sujetos_propuestos": list(sujetos_propuestos),
        "origen_sujetos": origen_sujetos,
        "avisos_cerrados": avisos_cerrados,
        **r,
        "creado_en": fila[1].isoformat(),
    }
