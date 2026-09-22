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
válidos, nunca una promesa de disponibilidad** (retomado en el punto 5). Cualquier
respuesta de estos tres endpoints lleva la advertencia obligatoria — texto exacto fijado
más abajo (punto 5) y repetido en cada ejemplo de respuesta (puntos 3, 9 y 10). Esta
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
general (nada vence pronto) y aun así la OC estar `bloqueo_confirmado` porque HOY el tipo
exigido específico no tiene NINGÚN candidato — nada por vencer pronto no es lo mismo que
haber alguien que lo cubra hoy mismo (ver puntos 6 y 7: `bloqueo_confirmado` como resumen
es siempre sobre el primer intervalo del rango, nunca uno posterior — eso es
`riesgo_documental`).

### 2.1 Declaración de alcance de `calendario_vigencias` (confirmación explícita)

**`calendario_vigencias` es exclusivamente un calendario general de vencimientos de
evidencia registrada.** Por diseño (no por omisión):

- **No cruza contra ninguna matriz ni ninguna OC.** No sabe, y no puede saber al
  responder, si un requisito es exigido, opcional o irrelevante para ningún compromiso.
  Consultarlo NO reemplaza a `proyeccion_documental`/`proyeccion_documental_backlog`, que
  son las únicas dos consultas que sí resuelven esa pregunta.
- **No emite ni puede emitir un estado `sin_evidencia`.** Sólo devuelve filas que
  provienen de evidencia YA REGISTRADA (`documento`/`acreditacion_competencia`/
  `induccion` existentes) — la ausencia total de un dato no es una fila de este endpoint,
  es la ausencia de una fila. Detectar "falta evidencia para el requisito X de la OC Y" es
  exactamente lo que hace `proyeccion_documental` (vía `bloqueo_confirmado`/
  `causas[].motivo`), nunca `calendario_vigencias`.
- **No puede presentar ninguna evidencia como obligatoria.** Cada fila trae el hecho
  crudo (`sujeto_id`, `requisito`, `vigente_desde/hasta`, `estado_confirmacion`,
  `archivo_validacion`, `dias_para_vencer`) sin ningún campo de "obligatoriedad" ni de
  "contexto de matriz/OC" — porque no tiene ese dato. Un consumidor que necesite saber si
  un vencimiento es exigible tiene que cruzarlo con `proyeccion_documental`/`_backlog`
  para ESA OC puntual; `calendario_vigencias` nunca inventa esa respuesta por su cuenta.

Esto es una respuesta directa a la especificación previa del frontend (Q-DOC-01,
`docs/frontend/API_GAPS.md`), que pedía que cada ítem del calendario trajera "contexto de
aplicabilidad" (matriz/OC o ausencia explícita) y un estado `sin_evidencia`: **ese pedido
no se puede cumplir con este endpoint tal como está diseñado**, porque cruzar contra
matriz/OC es precisamente lo que este endpoint decide no hacer (punto 2, arriba). Si se
necesita esa combinación en una sola respuesta, es una decisión de producto pendiente —
options: (a) el frontend arma la combinación en el cliente, cruzando
`calendario_vigencias` con `proyeccion_documental_backlog`/`proyeccion_documental` por
`sujeto_id`/`commitment_id`; o (b) se diseña un cuarto endpoint explícito para eso (fuera
del alcance de este documento; no implementado). No se resuelve acá.

## 3. `GET /v1/consultas/calendario_vigencias`

**Rol**: `responsable_legajos` (todo el tenant), `supervisor` (su universo) y `técnico`
(su propio legajo + custodia) — los tres vía `alcance_de_sujetos`. Amplía deliberadamente
la matriz de `tablero_vencimientos` (hoy sólo `responsable_legajos`/`supervisor`): un
técnico ya ve sus propios vencimientos en el resumen de `mi_legajo`
(`vencidos`/`vigentes_hoy`), pero sin control de rango de fechas; `calendario_vigencias`
con `alcance_de_sujetos` acotado a su propio legajo es exactamente eso mismo con rango
explícito, no un permiso nuevo — coherente con que `documentos`/`sujetos` (H-06) ya
incluyen técnico en su matriz de roles.

