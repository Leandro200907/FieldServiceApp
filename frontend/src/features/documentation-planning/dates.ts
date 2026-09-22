// Funciones puras de fecha para el calendario documental — separadas del componente para
// poder testearlas sin renderizar React (F-01/F-03, auditoría externa 2026-09-22).

// F-03: `Date.toISOString()` siempre da la fecha en UTC. Entre las 21:00 y las 00:00 de
// un tenant al oeste de UTC (Argentina, UTC-3), el "hoy" en UTC ya es el día siguiente —
// el front pedía un rango un día adelantado al `hoy` real que devuelve el backend
// (`hoy_del_tenant`, con la zona configurada del tenant). Se usa la fecha LOCAL del
// dispositivo (no UTC, tampoco una zona IANA hardcodeada: la zona del tenant es
// configurable server-side, así que asumir una fija acá reintroduce el mismo problema
// con otro nombre) — en un deployment real, quien opera está físicamente en la zona del
// tenant, así que la fecha local del dispositivo coincide con la del tenant.
export function todayIso(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

// F-01: posición proporcional de UNA fecha dentro de `[from, to]`, en porcentaje —
// misma fórmula que ya usaba `trackPosition` para los tramos de evidencia, generalizada
// para poder ubicar también la marca de "hoy" (antes fija al 40%, resto de un rango
// viejo del mock que ya no corresponde: con `from` siempre igual a hoy, hoy tiene que
// estar en 0%, nunca en un valor fijo). Recortada a [0, 100] — una fecha fuera del rango
// pedido no debe dibujar la marca fuera del track.
export function dayPosition(iso: string, from: string, to: string): number {
  const start = new Date(`${from}T00:00:00Z`).getTime();
  const end = new Date(`${to}T00:00:00Z`).getTime();
  const span = Math.max(end - start, 1);
  const point = new Date(`${iso}T00:00:00Z`).getTime();
  const pct = ((point - start) / span) * 100;
  return Math.min(Math.max(pct, 0), 100);
}
