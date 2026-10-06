import { describe, expect, it } from 'vitest';
import {
  etiquetaEstadoRequisitoRadar,
  motivoFalloRequisitoRadar,
  requisitosRadarVisibles,
  textoSinCoberturaRequisitoRadar,
  tituloLegajoRadar,
} from '../src/features/documentation-planning/radarLegajoPresentation';
import { temporaryMockAccess } from '../src/features/documentation-planning/temporaryMockAccess';

describe('radar legajo evidencia', () => {
  it('arma título con nombre y DNI', () => {
    expect(tituloLegajoRadar({
      tipo_sujeto: 'persona',
      nombre_apellido: 'María González',
      identificador_natural: '30.111.222',
    })).toBe('María González · DNI 30.111.222');
  });

  it('traduce el código de estado del motor a etiqueta visible', () => {
    expect(etiquetaEstadoRequisitoRadar({ estado: 'pendiente_revision' })).toBe('En revisión');
    expect(etiquetaEstadoRequisitoRadar({ estado: 'evidencia_invalida' })).toBe('Sin respaldo');
    expect(etiquetaEstadoRequisitoRadar({ estado: 'vigente_todo_el_periodo' })).toBe('Vigente');
  });

  it('Constancia ART vencida con evidencia inválida muestra Vencido (D19)', () => {
    expect(etiquetaEstadoRequisitoRadar({
      estado: 'vencido_antes_inicio',
    })).toBe('Vencido');
    expect(motivoFalloRequisitoRadar({
      estado: 'vencido_antes_inicio',
      motivo: 'Constancia ART está vencido antes del inicio del período',
    })).toContain('vencido antes del inicio');
  });

  it('describe el período sin cobertura para vence_durante_periodo', () => {
    const format = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
    expect(textoSinCoberturaRequisitoRadar({
      estado: 'vence_durante_periodo',
      primer_quiebre: '2026-10-24',
    }, '2026-11-02', format)).toBe('Sin cobertura del 24/10/2026 al 02/11/2026 (10 días)');
    expect(textoSinCoberturaRequisitoRadar({
      estado: 'vencido_antes_inicio',
      primer_quiebre: '2026-10-24',
    }, '2026-11-02', format)).toBeNull();
  });

  it('licencia que vence durante la OC no se etiqueta como Vencido', () => {
    expect(etiquetaEstadoRequisitoRadar({
      estado: 'vence_durante_periodo',
    })).toBe('Vence durante la OC');
    expect(motivoFalloRequisitoRadar({
      estado: 'vence_durante_periodo',
      vigente_hasta: '2026-10-23',
      motivo: 'Licencia de conducir deja un período sin cobertura documental',
    })).toContain('sin cobertura documental');
  });

  it('expone motivo solo cuando el requisito no está vigente', () => {
    expect(motivoFalloRequisitoRadar({
      estado: 'vigente_todo_el_periodo',
      motivo: 'Cubierto',
      archivo_validacion: 'valido',
    })).toBeNull();
    expect(motivoFalloRequisitoRadar({
      estado: 'faltante',
      motivo: 'No existe evidencia vigente',
      archivo_validacion: null,
    })).toBe('No existe evidencia vigente');
  });

  it('el mock de radar legajo trae requisitos evaluados con estado y motivo', async () => {
    const radar = await temporaryMockAccess.readRadarBacklog({ estado: ['con_alertas_documentales'] });
    const legajo = await temporaryMockAccess.readRadarLegajo({
      ocId: radar.items[0].oc_id,
      sujetoId: 'persona-marina',
    });
    const requisitos = requisitosRadarVisibles(
      (legajo.legajo.requisitos as { estado?: string; motivo?: string; requerido?: boolean }[]) ?? [],
    );
    expect(requisitos.length).toBeGreaterThanOrEqual(4);
    expect(requisitos.every(r => r.estado && r.motivo)).toBe(true);
    expect(tituloLegajoRadar(legajo.legajo as Parameters<typeof tituloLegajoRadar>[0])).toContain('María González');
    expect(tituloLegajoRadar(legajo.legajo as Parameters<typeof tituloLegajoRadar>[0])).toContain('30.111.222');
  });
});
