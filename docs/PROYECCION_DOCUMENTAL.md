# Proyección documental — diseño (sin implementar)

Documento de diseño para tres consultas nuevas bajo `GET /v1/consultas/…`. **Nada de esto
está implementado todavía**: es la base para decidir alcance antes de tocar código,
siguiendo el mismo patrón que ya cerró H-01..H-06 y la reauditoría (triage → aprobación →
commit). No hay endpoints, no hay migración, no se regeneró `docs/openapi.json`.

1. `GET /v1/consultas/calendario_vigencias`
2. `GET /v1/consultas/proyeccion_documental_backlog`
3. `GET /v1/consultas/proyeccion_documental?commitment_id=…`

Nace de la idea del "Gantt de cobertura documental" discutida antes del congelamiento de
la reauditoría (día a día, verde→rojo por OC, gris = sin matriz) y de la vista compuesta
del supervisor (anexo de `modulo1-documentacion-habilitante.md`). Es una CONSULTA — modo
`consulta` en el sentido ya cerrado de 2.1 de `modelo-dominio.md`: nunca persiste, nunca
crea tareas, nunca emite eventos. Reutiliza el motor puro (`app/core/evaluacion.py`) y la
orquestación existente (`app/core/orquestacion.py`) tal cual están; no les agrega reglas de
negocio nuevas, sólo las recorre en más de una fecha y las resume.

## 0. Responsabilidades y límites respecto de Módulo 2

Esto es documentación, no logística. La proyección contesta **"¿qué candidatos
documentalmente aptos existen hoy, y hasta cuándo van a seguir siéndolo, para cubrir esta
OC?"** — nunca **"¿quién va a ir?"**.

Lo que este módulo NO sabe y no debe fingir que sabe:
- si un candidato está efectivamente libre esa fecha (otra OC, franco, licencia, vacaciones);
- logística: transporte, alojamiento, disponibilidad de vehículo/equipo más allá de la
  custodia documental;
- si alguien va a ser realmente asignado — eso lo decide Módulo 2, con datos que este
  módulo no tiene (¹).

Por eso **`capacidad_documental_potencial` es un conteo de candidatos documentalmente
válidos, nunca una promesa de disponibilidad** (retomado en el punto 6). Cualquier
respuesta de estos tres endpoints lleva la advertencia obligatoria (punto 10). Esta
proyección es exactamente la pieza que, cruzada con el backlog de OC de Módulo 2, permite
la frase *"de tus 40 OC abiertas hay 6 que hoy no podés cubrir con nadie habilitado"* — pero
la frase la arma Módulo 2 cruzando los dos lados del negocio; acá sólo vive el lado
documental.

(¹) Ver `modulo1-documentacion-habilitante.md`, Anexo "Competencia directa: Tracxa":
*"Para Tracxa el documento habilitante es el fin del producto. Acá es una precondición del
flujo de dinero... la diferenciación de fondo... es otra: ser el único que cruza el legajo
contra el trabajo comprometido"* — ese cruce es Módulo 2, no esto.

## 1. Qué reutiliza y qué es nuevo

Reutiliza tal cual, sin reabrir ninguna regla cerrada:
- `matriz_vigente(session, tenant_id, cliente_id, locacion_id, tipo_servicio_id, hoy)` —
  resolución de matriz por clave.
- **Regla temporal cerrada (4.1 de `especificacion.md`, ya en `clasificacion_vigente`):**
  la matriz que rige una OC es la vigente al **día de ingreso** (`oc.vigencia_desde`), no
  la del día en que se corre el cálculo. La proyección hereda esto sin excepción: para una
  OC dada, el conjunto de tipos/requisitos exigidos es el MISMO en todos los días
  proyectados — lo que cambia día a día es sólo si hay candidatos que los cubran, nunca
  cuáles son los requisitos.
- `lineas_efectivas` (matriz + requisito particular del commitment).
- `evaluar_documento_en_periodo` (motor puro, `app/core/evaluacion.py`) — incluye ya el
  gate de `archivo_requiere_revision` (Fase 2 punto 2): un documento con archivo pendiente
  o inválido devuelve `REQUIERE_REVISION` sin que la proyección tenga que saber nada de
  storage.
- `alcance_de_sujetos` / `sujeto_en_alcance` — universo del supervisor, alcance total de
  responsable_legajos (única fuente de verdad, `app/auth/alcance.py`).
- `filtro_decisiones_visibles` / `decision_visible` (A-04) — para "última evaluación
  visible" (punto 4).

