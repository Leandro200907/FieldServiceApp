"""Comandos del dominio Evidencia (legajos, documentos, competencias, inducciones,
lotes, asignación de supervisor) — 2.x de especificacion.md.

Cada función recibe la sesión ya abierta con `tenant_session` (una por request), la
identidad autenticada y el body validado; escribe con SQL explícito, registra los
eventos del catálogo en la misma transacción y devuelve el dict que el router
responde (ids generados + `eventos`). Los permisos por rol los exige el router antes
de abrir la sesión (`ejecutar_comando`); acá se validan reglas de dominio.

Invariante central (2.2): a lo sumo un Documento `vigente` por (sujeto, requisito).
Cargar uno nuevo sucede al anterior y deja el vínculo en `documento.sucede_a`, que es
lo que permite restaurar exactamente esa versión al rechazar una propuesta o revertir
un lote.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.identidad import Identidad
from app.comun.eventos import registrar_evento
from app.comun.idempotencia import buscar_resultado, guardar_resultado
from app.comun.reloj import hoy_del_tenant
from app.modules.legajos import esquemas as e

# --------------------------------------------------------------------------- helpers


def _legajo_activo(s: Session, tenant_id: str, sujeto_id: str, *, bloquear: bool = False) -> dict[str, Any]:
    fila = s.execute(
        text(
            "SELECT legajo_id, sujeto_id, tipo_sujeto, dado_de_baja_en FROM modulo1.legajo "
            "WHERE tenant_id = :t AND sujeto_id = :sj" + (" FOR UPDATE" if bloquear else "")
        ),
        {"t": tenant_id, "sj": sujeto_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Legajo inexistente", {"sujeto_id": sujeto_id})
    if fila["dado_de_baja_en"] is not None:
        raise Conflicto("El sujeto está dado de baja", {"sujeto_id": sujeto_id})
    return dict(fila)


def _definicion_activa(s: Session, tenant_id: str, requisito_definicion_id: str) -> dict[str, Any]:
    fila = s.execute(
        text(
            "SELECT requisito_definicion_id, nombre, categoria, tipo_sujeto_aplicable, locacion_id, activa "
            "FROM modulo1.definicion_requisito WHERE tenant_id = :t AND requisito_definicion_id = :r"
        ),
        {"t": tenant_id, "r": requisito_definicion_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Definición de requisito inexistente", {"requisito_definicion_id": requisito_definicion_id})
    if not fila["activa"]:
        raise ErrorDeDominio("La definición de requisito está dada de baja", {"requisito_definicion_id": requisito_definicion_id})
    return dict(fila)


def _exigir_aplicable(definicion: dict[str, Any], legajo: dict[str, Any]) -> None:
    if definicion["tipo_sujeto_aplicable"] != legajo["tipo_sujeto"]:
        raise ErrorDeDominio(
            "El requisito no aplica a este tipo de sujeto",
            {"tipo_sujeto": legajo["tipo_sujeto"], "tipo_sujeto_aplicable": definicion["tipo_sujeto_aplicable"]},
        )


def _exigir_vigencia(desde: date, hasta: date) -> None:
    if desde > hasta:
        raise ErrorDeDominio("vigente_desde no puede ser posterior a vigente_hasta", {"vigente_desde": str(desde), "vigente_hasta": str(hasta)})


def _bloquear_legajo(s: Session, tenant_id: str, sujeto_id: str) -> None:
    """Ancla de serialización: toda escritura que cambie qué versión está `vigente` para
    un sujeto (cargar/proponer, rechazar, revertir lote) toma primero el lock de la fila
    de `legajo`. Sin esto, dos escritores concurrentes pasan ambos el `FOR UPDATE` sobre
    el vigente (READ COMMITTED re-evalúa el WHERE tras el commit ajeno y devuelve vacío)
    y el segundo termina chocando contra `uq_documento_vigente`. Orden de bloqueo fijo en
    todo el módulo: legajo → documento (evita deadlocks entre comandos)."""
    s.execute(
        text("SELECT legajo_id FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :sj FOR UPDATE"),
        {"t": tenant_id, "sj": sujeto_id},
    )


def _documento(s: Session, tenant_id: str, documento_id: str, *, bloquear: bool = False) -> dict[str, Any]:
    fila = s.execute(
        text(
            "SELECT documento_id, sujeto_id, requisito_definicion_id, estado_confirmacion, estado_version, "
            "origen_propuesta, version, sucede_a, lote_id FROM modulo1.documento "
            "WHERE tenant_id = :t AND documento_id = :d" + (" FOR UPDATE" if bloquear else "")
        ),
        {"t": tenant_id, "d": documento_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Documento inexistente", {"documento_id": documento_id})
    return dict(fila)


def _exigir_documentos_del_sujeto(s: Session, tenant_id: str, sujeto_id: str, ids: list[str]) -> None:
    """Las evidencias de una acreditación/inducción tienen que ser documentos del mismo
    sujeto y del mismo tenant (RLS ya garantiza lo segundo)."""
    filas = s.execute(
        text("SELECT documento_id FROM modulo1.documento WHERE tenant_id = :t AND sujeto_id = :sj AND documento_id = ANY(CAST(:ids AS uuid[]))"),
        {"t": tenant_id, "sj": sujeto_id, "ids": ids},
    ).scalars().all()
    faltan = sorted(set(ids) - {str(x) for x in filas})
    if faltan:
        raise NoEncontrado("Evidencias inexistentes o de otro sujeto", {"documento_ids": faltan})


def _insertar_version_documento(
    s: Session,
    identidad: Identidad,
    *,
    sujeto_id: str,
    requisito_definicion_id: str,
    vigente_desde: date,
    vigente_hasta: date,
    numero: str | None,
    origen: str,
    estado_confirmacion: str,
    origen_propuesta: bool = False,
    confianza_extraccion: str | None = None,
    lote_id: str | None = None,
    eventos: list[str],
) -> dict[str, Any]:
    """Núcleo compartido por CargarDocumento, ProponerDocumento e ImportarLote: inserta
    la nueva versión `vigente` y sucede a la anterior (si la hay) en la misma
    transacción. Bloquea la fila vigente anterior para que dos cargas concurrentes del
    mismo (sujeto, requisito) se serialicen en vez de chocar contra uq_documento_vigente.
    """
    t = identidad.tenant_id
    _bloquear_legajo(s, t, sujeto_id)
    anterior = s.execute(
        text(
            "SELECT documento_id, version FROM modulo1.documento "
            "WHERE tenant_id = :t AND sujeto_id = :sj AND requisito_definicion_id = :r AND estado_version = 'vigente' "
            "FOR UPDATE"
        ),
        {"t": t, "sj": sujeto_id, "r": requisito_definicion_id},
    ).mappings().first()

    documento_id = str(uuid.uuid4())
    version = (anterior["version"] + 1) if anterior else 1
    sucede_a = str(anterior["documento_id"]) if anterior else None

    if anterior:
        s.execute(
            text("UPDATE modulo1.documento SET estado_version = 'sucedida' WHERE tenant_id = :t AND documento_id = :d"),
            {"t": t, "d": sucede_a},
        )

    s.execute(
        text(
            "INSERT INTO modulo1.documento (documento_id, tenant_id, sujeto_id, requisito_definicion_id, numero, "
            "vigente_desde, vigente_hasta, estado_confirmacion, estado_version, origen_propuesta, version, origen, "
            "confianza_extraccion, lote_id, sucede_a) "
            "VALUES (:d, :t, :sj, :r, :num, :desde, :hasta, :conf, 'vigente', :prop, :ver, :origen, "
            ":confianza, :lote, :sucede_a)"
        ),
        {
            "d": documento_id, "t": t, "sj": sujeto_id, "r": requisito_definicion_id, "num": numero,
            "desde": vigente_desde, "hasta": vigente_hasta, "conf": estado_confirmacion, "prop": origen_propuesta,
            "ver": version, "origen": origen, "confianza": confianza_extraccion,
            "lote": lote_id, "sucede_a": sucede_a,
        },
    )

    registrar_evento(
        s, t, "DocumentoCargado",
        {
            "documento_id": documento_id, "sujeto_id": sujeto_id, "requisito_definicion_id": requisito_definicion_id,
            "version": version, "estado_confirmacion": estado_confirmacion, "origen": origen,
            "origen_propuesta": origen_propuesta, "lote_id": lote_id,
        },
        identidad.usuario_id,
    )
    eventos.append("DocumentoCargado")
    if anterior:
        registrar_evento(
            s, t, "DocumentoSucedido",
            {"documento_id": sucede_a, "sucedido_por": documento_id, "sujeto_id": sujeto_id, "requisito_definicion_id": requisito_definicion_id},
            identidad.usuario_id,
        )
        eventos.append("DocumentoSucedido")

    return {"documento_id": documento_id, "version": version, "sucede_a": sucede_a}


# --------------------------------------------------------------------------- legajos


def alta_de_sujeto(s: Session, identidad: Identidad, body: e.AltaDeSujeto) -> dict[str, Any]:
    t = identidad.tenant_id
    # identificador_natural único por tenant+tipo entre legajos activos: si el sujeto se
    # dio de baja, se admite un alta nueva con el mismo identificador (otro sujeto_id).
    repetido = s.execute(
        text(
            "SELECT sujeto_id FROM modulo1.legajo WHERE tenant_id = :t AND tipo_sujeto = :tipo "
            "AND identificador_natural = :ident AND dado_de_baja_en IS NULL"
        ),
        {"t": t, "tipo": body.tipo_sujeto, "ident": body.identificador_natural},
    ).first()
    if repetido:
        raise Conflicto(
            "Ya existe un legajo activo con ese identificador natural",
            {"tipo_sujeto": body.tipo_sujeto, "identificador_natural": body.identificador_natural, "sujeto_id": repetido[0]},
        )

    sujeto_id = body.sujeto_id or f"{body.tipo_sujeto}_{uuid.uuid4().hex[:8]}"
    existe = s.execute(
        text("SELECT 1 FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :sj"), {"t": t, "sj": sujeto_id}
    ).first()
    if existe:
        raise Conflicto("Ya existe un legajo con ese sujeto_id", {"sujeto_id": sujeto_id})

    legajo_id = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.legajo (legajo_id, tenant_id, sujeto_id, tipo_sujeto, identificador_natural) "
            "VALUES (:l, :t, :sj, :tipo, :ident)"
        ),
        {"l": legajo_id, "t": t, "sj": sujeto_id, "tipo": body.tipo_sujeto, "ident": body.identificador_natural},
    )
    registrar_evento(
        s, t, "LegajoCreado",
        {"legajo_id": legajo_id, "sujeto_id": sujeto_id, "tipo_sujeto": body.tipo_sujeto, "identificador_natural": body.identificador_natural},
        identidad.usuario_id,
    )
    return {"legajo_id": legajo_id, "sujeto_id": sujeto_id, "eventos": ["LegajoCreado"]}


def baja_de_sujeto(s: Session, identidad: Identidad, body: e.BajaDeSujeto) -> dict[str, Any]:
    t = identidad.tenant_id
    legajo = _legajo_activo(s, t, body.sujeto_id)
    s.execute(
        text("UPDATE modulo1.legajo SET dado_de_baja_en = now() WHERE tenant_id = :t AND legajo_id = :l"),
        {"t": t, "l": str(legajo["legajo_id"])},
    )
    registrar_evento(s, t, "LegajoDadoDeBaja", {"legajo_id": str(legajo["legajo_id"]), "sujeto_id": body.sujeto_id}, identidad.usuario_id)
    return {"legajo_id": str(legajo["legajo_id"]), "sujeto_id": body.sujeto_id, "eventos": ["LegajoDadoDeBaja"]}


# --------------------------------------------------------------------------- documentos


def cargar_documento(s: Session, identidad: Identidad, body: e.CargarDocumento) -> dict[str, Any]:
    t = identidad.tenant_id
    legajo = _legajo_activo(s, t, body.sujeto_id)
    definicion = _definicion_activa(s, t, str(body.requisito_definicion_id))
    _exigir_aplicable(definicion, legajo)
    _exigir_vigencia(body.vigente_desde, body.vigente_hasta)

    eventos: list[str] = []
    r = _insertar_version_documento(
        s, identidad,
        sujeto_id=body.sujeto_id, requisito_definicion_id=str(body.requisito_definicion_id),
        vigente_desde=body.vigente_desde, vigente_hasta=body.vigente_hasta, numero=body.numero,
        origen=body.origen, estado_confirmacion=body.estado_confirmacion,
        confianza_extraccion=body.confianza_extraccion, eventos=eventos,
    )
    return {**r, "eventos": eventos}


def proponer_documento(s: Session, identidad: Identidad, body: e.ProponerDocumento) -> dict[str, Any]:
    # Técnico: solo sobre su propio legajo (matriz 2.2).
    if not identidad.sujeto_id or identidad.sujeto_id != body.sujeto_id:
        raise Prohibido("Un técnico solo puede proponer documentos sobre su propio legajo", {"sujeto_id": body.sujeto_id})
    t = identidad.tenant_id
    legajo = _legajo_activo(s, t, body.sujeto_id)
    definicion = _definicion_activa(s, t, str(body.requisito_definicion_id))
    _exigir_aplicable(definicion, legajo)
    _exigir_vigencia(body.vigente_desde, body.vigente_hasta)

    eventos: list[str] = []
    r = _insertar_version_documento(
        s, identidad,
        sujeto_id=body.sujeto_id, requisito_definicion_id=str(body.requisito_definicion_id),
        vigente_desde=body.vigente_desde, vigente_hasta=body.vigente_hasta, numero=body.numero,
        origen=body.origen, estado_confirmacion="declarado", origen_propuesta=True,
        eventos=eventos,
    )
    return {**r, "eventos": eventos}


def confirmar_documento(s: Session, identidad: Identidad, body: e.ConfirmarDocumento) -> dict[str, Any]:
    t = identidad.tenant_id
    doc = _documento(s, t, str(body.documento_id), bloquear=True)
    if doc["estado_version"] != "vigente":
        raise Conflicto("Solo se confirma la versión vigente", {"estado_version": doc["estado_version"]})
    if doc["estado_confirmacion"] != "declarado":
        raise Conflicto("El documento no está en estado declarado", {"estado_confirmacion": doc["estado_confirmacion"]})

    s.execute(
        text("UPDATE modulo1.documento SET estado_confirmacion = 'verificado' WHERE tenant_id = :t AND documento_id = :d"),
        {"t": t, "d": str(doc["documento_id"])},
    )
    eventos = ["DocumentoVerificado"]
    registrar_evento(
        s, t, "DocumentoVerificado",
        {"documento_id": str(doc["documento_id"]), "sujeto_id": doc["sujeto_id"], "requisito_definicion_id": str(doc["requisito_definicion_id"])},
        identidad.usuario_id,
    )

    # Regularización automática: si cubre el requisito de una Excepción otorgada del
    # mismo sujeto, esa excepción pasa a `regularizada` (2.2 / 4.4).
    regularizadas: list[str] = []
    if doc["requisito_definicion_id"] is not None:
        filas = s.execute(
            text(
                "UPDATE modulo1.excepcion SET estado = 'regularizada' "
                "WHERE tenant_id = :t AND sujeto_id = :sj AND requisito_definicion_id = :r AND estado = 'otorgada' "
                "RETURNING excepcion_id, commitment_id"
            ),
            {"t": t, "sj": doc["sujeto_id"], "r": str(doc["requisito_definicion_id"])},
        ).mappings().all()
        for f in filas:
            regularizadas.append(str(f["excepcion_id"]))
            registrar_evento(
                s, t, "ExcepcionRegularizada",
                {"excepcion_id": str(f["excepcion_id"]), "commitment_id": f["commitment_id"], "documento_id": str(doc["documento_id"]),
                 "sujeto_id": doc["sujeto_id"], "requisito_definicion_id": str(doc["requisito_definicion_id"])},
                identidad.usuario_id,
            )
            eventos.append("ExcepcionRegularizada")

    return {"documento_id": str(doc["documento_id"]), "excepciones_regularizadas": regularizadas, "eventos": eventos}


def rechazar_propuesta(s: Session, identidad: Identidad, body: e.RechazarPropuesta) -> dict[str, Any]:
    t = identidad.tenant_id
    doc = _documento(s, t, str(body.documento_id))
    _bloquear_legajo(s, t, doc["sujeto_id"])
    doc = _documento(s, t, str(body.documento_id), bloquear=True)  # re-lectura ya serializada
    if not doc["origen_propuesta"]:
        raise Conflicto("El documento no es una propuesta", {"documento_id": str(doc["documento_id"])})
    if doc["estado_confirmacion"] != "declarado":
        raise Conflicto("Solo se rechaza una propuesta declarada", {"estado_confirmacion": doc["estado_confirmacion"]})
    if doc["estado_version"] != "vigente":
        # `rechazada` es terminal; una propuesta ya sucedida por otra versión tampoco se
        # rechaza (la sucesión ya la dejó fuera de juego).
        raise Conflicto("La propuesta ya no está vigente", {"estado_version": doc["estado_version"]})

    s.execute(
        text("UPDATE modulo1.documento SET estado_version = 'rechazada' WHERE tenant_id = :t AND documento_id = :d"),
        {"t": t, "d": str(doc["documento_id"])},
    )
    restaurado = _restaurar_sucedido(s, t, doc["sucede_a"])
    registrar_evento(
        s, t, "DocumentoRechazado",
        {"documento_id": str(doc["documento_id"]), "sujeto_id": doc["sujeto_id"], "requisito_definicion_id": str(doc["requisito_definicion_id"]),
         "motivo": body.motivo, "restaurado_documento_id": restaurado},
        identidad.usuario_id,
    )
    return {"documento_id": str(doc["documento_id"]), "restaurado_documento_id": restaurado, "eventos": ["DocumentoRechazado"]}


def _restaurar_sucedido(s: Session, tenant_id: str, sucede_a: Any) -> str | None:
    """Vuelve a `vigente` el antecesor no terminal más cercano de la versión que se está
    anulando, siguiendo la cadena `sucede_a`.

    Regla cerrada (2.2 de especificacion.md: una versión anulada "es como si nunca hubiera
    llegado a ser candidata"): al anular una versión se vuelve al estado previo a ella. Si
    su antecesora inmediata ya es terminal (`rechazada` / `revertida_por_lote` — por
    ejemplo, un lote revertido después de que el técnico propuso sobre él), se sigue
    subiendo por la cadena hasta encontrar una `sucedida`. Una versión terminal nunca se
    resucita. Si no queda ninguna, el sujeto se queda sin vigente para ese requisito."""
    actual = sucede_a
    visitados: set[str] = set()
    while actual is not None and str(actual) not in visitados:
        visitados.add(str(actual))
        fila = s.execute(
            text("SELECT estado_version, sucede_a FROM modulo1.documento WHERE tenant_id = :t AND documento_id = :d FOR UPDATE"),
            {"t": tenant_id, "d": str(actual)},
        ).mappings().first()
        if fila is None:
            return None
        if fila["estado_version"] == "sucedida":
            s.execute(
                text("UPDATE modulo1.documento SET estado_version = 'vigente' WHERE tenant_id = :t AND documento_id = :d"),
                {"t": tenant_id, "d": str(actual)},
            )
            return str(actual)
        if fila["estado_version"] == "vigente":
            # Ya hay un vigente más nuevo en la cadena: no se toca (uq_documento_vigente).
            return None
        actual = fila["sucede_a"]
    return None


# --------------------------------------------------------------------------- competencias / inducciones


def registrar_acreditacion_de_competencia(
    s: Session, identidad: Identidad, body: e.RegistrarAcreditacionDeCompetencia
) -> dict[str, Any]:
    t = identidad.tenant_id
    legajo = _legajo_activo(s, t, body.persona_id)
    if legajo["tipo_sujeto"] != "persona":
        raise ErrorDeDominio("Las competencias se acreditan a personas", {"tipo_sujeto": legajo["tipo_sujeto"]})
    definicion = _definicion_activa(s, t, str(body.requisito_definicion_id))
    if definicion["categoria"] != "competencia":
        raise ErrorDeDominio("El requisito no es de categoría competencia", {"categoria": definicion["categoria"]})
    _exigir_aplicable(definicion, legajo)
    _exigir_vigencia(body.vigente_desde, body.vigente_hasta)
    evidencias = [str(x) for x in body.evidencias]
    _exigir_documentos_del_sujeto(s, t, body.persona_id, evidencias)

    acreditacion_id = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.acreditacion_competencia (acreditacion_id, tenant_id, persona_id, requisito_definicion_id, "
            "vigente_desde, vigente_hasta, estado_confirmacion, evidencias) "
            "VALUES (:a, :t, :p, :r, :desde, :hasta, :conf, CAST(:ev AS uuid[]))"
        ),
        {"a": acreditacion_id, "t": t, "p": body.persona_id, "r": str(body.requisito_definicion_id),
         "desde": body.vigente_desde, "hasta": body.vigente_hasta, "conf": body.estado_confirmacion, "ev": evidencias},
    )
    registrar_evento(
        s, t, "AcreditacionDeCompetenciaRegistrada",
        {"acreditacion_id": acreditacion_id, "persona_id": body.persona_id, "requisito_definicion_id": str(body.requisito_definicion_id),
         "vigente_desde": body.vigente_desde, "vigente_hasta": body.vigente_hasta, "evidencias": evidencias},
        identidad.usuario_id,
    )
    return {"acreditacion_id": acreditacion_id, "eventos": ["AcreditacionDeCompetenciaRegistrada"]}


def registrar_induccion(s: Session, identidad: Identidad, body: e.RegistrarInduccion) -> dict[str, Any]:
    t = identidad.tenant_id
    legajo = _legajo_activo(s, t, body.persona_id)
    if legajo["tipo_sujeto"] != "persona":
        raise ErrorDeDominio("Las inducciones se registran a personas", {"tipo_sujeto": legajo["tipo_sujeto"]})
    definicion = _definicion_activa(s, t, str(body.requisito_definicion_id))
    if definicion["categoria"] != "induccion":
        raise ErrorDeDominio("El requisito no es de categoría inducción", {"categoria": definicion["categoria"]})
    if str(definicion["locacion_id"]) != str(body.locacion_id):
        raise ErrorDeDominio(
            "La locación no coincide con la de la definición de inducción",
            {"locacion_id": str(body.locacion_id), "locacion_de_la_definicion": str(definicion["locacion_id"])},
        )
    _exigir_aplicable(definicion, legajo)
    _exigir_vigencia(body.vigente_desde, body.vigente_hasta)
    _exigir_documentos_del_sujeto(s, t, body.persona_id, [str(body.evidencia)])

    induccion_id = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.induccion (induccion_id, tenant_id, persona_id, locacion_id, requisito_definicion_id, "
            "vigente_desde, vigente_hasta, estado_confirmacion, evidencia) "
            "VALUES (:i, :t, :p, :loc, :r, :desde, :hasta, :conf, :ev)"
        ),
        {"i": induccion_id, "t": t, "p": body.persona_id, "loc": str(body.locacion_id), "r": str(body.requisito_definicion_id),
         "desde": body.vigente_desde, "hasta": body.vigente_hasta, "conf": body.estado_confirmacion, "ev": str(body.evidencia)},
    )
    registrar_evento(
        s, t, "InduccionRegistrada",
        {"induccion_id": induccion_id, "persona_id": body.persona_id, "locacion_id": str(body.locacion_id),
         "requisito_definicion_id": str(body.requisito_definicion_id), "vigente_desde": body.vigente_desde,
         "vigente_hasta": body.vigente_hasta, "evidencia": str(body.evidencia)},
        identidad.usuario_id,
    )
    return {"induccion_id": induccion_id, "eventos": ["InduccionRegistrada"]}


# --------------------------------------------------------------------------- lotes


def _politica_reimportacion(s: Session, tenant_id: str, fila: e.FilaDeLote) -> dict[str, Any]:
    """Tres casos de 2.11 de modelo-dominio.md contra el documento vigente del mismo
    (sujeto, requisito), si lo hay. Devuelve {"accion": "crear"|"renovar"|"sin_cambios"}
    o levanta ErrorDeDominio (rechazo de la fila) por conflicto con un dato verificado."""
    vigente = s.execute(
        text(
            "SELECT documento_id, numero, vigente_desde, vigente_hasta, estado_confirmacion FROM modulo1.documento "
            "WHERE tenant_id = :t AND sujeto_id = :sj AND requisito_definicion_id = :r AND estado_version = 'vigente'"
        ),
        {"t": tenant_id, "sj": fila.sujeto_id, "r": str(fila.requisito_definicion_id)},
    ).mappings().first()
    if vigente is None:
        return {"accion": "crear", "documento_id": None}
    mismo_numero = fila.numero is None or vigente["numero"] is None or fila.numero == vigente["numero"]
    if fila.vigente_desde == vigente["vigente_desde"] and fila.vigente_hasta == vigente["vigente_hasta"] and mismo_numero:
        return {"accion": "sin_cambios", "documento_id": str(vigente["documento_id"])}
    if fila.vigente_hasta > vigente["vigente_hasta"]:
        return {"accion": "renovar", "documento_id": str(vigente["documento_id"])}
    if vigente["estado_confirmacion"] != "declarado":
        raise ErrorDeDominio(
            "conflicto con dato verificado: la fila contradice un documento verificado con vigencia no posterior",
            {"documento_vigente_id": str(vigente["documento_id"]), "vigente_hasta_actual": str(vigente["vigente_hasta"]),
             "vigente_hasta_fila": str(fila.vigente_hasta), "estado_confirmacion": vigente["estado_confirmacion"]},
            codigo="conflicto_con_dato_verificado",
        )
    # El vigente es solo `declarado` (misma confianza que la planilla): la planilla es el
    # dato más reciente y entra como versión nueva.
    return {"accion": "renovar", "documento_id": str(vigente["documento_id"])}


def _clave_lote(lote_id: str) -> str:
    return f"lote:{lote_id}"


def importar_lote(s: Session, identidad: Identidad, body: e.ImportarLote) -> dict[str, Any]:
    """Una transacción, idempotente por `lote_id` (8.2): si el lote ya existe se devuelve
    el resultado guardado bajo `lote:<lote_id>` sin re-aplicar nada. Las filas inválidas
    se rechazan una por una (van a `detalle_filas_rechazadas`); las válidas se aplican
    como CargarDocumento con `lote_id`."""
    t = identidad.tenant_id
    lote_id = str(body.lote_id)

    previo = buscar_resultado(s, t, _clave_lote(lote_id))
    if previo is not None:
        return previo
    existente = s.execute(
        text(
            "SELECT estado, filas_totales, filas_aceptadas, filas_rechazadas, detalle_filas_rechazadas "
            "FROM modulo1.lote_importacion WHERE tenant_id = :t AND lote_id = :l"
        ),
        {"t": t, "l": lote_id},
    ).mappings().first()
    if existente is not None:
        # El registro de idempotencia venció (24 h) pero el lote existe: no se re-aplica.
        return {
            "lote_id": lote_id, "estado": existente["estado"], "filas_totales": existente["filas_totales"],
            "filas_aceptadas": existente["filas_aceptadas"], "filas_rechazadas": existente["filas_rechazadas"],
            "detalle_filas_rechazadas": existente["detalle_filas_rechazadas"], "documentos": [], "eventos": [],
            "ya_aplicado": True,
        }

    # 1) Validación fila por fila, sin escribir todavía. Incluye las tres políticas de
    #    "documento existente al reimportar" (2.11 de modelo-dominio.md): vigencia
    #    posterior → renovación; coincide con lo que ya hay → no hace nada, no duplica;
    #    contradice un dato ya verificado con vigencia no posterior → rechazada (un dato
    #    de menor confianza nunca pisa uno de mayor confianza sin confirmación humana).
    validas: list[tuple[int, e.FilaDeLote]] = []
    sin_cambios: list[dict[str, Any]] = []
    rechazadas: list[dict[str, Any]] = []
    for i, fila in enumerate(body.filas):
        try:
            legajo = _legajo_activo(s, t, fila.sujeto_id)
            definicion = _definicion_activa(s, t, str(fila.requisito_definicion_id))
            _exigir_aplicable(definicion, legajo)
            _exigir_vigencia(fila.vigente_desde, fila.vigente_hasta)
            politica = _politica_reimportacion(s, t, fila)
        except ErrorDeDominio as err:
            rechazadas.append({"fila": i, "sujeto_id": fila.sujeto_id, "requisito_definicion_id": str(fila.requisito_definicion_id),
                               "codigo": err.codigo, "motivo": err.mensaje, "detalles": err.detalles})
            continue
        if politica["accion"] == "sin_cambios":
            sin_cambios.append({"fila": i, "sujeto_id": fila.sujeto_id, "requisito_definicion_id": str(fila.requisito_definicion_id),
                                "documento_id": politica["documento_id"]})
            continue
        validas.append((i, fila))

    # 2) Cabecera del lote (los documentos referencian lote_id por FK).
    # Una fila "sin cambios" cuenta como aceptada (no es un error) aunque no cree versión.
    aceptadas = len(validas) + len(sin_cambios)
    s.execute(
        text(
            "INSERT INTO modulo1.lote_importacion (lote_id, tenant_id, origen, entidad, filas_totales, filas_aceptadas, "
            "filas_rechazadas, detalle_filas_rechazadas, estado, hash_archivo) "
            "VALUES (:l, :t, :o, 'legajos', :tot, :ok, :rech, CAST(:det AS jsonb), 'aplicado', :hash)"
        ),
        {"l": lote_id, "t": t, "o": body.origen, "tot": len(body.filas), "ok": aceptadas, "rech": len(rechazadas),
         "det": json.dumps(rechazadas, default=str, ensure_ascii=False), "hash": body.hash_archivo},
    )

    # 3) Aplicación de las válidas.
    eventos: list[str] = []
    documentos: list[dict[str, Any]] = []
    for i, fila in validas:
        r = _insertar_version_documento(
            s, identidad,
            sujeto_id=fila.sujeto_id, requisito_definicion_id=str(fila.requisito_definicion_id),
            vigente_desde=fila.vigente_desde, vigente_hasta=fila.vigente_hasta, numero=fila.numero,
            origen=body.origen, estado_confirmacion=fila.estado_confirmacion, lote_id=lote_id, eventos=eventos,
        )
        documentos.append({"fila": i, **r})

    registrar_evento(
        s, t, "LoteAplicado",
        {"lote_id": lote_id, "entidad": "legajos", "origen": body.origen, "filas_totales": len(body.filas),
         "filas_aceptadas": aceptadas, "filas_rechazadas": len(rechazadas), "filas_sin_cambios": len(sin_cambios)},
        identidad.usuario_id,
    )
    eventos.append("LoteAplicado")

    resultado = {
        "lote_id": lote_id, "estado": "aplicado", "filas_totales": len(body.filas), "filas_aceptadas": aceptadas,
        "filas_rechazadas": len(rechazadas), "detalle_filas_rechazadas": rechazadas, "documentos": documentos,
        "filas_sin_cambios": sin_cambios,
        "eventos": eventos,
    }
    guardar_resultado(s, t, _clave_lote(lote_id), resultado)
    return resultado


def revertir_lote(s: Session, identidad: Identidad, body: e.RevertirLote) -> dict[str, Any]:
    t = identidad.tenant_id
    lote_id = str(body.lote_id)
    lote = s.execute(
        text("SELECT estado, entidad FROM modulo1.lote_importacion WHERE tenant_id = :t AND lote_id = :l FOR UPDATE"),
        {"t": t, "l": lote_id},
    ).mappings().first()
    if lote is None:
        raise NoEncontrado("Lote inexistente", {"lote_id": lote_id})
    if lote["entidad"] != "legajos":
        raise ErrorDeDominio("Este comando solo revierte lotes de legajos", {"entidad": lote["entidad"]})
    if lote["estado"] != "aplicado":
        raise Conflicto("Solo se revierte un lote aplicado", {"estado": lote["estado"]})

    sujetos = s.execute(
        text("SELECT DISTINCT sujeto_id FROM modulo1.documento WHERE tenant_id = :t AND lote_id = :l ORDER BY sujeto_id"),
        {"t": t, "l": lote_id},
    ).scalars().all()
    for sujeto_id in sujetos:  # orden fijo (alfabético) → sin deadlock entre dos reversiones
        _bloquear_legajo(s, t, sujeto_id)
    docs = s.execute(
        text(
            "SELECT documento_id, estado_version, sucede_a FROM modulo1.documento "
            "WHERE tenant_id = :t AND lote_id = :l ORDER BY creado_en FOR UPDATE"
        ),
        {"t": t, "l": lote_id},
    ).mappings().all()

    revertidos: list[str] = []
    restaurados: list[str] = []
    for d in docs:
        if d["estado_version"] in ("rechazada", "revertida_por_lote"):
            continue
        s.execute(
            text("UPDATE modulo1.documento SET estado_version = 'revertida_por_lote' WHERE tenant_id = :t AND documento_id = :d"),
            {"t": t, "d": str(d["documento_id"])},
        )
        revertidos.append(str(d["documento_id"]))
        # Solo se restaura el antecesor si el documento del lote seguía vigente: si ya
        # fue sucedido por una carga posterior, esa carga posterior es la vigente y
        # restaurar dos versiones rompería uq_documento_vigente.
        if d["estado_version"] == "vigente":
            r = _restaurar_sucedido(s, t, d["sucede_a"])
            if r:
                restaurados.append(r)

    s.execute(
        text("UPDATE modulo1.lote_importacion SET estado = 'revertido' WHERE tenant_id = :t AND lote_id = :l"),
        {"t": t, "l": lote_id},
    )
    registrar_evento(
        s, t, "LoteRevertido",
        {"lote_id": lote_id, "documentos_revertidos": revertidos, "documentos_restaurados": restaurados},
        identidad.usuario_id,
    )
    return {"lote_id": lote_id, "documentos_revertidos": revertidos, "documentos_restaurados": restaurados, "eventos": ["LoteRevertido"]}


# --------------------------------------------------------------------------- supervisor


def _exigir_supervisor(s: Session, tenant_id: str, usuario_id: str) -> None:
    fila = s.execute(
        text("SELECT roles, activo FROM modulo1.usuario WHERE tenant_id = :t AND usuario_id = :u"),
        {"t": tenant_id, "u": usuario_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Usuario inexistente", {"supervisor_usuario_id": usuario_id})
    if not fila["activo"] or "supervisor" not in (fila["roles"] or []):
        raise ErrorDeDominio("El usuario no es un supervisor activo", {"supervisor_usuario_id": usuario_id, "roles": list(fila["roles"] or [])})


def _asignacion_vigente(s: Session, tenant_id: str, sujeto_id: str) -> dict[str, Any] | None:
    fila = s.execute(
        text(
            "SELECT asignacion_id, supervisor_usuario_id, desde FROM modulo1.asignacion_supervisor "
            "WHERE tenant_id = :t AND sujeto_id = :sj AND estado = 'vigente' FOR UPDATE"
        ),
        {"t": tenant_id, "sj": sujeto_id},
    ).mappings().first()
    return dict(fila) if fila else None


def _abrir_asignacion(s: Session, identidad: Identidad, sujeto_id: str, supervisor_usuario_id: str, desde: date) -> str:
    asignacion_id = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.asignacion_supervisor (asignacion_id, tenant_id, sujeto_id, supervisor_usuario_id, desde, asignada_por) "
            "VALUES (:a, :t, :sj, :sup, :desde, :por)"
        ),
        {"a": asignacion_id, "t": identidad.tenant_id, "sj": sujeto_id, "sup": supervisor_usuario_id, "desde": desde, "por": identidad.usuario_id},
    )
    return asignacion_id


def asignar_supervisor(s: Session, identidad: Identidad, body: e.AsignarSupervisor) -> dict[str, Any]:
    t = identidad.tenant_id
    _legajo_activo(s, t, body.sujeto_id, bloquear=True)  # serializa dos primeras asignaciones
    sup = str(body.supervisor_usuario_id)
    _exigir_supervisor(s, t, sup)
    if _asignacion_vigente(s, t, body.sujeto_id) is not None:
        raise Conflicto("El sujeto ya tiene un supervisor vigente: usar reasignar_supervisor", {"sujeto_id": body.sujeto_id})
    desde = body.desde or hoy_del_tenant(s, t)
    asignacion_id = _abrir_asignacion(s, identidad, body.sujeto_id, sup, desde)
    registrar_evento(
        s, t, "SupervisorAsignado",
        {"asignacion_id": asignacion_id, "sujeto_id": body.sujeto_id, "supervisor_usuario_id": sup, "desde": desde},
        identidad.usuario_id,
    )
    return {"asignacion_id": asignacion_id, "sujeto_id": body.sujeto_id, "desde": desde, "eventos": ["SupervisorAsignado"]}


def reasignar_supervisor(s: Session, identidad: Identidad, body: e.ReasignarSupervisor) -> dict[str, Any]:
    t = identidad.tenant_id
    _legajo_activo(s, t, body.sujeto_id, bloquear=True)
    sup = str(body.supervisor_usuario_id)
    _exigir_supervisor(s, t, sup)
    actual = _asignacion_vigente(s, t, body.sujeto_id)
    if actual is None:
        raise Conflicto("El sujeto no tiene supervisor vigente: usar asignar_supervisor", {"sujeto_id": body.sujeto_id})
    desde = body.desde or hoy_del_tenant(s, t)
    if desde <= actual["desde"]:
        raise ErrorDeDominio(
            "La reasignación debe empezar después del inicio de la asignación vigente",
            {"desde": str(desde), "desde_vigente": str(actual["desde"])},
        )
    hasta_anterior = desde - timedelta(days=1)
    s.execute(
        text(
            "UPDATE modulo1.asignacion_supervisor SET estado = 'cerrada', hasta = :hasta "
            "WHERE tenant_id = :t AND asignacion_id = :a"
        ),
        {"t": t, "a": str(actual["asignacion_id"]), "hasta": hasta_anterior},
    )
    asignacion_id = _abrir_asignacion(s, identidad, body.sujeto_id, sup, desde)
    registrar_evento(
        s, t, "SupervisorReasignado",
        {"asignacion_id": asignacion_id, "asignacion_cerrada_id": str(actual["asignacion_id"]), "sujeto_id": body.sujeto_id,
         "supervisor_anterior_usuario_id": str(actual["supervisor_usuario_id"]), "supervisor_usuario_id": sup,
         "desde": desde, "hasta_anterior": hasta_anterior},
        identidad.usuario_id,
    )
    return {
        "asignacion_id": asignacion_id, "asignacion_cerrada_id": str(actual["asignacion_id"]), "sujeto_id": body.sujeto_id,
        "desde": desde, "hasta_anterior": hasta_anterior, "eventos": ["SupervisorReasignado"],
    }
