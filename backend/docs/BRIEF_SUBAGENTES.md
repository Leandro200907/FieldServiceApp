# Brief común para las piezas paralelas de Módulo 1

Leer completo antes de tocar código. Esto NO es diseño: el diseño está cerrado. Es el
contrato mínimo para que cinco piezas construidas en paralelo encajen sin pisarse.

## Contexto en 10 líneas

Field Service Management para servicios de campo en oil & gas (Vaca Muerta). Módulo 1 =
trazabilidad de habilitación de recursos (personas/vehículos/equipos/empresa) para
trabajar en un cliente: documentación, matrices de requisitos por cliente/locación/tipo
de servicio, evaluación de habilitación, custodia de recursos, excepciones y constancias.
Stack: Python 3.13, FastAPI, SQLAlchemy 2.0 (Core con `text()` — no hay modelos ORM,
y no hace falta crearlos), Alembic, Postgres 16, pytest. Idioma del código, comentarios
y tests: castellano rioplatense, mismo tono que `app/db.py` y `app/core/evaluacion.py`.

## Verdad del schema

`docs_schema_actual.sql` (dump real de la base) + `migrations/versions/0002_*.py`.
Nombres de columnas y valores de enum salen de ahí, no se inventan. Si necesitás una
columna/tabla que no existe: agregá una migración nueva `migrations/versions/000N_*.py`
con nombre único (prefijo con tu pieza, ej. `0003_worker_*.py`), con RLS ENABLE+FORCE
+ policy igual que 0002, y `GRANT ... TO modulo1_app`. NO edites 0001 ni 0002. Cada
migración nueva se aplica con `.venv/Scripts/alembic upgrade head` — corré eso vos.

Recordar: FORCE RLS aplica también al owner → una migración no puede hacer
UPDATE/INSERT de datos sobre tablas tenant-scoped (usar DEFAULT en DDL si hace falta).

## Reglas duras (violarlas es bug)

1. **tenant_id solo desde `Identidad`** (`app/auth/identidad.py`), que viene del JWT.
   Nunca de query/body/header. Toda sesión se abre con
   `with tenant_session(identidad.tenant_id) as s:` (`app/db.py`). Nunca `SessionLocal()`
   directo salvo en `platform_session` para `plataforma.*`.
2. **"Hoy" = `app/comun/reloj.py::hoy_del_tenant(session, tenant_id)`**. Prohibido
   `date.today()` / `datetime.now()` sin tz en código de dominio. `vigente_hasta` es
   inclusive.
3. **Motor puro no se toca**: `app/core/evaluacion.py` y `app/core/tipos.py` se USAN, no
   se modifican. Los 5 casos de oro (`tests/test_casos_de_oro.py`) tienen que seguir en
   verde después de tu trabajo.
4. **Permisos por rol**: cada comando llama `identidad.exigir_rol(Rol.X, ...)` según la
   matriz (abajo). Un rol exclusivo es exclusivo.
5. **Eventos**: `app/comun/eventos.py::registrar_evento(...)` para TODO evento de dominio
   (mismo nombre que el catálogo, abajo), en la misma transacción. Solo
   `HabilitacionRequiereRevaluacion` y `CumplimientoEmpresaAfectado` van además a
   `encolar_outbox(...)`. Nunca publicar directo.
