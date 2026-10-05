# FLUJO C — Renovación de un documento

Decisiones de referencia: **D1**, **D3**, **D17**, **D19**, **E-20** (ver `backend/docs/DECISIONES_DOMINIO.md`).

## Recorrido de punta a punta

1. El técnico ve en **Mi legajo** que un documento vence (por ejemplo, una licencia que vence en 20 días) y toca **Renovar** en **ese** documento. El requisito viene **preseleccionado** (D17): no lo elige de una lista.

2. Carga la foto o archivo del documento nuevo y la **fecha de vencimiento**. Validaciones en la app: archivo obligatorio; formato válido (imagen o PDF); fecha de vencimiento futura y **posterior a la vigente**. Envía.

3. La carga queda como **PROPUESTA** (`estado_version = 'propuesta'`, E-20). El técnico ve en su legajo *Renovación enviada · en revisión*. El documento vigente **sigue vigente**.

4. El responsable entra y su pantalla de inicio es la **Bandeja de revisión** (D3), ordenada de la más antigua a la más nueva.

5. Abre una propuesta: ve el **archivo** al lado de los datos (D1), la comparación **vigente vs. propuesta** (desde, hasta, cargado por) y las **OC que afecta**. No puede confirmar sin haber abierto el archivo.

6. **Decisión del responsable**
   - **6a. CONFIRMA** → la propuesta pasa a vigente (verificada), la anterior a sucedida; se recalculan legajo, Radar, Acciones pendientes y Línea de tiempo; el técnico ve *Renovación aprobada*.
   - **6b. RECHAZA** con motivo **obligatorio** → el técnico ve el motivo en su legajo y puede volver a enviar (la nueva propuesta reemplaza a la rechazada según E-20).

7. **Confirmar y seguir** / **Siguiente** lleva a la próxima propuesta de la bandeja sin volver a la lista.

## Terminado cuando

Verificable en pantalla con datos demo:

- Como **María González** (`tecnico1`): renovar la licencia con un archivo y una fecha.
- Como **responsable**: verla en la bandeja, abrir el archivo, confirmar, y comprobar que Radar y Acciones pendientes cambian solos.
- Como **Juan Pérez** (`tecnico2`): renovar; como responsable: rechazar con motivo; como Juan: ver el motivo.

## Fuera de alcance

- Detección de conflictos de OC (D5).
- Carga masiva (P4).
- Notificaciones por mail.

## Pulido pendiente (no implementado en esta ronda)

- **E-92:** Si la propuesta no tiene archivo adjunto, ocultar el recuadro de vista previa (hoy muestra el texto genérico «La vista previa aparece acá después de ver el archivo»).

## E-91 (implementado — ver PR #13 y D23 / «Ficha de legajo: tarjetas vs cumplimiento»)

La **ficha del legajo** y **Mi legajo** fusionan evidencia cargada con **requisitos exigidos**
por el backlog (misma ventana que Radar). Faltantes de documento, inducción o competencia se
listan; Incorporar solo para documento; inducción/competencia las registra el responsable.
Tarjetas y resumen de exigidos según decisión de dominio (calendario del papel vs cumplimiento
del backlog).

## Pendientes (no implementados)

- **E-97 (grave):** `registrar_induccion` / `registrar_acreditacion_de_competencia` aceptan como
  respaldo **cualquier** `documento_id` del mismo sujeto; el front envía `estado_confirmacion:
  "verificado"` fijo y `vigente_desde = hoy` sin validar D19 ni tipo de evidencia. Corregir en
  rama propia (backend + formulario). El test `test_e91_flujo_legajo` usa `doc_apto` como
  respaldo de inducción y debe alinearse en E-97.
- **E-99:** documento **rechazado por operadora** sin acción de gestión en la ficha (ej. apto
  vigente rechazado por Vista). Pendiente de definir con negocio (regularizar / reenvío / solo
  observación).
