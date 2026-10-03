import { Link } from 'react-router-dom';

const accesos = [
  { to: '/catalogos-oc', titulo: 'Catálogos OC', descripcion: 'Operadoras, locaciones y tipos de servicio.' },
  { to: '/matrices', titulo: 'Matrices', descripcion: 'Requisitos por operadora, locación y tipo de servicio.' },
];

const proximamente = [
  { titulo: 'Usuarios', descripcion: 'Alta y permisos de acceso.' },
  { titulo: 'Plantillas', descripcion: 'Modelos de documentación y notificaciones.' },
];

export function ConfiguracionScreen() {
  return (
    <div className="planning-layout">
      <header className="panel">
        <h2>Configuración</h2>
        <p className="muted">Administración documental de tu empresa.</p>
      </header>
      <div className="config-dashboard">
        {accesos.map(item => (
          <Link key={item.to} className="config-dashboard-card panel" to={item.to}>
            <h3>{item.titulo}</h3>
            <p>{item.descripcion}</p>
          </Link>
        ))}
        {proximamente.map(item => (
          <div key={item.titulo} className="config-dashboard-card panel config-dashboard-card--soon" aria-disabled="true">
            <h3>{item.titulo}</h3>
            <p>{item.descripcion}</p>
            <span className="muted">Próximamente</span>
          </div>
        ))}
      </div>
    </div>
  );
}