Nuevo (sólo en este documento, todavía no escrito):
- un recorrido del motor puro sobre **un rango de fechas** en vez de una sola, con
  **puntos de quiebre** (punto 8) para no evaluar los 366 días uno por uno;
- un **resumen** por OC con 6 estados cerrados y su precedencia (puntos 6 y 9);
- una lectura de "calendario general" (`calendario_vigencias`) que es deliberadamente MÁS
  simple que la proyección: vencimientos de evidencia en un rango, sin cruzar contra
  ninguna matriz (punto 5).

## 2. Diferencia entre calendario general y requisitos exigidos por una matriz

Son dos preguntas distintas y los tres endpoints no las mezclan:

- **`calendario_vigencias`**: *"¿qué evidencia vence entre estas dos fechas?"* — barre
  `documento`/`acreditacion_competencia`/`induccion` vigentes por `vigente_hasta` dentro
  del rango, con alcance por rol, **sin mirar ninguna matriz ni ninguna OC**. Es el mismo
  universo que ya usa `tablero_vencimientos` (`app/modules/consultas/servicio.py:147`),
  con rango de fechas explícito en vez de sólo "próximos N días" — pensado para pintar un
  calendario, no para decidir si una OC se puede cubrir.
- **`proyeccion_documental` / `proyeccion_documental_backlog`**: *"¿esos vencimientos le
  importan a ESTA OC?"* — sólo entran los tipos/requisitos que la matriz vigente de la OC
  (o el requisito particular) efectivamente exige, y sólo importa si, para cada tipo
  exigido, existe al menos un candidato que los cubra ese día — igual que
  `_evaluar()`/`cobertura_de_oc` ya lo hacen para un único día.

Un vencimiento que aparece en `calendario_vigencias` puede no aparecer en ninguna
proyección (nadie usa ese requisito en ninguna matriz activa, o el sujeto no es candidato
de ninguna OC vigente) — y viceversa, un candidato puede estar "verde" en el calendario
general (nada vence pronto) y aun así la OC estar `bloqueo_confirmado` porque el tipo
exigido específico no tiene NINGÚN candidato, venza o no.

## 3. `GET /v1/consultas/calendario_vigencias`

**Rol**: `responsable_legajos` (todo el tenant), `supervisor` (su universo, vía
`alcance_de_sujetos`) — misma matriz 2.2 que `tablero_vencimientos`.

**Parámetros**

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `desde` | fecha | `hoy` del tenant | no puede ser anterior a `hoy - 366` (para no convertir esto en un archivo histórico completo; ver punto 8) |
| `hasta` | fecha | `desde + 30` | `hasta - desde <= 366` días (punto 8) |
| `tipo_sujeto` | `persona\|vehiculo\|equipo\|empresa` | todos | filtro |
| `categoria` | `documento\|competencia\|induccion` | todas | filtro |
| `estado` | `vigente\|vencido\|todos` | `todos` dentro del rango | un vencido con `vigente_hasta` dentro del rango sigue apareciendo |
| `q` | texto | — | ILIKE sobre `sujeto_id` (igual que otras consultas) |
| paginación | `offset`/`limit` | `0`/`50`, máx. `500` | igual convención que el resto (`app/comun/paginacion.py`) |

**Respuesta**

```json
{
  "hoy": "2026-09-21",
  "desde": "2026-09-21",
  "hasta": "2026-10-21",
  "items": [
    {
      "sujeto_id": "persona_0042",
      "tipo_sujeto": "persona",
      "requisito_definicion_id": "…",
      "requisito": "Apto médico",
      "categoria": "documento",
      "vigente_hasta": "2026-09-30",
      "dias_para_vencer": 9,
      "estado_confirmacion": "verificado",
      "archivo_validacion": "valido"
    }
  ],
  "total": 1,
  "offset": 0,
  "limit": 50,
  "advertencia": "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
}
```

`archivo_validacion` viaja igual que en `bandeja_validacion_evidencia` (Fase 2 punto 2):
`pendiente`/`valido`/`invalido`/`null` si el requisito no tiene archivo. No agrega
`estado` resumen (ese vocabulario es sólo de los otros dos endpoints, punto 6) — acá cada
fila es un hecho suelto, no una conclusión sobre una OC.

## 4. Última evaluación visible como conjunto de sujetos

Ni `proyeccion_documental` ni `proyeccion_documental_backlog` inventan a quién evaluar.
Para cada OC, el conjunto de sujetos a proyectar sale de, en este orden:

