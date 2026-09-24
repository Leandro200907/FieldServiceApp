# Recepción de backend/foundation

Fuente revisada: commit `98a9c5d121957cfb07c971d13067d37579bd88bc`. Esta revisión contractual no certifica el backend ni cierra la auditoría.

## Resultado del diff

OpenAPI pasa de 47 operaciones / 46 paths a **85 operaciones / 84 paths**. Hay 38 operaciones agregadas, ninguna eliminada y ninguna modificación estructural de las 47 operaciones previas. Migración declarada: `0021_validacion_evidencia`. La versión sigue siendo `1.0.0-rc1`.

SHA-256 del documento recibido: `90c66f214d298a49c6aa6a5a606724a297a0e44614f71f8c520c93f71a81208c`.

Se preservaron OpenAPI, diff legible por máquina y tipos regenerados en `frontend/contracts/modulo1/review-98a9c5d/`. Son candidatos de revisión, no el contrato activo de la aplicación. Las respuestas de consultas de negocio continúan como objetos libres; generar TypeScript no convierte esas respuestas en DTOs utilizables. G-01 permanece abierto.

Hay nuevas rutas de sujetos, usuarios, documentos, definiciones, matrices, custodias, constancias, excepciones, lotes y `mi_legajo`. Por tanto, la ausencia de todas las consultas de selección ya no es una descripción actual correcta. Cada selector requiere comprobar filtros, alcance y schema; no se cierra G-02 globalmente. También aparecen rutas para capacidades auditadas: su existencia no demuestra operación real de integraciones externas ni autoriza encender flags.

## Contraste de PROYECCION_DOCUMENTAL.md

El documento recibido se titula «diseño (sin implementar)» y declara que sus tres rutas no existen todavía. Ninguna aparece en el OpenAPI recibido. G-18 continúa abierto.

| Tema | Evidencia recibida | Resolución de integración |
|---|---|---|
| Tercera consulta | §§9–10 proponen `GET /v1/consultas/proyeccion_documental?commitment_id=…`, no el detalle genérico por referencia propuesto por frontend | Registrar la ruta de Claude como candidata para detalle de OC. No agregarla al cliente antes del OpenAPI. El detalle de tramo de calendario queda sin fuente equivalente |
| Calendario | §§2–3 ofrecen vencimientos, sin `vigente_desde`, intervalos ni contexto de matriz/OC | No alcanza para dibujar intervalos verdaderos ni ausencia de evidencia. No inventar inicio ni obligatoriedad a partir de vencimiento. Resolver ampliación de contrato o ajuste explícito del recorrido |
| Roles | §3 limita calendario a Responsable/Supervisor | El prototipo incluye Técnico propio: conflicto abierto con UX solicitada. No ampliar permisos backend por inferencia. Configuración tampoco obtiene acceso implícito |
| Origen de sujetos | §4: última decisión visible o candidatos del alcance | El prototipo debe poder mostrar ambos orígenes. `pendiente_de_planificacion` es estado; no equivale simplemente a fechas faltantes |
| Planificación | §4.2 menciona candidatos sin nada cargado; §6 define conjunto vacío | Backend debe unificar el significado. No clasificarlo en frontend |
| Riesgo vs bloqueo | §6 define bloqueo por cualquier día del horizonte sin candidato; también define riesgo por pérdida futura de toda cobertura. §7 prioriza bloqueo | Ambas condiciones se superponen y podrían hacer inalcanzable riesgo. Resolver distinción hoy/futuro antes de implementar |
| Ejemplo de riesgo | §9 mantiene persona=1 y vehículo=1; §12 dice que con respaldo el intervalo sigue verde | Ejemplo contradice regla de pérdida de TODA cobertura. No copiarlo como fixture definitivo |
| Ventana | §9 prohíbe empezar antes de vigencia OC, pero ejemplo comienza 21/09 para OC desde 01/10 | Corregir ejemplo y acordar intersección horizonte/vigencia; definir OC fuera del horizonte |
| Primer día de riesgo | §10 `primer_quiebre` es primer estado distinto de sin riesgos, incluidos sin matriz/planificación | No renombrar automáticamente como primer riesgo confirmado. Acordar etiqueta o campo específico |
| Resumen backlog | §10 no incluye motivos, etiquetas cliente ni origen de sujetos; están parcialmente en detalle | Definir resumen mínimo para la tabla sin una consulta por fila; nullabilidad y conteos desconocidos no deben convertirse en cero |
| Explicaciones | §9 exige tipo/requisito en todo estado no verde | Definir causas estructurales para sin matriz/sin candidatos, donde puede no existir requisito identificable |
| Etiquetas y búsqueda | Calendario usa sujeto_id e ILIKE sobre ID, sin nombre legible | Añadir etiquetas autorizadas o consulta contextual; no trasladar búsqueda por UUID libre al usuario |

## Secuencia actualizada

1. Conciliar las diferencias anteriores con Claude en el documento de diseño, conservando límites de Módulo 2. Este informe no se envió a terceros.
2. Completar schemas de respuestas para las nuevas consultas y selectores. Aclarar alcance personal del Supervisor y composición propia del Técnico.
3. Recibir OpenAPI con las tres consultas implementadas y pruebas de autorización/temporalidad/solo lectura.
4. Regenerar tipos y fixtures definitivas, reemplazar adaptador temporal, probar contra backend y cerrar únicamente los gaps resueltos.

La revisión actual no ejecutó tests del backend. La PR #1 permanece en borrador; no se habilita integración ni se etiqueta v1.0.
