import { StatusDot, type StatusVariant } from './StatusDot';

type RefItem = { label: string; variant: StatusVariant; hint: string };

const estadosLegajo: RefItem[] = [
  { label: 'Vencido', variant: 'vencido', hint: 'la evidencia no cubre el período o ya expiró.' },
  { label: 'Por vencer / Vence durante la OC', variant: 'por_vencer', hint: 'vigente hoy pero expira antes o durante una orden de compra observada.' },
  { label: 'En revisión / Propuesta en revisión', variant: 'revision', hint: 'hay una propuesta o archivo pendiente de confirmación.' },
  { label: 'Vigente / Verificada', variant: 'vigente', hint: 'cumple fechas y respaldo según la evaluación actual.' },
  { label: 'Sin respaldo / Evidencia inválida', variant: 'sin_respaldo', hint: 'falta archivo o el respaldo no es válido.' },
];

const estadosPresentacion: RefItem[] = [
  { label: 'Pendiente de envío', variant: 'revision', hint: 'aún no se registró ante la operadora.' },
  { label: 'Pendiente de aceptación', variant: 'por_vencer', hint: 'enviado, esperando respuesta de la operadora.' },
  { label: 'Rechazado', variant: 'vencido', hint: 'la operadora no aceptó la presentación.' },
  { label: 'Al día', variant: 'vigente', hint: 'presentación aceptada y alineada con el legajo.' },
];

function ListaReferencia({ items }: { items: RefItem[] }) {
  return (
    <ul className="estado-referencia-list">
      {items.map(item => (
        <li key={item.label}>
          <StatusDot variant={item.variant}>{item.label}</StatusDot>
          <span className="muted"> — {item.hint}</span>
        </li>
      ))}
    </ul>
  );
}

export function EstadoReferenciaLegajo({ incluirPresentaciones = false }: { incluirPresentaciones?: boolean }) {
  return (
    <details className="estado-referencia">
      <summary>Referencia de estados</summary>
      <ListaReferencia items={estadosLegajo} />
      {incluirPresentaciones && (
        <>
          <p className="eyebrow" style={{ marginTop: 12 }}>Estados ante operadora</p>
          <ListaReferencia items={estadosPresentacion} />
        </>
      )}
    </details>
  );
}
