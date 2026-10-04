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
