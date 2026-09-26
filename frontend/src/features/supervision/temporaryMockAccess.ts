import type {
  AsignacionesQuery, AsignacionesSupervisorResponse, AsignacionSupervisionHistorial, AsignacionSupervisorItem,
  AsignarSupervisorResponse, HistorialQuery, HistorialSupervisionResponse, ReasignarSupervisorResponse,
  SujetoItem, SujetoSearchQuery, SujetosResponse, SupervisionAccess, SupervisorSearchQuery, UsuarioItem, UsuariosResponse,
} from './contracts';

// Mock de desarrollo con la FORMA REAL del contrato — mismo patrón que
// propuestas/temporaryMockAccess.ts. Estado mutable en memoria para que
// asignar/reasignar realmente actualicen la asignación vigente, igual que el backend.
const HOY = '2026-09-21';

const sujetos: SujetoItem[] = [
  { sujeto_id: 'persona-marina', tipo_sujeto: 'persona', identificador_natural: 'Marina López', dado_de_baja_en: null, creado_en: '2026-01-10T09:00:00Z' },
  { sujeto_id: 'persona-diego', tipo_sujeto: 'persona', identificador_natural: 'Diego Suárez', dado_de_baja_en: null, creado_en: '2026-01-12T09:00:00Z' },
];

const supervisores: UsuarioItem[] = [
  { usuario_id: 'usr-supervisor-01', email: 'ana.supervisor@example.com', nombre: 'Ana Fernández', roles: ['supervisor'], sujeto_id: null, activo: true, creado_en: '2026-01-01T09:00:00Z' },
  { usuario_id: 'usr-supervisor-02', email: 'luis.supervisor@example.com', nombre: 'Luis Herrera', roles: ['supervisor'], sujeto_id: null, activo: true, creado_en: '2026-01-01T09:00:00Z' },
];

let historiales: Record<string, AsignacionSupervisionHistorial[]> = {
  'persona-marina': [
    { asignacion_id: 'asig-marina-01', sujeto_id: 'persona-marina', supervisor_usuario_id: 'usr-supervisor-01', supervisor_nombre: 'Ana Fernández', desde: '2026-06-01', hasta: null, estado: 'vigente', asignada_por: 'usr-config-01', creado_en: '2026-06-01T09:00:00Z' },
  ],
  'persona-diego': [],
};

function vigente(sujetoId: string): AsignacionSupervisionHistorial | undefined {
  return (historiales[sujetoId] || []).find(item => item.estado === 'vigente');
}

export const temporaryMockAccess: SupervisionAccess = {
  async readAsignaciones(query: AsignacionesQuery): Promise<AsignacionesSupervisorResponse> {
    const items: AsignacionSupervisorItem[] = Object.values(historiales).flat()
      .filter(item => (!query.sujetoId || item.sujeto_id === query.sujetoId)
        && (!query.supervisorUsuarioId || item.supervisor_usuario_id === query.supervisorUsuarioId)
        && (query.soloVigentes === false || item.estado === 'vigente'))
      .map(item => ({ ...item, supervisor: supervisores.find(s => s.usuario_id === item.supervisor_usuario_id)?.nombre ?? null, supervisor_email: supervisores.find(s => s.usuario_id === item.supervisor_usuario_id)?.email ?? null }));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: items.slice(offset, offset + limit), total: items.length, offset, limit };
  },
  async readHistorial(query: HistorialQuery): Promise<HistorialSupervisionResponse> {
    const items = historiales[query.sujetoId] || [];
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: items.slice(offset, offset + limit), total: items.length, offset, limit };
  },
  async searchSujetos(query: SujetoSearchQuery): Promise<SujetosResponse> {
    const q = query.q?.trim().toLowerCase();
    const filtered = sujetos.filter(sujeto => !q || sujeto.identificador_natural.toLowerCase().includes(q) || sujeto.sujeto_id.toLowerCase().includes(q));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit };
  },
  async searchSupervisores(query: SupervisorSearchQuery): Promise<UsuariosResponse> {
    const q = query.q?.trim().toLowerCase();
    const filtered = supervisores.filter(usuario => !q || usuario.nombre.toLowerCase().includes(q) || usuario.email.toLowerCase().includes(q));
    const offset = query.offset ?? 0;
    const limit = query.limit ?? 50;
    return { items: filtered.slice(offset, offset + limit), total: filtered.length, offset, limit };
  },
  async asignarSupervisor(sujetoId: string, supervisorUsuarioId: string, desde?: string): Promise<AsignarSupervisorResponse> {
    if (vigente(sujetoId)) throw new Error('El sujeto ya tiene un supervisor vigente: usar reasignar_supervisor');
    const fecha = desde || HOY;
    const asignacionId = `asig-${sujetoId}-${(historiales[sujetoId] || []).length + 1}`;
    const supervisor = supervisores.find(s => s.usuario_id === supervisorUsuarioId);
    historiales = { ...historiales, [sujetoId]: [...(historiales[sujetoId] || []), { asignacion_id: asignacionId, sujeto_id: sujetoId, supervisor_usuario_id: supervisorUsuarioId, supervisor_nombre: supervisor?.nombre ?? null, desde: fecha, hasta: null, estado: 'vigente', asignada_por: 'usr-mock-actual', creado_en: `${fecha}T00:00:00Z` }] };
    return { asignacion_id: asignacionId, sujeto_id: sujetoId, desde: fecha, eventos: ['SupervisorAsignado'] };
  },
  async reasignarSupervisor(sujetoId: string, supervisorUsuarioId: string, desde?: string): Promise<ReasignarSupervisorResponse> {
    const actual = vigente(sujetoId);
    if (!actual) throw new Error('El sujeto no tiene supervisor vigente: usar asignar_supervisor');
    const fecha = desde || HOY;
    const cerrada = { ...actual, estado: 'cerrada', hasta: fecha };
    const nuevaId = `asig-${sujetoId}-${(historiales[sujetoId] || []).length + 1}`;
    const supervisor = supervisores.find(s => s.usuario_id === supervisorUsuarioId);
    historiales = { ...historiales, [sujetoId]: [...(historiales[sujetoId] || []).map(item => item.asignacion_id === actual.asignacion_id ? cerrada : item), { asignacion_id: nuevaId, sujeto_id: sujetoId, supervisor_usuario_id: supervisorUsuarioId, supervisor_nombre: supervisor?.nombre ?? null, desde: fecha, hasta: null, estado: 'vigente', asignada_por: 'usr-mock-actual', creado_en: `${fecha}T00:00:00Z` }] };
    return { asignacion_id: nuevaId, asignacion_cerrada_id: actual.asignacion_id, sujeto_id: sujetoId, desde: fecha, hasta_anterior: cerrada.hasta as string, eventos: ['SupervisorReasignado'] };
  },
};