**Parámetros**

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `desde` | fecha | `hoy` del tenant | no puede ser anterior a `hoy - 366` (para no convertir esto en un archivo histórico completo; ver punto 8) |
| `hasta` | fecha | `desde + 30` | `hasta - desde <= 366` días (punto 8) |
| `tipo_sujeto` | `persona\|vehiculo\|equipo\|empresa` | todos | filtro |
| `categoria` | `documento\|competencia\|induccion` | todas | filtro |
| `estado` | `vigente\|vencido\|todos` | `todos` dentro del rango | un vencido con `vigente_hasta` dentro del rango sigue apareciendo |
| `q` | texto | — | ILIKE sobre `sujeto_id` o `identificador_natural` (misma convención que `sujetos` en H-06) |
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
      "vigente_desde": "2026-03-30",
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

### 3.1 Decisión explícita: los 4 "estados visuales" (verificada/próxima a vencer/vencida/declarada)

El frontend (mock temporal, Q-DOC-01) imaginó un campo `estado` de calendario con 5
valores: `verificada`, `proxima_a_vencer`, `vencida`, `declarada`, `sin_evidencia`.
`sin_evidencia` ya queda resuelto en el punto 2.1 (nunca es una fila de este endpoint).
Para los otros 4, la decisión, campo por campo:

- **`declarada`, `verificada`, `vencida`: presentación INEQUÍVOCA de campos ya devueltos,
  el frontend los deriva — no hace falta que el backend agregue nada.** Fórmulas exactas,
  sin ningún número a inventar:
  - `declarada` ⟺ `estado_confirmacion === "declarado"`.
  - `vencida` ⟺ `dias_para_vencer < 0` (equivalente a `vigente_hasta < hoy`).
  - `verificada` ⟺ `estado_confirmacion !== "declarado"` Y NO `vencida`.
  Ninguna de las tres necesita un umbral: son funciones directas y sin ambigüedad de
  campos que ya viajan en cada ítem (`estado_confirmacion`, `dias_para_vencer`).
- **`proxima_a_vencer` es la EXCEPCIÓN y NO se resuelve así.** Definir "próxima" exige un
  umbral en días, y ese umbral **ya existe como concepto de dominio**:
  `plazo_aviso_dias` (`modulo1.configuracion_alertas`, con override opcional por
  `definicion_requisito.plazo_aviso_dias` — el mismo mecanismo que ya usa
  `app/core/alertas.py`/`ParametrosAlerta` para decidir cuándo abrir una Alerta de
  Vencimiento). **El frontend NO debe inventar un número de días propio para esto** — ni
  hardcodeado ni configurable en el cliente. Mientras `calendario_vigencias` no lo calcule
  server-side (no lo hace hoy: es deliberadamente genérico, sin cruzar contra
  `configuracion_alertas` ni `definicion_requisito.plazo_aviso_dias` por sujeto/requisito),
  `proxima_a_vencer` **no es un estado disponible** en esta consulta. Si hace falta
  mostrarlo, hay dos caminos — ninguno es "el frontend decide un número":
  1. Ampliar `calendario_vigencias` (cambio de contrato, requiere aprobación) para que
     cada ítem traiga el mismo `plazo_aviso_dias` resuelto que ya usa el motor de alertas,
     y el frontend compare `dias_para_vencer <= plazo_aviso_dias` con el valor que le
     llegó — nunca uno propio.
  2. Cruzar del lado del cliente contra `GET /v1/consultas/configuracion_alertas` (ya
     existente, ver `docs/HANDOFF_FRONTEND.md`) para el plazo del tenant, y contra
     `definiciones_requisito` para el override por requisito si lo hay — más trabajo en el
     cliente, pero sigue sin inventar ningún número: usa el mismo dato que ya existe.

## 4. Última evaluación visible como conjunto de sujetos

Ni `proyeccion_documental` ni `proyeccion_documental_backlog` inventan a quién evaluar.
Para cada OC, el conjunto de sujetos a proyectar sale de, en este orden:

### 4.1. Última decisión visible

