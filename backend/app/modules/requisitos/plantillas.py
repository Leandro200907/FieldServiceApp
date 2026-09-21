"""Plantillas globales de industria → copias locales opt-in (no-funcionales 1.5.1–1.5.3).

- El motor nunca lee `plataforma.*`: las Líneas de requisito, Documentos, etc. citan SIEMPRE
  la copia local (`modulo1.definicion_requisito`, `modulo1.matriz_requisitos`).
- `copiar_definicion_global`: crea la definición local con `definicion_global_id` y
  `copiada_de_version`; para inducción el tenant elige `locacion_id` en ese momento.
- `copiar_matriz_global`: para cada línea global reutiliza la copia local existente de esa
  definición (o la crea) y publica una versión de Matriz del tenant con
  `matriz_global_id`/`copiada_de_version` — pasa por el mismo `publicar_version_de_matriz`
  (caso de oro 6.3 incluido). Nunca sobreescribe: es una versión nueva.
- `plantillas_globales` (consulta): cada plantilla global junto a su copia local vigente
  y el estado `sin_copia` · `al_dia` · `actualizacion_disponible`, con las líneas de ambas
  para decidir a mano qué traer (v1 no hace merge).
- `control_plantillas` (reloj): por tenant, cada copia atrasada genera UNA vez por versión
  el evento `PlantillaGlobalActualizada` y una notificación al responsable de legajos.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.errores import Conflicto, ErrorDeDominio, NoEncontrado
from app.auth.identidad import Identidad, Rol
from app.comun.eventos import registrar_evento, registrar_evento_interno
from app.modules.requisitos import esquemas as e
from app.modules.requisitos.servicio import publicar_version_de_matriz

# --------------------------------------------------------------------------- lectura del catálogo global


def _definicion_global(s: Session, definicion_global_id: str) -> dict[str, Any]:
    fila = s.execute(
        text("SELECT definicion_global_id, nombre, categoria, tipo_sujeto_aplicable, version, activa, descripcion "
             "FROM plataforma.definicion_requisito_global WHERE definicion_global_id = :g"),
        {"g": definicion_global_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Definición global inexistente", {"definicion_global_id": definicion_global_id})
    return dict(fila)


def _matriz_global(s: Session, matriz_global_id: str) -> dict[str, Any]:
    fila = s.execute(
        text("SELECT matriz_global_id, operadora, tipo_servicio, descripcion, version, activa, fuente "
             "FROM plataforma.matriz_global WHERE matriz_global_id = :m"),
        {"m": matriz_global_id},
    ).mappings().first()
    if fila is None:
        raise NoEncontrado("Matriz global inexistente", {"matriz_global_id": matriz_global_id})
    return dict(fila)


def _lineas_globales(s: Session, matriz_global_id: str) -> list[dict[str, Any]]:
    return [dict(f) for f in s.execute(
        text("SELECT l.definicion_global_id, d.nombre, d.categoria, d.tipo_sujeto_aplicable, d.version AS version_definicion, "
             "l.clasificacion, l.bloqueante_durante_ejecucion "
             "FROM plataforma.linea_matriz_global l JOIN plataforma.definicion_requisito_global d USING (definicion_global_id) "
             "WHERE l.matriz_global_id = :m ORDER BY d.tipo_sujeto_aplicable, d.nombre"),
        {"m": matriz_global_id},
    ).mappings()]


def _copia_local_de_definicion(s: Session, tenant_id: str, definicion_global_id: str, locacion_id: str | None) -> dict[str, Any] | None:
    fila = s.execute(
        text("SELECT requisito_definicion_id, nombre, copiada_de_version, activa, locacion_id FROM modulo1.definicion_requisito "
             "WHERE tenant_id = :t AND definicion_global_id = :g AND locacion_id IS NOT DISTINCT FROM CAST(:l AS uuid) "
             "ORDER BY activa DESC, creado_en DESC LIMIT 1"),
        {"t": tenant_id, "g": definicion_global_id, "l": locacion_id},
    ).mappings().first()
    return dict(fila) if fila else None


# --------------------------------------------------------------------------- comandos (rol configuracion)


def _insertar_copia_definicion(s: Session, identidad: Identidad, g: dict[str, Any], locacion_id: str | None) -> str:
    t = identidad.tenant_id
    if g["categoria"] == "induccion" and locacion_id is None:
        raise ErrorDeDominio("Una inducción exige locacion_id al copiarla (la locación es propia del tenant)",
                             {"definicion_global_id": str(g["definicion_global_id"])}, codigo="locacion_requerida")
    if g["categoria"] != "induccion" and locacion_id is not None:
        raise ErrorDeDominio("Solo las inducciones llevan locacion_id", {"definicion_global_id": str(g["definicion_global_id"])})
    if not g["activa"]:
        raise ErrorDeDominio("La definición global está dada de baja", {"definicion_global_id": str(g["definicion_global_id"])})
    existente = s.execute(
        text("SELECT requisito_definicion_id, activa FROM modulo1.definicion_requisito WHERE tenant_id = :t AND nombre = :n "
             "AND categoria = :c AND tipo_sujeto_aplicable = :ts AND locacion_id IS NOT DISTINCT FROM CAST(:l AS uuid)"),
        {"t": t, "n": g["nombre"], "c": g["categoria"], "ts": g["tipo_sujeto_aplicable"], "l": locacion_id},
    ).mappings().first()
    if existente is not None:
        raise Conflicto("Ya existe una definición local con esa clave (copiá una sola vez; para actualizar, revisá la comparación)",
                        {"requisito_definicion_id": str(existente["requisito_definicion_id"]), "activa": existente["activa"]},
                        codigo="definicion_duplicada")
    rid = str(uuid.uuid4())
    s.execute(
        text("INSERT INTO modulo1.definicion_requisito (requisito_definicion_id, tenant_id, nombre, categoria, tipo_sujeto_aplicable, "
             "locacion_id, definicion_global_id, copiada_de_version) VALUES (:r, :t, :n, :c, :ts, :l, :g, :v)"),
        {"r": rid, "t": t, "n": g["nombre"], "c": g["categoria"], "ts": g["tipo_sujeto_aplicable"], "l": locacion_id,
         "g": str(g["definicion_global_id"]), "v": g["version"]},
    )
    registrar_evento(
        s, t, "DefinicionDeRequisitoDadaDeAlta",
        {"requisito_definicion_id": rid, "nombre": g["nombre"], "categoria": g["categoria"], "tipo_sujeto_aplicable": g["tipo_sujeto_aplicable"],
         "locacion_id": locacion_id, "definicion_global_id": str(g["definicion_global_id"]), "copiada_de_version": g["version"]},
        identidad.usuario_id,
    )
    return rid


def copiar_definicion_global(s: Session, identidad: Identidad, body: e.CopiarDefinicionGlobal) -> dict[str, Any]:
    identidad.exigir_rol(Rol.CONFIGURACION)
    g = _definicion_global(s, str(body.definicion_global_id))
    rid = _insertar_copia_definicion(s, identidad, g, str(body.locacion_id) if body.locacion_id else None)
    return {"requisito_definicion_id": rid, "definicion_global_id": str(g["definicion_global_id"]), "copiada_de_version": g["version"],
            "eventos": ["DefinicionDeRequisitoDadaDeAlta"]}


def copiar_matriz_global(s: Session, identidad: Identidad, body: e.CopiarMatrizGlobal) -> dict[str, Any]:
    """Publica una versión local de Matriz a partir de la plantilla: reutiliza copias
    locales existentes de cada definición global (misma locación para inducciones) y crea
    las que falten. La locación de las inducciones es la de la matriz."""
    identidad.exigir_rol(Rol.CONFIGURACION)
    t = identidad.tenant_id
    m = _matriz_global(s, str(body.matriz_global_id))
    if not m["activa"]:
        raise ErrorDeDominio("La matriz global está dada de baja", {"matriz_global_id": str(m["matriz_global_id"])})
    lineas_globales = _lineas_globales(s, str(m["matriz_global_id"]))
    if not lineas_globales:
        raise ErrorDeDominio("La matriz global no tiene líneas", {"matriz_global_id": str(m["matriz_global_id"])})

    definiciones_creadas: list[str] = []
    lineas: list[e.LineaDeMatriz] = []
    eventos: list[str] = []
    for lg in lineas_globales:
        locacion = str(body.locacion_id) if lg["categoria"] == "induccion" else None
        copia = _copia_local_de_definicion(s, t, str(lg["definicion_global_id"]), locacion)
        if copia is None or not copia["activa"]:
            g = _definicion_global(s, str(lg["definicion_global_id"]))
            rid = _insertar_copia_definicion(s, identidad, g, locacion)
            definiciones_creadas.append(rid)
            eventos.append("DefinicionDeRequisitoDadaDeAlta")
        else:
            rid = str(copia["requisito_definicion_id"])
        lineas.append(e.LineaDeMatriz(requisito_definicion_id=rid, clasificacion=lg["clasificacion"],
                                      bloqueante_durante_ejecucion=lg["bloqueante_durante_ejecucion"]))

    publicada = publicar_version_de_matriz(
        s, identidad,
        e.PublicarVersionDeMatriz(
            cliente_id=body.cliente_id, locacion_id=body.locacion_id, tipo_servicio_id=body.tipo_servicio_id,
            vigente_desde=body.vigente_desde, lineas=lineas,
            fuente=f"plantilla global {m['operadora']} / {m['tipo_servicio']} v{m['version']}",
            autor=identidad.usuario_id,
        ),
    )
    s.execute(
        text("UPDATE modulo1.matriz_requisitos SET matriz_global_id = :g, copiada_de_version = :v WHERE tenant_id = :t AND matriz_version_id = :m"),
        {"g": str(m["matriz_global_id"]), "v": m["version"], "t": t, "m": publicada["matriz_version_id"]},
    )
    registrar_evento_interno(
        s, t, "MatrizCopiadaDePlantilla",
        {"matriz_version_id": publicada["matriz_version_id"], "matriz_global_id": str(m["matriz_global_id"]),
         "copiada_de_version": m["version"], "definiciones_creadas": definiciones_creadas, "lineas": len(lineas)},
        identidad.usuario_id,
    )
    return {**publicada, "matriz_global_id": str(m["matriz_global_id"]), "copiada_de_version": m["version"],
            "definiciones_creadas": definiciones_creadas, "eventos": eventos + publicada["eventos"] + ["MatrizCopiadaDePlantilla"]}


# --------------------------------------------------------------------------- consulta


def _estado(copiada_de_version: int | None, version_global: int) -> str:
    if copiada_de_version is None:
        return "sin_copia"
    return "al_dia" if copiada_de_version >= version_global else "actualizacion_disponible"


def plantillas_globales(s: Session, identidad: Identidad) -> dict[str, Any]:
    """Plantilla global junto a la(s) copia(s) local(es): para decidir a mano qué traer."""
    identidad.exigir_rol(Rol.CONFIGURACION, Rol.RESPONSABLE_LEGAJOS)
    t = identidad.tenant_id
    definiciones = []
    for g in s.execute(text(
        "SELECT definicion_global_id, nombre, categoria, tipo_sujeto_aplicable, version, activa, descripcion, actualizado_en "
        "FROM plataforma.definicion_requisito_global WHERE activa ORDER BY tipo_sujeto_aplicable, nombre")).mappings():
        copias = [dict(c) for c in s.execute(text(
            "SELECT requisito_definicion_id, nombre, locacion_id, copiada_de_version, activa FROM modulo1.definicion_requisito "
            "WHERE tenant_id = :t AND definicion_global_id = :g AND activa ORDER BY creado_en"), {"t": t, "g": str(g["definicion_global_id"])}).mappings()]
        definiciones.append({
            **dict(g), "definicion_global_id": str(g["definicion_global_id"]),
            "estado": "sin_copia" if not copias else ("actualizacion_disponible" if any(c["copiada_de_version"] < g["version"] for c in copias) else "al_dia"),
            "copias_locales": [{**c, "requisito_definicion_id": str(c["requisito_definicion_id"]), "locacion_id": str(c["locacion_id"]) if c["locacion_id"] else None,
                                "estado": _estado(c["copiada_de_version"], g["version"])} for c in copias],
        })
    matrices = []
    for m in s.execute(text(
        "SELECT matriz_global_id, operadora, tipo_servicio, descripcion, version, fuente, actualizado_en "
        "FROM plataforma.matriz_global WHERE activa ORDER BY operadora, tipo_servicio")).mappings():
        copias = []
        for c in s.execute(text(
            "SELECT DISTINCT ON (cliente_id, locacion_id, tipo_servicio_id) matriz_version_id, cliente_id, locacion_id, tipo_servicio_id, "
            "version, vigente_desde, vigente_hasta, copiada_de_version FROM modulo1.matriz_requisitos "
            "WHERE tenant_id = :t AND matriz_global_id = :m ORDER BY cliente_id, locacion_id, tipo_servicio_id, version DESC"),
            {"t": t, "m": str(m["matriz_global_id"])}).mappings():
            lineas_locales = [dict(x) for x in s.execute(text(
                "SELECT l.requisito_definicion_id, d.nombre, d.definicion_global_id, l.clasificacion, l.bloqueante_durante_ejecucion "
                "FROM modulo1.linea_requisito l JOIN modulo1.definicion_requisito d ON d.requisito_definicion_id = l.requisito_definicion_id AND d.tenant_id = l.tenant_id "
                "WHERE l.tenant_id = :t AND l.matriz_version_id = :m ORDER BY d.nombre"), {"t": t, "m": str(c["matriz_version_id"])}).mappings()]
            copias.append({**{k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in dict(c).items()},
                           "estado": _estado(c["copiada_de_version"], m["version"]),
                           "lineas": [{**x, "requisito_definicion_id": str(x["requisito_definicion_id"]),
                                       "definicion_global_id": str(x["definicion_global_id"]) if x["definicion_global_id"] else None} for x in lineas_locales]})
        matrices.append({
            **dict(m), "matriz_global_id": str(m["matriz_global_id"]),
            "lineas": [{**lg, "definicion_global_id": str(lg["definicion_global_id"])} for lg in _lineas_globales(s, str(m["matriz_global_id"]))],
            "estado": "sin_copia" if not copias else ("actualizacion_disponible" if any(c["estado"] == "actualizacion_disponible" for c in copias) else "al_dia"),
            "copias_locales": copias,
        })
    return {"definiciones": definiciones, "matrices": matrices}


# --------------------------------------------------------------------------- reloj


def control_plantillas(s: Session, tenant_id: str, ahora: datetime) -> dict[str, int]:
    """Copias locales atrasadas respecto de la versión global → `PlantillaGlobalActualizada`
    (una vez por plantilla y versión nueva) + notificación al responsable de legajos."""
    from app.worker.cola import encolar

    avisos = 0
    atrasadas = s.execute(text(
        "SELECT 'definicion_requisito' AS plantilla_tipo, g.definicion_global_id AS plantilla_global_id, g.version AS version_nueva, "
        "       g.actualizado_en, g.nombre AS nombre, d.requisito_definicion_id::text AS copia_local_id, d.copiada_de_version "
        "FROM modulo1.definicion_requisito d JOIN plataforma.definicion_requisito_global g USING (definicion_global_id) "
        "WHERE d.tenant_id = :t AND d.activa AND d.copiada_de_version < g.version "
        "UNION ALL "
        "SELECT 'matriz', g.matriz_global_id, g.version, g.actualizado_en, g.operadora || ' / ' || g.tipo_servicio, "
        "       m.matriz_version_id::text, m.copiada_de_version "
        "FROM modulo1.matriz_requisitos m JOIN plataforma.matriz_global g USING (matriz_global_id) "
        "WHERE m.tenant_id = :t AND m.copiada_de_version < g.version AND (m.vigente_hasta IS NULL OR m.vigente_hasta >= CURRENT_DATE)"
    ), {"t": tenant_id}).mappings().all()
    for a in atrasadas:
        insertado = s.execute(text(
            "INSERT INTO modulo1.plantilla_aviso (tenant_id, plantilla_tipo, plantilla_global_id, version_nueva, notificado_en) "
            "VALUES (:t, :tipo, :g, :v, :ahora) ON CONFLICT DO NOTHING RETURNING plantilla_global_id"),
            {"t": tenant_id, "tipo": a["plantilla_tipo"], "g": str(a["plantilla_global_id"]), "v": a["version_nueva"], "ahora": ahora}).first()
        if insertado is None:
            continue  # ya avisado para esta versión
        payload = {"plantilla_tipo": a["plantilla_tipo"], "plantilla_global_id": str(a["plantilla_global_id"]),
                   "version_nueva": a["version_nueva"], "actualizado_en": a["actualizado_en"],
                   "copia_local_id": a["copia_local_id"], "copiada_de_version": a["copiada_de_version"], "nombre": a["nombre"]}
        evento_id = registrar_evento_interno(s, tenant_id, "PlantillaGlobalActualizada", payload, None)
        s.execute(text("UPDATE modulo1.plantilla_aviso SET evento_id = :e WHERE tenant_id = :t AND plantilla_tipo = :tipo "
                       "AND plantilla_global_id = :g AND version_nueva = :v"),
                  {"e": evento_id, "t": tenant_id, "tipo": a["plantilla_tipo"], "g": str(a["plantilla_global_id"]), "v": a["version_nueva"]})
        encolar(s, "notificaciones", {"tipo": "PlantillaGlobalActualizada", "destinatario_rol": "responsable_legajos", **payload}, tenant_id=tenant_id)
        avisos += 1
    return {"copias_atrasadas": len(atrasadas), "avisos_nuevos": avisos}
