import type { components } from '../../api/generated/modulo1';
import { formatFecha } from './dates';

type Disponibilidad = components['schemas']['DisponibilidadTipoOc'];
type Alerta = components['schemas']['AlertaCiertaOc'];

type Persona = { nombre?: string; fecha?: string; requisito?: string };
type Impacto = { tipo_sujeto?: string; dias_sin_habilitados?: number; tramos?: { desde?: string; hasta?: string }[] };

function nombres(items: { nombre?: unknown }[]): string {
  return items.map(i => String(i.nombre || '')).filter(Boolean).join(', ');
}

export function lineasDisponibilidad(d: Disponibilidad, timeZone: string): string[] {
  const lineas: string[] = [];
  const hab = d.habilitados_toda_ventana as Persona[];
  const cae = d.se_cae_en_ventana as Persona[];
  const no = d.no_habilitados as Persona[];
  if (hab.length) lineas.push(`habilitados toda la ventana: ${nombres(hab)}`);
  for (const s of cae) {
    const cuando = s.fecha ? ` el ${formatFecha(s.fecha, timeZone)}` : '';
    const req = s.requisito || 'requisito';
    lineas.push(`se cae${cuando} por ${req}${s.nombre ? ` (${s.nombre})` : ''}`);
  }
  if (no.length) lineas.push(`no habilitados: ${nombres(no)}`);
  if (d.texto.toLowerCase().includes('fuera de tu alcance')) {
    const extra = d.texto.toLowerCase().includes('hay recursos habilitados')
      ? 'hay recursos habilitados fuera de tu alcance'
      : d.texto.replace(`${d.etiqueta}: `, '');
    if (!lineas.some(l => l.toLowerCase().includes('fuera de tu alcance'))) lineas.push(extra);
  }
  return lineas;
}

export function textoAlertaCierta(alerta: Alerta, impactos: Impacto[], timeZone: string): string {
  const tramos = (alerta.tramos as { desde?: string; hasta?: string }[] | undefined)
    || (alerta.desde && alerta.hasta ? [{ desde: alerta.desde, hasta: alerta.hasta }] : []);
  const tramoTxt = tramos
    .filter(t => t.desde && t.hasta)
    .map(t => `${formatFecha(t.desde!, timeZone)} al ${formatFecha(t.hasta!, timeZone)}`)
    .join(', ');
  const imp = impactos.find(i => i.tipo_sujeto === alerta.tipo_sujeto);
  const etiqueta = alerta.tipo_sujeto === 'persona' ? 'Personas'
    : alerta.tipo_sujeto === 'vehiculo' ? 'Vehículos'
    : alerta.tipo_sujeto === 'equipo' ? 'Equipos'
    : alerta.tipo_sujeto === 'empresa' ? 'Empresa'
    : alerta.mensaje;
  if (imp?.dias_sin_habilitados && tramoTxt) {
    return `${etiqueta}: ${imp.dias_sin_habilitados} días sin ningún habilitado, ${tramoTxt}`;
  }
  return tramoTxt ? `${alerta.mensaje} (${tramoTxt})` : alerta.mensaje;
}

export function textoHistorial(h: { fecha?: unknown; origen?: unknown; motivo?: unknown }, timeZone: string): string {
  const fecha = typeof h.fecha === 'string' && h.fecha ? formatFecha(h.fecha, timeZone) : '';
  const origen = typeof h.origen === 'string' ? h.origen : '';
  const motivo = typeof h.motivo === 'string' && h.motivo ? h.motivo : '—';
  return [fecha, origen, motivo].filter(Boolean).join(' · ');
}