La última decisión persistida y VISIBLE para quien consulta (misma regla A-04 que ya usa
`backlog_oc`: `filtro_decisiones_visibles` — si algún sujeto propuesto de esa decisión
queda fuera del alcance de un supervisor, la decisión entera "no existe" para él, y se
cae al punto 4.2). Los sujetos de `evaluacion_sujeto_propuesto` de esa
`referencia_evaluacion` son el conjunto — **se lee, nunca se recalcula ni se sobreescribe
la decisión histórica**: `evaluacion_habilitacion.snapshot`, `veredicto_de_cumplimiento` y
`resultado_de_decision` de esa fila quedan intactos para siempre (mismo principio ya
cerrado para matrices: "una auditoría pregunta por la fecha de la OC, no por hoy").

### 4.2. Candidatos del alcance (sin decisión visible)

Si no hay ninguna decisión visible (nunca se evaluó esa OC, o la única que hay queda
fuera de alcance): el universo por defecto es el `candidatos` de `cobertura_de_oc` en modo
consulta — todos los legajos activos del tenant para responsable_legajos, o el universo
del supervisor. Este caso es exactamente `pendiente_de_planificacion` si además no hay
ningún candidato con NADA cargado (punto 6) — pero si hay candidatos potenciales (aunque
nadie los haya propuesto formalmente todavía), la proyección los usa igual: el objetivo es
anticipar, no esperar a que alguien arme la propuesta primero.

La proyección deja explícito de cuál de los dos (4.1 o 4.2) vino el conjunto:

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
legajo alcanzaría, documentalmente, si se las asignara". El nombre del campo ya lo dice
("potencial"), pero no alcanza solo con el nombre — de ahí que la advertencia sea
obligatoria y no opcional en el contrato, con el mismo texto exacto en las tres
respuestas:

> "Proyección documental calculada con la información registrada a la fecha. No garantiza
> disponibilidad ni asignación operativa."

**`0` no es lo mismo que ausente.** Las claves de este objeto (y de
`capacidad_documental_potencial_hoy`, punto 10) son SOLO los `tipo_sujeto` que la matriz
vigente de la OC efectivamente exige (punto 1). Un tipo ausente significa "esta OC no
pide ese tipo" — nunca aparece con `0` ni con `null`. Un tipo presente con valor `0`
significa "la OC lo exige y, ese día, ningún candidato del conjunto lo cubre" — es
precisamente la condición que dispara `bloqueo_confirmado` (hoy) o el intervalo de
`riesgo_documental`/`pendiente_de_planificacion` correspondiente (futuro). El objeto nunca
lleva un valor `null` explícito para ningún tipo.

## 6. Los seis estados cerrados

Vocabulario CERRADO — no se agregan variantes sin reabrir este documento. Aplican al
`estado` **resumen** de una OC completa (`proyeccion_documental` y cada fila de
`proyeccion_documental_backlog`); `calendario_vigencias` no los usa (punto 3).

**No los seis aplican a `intervalos[].estado`.** Cada intervalo (punto 8) es, por
construcción, un tramo donde la cobertura NO cambia — así que dentro de un mismo
intervalo no hay "hoy" ni "futuro" que comparar entre sí, sólo un hecho constante. Por
eso `intervalos[].estado` usa sólo TRES de los seis (los que describen un hecho de UN
intervalo en sí mismo, no una comparación entre intervalos):

- `bloqueo_confirmado`: algún tipo exigido tiene cero candidatos durante ESE intervalo.
- `requiere_revision`: la cobertura de algún tipo exigido durante ESE intervalo depende
  de un documento `REQUIERE_REVISION`.
- `sin_riesgos_detectados`: cubierto, sin duda, durante ESE intervalo.

`sin_matriz`, `pendiente_de_planificacion` y `riesgo_documental` sólo existen al nivel del
**resumen** (`estado`, no `intervalos[].estado`) — los dos primeros porque son anteriores
a tener ningún intervalo que evaluar (punto 7); `riesgo_documental` porque es
intrínsecamente una comparación ENTRE intervalos ("el primero está bien, uno posterior no")
y por eso no puede ser el hecho de un solo intervalo — ver el cálculo del resumen en el
punto 7.

