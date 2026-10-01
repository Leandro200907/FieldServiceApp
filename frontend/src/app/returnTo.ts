/** Rutas internas seguras para redirigir después del login (sin open redirect). */
export function isInternalReturn(path: string): boolean {
  if (!path.startsWith('/') || path.startsWith('//') || path.startsWith('/login')) return false;
  try {
    const parsed = new URL(path, 'https://app.local');
    return parsed.origin === 'https://app.local' && parsed.pathname.startsWith('/');
  } catch {
    return false;
  }
}

export function loginPathWithReturn(pathname: string, search: string): string {
  const candidate = `${pathname}${search}`;
  if (!isInternalReturn(candidate)) return '/login';
  return `/login?return=${encodeURIComponent(candidate)}`;
}
