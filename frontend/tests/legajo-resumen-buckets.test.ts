import { describe, expect, it } from 'vitest';
import { contarBuckets, resumenExigidosTexto } from '../src/features/legajos/legajoResumen';
import type { EvidenciaVigente } from '../src/features/mi-legajo/contracts';

function fila(partial: Partial<EvidenciaVigente> & Pick<EvidenciaVigente, 'estado_presentacion'>): EvidenciaVigente {
  return {
    tipo: 'documento',
    id: 'doc-1',
    sujeto_id: 'persona_patagonia_demo_t1',
    requisito_definicion_id: 'req-1',
    requisito: 'Licencia de conducir',
    categoria: 'documento',
    vigente_desde: '2025-01-01',
    vigente_hasta: '2026-11-15',
    estado_confirmacion: 'verificado',
    origen_propuesta: false,
    locacion_id: null,
    vigente_hoy: true,
    dias_para_vencer: 30,
    vencido: false,
    estado_presentacion_explicacion: '',
    ...partial,
  } as EvidenciaVigente;
}

describe('resumenExigidosTexto (E-96)', () => {
  it('Lucía: 1 sin documento', () => {
    expect(resumenExigidosTexto({ exigidos_sin_documento: 1, exigidos_vencidos: 0, exigidos_por_vencer: 0 })).toBe(
      '1 sin documento',
    );
  });

  it('María: sin pendientes de calendario ni faltantes', () => {
    expect(resumenExigidosTexto({ exigidos_sin_documento: 0, exigidos_vencidos: 0, exigidos_por_vencer: 0 })).toBe(
      'Sin pendientes',
    );
  });
});

describe('contarBuckets (E-6: tarjetas por fecha, revisión aparte)', () => {
  it('María: licencia por vencer con propuesta en revisión sigue en «Por vencer»', () => {
    const lic = fila({
      estado_presentacion: 'por_vencer',
      propuesta_en_revision: {
        documento_id: 'prop-1',
        vigente_desde: '2026-10-01',
        vigente_hasta: '2027-10-01',
        estado_presentacion: 'propuesta_en_revision',
        estado_presentacion_explicacion: '',
      },
    });
    const buckets = contarBuckets([lic]);
    expect(buckets.por_vencer).toBe(1);
    expect(buckets.en_revision).toBe(0);
  });

  it('Juan: vencida con archivo en revisión cuenta en «Vencidos»', () => {
    const lic = fila({
      sujeto_id: 'persona_patagonia_demo_t2',
      estado_presentacion: 'vencida',
      vencido: true,
      dias_para_vencer: -10,
      estados_adicionales: ['archivo_en_revision'],
      propuesta_en_revision: {
        documento_id: 'prop-2',
        vigente_desde: '2026-08-01',
        vigente_hasta: '2027-08-01',
        estado_presentacion: 'propuesta_en_revision',
        estado_presentacion_explicacion: '',
      },
    });
    const buckets = contarBuckets([lic]);
    expect(buckets.vencidos).toBe(1);
    expect(buckets.en_revision).toBe(0);
  });
});