| Estado | Cuándo (nivel) |
|---|---|
| `sin_matriz` | No hay matriz vigente para (cliente, locación, tipo_servicio) de la OC al día de ingreso (`oc.vigencia_desde`) — mismo caso que hoy dispara `sin_matriz_vigente` en `_evaluar()`/`avisar_oc_sin_matriz` (H-02), pero acá NUNCA se propaga como error 422: la proyección lo devuelve como estado, no como falla. (Resumen.) |
| `pendiente_de_planificacion` | Hay matriz, pero el conjunto de sujetos del punto 4 está vacío (ninguna decisión visible Y ningún candidato en el alcance) — no hay nada que evaluar todavía. (Resumen.) |
| `bloqueo_confirmado` | Durante ese intervalo, algún tipo exigido no tiene NINGÚN candidato que cubra todos sus requisitos bloqueantes. (Intervalo — y, si es el PRIMER intervalo del rango pedido, también es candidato a resumen: ver punto 7.) |
| `requiere_revision` | La cobertura de al menos un tipo exigido durante ese intervalo depende de un documento `REQUIERE_REVISION` (declarado sin confirmar, o archivo pendiente/inválido — Fase 2 punto 2) — el dato existe pero no es confiable, nunca se lo cuenta como cobertura real ni como bloqueo real. (Intervalo y resumen.) |
| `riesgo_documental` | El PRIMER intervalo del rango (el que cubre `desde`) es `sin_riesgos_detectados`, pero algún intervalo POSTERIOR es `bloqueo_confirmado` o `requiere_revision` — hoy bien, un vencimiento futuro sin candidato de respaldo detrás. (Sólo resumen — ver punto 7.) |
| `sin_riesgos_detectados` | Cubierta todos los intervalos del horizonte evaluado, sin documentos `REQUIERE_REVISION` en juego. (Intervalo y resumen.) |

## 7. Cómo se calcula el `estado` resumen a partir de los intervalos

**No es simplemente `peor(intervalos)`** — `riesgo_documental` no es un valor que ningún
intervalo individual pueda tener (punto 6), así que el cálculo tiene un paso extra antes
de comparar:

1. Si no hay matriz (`sin_matriz`) o el conjunto de sujetos está vacío
   (`pendiente_de_planificacion`), ESE es el resumen — no se llega a calcular ningún
   intervalo (2.2 de este documento no cambia).
2. Si no, se mira el PRIMER intervalo del rango pedido — el que cubre `desde`. **La
   fórmula de `desde` es la MISMA para los dos endpoints, sin excepción** (punto 10):
   `desde = max(hoy, oc.vigencia_desde)`. Nunca el calendario-hoy si la OC todavía no
   arrancó — ni en `proyeccion_documental` ni en `proyeccion_documental_backlog`: **ese
   primer intervalo ES el resumen** si es `bloqueo_confirmado` o `requiere_revision`.
3. Si el primer intervalo es `sin_riesgos_detectados`, se mira si ALGÚN intervalo
   posterior es `bloqueo_confirmado` o `requiere_revision`: si lo hay, el resumen es
   `riesgo_documental` (el primero sigue bien, pero hay un problema más adelante). Nunca
   se usa el estado de ese intervalo posterior directamente como resumen — eso sería
   mezclar "hoy" con "un día futuro" en el mismo campo, que es exactamente el defecto que
   esta sección corrige.
4. Si ningún intervalo tiene problema, el resumen es `sin_riesgos_detectados`.

Esto reemplaza una versión anterior de este documento que trataba `bloqueo_confirmado`
como "algún día del horizonte" sin distinguir el primero de los siguientes: con esa
redacción, todo caso de "hoy bien, futuro mal" (lo que hoy es `riesgo_documental`) también
cumplía la definición vieja de `bloqueo_confirmado`, y como tenía precedencia más alta,
`riesgo_documental` nunca se alcanzaba. El paso 2/3 de arriba es la corrección: SOLO el
primer intervalo puede producir `bloqueo_confirmado`/`requiere_revision` como resumen
directo; cualquier intervalo posterior con el mismo problema baja a `riesgo_documental`.

