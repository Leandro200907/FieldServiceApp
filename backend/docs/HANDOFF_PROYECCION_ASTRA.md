# Handoff — Proyección documental para Astra

Documento puntual para integrar `calendario_vigencias`, `proyeccion_documental` y
`proyeccion_documental_backlog`. Complementa a `docs/HANDOFF_FRONTEND.md` (§4.5bis) y a
`docs/PROYECCION_DOCUMENTAL.md` (diseño completo, estados, precedencia, puntos de
quiebre). Rama: `backend/calendario-proyeccion-documental`.

**No está declarado integrado.** Esto es el contrato tal como quedó implementado y
probado; la decisión de conectarlo a pantallas es de Astra, después de comparar este
contrato, regenerar tipos y verificar.

## 1. Las 3 rutas y roles

| Ruta | Método | Roles habilitados |
|---|---|---|
| `/v1/consultas/calendario_vigencias` | GET | `responsable_legajos`, `supervisor` (su universo), `técnico` (su propio legajo + custodia) |
| `/v1/consultas/proyeccion_documental` | GET | `responsable_legajos`, `supervisor` (alcance vía última decisión visible o candidatos del universo) |
| `/v1/consultas/proyeccion_documental_backlog` | GET | `responsable_legajos`, `supervisor` (una OC entra sólo si al menos un candidato de su conjunto está en su universo) |

`configuracion` **no tiene acceso a ninguna de las tres** (403) — mismo criterio que
`backlog_oc`/`cobertura_oc`/`tablero_vencimientos`, que tampoco se lo dan. `técnico` sólo
tiene `calendario_vigencias`; las otras dos exigen `responsable_legajos` o `supervisor`.

Las tres exigen `Authorization: Bearer <access_token>` (`security: [{"bearerAuth": []}]`
en el OpenAPI) y devuelven 401/403 con el mismo `ErrorEnvelope` que el resto de la API.

## 2. Campos obligatorios de cada response

**Las tres** llevan siempre:
- `advertencia`: string, texto EXACTO fijo (ver §3) — nunca ausente, nunca vacío.

**`calendario_vigencias`** → `CalendarioVigenciasResponse`:
- `hoy`, `desde`, `hasta`: fecha (`YYYY-MM-DD`).
- `items[]`: cada uno con `categoria`, `id`, `sujeto_id`, `tipo_sujeto`,
  `identificador_natural`, `requisito_definicion_id`, `requisito`, `vigente_desde`,
  `vigente_hasta`, `estado_confirmacion`, `archivo_validacion` (string o `null`),
  `dias_para_vencer` (int, negativo si ya venció).
- `total`, `offset`, `limit`: paginación estándar.

**`proyeccion_documental`** → `ProyeccionDocumentalResponse`:
- `commitment_id`, `hoy`, `oc` (objeto), `desde`, `hasta`.
- `sujetos`: `{origen, referencia_evaluacion, evaluada_en, sujeto_ids}` — `origen` es
  **siempre** uno de `"ultima_decision_visible"` / `"candidatos_del_alcance"`, nunca otro
  valor ni ausente.
- `matriz`: objeto o `null` (null sólo si `estado = sin_matriz`).
- `estado`: uno de los 6 valores cerrados (ver §2.1).
- `intervalos[]`: cada uno con `desde`, `hasta`, `estado` (subconjunto de 3 valores — ver
  §2.1), `capacidad_documental_potencial` (dict), `causas` (opcional, ausente sólo si el
  intervalo es `sin_riesgos_detectados`).
- `causas`: sólo presente en las respuestas `sin_matriz`/`pendiente_de_planificacion` (sin
  intervalos que explicar); en el resto va ausente, la explicación vive en
  `intervalos[].causas`.
- `estado_por_dia`: sólo con `detalle=diario`.

**`proyeccion_documental_backlog`** → `ProyeccionDocumentalBacklogResponse`:
- `hoy`, `horizonte_dias`.
- `items[]`: cada fila con `commitment_id`, `vigencia_desde`, `vigencia_hasta`, `estado`
  (uno de los 6), `primer_quiebre` (fecha o `null`),
  `capacidad_documental_potencial_hoy` (dict, **nunca `null`** — objeto vacío `{}` si no
  hay nada que calcular), **`origen_calculo`** (mismos dos valores que `sujetos.origen`
  del detalle) y **`motivos_resumidos`** (lista de strings — vacía sólo si
  `estado = sin_riesgos_detectados`).
