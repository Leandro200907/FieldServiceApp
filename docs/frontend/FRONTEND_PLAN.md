# FieldServiceApp — Plan de inicio del frontend del Módulo 1

> Actualización de recepción: backend `98a9c5d` agrega 38 operaciones (85 total), pero no las tres consultas de proyección. Ver [BACKEND_REVIEW_98A9C5D.md](BACKEND_REVIEW_98A9C5D.md) para diferencias, conflictos y secuencia vigente. Las afirmaciones de ausencia basadas en bbf42b5 son históricas y requieren revisión por selector. G-01 y G-18 siguen abiertos.

Plan actualizado tras confirmación de continuidad · Actualizado 21/09/2026 · Integrador responsable: Astra

## 1. Decisión y límites

Recomiendo **React + TypeScript + Vite**, una SPA que consume la API existente. Leandro confirmó continuar wireframes, layout/componentes, estados y mocks contractuales, sin cerrar integración de pantallas bloqueadas. Esta entrega materializa diseños y fixtures; no hay aplicación implementada, rama creada, cambios de backend, push ni tag. Tras la conformidad se trabajará en `frontend/foundation`, sobre el repositorio que se identifique para el frontend. El ZIP no contiene `.git` y no permite inferir un remoto.

El backend continúa en corrección. `info.version = 1.0.0-rc1` es metadata del artefacto recibido, no una aprobación ni un cierre de v1. Las funciones pendientes siguen formando parte del alcance original hasta una decisión explícita del dueño del producto. Feature flags no equivalen a aprobar un recorte.

## 2. Baseline y fuentes

- ZIP recibido: `modulo1-backend-auditoria-bbf42b5(1).zip`.
- HEAD **declarado en el manifiesto**, no comprobado contra Git: `bbf42b5c46e385122b39cb79dc72bdc55df60554`.
- OpenAPI: 47 operaciones, 46 paths; migración declarada `0015_job_queue_dead_letter`.
- SHA-256 exacto de `docs/openapi.json`: `7608202069de835c8fbb40acbc0b2e41e1b4535edc15e0be1b1c15087b979e72`.
- Copia inalterada: `contract/openapi.bbf42b5.json`; hashes de todos los insumos: `CONTRACT_BASELINE.json`.
- Auditoría independiente recibida, fechada 19/09/2026: H-01…H-04, M-01…M-07, L-01…L-07.

Fuentes funcionales: las seis especificaciones originales, en particular habilitante §§2–3 y alcance v1; modelo de dominio §§1.5–1.6, 2.4, 2.11–2.12; especificación de agregados y reglas temporales; no funcionales §§2–4; arquitectura técnica §§8.4–8.8; wireframes/API §9.1. Se revisaron además README, handoff, decisiones, routers, servicios y pruebas relevantes mediante lectura estática.

**Precedencia:** especificaciones para lo que el producto debe hacer; OpenAPI para las rutas y estructuras publicadas; código/tests como evidencia de comportamiento actual; auditoría como restricciones abiertas. Una contradicción se registra en `API_GAPS.md`; no se resuelve silenciosamente a favor del documento más cómodo. El código no se convierte en un DTO frontend inventado.

## 3. Hallazgo que cambia la secuencia

Solo **3 respuestas 200 están estructuradas**: login, refresh y perfil. Otras **42** son objetos libres y **2** tienen esquema vacío. Todas las consultas de negocio carecen de estructura publicada de respuesta. Hay comandos reales, pero eso no basta para cerrar un recorrido con tipos y mocks estrictamente derivados del contrato.

Además faltan consultas de selección de sujetos, definiciones, clientes, locaciones, servicios, supervisores e históricos de varias entidades. La cobertura por OC no sustituye la consulta puntual de un conjunto elegido por el supervisor. Estos límites están detallados en G-01…G-12.

Por eso una pantalla puede ser estable en intención funcional y, a la vez, no estar lista para integración. No se simularán tablas, veredictos o campos aprovechando `additionalProperties: true`.

## 4. Organización del trabajo

