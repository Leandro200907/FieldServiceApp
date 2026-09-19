# Decisiones de dominio cerradas en implementación

Reglas que la especificación deja implícitas o que el código tuvo que resolver, cerradas
contra el texto de los documentos de diseño (`Escritorio/Ticketera/modulo1-*.md`).
Cada una tiene su test de aceptación en `tests/test_reglas_cerradas.py`. Cambiar una de
estas reglas exige releer la cita y justificar contra ella.

## 1. Propuesta del técnico (`ProponerDocumento` / `RechazarPropuesta`)

**Cita.** especificacion.md 2.2, invariantes de Documento: *"Al **declarar** o confirmar
una versión nueva del mismo requisito+sujeto, la anterior pasa a `sucedida` en la misma
operación"*; *"`rechazada` es terminal … ni participa de la invariante de 'a lo sumo un
vigente' — es como si nunca hubiera llegado a ser candidata"*; *"El motor siempre filtra
primero por `estado_version = vigente` y recién ahí mira `estado_confirmacion`"*.
documentacion-habilitante.md 1.10 / modelo-dominio.md 2.4: lo declarado nunca prueba la
habilitación; *"una renovación propuesta y no confirmada no cierra nada, solo pausa"*.

**Regla definitiva.**
- La propuesta entra como versión `vigente` + `declarado` + `origen_propuesta=true` y
  sucede al vigente anterior (guardando `sucede_a`). Mientras está pendiente, el motor
  ve esa versión y devuelve `requiere_revision` para ese requisito: el sujeto no prueba
  habilitación hasta que el Responsable confirme. **Consecuencia deliberada de la spec**:
  proponer una renovación temprano degrada el veredicto del sujeto hasta la revisión —
  por eso existe la alerta "propuesta pendiente hace más de N días" (habilitante 2.x).
- `RechazarPropuesta` → `rechazada` (terminal) y se restaura el **antecesor no terminal
  más cercano** siguiendo la cadena `sucede_a` (una `sucedida`). Si la antecesora
  inmediata ya es terminal (p. ej. un lote revertido después de la propuesta) se sigue
  subiendo; una versión terminal nunca se resucita.
- Solo se rechaza una propuesta `vigente`; una propuesta ya sucedida por otra versión
  devuelve 409 (la sucesión ya la dejó fuera de juego, y "rechazarla" no cambiaría nada).

**Código.** `app/modules/legajos/servicio.py::_insertar_version_documento`,
`rechazar_propuesta`, `_restaurar_sucedido`. Migración `0003_legajos_documento_sucede_a`.

## 2. Agregación del veredicto de la OC (`evaluar_compromiso`)

