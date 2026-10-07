import type { components } from '../../api/generated/modulo1';

export type ModoArranque = 'plantilla' | 'copiar' | 'cero';
export type EditorLinea = {
  requisito_definicion_id: string;
  nombre: string;
  tipo_sujeto_aplicable: string;
  categoria: string;
  incluido: boolean;
  clasificacion: 'bloqueante_duro' | 'excepcionable';
  bloqueante_durante_ejecucion: boolean;
};

export type MatrizDraft = {
  clienteId: string;
  locacionId: string;
  tipoServicioId: string;
  modo: ModoArranque;
  matrizGlobalId?: string;
  copiarDesde?: { clienteId: string; locacionId: string; tipoServicioId: string };
  lineas: EditorLinea[];
  vigenteDesde: string;
  fuente: string;
  archivoDeRespaldo: string;
};

const KEY = 'fsm.matriz-draft';

export function saveMatrizDraft(draft: MatrizDraft) {
  sessionStorage.setItem(KEY, JSON.stringify(draft));
}

export function loadMatrizDraft(): MatrizDraft | null {
  const raw = sessionStorage.getItem(KEY);
  if (!raw) return null;
  return JSON.parse(raw) as MatrizDraft;
}

export function clearMatrizDraft() {
  sessionStorage.removeItem(KEY);
}

export type CambioPlantilla = components['schemas']['CambioPlantillaMatriz'];

export const GRUPOS_EDITOR: { id: string; titulo: string }[] = [
  { id: 'empresa', titulo: 'Empresa' },
  { id: 'persona', titulo: 'Técnicos' },
  { id: 'vehiculo', titulo: 'Vehículos' },
  { id: 'equipo', titulo: 'Equipos' },
];

export function lineaFromVigente(l: components['schemas']['LineaMatrizVigente']): EditorLinea {
  return {
    requisito_definicion_id: l.requisito_definicion_id,
    nombre: l.requisito || 'Requisito',
    tipo_sujeto_aplicable: l.tipo_sujeto_aplicable || 'persona',
    categoria: l.categoria || 'documento',
    incluido: true,
    clasificacion: l.clasificacion as EditorLinea['clasificacion'],
    bloqueante_durante_ejecucion: l.bloqueante_durante_ejecucion,
  };
}
