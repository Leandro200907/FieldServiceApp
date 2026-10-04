/** Tras confirmar/rechazar: primero el aviso y el refresh; el salto al siguiente ítem va en microtarea para que el banner se pinte. */
export function ejecutarAccionBandejaExitosa(opts: {
  mensaje: string;
  setAviso: (mensaje: string) => void;
  refresh: () => void;
  avanzar?: () => void;
}): void {
  opts.setAviso(opts.mensaje);
  opts.refresh();
  if (opts.avanzar) queueMicrotask(opts.avanzar);
}
