import type { LegajoCompuesto } from '../mi-legajo/contracts';
import { todosLosDocumentos } from './legajoResumen';

export function textoObservadosOperadora(data: LegajoCompuesto): string | null {
  const n = data.resumen.observados_operadora ?? 0;
  if (n <= 0) return null;
  const fila = todosLosDocumentos(data).find(
    i => (i as { observacion_operadora?: string }).observacion_operadora?.startsWith('Rechazado por '),
  );
  const raw = (fila as { observacion_operadora?: string } | undefined)?.observacion_operadora;
  const operadora = raw?.replace('Rechazado por ', '').split(' el ')[0]?.trim();
  const base = `${n} observado${n === 1 ? '' : 's'}`;
  return operadora ? `${base} ante ${operadora}` : base;
}

export function textoCumplimientoExigidos(data: LegajoCompuesto): string {
  const exigidos = data.resumen.exigidos ?? data.resumen.total;
  const enRegla = data.resumen.en_regla_exigidos ?? data.resumen.en_regla ?? 0;
  const obs = textoObservadosOperadora(data);
  const core = `${enRegla} de ${exigidos} en regla`;
  return obs ? `${core} · ${obs}` : core;
}
