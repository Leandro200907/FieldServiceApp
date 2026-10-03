import type { ReactNode } from 'react';

export type StatusVariant = 'vencido' | 'por_vencer' | 'revision' | 'vigente' | 'sin_respaldo' | 'neutral';

const variantClass: Record<StatusVariant, string> = {
  vencido: 'status-dot-vencido',
  por_vencer: 'status-dot-por-vencer',
  revision: 'status-dot-revision',
  vigente: 'status-dot-vigente',
  sin_respaldo: 'status-dot-sin-respaldo',
  neutral: 'status-dot-neutral',
};

export function StatusDot({ variant, children }: { variant: StatusVariant; children: ReactNode }) {
  return (
    <span className={`status-dot ${variantClass[variant]}`}>
      <span className="status-dot-mark" aria-hidden="true" />
      <span className="status-dot-label">{children}</span>
    </span>
  );
}

export function variantFromEtiquetaVigencia(label: string): StatusVariant {
  const n = label.toLowerCase();
  if (n.includes('vencid')) return 'vencido';
  if (n.includes('por vencer') || n.includes('vence durante')) return 'por_vencer';
  if (n.includes('revisión') || n.includes('revision') || n.includes('propuesta')) return 'revision';
  if (n.includes('sin respaldo') || n.includes('inválid')) return 'sin_respaldo';
  if (n.includes('vigente') || n.includes('verificada') || n.includes('en regla')) return 'vigente';
  return 'neutral';
}
