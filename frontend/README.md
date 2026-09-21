# FieldServiceApp frontend foundation

Base de React + TypeScript + Vite para el Módulo 1. Consume el contrato versionado del backend y mantiene bloqueadas las pantallas que todavía no tienen respuestas tipadas o consultas de selección.

## Requisitos

- Node.js 22.12 o posterior
- npm
- Backend servido bajo el mismo origen en `/v1`, o proxy local configurado con `API_PROXY_TARGET`

## Desarrollo

```bash
npm ci
cp .env.example .env.local
npm run check:contract
npm run generate:api
npm run dev
```

La aplicación abre en `http://127.0.0.1:5173`. El proxy local envía `/v1` al backend configurado.

Para explorar el layout sin backend, establecer `VITE_ENABLE_MOCKS=true` en `.env.local`. En el formulario de ingreso se puede usar cualquier empresa y contraseña; el texto anterior a `@` elige uno de estos perfiles sintéticos: `configuracion`, `responsable_legajos`, `supervisor` o `tecnico`. MSW implementa únicamente login, refresh y perfil. El calendario y la proyección del backlog usan una capa local aparte con mocks contractuales temporales, siempre rotulados como no integrados; no interceptan endpoints ni simulan reglas de dominio.

Los adaptadores temporales viven en `src/features/documentation-planning/`. No deben migrarse al cliente API por copia: al llegar `docs/PROYECCION_DOCUMENTAL.md` y el nuevo `openapi.json`, se compara el contrato, se regeneran tipos y se reemplaza `DocumentationPlanningAccess` con un adaptador real.

## Comprobaciones

```bash
npm run typecheck
npm test
npm run build
```

`contracts/modulo1/openapi.json` corresponde al backend auditado en `bbf42b5`. Cuando llegue un backend corregido, primero se compara el nuevo contrato, luego se reemplaza esta copia y finalmente se regeneran los tipos. Los archivos de `src/api/generated/` no se editan manualmente.

La sesión vive solo en memoria. Recargar la página exige volver a ingresar. Las capacidades bloqueadas están documentadas en `../docs/frontend/API_GAPS.md`.