6. **Idempotencia**: los POST /comandos/* leen header `Idempotency-Key` y usan
   `app/comun/idempotencia.py`. ImportarLote es idempotente por `lote_id` del body.
7. **Errores**: levantar `ErrorDeDominio` / `NoEncontrado` / `Conflicto` / `Prohibido` /
   `NoAutenticado` de `app/api/errores.py`. Nunca `HTTPException` a mano.
8. **API**: `POST /v1/comandos/<NombreDelComando>` (mismo nombre del catálogo, en
   snake_case: `cargar_documento`), `GET /v1/consultas/<nombre>`. Paginación con
   `app/comun/paginacion.py`. Respuesta de comando: JSON con los ids generados +
   `eventos: [nombres]`.
9. **Sin ORM declarativo**: SQL explícito con `text()` y parámetros bind. Nunca f-strings
   con datos del usuario en SQL.
10. **Tests con base real**: `tests/conftest.py` da `tenant_de_prueba` (crea tenant +
    usuario por rol y limpia al final) y `cliente_api` (TestClient con token). Usalos.
    Todos los tests tienen que pasar con `.venv/Scripts/python -m pytest -q`.

## Contrato de auth (lo construye la pieza Auth; el resto lo consume)

```python
from app.auth.dependencies import identidad_actual   # Depends → Identidad
from app.auth.identidad import Identidad, Rol
```
Hasta que Auth termine, `tests/conftest.py` provee `token_para(tenant_id, usuario_id,
roles, sujeto_id)` firmando con `settings.jwt_secret`, claims:
`{"sub": usuario_id, "tenant_id": ..., "roles": [...], "sujeto_id": ..., "exp": ...}`.
Auth DEBE respetar exactamente esos claims.

## Matriz de permisos por comando (2.2 de no-funcionales)

| Comando | configuracion | responsable_legajos | supervisor | tecnico |
|---|---|---|---|---|
| CargarDocumento | | ✓ | | |
| ProponerDocumento | | | | ✓ (solo su propio legajo) |
| ConfirmarDocumento / RechazarPropuesta | | ✓ | | |
| RegistrarAcreditacionDeCompetencia / RegistrarInduccion | | ✓ | | |
| AltaDeSujeto / BajaDeSujeto | | ✓ | | |
| ImportarLote / RevertirLote | | ✓ | | |
| DarDeAltaDefinicionDeRequisito / DarDeBajaDefinicionDeRequisito | ✓ | | | |
| PublicarVersionDeMatriz | ✓ | | | |
| CargarRequisitoParticular | | ✓ | | |
| CambiarCustodia / CorregirCustodia | | | ✓ | |
| OtorgarExcepcion / RevocarExcepcion | | | ✓ | |
| RegistrarConstanciaDelCliente / RevocarConstanciaDelCliente | | ✓ | | |
| AsignarSupervisor / ReasignarSupervisor | ✓ | ✓ | | |
| Verificar habilitación (consulta) | | ✓ | ✓ | |
| Tablero vencimientos/cobertura | | ✓ (toda la empresa) | ✓ (su universo) | |
| DescargarArchivoDeEvidencia | | ✓ | ✓ (su universo) | ✓ (propio) |
| VerLogDeAuditoria | ✓ | ✓ | | |

"Su universo" del supervisor = sujetos con `asignacion_supervisor` vigente hacia él
(+ vehículos/equipos bajo custodia de esos sujetos).

## Invariantes de dominio (resumen; el detalle está en el motor)

- A lo sumo un Documento `estado_version=vigente` por (sujeto, requisito) → índice
  `uq_documento_vigente`. Cargar uno nuevo sucede al anterior (`sucedida`, evento
  `DocumentoSucedido`).
- RechazarPropuesta solo si `origen_propuesta=true` y `estado_confirmacion=declarado`;
  `rechazada` es terminal.
- ConfirmarDocumento: declarado → verificado (evento `DocumentoVerificado`). Si cubre el
  requisito de una Excepción `otorgada` del mismo sujeto → esa excepción pasa a
  `regularizada` (evento `ExcepcionRegularizada`) automáticamente.
- Matriz: versiones no se superponen; `validar_nueva_version_matriz` decide; al aceptar,
  cerrar la anterior a `vigente_desde - 1` en la misma transacción. Evento
  `MatrizVersionPublicada`.
- Excepción solo sobre requisito `excepcionable` (según la línea de matriz vigente para
  el compromiso, o requisito particular); Constancia solo sobre `bloqueante_duro`.
- Excepción nunca vuelve verde: `ck_excepcion_nunca_verde`.
- Constancia específica terminal anula la general SOLO para ese commitment_id.
- Excepción sobre requisito reclasificado a bloqueante_duro: sigue `otorgada`, sin efecto.
- Lote: ImportarLote una transacción, idempotente por `lote_id` (si ya existe, devolver el
  resultado guardado sin re-aplicar). RevertirLote solo sobre `aplicado`; documentos del
  lote pasan a `revertida_por_lote` y el vigente anterior (`sucedida` por ese lote) vuelve
  a `vigente`.
- Custodia: un solo `periodo_custodia` vigente por custodia (`uq_periodo_custodia_vigente`).
  CambiarCustodia cierra el vigente (`hasta` = día anterior al nuevo `desde`) y abre uno
  nuevo. CorregirCustodia marca el período como `corregido` (con `corregido_por` apuntando
  al nuevo) sin borrar historia.

## Catálogo de eventos (nombres exactos)

LegajoCreado, LegajoDadoDeBaja, DocumentoCargado, DocumentoSucedido, DocumentoVerificado,
DocumentoRechazado, AcreditacionDeCompetenciaRegistrada, InduccionRegistrada,
LoteAplicado, LoteRevertido, SupervisorAsignado, SupervisorReasignado,
DefinicionDeRequisitoDadaDeAlta, DefinicionDeRequisitoDadaDeBaja,
MatrizVersionPublicada, RequisitoParticularCargado, CustodiaCambiada, CustodiaCorregida,
ExcepcionOtorgada, ExcepcionRevocada, ExcepcionRegularizada, ExcepcionVencida,
ConstanciaRegistrada, ConstanciaRevocada, ConstanciaReemplazada, ConstanciaVencida,
EvaluacionDeHabilitacionRealizada, AlertaDeVencimientoAbierta, AlertaEscalada,
AlertaPausada, AlertaResuelta, AvisoDeRevaluacionAbierto, AvisoDeRevaluacionCerrado,
TareaDeRegularizacionCreada, ArchivoPurgado.
Outbox (Módulo 2): HabilitacionRequiereRevaluacion, CumplimientoEmpresaAfectado.

## Reparto de archivos (disjunto — no tocar los de otra pieza)

| Pieza | Archivos propios |
|---|---|
| Auth | `app/auth/jwt.py`, `app/auth/dependencies.py`, `app/auth/router.py`, `app/auth/passwords.py`, `tests/test_auth.py` |
| Comandos Evidencia+Requisitos | `app/modules/legajos/*`, `app/modules/requisitos/*`, `tests/test_comandos_legajos.py`, `tests/test_comandos_requisitos.py` |
| Comandos Operación + orquestación | `app/modules/operacion/*`, `app/core/orquestacion.py`, `tests/test_comandos_operacion.py`, `tests/test_orquestacion.py` |
| Consultas + backlog OC | `app/modules/consultas/*`, `app/modules/oc/*`, `tests/test_consultas.py`, `tests/test_oc.py` |
| Worker | `app/worker/*`, `app/storage/*`, `tests/test_worker.py`, `tests/test_storage.py`, migraciones `0003_worker_*` si hacen falta |

Compartidos (solo lectura): `app/db.py`, `app/config.py`, `app/api/*`, `app/comun/*`,
`app/auth/identidad.py`, `app/core/evaluacion.py`, `app/core/tipos.py`, `app/main.py`,
`tests/conftest.py`. Si necesitás algo ahí, dejalo escrito en tu informe final en vez de
editarlo.

## Interfaz de orquestación (la construye Operación; la consumen Consultas y Worker)

```python
# app/core/orquestacion.py
def evaluar_compromiso(session, tenant_id: str, commitment_id: str, ahora_utc: datetime,
                       usuario_id: str | None) -> dict
```
Evalúa la OC (`modulo1.oc.clave_origen == commitment_id`) en dos pasos: (1) empresa en su
conjunto (sujeto de tipo `empresa` del tenant, requisitos de la matriz vigente para
cliente+locación+tipo_servicio con `tipo_sujeto_aplicable='empresa'`); (2) cada tipo de
recurso exigido, sujeto por sujeto. Aplica constancias (`resolver_constancia_aplicable`)
y excepciones (`excepcion_tiene_efecto`), persiste una fila en
`evaluacion_habilitacion` (con `snapshot` completo), registra
`EvaluacionDeHabilitacionRealizada` y devuelve el dict persistido. El veredicto
agregado es el peor de los individuales (habilitado < vence_durante_el_trabajo <
requiere_revision < no_habilitado). Hasta que exista, los consumidores la importan de
forma tolerante (`try/except ImportError`) y marcan el test correspondiente como skip.

## Cómo entregar

- Código + tests en tus archivos. Corré `.venv/Scripts/python -m pytest -q` completo al
  final y pegá el resultado en tu informe.
- NO hagas commits ni `git add`; el integrador commitea.
- Informe final: qué endpoints/funciones creaste (lista), qué migración agregaste (si
  alguna), qué dejaste pendiente y por qué, y qué necesitarías de los archivos
  compartidos. Corto y concreto.
