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
