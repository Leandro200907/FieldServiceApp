import { useId, useState } from 'react';
import type { ReactNode } from 'react';

export function Badge({ children, tone = 'neutral' }: { children: ReactNode; tone?: 'neutral' | 'warning' | 'accent' }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}
export function Pending({ title = 'Esta vista todavía no está disponible', children }: { title?: string; children?: ReactNode }) {
  return <div className="state state-pending"><span className="state-symbol" aria-hidden="true">◷</span><div><h3>{title}</h3><p>{children || 'La integración se habilitará cuando las consultas y los permisos estén confirmados.'}</p></div></div>;
}
export function LoadingState() {
  return <div className="state" role="status" aria-busy="true"><div><h3>Cargando información</h3><p>Esperando la respuesta del servidor.</p><div className="skeleton" /><div className="skeleton skeleton-short" /></div></div>;
}
export function EmptyState() {
  return <div className="state"><div><h3>No hay resultados para estos filtros</h3><p>Este estado se utiliza únicamente después de una respuesta válida que confirme una lista vacía.</p></div></div>;
}
export function ErrorState({ message, requestId, onRetry }: { message: string; requestId?: string | null; onRetry?: () => void }) {
  const [copied, setCopied] = useState(false);
  return <div className="state state-error" role="alert"><div><h3>No pudimos completar la solicitud</h3><p>{message}</p>{requestId && <p className="request-id">Referencia: <code>{requestId}</code></p>}<div className="actions">{requestId && <button className="button button-secondary" onClick={async () => { try { await navigator.clipboard.writeText(requestId); setCopied(true); } catch { setCopied(false); } }}>{copied ? 'Referencia copiada' : 'Copiar referencia'}</button>}{onRetry && <button className="button button-secondary" onClick={onRetry}>Reintentar lectura</button>}</div></div></div>;
}
export function BlockedSelector({ label, dependency }: { label: string; dependency: string }) {
  const id = useId();
  return <div className="form-field"><label htmlFor={id}>{label}</label><select id={id} disabled aria-describedby={`${id}-help`}><option>Selección no disponible</option></select><small id={`${id}-help`}>{dependency}. Sin ingreso manual de identificadores.</small></div>;
}