- `total`, `offset`, `limit`.

### 2.1 Vocabulario cerrado — NO confundir los dos niveles

- **Estado resumen** (`proyeccion_documental.estado`, cada fila del backlog): los 6
  valores — `sin_matriz`, `pendiente_de_planificacion`, `bloqueo_confirmado`,
  `requiere_revision`, `riesgo_documental`, `sin_riesgos_detectados`.
- **Estado de intervalo** (`intervalos[].estado`): sólo 3 — `bloqueo_confirmado`,
  `requiere_revision`, `sin_riesgos_detectados`. `riesgo_documental`,
  `sin_matriz` y `pendiente_de_planificacion` NO existen a nivel de intervalo — son
  conclusiones de resumen (`docs/PROYECCION_DOCUMENTAL.md` §6-7).
- `calendario_vigencias` no usa este vocabulario en absoluto.

### 2.2 `capacidad_documental_potencial(_hoy)` — semántica de `null` vs ausente vs `0`

- Un tipo de sujeto **ausente** en el objeto = la OC no lo exige.
- Un tipo **presente en `0`** = lo exige y hoy ningún candidato lo cubre.
- **Nunca hay un valor `null`** para ningún tipo dentro del objeto.
- Cuando no hay NADA que calcular (sin matriz, sin candidatos), el campo es un objeto
  **vacío `{}`**, nunca `null` el campo entero — así el frontend no necesita un chequeo de
  nulidad aparte del vacío.

### 2.3 Corrección de contrato: `matriz` en `pendiente_de_planificacion`

**Bug encontrado y corregido en esta revisión.** El código anterior devolvía `matriz:
null` en CUALQUIER estado que no fuera el cálculo completo de intervalos — incluyendo
`pendiente_de_planificacion`, donde SÍ hay una matriz vigente resuelta (lo que falta es el
conjunto de sujetos, no la matriz). Corregido: **`matriz` es `null` única y
exclusivamente cuando `estado = sin_matriz`.** Con `pendiente_de_planificacion`, `matriz`
trae `matriz_version_id`, `version` y `tipos_exigidos` reales — así el frontend puede
mostrar qué exige la OC aunque todavía no haya a quién evaluar. Dos tests de regresión
dedicados en `tests/test_proyeccion_documental.py` (uno por cada lado del contrato).

### 2.4 `calendario_vigencias`: alcance confirmado y estados visuales

Confirmación por escrito, en respuesta directa a Q-DOC-01
(`docs/frontend/API_GAPS.md`) y al mock `EvidenceIntervalState` de
`src/features/documentation-planning/contracts.ts`:

- **`calendario_vigencias` es y seguirá siendo un calendario general de vencimientos.**
  No cruza contra matriz ni OC — no puede saber si un requisito es exigible para ningún
  compromiso, y por lo tanto **no puede emitir `sin_evidencia` ni ningún campo de
  "obligatoriedad"/"contexto de matriz/OC"** (desarrollado en
  `docs/PROYECCION_DOCUMENTAL.md` §2.1). Un ítem ausente de este calendario no significa
  "sin evidencia, requisito incumplido" — puede significar simplemente que nada vence en
  el rango pedido, o que el sujeto no tiene ese requisito cargado por ningún motivo. Para
  saber si algo es exigible y falta, la pregunta es de `proyeccion_documental`/`_backlog`,
  nunca de este endpoint.
- **De los 4 estados visuales que planeaba el mock** (`verificada`, `proxima_a_vencer`,
  `vencida`, `declarada`), **3 son presentación del lado del cliente**, con fórmula fija
  y sin ningún umbral a inventar (detalle en `docs/PROYECCION_DOCUMENTAL.md` §3.1):
  - `declarada` ⟺ `estado_confirmacion === "declarado"`
  - `vencida` ⟺ `dias_para_vencer < 0`
  - `verificada` ⟺ `estado_confirmacion !== "declarado"` Y NO `vencida`
  **El cuarto, `proxima_a_vencer`, NO está disponible hoy y el frontend no debe inventar
  un umbral propio para simularlo.** El concepto de "cuántos días antes es próximo" ya
  existe en el dominio (`plazo_aviso_dias`, el mismo que usa el motor de Alertas) y
  cualquier implementación futura de este estado tiene que reusar ESE valor — nunca un
  número hardcodeado ni configurable sólo en el cliente. Mientras tanto: no mostrar
  `proxima_a_vencer` como estado propio, o derivarlo aparte cruzando contra
  `GET /v1/consultas/configuracion_alertas` + `definiciones_requisito` (dato real, no
  inventado) si hace falta antes de que el backend lo entregue directamente.

