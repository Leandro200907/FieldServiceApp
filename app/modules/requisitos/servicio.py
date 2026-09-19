"""Comandos del dominio Requisitos: definiciones, versiones de Matriz y requisitos
particulares — 3.x de especificacion.md.

Misma convención que app/modules/legajos/servicio.py: sesión abierta por el router,
SQL explícito, eventos del catálogo en la misma transacción, respuesta con ids +
`eventos`. La regla de versionado de la Matriz NO se reimplementa acá: la decide
`app.core.evaluacion.validar_nueva_version_matriz` (caso de oro 6.3) y este módulo
solo ejecuta la escritura atómica que esa función pide (cerrar la actual + crear la
nueva).
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad
from app.comun.eventos import registrar_evento
from app.core.evaluacion import validar_nueva_version_matriz
from app.modules.requisitos import esquemas as e


def _definicion(s: Session, tenant_id: str, requisito_definicion_id: str) -> dict[str, Any]:
    fila = s.execute(
        text(
            "SELECT requisito_definicion_id, nombre, categoria, tipo_sujeto_aplicable, activa "
            "FROM modulo1.definicion_requisito WHERE tenant_id = :t AND requisito_definicion_id = :r FOR UPDATE"
        ),
        {"t": tenant_id, "r": requisito_definicion_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Definición de requisito inexistente", {"requisito_definicion_id": requisito_definicion_id})
    return dict(fila)


def _definicion_activa(s: Session, tenant_id: str, requisito_definicion_id: str) -> dict[str, Any]:
    d = _definicion(s, tenant_id, requisito_definicion_id)
    if not d["activa"]:
        raise ErrorDeDominio("La definición de requisito está dada de baja", {"requisito_definicion_id": requisito_definicion_id})
    return d


# --------------------------------------------------------------------------- definiciones


def dar_de_alta_definicion_de_requisito(
    s: Session, identidad: Identidad, body: e.DarDeAltaDefinicionDeRequisito
) -> dict[str, Any]:
    t = identidad.tenant_id
    # Misma regla que el CHECK induccion_requiere_locacion, validada antes para
    # devolver un error de dominio legible en vez de un 500 por constraint.
    if body.categoria == "induccion" and body.locacion_id is None:
        raise ErrorDeDominio("Una inducción exige locacion_id", {"categoria": body.categoria})
    if body.categoria != "induccion" and body.locacion_id is not None:
        raise ErrorDeDominio("Solo las inducciones llevan locacion_id", {"categoria": body.categoria})

    locacion = str(body.locacion_id) if body.locacion_id else None
    global_id = str(body.definicion_global_id) if body.definicion_global_id else None
    if global_id:
        existe_global = s.execute(
            text("SELECT 1 FROM plataforma.definicion_requisito_global WHERE definicion_global_id = :g"), {"g": global_id}
        ).first()
        if not existe_global:
            raise NoEncontrado("Definición global inexistente", {"definicion_global_id": global_id})

    repetida = s.execute(
        text(
            "SELECT requisito_definicion_id, activa FROM modulo1.definicion_requisito "
            "WHERE tenant_id = :t AND nombre = :n AND categoria = :c AND tipo_sujeto_aplicable = :ts "
            "AND locacion_id IS NOT DISTINCT FROM CAST(:loc AS uuid)"
        ),
        {"t": t, "n": body.nombre, "c": body.categoria, "ts": body.tipo_sujeto_aplicable, "loc": locacion},
    ).mappings().first()
    if repetida:
        raise Conflicto(
            "Ya existe una definición con ese nombre, categoría, tipo de sujeto y locación",
            {"requisito_definicion_id": str(repetida["requisito_definicion_id"]), "activa": repetida["activa"]},
        )

    requisito_definicion_id = str(uuid.uuid4())
    try:
        s.execute(
            text(
                "INSERT INTO modulo1.definicion_requisito (requisito_definicion_id, tenant_id, nombre, categoria, "
                "tipo_sujeto_aplicable, locacion_id, definicion_global_id, plazo_retencion_archivo) "
                "VALUES (:r, :t, :n, :c, :ts, :loc, :g, "
                "CASE WHEN CAST(:dias AS int) IS NULL THEN NULL ELSE make_interval(days => CAST(:dias AS int)) END)"
            ),
            {"r": requisito_definicion_id, "t": t, "n": body.nombre, "c": body.categoria, "ts": body.tipo_sujeto_aplicable,
             "loc": locacion, "g": global_id, "dias": body.plazo_retencion_archivo_dias},
        )
    except IntegrityError as err:
        # Dos altas concurrentes de la misma clave (M-04, 0013 NULLS NOT DISTINCT): la que
        # pierde la carrera recibe el mismo 409 de dominio que una repetida secuencial.
        if getattr(getattr(err.orig, "diag", None), "constraint_name", None) != "uq_definicion_clave_negocio":
            raise
        raise Conflicto(
            "Ya existe una definición con ese nombre, categoría, tipo de sujeto y locación",
            {"nombre": body.nombre, "categoria": body.categoria, "tipo_sujeto_aplicable": body.tipo_sujeto_aplicable,
             "locacion_id": locacion},
            codigo="definicion_duplicada",
        ) from err
    registrar_evento(
        s, t, "DefinicionDeRequisitoDadaDeAlta",
        {"requisito_definicion_id": requisito_definicion_id, "nombre": body.nombre, "categoria": body.categoria,
         "tipo_sujeto_aplicable": body.tipo_sujeto_aplicable, "locacion_id": locacion, "definicion_global_id": global_id},
        identidad.usuario_id,
    )
    return {"requisito_definicion_id": requisito_definicion_id, "eventos": ["DefinicionDeRequisitoDadaDeAlta"]}


def dar_de_baja_definicion_de_requisito(
    s: Session, identidad: Identidad, body: e.DarDeBajaDefinicionDeRequisito
) -> dict[str, Any]:
    t = identidad.tenant_id
    rid = str(body.requisito_definicion_id)
    d = _definicion(s, t, rid)
    if not d["activa"]:
        raise Conflicto("La definición ya está dada de baja", {"requisito_definicion_id": rid})
    s.execute(
        text("UPDATE modulo1.definicion_requisito SET activa = false WHERE tenant_id = :t AND requisito_definicion_id = :r"),
        {"t": t, "r": rid},
    )
    registrar_evento(s, t, "DefinicionDeRequisitoDadaDeBaja", {"requisito_definicion_id": rid, "nombre": d["nombre"]}, identidad.usuario_id)
    return {"requisito_definicion_id": rid, "eventos": ["DefinicionDeRequisitoDadaDeBaja"]}


# --------------------------------------------------------------------------- matriz


def publicar_version_de_matriz(s: Session, identidad: Identidad, body: e.PublicarVersionDeMatriz) -> dict[str, Any]:
    """Caso de oro 6.3 vía comando: la versión actual es la de mayor `version` para la
    clave (cliente, locación, tipo de servicio). Si existe, el motor decide; al aceptar,
    se cierra la actual a `vigente_desde - 1` y se inserta la nueva con `version + 1` y
    sus líneas, todo en la misma transacción."""
    t = identidad.tenant_id
    cliente, locacion, tipo_servicio = str(body.cliente_id), str(body.locacion_id), str(body.tipo_servicio_id)

    for linea in body.lineas:
        _definicion_activa(s, t, str(linea.requisito_definicion_id))

    actual = s.execute(
        text(
            "SELECT matriz_version_id, version, vigente_desde, vigente_hasta FROM modulo1.matriz_requisitos "
            "WHERE tenant_id = :t AND cliente_id = :c AND locacion_id = :l AND tipo_servicio_id = :ts "
            "ORDER BY version DESC LIMIT 1 FOR UPDATE"
        ),
        {"t": t, "c": cliente, "l": locacion, "ts": tipo_servicio},
    ).mappings().first()

    version = 1
    version_anterior: dict[str, Any] | None = None
    if actual is not None:
        aceptada, nuevo_hasta = validar_nueva_version_matriz(actual["vigente_desde"], body.vigente_desde)
        if not aceptada:
            raise Conflicto(
                "La nueva versión no puede empezar antes (ni el mismo día) que la versión vigente",
                {"version_actual": actual["version"], "vigente_desde_actual": str(actual["vigente_desde"]), "vigente_desde_nueva": str(body.vigente_desde)},
            )
        s.execute(
            text("UPDATE modulo1.matriz_requisitos SET vigente_hasta = :h WHERE tenant_id = :t AND matriz_version_id = :m"),
            {"t": t, "m": str(actual["matriz_version_id"]), "h": nuevo_hasta},
        )
        version = actual["version"] + 1
        version_anterior = {"matriz_version_id": str(actual["matriz_version_id"]), "version": actual["version"], "vigente_hasta": nuevo_hasta}

    matriz_version_id = str(uuid.uuid4())
    try:
        s.execute(
            text(
                "INSERT INTO modulo1.matriz_requisitos (matriz_version_id, tenant_id, cliente_id, locacion_id, tipo_servicio_id, "
                "version, vigente_desde, vigente_hasta, fuente, archivo_de_respaldo, autor) "
                "VALUES (:m, :t, :c, :l, :ts, :v, :desde, NULL, :fuente, :archivo, :autor)"
            ),
            {"m": matriz_version_id, "t": t, "c": cliente, "l": locacion, "ts": tipo_servicio, "v": version,
             "desde": body.vigente_desde, "fuente": body.fuente, "archivo": body.archivo_de_respaldo,
             "autor": body.autor or identidad.usuario_id},
        )
    except IntegrityError as err:  # dos publicaciones concurrentes de la primera versión
        raise Conflicto("Otra versión de la matriz se publicó al mismo tiempo; reintentar", {"version": version}) from err

    for linea in body.lineas:
        s.execute(
            text(
                "INSERT INTO modulo1.linea_requisito (matriz_version_id, requisito_definicion_id, tenant_id, clasificacion, "
                "bloqueante_durante_ejecucion) VALUES (:m, :r, :t, :cl, :bl)"
            ),
            {"m": matriz_version_id, "r": str(linea.requisito_definicion_id), "t": t, "cl": linea.clasificacion,
             "bl": linea.bloqueante_durante_ejecucion},
        )

    registrar_evento(
        s, t, "MatrizVersionPublicada",
        {"matriz_version_id": matriz_version_id, "cliente_id": cliente, "locacion_id": locacion, "tipo_servicio_id": tipo_servicio,
         "version": version, "vigente_desde": body.vigente_desde, "lineas": len(body.lineas), "version_anterior": version_anterior,
         "version_anterior_id": version_anterior["matriz_version_id"] if version_anterior else None},
        identidad.usuario_id,
    )
    return {
        "matriz_version_id": matriz_version_id, "version": version, "vigente_desde": body.vigente_desde,
        "version_anterior": version_anterior, "eventos": ["MatrizVersionPublicada"],
    }


# --------------------------------------------------------------------------- requisito particular


def cargar_requisito_particular(s: Session, identidad: Identidad, body: e.CargarRequisitoParticular) -> dict[str, Any]:
    t = identidad.tenant_id
    rid = str(body.requisito_definicion_id)
    _definicion_activa(s, t, rid)
    repetido = s.execute(
        text(
            "SELECT requisito_particular_id FROM modulo1.requisito_particular "
            "WHERE tenant_id = :t AND commitment_id = :c AND requisito_definicion_id = :r"
        ),
        {"t": t, "c": body.commitment_id, "r": rid},
    ).first()
    if repetido:
        raise Conflicto(
            "Ese compromiso ya tiene un requisito particular para esa definición",
            {"requisito_particular_id": str(repetido[0]), "commitment_id": body.commitment_id},
        )
    requisito_particular_id = str(uuid.uuid4())
    s.execute(
        text(
            "INSERT INTO modulo1.requisito_particular (requisito_particular_id, tenant_id, commitment_id, requisito_definicion_id, "
            "clasificacion, bloqueante_durante_ejecucion) VALUES (:p, :t, :c, :r, :cl, :bl)"
        ),
        {"p": requisito_particular_id, "t": t, "c": body.commitment_id, "r": rid, "cl": body.clasificacion,
         "bl": body.bloqueante_durante_ejecucion},
    )
    registrar_evento(
        s, t, "RequisitoParticularCargado",
        {"requisito_particular_id": requisito_particular_id, "commitment_id": body.commitment_id, "requisito_definicion_id": rid,
         "clasificacion": body.clasificacion, "bloqueante_durante_ejecucion": body.bloqueante_durante_ejecucion},
        identidad.usuario_id,
    )
    return {"requisito_particular_id": requisito_particular_id, "eventos": ["RequisitoParticularCargado"]}