Justificación adicional:
- `bloqueo_confirmado` sobre `requiere_revision` cuando ambos podrían aplicar al primer
  intervalo a la vez (dos tipos exigidos distintos, uno sin ningún candidato y otro con
  candidato pero `REQUIERE_REVISION`): un bloqueo confirmado con datos confiables es más
  grave que una duda sobre datos.
- `requiere_revision` sobre `riesgo_documental` cuando el primer intervalo tiene
  `requiere_revision` Y además hay un intervalo posterior en `bloqueo_confirmado`: no se
  puede llamar "en riesgo" (que implica que hoy está bien) a algo que hoy mismo no se
  puede confirmar.

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
resumen (punto 7) y `proyeccion_documental_backlog` nunca necesitan expandirlo — corren
el cálculo del punto 7 directamente sobre la lista de intervalos.

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

En el ejemplo de abajo la OC ya está vigente (`oc.vigencia_desde = 2026-08-01`, anterior a
`hoy = 2026-09-21`), por eso `desde = max(hoy, oc.vigencia_desde) = hoy`. Si la OC
arrancara DESPUÉS de hoy, `desde` sería `oc.vigencia_desde`, no `hoy` — la regla de la
tabla siempre manda, el ejemplo es sólo un caso particular de ella.

**Respuesta (`detalle=resumen`)**

```json
{
  "commitment_id": "OC-4587",
  "hoy": "2026-09-21",
  "oc": {"cliente_id": "…", "locacion_id": "…", "tipo_servicio_id": "…",
         "vigencia_desde": "2026-08-01", "vigencia_hasta": "2026-10-10"},
  "desde": "2026-09-21", "hasta": "2026-10-10",
  "matriz": {"matriz_version_id": "…", "version": 3, "tipos_exigidos": ["persona", "vehiculo"]},
  "sujetos": { "...": "ver punto 4" },
  "estado": "riesgo_documental",
  "intervalos": [
    {
      "desde": "2026-09-21", "hasta": "2026-09-29", "estado": "sin_riesgos_detectados",
      "capacidad_documental_potencial": {"persona": 2, "vehiculo": 1}
    },
    {
      "desde": "2026-09-30", "hasta": "2026-10-04", "estado": "sin_riesgos_detectados",
      "capacidad_documental_potencial": {"persona": 1, "vehiculo": 1}
    },
    {
      "desde": "2026-10-05", "hasta": "2026-10-10", "estado": "bloqueo_confirmado",
      "capacidad_documental_potencial": {"persona": 0, "vehiculo": 1},
      "causas": [
        {
          "tipo_sujeto": "persona",
          "requisito_definicion_id": "…", "requisito": "Apto médico",
          "motivo": "persona_0077 venció el 2026-09-29 sin ser reemplazado; persona_0042, el único candidato de respaldo que quedaba, vence el 2026-10-04 — desde el 2026-10-05 el tipo persona queda sin ningún candidato",
          "sujetos_que_pierden_cobertura": ["persona_0042"],
          "sujetos_que_mantienen_cobertura": []
        }
      ]
    }
  ],
  "advertencia": "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
}
```

Por qué el resumen es `riesgo_documental` y no `bloqueo_confirmado` (punto 7): el PRIMER
intervalo (2026-09-21 a 2026-09-29, el que cubre `desde`) es `sin_riesgos_detectados` — hoy
está cubierto. El intervalo del medio (2026-09-30 a 2026-10-04) también, aunque con un solo
candidato de respaldo: eso no es un problema en sí mismo, así que sigue
`sin_riesgos_detectados` a nivel de intervalo (punto 6) — no hay que confundir "queda un
solo candidato" con "está en riesgo": un ejemplo anterior de este documento cometía
exactamente ese error, etiquetando ese intervalo intermedio como `riesgo_documental`
cuando todavía tenía cobertura real. El TERCER intervalo (desde 2026-10-05) sí es
`bloqueo_confirmado` a nivel de intervalo (cero candidatos de persona) — pero por ser
POSTERIOR al primero, no se propaga tal cual al resumen: se traduce a `riesgo_documental`
("hoy bien, más adelante no").

