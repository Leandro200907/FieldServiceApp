import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useLocation } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useQueryClient } from '@tanstack/react-query';
import { session } from '../api';
import type { components } from '../api/generated/modulo1';
import { canOpen, entryFor, knownRoles, navigationFor, pages, roleLabels } from './capabilities';
import type { Role } from './capabilities';
import { BusinessDesign } from './BusinessDesign';
import { DesignCatalog } from './DesignCatalog';
import { Badge, ErrorState, LoadingState, Pending } from '../ui/States';

type LoginValues = components['schemas']['LoginRequest'];
function useSession() { return useSyncExternalStore(session.subscribe, session.getSnapshot); }
function Login() {
  const snapshot = useSession();
  const { register, handleSubmit, formState: { errors } } = useForm<LoginValues>();
  const roles = knownRoles(snapshot.identity?.roles || []);
  if (snapshot.identity) return <Navigate to={roles.length === 1 ? `/${entryFor(roles[0])}` : '/perfil'} replace />;
  return <main id="main-content" className="login-layout"><section className="login-intro"><Link to="/" className="brand"><span className="brand-mark">F</span>FieldServiceApp</Link><div><p className="eyebrow">Documentación habilitante · Módulo 1</p><h1>Cada documento.<br />Cada recurso.<br />Una vista clara.</h1><p>Una base para gestionar la documentación de personas, vehículos y equipos.</p></div><p className="login-caption">Foundation en desarrollo · backend en corrección</p></section><section className="login-form-section"><div className="login-form"><Badge>Acceso a tu empresa</Badge><h2>Ingresá a tu espacio de trabajo</h2><p>Usá la empresa y las credenciales que te asignó el administrador.</p>{import.meta.env.DEV && import.meta.env.VITE_ENABLE_MOCKS === 'true' && <p className="mock-notice">MODO DE PRUEBA · sesión y perfil sintéticos. No hay conexión de negocio.</p>}<form onSubmit={handleSubmit(values => session.login(values))} aria-busy={snapshot.status === 'authenticating'}>
    <div className="form-field"><label htmlFor="tenant">Empresa</label><input id="tenant" autoComplete="organization" {...register('tenant_slug', { required: 'Ingresá el identificador de tu empresa.', maxLength: { value: 200, message: 'Máximo 200 caracteres.' } })} aria-invalid={Boolean(errors.tenant_slug)} aria-describedby="tenant-error" /><small id="tenant-error" className="field-error">{errors.tenant_slug?.message}</small></div>
    <div className="form-field"><label htmlFor="email">Correo electrónico</label><input id="email" type="email" autoComplete="username" {...register('email', { required: 'Ingresá tu correo.', maxLength: { value: 320, message: 'Máximo 320 caracteres.' } })} aria-invalid={Boolean(errors.email)} aria-describedby="email-error" /><small id="email-error" className="field-error">{errors.email?.message}</small></div>
    <div className="form-field"><label htmlFor="password">Contraseña</label><input id="password" type="password" autoComplete="current-password" {...register('password', { required: 'Ingresá tu contraseña.', validate: value => new TextEncoder().encode(value).length <= 72 || 'La contraseña supera el límite de 72 bytes UTF-8.' })} aria-invalid={Boolean(errors.password)} aria-describedby="password-error" /><small id="password-error" className="field-error">{errors.password?.message}</small></div>
    <button className="button button-primary full-width" disabled={snapshot.status === 'authenticating'}>{snapshot.status === 'authenticating' ? 'Ingresando…' : 'Ingresar'}</button>
  </form>{snapshot.error && <ErrorState message={snapshot.error.message} requestId={snapshot.error.referenceSource === 'server' ? snapshot.error.requestId : undefined} />}<p className="session-note">La sesión se mantiene en esta pestaña. Al recargar, vas a necesitar ingresar nuevamente.</p><Link className="design-link" to="/diseno">Explorar el diseño sin iniciar sesión →</Link></div></section></main>;
}
function Profile() {
  const { identity, status, error } = useSession();
  if (!identity) return null;
  return <><section className="panel"><h3>Identidad de la sesión</h3><dl className="identity-list"><dt>Empresa / tenant</dt><dd>{identity.tenant_id}</dd><dt>Usuario</dt><dd>{identity.usuario_id}</dd><dt>Roles</dt><dd>{identity.roles.map(role => roleLabels[role as Role] || 'Rol no reconocido').join(' · ') || 'Sin roles disponibles'}</dd><dt>Sujeto asociado</dt><dd>{identity.sujeto_id || 'Sin legajo asociado'}</dd></dl><p className="muted">Información recibida de /auth/yo. Este panel es de consulta.</p><button className="button button-secondary" disabled={status === 'refreshing'} onClick={() => { void session.refresh().catch(() => {}); }}>{status === 'refreshing' ? 'Renovando sesión…' : 'Renovar sesión y actualizar permisos'}</button></section>{error && <ErrorState message={error.message} requestId={error.referenceSource === 'server' ? error.requestId : undefined} />}</>;
}
function Workspace() {
  const snapshot = useSession();
  const location = useLocation();
  const queryClient = useQueryClient();
  const roles = knownRoles(snapshot.identity?.roles || []);
  const [preferredContext, setPreferredContext] = useState<Role | ''>('');
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const drawer = useRef<HTMLDialogElement>(null);
  const identityKey = snapshot.identity ? JSON.stringify([snapshot.identity.tenant_id, snapshot.identity.usuario_id, snapshot.identity.roles, snapshot.identity.sujeto_id]) : '';
  useEffect(() => { queryClient.clear(); return () => { queryClient.clear(); }; }, [identityKey, queryClient]);
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);
  useEffect(() => {
    const dialog = drawer.current;
    if (menuOpen) dialog?.showModal(); else if (dialog?.open) { dialog.close(); menuButton.current?.focus(); }
  }, [menuOpen]);
  useEffect(() => { const listener = () => { if (window.innerWidth >= 900) setMenuOpen(false); }; window.addEventListener('resize', listener); return () => window.removeEventListener('resize', listener); }, []);
  if (!snapshot.identity) return <Navigate to="/login" replace />;
  const context = preferredContext && roles.includes(preferredContext) ? preferredContext : roles.length === 1 ? roles[0] : '';
  const page = pages.find(item => `/${item.id}` === location.pathname);
  const nav = context ? navigationFor(context) : pages.filter(item => canOpen(item, roles));
  const menu = <><Link className="brand" to="/perfil"><span className="brand-mark">F</span><span>FieldService<span className="brand-app">App</span></span></Link><p className="nav-section-label">DOCUMENTACIÓN / MÓDULO 1</p><nav aria-label="Navegación principal">{nav.map(item => <NavLink key={item.id} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to={`/${item.id}`}><span className="nav-dot" aria-hidden="true" />{item.label}</NavLink>)}</nav><div className="sidebar-bottom"><Badge tone="warning">Base en desarrollo</Badge><Link to="/diseno">Ver catálogo de diseño ↗</Link></div></>;
  return <div className="workspace"><aside className="sidebar desktop-sidebar">{menu}</aside><div className="workspace-body"><header className="workspace-header"><button ref={menuButton} className="button button-secondary menu-toggle" aria-label="Abrir navegación" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>Menú</button><div className="header-context">{roles.length > 1 ? <><label htmlFor="work-context">Contexto de trabajo</label><select id="work-context" value={context} onChange={event => setPreferredContext(event.target.value as Role | '')}><option value="">Todos mis permisos</option>{roles.map(role => <option value={role} key={role}>{roleLabels[role]}</option>)}</select></> : <span>{context ? roleLabels[context] : 'Sin rol reconocido'}</span>}</div><button className="button button-secondary" onClick={() => { void session.logout(); }}>Cerrar sesión</button></header><main id="main-content" className="workspace-main"><div className="page-heading"><div><p className="eyebrow">FieldServiceApp / Módulo 1</p><h1>{page?.label || 'Vista no encontrada'}</h1><p className="lede">{page?.description || 'Elegí una opción del menú para continuar.'}</p></div>{page?.id !== 'perfil' && <Badge tone="warning">Pendiente de integración</Badge>}</div>{roles.includes('supervisor') && <nav className="supervisor-contexts" aria-label="Contextos del Supervisor"><NavLink to="/mi-legajo"><strong>Mi legajo</strong><span>Mi documentación como persona</span></NavLink><NavLink to="/equipo-supervisado"><strong>Equipo supervisado</strong><span>Mi responsabilidad de supervisión</span></NavLink><p>El rol Supervisor no demuestra habilitación documental.</p></nav>}{snapshot.status === 'refreshing' ? <LoadingState /> : !page ? <Pending title="La dirección no corresponde a una pantalla disponible"><Link to="/perfil">Volver a mi sesión</Link></Pending> : !canOpen(page, roles) ? <Pending title="No tenés permiso para esta vista">El menú muestra las funciones de tus roles actuales.</Pending> : page.id === 'perfil' ? <Profile /> : <BusinessDesign page={page} roles={context ? [context] : roles} />}</main></div><dialog ref={drawer} className="mobile-drawer" onCancel={() => setMenuOpen(false)} onClose={() => setMenuOpen(false)}><button className="button button-secondary drawer-close" onClick={() => setMenuOpen(false)}>Cerrar menú</button><div className="sidebar">{menu}</div></dialog></div>;
}
export function App() {
  return <><a className="skip-link" href="#main-content">Saltar al contenido</a><Routes><Route path="/login" element={<Login />} /><Route path="/diseno" element={<DesignCatalog />} /><Route path="/" element={<Navigate to="/login" replace />} /><Route path="*" element={<Workspace />} /></Routes></>;
}