## 3. Qué NO garantiza la proyección

Texto exacto de `advertencia` en las tres respuestas:

> "Proyección documental calculada con la información registrada a la fecha. No garantiza
> disponibilidad ni asignación operativa."

Explícitamente, la proyección:
- **No sabe si un candidato está libre** esa fecha (otra OC, franco, licencia, vacaciones).
- **No sabe nada de logística**: transporte, alojamiento, vehículo/equipo más allá de la
  custodia documental.
- **No decide ni predice quién va a ser asignado** — eso es Módulo 2, con datos que este
  módulo no tiene.
- `capacidad_documental_potencial` es un **conteo de candidatos documentalmente válidos**,
  nunca una promesa de disponibilidad ("hay 3 personas cuyo legajo alcanzaría", no "hay 3
  personas libres").
- **No persiste, no crea tareas, no emite eventos, no modifica ninguna decisión histórica**
  (`evaluacion_habilitacion`) ni el estado de custodia — verificado con test
  (`test_ningun_endpoint_escribe_nada`, `test_proyeccion_no_modifica_decisiones_historicas`).
- No incluye nada de Módulo 2: sin OT, sin disponibilidad, sin ejecución, sin tiempos
  reales, sin firmas ni certificados.

## 4. Regenerar `docs/openapi.json` y correr los tests de proyección

```bash
# Desde backend/ (raíz del repo Python), con el entorno virtual activado:
.venv/Scripts/python scripts/generar_openapi.py            # escribe docs/openapi.json
.venv/Scripts/python scripts/generar_openapi.py --check    # sale 1 si difiere (CI)

# Sólo los tests de proyección (motor puro + integración HTTP):
.venv/Scripts/python -m pytest tests/test_motor_proyeccion.py tests/test_proyeccion_documental.py -v

# Suite completa (requiere PostgreSQL real, ver README §Arrancar):
.venv/Scripts/python -m pytest -q
```

Resultado de la suite completa en este commit: **568 passed, 0 failed, 0 excluidos**
(corrida limpia, secuencial, sin contención de procesos paralelos).

## 5. Diff de operaciones vs `db400e6` (main) — verificado, no asumido

Comparación directa `docs/openapi.json` de este commit contra el de `main`
(`db400e6`, obtenido de GitHub):

```
paths antes: 84   →   paths ahora: 87
operaciones antes: 85   →   operaciones ahora: 88

ALTAS (3, todas GET, nada más):
  /v1/consultas/calendario_vigencias
  /v1/consultas/proyeccion_documental
  /v1/consultas/proyeccion_documental_backlog

BAJAS: (ninguna)
Rutas existentes con cambio de método: (ninguna)
```

Ningún endpoint existente cambió de forma en este commit. `components.schemas` sólo
ganó los schemas nuevos de estos 3 endpoints — no se tocó ningún schema existente.

## 6. Los 9 escenarios validados con PostgreSQL real

| # | Escenario | Archivo · test | Qué asserta |
|---|---|---|---|
| 1 | OC futuras | `test_proyeccion_documental.py::test_proyeccion_oc_futura_desde_es_vigencia_desde_no_hoy` | `desde` de la respuesta = `oc.vigencia_desde`, nunca `hoy`, cuando la OC arranca después de hoy. |
| | | `test_proyeccion_documental.py::test_backlog_oc_futura_lejana_entra_con_ventana_completa` | Una OC que arranca después de `hoy + horizonte_dias` entra igual al backlog (nunca excluida, nunca `desde > hasta`); ventana propia desde su `vigencia_desde`; **`origen_calculo` y `motivos_resumidos` verificados**. |
| 2 | Límites inclusivos de fechas | `test_proyeccion_documental.py::test_calendario_vigencias_rango_simple_y_borde_inclusive` | Un vencimiento exactamente en `hasta` entra; un día después no. |
| | | `test_motor_proyeccion.py::test_quiebre_exacto_en_vigente_hasta_mas_uno_nunca_en_vigente_hasta` | El quiebre cae en `vigente_hasta + 1`, nunca en `vigente_hasta` — `vigente_hasta` sigue cubierto. |
| 3 | Transferencias de custodia | `test_proyeccion_documental.py::test_calendario_vigencias_respeta_transferencia_de_custodia_futura` | Un vehículo con transferencia de custodia programada a futuro sigue apareciendo del lado del custodio ACTUAL, no del futuro (regresión directa de A-01). |
| 4 | Falta de matriz | `test_proyeccion_documental.py::test_proyeccion_sin_matriz_nunca_da_422` | `estado = sin_matriz`, nunca 422; `matriz = null`; `causas[0].motivo` presente con `tipo_sujeto = null`. **Backlog: `origen_calculo` y `motivos_resumidos` (texto exacto) verificados.** |
| 5 | Candidatos vacíos | `test_proyeccion_documental.py::test_proyeccion_pendiente_de_planificacion_sin_candidatos` | `estado = pendiente_de_planificacion` con matriz pero sin candidatos. **Backlog: `capacidad_documental_potencial_hoy = {}` y `motivos_resumidos` (texto exacto) verificados.** |
| | | `test_proyeccion_documental.py::test_proyeccion_pendiente_de_planificacion_con_matriz_informa_matriz_no_null` | **Corrección de contrato §2.3**: `matriz` NO es `null` en `pendiente_de_planificacion` cuando hay matriz vigente — `matriz_version_id`/`version`/`tipos_exigidos` reales verificados. |
| | | `test_proyeccion_documental.py::test_proyeccion_sin_matriz_es_el_unico_caso_con_matriz_null` | Contraparte: `matriz` sí es `null`, pero únicamente cuando `estado = sin_matriz`. |
| 6 | Evidencia declarada | `test_proyeccion_documental.py::test_proyeccion_requiere_revision_documento_declarado` | Documento `declarado` (sin confirmar) → `estado = requiere_revision`, `capacidad_documental_potencial = 0` (nunca cuenta como cobertura real). **Backlog: `origen_calculo` y `motivos_resumidos` verificados.** |
| 7 | Pérdida de cobertura, con y sin respaldo | `test_proyeccion_documental.py::test_proyeccion_bloqueo_confirmado_desde_el_primer_dia` | Sin ningún candidato con documento → `bloqueo_confirmado` desde el primer intervalo. **Backlog: `origen_calculo`/`motivos_resumidos` verificados.** |
| | | `test_proyeccion_documental.py::test_proyeccion_riesgo_documental_hoy_verde_futuro_sin_respaldo` | Hoy cubierto, un candidato vence pronto sin respaldo → `riesgo_documental`. **Backlog: `origen_calculo`/`motivos_resumidos` verificados.** |
| | | `test_proyeccion_documental.py::test_proyeccion_mutua_exclusion_un_solo_candidato_de_respaldo_no_es_riesgo` | Con respaldo (queda 1 candidato válido): el intervalo intermedio sigue `sin_riesgos_detectados`, NUNCA se etiqueta como riesgo — regresión directa del bug del ejemplo anterior de A-02. |
| 8 | Permisos y aislamiento | `test_calendario_vigencias_alcance_supervisor_vs_responsable`, `test_calendario_vigencias_tecnico_solo_ve_su_propio_legajo`, `test_proyeccion_supervisor_sin_candidatos_en_su_universo_cae_a_pendiente`, `test_backlog_alcance_supervisor_una_oc_sin_candidatos_en_su_universo_no_aparece`, `test_aislamiento_entre_tenants` | Supervisor limitado a su universo; técnico sólo su propio legajo; una OC sin candidatos en el universo del supervisor no aparece ni se sustituye por "sin datos"; un `commitment_id`/dato de otro tenant es 404/vacío (RLS), nunca visible. |
| 9 | Resumen backlog = detalle, misma ventana | `test_proyeccion_documental.py::test_backlog_mismo_estado_que_el_detalle_para_la_misma_ventana` | El `estado` de una fila del backlog coincide exactamente con el que devuelve `proyeccion_documental` para la misma OC y ventana; `hoy`, `origen_calculo` y `motivos_resumidos` verificados en ambos lados. |

Los 5 tests marcados en negrita con verificación de `origen_calculo`/`motivos_resumidos`
se reforzaron explícitamente para este documento — antes cubrían el `estado` pero no esos
dos campos en ese escenario puntual.

## 7. Qué NO cambia en este documento

- No se renombra ningún campo del contrato existente.
- No se agregan endpoints nuevos a los ya implementados.
- No se toca nada de Módulo 2.
