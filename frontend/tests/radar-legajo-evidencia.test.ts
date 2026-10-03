import { describe, expect, it } from 'vitest';
import {
  etiquetaEstadoRequisitoRadar,
  motivoFalloRequisitoRadar,
  requisitosRadarVisibles,
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

  it('aplica precedencia de estados del motor documental', () => {
    expect(etiquetaEstadoRequisitoRadar({ estado: 'vence_durante_periodo', archivo_validacion: 'valido' })).toBe('Vencido');
    expect(etiquetaEstadoRequisitoRadar({ estado: 'pendiente_revision', archivo_validacion: 'sin_archivo' })).toBe('Sin respaldo');
    expect(etiquetaEstadoRequisitoRadar({ estado: 'pendiente_revision', archivo_validacion: 'pendiente' })).toBe('En revisión');
    expect(etiquetaEstadoRequisitoRadar({ estado: 'vigente_todo_el_periodo', archivo_validacion: 'valido' })).toBe('Vigente');
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
