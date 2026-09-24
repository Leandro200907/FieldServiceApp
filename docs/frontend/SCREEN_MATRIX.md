# FieldServiceApp — Matriz de pantallas y operaciones

> Actualización de recepción: backend `98a9c5d` agrega 38 operaciones (85 total), pero no las tres consultas de proyección. Ver [BACKEND_REVIEW_98A9C5D.md](BACKEND_REVIEW_98A9C5D.md) para diferencias, conflictos y secuencia vigente. Las afirmaciones de ausencia basadas en bbf42b5 son históricas y requieren revisión por selector. G-01 y G-18 siguen abiertos.

Actualizado 21/09/2026 · Baseline bbf42b5 · 47 operaciones verificadas contra el archivo recibido.

C = Configuración; R = Responsable; S = Supervisor; T = Técnico. Los roles efectivos proceden de código/handoff contrastados con no funcionales §2.2, porque OpenAPI solo expresa autenticación y no autorización por rol. «Alcance» siempre lo aplica el servidor. Las diferencias se registran, no se heredan como permisos nuevos.

## 1. Estado por pantalla

| ID / pantalla | Actor/rol | Recorrido | Operaciones (catálogo abajo) | Estado backend | Bloqueo o dependencia |
|---|---|---|---|---|---|
| S-01 Login | Todos | Ingresar al tenant | O-01 | Éxito tipado | G-11: error 401 no publicado; manejo de transporte |
| S-02 Perfil/sesión | Todos | Identidad, renovar, salir | O-02…O-04 | Identidad/tokens tipados; logout abierto | G-08/G-11; decisión memoria D-02 |
| S-03 Legajos / Mi legajo | R/T/S | R administra; T compuesto; S persona propia potencialmente operativa | O-05, O-07, O-38 | Consulta actual sin respuesta tipada ni garantía explícita de acceso propio S | G-01, SEL-01…33, G-05/G-06/G-16/G-17; no presumir habilitación S |
| S-03S Equipo supervisado | S | Navegar universo asignado | Operación faltante; O-38 solo abre un sujeto conocido | Bloqueado | G-17/SEL-33; sin sujeto_id o supervisor_usuario_id libre |
| S-04 Evidencia | R/T; S descarga | Documento/acreditación/inducción, binario | O-10, O-13, O-21, O-22, O-26, O-28, O-45…O-47 | Núcleo presente; storage incoherente en OpenAPI | G-01/G-02/G-03/G-13 |
| S-05 Propuestas | R | Listar, revisar, confirmar/rechazar | O-12, O-25, O-41; evidencia O-45…O-46 | Presente | G-01; G-03 para revisar archivo |
| S-06 Matrices/definiciones | C escribe; R/S/T leen | Consultar, publicar, catálogo local | O-15, O-16, O-23, O-40 | Presente parcialmente navegable | G-01/G-02; H-04 plantillas no incluidas |
| S-07 Backlog/cobertura | R/S | OC, cobertura, particulares/cancelar | O-09, O-11, O-32, O-33; O-37 C/R | Presente con brecha semántica | G-01/G-02/G-04/G-07/G-14 |
| S-08 Evaluación/decisiones | R crea; R/S consultan | Elegir sujetos, persistir, consultar | O-17, O-20, O-27, O-30, O-31, O-34, O-35 | Presente; no consulta puntual supervisor | G-01/G-02/G-07; constancia R, excepción S |
| S-09 Vencimientos | R/S | Filtrar días y abrir legajo | O-42, O-38 | Lectura de evidencia, no máquina de alertas | G-01/H-02 |
| S-09A Calendario documental de vigencias | R/S/T según alcance | Explorar intervalos por empresa/persona/vehículo/equipo y explicar un tramo | Operaciones faltantes Q-DOC-01/Q-DOC-03 | Diseño con mock contractual temporal; no integrado | G-18; empresa solo R; obligatoriedad solo con contexto matriz/OC |
| S-09B Proyección documental del backlog | R/S | Una fila por OC, riesgo y capacidad documental potencial | Operaciones faltantes Q-DOC-02/Q-DOC-03 | Diseño con mock contractual temporal; no integrado | G-18; advertencia de no disponibilidad; sin funciones Módulo 2 |
| S-10 Auditoría | C/R | Filtrar y paginar eventos | O-39 | Presente | G-01; no es monitor de infraestructura |
| S-11 Supervisión | C/R | Asignar/reasignar e historial | O-06, O-24, O-36 | Presente sin directorio completo | G-01/G-02 |
| S-12 Custodias/excepciones | S | Cambiar/corregir/revocar | O-08, O-14, O-20, O-31 | Comandos presentes; faltan consultas | G-01/G-02/G-13/G-15 |
| S-13 Lotes | R | Importar/revertir documental; importar OC | O-18, O-19, O-29 | Documental observado; filas OC abiertas | H-03/G-01/G-02/G-14 |
| S-14 Configuración | C | Entrada administrativa y parámetros | O-15, O-16, O-23, O-37 | Núcleo local; integraciones ausentes | G-01/G-02/H-01/H-02/H-04 |
| S-15 Diseños pendientes | Roles según API_GAPS | Drive/canales/QR/score/exportación/alertas/plantillas/M2 | Ninguna operación soportada para esos recorridos completos | Ausente/incompleto | Flags OFF; no endpoints propuestos |