1. **La última decisión persistida y VISIBLE** para quien consulta (misma regla A-04 que
   ya usa `backlog_oc`: `filtro_decisiones_visibles` — si algún sujeto propuesto de esa
   decisión queda fuera del alcance de un supervisor, la decisión entera "no existe" para
   él, y se cae al punto 2). Los sujetos de `evaluacion_sujeto_propuesto` de esa
   `referencia_evaluacion` son el conjunto — **se lee, nunca se recalcula ni se
   sobreescribe la decisión histórica**: `evaluacion_habilitacion.snapshot`,
   `veredicto_de_cumplimiento` y `resultado_de_decision` de esa fila quedan intactos para
   siempre (mismo principio ya cerrado para matrices: "una auditoría pregunta por la
   fecha de la OC, no por hoy").
2. **Si no hay ninguna decisión visible** (nunca se evaluó esa OC, o la única que hay
   queda fuera de alcance): el universo por defecto es el `candidatos` de
   `cobertura_de_oc` en modo consulta — todos los legajos activos del tenant para
   responsable_legajos, o el universo del supervisor. Este caso es exactamente
   `pendiente_de_planificacion` si además no hay ningún candidato con NADA cargado (punto
   6) — pero si hay candidatos potenciales (aunque nadie los haya propuesto formalmente
   todavía), la proyección los usa igual: el objetivo es anticipar, no esperar a que
   alguien arme la propuesta primero.

La proyección deja explícito de cuál de los dos vino el conjunto:

```json
"sujetos": {
  "origen": "ultima_decision_visible",
  "referencia_evaluacion": "…",
  "evaluada_en": "2026-09-15T10:00:00Z",
  "sujeto_ids": ["persona_0042", "vehiculo_ABC123"]
}
```
o
```json
"sujetos": {
  "origen": "candidatos_del_alcance",
  "referencia_evaluacion": null,
  "sujeto_ids": ["persona_0042", "persona_0077", "vehiculo_ABC123"]
}
```

## 5. `capacidad_documental_potencial` — información, nunca disponibilidad

Por cada tipo exigido y cada día proyectado:

```json
"capacidad_documental_potencial": {
  "persona": 3,
  "vehiculo": 1
}
```

Es el **conteo de candidatos del conjunto del punto 4** que, ESE día, cubren todos sus
requisitos bloqueantes de ese tipo — sin importar si son 3 personas distintas o la misma
persona con 3 vehículos. Nunca dice "hay 3 personas libres": dice "hay 3 personas cuyo
legajo alcanzaría, documentalmente, si se las asignara". La advertencia obligatoria
(punto 10) es la aclaración explícita de esto en cada respuesta; el nombre del campo ya lo
dice ("potencial"), pero no alcanza solo con el nombre — de ahí que la advertencia sea
obligatoria y no opcional en el contrato.

## 6. Los seis estados cerrados

Vocabulario CERRADO — no se agregan variantes sin reabrir este documento. Aplican al
`estado` resumen de una OC completa (`proyeccion_documental` y cada fila de
`proyeccion_documental_backlog`); `calendario_vigencias` no los usa (punto 3).

| Estado | Cuándo |
|---|---|
| `sin_matriz` | No hay matriz vigente para (cliente, locación, tipo_servicio) de la OC al día de ingreso (`oc.vigencia_desde`) — mismo caso que hoy dispara `sin_matriz_vigente` en `_evaluar()`/`avisar_oc_sin_matriz` (H-02), pero acá NUNCA se propaga como error 422: la proyección lo devuelve como estado, no como falla. |
| `pendiente_de_planificacion` | Hay matriz, pero el conjunto de sujetos del punto 4 está vacío (ninguna decisión visible Y ningún candidato en el alcance) — no hay nada que evaluar todavía. |
| `bloqueo_confirmado` | Con los datos de HOY, existe al menos un día dentro del horizonte evaluado en el que algún tipo exigido no tiene NINGÚN candidato que cubra todos sus requisitos bloqueantes — incluye siempre el día de hoy si hoy está bloqueada. |
| `requiere_revision` | No hay `bloqueo_confirmado`, pero la cobertura de al menos un tipo exigido en algún día depende de un documento `REQUIERE_REVISION` (declarado sin confirmar, o archivo pendiente/inválido — Fase 2 punto 2) — el dato existe pero no es confiable, nunca se lo cuenta como cobertura real ni como bloqueo real. |
| `riesgo_documental` | Hoy cubierta (sin bloqueo ni revisión pendiente), pero al menos un tipo exigido pierde TODA cobertura en algún día futuro dentro del horizonte (un vencimiento sin candidato de respaldo detrás) — ver "puntos de quiebre" (punto 8). |
| `sin_riesgos_detectados` | Cubierta todos los días del horizonte evaluado, sin documentos `REQUIERE_REVISION` en juego. |

## 7. Precedencia del estado resumen

Un día puede tener un veredicto y el rango completo otro (peor). Se resuelve exactamente
como `peor()`/`ORDEN_VEREDICTO` ya resuelven el veredicto de un sujeto
(`app/core/orquestacion.py:51-63`) — mismo patrón, extendido a 6 valores, evaluado en este
orden (el primero que aplica gana, sin mezclarlos):

```
sin_matriz > pendiente_de_planificacion > bloqueo_confirmado
           > requiere_revision > riesgo_documental > sin_riesgos_detectados
```

Justificación de cada salto:
- `sin_matriz` y `pendiente_de_planificacion` van primero porque son "no se puede
  evaluar", no "se evaluó y dio mal" — estructuralmente distintos del resto, igual que
  hoy `sin_matriz_vigente` corta el cálculo antes de llegar a ningún veredicto.
- `bloqueo_confirmado` sobre `requiere_revision`: un bloqueo confirmado con datos
  confiables es más grave que una duda sobre datos — si además de la duda hay un día
  claramente bloqueado por otro motivo, ese es el resumen.
- `requiere_revision` sobre `riesgo_documental`: no se puede llamar "en riesgo" (que
  implica que hoy está bien) a algo que hoy mismo no se puede confirmar.

## 8. Puntos de quiebre temporales (cómo se evalúan hasta 366 días sin 366 evaluaciones)

No se corre el motor puro una vez por calendario. El resultado de un día sólo puede
cambiar en una fecha donde cambia alguno de sus insumos, así que se calculan los **puntos
de quiebre** del rango y se evalúa una sola vez por intervalo constante entre dos
quiebres consecutivos:

- `vigente_hasta + 1` de cada documento/acreditación/inducción vigente de cada candidato
  del conjunto (punto 4) que cubra algún requisito exigido — ahí deja de cubrir.
- `vigente_hasta + 1` de cada excepción/constancia con vigencia acotada que esté en juego.
- la fecha de inicio del rango pedido (`desde`) y el día siguiente a su fin (`hasta + 1`,
  como límite, no se evalúa).
- **la matriz NO agrega puntos de quiebre dentro del rango de una OC ya existente** (regla
  del punto 1: fija al día de ingreso) — sólo importa para decidir si HAY matriz en el
  primer lugar (`sin_matriz`).

Con eso, evaluar un año completo son unos pocos intervalos (tantos como vencimientos
reales tengan los candidatos en juego, normalmente muy por debajo de 366), no 366 pasadas
del motor. El resultado por intervalo se expande a `estado_por_dia` sólo si el llamador
pide el detalle diario (`GET proyeccion_documental` con `detalle=diario`, punto 9); el
resumen (punto 6) y `proyeccion_documental_backlog` nunca necesitan expandirlo, resuelven
directamente `peor(estado_de_cada_intervalo)`.

## 9. `GET /v1/consultas/proyeccion_documental?commitment_id=…`

**Rol**: `responsable_legajos`, `supervisor` (alcance vía punto 4; si la última decisión
visible queda fuera de su universo, ver punto 4.2 — nunca expone sujetos ajenos).

**Parámetros**

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `commitment_id` | string | **obligatorio** | igual que `cobertura_oc` |
| `desde` | fecha | `max(hoy, oc.vigencia_desde)` | no permite empezar antes de la vigencia de la OC |
| `hasta` | fecha | `oc.vigencia_hasta` | `hasta - desde <= 366` (422 si se excede) |
| `detalle` | `resumen\|diario` | `resumen` | `diario` agrega `estado_por_dia` expandido (punto 8); `resumen` sólo trae el estado + intervalos + causas |

**Respuesta (`detalle=resumen`)**

```json
{
  "commitment_id": "OC-4587",
  "oc": {"cliente_id": "…", "locacion_id": "…", "tipo_servicio_id": "…",
         "vigencia_desde": "2026-10-01", "vigencia_hasta": "2026-10-05"},
  "desde": "2026-09-21", "hasta": "2026-10-05",
  "matriz": {"matriz_version_id": "…", "version": 3, "tipos_exigidos": ["persona", "vehiculo"]},
  "sujetos": { "...": "ver punto 4" },
  "estado": "riesgo_documental",
  "intervalos": [
    {
      "desde": "2026-09-21", "hasta": "2026-09-29", "estado": "sin_riesgos_detectados",
      "capacidad_documental_potencial": {"persona": 2, "vehiculo": 1}
    },
    {
      "desde": "2026-09-30", "hasta": "2026-10-05", "estado": "riesgo_documental",
      "capacidad_documental_potencial": {"persona": 1, "vehiculo": 1},
      "causas": [
        {
          "tipo_sujeto": "persona",
          "requisito_definicion_id": "…", "requisito": "Apto médico",
          "motivo": "persona_0077 vence el 2026-09-29; queda persona_0042 como único candidato de respaldo",
          "sujetos_que_pierden_cobertura": ["persona_0077"],
          "sujetos_que_mantienen_cobertura": ["persona_0042"]
        }
      ]
    }
  ],
  "advertencia": "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
}
```

Con `detalle=diario`, se agrega `"estado_por_dia": {"2026-09-21": "sin_riesgos_detectados", …}`
expandiendo cada intervalo — pensado para pintar el Gantt día a día tal como se discutió,
sin que el backend tenga que recalcular nada distinto (es el mismo resultado por
intervalo, sólo repetido por fecha).

**Causas explicables**: todo estado que no sea `sin_riesgos_detectados` trae `causas[]`
con, como mínimo, el tipo/requisito afectado y qué sujetos pierden o mantienen cobertura
— nunca un estado "bloqueado" o "en riesgo" sin decir por qué, mismo estándar que ya exige
`VeredictoRequisito.motivo` en el motor puro.

## 10. `GET /v1/consultas/proyeccion_documental_backlog`

**Rol**: `responsable_legajos`, `supervisor` (alcance por OC: una OC entra en el backlog
del supervisor sólo si al menos un candidato de su conjunto — punto 4 — está en su
universo; si no, no aparece, no se sustituye por "sin datos").

**Parámetros**

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `estado_oc` | `activo\|cancelado` | `activo` | mismo filtro que `backlog_oc` |
| `estado` | uno de los 6 (punto 6), repetible | todos | filtra el resumen — p. ej. `?estado=bloqueo_confirmado&estado=riesgo_documental` para la vista "qué me preocupa" |
| `horizonte_dias` | entero | `30` | ventana desde hoy para el cálculo del resumen de cada OC; `<= 366` |
| paginación | `offset`/`limit` | `0`/`50`, máx. `500` | igual convención que `backlog_oc` |

**Respuesta**

```json
{
  "hoy": "2026-09-21",
  "horizonte_dias": 30,
  "items": [
    {
      "commitment_id": "OC-4587",
      "vigencia_desde": "2026-10-01", "vigencia_hasta": "2026-10-05",
      "estado": "riesgo_documental",
      "primer_quiebre": "2026-09-30",
      "capacidad_documental_potencial_hoy": {"persona": 2, "vehiculo": 1}
    }
  ],
  "total": 214,
  "offset": 0,
  "limit": 50,
  "advertencia": "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
}
```

Cada fila es el resumen de `proyeccion_documental` para esa OC sin `causas`/`intervalos`
completos (eso se pide aparte, por OC, con el endpoint puntual — el backlog es para barrer
y priorizar, no para explicar cada caso en detalle). `primer_quiebre` es la fecha del
primer intervalo cuyo estado no es `sin_riesgos_detectados`, o `null` si no hay ninguno.

## 11. Límite de 366 días — dónde se aplica

- `calendario_vigencias`: `hasta - desde <= 366`.
- `proyeccion_documental`: `hasta - desde <= 366` (default ya acotado a la vigencia de la
  OC, que en la práctica siempre es mucho menor; el límite existe para cuando alguien pide
  explícitamente un `hasta` lejano).
- `proyeccion_documental_backlog`: `horizonte_dias <= 366` — el backlog en sí ya pagina
  por OC (offset/limit), el límite temporal es por-OC, no achica la cantidad de OCs.

Excederlo es 422 `rango_temporal_excedido`, mismo estilo que el resto de las validaciones
de rango (`dias debe ser >= 0` de `tablero_vencimientos`).

## 12. Tests previstos (cuando se implemente)

**Motor de quiebres (puro, sin DB, en `app/core/…` si se extrae, o en el módulo de
consultas si queda ahí):**
- un solo intervalo cuando nada vence en el rango;
- un quiebre exacto en `vigente_hasta + 1`, nunca en `vigente_hasta` (mismo borde
  inclusivo ya cerrado en el motor, caso de oro 6.1);
- dos candidatos con vencimientos distintos → tres intervalos, el del medio sigue verde
  porque el otro candidato sostiene la cobertura.

**`calendario_vigencias`:**
- rango simple, alcance de supervisor vs. responsable_legajos;
- `hasta - desde > 366` → 422;
- vencido dentro del rango aparece con `estado=vencido`, control de `desde`/`hasta` con
  borde inclusivo.

**`proyeccion_documental`:**
- `sin_matriz` cuando no hay matriz vigente al día de ingreso — nunca un 422 como hoy
  (verificar explícitamente que NO se propaga `sin_matriz_vigente` como excepción);
- `pendiente_de_planificacion` sin ninguna decisión ni candidatos;
- `bloqueo_confirmado` desde el primer día cuando ya hoy no hay cobertura;
- `requiere_revision` con un documento declarado sin confirmar, y por separado con un
  archivo con `archivo_validacion` pendiente/inválido (Fase 2 punto 2) — confirmar que
  NUNCA se cuenta como cobertura real ni figura en `capacidad_documental_potencial`;
  regresión específica: un `REQUIERE_REVISION` no debe filtrarse a `sin_riesgos_detectados`;
- `riesgo_documental`: hoy verde, un vencimiento futuro sin respaldo → intervalo
  correcto, `causas` con el sujeto que pierde cobertura;
- `sin_riesgos_detectados` de punta a punta;
- **última evaluación visible ≠ recálculo**: correr la proyección no modifica
  `evaluacion_habilitacion` (snapshot, veredicto, resultado) de la decisión que usó como
  base — comparar antes/después;
- supervisor sin ningún candidato en su universo para esa OC → misma semántica de
  ocultamiento que ya usa `decision_visible`/`backlog_oc` (cae a candidatos del alcance,
  que puede quedar vacío → `pendiente_de_planificacion`, nunca expone sujetos ajenos);
- `detalle=diario` expande exactamente los mismos intervalos, sin recalcular nada
  distinto (mismo resultado, sólo repetido por fecha);
- precedencia: un escenario armado a propósito con `requiere_revision` en un tipo y
  `riesgo_documental` en otro → el resumen es `requiere_revision` (gana el peor).

**`proyeccion_documental_backlog`:**
- filtro por `estado` (uno y varios a la vez);
- paginación real con más de una página;
- alcance del supervisor: una OC sin ningún candidato en su universo no aparece;
- `primer_quiebre` correcto y `null` cuando no hay ninguno;
- `horizonte_dias > 366` → 422.

**Transversal a los tres:**
- la advertencia obligatoria está SIEMPRE presente, con el texto exacto;
- ningún endpoint escribe nada (comparar `event_log`/`outbox_events`/
  `evaluacion_habilitacion` antes y después — cero filas nuevas).

## 13. ¿Se puede implementar sin migración?

**Sí.** Los tres endpoints son de sólo lectura sobre tablas que ya existen
(`oc`, `matriz_requisitos`, `linea_requisito`, `requisito_particular`, `documento`,
`acreditacion_competencia`, `induccion`, `evaluacion_habilitacion`,
`evaluacion_sujeto_propuesto`, `legajo`, `asignacion_supervisor`, y `archivo_validacion`/
`archivo_estado` de la migración 0021 ya aplicada). No hay estado nuevo que persistir: el
cálculo de quiebres, intervalos y estado resumen es enteramente derivado en memoria a
partir de lo que `_evaluar()`/`evaluar_documento_en_periodo` ya leen hoy. La única
condición es que la Fase 2 (ya cerrada) esté efectivamente en el head que se use como base
— `archivo_requiere_revision` (punto 2 de la Fase 2) es lo que alimenta el estado
`requiere_revision` de este diseño.

---

**Pendiente de tu decisión antes de implementar** (no bloquea aprobar este documento, pero
sí el código):
1. ¿El endpoint puntual (`proyeccion_documental`) vive en `app/modules/consultas/` junto a
   `cobertura_oc`, o en un módulo nuevo (`app/modules/proyeccion/`) dado el tamaño del
   cálculo de quiebres? Este documento no lo fija.
2. ¿`calendario_vigencias` reemplaza a `tablero_vencimientos` o conviven? Tal como está
   diseñado acá, son complementarios (rango explícito vs. "próximos N días"), pero es una
   decisión de producto, no técnica.
