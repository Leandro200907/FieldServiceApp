"""Comandos de Operación: custodia de recursos, excepciones, constancias del cliente y
evaluación de habilitación a pedido (4.2–4.5 de especificacion.md).

Cada función recibe una `tenant_session` ya abierta y la `Identidad` del usuario; hace
el chequeo de rol (matriz 2.2 de no-funcionales), aplica la regla de dominio, registra
los eventos en la misma transacción y devuelve el dict que el router responde
(ids generados + `eventos`). Nada acá abre sesiones ni conoce HTTP.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado, Prohibido
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento
from app.comun.reloj import ahora_utc, hoy_del_tenant
from app.auth.alcance import decision_visible, sujeto_en_alcance
from app.core.orquestacion import buscar_oc, clasificacion_vigente, decidir_habilitacion
from app.core.tipos import Clasificacion

__all__ = [
    "cambiar_custodia",
    "corregir_custodia",
    "otorgar_excepcion",
    "revocar_excepcion",
    "registrar_constancia_del_cliente",
    "revocar_constancia_del_cliente",
    "evaluar_habilitacion",
    "clasificacion_vigente",
]

TIPOS_RECURSO_CUSTODIABLE = ("vehiculo", "equipo")


def _bloquear_legajo(session: Session, tenant_id: str, sujeto_id: str) -> dict[str, Any]:
    """Ancla estable para la unicidad de filas ACTIVAS por sujeto (M-02, 0012): dos
    transacciones que quieran crear la primera excepción/constancia del mismo sujeto se
    serializan sobre su legajo, así la segunda ve lo que hizo la primera en lugar de
    chocar contra el índice. Devuelve el legajo (tipo y baja) o 404 si no existe."""
    fila = session.execute(
        text("SELECT sujeto_id, tipo_sujeto, dado_de_baja_en FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s FOR UPDATE"),
        {"t": tenant_id, "s": sujeto_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Legajo inexistente", {"sujeto_id": sujeto_id})
    return dict(fila)


def _es_colision_activa(err: IntegrityError, *indices: str) -> bool:
    diag = getattr(getattr(err, "orig", None), "diag", None)
    return getattr(diag, "constraint_name", None) in indices


# --------------------------------------------------------------------------- custodia


def _custodia_de(session: Session, tenant_id: str, recurso_id: str, tipo_recurso: str) -> str:
    """Devuelve el custodia_id del recurso; lo crea si es la primera vez que se custodia."""
    fila = session.execute(
        text(
            "SELECT custodia_id FROM modulo1.custodia_recurso "
            "WHERE tenant_id = :t AND recurso_id = :r AND tipo_recurso = :tr FOR UPDATE"
        ),
        {"t": tenant_id, "r": recurso_id, "tr": tipo_recurso},
    ).first()
    if fila:
        return str(fila[0])
    nuevo = session.execute(
        text(
            "INSERT INTO modulo1.custodia_recurso (tenant_id, recurso_id, tipo_recurso) "
            "VALUES (:t, :r, :tr) RETURNING custodia_id"
        ),
        {"t": tenant_id, "r": recurso_id, "tr": tipo_recurso},
    ).first()
    return str(nuevo[0])


def _validar_recurso_custodiable(session: Session, tenant_id: str, recurso_id: str, tipo_recurso: str) -> None:
    """El recurso existe en el tenant, es vehículo o equipo del tipo declarado y está activo.
    Bloquea su legajo (FOR UPDATE): es el ancla que serializa dos primeras custodias del
    mismo recurso (M-03), así la segunda ve la custodia y el período que creó la primera."""
    if tipo_recurso not in TIPOS_RECURSO_CUSTODIABLE:
        raise ErrorDeDominio("Solo vehículos y equipos tienen custodia", {"tipo_recurso": tipo_recurso})
    legajo = _bloquear_legajo(session, tenant_id, recurso_id)
    if legajo["tipo_sujeto"] != tipo_recurso:
        raise ErrorDeDominio(
            "El recurso no es del tipo declarado",
            {"recurso_id": recurso_id, "tipo_recurso": tipo_recurso, "tipo_sujeto": legajo["tipo_sujeto"]},
            codigo="recurso_no_custodiable",
        )
    if legajo["dado_de_baja_en"] is not None:
        raise ErrorDeDominio("El recurso está dado de baja", {"recurso_id": recurso_id}, codigo="legajo_dado_de_baja")


def _validar_custodio(session: Session, identidad: Identidad, tipo_recurso: str, custodio_id: str | None) -> None:
    """Custodio: persona activa del tenant, dentro del universo del supervisor que opera
    (2.3 §3). Vacío solo para equipo (`sin_custodio_personal`, documentacion-habilitante
    1.5 bis); un vehículo siempre tiene conductor responsable (1.5)."""
    tenant_id = identidad.tenant_id
    if custodio_id is None:
        if tipo_recurso != "equipo":
            raise ErrorDeDominio(
                "Un vehículo siempre tiene custodio; `sin_custodio_personal` solo vale para equipos",
                {"tipo_recurso": tipo_recurso},
                codigo="custodio_requerido",
            )
        return
    legajo = session.execute(
        text("SELECT tipo_sujeto, dado_de_baja_en FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s"),
        {"t": tenant_id, "s": custodio_id},
    ).mappings().first()
    if legajo is None:
        raise NoEncontrado("Custodio inexistente", {"custodio_id": custodio_id})
    if legajo["tipo_sujeto"] != "persona":
        raise ErrorDeDominio(
            "Solo una persona puede ser custodio",
            {"custodio_id": custodio_id, "tipo_sujeto": legajo["tipo_sujeto"]},
            codigo="custodio_no_permitido",
        )
    if legajo["dado_de_baja_en"] is not None:
        raise ErrorDeDominio("El custodio está dado de baja", {"custodio_id": custodio_id}, codigo="legajo_dado_de_baja")
    if not sujeto_en_alcance(session, identidad, custodio_id, hoy_del_tenant(session, tenant_id)):
        raise Prohibido("El custodio está fuera del universo del supervisor", {"custodio_id": custodio_id})


def cambiar_custodia(
    session: Session,
    identidad: Identidad,
    *,
    recurso_id: str,
    tipo_recurso: str,
    custodio_id: str | None,
    desde: date,
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.SUPERVISOR)
    tenant_id = identidad.tenant_id
    _validar_recurso_custodiable(session, tenant_id, recurso_id, tipo_recurso)
    _validar_custodio(session, identidad, tipo_recurso, custodio_id)
    custodia_id = _custodia_de(session, tenant_id, recurso_id, tipo_recurso)

    vigente = session.execute(
        text(
            "SELECT periodo_id, desde, custodio_id FROM modulo1.periodo_custodia "
            "WHERE tenant_id = :t AND custodia_id = :c AND estado = 'vigente' FOR UPDATE"
        ),
        {"t": tenant_id, "c": custodia_id},
    ).mappings().first()

    periodo_cerrado_id: str | None = None
    if vigente is not None:
        if desde <= vigente["desde"]:
            raise Conflicto(
                "El nuevo período tiene que empezar después del vigente",
                {"desde_vigente": str(vigente["desde"]), "desde_nuevo": str(desde)},
            )
        periodo_cerrado_id = str(vigente["periodo_id"])
        session.execute(
            text(
                "UPDATE modulo1.periodo_custodia SET estado = 'cerrado', hasta = :hasta "
                "WHERE tenant_id = :t AND periodo_id = :p"
            ),
            {"t": tenant_id, "p": periodo_cerrado_id, "hasta": desde - timedelta(days=1)},
        )

    try:
        periodo_id = str(
            session.execute(
                text(
                    "INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde, estado) "
                    "VALUES (:t, :c, :cu, :d, 'vigente') RETURNING periodo_id"
                ),
                {"t": tenant_id, "c": custodia_id, "cu": custodio_id, "d": desde},
            ).scalar()
        )
    except IntegrityError as err:
        if not _es_colision_activa(err, "uq_periodo_custodia_vigente"):
            raise
        raise Conflicto(
            "El recurso ya tiene un período de custodia vigente", {"custodia_id": custodia_id},
            codigo="custodia_vigente_duplicada",
        ) from err
    registrar_evento(
        session,
        tenant_id,
        "CustodiaCambiada",
        {
            "custodia_id": custodia_id,
            "recurso_id": recurso_id,
            "tipo_recurso": tipo_recurso,
            "periodo_id": periodo_id,
            "periodo_cerrado_id": periodo_cerrado_id,
            "custodio_anterior_id": vigente["custodio_id"] if vigente else None,
            "custodio_id": custodio_id,
            "desde": desde,
        },
        identidad.usuario_id,
    )
    return {
        "custodia_id": custodia_id,
        "periodo_id": periodo_id,
        "periodo_cerrado_id": periodo_cerrado_id,
        "eventos": ["CustodiaCambiada"],
    }


def corregir_custodia(
    session: Session,
    identidad: Identidad,
    *,
    periodo_id: str,
    custodio_id: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    motivo: str | None = None,
) -> dict[str, Any]:
    """Reemplaza un período por otro con los datos corregidos. El viejo queda
    `corregido` (con `corregido_por` → nuevo), nunca se borra. Si el corregido era el
    vigente, el nuevo queda vigente (y por eso no admite `hasta`)."""
    identidad.exigir_rol(Rol.SUPERVISOR)
    tenant_id = identidad.tenant_id
    viejo = session.execute(
        text(
            "SELECT periodo_id, custodia_id, custodio_id, desde, hasta, estado FROM modulo1.periodo_custodia "
            "WHERE tenant_id = :t AND periodo_id = :p FOR UPDATE"
        ),
        {"t": tenant_id, "p": periodo_id},
    ).mappings().first()
    if viejo is None:
        raise NoEncontrado("Período de custodia inexistente", {"periodo_id": periodo_id})
    if viejo["estado"] == "corregido":
        raise Conflicto("El período ya fue corregido; corregí el que lo reemplazó", {"periodo_id": periodo_id})

    nuevo_estado = viejo["estado"]  # vigente sigue vigente, cerrado sigue cerrado
    nuevo_custodio = custodio_id if custodio_id is not None else viejo["custodio_id"]
    tipo_recurso = session.execute(
        text("SELECT tipo_recurso FROM modulo1.custodia_recurso WHERE tenant_id = :t AND custodia_id = :c FOR UPDATE"),
        {"t": tenant_id, "c": str(viejo["custodia_id"])},
    ).scalar()
    _validar_custodio(session, identidad, tipo_recurso, nuevo_custodio)
    nuevo_desde = desde if desde is not None else viejo["desde"]
    if nuevo_estado == "vigente":
        if hasta is not None:
            raise ErrorDeDominio("El período vigente no lleva `hasta`; para cerrarlo usá cambiar_custodia")
        nuevo_hasta = None
    else:
        nuevo_hasta = hasta if hasta is not None else viejo["hasta"]
        if nuevo_hasta is not None and nuevo_hasta < nuevo_desde:
            raise ErrorDeDominio("`hasta` no puede ser anterior a `desde`", {"desde": str(nuevo_desde), "hasta": str(nuevo_hasta)})

    # Primero se saca al viejo de 'vigente' (índice único parcial), después se inserta el
    # nuevo, y recién entonces se apunta corregido_por (FK al nuevo).
    session.execute(
        text("UPDATE modulo1.periodo_custodia SET estado = 'corregido' WHERE tenant_id = :t AND periodo_id = :p"),
        {"t": tenant_id, "p": periodo_id},
    )
    nuevo_id = str(
        session.execute(
            text(
                "INSERT INTO modulo1.periodo_custodia (tenant_id, custodia_id, custodio_id, desde, hasta, estado) "
                "VALUES (:t, :c, :cu, :d, :h, :e) RETURNING periodo_id"
            ),
            {"t": tenant_id, "c": str(viejo["custodia_id"]), "cu": nuevo_custodio, "d": nuevo_desde, "h": nuevo_hasta, "e": nuevo_estado},
        ).scalar()
    )
    session.execute(
        text("UPDATE modulo1.periodo_custodia SET corregido_por = :n WHERE tenant_id = :t AND periodo_id = :p"),
        {"t": tenant_id, "p": periodo_id, "n": nuevo_id},
    )
    registrar_evento(
        session,
        tenant_id,
        "CustodiaCorregida",
        {
            "custodia_id": str(viejo["custodia_id"]),
            "periodo_corregido_id": periodo_id,
            "periodo_id": nuevo_id,
            "custodio_id": nuevo_custodio,
            "desde": nuevo_desde,
            "hasta": nuevo_hasta,
            "estado": nuevo_estado,
            "motivo": motivo,
        },
        identidad.usuario_id,
    )
    return {
        "custodia_id": str(viejo["custodia_id"]),
        "periodo_id": nuevo_id,
        "periodo_corregido_id": periodo_id,
        "eventos": ["CustodiaCorregida"],
    }


# --------------------------------------------------------------------------- excepciones


def _exigir_definicion(session: Session, tenant_id: str, requisito_definicion_id: str) -> None:
    existe = session.execute(
        text("SELECT 1 FROM modulo1.definicion_requisito WHERE tenant_id = :t AND requisito_definicion_id = :r"),
        {"t": tenant_id, "r": requisito_definicion_id},
    ).first()
    if existe is None:
        raise NoEncontrado("Definición de requisito inexistente", {"requisito_definicion_id": requisito_definicion_id})


def _rechazar_excepcion_sobre_empresa(session: Session, tenant_id: str, sujeto_id: str) -> None:
    """Cierre seguro (DECISIONES_DOMINIO §7): una excepción sobre la EMPRESA afecta a toda la
    dotación y ningún rol tiene hoy ese alcance definido → deshabilitado explícitamente,
    antes de cualquier chequeo de alcance, con error estable."""
    tipo = session.execute(
        text("SELECT tipo_sujeto FROM modulo1.legajo WHERE tenant_id = :t AND sujeto_id = :s"),
        {"t": tenant_id, "s": sujeto_id},
    ).scalar()
    if tipo == "empresa":
        raise ErrorDeDominio(
            "Las excepciones sobre requisitos de la empresa están deshabilitadas: afectan a toda la "
            "dotación y no hay un rol definido con ese alcance",
            {"sujeto_id": sujeto_id},
            codigo="excepcion_de_empresa_deshabilitada",
        )


def prevalidar_otorgar_excepcion(session: Session, identidad: Identidad, *, referencia_evaluacion: str, sujeto_id: str, **_) -> None:
    """Alcance ACTUAL del supervisor sobre la decisión citada y el sujeto (2.3 §3). Se
    ejecuta siempre —también antes de un replay idempotente— para que un supervisor que
    perdió el universo no recupere una respuesta almacenada."""
    identidad.exigir_rol(Rol.SUPERVISOR)
    _rechazar_excepcion_sobre_empresa(session, identidad.tenant_id, sujeto_id)
    hoy = hoy_del_tenant(session, identidad.tenant_id)
    if not decision_visible(session, identidad, referencia_evaluacion, hoy):
        raise NoEncontrado("Evaluación inexistente", {"referencia_evaluacion": referencia_evaluacion})
    if not sujeto_en_alcance(session, identidad, sujeto_id, hoy):
        raise Prohibido("El sujeto está fuera del universo del supervisor", {"sujeto_id": sujeto_id})


def otorgar_excepcion(
    session: Session,
    identidad: Identidad,
    *,
    referencia_evaluacion: str,
    sujeto_id: str,
    requisito_definicion_id: str,
    commitment_id: str,
    motivo: str,
    vigencia: date | None = None,
    evidencia: str | None = None,
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.SUPERVISOR)
    tenant_id = identidad.tenant_id
    prevalidar_otorgar_excepcion(session, identidad, referencia_evaluacion=referencia_evaluacion, sujeto_id=sujeto_id)

    evaluacion = session.execute(
        text("SELECT commitment_id FROM modulo1.evaluacion_habilitacion WHERE tenant_id = :t AND referencia_evaluacion = :e"),
        {"t": tenant_id, "e": referencia_evaluacion},
    ).first()
    if evaluacion is None:
        raise NoEncontrado("Evaluación inexistente", {"referencia_evaluacion": referencia_evaluacion})
    if evaluacion[0] != commitment_id:
        raise ErrorDeDominio(
            "La evaluación referida no corresponde a ese compromiso",
            {"referencia_evaluacion": referencia_evaluacion, "commitment_id": commitment_id},
        )
    _exigir_definicion(session, tenant_id, requisito_definicion_id)

    clasificacion = clasificacion_vigente(session, tenant_id, commitment_id, requisito_definicion_id)
    if clasificacion is None:
        raise ErrorDeDominio(
            "El requisito no está exigido por la matriz vigente ni por un requisito particular del compromiso",
            {"requisito_definicion_id": requisito_definicion_id, "commitment_id": commitment_id},
        )
    if clasificacion != Clasificacion.EXCEPCIONABLE:
        raise ErrorDeDominio(
            "No se puede otorgar excepción sobre un requisito bloqueante_duro",
            {"requisito_definicion_id": requisito_definicion_id, "clasificacion": clasificacion.value},
            codigo="requisito_no_excepcionable",
        )
    _bloquear_legajo(session, tenant_id, sujeto_id)
    ya = session.execute(
        text(
            "SELECT excepcion_id FROM modulo1.excepcion WHERE tenant_id = :t AND sujeto_id = :s "
            "AND requisito_definicion_id = :r AND commitment_id = :c AND estado = 'otorgada'"
        ),
        {"t": tenant_id, "s": sujeto_id, "r": requisito_definicion_id, "c": commitment_id},
    ).first()
    if ya is not None:
        raise Conflicto("Ya hay una excepción otorgada para ese sujeto, requisito y compromiso", {"excepcion_id": str(ya[0])})

    try:
        excepcion_id = str(
            session.execute(
                text(
                    "INSERT INTO modulo1.excepcion (tenant_id, referencia_evaluacion, sujeto_id, requisito_definicion_id, "
                    " commitment_id, otorgada_por, motivo, vigencia, evidencia) "
                    "VALUES (:t, :e, :s, :r, :c, :u, :m, :v, :ev) RETURNING excepcion_id"
                ),
                {
                    "t": tenant_id, "e": referencia_evaluacion, "s": sujeto_id, "r": requisito_definicion_id,
                    "c": commitment_id, "u": identidad.usuario_id, "m": motivo, "v": vigencia, "ev": evidencia,
                },
            ).scalar()
        )
    except IntegrityError as err:
        if not _es_colision_activa(err, "uq_excepcion_activa"):
            raise
        # Residual: el ancla del legajo ya serializa las creaciones; si aun así la base
        # rechaza, es un conflicto de dominio estable, nunca un 500.
        raise Conflicto(
            "Ya hay una excepción otorgada para ese sujeto, requisito y compromiso",
            {"sujeto_id": sujeto_id, "requisito_definicion_id": requisito_definicion_id, "commitment_id": commitment_id},
            codigo="excepcion_activa_duplicada",
        ) from err
    from app.modules.alertas.servicio import registrar_accion

    registrar_accion(session, tenant_id, sujeto_id, requisito_definicion_id, "excepcion", excepcion_id)
    registrar_evento(
        session,
        tenant_id,
        "ExcepcionOtorgada",
        {
            "excepcion_id": excepcion_id,
            "referencia_evaluacion": referencia_evaluacion,
            "sujeto_id": sujeto_id,
            "requisito_definicion_id": requisito_definicion_id,
            "commitment_id": commitment_id,
            "clasificacion_al_otorgar": clasificacion.value,
            "vigencia": vigencia,
            "motivo": motivo,
        },
        identidad.usuario_id,
    )
    return {"excepcion_id": excepcion_id, "eventos": ["ExcepcionOtorgada"]}


def revocar_excepcion(
    session: Session, identidad: Identidad, *, excepcion_id: str, motivo: str | None = None
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.SUPERVISOR)
    tenant_id = identidad.tenant_id
    fila = session.execute(
        text(
            "SELECT estado, sujeto_id, requisito_definicion_id, commitment_id FROM modulo1.excepcion "
            "WHERE tenant_id = :t AND excepcion_id = :e FOR UPDATE"
        ),
        {"t": tenant_id, "e": excepcion_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Excepción inexistente", {"excepcion_id": excepcion_id})
    if fila["estado"] != "otorgada":
        raise Conflicto("Solo se revoca una excepción otorgada", {"excepcion_id": excepcion_id, "estado": fila["estado"]})
    session.execute(
        text("UPDATE modulo1.excepcion SET estado = 'revocada' WHERE tenant_id = :t AND excepcion_id = :e"),
        {"t": tenant_id, "e": excepcion_id},
    )
    registrar_evento(
        session,
        tenant_id,
        "ExcepcionRevocada",
        {
            "excepcion_id": excepcion_id,
            "sujeto_id": fila["sujeto_id"],
            "requisito_definicion_id": str(fila["requisito_definicion_id"]),
            "commitment_id": fila["commitment_id"],
            "motivo": motivo,
        },
        identidad.usuario_id,
    )
    return {"excepcion_id": excepcion_id, "eventos": ["ExcepcionRevocada"]}


# --------------------------------------------------------------------------- constancias


def _cliente_clasifica_bloqueante_duro(session: Session, tenant_id: str, cliente_id: str, requisito_definicion_id: str) -> bool:
    """Para una constancia general: alguna matriz vigente HOY del cliente clasifica el
    requisito como bloqueante_duro."""
    hoy = hoy_del_tenant(session, tenant_id)
    fila = session.execute(
        text(
            "SELECT 1 FROM modulo1.matriz_requisitos m "
            "JOIN modulo1.linea_requisito l ON l.matriz_version_id = m.matriz_version_id AND l.tenant_id = m.tenant_id "
            "WHERE m.tenant_id = :t AND m.cliente_id = :c AND l.requisito_definicion_id = :r "
            "  AND l.clasificacion = 'bloqueante_duro' "
            "  AND m.vigente_desde <= :hoy AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= :hoy) LIMIT 1"
        ),
        {"t": tenant_id, "c": cliente_id, "r": requisito_definicion_id, "hoy": hoy},
    ).first()
    return fila is not None


def registrar_constancia_del_cliente(
    session: Session,
    identidad: Identidad,
    *,
    sujeto_id: str,
    requisito_definicion_id: str,
    cliente_id: str,
    evidencia: str,
    commitment_id: str | None = None,
    emisor: str | None = None,
    vigencia: date | None = None,
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    tenant_id = identidad.tenant_id
    _exigir_definicion(session, tenant_id, requisito_definicion_id)

    if commitment_id is not None:
        oc = buscar_oc(session, tenant_id, commitment_id)
        if oc is None:
            raise NoEncontrado("Compromiso inexistente", {"commitment_id": commitment_id})
        if str(oc["cliente_id"]) != str(cliente_id):
            raise ErrorDeDominio("El compromiso no pertenece a ese cliente", {"commitment_id": commitment_id, "cliente_id": cliente_id})
        clasificacion = clasificacion_vigente(session, tenant_id, commitment_id, requisito_definicion_id)
        es_bloqueante_duro = clasificacion == Clasificacion.BLOQUEANTE_DURO
    else:
        es_bloqueante_duro = _cliente_clasifica_bloqueante_duro(session, tenant_id, cliente_id, requisito_definicion_id)
    if not es_bloqueante_duro:
        raise ErrorDeDominio(
            "Una constancia del cliente solo cubre requisitos bloqueante_duro",
            {"requisito_definicion_id": requisito_definicion_id, "cliente_id": cliente_id, "commitment_id": commitment_id},
            codigo="requisito_no_bloqueante_duro",
        )

    _bloquear_legajo(session, tenant_id, sujeto_id)
    anterior = session.execute(
        text(
            "SELECT constancia_id FROM modulo1.constancia_cliente "
            "WHERE tenant_id = :t AND sujeto_id = :s AND requisito_definicion_id = :r AND cliente_id = :c "
            "  AND commitment_id IS NOT DISTINCT FROM :cm AND estado = 'vigente' FOR UPDATE"
        ),
        {"t": tenant_id, "s": sujeto_id, "r": requisito_definicion_id, "c": cliente_id, "cm": commitment_id},
    ).first()

    # Orden obligatorio por los índices únicos parciales (0012): la vigente anterior sale
    # de 'vigente' ANTES de insertar la nueva; `reemplazada_por` se apunta después (FK).
    eventos: list[str] = []
    reemplazada_id: str | None = None
    if anterior is not None:
        reemplazada_id = str(anterior[0])
        session.execute(
            text("UPDATE modulo1.constancia_cliente SET estado = 'reemplazada' WHERE tenant_id = :t AND constancia_id = :a"),
            {"t": tenant_id, "a": reemplazada_id},
        )
    try:
        constancia_id = str(
            session.execute(
                text(
                    "INSERT INTO modulo1.constancia_cliente (tenant_id, sujeto_id, requisito_definicion_id, cliente_id, "
                    " commitment_id, registrada_por, emisor, evidencia, vigencia) "
                    "VALUES (:t, :s, :r, :c, :cm, :u, :em, :ev, :v) RETURNING constancia_id"
                ),
                {
                    "t": tenant_id, "s": sujeto_id, "r": requisito_definicion_id, "c": cliente_id, "cm": commitment_id,
                    "u": identidad.usuario_id, "em": emisor, "ev": evidencia, "v": vigencia,
                },
            ).scalar()
        )
    except IntegrityError as err:
        if not _es_colision_activa(err, "uq_constancia_general_activa", "uq_constancia_especifica_activa"):
            raise
        raise Conflicto(
            "Ya hay una constancia vigente para ese sujeto, requisito, cliente y compromiso",
            {"sujeto_id": sujeto_id, "requisito_definicion_id": requisito_definicion_id, "cliente_id": cliente_id,
             "commitment_id": commitment_id},
            codigo="constancia_activa_duplicada",
        ) from err
    if reemplazada_id is not None:
        session.execute(
            text("UPDATE modulo1.constancia_cliente SET reemplazada_por = :n WHERE tenant_id = :t AND constancia_id = :a"),
            {"t": tenant_id, "a": reemplazada_id, "n": constancia_id},
        )
        registrar_evento(
            session,
            tenant_id,
            "ConstanciaReemplazada",
            {"constancia_id": reemplazada_id, "reemplazada_por": constancia_id, "sujeto_id": sujeto_id,
             "requisito_definicion_id": requisito_definicion_id, "cliente_id": cliente_id, "commitment_id": commitment_id},
            identidad.usuario_id,
        )
        eventos.append("ConstanciaReemplazada")
    registrar_evento(
        session,
        tenant_id,
        "ConstanciaRegistrada",
        {"constancia_id": constancia_id, "sujeto_id": sujeto_id, "requisito_definicion_id": requisito_definicion_id,
         "cliente_id": cliente_id, "commitment_id": commitment_id, "emisor": emisor, "vigencia": vigencia},
        identidad.usuario_id,
    )
    eventos.append("ConstanciaRegistrada")
    return {"constancia_id": constancia_id, "constancia_reemplazada_id": reemplazada_id, "eventos": eventos}


def revocar_constancia_del_cliente(
    session: Session, identidad: Identidad, *, constancia_id: str, motivo: str | None = None
) -> dict[str, Any]:
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    tenant_id = identidad.tenant_id
    fila = session.execute(
        text(
            "SELECT estado, sujeto_id, requisito_definicion_id, cliente_id, commitment_id FROM modulo1.constancia_cliente "
            "WHERE tenant_id = :t AND constancia_id = :c FOR UPDATE"
        ),
        {"t": tenant_id, "c": constancia_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Constancia inexistente", {"constancia_id": constancia_id})
    if fila["estado"] != "vigente":
        raise Conflicto("Solo se revoca una constancia vigente", {"constancia_id": constancia_id, "estado": fila["estado"]})
    session.execute(
        text("UPDATE modulo1.constancia_cliente SET estado = 'revocada' WHERE tenant_id = :t AND constancia_id = :c"),
        {"t": tenant_id, "c": constancia_id},
    )
    registrar_evento(
        session,
        tenant_id,
        "ConstanciaRevocada",
        {"constancia_id": constancia_id, "sujeto_id": fila["sujeto_id"],
         "requisito_definicion_id": str(fila["requisito_definicion_id"]), "cliente_id": str(fila["cliente_id"]),
         "commitment_id": fila["commitment_id"], "motivo": motivo},
        identidad.usuario_id,
    )
    return {"constancia_id": constancia_id, "eventos": ["ConstanciaRevocada"]}


# --------------------------------------------------------------------------- evaluación


def evaluar_habilitacion(
    session: Session, identidad: Identidad, *, commitment_id: str, sujetos_propuestos: list[str]
) -> dict[str, Any]:
    """MODO DECISIÓN (regla A-04): solo el responsable de legajos (y, cuando se integre, la
    identidad técnica de Módulo 2). El supervisor tiene únicamente modo consulta —matriz
    2.2 dice "modo consulta" expresamente— vía GET /consultas/cobertura_oc."""
    identidad.exigir_rol(Rol.RESPONSABLE_LEGAJOS)
    resultado = decidir_habilitacion(
        session, identidad.tenant_id, commitment_id, sujetos_propuestos, ahora_utc(), identidad.usuario_id
    )
    return {**resultado, "eventos": ["EvaluacionDeHabilitacionRealizada"]}