**Presente no significa certificado ni integrable con mocks estrictos.** En I1 solo auth/perfil y transporte tienen base suficiente. S-09A/S-09B son prototipos explícitos con contrato local temporal y no se contabilizan como operaciones backend. Ningún «vacío» de pantalla sustituye un schema desconocido.

## 2. Catálogo completo por operación

`T` = éxito con schema referenciado; `A` = objeto libre; `V` = schema vacío. Los 3 T son login/refresh/yo. Estados indican el contrato disponible, no aprobación del backend.

| ID | Actor/rol efectivo | Recorrido | Pantalla | Endpoint utilizado | Estado backend / 200 | Bloqueo o dependencia |
|---|---|---|---|---|---|---|
| O-01 | Público | Ingresar | S-01 | `POST /v1/auth/login` | Presente / T | G-11 |
| O-02 | C/R/S/T | Cerrar sesión | S-02 | `POST /v1/auth/logout` | Presente / A | G-01/G-08 |
| O-03 | Refresh válido | Renovar sesión | S-02 | `POST /v1/auth/refresh` | Presente / T | G-11 |
| O-04 | C/R/S/T | Consultar identidad | S-02 | `GET /v1/auth/yo` | Presente / T | G-08 |
| O-05 | R | Alta de legajo | S-03 | `POST /v1/comandos/alta_de_sujeto` | Presente / A | G-01/G-02 |
| O-06 | C/R | Asignar supervisor | S-11 | `POST /v1/comandos/asignar_supervisor` | Presente / A | G-01/G-02 |
| O-07 | R | Baja de legajo | S-03 | `POST /v1/comandos/baja_de_sujeto` | Presente / A | G-01/G-02 |
| O-08 | S | Cambiar custodio | S-12 | `POST /v1/comandos/cambiar_custodia` | Presente / A | G-01/G-02 |
| O-09 | R | Cancelar OC | S-07 | `POST /v1/comandos/cancelar_oc` | Presente / A | G-01/G-14 |
| O-10 | R | Cargar documento | S-04 | `POST /v1/comandos/cargar_documento` | Presente / A | G-01/G-02/G-03 |
| O-11 | R | Añadir requisito de OC | S-07 | `POST /v1/comandos/cargar_requisito_particular` | Presente / A | G-01/G-02 |
| O-12 | R | Confirmar propuesta | S-05 | `POST /v1/comandos/confirmar_documento` | Presente / A | G-01 |
| O-13 | R/T propio | Confirmar binario | S-04 | `POST /v1/comandos/confirmar_subida_de_evidencia` | Presente / A | G-01/G-03/G-13 |
| O-14 | S | Corregir período de custodia | S-12 | `POST /v1/comandos/corregir_custodia` | Presente / A | G-01/G-02 |
| O-15 | C | Crear definición local | S-06 | `POST /v1/comandos/dar_de_alta_definicion_de_requisito` | Presente / A | G-01/G-02 |
| O-16 | C | Baja de definición local | S-06 | `POST /v1/comandos/dar_de_baja_definicion_de_requisito` | Presente / A | G-01/G-02 |
| O-17 | R | Persistir decisión explícita | S-08 | `POST /v1/comandos/evaluar_habilitacion` | Presente / A | G-01/G-02/G-07 |
| O-18 | R | Importar documentación | S-13 | `POST /v1/comandos/importar_lote` | Observado H-03 / A | H-03/G-01/G-02 |
| O-19 | R | Importar OC | S-13 | `POST /v1/comandos/importar_lote_oc` | Presente / A | G-01/G-02/G-14 |
| O-20 | S | Otorgar excepción contextual | S-12/S-08 | `POST /v1/comandos/otorgar_excepcion` | Presente / A | G-01/G-02/G-13/G-15 |
| O-21 | R/T propio | Solicitar URL subida | S-04 | `POST /v1/comandos/preparar_subida_de_evidencia` | Presente / A | G-01/G-03/G-13 |
| O-22 | T propio | Proponer renovación | S-04 | `POST /v1/comandos/proponer_documento` | Presente / A | G-01/G-02/G-03 |
| O-23 | C | Publicar nueva versión | S-06 | `POST /v1/comandos/publicar_version_de_matriz` | Presente / A | G-01/G-02 |
| O-24 | C/R | Reasignar supervisor | S-11 | `POST /v1/comandos/reasignar_supervisor` | Presente / A | G-01/G-02 |
| O-25 | R | Rechazar con motivo | S-05 | `POST /v1/comandos/rechazar_propuesta` | Presente / A | G-01 |
| O-26 | R | Registrar competencia | S-04 | `POST /v1/comandos/registrar_acreditacion_de_competencia` | Presente / A | G-01/G-02 |
| O-27 | R | Registrar constancia | S-08 | `POST /v1/comandos/registrar_constancia_del_cliente` | Presente / A | G-01/G-02 |
| O-28 | R | Registrar inducción | S-04 | `POST /v1/comandos/registrar_induccion` | Presente / A | G-01/G-02 |
| O-29 | R | Revertir lote sin borrar historia | S-13 | `POST /v1/comandos/revertir_lote` | Presente / A | H-03/G-01/G-02 |
| O-30 | R | Revocar constancia | S-08 | `POST /v1/comandos/revocar_constancia_del_cliente` | Presente / A | G-01/G-02 |
| O-31 | S | Revocar excepción | S-12/S-08 | `POST /v1/comandos/revocar_excepcion` | Presente / A | G-01/G-02 |
| O-32 | R/S | Abrir backlog | S-07 | `GET /v1/consultas/backlog_oc` | Presente / A | G-01/G-07 |
| O-33 | R/S | Consultar cobertura sin persistir | S-07 | `GET /v1/consultas/cobertura_oc` | Presente / A | G-01/G-07 |
| O-34 | R/S alcance | Abrir snapshot de decisión | S-08 | `GET /v1/consultas/decision` | Presente / A | G-01 |
| O-35 | R/S alcance | Historial de decisiones | S-08 | `GET /v1/consultas/decisiones_oc` | Presente / A | G-01 |
| O-36 | C/R | Historial de supervisión | S-11 | `GET /v1/consultas/historial_supervision` | Presente / A | G-01/G-02 |
| O-37 | C/R efectivo | Consultar aviso de empresa | S-07/S-14 | `GET /v1/consultas/incumplimiento_empresa` | Presente / A | G-01/G-04 |
| O-38 | C/R/S/T efectivo; UI R/S/T | Consultar legajo | S-03 | `GET /v1/consultas/legajo` | Presente / A | G-01/G-02/G-05/G-06 |
| O-39 | C/R | Consultar eventos | S-10 | `GET /v1/consultas/log_auditoria` | Presente / A | G-01 |
| O-40 | C/R/S/T | Consultar matriz a fecha | S-06 | `GET /v1/consultas/matriz_vigente` | Presente / A | G-01/G-02 |
| O-41 | R | Revisar bandeja | S-05 | `GET /v1/consultas/propuestas_pendientes` | Presente / A | G-01 |
| O-42 | R/S alcance | Ver evidencia por vencer/vencida | S-09 | `GET /v1/consultas/tablero_vencimientos` | Presente / A | G-01/H-02 |
| O-43 | Público | Diagnóstico técnico readiness | Transversal | `GET /v1/salud/listo` | Presente / V | G-11/L-03 |
| O-44 | Público | Diagnóstico técnico liveness | Transversal | `GET /v1/salud/vivo` | Presente / A | G-01 |
| O-45 | R/S/T alcance | Solicitar descarga autorizada | S-04 | `GET /v1/storage/documentos/{documento_id}/url` | Presente / A | G-01/G-03 |
| O-46 | Firma válida runtime | Descargar bytes | S-04 | `GET /v1/storage/{firma}` | Presente / V | G-03 |
| O-47 | Firma válida runtime | Subir bytes | S-04 | `PUT /v1/storage/{firma}` | Presente / A | G-03 |