Con `detalle=diario`, se agrega `"estado_por_dia": {"2026-09-21": "sin_riesgos_detectados", …}`
expandiendo cada intervalo — pensado para pintar el Gantt día a día tal como se discutió,
sin que el backend tenga que recalcular nada distinto (es el mismo resultado por
intervalo, sólo repetido por fecha).

**Causas explicables**: todo estado que no sea `sin_riesgos_detectados` trae `causas[]` —
nunca un estado "bloqueado" o "en riesgo" sin decir por qué, mismo estándar que ya exige
`VeredictoRequisito.motivo` en el motor puro. La forma de `causas[]` depende del estado:

- `bloqueo_confirmado`, `requiere_revision`, `riesgo_documental`: por tipo/requisito
  afectado, con `tipo_sujeto`, `requisito_definicion_id`, `requisito`, `motivo` y
  `sujetos_que_pierden_cobertura`/`sujetos_que_mantienen_cobertura` (forma del ejemplo de
  arriba) — hay una matriz resuelta y candidatos evaluados, así que hay tipo/requisito al
  que apuntar.
- `sin_matriz` y `pendiente_de_planificacion`: **no hay matriz resuelta ni candidatos
  evaluados** (punto 6/7: son "no se puede evaluar", nunca llegan al motor puro), así que
  no hay tipo/requisito que citar. `causas` es una lista de un solo elemento con `motivo`
  (string) con dato real y el resto de los campos (`tipo_sujeto`,
  `requisito_definicion_id`, `sujetos_que_pierden_cobertura`,
  `sujetos_que_mantienen_cobertura`) en `null` — mismo criterio que el resto del contrato
  (p. ej. `periodo_cerrado_id` en `cambiar_custodia`): un campo sin dato viaja en `null`,
  nunca se omite la clave. P. ej. `[{"motivo": "No hay matriz vigente para (cliente_id,
  locacion_id, tipo_servicio_id) al día de ingreso de la OC", "tipo_sujeto": null,
  "requisito_definicion_id": null, "sujetos_que_pierden_cobertura": null,
  "sujetos_que_mantienen_cobertura": null}]`.

## 10. `GET /v1/consultas/proyeccion_documental_backlog`

**Rol**: `responsable_legajos`, `supervisor` (alcance por OC: una OC entra en el backlog
del supervisor sólo si al menos un candidato de su conjunto — punto 4 — está en su
universo; si no, no aparece, no se sustituye por "sin datos").

**Parámetros**

| Parámetro | Tipo | Default | Notas |
|---|---|---|---|
| `estado_oc` | `activo\|cancelado` | `activo` | mismo filtro que `backlog_oc` |
| `estado` | uno de los 6 (punto 6), repetible | todos | filtra el resumen — p. ej. `?estado=bloqueo_confirmado&estado=riesgo_documental` para la vista "qué me preocupa" |
| `horizonte_dias` | entero | `30` | tope de ventana por OC; `<= 366` |
| paginación | `offset`/`limit` | `0`/`50`, máx. `500` | igual convención que `backlog_oc` |

**Respuesta**

```json
{
  "hoy": "2026-09-21",
  "horizonte_dias": 30,
  "items": [
    {
      "commitment_id": "OC-4587",
      "vigencia_desde": "2026-08-01", "vigencia_hasta": "2026-10-10",
      "estado": "riesgo_documental",
      "primer_quiebre": "2026-10-05",
      "capacidad_documental_potencial_hoy": {"persona": 2, "vehiculo": 1},
      "origen_calculo": "ultima_decision_visible",
      "motivos_resumidos": [
        "Apto médico: persona_0077 venció el 2026-09-29 sin ser reemplazado; persona_0042, el único candidato de respaldo que quedaba, vence el 2026-10-04 — desde el 2026-10-05 el tipo persona queda sin ningún candidato"
      ]
    }
  ],
  "total": 214,
  "offset": 0,
  "limit": 50,
  "advertencia": "Proyección documental calculada con la información registrada a la fecha. No garantiza disponibilidad ni asignación operativa."
}
```

