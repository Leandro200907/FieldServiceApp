import { describe, expect, it } from 'vitest';
import { buildPublicarVersionBody, lineasIncluidas, planPublicarMatriz } from '../src/features/matrices/matrizPublishLogic';
import type { MatrizDraft } from '../src/features/matrices/matrizDraft';
import {
  buildLineasTraerCambios,
  buildTraerPublicacionBody,
  copiasDefinicionNecesarias,
} from '../src/features/matrices/plantillaTraerLogic';
import { parseApiError } from '../src/api/errors';

const baseDraft = (): MatrizDraft => ({
  clienteId: 'c-1',
  locacionId: 'l-1',
  tipoServicioId: 'ts-1',
  modo: 'plantilla',
  matrizGlobalId: 'mg-1',
  vigenteDesde: '2026-09-20',
  fuente: 'Plantilla Vista',
  archivoDeRespaldo: '',
  lineas: [
    { requisito_definicion_id: 'r1', nombre: 'A', tipo_sujeto_aplicable: 'persona', categoria: 'documento', incluido: true, clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
  ],
});

describe('matrizPublishLogic', () => {
  it('5: plantilla sin cambios → un solo POST publicar_version_de_matriz', () => {
    const plans = planPublicarMatriz(baseDraft());
    expect(plans).toHaveLength(1);
    expect(plans[0].path).toBe('/v1/comandos/publicar_version_de_matriz');
    expect(plans[0].body.matriz_global_id).toBe('mg-1');
    expect(plans[0].body.lineas).toHaveLength(1);
  });

  it('6: candado excepcionable en el pedido', () => {
    const d = baseDraft();
    d.lineas[0].clasificacion = 'excepcionable';
    d.lineas[0].bloqueante_durante_ejecucion = false;
    const body = buildPublicarVersionBody(d);
    expect(body.lineas[0].clasificacion).toBe('excepcionable');
    expect(body.lineas[0].bloqueante_durante_ejecucion).toBe(false);
  });

  it('7: copiar matriz mía → líneas incluidas en el body', () => {
    const d: MatrizDraft = {
      ...baseDraft(),
      modo: 'copiar',
      matrizGlobalId: undefined,
      lineas: [
        { requisito_definicion_id: 'rx', nombre: 'X', tipo_sujeto_aplicable: 'empresa', categoria: 'documento', incluido: true, clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true },
        { requisito_definicion_id: 'ry', nombre: 'Y', tipo_sujeto_aplicable: 'persona', categoria: 'documento', incluido: false, clasificacion: 'excepcionable', bloqueante_durante_ejecucion: false },
      ],
    };
    expect(lineasIncluidas(d.lineas)).toEqual([{ requisito_definicion_id: 'rx', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true }]);
  });
});

describe('plantillaTraerLogic', () => {
  const copia = {
    matriz_version_id: 'mv-1',
    cliente_id: 'c-1',
    locacion_id: 'l-1',
    tipo_servicio_id: 'ts-1',
    version: 1,
    vigente_desde: '2026-01-01',
    vigente_hasta: null,
    copiada_de_version: 1,
    estado: 'actualizacion_disponible',
    lineas: [{ requisito_definicion_id: 'r-old', nombre: 'A', definicion_global_id: 'dg-old', clasificacion: 'bloqueante_duro', bloqueante_durante_ejecucion: true }],
    cambios: [],
  };
  const cambios = [
    { tipo: 'agregado' as const, grupo: 'persona', nombre: 'N1', version_origen: 0, version_destino: 2, definicion_global_id: 'dg-1', requisito_definicion_id: null, clasificacion_destino: 'bloqueante_duro' as const, bloqueante_durante_ejecucion_destino: true },
    { tipo: 'agregado' as const, grupo: 'persona', nombre: 'N2', version_origen: 0, version_destino: 2, definicion_global_id: 'dg-2', requisito_definicion_id: null, clasificacion_destino: 'bloqueante_duro' as const, bloqueante_durante_ejecucion_destino: true },
    { tipo: 'agregado' as const, grupo: 'persona', nombre: 'N3', version_origen: 0, version_destino: 2, definicion_global_id: 'dg-3', requisito_definicion_id: null, clasificacion_destino: 'bloqueante_duro' as const, bloqueante_durante_ejecucion_destino: true },
  ];

  it('8: traer 3 cambios con 1 destildado → 2 en body y vigente_desde hoy', () => {
    const elegidos = [cambios[0], cambios[2]];
    const map = new Map([['dg-1', 'r-new-1'], ['dg-3', 'r-new-3']]);
    const lineas = buildLineasTraerCambios(copia, cambios, elegidos, [], map);
    expect(lineas.filter(l => l.requisito_definicion_id.startsWith('r-new'))).toHaveLength(2);
    const body = buildTraerPublicacionBody(copia, 'mg-1', '2026-09-20', lineas, 2);
    expect(body.vigente_desde).toBe('2026-09-20');
    expect(body.matriz_global_id).toBe('mg-1');
    expect(copiasDefinicionNecesarias(elegidos, [], 'l-1')).toHaveLength(2);
  });

  it('9: mensaje 409 del backend visible', () => {
    const msg = parseApiError(
      { error: { codigo: 'conflicto', mensaje: 'La nueva versión no puede empezar antes (ni el mismo día) que la versión vigente', detalles: {}, request_id: 'x' } },
      { status: 409, headers: new Headers({ 'X-Request-ID': 'x' }) },
      'local',
    );
    expect(msg.message).toContain('mismo día');
  });
});
