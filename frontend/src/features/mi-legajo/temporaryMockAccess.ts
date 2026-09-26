import type { EvidenciaVigente, LegajoCompuesto, LegajoDatos, MiLegajoAccess, MiLegajoResponse, RecursoCustodiado } from './contracts';

// Mock de desarrollo (`VITE_ENABLE_MOCKS=true`) con la FORMA REAL del contrato — mismo
// criterio que documentation-planning/temporaryMockAccess.ts. Se usa sólo cuando
// `featureFlags.technicianCompositeView` está en `false` — ver `access.ts`.
const HOY = '2026-09-22';

function evidencia(partial: Pick<EvidenciaVigente, 'tipo' | 'id' | 'sujeto_id' | 'requisito' | 'vigente_hasta' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido'>): EvidenciaVigente {
  return {
    requisito_definicion_id: `req-${partial.id}`,
    categoria: partial.tipo === 'documento' ? 'documento' : partial.tipo === 'acreditacion' ? 'competencia' : 'induccion',
    origen_propuesta: false,
    locacion_id: null,
    vigente_hoy: !partial.vencido,
    vigente_desde: '2026-08-01',
    ...partial,
  };
}

function legajoDatos(sujeto_id: string, tipo_sujeto: string, nombre: string): LegajoDatos {
  return { legajo_id: `legajo-${sujeto_id}`, sujeto_id, tipo_sujeto, identificador_natural: nombre, dado_de_baja_en: null, creado_en: '2026-01-15T10:00:00Z' };
}

const persona: LegajoCompuesto = {
  hoy: HOY,
  legajo: legajoDatos('persona-mock', 'persona', 'Técnico de ejemplo'),
  documentos: [
    evidencia({ tipo: 'documento', id: 'doc-apto', sujeto_id: 'persona-mock', requisito: 'Apto médico', vigente_hasta: '2026-10-15', estado_confirmacion: 'verificado', dias_para_vencer: 23, vencido: false }),
    evidencia({ tipo: 'documento', id: 'doc-licencia', sujeto_id: 'persona-mock', requisito: 'Licencia de conducir', vigente_hasta: '2026-09-10', estado_confirmacion: 'verificado', dias_para_vencer: -12, vencido: true }),
  ],
  acreditaciones: [
    evidencia({ tipo: 'acreditacion', id: 'acr-espacios', sujeto_id: 'persona-mock', requisito: 'Espacios confinados', vigente_hasta: '2026-12-01', estado_confirmacion: 'declarado', dias_para_vencer: 70, vencido: false }),
  ],
  inducciones: [
    evidencia({ tipo: 'induccion', id: 'ind-locacion', sujeto_id: 'persona-mock', requisito: 'Inducción de locación', vigente_hasta: '2026-11-01', estado_confirmacion: 'verificado', dias_para_vencer: 40, vencido: false }),
  ],
  resumen: { total: 4, vigentes_hoy: 3, vencidos: 1 },
};

const recursosBajoCustodia: RecursoCustodiado[] = [
  {
    tipo_recurso: 'vehiculo', periodo_id: 'periodo-vx23', custodia_desde: '2026-08-01', hoy: HOY,
    legajo: legajoDatos('vehiculo-mock', 'vehiculo', 'Unidad de ejemplo VX-23'),
    documentos: [evidencia({ tipo: 'documento', id: 'doc-vtv', sujeto_id: 'vehiculo-mock', requisito: 'VTV', vigente_hasta: '2026-10-05', estado_confirmacion: 'verificado', dias_para_vencer: 13, vencido: false })],
    acreditaciones: [], inducciones: [],
    resumen: { total: 1, vigentes_hoy: 1, vencidos: 0 },
  },
];

const respuesta: MiLegajoResponse = {
  hoy: HOY,
  persona,
  recursos_bajo_custodia: recursosBajoCustodia,
  resumen: { vencidos: 1, vigentes_hoy: 4 },
};

export const temporaryMockAccess: MiLegajoAccess = {
  async readMiLegajo() {
    return respuesta;
  },
};
