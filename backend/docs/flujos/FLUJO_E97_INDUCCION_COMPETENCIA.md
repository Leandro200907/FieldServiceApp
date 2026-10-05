# FLUJO E-97 — Respaldo de inducción y competencia

Decisiones de referencia: **D1**, **D19**, **C1** (reglas de vigencia de incorporación/carga),
**regla general: el frontend no calcula estados** (ver `backend/docs/DECISIONES_DOMINIO.md`).

**Supuesto de negocio (a confirmar con el cliente):** la inducción y la competencia se acreditan
con un **certificado propio** (PDF o imagen) emitido por el curso u operadora, con **fecha de
realización** y, si aplica, **fecha de vencimiento** en el certificado. Ese archivo no es
intercambiable por otro requisito del legajo (apto, ART, licencia).

## Roles

| Acción | Inducción | Competencia |
|--------|-----------|-------------|
| Ver faltante en ficha / Mi legajo | Técnico y responsable | Técnico y responsable |
| Subir certificado y fechas | **Responsable** (ficha del legajo) | **Responsable** |
| Registrar la evidencia en el sistema | **Responsable** (`registrar_induccion` / `registrar_acreditacion_de_competencia`) | Igual |
| Incorporar / renovar documentos “de legajo” | Técnico (flujos C / incorporación) | No aplica |

El técnico **no** registra inducción ni competencia (E-91); solo el responsable cierra el
faltante exigido por el backlog.

## Recorrido de punta a punta

### Inducción (responsable)

1. El responsable abre la **ficha del legajo** de la persona. En la tabla de documentación ve
   un faltante exigido de categoría **inducción** (nombre del requisito, p. ej. «Inducción HSE
   de la operadora») con acción **Registrar inducción**.

2. El formulario muestra en **solo lectura** la **locación / operadora** tomada de la definición
   del requisito (`locacion_id` de `definicion_requisito`); el responsable no la elige.

3. El responsable carga el **archivo del certificado** (imagen o PDF). El archivo sigue el mismo
   camino que cualquier documento: storage → worker → `archivo_validacion` (`pendiente` → `valido`
   o `invalido`). En paralelo indica:
   - **Fecha de realización** → `vigente_desde` (no futura respecto al «hoy» del tenant).
   - **Fecha de vencimiento** → `vigente_hasta` (reglas **C1**: posterior a `vigente_desde`; tope
     configurable, por defecto **10 años** desde hoy del tenant).

4. El sistema crea (o reutiliza, ver decisiones pendientes) un **documento soporte** del mismo
   sujeto y tenant — el certificado — y ejecuta `registrar_induccion` enlazando ese
   `documento_id` en `documento_soporte`.

5. **Validación backend (obligatoria en E-97):**
   - Categoría del requisito = `induccion`; `locacion_id` del body = locación de la definición.
   - El soporte pertenece al **mismo sujeto** y tenant (`_exigir_documentos_del_sujeto`).
   - El soporte cumple **tipo de respaldo admitido** (no cualquier documento del legajo).
   - Para **habilitar** (D19): al menos un soporte con `archivo_validacion = valido` (y
     `archivo_estado = confirmado`).
   - **`estado_confirmacion` lo fija el backend**, no el cliente: el front **no** envía
     `verificado` por defecto. Propuesta de regla (implementación): al registrar, si el soporte
     ya tiene `archivo_validacion = valido` → `verificado`; si está `pendiente` o sin archivo →
     `declarado` hasta que el worker valide; si `invalido` → rechazar el registro o dejar
     `declarado` sin habilitar (ver etapa backend).

6. Tras el registro, el responsable ve la inducción en la ficha; el técnico la ve en **Mi legajo**.
   Radar, acciones pendientes y resumen de exigidos se actualizan según D19 y el backlog (E-91).

### Competencia (responsable)

Mismo patrón que inducción, sin `locacion_id`:

1. Faltante exigido de categoría **competencia** en la ficha → **Registrar competencia** (formulario
   a crear; hoy solo existe API).
2. Certificado propio del curso (PDF/imagen), fechas **realización** y **vencimiento** (C1).
3. `registrar_acreditacion_de_competencia` con `evidencias[]` apuntando al documento certificado.
4. Mismas validaciones de tenant/sujeto, tipo de soporte, D19 y **estado decidido en backend**.

## Mientras el worker valida el archivo

**Propuesta (alineada a D19):** la inducción/competencia **registrada** con soporte en
`archivo_validacion = pendiente` (o sin archivo) **no cuenta como en regla** para habilitación:
figura *pendiente de revisión* en motor, Radar y acciones, igual que un documento verificado sin
respaldo válido. Cuando el worker marca el soporte como `valido`, sin nueva acción del usuario el
backend puede **promover** `estado_confirmacion` a `verificado` si aún estaba `declarado` (hook en
worker o job de consistencia — detalle en plan de implementación).

Si el worker marca `invalido`, no habilita; el responsable debe cargar un certificado nuevo y
registrar de nuevo (o sustituir el soporte — fuera de alcance de la primera entrega).