Es EXACTAMENTE la OC-4587 del ejemplo del punto 9 (mismos `vigencia_desde`/`vigencia_hasta`,
mismo `estado`) — a propósito, para que se pueda verificar la equivalencia a simple vista:
el punto 9 tiene tres intervalos (2026-09-21 a 09-29 y 09-30 a 10-04, ambos
`sin_riesgos_detectados` a nivel de intervalo — ver punto 6, un solo candidato de respaldo
no es problema por sí mismo —, y 10-05 a 10-10, `bloqueo_confirmado` a nivel de intervalo).
`primer_quiebre` es la fecha del primer intervalo cuyo estado DE INTERVALO no es
`sin_riesgos_detectados` — acá el tercero, `2026-10-05`, no el segundo: ese sigue cubierto
(persona: 1), no es un quiebre. `null` si no hay ninguno. `capacidad_documental_potencial_hoy`
es la del primer intervalo (el mismo que en el punto 9), no la de un intervalo posterior.

Cada fila es el resumen de `proyeccion_documental` para esa OC sin `causas`/`intervalos`
completos (eso se pide aparte, por OC, con el endpoint puntual — el backlog es para barrer
y priorizar, no para explicar cada caso en detalle). Dos campos la resumen sin obligar a
pedir el detalle puntual:

- `origen_calculo`: el mismo valor que `sujetos.origen` del punto 4/9 para esa OC —
  `ultima_decision_visible` o `candidatos_del_alcance` — para que quien lee el backlog
  sepa si el cálculo se apoya en una decisión ya tomada o en el universo de candidatos sin
  decisión formal todavía.
- `motivos_resumidos`: los `motivo` de las `causas` del intervalo que efectivamente explica
  el `estado` (punto 7: el primero si es `bloqueo_confirmado`/`requiere_revision`, o el
  primer intervalo posterior con problema si es `riesgo_documental`) — lista vacía sólo
  cuando `estado = sin_riesgos_detectados`. Para `sin_matriz`/`pendiente_de_planificacion`
  es un único motivo genérico (mismo texto que el `causas[0].motivo` del punto 9).

