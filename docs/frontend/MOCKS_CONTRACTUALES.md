# Fixtures contractuales y estados visuales

Actualizado 21/09/2026 · Solo diseño/desarrollo/test · Baseline bbf42b5 sin cambios

Se entregan ocho fixtures en `mocks/fixtures.json`, separadas de las láminas de negocio. Cada escenario declara método, path y status existente; `body` es la respuesta sintética. El wrapper y la marca `synthetic` son metadatos de pruebas, no campos agregados a la API.

| Escenarios | Contrato fuente | Límite |
|---|---|---|
| Login 200 y refresh 200 | ParDeTokens | Tokens deliberadamente inválidos, sin valor de autenticación; TTL de ejemplo no es configuración del servidor |
| Perfil 200 de C/R/S/T | IdentidadResponse | Roles conocidos de especificación; el schema solo define string[]; IDs sintéticos, no seleccionables ni datos reales |
| Perfil 401 | ErrorEnvelope en GET /v1/auth/yo | Mensaje de prueba y referencia explícitamente sintética |
| Login 422 | ErrorEnvelope en POST /v1/auth/login | detalles=null permitido; no se inventan estructuras de validación |

Ejecutar `python mocks/validate_fixtures.py` desde el paquete extraído. El script verifica hash de baseline, existencia de operación/status y campos/tipos/requeridos de los schemas usados, incluidos `$ref`, arrays y nullable. Es un verificador acotado de estas fixtures, **no un validador general OpenAPI/JSON Schema**; falla ante keywords nuevas no soportadas. Al integrar MSW se requiere validación completa compatible con OpenAPI 3.1 y el nuevo contrato.

La foundation implementa handlers MSW únicamente para autenticación/perfil. Además, las pantallas S-09A/S-09B usan un segundo conjunto **local y separado** de mocks contractuales temporales mediante `DocumentationPlanningAccess`. Estos objetos se identifican con `source="temporary-contract-mock"`, no interceptan HTTP, no entran al cliente generado y serán reemplazados después de recibir `docs/PROYECCION_DOCUMENTAL.md` y el nuevo OpenAPI.

## Exclusiones intencionales

- Sin filas definitivas de legajos, propuestas, matrices, cobertura o decisiones: faltan schemas de respuesta. Los sujetos/OC visibles en S-09A/S-09B son ejemplos temporales rotulados dentro del prototipo, no fixtures que pretendan pertenecer a la baseline.
- Sin mocks de consultas propuestas SEL-01…32 ni de vista compuesta G-16: no existen en la baseline.
- Sin 401 de login/refresh: el OpenAPI recibido no los publica; G-11 exige corregirlo. El cliente futuro debe manejar el HTTP inesperado sin fingir contrato completo.
- Sin respuestas de upload/download: G-03 pendiente.
- Sin motores simulados de habilitación, custodia, vencimientos o alertas.
- Sin cálculo local de riesgo, obligatoriedad o disponibilidad: los estados de S-09A/S-09B ya vienen fijados en el mock temporal para probar la presentación.

## Catálogo de estados de presentación

La lámina 12 de `WIREFRAMES.html` muestra loading, vacío, error/request_id, selector bloqueado, acceso denegado y mutación incierta. Son variantes visuales de componentes, no payloads de API.

El estado vacío solo aparece después de una respuesta válida y autorizada que confirme que no hay resultados. Antes de contar con consulta/schema, se usa **bloqueado por dependencia**. No se muestran cero vehículos/equipos para suplir la falta de consulta compuesta, ni se habilitan entradas libres de UUID/ID.