## D1 — ¿Abrir el archivo antes de confirmar?

En renovación (flujo C) el responsable **no puede confirmar** sin abrir el archivo (D1).

**Propuesta para E-97:** el registro de inducción/competencia es **un solo paso** (no hay bandeja
de propuestas). Exigir **vista previa abierta al menos una vez** en el formulario antes de
habilitar **Registrar**, cuando el responsable sube el archivo en esa misma sesión.

**Decisión pendiente del usuario (1):** ¿basta con esa vista previa en el formulario, o debe
existir un segundo paso tipo bandeja (declarado → confirmar tras abrir archivo)?

- **Recomendación:** vista previa obligatoria en el formulario en la misma sesión; sin segunda
  bandeja (menor fricción, mismo espíritu que D1).

## Respaldo = documento ya cargado en el legajo

Hoy el front ofrece **cualquier** documento vigente del legajo como respaldo (`docsRespaldo` =
todos los `data.documentos`).

**Propuesta:** permitir elegir un documento **ya cargado** solo si su `requisito_definicion_id`
está en una lista explícita de **tipos de certificado admitidos** en la definición del requisito
de inducción/competencia (p. ej. metadato en `definicion_requisito` o catálogo de “certificado
de inducción HSE” / “certificado de manejo defensivo”). Nunca apto, ART ni licencia como soporte
de inducción HSE.

**Decisión pendiente del usuario (2):** ¿solo certificado subido en el mismo flujo (sin combo de
legajo), o también reutilizar certificados previos del mismo tipo?

- **Recomendación:** permitir ambos: subida nueva **o** selección de documentos cuyo requisito
  esté en la lista admitida y con archivo `valido`.

**Decisión pendiente del usuario (3):** ¿cómo se declara la lista de tipos admitidos — un
requisito documental “plantilla” por tenant, convención por nombre, o campo nuevo en definición?

- **Recomendación:** campo explícito en definición (p. ej. `requisitos_respaldo_admitidos[]`) para
  no acoplar por nombre libre.

## Terminado cuando

Verificable en pantalla (demo **patagonia-demo**) y por API:

- Como **responsable**, en la ficha de **María González** (`persona_patagonia_demo_t1`): registrar
  la inducción HSE con **certificado propio** (no apto médico), fecha de realización pasada y
  vencimiento válido; comprobar que el legajo pasa el faltante y que Radar/acciones reflejan
  habilitación cuando el soporte está `valido`.
- `POST /v1/comandos/registrar_induccion` **sin** `estado_confirmacion` en el body (o ignorado):
  la respuesta y `GET /v1/consultas/legajo` muestran el estado que asignó el backend.
- `vigente_desde` en la inducción registrada coincide con la fecha de realización ingresada, no con
  «hoy» automático.
- Test API negativo: intentar registrar inducción HSE con `evidencia` = documento de **Apto
  médico** → **422** con código claro (p. ej. `respaldo_tipo_no_admitido`).
- `test_e91_flujo_legajo` actualizado: certificado de prueba con respaldo válido, no `doc_apto`.
- (Competencia) Mismo criterio para **Curso de manejo defensivo** cuando exista formulario.

## Fuera de alcance (esta rama / primera implementación)

- Sustitución de soporte en una inducción ya registrada sin nueva versión.
- Carga masiva de certificados (P4).
- Cambiar en silencio `estado_confirmacion` de datos históricos en producción (solo seed demo y
  nuevas cargas).

---

## Diagnóstico de datos — `fsm_demo`, tenant `patagonia-demo` (solo lectura)

Consulta al **2026-10-05** sobre evidencias vigentes de categoría `induccion` y `competencia`,
con su `documento_soporte` y `archivo_validacion` del soporte.

| Persona (sujeto_id) | Requisito | Categoría | Vigencia | Soporte (requisito) | `archivo_validacion` soporte |
|---------------------|-----------|-----------|----------|---------------------|------------------------------|
| `persona_patagonia_demo_t1` | Manejo defensivo | competencia | 2026-03-18 → 2027-02-01 | Apto médico | `valido` |
| `persona_patagonia_demo_t2` | Manejo defensivo | competencia | 2025-08-30 → 2026-09-19 | Apto médico | `valido` |
| `persona_patagonia_demo_t3` | Manejo defensivo | competencia | 2026-03-18 → 2027-02-01 | Apto médico | `valido` |
| `persona_patagonia_demo_t1` | Inducción HSE de la operadora | inducción | 2026-03-18 → 2027-02-01 | Apto médico | `valido` |

**Notas:**

- **Lucía** (`persona_patagonia_demo_t3`) no tiene inducción vigente en demo (coherente con la
  semilla cuando aplica `copiar_globales`).
- **Juan** (`persona_patagonia_demo_t2`) tiene competencia pero no inducción en estos datos.

### Validez bajo la regla nueva