**La ventana por OC es exactamente la del punto 9, nunca otra**: `desde = max(hoy,
oc.vigencia_desde)`, `hasta = min(oc.vigencia_hasta, desde + horizonte_dias)` — así el
`estado` de una OC en el backlog es SIEMPRE el mismo que devolvería consultarla
puntualmente con ese `hasta` acotado; `horizonte_dias` sólo recorta cuánto del rango de la
OC se mira, relativo a `desde` (el inicio efectivamente evaluado, no el calendario-hoy).
Con `horizonte_dias > 0` la fórmula nunca produce `desde > hasta` para una OC futura —
lejana o no, `hasta = min(oc.vigencia_hasta, desde + horizonte_dias) >= desde` siempre
que `oc.vigencia_hasta >= desde` (una OC con `vigencia_desde <= vigencia_hasta` cumple
esto salvo el caso aparte de abajo. Una OC futura lejana simplemente entra al backlog con
un rango completo, empezando en su propia `vigencia_desde` — no hay ningún caso en que
quede excluida por estar lejos.

Único caso real donde no hay ventana válida: una OC `activo` (no cancelada, punto 10)
cuya `vigencia_hasta` ya quedó en el pasado respecto de `desde` (su ventana entera ya
terminó sin que nadie la cancelara explícitamente) — ahí no hay ningún intervalo que
calcular; la fila entra igual al backlog con el `estado` que corresponda por punto 4/6
(`pendiente_de_planificacion` si además no hay candidatos, u otro válido si los hay) y
`primer_quiebre: null`, nunca se excluye ni se sustituye por "sin datos".

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
- **`matriz` no es `null` en `pendiente_de_planificacion` cuando SÍ hay matriz vigente**
  (`matriz_version_id`/`version`/`tipos_exigidos` reales) — `matriz` es `null` únicamente
  cuando `estado = sin_matriz`; test de regresión dedicado, con su contraparte
  (`sin_matriz` ⟹ `matriz` es `null`) en el mismo archivo;
- `bloqueo_confirmado` desde el primer día cuando ya hoy no hay cobertura;
- `requiere_revision` con un documento declarado sin confirmar, y por separado con un
  archivo con `archivo_validacion` pendiente/inválido (Fase 2 punto 2) — confirmar que
  NUNCA se cuenta como cobertura real ni figura en `capacidad_documental_potencial`;
  regresión específica: un `REQUIERE_REVISION` no debe filtrarse a `sin_riesgos_detectados`;
- `riesgo_documental`: hoy verde, un vencimiento futuro sin respaldo → intervalo
  correcto, `causas` con el sujeto que pierde cobertura;
- **regresión de la mutua exclusión (puntos 6/7)**: un tipo exigido con cobertura en el
  primer intervalo y pérdida total de cobertura en un intervalo posterior tiene que dar
  `riesgo_documental` de resumen, NUNCA `bloqueo_confirmado` — el caso que exactamente
  distingue las dos definiciones (regresión directa del ejemplo del punto 9);
- **intervalo intermedio con un solo candidato de respaldo NO es riesgo**: un intervalo
  que sigue cubierto (aunque con un solo candidato en vez de varios) tiene que quedar
  `sin_riesgos_detectados` a nivel de intervalo — no confundir "menos redundancia" con
  "en riesgo" (regresión directa del error que tenía la versión anterior del ejemplo);
- **OC que todavía no arrancó** (`oc.vigencia_desde` en el futuro, hoy anterior a esa
  fecha): `desde = oc.vigencia_desde`, no `hoy` (punto 9); si ese primer intervalo (el que
  arranca en el futuro) es `bloqueo_confirmado`, el resumen tiene que ser
  `bloqueo_confirmado` igual, aunque calendario-hoy sea antes de que la OC empiece — la
  referencia para "primero" es el primer intervalo del RANGO PEDIDO, nunca la fecha civil
  de hoy si la OC arranca después;
- `causas` de `sin_matriz`/`pendiente_de_planificacion` sin `tipo_sujeto` ni
  `requisito_definicion_id`, sólo `motivo` (punto 9) — nunca el formato de las otras
  causas;
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
- **misma OC, mismo estado**: el `estado` de una fila del backlog coincide con el que
  devuelve `proyeccion_documental?commitment_id=…` para esa OC con `hasta` acotado a
  `min(oc.vigencia_hasta, desde + horizonte_dias)` (punto 10) — nunca un resumen
  diferente entre los dos endpoints para los mismos datos;
- filtro por `estado` (uno y varios a la vez);
- paginación real con más de una página;
- alcance del supervisor: una OC sin ningún candidato en su universo no aparece;
- `primer_quiebre` correcto y `null` cuando no hay ninguno;
- **OC futura lejana** (`oc.vigencia_desde` bastante después de `hoy + horizonte_dias`):
  entra igual al backlog con ventana completa desde su propia `vigencia_desde` — nunca
  `desde > hasta`, nunca excluida por estar lejos (regresión directa del punto 10);
- **OC ya vencida** (`activo` pero `oc.vigencia_hasta < desde`): entra igual, sin
  intervalos, `primer_quiebre: null`, nunca se cae del backlog;
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

## 14. Decisiones ya resueltas (histórico)

Las dos decisiones que este documento dejaba pendientes antes de implementar quedaron
resueltas en el código, no sólo en el diseño:

1. **Ubicación del endpoint puntual**: vive en un módulo nuevo, `app/modules/proyeccion/`
   (`servicio.py` + `router.py`), separado de `app/modules/consultas/` — el motor de
   quiebres (`app/core/proyeccion.py`) justificaba el módulo aparte.
2. **`calendario_vigencias` vs `tablero_vencimientos`**: conviven. `tablero_vencimientos`
   sigue existiendo tal cual (responsable_legajos/supervisor, "próximos N días");
   `calendario_vigencias` es la versión con rango explícito y ampliada a técnico — ninguno
   reemplazó al otro.

Sigue abierta, en cambio, la decisión del punto 2.1 (endpoint combinado
calendario+matriz/OC): esa no se resuelve en este documento a propósito.
