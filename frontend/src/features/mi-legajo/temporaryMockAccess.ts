import type { EvidenciaVigente, LegajoCompuesto, LegajoDatos, MiLegajoAccess, MiLegajoResponse, RecursoCustodiado } from './contracts';

// Mock de desarrollo (`VITE_ENABLE_MOCKS=true`) con la FORMA REAL del contrato — mismo
// criterio que documentation-planning/temporaryMockAccess.ts. Se usa sólo cuando
// `featureFlags.technicianCompositeView` está en `false` — ver `access.ts`.
const HOY = '2026-09-22';

function evidencia(partial: Pick<EvidenciaVigente, 'tipo' | 'id' | 'sujeto_id' | 'requisito' | 'vigente_hasta' | 'estado_confirmacion' | 'dias_para_vencer' | 'vencido'>): EvidenciaVigente {
  const estado_presentacion = partial.vencido ? 'vencida' : (partial.estado_confirmacion === 'declarado' ? 'declarada' : 'verificada');
  return {
    requisito_definicion_id: `req-${partial.id}`,
    categoria: partial.tipo === 'documento' ? 'documento' : partial.tipo === 'acreditacion' ? 'competencia' : 'induccion',
    origen_propuesta: false,
    locacion_id: null,
    vigente_hoy: !partial.vencido,
    vigente_desde: '2026-08-01',
    estado_presentacion,
    estado_presentacion_explicacion: 'Mock temporal',
    exigido_backlog: true,
    no_exigido_backlog: false,
    faltante_exigido: false,
    ...partial,
  };
}

const resumenBacklog = (base: { total: number; vigentes_hoy: number; por_vencer: number; vencidos: number; en_regla: number; ocs_afectadas: number }) => ({
  ...base,
  exigidos: base.total,
  en_regla_exigidos: base.en_regla,
  sin_documento: 0,
  observados_operadora: 0,
  exigidos_vencidos: base.vencidos,
  exigidos_por_vencer: base.por_vencer,
  exigidos_vigentes: base.vigentes_hoy,
  exigidos_sin_documento: 0,
});

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
  resumen: resumenBacklog({ total: 4, vigentes_hoy: 3, por_vencer: 0, vencidos: 1, en_regla: 2, ocs_afectadas: 0 }),
};

const recursosBajoCustodia: RecursoCustodiado[] = [
  {
    tipo_recurso: 'vehiculo', periodo_id: 'periodo-vx23', custodia_desde: '2026-08-01', hoy: HOY,
    legajo: legajoDatos('vehiculo-mock', 'vehiculo', 'Unidad de ejemplo VX-23'),
    documentos: [evidencia({ tipo: 'documento', id: 'doc-vtv', sujeto_id: 'vehiculo-mock', requisito: 'VTV', vigente_hasta: '2026-10-05', estado_confirmacion: 'verificado', dias_para_vencer: 13, vencido: false })],
    acreditaciones: [], inducciones: [],
    resumen: resumenBacklog({ total: 1, vigentes_hoy: 1, por_vencer: 0, vencidos: 0, en_regla: 1, ocs_afectadas: 0 }),
  },
];

const respuesta: MiLegajoResponse = {
  hoy: HOY,
  persona,
  recursos_bajo_custodia: recursosBajoCustodia,
  resumen: { vencidos: 1, por_vencer: 0, vigentes_hoy: 4 },
};

export const temporaryMockAccess: MiLegajoAccess = {
  async readMiLegajo() {
    return respuesta;
  },
};