| Registro | ¿Habilita hoy (D19 archivo)? | ¿Válido con tipo de certificado propio? |
|----------|------------------------------|----------------------------------------|
| Las 4 filas anteriores | Sí (soporte con `valido`) | **No** — el soporte es **Apto médico**, no certificado de inducción/competencia |

**Propuesta para demo (sin tocar `fsm_demo` manual en esta etapa):** en `semilla_tenant.py`, crear
requisitos documentales de certificado (o usar definiciones dedicadas), subir PDF/imagen de
prueba por el mismo camino que el apto (`_subir_y_verificar`), y registrar inducción/competencia
con `evidencias` / `evidencia` apuntando a esos certificados. Opcional: dejar un caso demo de
«pendiente de revisión» con certificado en `archivo_validacion = pendiente`.

---

## Plan por etapas (implementación — sin código en esta etapa)

### Etapa 1 — Backend: validación de respaldo y estado

**Archivos:** `backend/app/modules/legajos/servicio.py`, `esquemas.py` (opcional deprecar
`estado_confirmacion` en body), helper nuevo p. ej. `_exigir_respaldo_registro_induccion_competencia`,
`backend/app/core/resolucion_evidencia.py` (solo si hace falta alinear promoción post-worker),
tests nuevos en `backend/tests/test_e97_respaldo_induccion_competencia.py`.

**Migración:** solo si se agrega campo `requisitos_respaldo_admitidos` (o similar) en
`definicion_requisito`; si la etapa 1 usa lista fija por categoría en código + seed, migración
puede ir en etapa 1b.

**Cierra con:** tests API que registran inducción/competencia con certificado `valido` → legajo
en regla; sin `estado_confirmacion` en request; test negativo apto → `respaldo_tipo_no_admitido`.

### Etapa 2 — Backend: vigencia C1 en registro

**Archivos:** `servicio.py` (`_exigir_vigencia` ampliada o `_exigir_vigencia_registro_certificado`:
`vigente_desde` ≤ hoy; `vigente_hasta` > `vigente_desde`; tope 10 años).

**Migración:** no.

**Cierra con:** tests 422 por `vigente_desde` futura y por `vigente_hasta` incoherente.

### Etapa 3 — Worker / estado tras validación

**Archivos:** hook en worker al pasar soporte a `valido` (promover `declarado` → `verificado` en
la fila inducción/competencia padre si aplica).

**Migración:** no.

**Cierra con:** test de integración: registrar con archivo `pendiente` → no habilita; simular
worker `valido` → habilita.

### Etapa 4 — Front: formulario de inducción

**Archivos:** `frontend/src/features/legajos/RegistrarInduccionForm.tsx`,
`LegajoFicha.tsx`, validación de fechas (reutilizar reglas C1), flujo subida de archivo
(mismo patrón que incorporación/renovación), quitar `estado_confirmacion` y selector libre de
legajo (o filtrar por tipos admitidos).

**Migración:** no.

**Cierra con:** prueba manual en ficha patagonia-demo + contrato OpenAPI regenerado si el schema
marca `estado_confirmacion` como read-only en servidor.

### Etapa 5 — Front: formulario de competencia

**Archivos:** nuevo `RegistrarCompetenciaForm.tsx`, cable en `LegajoFicha.tsx` para
`gestion_responsable === 'registrar_acreditacion'`.

**Migración:** no.

**Cierra con:** registro de manejo defensivo con certificado en demo.

**¿Va en la misma rama `fix/app-e97-respaldo-induccion`?** **Sí, recomendado en la rama de
implementación** después de este documento: comparte validación backend, D19 y UX de fechas/archivo;
dejar solo API sin formulario dejaría al responsable sin cerrar faltantes de competencia en UI.
Si el alcance se acota por tiempo, **mínimo entregable:** etapas 1–2 + inducción (etapa 4);
competencia (etapa 5) como PR seguido en la misma rama antes de merge.

### Etapa 6 — Tests y semilla

**Archivos:** `backend/tests/test_e91_flujo_legajo.py` (certificado en lugar de `doc_apto`),
`backend/scripts/demo/semilla_tenant.py`, `config.py` (definiciones de certificado),
`backend/docs/flujos/FLUJO_C_RENOVACION.md` (quitar ítem E-97 de pendientes al cerrar).

**Migración:** no (solo datos demo al re-sembrar).

**Cierra con:** `pytest test_e91_flujo_legajo.py test_e97_*` y re-sembrado demo documentado.

---

## Decisiones pendientes para el usuario (resumen)

1. **D1 en registro único:** ¿vista previa obligatoria en formulario o bandeja de confirmación?
   → **Recomendación:** vista previa en formulario.
2. **Reutilizar documentos del legajo como soporte:** ¿sí, filtrado por tipo admitido, o solo
   subida en el flujo? → **Recomendación:** ambos, filtrados.
3. **Modelado de tipos admitidos:** ¿campo en definición u otra convención? → **Recomendación:**
   campo explícito en `definicion_requisito`.
4. **Supuesto certificado propio con fechas en el PDF:** confirmar con el cliente (marcado arriba).
