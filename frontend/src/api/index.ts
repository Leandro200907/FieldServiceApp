import { createSession } from './session';
export { createSession } from './session';
export { ApiFailure, parseApiError, safeFailure } from './errors';
export type { SafeApiError } from './errors';
export const session = createSession({ baseUrl: import.meta.env.VITE_API_ORIGIN || undefined });