Astra es el único integrador: mantiene baseline, permisos, ADRs, matriz y secuencia de integración. Los especialistas revisan contrato/seguridad y UX/accesibilidad; entregan propuestas o cambios aislados. Ningún especialista cambia permisos, DTOs, navegación compartida ni flags unilateralmente. Leandro aprueba producto y arquitectura. Claude Code conserva la responsabilidad de las correcciones del backend; esta entrega no le envía mensajes ni modifica su trabajo.

Cada cambio frontend deberá citar pantalla S-xx, operación O-xx, gap cuando aplique, y prueba de aceptación. Un cambio de contrato exige revisión del integrador antes de mezclar trabajo de pantallas.

## 5. Iteraciones propuestas

| Iteración | Trabajo | Dependencias / entrada | Resultado verificable |
|---|---|---|---|
| I0 · Esta entrega | Plan, matriz completa, arquitectura, brechas, navegación y wireframes | Insumos recibidos | Revisión y decisiones D-01…D-05 y ajustes confirmados de UX; sin aplicación implementada |
| I1 · Foundation | Rama `frontend/foundation`, Vite, TS estricto, tokens visuales, layout responsive, rutas/guards, perfil, login, sesión en memoria, cliente generado, errores/request_id, claves idempotentes, infraestructura de mocks | Aprobación D-01…D-04 y ubicación del repo D-05 | Build y tipos reproducibles; contrato fijado; sin requests fuera de baseline; roles desconocidos no habilitan nada |
| I2 · Lecturas documentales | Vista compuesta del Técnico (G-16), Mi legajo del Supervisor y Equipo supervisado separados (G-17), apertura contextual de legajo, propuestas, matriz vigente, vencimientos, auditoría, calendario de vigencias y proyección documental del backlog | G-01 tipado por pantalla; selectores SEL-01…33 sin IDs libres; G-16/G-17; G-18 y Q-DOC-01…03; permisos G-04/G-05 conciliados | Lecturas reales, vacíos distintos de falta de permiso; calendario/proyección sin disponibilidad ni acciones de Módulo 2; paginación servidor; no indicadores calculados en navegador |
| I3 · Evidencia y revisión | Documento/propuesta → preparación → PUT firmado → confirmación; descargar; confirmar/rechazar propuestas | G-01 y G-03; catálogos G-02; entorno de storage | Un binario subido no se confunde con documento verificado; fallo parcial recuperable sin duplicar documento |
| I4 · Operación de OC | Backlog, cobertura consultiva, decisiones históricas y evaluación persistida del responsable | G-01, G-02, G-07; datasets autorizados | No persiste por visitar; cobertura no se presenta como asignación; no Gantt/Módulo 2 ficticio |
| I5 · Administración y flujos complementarios | Definiciones/matrices, supervisión, acreditaciones/inducciones, particulares, constancias, excepciones y custodia | Respuestas + selectores/historiales; resolución de permisos | Recorridos recuperables y auditables; confirmaciones explícitas de mutaciones |
| I6 · Capacidades auditadas | Importación documental, alertas completas, Drive, canales, QR/paquete, score, exportación, plantillas y Módulo 2 según entregas | Corrección H-01…H-04/M-03 y nuevo contrato por capacidad | Activación gradual por evidencia y pruebas, sin habilitación global por versión |

I2–I5 pueden diseñarse durante I1 y ejecutarse por rebanadas que cierren sus dependencias. No son un compromiso de fecha: el camino crítico es el contrato de respuestas y las consultas de selección. La importación OC existente se distingue de H-03 documental, pero su UI también requiere contrato y consultas; no se declara lista por analogía.

## 6. Criterios transversales de aceptación

1. Ninguna URL de backend ajena al OpenAPI aprobado; rutas internas de navegación claramente separadas.
2. Permisos por rol y acción, con backend como autoridad de alcance. Un flag o un menú oculto no es autorización.
3. No recalcular habilitación, cobertura, prioridad, vigencia efectiva, excepciones o estado de alertas en navegador. Formatear y validar forma de inputs sí está permitido.
4. No presentar como hecho un comando con resultado incierto. Mutaciones sin retry automático genérico; reintentos seguros conservan intención, body y clave.
5. Logout/desactivación limpian sesión, cachés y evidencia. El perfil no inventa nombre/email ni parámetros ausentes.
6. Recorridos de teclado, foco, errores vinculados al campo, contraste y reflow en 360/768/1440 px. Ningún estado depende únicamente del color.
7. Mocks de desarrollo separados de producción; fixtures validadas contra la baseline; objeto sin esquema no habilita inventar campos.
8. El tablero de vencimientos nunca se presenta como bandeja completa de alertas ni como confirmación de envío.

