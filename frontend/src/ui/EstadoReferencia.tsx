export function EstadoReferenciaLegajo() {
  return (
    <details className="estado-referencia">
      <summary>Referencia de estados</summary>
      <ul>
        <li><strong>Vencido</strong> — la evidencia no cubre el período o ya expiró.</li>
        <li><strong>Por vencer / Vence durante la OC</strong> — vigente hoy pero expira antes o durante una orden de compra observada.</li>
        <li><strong>En revisión / Propuesta en revisión</strong> — hay una propuesta o archivo pendiente de confirmación.</li>
        <li><strong>Vigente / Verificada</strong> — cumple fechas y respaldo según la evaluación actual.</li>
        <li><strong>Sin respaldo / Evidencia inválida</strong> — falta archivo o el respaldo no es válido.</li>
      </ul>
    </details>
  );
}
