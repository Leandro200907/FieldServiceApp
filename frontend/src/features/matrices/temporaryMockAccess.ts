import type { MatricesAccess, MatricesQuery, MatrizItem, MatrizVigenteQuery, MatrizVigenteResponse } from './contracts';

// Mock de desarrollo con la FORMA REAL del contrato — mismo patrón que el resto de
// features. No hay catálogo de nombres para cliente/locación/tipo de servicio (SEL-09/
// 10/11 siguen abiertos) — los IDs se muestran crudos, igual que haría el backend real.
// `clasificacion` es `Literal["bloqueante_duro", "excepcionable"]` en el backend
// (visto en `CargarRequisitoParticular` del contrato generado) — no "obligatorio"/
// "recomendado".
const versiones: MatrizItem[] = [
  { matriz_version_id: 'matriz-norte-01-v2', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'servicio-mantenimiento', version: 2, vigente_desde: '2026-06-01', vigente_hasta: null, fuente: 'planilla', autor: 'usr-config-01', matriz_global_id: null, copiada_de_version: 1, creado_en: '2026-06-01T09:00:00Z', lineas: 3 },
  { matriz_version_id: 'matriz-norte-01-v1', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'servicio-mantenimiento', version: 1, vigente_desde: '2026-01-01', vigente_hasta: '2026-05-31', fuente: 'planilla', autor: 'usr-config-01', matriz_global_id: null, copiada_de_version: null, creado_en: '2026-01-01T09:00:00Z', lineas: 2 },
  { matriz_version_id: 'matriz-sur-02-v1', cliente_id: 'cliente-sur', locacion_id: 'locacion-sur-02', tipo_servicio_id: 'servicio-perforacion', version: 1, vigente_desde: '2026-03-15', vigente_hasta: null, fuente: 'drive', autor: 'usr-config-02', matriz_global_id: 'global-perforacion-01', copiada_de_version: null, creado_en: '2026-03-15T09:00:00Z', lineas: 4 },
];

const lineasPorVersion: Record<string, MatrizVigenteResponse> = {
  'matriz-norte-01-v2': {
    matriz_version_id: 'matriz-norte-01-v2', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'servicio-mantenimiento', version: 2,
    vigente_desde: '2026-06-01', vigente_hasta: null, fuente: 'planilla', archivo_de_respaldo: null, autor: 'usr-config-01', creado_en: '2026-06-01T09:00:00Z', fecha_consultada: '2026-09-21',
    lineas: [
      { requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', categoria: 'documento', tipo_sujeto_aplicable: 'persona', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
      { requisito_definicion_id: 'req-induccion-locacion', requisito: 'Inducción de locación', categoria: 'induccion', tipo_sujeto_aplicable: 'persona', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
      { requisito_definicion_id: 'req-vtv', requisito: 'VTV', categoria: 'documento', tipo_sujeto_aplicable: 'vehiculo', clasificacion: 'excepcionable', bloqueante_durante_ejecucion: false },
    ],
  },
  'matriz-norte-01-v1': {
    matriz_version_id: 'matriz-norte-01-v1', cliente_id: 'cliente-norte', locacion_id: 'locacion-norte-01', tipo_servicio_id: 'servicio-mantenimiento', version: 1,
    vigente_desde: '2026-01-01', vigente_hasta: '2026-05-31', fuente: 'planilla', archivo_de_respaldo: null, autor: 'usr-config-01', creado_en: '2026-01-01T09:00:00Z', fecha_consultada: '2026-01-01',
    lineas: [
      { requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', categoria: 'documento', tipo_sujeto_aplicable: 'persona', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
      { requisito_definicion_id: 'req-induccion-locacion', requisito: 'Inducción de locación', categoria: 'induccion', tipo_sujeto_aplicable: 'persona', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
    ],
  },
  'matriz-sur-02-v1': {
    matriz_version_id: 'matriz-sur-02-v1', cliente_id: 'cliente-sur', locacion_id: 'locacion-sur-02', tipo_servicio_id: 'servicio-perforacion', version: 1,
    vigente_desde: '2026-03-15', vigente_hasta: null, fuente: 'drive', archivo_de_respaldo: 'respaldo-sur-02.pdf', autor: 'usr-config-02', creado_en: '2026-03-15T09:00:00Z', fecha_consultada: '2026-09-21',
    lineas: [
      { requisito_definicion_id: 'req-apto-medico', requisito: 'Apto médico', categoria: 'documento', tipo_sujeto_aplicable: 'persona', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
      { requisito_definicion_id: 'req-calibracion-informada', requisito: 'Calibración informada', categoria: 'competencia', tipo_sujeto_aplicable: 'equipo', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: false },
      { requisito_definicion_id: 'req-vtv', requisito: 'VTV', categoria: 'documento', tipo_sujeto_aplicable: 'vehiculo', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
      { requisito_definicion_id: 'req-certificado-calibracion', requisito: 'Certificado de calibración', categoria: 'documento', tipo_sujeto_aplicable: 'equipo', clasificacion: 'excepcionable', bloqueante_durante_ejecucion: false },
    ],
  },
};

export const temporaryMockAccess: MatricesAccess = {
  async readMatrices(query: MatricesQuery) {
    const hoy = '2026-09-21';
    const filtered = versiones.filter(item =>
      (!query.clienteId || item.cliente_id === query.clienteId)
      && (!query.soloVigentes || (item.vigente_desde <= hoy && (item.vigente_hasta === null || item.vigente_hasta >= hoy))));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit };
  },
  async readMatrizVigente(query: MatrizVigenteQuery) {
    const match = Object.values(lineasPorVersion).find(version =>
      version.cliente_id === query.clienteId && version.locacion_id === query.locacionId && version.tipo_servicio_id === query.tipoServicioId
      && (!query.fecha || (version.vigente_desde <= query.fecha && (version.vigente_hasta === null || version.vigente_hasta >= query.fecha))));
    if (!match) throw new Error('El mock temporal no contiene una matriz vigente para esa combinación/fecha.');
    return match;
  },
};
