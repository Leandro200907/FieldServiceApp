# Revisión de correcciones e59a0e3

Fecha: 2026-09-22. Rama revisada: `backend/audit-fixes-db400e6`.
Commit: `e59a0e38a7017049a2da0616c4691466172d27b4`.
Base: `db400e60975f132ac783640ce33214e645d36876`.

## Dictamen

A-01 y A-03 corregidos en el código revisado. A-02 parcialmente corregido: queda una inconsistencia de ventana temporal y un ejemplo de backlog desactualizado. No aprobar todavía el documento de proyección como contrato implementable.

Estos pendientes documentales no invalidan las correcciones de custodias/storage ni impiden avanzar el frontend estable. No se realizó merge, no se abrió PR y no se promovió un contrato activo del frontend. La decisión de integrar la rama queda pendiente.

## Evidencia independiente

- La reproducción de A-01 que fallaba en db400e6 ahora pasa sobre el código de e59a0e3: el 2026-09-22 el custodio actual conserva `vehiculo` y el futuro recibe lista vacía. Esta reproducción aísla el SQL de lectura usando SQLite; no certifica PostgreSQL/RLS.
- Condición compartida: estados vigente/cerrado, inicio inclusivo y fin inclusivo o abierto. Excluye corregido. Se aplica en recursos propios, universo supervisado, helper de período de mi_legajo y destinatario de alertas.
- Se revisaron las cuatro regresiones nuevas con PostgreSQL, incluyendo transferencia y fecha de inicio. No se ejecutaron aquí por falta de PostgreSQL local.
- Se revisó el test HTTP de storage con Bearer inválido para PUT/GET y el cambio de SIN_401. El Bearer continúa siendo opcional.
- Pruebas ejecutadas aquí: **21 passed, 1 deselected** (worker necesita PostgreSQL), dos advertencias de deprecación.
- Recolección independiente: **533 tests collected**. Esto confirma el número de casos, no que los 533 hayan pasado en este entorno.
- Resultado comunicado por Claude: **533 passed, 0 failed, 0 skipped/excluidos**, sobre PostgreSQL real. Se registra como resultado externo reportado, no como ejecución independiente propia.
- Verificado remotamente: main permanece en db400e6.

Comando de pruebas seleccionadas:

```sh
python -m pytest tests/test_casos_de_oro.py tests/test_openapi_versionado.py tests/test_arranque_falla_rapido.py tests/test_env_file.py tests/test_auditoria_credenciales.py -k 'not worker_arranca' -q
```

## OpenAPI

85 operaciones, sin altas ni bajas. Únicas operaciones modificadas: GET y PUT `/v1/storage/{firma}`, por incorporar 401 con ErrorEnvelope. Los schemas de components son idénticos a db400e6. Comparación del OpenAPI versionado contra la app aprobada dentro de las 21 pruebas.

No existen rutas de calendario/proyección. El cambio documental no habilita su integración. Al promover el contrato del frontend se deben regenerar los tipos con esta versión o con el commit finalmente integrado, aunque los schemas de datos no hayan cambiado.

## A-02: pendientes documentales concretos

Archivo: `backend/docs/PROYECCION_DOCUMENTAL.md`.

1. **Ventana del backlog contradictoria.** La sección 7, paso 2, dice que el primer intervalo de proyeccion_documental_backlog empieza en hoy. La sección 10 establece `desde = max(hoy, oc.vigencia_desde)` y exige equivalencia con el detalle. Para una OC futura son fechas diferentes. Usar la fórmula de la sección 10 en ambos lugares.
2. **Horizonte de una OC lejana.** La sección 10 fija `hasta = min(oc.vigencia_hasta, desde + horizonte_dias)` pero luego afirma que una OC que comienza después de `hoy + horizonte_dias` produce `desde > hasta`. Eso no se deriva de la fórmula: con OC válida y horizonte positivo, el rango continúa siendo válido aunque la OC sea lejana. Elegir ventana relativa al inicio evaluado o ventana global relativa a hoy y eliminar la afirmación incompatible. No resolverlo en el frontend.
3. **Ejemplo de backlog desactualizado.** Para OC-4587, la sección 9 corregida conserva cobertura el 2026-09-30 y pierde toda cobertura de persona el 2026-10-05. La sección 10 aún informa primer_quiebre 2026-09-30, y su fecha final tampoco coincide con la OC del ejemplo de detalle. Sin señalar escenarios distintos, los dos ejemplos contradicen la equivalencia prometida. Actualizar el backlog para mostrar el mismo caso.

La distinción nueva entre estado de intervalo y estado resumen sí resuelve el error principal anterior: tener un único candidato válido ya no se presenta como riesgo por sí solo. El ejemplo corregido de tres intervalos es consistente con esa regla.

## Recomendación

Conservar la rama sin merge por ahora y corregir estos tres puntos documentales antes de tomarla como referencia final. No hace falta reabrir A-01 ni A-03 ni frenar layout, componentes y pantallas estables por estos pendientes de proyección. Calendario y proyección permanecen temporales y sin integración hasta disponer de endpoints implementados y contrato validado.