**Citas.** documentacion-habilitante.md 1.12: *"Se evalúa primero la empresa. Si no está
habilitada, bloquea toda la OC"*; *"para cada tipo de recurso que la matriz exige … se
pregunta si existe al menos un legajo individual de ese tipo que cumpla todos los
requisitos que le aplican. Nunca se compone el cumplimiento entre varios legajos
parciales"*. 1.8: la empresa es *"siempre una"* y *"siempre evaluada"*. 1.9: `vence
durante el trabajo` *"Avisa siempre; bloquea solo si el requisito está marcado
`bloqueante_durante_ejecucion`"*; `requiere revisión` *"No habilita ni bloquea en
firme"*. 1.6: la OT queda *"asignada bajo excepción"*. especificacion.md 4.1: *"si
`resultado_de_decision = puede_asignarse_bajo_excepcion`, entonces
`veredicto_de_cumplimiento` no puede ser `habilitado`"*; regla temporal: *"`version_matriz`
es la vigente a `periodo_desde` (el día de ingreso)"*.

**Regla definitiva.**
- Por requisito se calcula un veredicto (motor puro, sin cambios) y una **asignabilidad**:
  `habilitado` → asignable; `vence_durante_el_trabajo` y la línea no es
  `bloqueante_durante_ejecucion` → asignable (avisa, no bloquea); cualquier otro caso →
  asignable solo si hay excepción `otorgada` con efecto (`excepcion_tiene_efecto`).
  Constancia del cliente vigente y aplicable vuelve `habilitado` un requisito
  `bloqueante_duro` (4.5); sobre excepcionable no tiene efecto.
- Por sujeto: veredicto = peor de sus requisitos; asignable = **todos** sus requisitos
  asignables; `bajo_excepcion` = asignable y al menos un requisito depende de excepción.
- Representante por tipo exigido (1.12): primero asignable por sí mismo, después
  asignable bajo excepción, después no asignable; dentro de cada clase, el de menor
  severidad. Así un sujeto `no_habilitado` bajo excepción cubre la OC por delante de uno
  `vence_durante_el_trabajo` bloqueante, y si nadie cubre, el motivo apunta al menos grave.
- Global: `veredicto_de_cumplimiento` = **peor** entre empresa y representantes (nunca más
  favorable que ellos). `resultado_de_decision` = `no_puede_asignarse` si la empresa o
  algún tipo exigido no tiene representante asignable (o no hay legajo de empresa
  cuando la matriz le exige requisitos, o no hay legajos activos del tipo);
  `puede_asignarse_bajo_excepcion` si todos son asignables y alguno depende de
  excepción (⇒ el global no es `habilitado`, se cumple `ck_excepcion_nunca_verde` por
  construcción); `puede_asignarse` en el resto.
- `requiere_revision` no es asignable: la decisión en firme es `no_puede_asignarse`
  (la spec pide "completar o confirmar el dato antes de decidir"; no existe un cuarto
  resultado de decisión).
- La versión de matriz (y la clasificación que rige para excepciones/constancias) es la
  vigente al `vigencia_desde` de la OC, **no a hoy**. "Hoy" (fecha civil del tenant)
  solo decide vencimientos de constancias/excepciones, que son hechos del presente.

**Casos borde que estaban mal cubiertos antes de esta revisión.**
1. Sujeto A `vence_durante` bloqueante + sujeto B `no_habilitado` bajo excepción: elegía A
   (menor severidad) y daba `no_puede_asignarse`; ahora cubre B bajo excepción.
2. `bloqueante_durante_ejecucion=false` se ignoraba: un requisito que vence durante la OT
   bloqueaba siempre. Ahora avisa y deja asignar.
3. Sin legajo de empresa con requisitos de empresa en la matriz: se omitía la empresa y
   podía dar `puede_asignarse`. Ahora `no_habilitado`.
4. Matriz elegida por "hoy": una OC de septiembre evaluada en octubre usaba la matriz de
   octubre. Ahora usa la vigente al día de ingreso.

**Código.** `app/core/orquestacion.py` (`_evaluar_requisito`, `_evaluar_sujeto`,
`_clave_mejor_sujeto`, `evaluar_compromiso`, `clasificacion_vigente`).

## 3. Lotes (`ImportarLote` / `RevertirLote`)

**Citas.** especificacion.md 2.5: *"Al revertir, todos los Documentos … creados por ese
`lote_id` se marcan `revertida_por_lote` en la misma operación — no puede quedar un
subconjunto sin marcar"*; 2.2 máquina de estados: `vigente ──[RevertirLote]──►
revertida_por_lote`. modelo-dominio.md 2.11 políticas: *"Fila que matchea un documento
existente, con vigencia posterior → renovación (nueva versión, se guarda la anterior)"*;
*"coincide con lo que ya hay → no hace nada, no duplica"*; *"contradice un dato ya
`verificado` con vigencia no posterior → nunca se sobreescribe solo … un dato de menor
confianza nunca pisa uno de mayor confianza sin que una persona lo confirme"*; 2.12:
*"Revertir sin borrar"*.

**Regla definitiva.**
- Revertir marca `revertida_por_lote` **todos** los documentos del lote que no sean ya
  terminales, estuvieran `vigente` o `sucedida`. Restaura el antecesor (cadena
  `sucede_a`, antecesor no terminal más cercano) **solo** para los que seguían `vigente`:
  si hubo una carga manual posterior, esa carga es una decisión humana más reciente y
  queda vigente; el lote se anula igual (auditoría completa), sin resucitar dos versiones
  (`uq_documento_vigente`).
- Reimportación, contra el vigente del mismo (sujeto, requisito): mismas fechas y mismo
  número (o número ausente) → `sin_cambios` (cuenta como aceptada, no crea versión);
  `vigente_hasta` posterior → nueva versión; no posterior y el vigente está
  `verificado`/`confirmado_en_fuente` → fila rechazada con
  `conflicto_con_dato_verificado`; no posterior y el vigente es solo `declarado` → nueva
  versión (misma confianza, la planilla es el dato más reciente).
- No hace falta conservar más historia: `sucede_a` + `lote_id` + `estado_version`
  alcanzan para reconstruir y revertir con seguridad; la información nunca se borra.

**Código.** `app/modules/legajos/servicio.py::_politica_reimportacion`, `importar_lote`,
`revertir_lote`, `_restaurar_sucedido`.

## 4. Universo del supervisor — fuente única

**Citas.** no-funcionales.md 2.2 (matriz) y 2.3 (visibilidad); habilitante 1.5 / 1.5 bis
(la custodia la administra el supervisor).

**Regla definitiva.** `app/auth/alcance.py` es la única implementación: universo =
sujetos con `asignacion_supervisor` vigente hacia el usuario (`desde <= hoy`) ∪
vehículos/equipos con `periodo_custodia` vigente cuyo custodio está en ese conjunto. Un
supervisor sin asignaciones ve vacío, nunca todo. Lo único que varía por capacidad es
**qué roles ven todo** (`roles_con_todo`): lectura de consultas → responsable +
configuración; descarga de evidencia → solo responsable (matriz 2.2). `consultas/acceso.py`
reexporta; `storage/servicio.py` llama a `sujeto_en_alcance`. Las dos implementaciones
anteriores tenían la misma semántica (mismas condiciones, misma JOIN de custodia); la
única divergencia real era la lista de roles con todo, que ahora es explícita.

## Puntos que la especificación no permite decidir sola

1. **Calendario de la locación** (4.1: *"en el calendario de la locación de ese
   compromiso"*). No hay dato de zona horaria por locación en el modelo; se usa
   `tenant.zona_horaria`. Correcto mientras todas las locaciones del tenant estén en la
   misma zona (caso Vaca Muerta). Si aparece un tenant multi-zona, hace falta
   `locacion.zona_horaria` y un cambio en `evaluar_compromiso`.
2. **Propuesta y veredicto intermedio.** La spec dice que la propuesta sucede al vigente
   y que lo declarado no prueba; la consecuencia (el sujeto queda `requiere_revision`
   hasta la revisión, aunque el documento anterior siguiera vigente) es literal pero
   operativamente incómoda. Está implementada tal cual; si se quiere "el anterior sigue
   probando hasta que se confirme o rechace la propuesta", es un cambio de dominio (dos
   vigentes por (sujeto, requisito) o un estado nuevo), no de implementación.
3. **Excepción sobre un requisito de empresa.** 1.6 habla de excepciones del supervisor
   sobre documentos excepcionables sin distinguir familia de sujeto; modelo-dominio 2.4
   solo aclara que un bloqueante duro de empresa no admite excepción. Se implementa la
   regla general (excepcionable de empresa admite excepción). Confirmar si se desea
   restringir.
4. **`requiere_revision` como decisión.** No existe un resultado de decisión "pendiente";
   se mapea a `no_puede_asignarse`. Si Módulo 2 necesita distinguir "bloqueado" de
   "falta confirmar un dato", debería leer `veredicto_de_cumplimiento`, no solo
   `resultado_de_decision`.
5. **`sin_cambios` en lotes**: la spec dice "no hace nada, no duplica" pero no si cuenta
   como fila aceptada o rechazada. Se cuenta como aceptada (no es un error) y se informa
   aparte en `filas_sin_cambios`.

## 5. Concurrencia — dónde protege la base y dónde la lógica

Revisado en la sesión 4 (`tests/test_robustez.py`, sección 6).

| Carrera | Invariante | Protección en la base | Protección en código |
|---|---|---|---|
| Dos versiones nuevas del mismo (sujeto, requisito) | ≤ 1 vigente | `uq_documento_vigente` | lock de la fila `legajo` (`_bloquear_legajo`) antes del vigente: el segundo escritor ve la versión del primero y la sucede. Sin ese ancla, READ COMMITTED re-evaluaba el `FOR UPDATE` sobre el vigente ya sucedido, devolvía vacío y el segundo chocaba contra el índice (500). |
| Confirmar y rechazar la misma propuesta | transiciones desde estado origen | — | `FOR UPDATE` por PK del documento; el segundo re-lee el estado nuevo → 409 |
| Revertir lote vs carga manual | ≤ 1 vigente | `uq_documento_vigente` | ambos toman el lock de `legajo` (revertir: legajos ordenados alfabéticamente → documentos; carga: legajo → documento). Orden fijo = sin deadlock. |
| Dos primeras asignaciones de supervisor | ≤ 1 vigente por sujeto | `uq_asignacion_supervisor_vigente` | lock de `legajo` en asignar/reasignar → el segundo ve la vigente → 409 |
| Dos evaluaciones de la misma OC | ninguna (inmutables) | — | dos filas, cada una consistente con su propio snapshot (4.1: "toda corrección es una evaluación nueva") |
| Primera versión de matriz para una clave | sin dos v1 | `uq_matriz_clave_version` | `IntegrityError` → 409 en `publicar_version_de_matriz` |
| Cambio de custodia concurrente | ≤ 1 período vigente | `uq_periodo_custodia_vigente` | lock de `custodia_recurso` (ancla) antes del período vigente |

Red de seguridad global: `app/api/errores.py` traduce cualquier `IntegrityError` no anticipado
a **409 `conflicto_concurrencia`** (la transacción ya fue revertida por `tenant_session`).
Ninguna invariante crítica depende solo de Python: las que importan tienen índice/CHECK.

**Riesgos abiertos (aceptados):**
- `ImportarLote` toma el lock de cada legajo fila por fila (a través de
  `_insertar_version_documento`), no de todos al inicio; un lote grande concurrente con
  otro lote sobre los mismos sujetos en orden distinto podría deadlockear → Postgres
  aborta uno → 409 reintentable. No se serializa por tenant a propósito (bloquearía
  toda la carga masiva).
- `evaluar_compromiso` no bloquea nada: una evaluación puede leer un documento que otro
  comando está sucediendo en ese instante. Es consistente con el snapshot que persiste y
  con `HabilitacionRequiereRevaluacion` como mecanismo de corrección.

## 6. Contrato HTTP — orden de validación y autorización

FastAPI valida el body **antes** de ejecutar el handler, donde corre `exigir_rol`. Por
eso un body inválido con un rol incorrecto responde **422**, no 403. No es filtración
(el esquema es público en `/openapi.json`) y todas las rutas protegidas responden 401 sin
token antes de cualquier otra cosa (`test_contrato_http_todas_las_rutas_estan_protegidas`).

## 7. Modo consulta vs. modo decisión y alcance del supervisor (A-04, cerrado 2026-09-19)

**Citas.** modelo-dominio 2.1: *"Puntual: sujetos propuestos + un compromiso → veredicto.
Los recursos propuestos los declara el módulo 2 … Barrido: toda la vista de compromiso ×
todos los legajos → cobertura. Siempre en modo consulta"*; *"Consulta: no persiste, no
crea tareas, no emite eventos. Decisión: persiste el snapshot, emite el evento y devuelve
`referencia_evaluacion`"*. habilitante 1.5/1.5 bis: *"el motor evalúa siempre sobre los
sujetos propuestos que recibe"* (un parámetro). no-funcionales 2.2: *"Verificar
habilitación (**modo consulta**, antes de asignar)"* → responsable y supervisor;
*"cobertura del backlog"* → supervisor **"su universo"**. no-funcionales 2.3: el supervisor
ve *"las Evaluaciones de habilitación … cuyo sujeto caiga dentro"* de su universo.

**Regla definitiva.**
| | Decisión — `POST /comandos/evaluar_habilitacion` | Consulta — `GET /consultas/cobertura_oc` |
|---|---|---|
| Entrada | `commitment_id` + `sujetos_propuestos[]` (≥1; sin duplicados; legajos activos del tenant; nunca la empresa, que entra siempre implícita) | `commitment_id` |
| Cálculo | Empresa + **cada** propuesto entero. Todos deben ser asignables y cada tipo exigido debe estar presente | Empresa + mejor candidato asignable por tipo (1.12) |
| Candidatos | los propuestos | responsable: todo el tenant; supervisor: **solo su universo** |
| Persiste / emite | Sí: `evaluacion_habilitacion` + `evaluacion_sujeto_propuesto` (relación normalizada, FKs compuestas por tenant) + `EvaluacionDeHabilitacionRealizada`, misma transacción | **Nunca** |
| Roles | **solo responsable de legajos** (y la identidad técnica de Módulo 2 cuando se integre). Supervisor → 403 (mínimo privilegio: la matriz solo le da "modo consulta") | responsable, supervisor |

**Historial** (`backlog_oc.ultima_decision`, `decisiones_oc`, `decision`): el supervisor ve
una decisión solo si **todos** sus sujetos propuestos están en su universo; si uno queda
afuera la decisión entera no existe para él (404, sin filtrado parcial). La empresa no
interviene en el universo. `otorgar_excepcion` aplica lo mismo: la decisión citada tiene
que ser visible y el sujeto tiene que estar en el universo (403).

**`ultima_decision` del backlog** es la última decisión **global** de la OC. Para el
supervisor se devuelve solo si es visible; si no, `null` — nunca se sustituye por una
decisión anterior visible (se presentaría como "última" algo que no lo es).

**Excepciones sobre la empresa — DESHABILITADAS (cierre seguro).** Una excepción sobre un
requisito de la empresa afecta a toda la dotación y ningún rol tiene hoy ese alcance
definido (la empresa nunca está en el universo de un supervisor, y solo el supervisor
otorga excepciones). `otorgar_excepcion` con un sujeto de tipo empresa responde 422
`excepcion_de_empresa_deshabilitada` antes de cualquier chequeo de alcance, para
cualquier supervisor. Queda así hasta que el dominio defina qué rol puede afectar
globalmente a la empresa (ver "Puntos que la especificación no permite decidir sola",
ítem 3). Coherente con 2.4 de modelo-dominio ("para un bloqueante duro de empresa no
existe excepción").

**`evaluacion_sujeto_propuesto.tipo_sujeto_al_proponer`** es un snapshot deliberado del
tipo del legajo al decidir (parte de la foto inmutable de 4.1, CHECK sobre el enum); el
tipo vivo se lee siempre de `legajo.tipo_sujeto`.

**Código.** `app/core/orquestacion.py` (`_evaluar`, `cobertura_de_oc`,
`decidir_habilitacion`, `_validar_sujetos_propuestos`), `app/auth/alcance.py`
(`filtro_decisiones_visibles`, `decision_visible`), `app/modules/consultas/servicio.py`,
`app/modules/operacion/servicio.py`. Migración `0006_evaluacion_sujetos`. Tests:
`tests/test_a04_alcance_evaluacion.py`.

## 8. Política de revaluación y outbox (A-07, cerrado 2026-09-19)

Implementación declarativa de la tabla 7.2 en `app/core/revaluacion.py::EVENTOS_FUENTE`
(único lugar donde se decide qué evento marca qué decisiones). Definiciones:
- **Decisión vigente**: última decisión de un commitment (`ORDER BY creado_en DESC,
  secuencia DESC` — `secuencia` BIGSERIAL desempata de forma determinista; `creado_en` lo
  genera la base, nunca el cliente) con OC activa y `vigencia_hasta ≥ hoy`.
- **Marcar** = `aviso_revaluacion` (uno abierto por evaluación; coalescing: nuevas causas se
  suman en `aviso_revaluacion_causa`, única por `(aviso, evento_id)`, sin repetir el
  evento) + un `HabilitacionRequiereRevaluacion` en outbox por apertura
  (`clave_dedup = hrr:{referencia}:{aviso_id}`, UNIQUE por tenant). Nunca crea decisiones.
- **Idempotencia por evento causal**: `politica_evento_procesado (tenant_id, evento_id)`;
  reprocesar un evento antiguo no reabre un aviso cerrado.
- **Despachador**: `registrar_evento` despacha solo eventos fuente; los producidos por la
  política (`AvisoDeRevaluacion*`, `CumplimientoEmpresa*`) van por `registrar_evento_interno`.

| Evento | HRR | Selector |
|---|---|---|
| DocumentoVerificado | sí | decisiones que proponen al sujeto; empresa → todas |
| DocumentoCargado (cualquier estado) | **no** | el productor emite además `DocumentoVerificado` cuando la carga ya viene verificada (verificación implícita, evento canónico) |
| LoteRevertido | sí | sujetos de los documentos revertidos |
| LegajoDadoDeBaja | sí | decisiones que proponen al sujeto |
| MatrizVersionPublicada | sí | decisiones bajo la versión que se cierra (`version_anterior_id`) |
| RequisitoParticularCargado | sí | decisiones del commitment |
| Excepcion Otorgada/Revocada/Regularizada/Vencida | sí | decisión citada (si existe) + vigentes del commitment con el sujeto |
| Constancia Registrada/Revocada/Vencida | sí | específica: commitment; general: OCs del cliente con el sujeto |
| CustodiaCambiada | **condicional** | solo decisiones con `origen_sujetos = custodia_por_defecto` que proponen el recurso; `explicito` nunca. `origen_sujetos` lo fija exclusivamente el servidor: el body público lo rechaza con 422 (`extra=forbid`) |
| CompromisoModificado / CompromisoCancelado | sí | `referencias_afectadas` capturadas por el productor ANTES del cambio; payload con `tipo_cambio` — con `cancelacion` el consumidor **invalida**, nunca crea una decisión. `importar_lote_oc` emite UN `CompromisoModificado` por OC y transacción solo si cambia una entrada de la evaluación (`cliente_id`, `locacion_id`, `tipo_servicio_id`, `vigencia_desde`, `vigencia_hasta`); OC nueva, reimportación idéntica o cambio solo de `referencia` no emiten. El evento audita `campos_modificados`, `anterior` y `nuevo` |
| Vencimiento de documento de empresa (reloj) | outbox `CumplimientoEmpresaAfectado` | `aviso_incumplimiento_empresa` (uno abierto por tenant) con causas normalizadas (una activa por requisito); payload flaco con `aviso_id`; el consumidor consulta `GET /consultas/incumplimiento_empresa`. Marca internamente las decisiones vigentes sin HRR (2.9). Se regulariza solo cuando la reevaluación de TODAS las causas activas no encuentra ninguna incumplida |
| Resto de 7.2 (Cargado, Rechazado, Sucedido, Acreditación/Inducción, LoteAplicado, LegajoCreado, Supervisor*, Definicion*, EvaluacionRealizada, Tarea, CustodiaCorregida, ConstanciaReemplazada, Alerta*, ArchivoPurgado, Aviso*) | no | tests negativos uno por uno |

`EvaluacionDeHabilitacionRealizada` no genera HRR pero cierra, en la misma transacción,
los avisos abiertos de decisiones anteriores del mismo commitment (`AvisoDeRevaluacionCerrado`
por la vía interna), nunca de otra OC.

Ambigüedad registrada: acreditaciones e inducciones también son entradas del snapshot pero
la tabla 7.2 no les asigna HRR; se respeta la tabla.

## 9. Semántica del borrado físico (A-05)

`storage.borrar()` es **al menos una vez** e idempotente (borrar una clave ausente es
éxito). Están garantizados exactamente una confirmación en la base y un solo
`ArchivoPurgado`; una sola llamada física NO.

## 10. Integridad multi-tenant por claves foráneas compuestas (M-01, migración 0011)

Toda relación entre tablas tenant-scoped referencia `(tenant_id, id_padre)`; el padre
tiene `UNIQUE (tenant_id, id)`. RLS filtra lo que se lee; la FK prueba además que padre e
hijo son del mismo tenant aunque un bug o un endpoint nuevo se saltee la validación.
`ON DELETE` se conserva salvo dos correcciones: `custodia_recurso → periodo_custodia` y
`event_log → aviso_revaluacion_causa` dejan de ser CASCADE (historial y auditoría no se
borran por arrastre). Ningún CASCADE nuevo. Las migraciones que agregan FKs suspenden
`FORCE ROW LEVEL SECURITY` dentro de su transacción para que la validación de filas
existentes sea un escaneo real y no "cero filas visibles".

**Excepciones intencionales (sin FK):** `usuario.sujeto_id` (el usuario técnico puede
existir antes de importar su legajo; se valida en servicio), `acreditacion.evidencias[]`
(array; `_exigir_documentos_del_sujeto`), `*_por` (texto de auditoría), `cliente_id` /
`locacion_id` / `tipo_servicio_id` (maestros externos no modelados en Módulo 1),
`aviso_revaluacion_causa.entidad_id` (polimórfico), `idempotency_keys.actor_id`,
`job_queue.tenant_id` nullable (jobs de sistema).