## 3. Entradas publicadas

No se amplían filtros ni se fabrican cuerpos. Detalle exacto de propiedades, formatos y enums: copia OpenAPI incluida. Paginación declarada: offset >= 0, limit 1…500 (default 50); dias 0…3650 (default 30). No sort/búsqueda por nombre no declarados.

| Operación | Schema del body JSON | Parámetros publicados |
|---|---|---|
| O-01 | LoginRequest | — |
| O-02 | LogoutRequest | — |
| O-03 | RefreshRequest | — |
| O-04 | — | — |
| O-05 | AltaDeSujeto | header:`Idempotency-Key` |
| O-06 | AsignarSupervisor | header:`Idempotency-Key` |
| O-07 | BajaDeSujeto | header:`Idempotency-Key` |
| O-08 | CambiarCustodiaBody | header:`Idempotency-Key` |
| O-09 | CancelarOC | header:`Idempotency-Key` |
| O-10 | CargarDocumento | header:`Idempotency-Key` |
| O-11 | CargarRequisitoParticular | header:`Idempotency-Key` |
| O-12 | ConfirmarDocumento | header:`Idempotency-Key` |
| O-13 | ConfirmarSubida | header:`Idempotency-Key` |
| O-14 | CorregirCustodiaBody | header:`Idempotency-Key` |
| O-15 | DarDeAltaDefinicionDeRequisito | header:`Idempotency-Key` |
| O-16 | DarDeBajaDefinicionDeRequisito | header:`Idempotency-Key` |
| O-17 | EvaluarHabilitacionBody | header:`Idempotency-Key` |
| O-18 | ImportarLote | header:`Idempotency-Key` |
| O-19 | ImportarLoteOC | — |
| O-20 | OtorgarExcepcionBody | header:`Idempotency-Key` |
| O-21 | PrepararSubida | header:`Idempotency-Key` |
| O-22 | ProponerDocumento | header:`Idempotency-Key` |
| O-23 | PublicarVersionDeMatriz | header:`Idempotency-Key` |
| O-24 | ReasignarSupervisor | header:`Idempotency-Key` |
| O-25 | RechazarPropuesta | header:`Idempotency-Key` |
| O-26 | RegistrarAcreditacionDeCompetencia | header:`Idempotency-Key` |
| O-27 | RegistrarConstanciaBody | header:`Idempotency-Key` |
| O-28 | RegistrarInduccion | header:`Idempotency-Key` |
| O-29 | RevertirLote | header:`Idempotency-Key` |
| O-30 | RevocarConstanciaBody | header:`Idempotency-Key` |
| O-31 | RevocarExcepcionBody | header:`Idempotency-Key` |
| O-32 | — | query:`estado`, query:`offset`, query:`limit` |
| O-33 | — | query:`commitment_id` requerido |
| O-34 | — | query:`referencia_evaluacion` requerido |
| O-35 | — | query:`commitment_id` requerido, query:`offset`, query:`limit` |
| O-36 | — | query:`sujeto_id` requerido, query:`offset`, query:`limit` |
| O-37 | — | — |
| O-38 | — | query:`sujeto_id` requerido |
| O-39 | — | query:`tipo`, query:`desde`, query:`hasta`, query:`offset`, query:`limit` |
| O-40 | — | query:`cliente_id` requerido, query:`locacion_id` requerido, query:`tipo_servicio_id` requerido, query:`fecha` |
| O-41 | — | query:`offset`, query:`limit` |
| O-42 | — | query:`dias`, query:`offset`, query:`limit` |
| O-43 | — | — |
| O-44 | — | — |
| O-45 | — | path:`documento_id` requerido |
| O-46 | — | path:`firma` requerido |
| O-47 | — | path:`firma` requerido |

