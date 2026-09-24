# FieldServiceApp — Entrega de planificación frontend

Actualizado 21/09/2026 · Baseline bbf42b5 · Revisión para Leandro

## Orden de lectura

1. `FRONTEND_PLAN.md`: recomendación, iteraciones, criterios y decisiones D-01…D-05.
2. `WIREFRAMES.html`: trece láminas offline; abrir en navegador. Los enlaces del índice recorren las láminas; los controles de aplicación son ilustrativos e inactivos. No requiere servidor ni conexión.
3. `NAVIGATION.md`: mapa por rol y rutas UI propuestas.
4. `SCREEN_MATRIX.md`: pantallas, recorrido y catálogo exacto de 47 operaciones con entradas.
5. `FRONTEND_ARCHITECTURE.md`: Vite vs Next.js, stack, carpetas, sesión, errores, idempotencia, evidencia y mocks.
6. `API_GAPS.md`: H/M/L de la auditoría y G-01…G-17 y los 33 selectores adicionales para integración.
7. `CONTRACT_BASELINE.json` y `contract/openapi.bbf42b5.json`: hashes de insumos y contrato exacto para el diff posterior.

## Qué se verificó

- ZIP recibido: SHA-256 `abc1204ce2f11f7441c3d4c56e7c42a1d1718a162f7c96da1a1965cf7d3e271e`, coincide con el informe.
- Baseline OpenAPI copiada byte a byte sin cambios; 47 operaciones / 46 paths.
- Matriz contiene 47 IDs únicos de operación, tanto en inventario como en entradas.
- Todas las referencias HTTP explícitas de los documentos y wireframes corresponden al contrato recibido.
- Los archivos extraídos del backend siguen idénticos al ZIP.
- Revisiones estáticas especializadas de contrato y UX, con integración única de Astra.
- HTML: 13 secciones, índice resuelto, controles de aplicación y selectores deshabilitados y ningún script ni llamada API.

Limitaciones: no se ejecutó la suite backend ni se levantó PostgreSQL. No se certifica v1 ni el entorno corregido que aún no fue entregado. Se inspeccionó estructura HTML/CSS, pero no se pudo completar la comprobación visual en navegador automatizado: el navegador no estaba instalado y su descarga no estuvo disponible. La comprobación responsive visual queda pendiente antes de implementar los componentes definitivos.

- Ocho fixtures de auth/perfil/error verificadas contra las operaciones/status/schemas publicados; sin mocks de negocio ni consultas propuestas. Ver `MOCKS_CONTRACTUALES.md`.

## Estado final de este paquete

Planificación, diseños y fixtures contractuales. Continuidad de layout/componentes/estados/mocks autorizada por Leandro; integración de pantallas bloqueadas sigue abierta. No hay aplicación React, tipos generados instalados, cambios de backend, rama creada, push, despliegue ni tag. Con la continuidad confirmada, resta identificar el repositorio para iniciar la foundation en `frontend/foundation` dentro del repositorio indicado. No se transmitieron mensajes ni archivos a terceros.
