import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { App } from './app/App';
import './ui/styles.css';

async function bootstrap() {
  if (import.meta.env.DEV && import.meta.env.VITE_ENABLE_MOCKS === 'true') {
    const { worker } = await import('./mocks/browser');
    await worker.start({ onUnhandledRequest(request, print) { if (new URL(request.url).pathname.startsWith('/v1/')) print.error(); } });
  }
  const root = document.getElementById('root');
  if (!root) throw new Error('Missing application root');
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false }, mutations: { retry: false } } });
  createRoot(root).render(<StrictMode><QueryClientProvider client={queryClient}><BrowserRouter><App /></BrowserRouter></QueryClientProvider></StrictMode>);
}
void bootstrap().catch(() => {
  const root = document.getElementById('root');
  if (root) root.textContent = 'No se pudo iniciar la aplicación. Revisá la configuración de desarrollo y volvé a cargar.';
});
