# FLUJO E-97 — Respaldo de inducción y competencia

Decisiones de referencia: **D1**, **D19**, **C1** (validación de fechas de vigencia, en «Convenciones transversales»),
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
   (`vigente_desde`, no futura) y **vencimiento** (`vigente_hasta`: no anterior a `vigente_desde`,
   tope **C1** `propuesta_max_anios_vigencia` = 10 años desde hoy del tenant).
4. **API (etapa 1 backend):** `crear_certificado_respaldo` → subida estándar de evidencia →
   `registrar_induccion` con `certificado_documento_id` (no `evidencia` de legajo).
5. El backend valida sujeto/tenant, que el certificado sea `origen = certificado_respaldo`, archivo
   confirmado, no reutilizado, y aplica **C1** en vigencias. **`estado_confirmacion` lo decide el
   backend** (`declarado` si el archivo sigue `pendiente`; `verificado` si ya es `valido`; tras
   validar el worker, promoción automática del registro padre). En ambos casos de `verificado`
   se emite `DocumentoVerificado`; en la promoción el actor es `sistema` y el payload lleva
   `promovido_por = validacion_evidencia_worker` (E-107).
6. **D1 (front, etapa posterior):** no habilitar **Registrar** hasta abrir la vista previa del
   archivo subido en la sesión.

### Competencia (responsable)

Igual que inducción, sin `locacion_id`, con `registrar_acreditacion_de_competencia` y formulario
en la misma rama.

## Mientras el worker valida el archivo

Alineado a **D19:** con `archivo_validacion = pendiente` en el certificado, el registro padre queda
`declarado` y **no cuenta como en regla**. Cuando el worker marca el certificado `valido`, el
backend promueve el padre a `verificado` si el enlace es `es_certificado_propio` y emite
`DocumentoVerificado` con actor `sistema` (E-107, `certificado_respaldo.py::promover_padres_si_certificado_valido`),
que dispara la política de revaluación. Si el worker marca el certificado `invalido`, el padre
queda `declarado` y hoy no se notifica (pendiente; ver §25 en `DECISIONES_DOMINIO.md`).

## Terminado cuando

- [x] Registro con certificado nuevo por API; negativo con apto médico → `respaldo_tipo_no_admitido`. **(cumplido 2026-10-05)**
- [x] Lectura: inducción/competencia con soporte que no es certificado propio → no en regla / sin respaldo válido (D19). **(cumplido 2026-10-05)**
- [x] Tests API y lectura (`test_e97_*`, `test_e91_flujo_legajo`, ficha E-101). **(cumplido 2026-10-05)**
- [x] Front: formularios inducción + competencia con subida, fechas C1 y D1 (vista previa). **(cumplido 2026-10-05)**
- [x] Semilla demo: certificados propios (María/Juan/Lucía manejo defensivo; María inducción; Lucía **sin** inducción E-91); CI `modulo1_ci_demo`. **(cumplido 2026-10-05)**
- [ ] **Supuesto de negocio (certificado propio con fechas de realización/vencimiento en el archivo) a confirmar con el cliente.** Sigue pendiente de validación comercial; la implementación ya exige certificado propio y vigencias C1 en API.

## Fuera de alcance

- Elegir documentos del legajo como respaldo.
- Sustituir soporte sin nueva versión del registro.
- Carga masiva (P4).

---

## Diagnóstico de datos — semilla demo (referencia post E-97, 2026-10-05)

| Persona | Requisito | Soporte en semilla |
|---------|-----------|-------------------|
| María (t1) | Manejo defensivo / Inducción HSE | Certificado propio (`certificado_respaldo`, `es_certificado_propio`, archivo válido) |
| Juan (t2) | Manejo defensivo | Certificado propio |
| Lucía (t3) | Manejo defensivo | Certificado propio; **sin** inducción registrada (caso E-91 en demo) |

El apto médico de María rechazado por Vista en el flujo operadora **no** se usa como soporte de inducción/competencia.

---

## Plan por etapas

### Etapa 1 — Backend **(cerrada 2026-10-05)**

**Archivos:** migración `0033_certificado_respaldo`, `legajos/servicio.py`, `esquemas.py`,
`router.py`, `resolucion_evidencia.py`, consultas que cargan soportes (`orquestacion.py`,
`radar.py`, `paquete/servicio.py`), `evidencia/servicio.py` (promoción post-validación),
`tests/test_e97_*`, `tests/test_e91_flujo_legajo.py`, ajustes en tests que usaban `evidencia`/`evidencias`.

**Cierra con:** tests API + lectura D19; sin front ni semilla. **Hecho.**

### Etapa 2 — Front: inducción + competencia **(cerrada 2026-10-05)**

`RegistrarInduccionForm`, `RegistrarCompetenciaForm`, subida, fechas C1, D1 vista previa, sin
`estado_confirmacion` ni selector de legajo. **Hecho.**

### Etapa 3 — Semilla demo y cierre doc **(cerrada 2026-10-05)**

`semilla_tenant.py`, CI demo; pendiente de negocio: supuesto de fechas en certificado (ver arriba).