## 4. Límites de interpretación

- O-33 no recibe sujetos: no es evaluación puntual; O-17 persiste y es exclusivo R.
- O-38: C autorizado en código, pero menú conservador sin acceso general hasta G-06. T runtime solo propio; diseño compuesto bloqueado G-16. S requiere separación entre legajo personal y universo supervisado G-17; su rol no implica habilitación.
- O-37: C/R en código, aunque handoff dice todos.
- O-42 es consulta de evidencia vigente que vence o venció, no alertas abiertas/historial de escalamiento.
- O-45 verifica rol/alcance; O-46/O-47 usan firma runtime aunque el OpenAPI marque Bearer. No arreglarlo con un token filtrado a storage.
- O-18 y O-19 son lotes distintos, con IDs únicos por operación; no reusar el mismo UUID entre clases porque comparten namespace de idempotencia.
- O-43/O-44 son diagnóstico técnico; no requieren una pantalla operativa de negocio. Readiness 503 no tiene ErrorEnvelope en la implementación.
- No hay consulta de persona por nombre, catálogo de usuarios ni endpoints de Drive/QR/exportación. Sus casilleros pendientes no representan rutas futuras acordadas. Las consultas de selectores propuestas en API_GAPS §§5–6 no están en este inventario de operaciones existentes.
