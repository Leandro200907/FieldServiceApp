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

Para explorar el layout sin backend, establecer `VITE_ENABLE_MOCKS=true` en `.env.local`. En el formulario de ingreso se puede usar cualquier empresa y contraseña; el texto anterior a `@` elige uno de estos perfiles sintéticos: `configuracion`, `responsable_legajos`, `supervisor` o `tecnico`. MSW implementa únicamente login, refresh y perfil. El calendario y el radar documental disponen de datos sintéticos con la forma contractual para probar la presentación.

El radar consume `radar_documental_backlog`, `radar_documental_oc` y el detalle por legajo. Es una consulta informativa: no expone candidatos, disponibilidad, capacidad potencial ni asignaciones.

## Comprobaciones

```bash
npm run typecheck
npm test
npm run build
```

`npm run check` corre todo junto (contrato + typecheck + tests + build); es lo que ejecuta CI.

## Contrato con el backend

`contracts/modulo1/openapi.json` es una copia fijada del contrato del backend (`../backend/docs/openapi.json`, generado por `backend/scripts/generar_openapi.py`). Los archivos de `src/api/generated/` se regeneran desde esa copia con `npm run generate:api` y no se editan manualmente.

`npm run check:contract` (`scripts/check-contract.mjs`) verifica que la copia no cambió: compara su SHA-256 con el hash fijado en `expectedHash` y la cantidad de operaciones y paths (hoy 89 operaciones / 88 paths).

> **Atención:** cuando cambia `backend/docs/openapi.json`, el frontend no se entera solo. Hay que sincronizar a mano, desde `frontend/`:
>
> 1. Revisar el diff del contrato del backend.
> 2. Copiar `../backend/docs/openapi.json` a `contracts/modulo1/openapi.json` (copia byte a byte, sin reformatear).
> 3. `npm run generate:api` para regenerar `src/api/generated/modulo1.d.ts`.
> 4. Calcular el nuevo hash (`node -e "console.log(require('crypto').createHash('sha256').update(require('fs').readFileSync('contracts/modulo1/openapi.json')).digest('hex'))"`) y reemplazar `expectedHash` en `scripts/check-contract.mjs`; si cambió la cantidad de operaciones o paths, actualizar también esas cifras en el mismo script.
> 5. `npm run check` y corregir lo que rompa por los tipos nuevos.

La sesión vive solo en memoria. Recargar la página exige volver a ingresar. Las capacidades que el backend todavía no expone están en `../backend/docs/HANDOFF_FRONTEND.md` (sección 8).


