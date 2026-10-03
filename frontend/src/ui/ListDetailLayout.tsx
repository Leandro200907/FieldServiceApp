import type { ReactNode } from 'react';

type Props = {
  listTitle: string;
  list: ReactNode;
  detail?: ReactNode;
  onCloseDetail?: () => void;
};

export function ListDetailLayout({ listTitle, list, detail, onCloseDetail }: Props) {
  return (
    <div className={`list-detail-layout${detail ? ' has-detail' : ''}`}>
      <aside className="list-detail-list panel" aria-label={listTitle}>
        <h2 className="list-detail-title">{listTitle}</h2>
        {list}
      </aside>
      {detail && (
        <section className="list-detail-detail panel" aria-label="Ficha de detalle">
          {onCloseDetail && (
            <button type="button" className="list-detail-close" aria-label="Cerrar ficha" onClick={onCloseDetail}>
              ×
            </button>
          )}
          {detail}
        </section>
      )}
    </div>
  );
}

export function FichaEncabezado({
  breadcrumb,
  titulo,
  subtitulo,
  acciones,
  datosClave,
}: {
  breadcrumb: string;
  titulo: string;
  subtitulo?: string;
  acciones?: ReactNode;
  datosClave?: ReactNode;
}) {
  return (
    <header className="ficha-encabezado">
      <div className="ficha-encabezado-top">
        <div>
          <p className="ficha-breadcrumb">{breadcrumb}</p>
          <h2 className="ficha-titulo">{titulo}</h2>
          {subtitulo && <p className="ficha-subtitulo">{subtitulo}</p>}
        </div>
        {acciones && <div className="ficha-acciones">{acciones}</div>}
      </div>
      {datosClave && <dl className="ficha-datos-clave">{datosClave}</dl>}
    </header>
  );
}

export function FichaDato({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <>
      <dt>{label}</dt>
      <dd className={mono ? 'font-mono' : undefined}>{children}</dd>
    </>
  );
}
