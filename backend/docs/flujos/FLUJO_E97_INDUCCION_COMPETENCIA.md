# FLUJO E-97 — Respaldo de inducción y competencia

Decisiones de referencia: **D1**, **D19**, **C1** (reglas de vigencia de incorporación/carga),
**regla general: el frontend no calcula estados** (ver `backend/docs/DECISIONES_DOMINIO.md`).

**Supuesto de negocio (a confirmar con el cliente):** la inducción y la competencia se acreditan
con un **certificado propio** (PDF o imagen) emitido por el curso u operadora, con **fecha de
realización** y, si aplica, **fecha de vencimiento** en el certificado. Ese archivo no es
intercambiable por otro requisito del legajo (apto, ART, licencia).

## Decisiones cerradas (usuario, E-97)

1. **D1:** vista previa del archivo en el formulario, obligatoria antes de **Registrar** (sin
   bandeja de confirmación aparte).
2. **Respaldo:** **solo** archivo **nuevo** subido en el mismo formulario. **No** se puede elegir
   un documento ya cargado en el legajo. Los comandos `registrar_induccion` y
   `registrar_acreditacion_de_competencia` **no** aceptan un `documento_id` arbitrario del legajo.
3. **Sin** lista de tipos admitidos en `definicion_requisito` (no hay combo de legajo).
4. El supuesto de certificado propio con fechas permanece **a confirmar con el cliente**.
5. El **formulario de competencia** entra en **esta misma rama** (junto con inducción).
6. La regla aplica al **leer** (D19 / `respaldo_valido`): un soporte que no sea certificado
   propio del flujo E-97 **no habilita**, aunque tenga `archivo_validacion = valido`.

### Marca «certificado propio» (implementación)

- Documento del archivo: `modulo1.documento.origen = 'certificado_respaldo'`, sin
  `requisito_definicion_id` (no es un requisito de legajo).
- Enlace al registro: `modulo1.documento_soporte.es_certificado_propio = true` (migración **0033**).
- Creación del shell: `POST /v1/comandos/crear_certificado_respaldo` → subida con
  `preparar_subida_de_evidencia` / `PUT /storage/{firma}` / `confirmar_subida_de_evidencia` →
  registro con `certificado_documento_id`.
- Soportes históricos (p. ej. apto médico enlazado en la semilla) tienen
  `es_certificado_propio = false` y **no cuentan** para D19.

## Roles

| Acción | Inducción | Competencia |
|--------|-----------|-------------|
| Ver faltante en ficha / Mi legajo | Técnico y responsable | Técnico y responsable |
| Subir certificado y fechas | **Responsable** (ficha del legajo) | **Responsable** |
| Registrar la evidencia en el sistema | **Responsable** | Igual |
| Incorporar / renovar documentos “de legajo” | Técnico (flujos C / incorporación) | No aplica |

## Recorrido de punta a punta

### Inducción (responsable)

1. Ficha del legajo → faltante exigido de **inducción** → **Registrar inducción**.
2. **Locación / operadora** en solo lectura (`locacion_id` de la definición).
3. El responsable sube el **certificado** (PDF/imagen) y completa **fecha de realización**
   (`vigente_desde`, no futura) y **vencimiento** (`vigente_hasta`: posterior a `vigente_desde`,
   tope **C1** ~10 años desde hoy del tenant).
4. **API (etapa 1 backend):** `crear_certificado_respaldo` → subida estándar de evidencia →
   `registrar_induccion` con `certificado_documento_id` (no `evidencia` de legajo).
5. El backend valida sujeto/tenant, que el certificado sea `origen = certificado_respaldo`, archivo
   confirmado, no reutilizado, y aplica **C1** en vigencias. **`estado_confirmacion` lo decide el
   backend** (`declarado` si el archivo sigue `pendiente`; `verificado` si ya es `valido`; tras
   validar el worker, promoción automática del registro padre).
6. **D1 (front, etapa posterior):** no habilitar **Registrar** hasta abrir la vista previa del
   archivo subido en la sesión.

### Competencia (responsable)

Igual que inducción, sin `locacion_id`, con `registrar_acreditacion_de_competencia` y formulario
en la misma rama.

## Mientras el worker valida el archivo

Alineado a **D19:** con `archivo_validacion = pendiente` en el certificado, el registro padre queda
`declarado` y **no cuenta como en regla**. Cuando el worker marca el certificado `valido`, el
backend promueve el padre a `verificado` si el enlace es `es_certificado_propio`.

## Terminado cuando

- Registro con certificado nuevo por API; negativo con apto médico → `respaldo_tipo_no_admitido`.
- Lectura: inducción vieja con soporte apto → no en regla / pendiente de revisión por respaldo.
- `test_e91_flujo_legajo` y demo (semilla, etapa posterior) alineados al flujo nuevo.
- Front: formularios inducción + competencia con subida, fechas y D1.

## Fuera de alcance

- Elegir documentos del legajo como respaldo.
- Sustituir soporte sin nueva versión del registro.
- Carga masiva (P4).

---

## Diagnóstico de datos — `fsm_demo`, tenant `patagonia-demo` (solo lectura, 2026-10-05)

| Persona | Requisito | Soporte actual | Con regla E-97 |
|---------|-----------|----------------|----------------|
| t1 | Manejo defensivo / Inducción HSE | Apto médico | **No habilita** (no certificado propio) |
| t2, t3 | Manejo defensivo | Apto médico | **No habilita** |

**Semilla (etapa posterior):** certificados propios por `crear_certificado_respaldo` + registro.

---

## Plan por etapas

### Etapa 1 — Backend (en curso)

**Archivos:** migración `0033_certificado_respaldo`, `legajos/servicio.py`, `esquemas.py`,
`router.py`, `resolucion_evidencia.py`, consultas que cargan soportes (`orquestacion.py`,
`radar.py`, `paquete/servicio.py`), `evidencia/servicio.py` (promoción post-validación),
`tests/test_e97_*`, `tests/test_e91_flujo_legajo.py`, ajustes en tests que usaban `evidencia`/`evidencias`.

**Cierra con:** tests API + lectura D19; sin front ni semilla.

### Etapa 2 — Front: inducción + competencia

`RegistrarInduccionForm`, `RegistrarCompetenciaForm`, subida, fechas C1, D1 vista previa, sin
`estado_confirmacion` ni selector de legajo.

### Etapa 3 — Semilla demo y cierre doc

`semilla_tenant.py`, re-sembrado `patagonia-demo`, actualizar pendiente E-97 en `FLUJO_C_RENOVACION.md`.
