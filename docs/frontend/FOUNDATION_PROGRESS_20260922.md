# Avance frontend — 2026-09-22

Rama: frontend/foundation. Guardado sin abrir nuevas PR ni unir a main. La PR existente permanece en su estado de borrador; un commit en su rama puede aparecer automáticamente en ella.

## Cambios

- Estructuras de lectura para legajos, propuestas, matrices, backlog OC, vencimientos y auditoría. Encabezados y mensajes sin registros, totales o estados de negocio inventados.
- Catálogo de diseño con selección de estado pendiente/cargando/vacío/error por pantalla. Estos estados son ejemplos explícitos y no respuestas del servidor.
- Accesos separados y responsive para Supervisor: Mi legajo y Equipo supervisado. El rol no representa habilitación documental.
- Vista personal compuesta para Supervisor y Técnico: persona, vehículos y equipos. No se presume un único vehículo donde el contrato devuelve una lista.
- Textos de selectores actualizados para distinguir consulta existente de integración pendiente. Selectores bloqueados, sin campos libres de UUID.
- Tipos regenerados de db400e6 en directorio candidato separado. Cliente activo y flags de integración no promovidos.
- Prototipo temporal documental: Técnico ve una sola persona ficticia propia y sus recursos de ejemplo; el detalle rechaza otra persona. El filtro de fechas respeta solapamiento de intervalos.
- Capacidades desconocidas se muestran como «Sin cálculo confirmado», no como cero. Pendiente de planificación ya no presupone ausencia de fechas.

## Mapa de contextos

| Rol | Contextos principales | Estado |
|---|---|---|
| Configuración | Configuración, matrices, supervisión, auditoría, sesión | Diseño; sesión usa contrato activo |
| Responsable de legajos | Propuestas, legajos, matrices, OC/cobertura, vencimientos, auditoría | Estructura de lectura pendiente de integración |
| Supervisor | Mi legajo / Equipo supervisado; vencimientos, OC/cobertura y custodias | Contextos separados; alcance por custodias bloqueado A-01 |
| Técnico | Mi legajo compuesto; calendario | Compuesto bloqueado A-01; calendario temporal sin endpoint |

## Validación

`npm run check`: contrato activo, TypeScript, 22 pruebas y build aprobados. No constituye prueba E2E contra backend ni revisión visual en navegador. Los mocks documentales son una propuesta temporal explícita, no ejemplos derivados de endpoints inexistentes.

## Siguiente integración

Corregir y auditar custodias, validar suite PostgreSQL; comparar el nuevo OpenAPI y regenerar el candidato. Conectar recorridos por permiso y alcance. Calendario y proyección esperan sus tres consultas y reglas consistentes. No se implementan funciones del Módulo 2.
