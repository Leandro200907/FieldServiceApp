import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { Link, Navigate, NavLink, Route, Routes, useLocation, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { useQueryClient } from '@tanstack/react-query';
import { session } from '../api';
import type { components } from '../api/generated/modulo1';
import { canOpen, knownRoles, pages, roleLabels } from './capabilities';
import type { Page, Role } from './capabilities';
import { detailIdFromPath, navigationGroupsFor, pageFromPath } from './navigationGroups';
import { BusinessDesign } from './BusinessDesign';
import { DesignCatalog } from './DesignCatalog';
import { ErrorState, LoadingState, Pending } from '../ui/States';
import { loginPathWithReturn, resolvePostLoginPath } from './returnTo';
import { isPropuestasIntegrated, propuestasAccess } from '../features/propuestas/access';

type LoginValues = components['schemas']['LoginRequest'];
function useSession() { return useSyncExternalStore(session.subscribe, session.getSnapshot); }

function usePropuestasPendientesCount(enabled: boolean) {
  const [count, setCount] = useState<number | null>(null);
  useEffect(() => {
    if (!enabled || !isPropuestasIntegrated()) {
      setCount(null);
      return;
    }
    let cancelled = false;
    void propuestasAccess()
      .readPropuestasPendientes({ offset: 0, limit: 1 })
      .then(data => { if (!cancelled) setCount(data.total ?? data.items.length); })
      .catch(() => { if (!cancelled) setCount(null); });
    return () => { cancelled = true; };
  }, [enabled]);
  return count;
}

function Login() {
  const snapshot = useSession();
  const [searchParams] = useSearchParams();
  const { register, handleSubmit, formState: { errors } } = useForm<LoginValues>();
  const roles = knownRoles(snapshot.identity?.roles || []);
  const returnTo = searchParams.get('return');
  if (snapshot.identity) {
    const dest = resolvePostLoginPath(returnTo, roles);
    return <Navigate to={dest} replace />;
  }
  return (
    <main id="main-content" className="login-layout">
      <section className="login-intro">
        <Link to="/" className="brand"><span className="brand-mark">F</span>FieldServiceApp</Link>
        <div>
          <p className="eyebrow">Documentación habilitante</p>
          <h1>Cada documento.<br />Cada recurso.<br />Una vista clara.</h1>
          <p>Una base para gestionar la documentación de personas, vehículos y equipos.</p>
        </div>
      </section>
      <section className="login-form-section">
        <div className="login-form">
          <h2>Ingresá a tu espacio de trabajo</h2>
          <p>Usá la empresa y las credenciales que te asignó el administrador.</p>
          {import.meta.env.DEV && import.meta.env.VITE_ENABLE_MOCKS === 'true' && (
            <p className="mock-notice">MODO DE PRUEBA · sesión y perfil sintéticos. No hay conexión de negocio.</p>
          )}
          <form onSubmit={handleSubmit(values => session.login(values))} aria-busy={snapshot.status === 'authenticating'}>
            <div className="form-field">
              <label htmlFor="tenant">Empresa</label>
              <input id="tenant" autoComplete="organization" {...register('tenant_slug', { required: 'Ingresá el identificador de tu empresa.', maxLength: { value: 200, message: 'Máximo 200 caracteres.' } })} aria-invalid={Boolean(errors.tenant_slug)} aria-describedby="tenant-error" />
              <small id="tenant-error" className="field-error">{errors.tenant_slug?.message}</small>
            </div>
            <div className="form-field">
              <label htmlFor="email">Correo electrónico</label>
              <input id="email" type="email" autoComplete="username" {...register('email', { required: 'Ingresá tu correo.', maxLength: { value: 320, message: 'Máximo 320 caracteres.' } })} aria-invalid={Boolean(errors.email)} aria-describedby="email-error" />
              <small id="email-error" className="field-error">{errors.email?.message}</small>
            </div>
            <div className="form-field">
              <label htmlFor="password">Contraseña</label>
              <input id="password" type="password" autoComplete="current-password" {...register('password', { required: 'Ingresá tu contraseña.', validate: value => new TextEncoder().encode(value).length <= 72 || 'La contraseña supera el límite de 72 bytes UTF-8.' })} aria-invalid={Boolean(errors.password)} aria-describedby="password-error" />
              <small id="password-error" className="field-error">{errors.password?.message}</small>
            </div>
            <button className="button button-primary full-width" disabled={snapshot.status === 'authenticating'}>{snapshot.status === 'authenticating' ? 'Ingresando…' : 'Ingresar'}</button>
          </form>
          {snapshot.error && <ErrorState message={snapshot.error.message} requestId={snapshot.error.referenceSource === 'server' ? snapshot.error.requestId : undefined} />}
          <p className="session-note">La sesión se mantiene en esta pestaña. Al recargar, vas a necesitar ingresar nuevamente.</p>
        </div>
      </section>
    </main>
  );
}

function Profile() {
  const { identity, status, error } = useSession();
  if (!identity) return null;
  const usuarioEtiqueta = identity.usuario_nombre || identity.usuario_id;
  const legajoAsociado = identity.legajo_etiqueta || (identity.sujeto_id ? identity.sujeto_id : 'Sin legajo asociado');
  return (
    <>
      <section className="panel">
        <h3>Identidad de la sesión</h3>
        <dl className="identity-list">
          <dt>Empresa</dt><dd>{identity.tenant_nombre}</dd>
          <dt>Usuario</dt><dd>{usuarioEtiqueta}{identity.usuario_email ? <><br /><small>{identity.usuario_email}</small></> : null}</dd>
          <dt>Roles</dt><dd>{identity.roles.map(role => roleLabels[role as Role] || 'Rol no reconocido').join(' · ') || 'Sin roles disponibles'}</dd>
          <dt>Legajo asociado</dt><dd className="font-mono">{legajoAsociado}</dd>
          <dt>Zona horaria</dt><dd>{identity.zona_horaria}</dd>
        </dl>
        <button className="button button-secondary" disabled={status === 'refreshing'} onClick={() => { void session.refresh().catch(() => {}); }}>{status === 'refreshing' ? 'Renovando sesión…' : 'Renovar sesión y actualizar permisos'}</button>
      </section>
      {error && <ErrorState message={error.message} requestId={error.referenceSource === 'server' ? error.requestId : undefined} />}
    </>
  );
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

  const showPropuestasCount = roles.includes('responsable_legajos');
  const propuestasPendientes = usePropuestasPendientesCount(showPropuestasCount);

  if (!snapshot.identity) {
    return snapshot.suppressLoginReturn
      ? <Navigate to="/login" replace />
      : <Navigate to={loginPathWithReturn(location.pathname, location.search)} replace />;
  }

  const context = preferredContext && roles.includes(preferredContext) ? preferredContext : roles.length === 1 ? roles[0] : '';
  const page = pageFromPath(location.pathname);
  const detailId = detailIdFromPath(location.pathname);
  const navGroups = navigationGroupsFor(context ? [context] : roles);
  const rolEtiqueta = context ? roleLabels[context] : roles.map(r => roleLabels[r]).join(' · ');
  const usuarioNombre = snapshot.identity.usuario_nombre || snapshot.identity.usuario_email || 'Usuario';

  const menu = (
    <>
      <p className="nav-section-label">Navegación</p>
      {navGroups.map(group => (
        <div key={group.title}>
          <p className="nav-section-label">{group.title}</p>
          <nav aria-label={group.title}>
            {group.pageIds.map(id => {
              const item = pages.find(p => p.id === id)!;
              return (
                <NavLink key={item.id} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to={`/${item.id}`} end={!['legajos', 'radar-documental', 'backlog-oc', 'matrices'].includes(item.id)}>
                  {item.label}
                  {item.id === 'propuestas' && propuestasPendientes != null && propuestasPendientes > 0 && (
                    <span className="nav-item-count" aria-label={`${propuestasPendientes} pendientes`}>{propuestasPendientes}</span>
                  )}
                </NavLink>
              );
            })}
          </nav>
        </div>
      ))}
      <div className="sidebar-bottom">
        <NavLink className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} to="/perfil">Mi sesión</NavLink>
      </div>
    </>
  );

  return (
    <div className="workspace">
      <header className="app-topbar">
        <Link className="brand" to="/perfil"><span className="brand-mark">F</span><span>FieldServiceApp</span></Link>
        <div className="app-topbar-meta">
          <span className="app-topbar-empresa">Empresa: <strong>{snapshot.identity.tenant_nombre}</strong></span>
          <span className="app-topbar-user">{usuarioNombre} · {rolEtiqueta}</span>
          <button className="button button-secondary" type="button" onClick={() => { void session.logout(); }}>Salir</button>
        </div>
      </header>
      <div className="workspace-shell">
        <aside className="sidebar desktop-sidebar">{menu}</aside>
        <div className="workspace-body">
          <header className="workspace-header">
            <button ref={menuButton} className="button button-secondary menu-toggle" aria-label="Abrir navegación" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>Menú</button>
          </header>
          <main id="main-content" className="workspace-main">
            <div className="page-heading"><h1>{page?.label || 'Vista no encontrada'}</h1></div>
            {snapshot.status === 'refreshing' ? <LoadingState /> : !page ? (
              <Pending title="La dirección no corresponde a una pantalla disponible"><Link to="/perfil">Volver a mi sesión</Link></Pending>
            ) : !canOpen(page, roles) ? (
              <Pending title="No tenés permiso para esta vista">El menú muestra las funciones de tus roles actuales.</Pending>
            ) : page.id === 'perfil' ? <Profile /> : (
              <BusinessDesign page={page} roles={context ? [context] : roles} detailId={detailId} />
            )}
          </main>
        </div>
      </div>
      <dialog ref={drawer} className="mobile-drawer" onCancel={() => setMenuOpen(false)} onClose={() => setMenuOpen(false)}>
        <button className="button button-secondary drawer-close" onClick={() => setMenuOpen(false)}>Cerrar menú</button>
        <div className="sidebar">{menu}</div>
      </dialog>
    </div>
  );
}

export function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">Saltar al contenido</a>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/diseno" element={<DesignCatalog />} />
        <Route path="/calendario-vigencias" element={<Navigate to="/timeline-recursos?vista=documentos" replace />} />
        <Route path="/" element={<Navigate to="/login" replace />} />
        <Route path="/legajos/:detailId" element={<Workspace />} />
        <Route path="/radar-documental/:detailId" element={<Workspace />} />
        <Route path="/matrices/:detailId" element={<Workspace />} />
        <Route path="*" element={<Workspace />} />
      </Routes>
    </>
  );
}