Pruebas futuras enfocadas: refresh concurrente; 401 sin bucles; logout mientras refresh está en vuelo; aislamiento de caché entre usuarios; 403/404 de alcance; replay/mismo body y body cambiado; evidencia con URL vencida; lectura sin efectos; campos inesperados y contrato incompleto; navegación móvil. Se harán pruebas E2E de negocio solo cuando el contrato permita expresar los datos.

## 7. Recepción del backend corregido

1. Identificar nuevo commit, OpenAPI, handoff, migración y evidencia de tests/auditoría. No asumir que el nombre del ZIP prueba su contenido.
2. Conservar la baseline recibida; calcular hash de la nueva y comparar semánticamente paths/métodos, operationId, security, requestBody, parámetros, required/nullability, enums, respuestas/status/media types, headers y formatos.
3. Comparar permisos y semántica contra especificaciones y código revisado: un cambio de rol o comportamiento puede no aparecer en OpenAPI.
4. Registrar delta por O-xx/S-xx/G-xx, separar adiciones, incompatibilidades y aclaraciones. Regenerar tipos **desde el nuevo archivo**, nunca corregir el generado a mano.
5. Regenerar/validar fixtures, actualizar cliente, matriz, flags y plan. Revisar pantallas afectadas antes de integrar pendientes.
6. Ejecutar checks contractuales y recorridos reales por rol contra entorno corregido. Cerrar cada gap con evidencia identificable; conservar los demás abiertos.
7. Integrar mediante revisión en la rama de trabajo. Ningún push a `main`, despliegue ni tag v1.0 implícito.

## 8. Decisiones de arquitectura y dato pendiente

| ID | Recomendación | Efecto de aprobar |
|---|---|---|
| D-01 | React + TypeScript + Vite SPA; stack de `FRONTEND_ARCHITECTURE.md` | Autoriza construir la base propuesta |
| D-02 | Access y refresh solo en memoria por pestaña inicialmente | Recargar/cerrar pestaña exige volver a ingresar; no se promete sesión persistente. Revisar BFF/cookies si luego se requiere persistencia |
| D-03 | Primero I1; pantallas de negocio como diseños hasta disponer de respuestas tipadas y consultas necesarias | Evita fijar contratos inventados; no cambia alcance v1 |
| D-04 | Navegación por capacidades, contexto multirrol y sistema visual propuesto; funciones pendientes visibles solo en catálogo de diseño | Autoriza UX base, con permisos conflictivos restringidos hasta resolución |
| D-05 | Trabajar en `frontend/foundation` en el repositorio que indique Leandro | Falta ubicación/remoto del repo; por ahora no se creó ni conectó ninguno |

La confirmación posterior autoriza continuar diseños, componentes/estados y mocks contractuales con las restricciones de §§5–6 de API_GAPS. No se vuelve a pedir permiso para ese trabajo. La ubicación de repositorio de D-05 sigue sin proporcionarse; antes de crear una rama en un repo real debe identificarse. Resolver G-04/G-05/G-07 exige confirmación contractual del backend/producto; no se pide aquí que Leandro diseñe nuevos endpoints. No se propone aprobar un tag ni reducir las especificaciones.

## 9. Entrega

`SCREEN_MATRIX.md`: pantallas y 47 operaciones. `FRONTEND_ARCHITECTURE.md`: ADR, carpetas y políticas transversales. `API_GAPS.md`: auditoría y conflictos adicionales. `NAVIGATION.md`: permisos y mapa por rol. `WIREFRAMES.html`: láminas de diseño offline con estados y dependencias. `MOCKS_CONTRACTUALES.md` y `mocks/fixtures.json`: fixtures sintéticas solo para respuestas publicadas, sin datos de dominio. `CONTRACT_BASELINE.json` + copia OpenAPI: base para el diff futuro.

Verificación de esta entrega: lectura estática, conteo de operaciones, hashes, referencias a paths y consistencia documental. **No se ejecutó aquí la suite del backend ni se volvió a certificar la auditoría.**
