# Espejo documental por operadora

## Objetivo

El legajo interno y el estado conocido por una operadora son realidades independientes.
El Módulo 1 conserva ambas y señala cualquier diferencia sin convertirla en una decisión
de planificación o asignación.

## Modelo relacional

No se crea una tabla `empleado` paralela: `legajo` es el maestro de sujetos y distingue
personas, vehículos y equipos mediante `tipo_sujeto`. Para personas representa al
empleado o técnico; así todas las clases de recurso comparten identidad, historial y
aislamiento por tenant sin duplicar relaciones.

- `legajo`: sujeto dueño del legajo;
- `definicion_requisito`: catálogo equivalente a TipoDocumento, con categorías
  `documento`, `competencia` e `induccion`;
- `documento`: hecho documental versionado y fuente canónica de vigencia;
- `documento_soporte`: archivos/documentos que prueban una competencia o inducción;
- `operadora_documental`: catálogo de operadoras;
- `operadora_legajo`: indica qué operadoras mantienen legajo del sujeto;
- `entrega_documento_operadora`: hecho de exportación, envío, aceptación o rechazo de
  una versión concreta;
- `alerta_actualizacion_operadora`: diferencia detectada entre la versión interna vigente
  y la versión conocida por cada operadora.

La migración `0023_documento_unificado` elimina las antiguas tablas separadas de
acreditaciones e inducciones. Las rutas con esos nombres continúan como comandos de
negocio compatibles, pero escriben en `documento` y `documento_soporte`.

## Regla principal

Cada combinación `operadora + sujeto + requisito` conserva qué versión documental fue
exportada, enviada, aceptada o rechazada. Cuando aparece una versión interna posterior,
el sistema no presume que la operadora la recibió.

Estados registrados de una entrega:

- `exportado`: se generó la salida, pero no consta el envío;
- `enviado`: consta el envío, pero no la aceptación;
- `aceptado`: la operadora aceptó esa versión;
- `rechazado`: la operadora rechazó esa versión.

Estados calculados de la diferencia:

- `pendiente_envio`: la versión vigente interna no fue registrada ante la operadora;
- `pendiente_aceptacion`: fue exportada o enviada, pero no aceptada;
- `rechazado`: la versión vigente fue rechazada;
- `resuelta`: la operadora aceptó la misma versión que está vigente internamente.

## Trazabilidad de Excel

El registro puede conservar `fuente_archivo`, `fuente_hoja` y `fuente_fila`. El backend
recibe filas normalizadas; la lectura física del libro Excel corresponde al adaptador de
importación del frontend o de integración. Importar una fila nunca reemplaza el historial
de versiones del legajo.

## Alertas

La alerta es única por `operadora + sujeto + requisito + versión interna`. No se recrea
al abrir una pantalla. Se notifica al rol `responsable_legajos` y, cuando existe, al
supervisor vigente del sujeto. Los cambios significativos de estado pueden emitir una
nueva notificación; aceptar la versión vigente cierra la alerta.

## Pantallas

`Vencimientos` presenta por separado:

1. vencimientos internos del legajo;
2. actualizaciones pendientes ante operadoras.

El primer bloque responde si el documento interno está vigente. El segundo responde si
cada operadora posee y aceptó esa misma versión.

