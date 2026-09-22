# Auditoría de main — db400e6

Fecha: 2026-09-22. Commit auditado: `db400e60975f132ac783640ce33214e645d36876`.

**Resultado: no aprobado todavía para continuar la integración del frontend.** Se revisaron los cambios respecto de `98a9c5d`, el contrato, los hallazgos anteriores y los puntos críticos asociados. Esta revisión no certifica exhaustivamente todo el backend ni integraciones externas.

## A-01 — Alta: programar una custodia futura retira acceso al custodio actual

Archivos: `app/modules/operacion/servicio.py` (`cambiar_custodia`), `app/auth/alcance.py` (`recursos_bajo_custodia`, `_SQL_UNIVERSO`) y `app/modules/consultas/catalogos.py` (`mi_legajo`).

`cambiar_custodia` cierra inmediatamente el período anterior, fijando `hasta = desde_nuevo - 1 día`. Las consultas de alcance sólo admiten `estado = vigente`. La corrección nueva impide que el futuro custodio acceda antes de `desde`, pero el período del custodio actual queda excluido aunque todavía cubra la fecha de consulta.

Reproducción: persona A custodia desde 2026-09-01; se programa transferencia a B para 2026-10-01. El 2026-09-22 A debe conservar el recurso y B no debe verlo. Resultado observado: ambos reciben lista vacía.

Archivo ejecutable: `audit/repro_custodia_db400e6.py`. Ejecuta el predicado SQL real sobre tablas mínimas SQLite para aislar el problema lógico; NO sustituye pruebas PostgreSQL ni verifica RLS. La transición que produce esas filas se comprobó en el código de `cambiar_custodia`.

Corrección requerida: consultar períodos efectivos en la fecha civil del tenant (inicio inclusivo, fin inclusivo o abierto), incluyendo períodos cerrados que todavía cubren la fecha y excluyendo los corregidos. Mantener el mismo criterio en alcance propio, supervisado y vista compuesta. Agregar regresión PostgreSQL con transferencia futura y los dos bordes. Los tests actuales de custodia futura sólo cubren una primera asignación, no la transferencia de una custodia existente.

## A-02 — Media: reglas de proyección todavía contradictorias

Archivo: `docs/PROYECCION_DOCUMENTAL.md`, secciones 6 y 9.

1. La regla de `riesgo_documental` exige pérdida de TODA cobertura futura de algún tipo. El ejemplo conserva una persona y un vehículo válidos, pero devuelve riesgo y explica que queda un candidato de respaldo. Según la regla, ese ejemplo no justifica riesgo. Corregir ejemplo o acordar explícitamente una nueva regla; no introducir esa diferencia en el frontend.
2. `bloqueo_confirmado` dice «sólo HOY, nunca un día futuro», pero define el primer día de detalle como `max(hoy, oc.vigencia_desde)`. Para una OC futura ese primer día está en el futuro. Definir una fecha de referencia común para detalle y backlog, y probar una OC que todavía no comenzó.

Esto bloquea integración de calendario/proyección; no el diseño identificado como temporal.

## A-03 — Baja: respuesta 401 del storage omitida en contrato

Archivos: `app/openapi_extra.py` (`SIN_401`) y `app/storage/router.py` (`_exigir_tenant_del_token`).

La ruta firmada `/v1/storage/{firma}` no exige Bearer, correctamente. Sin embargo, si se envía un Bearer inválido, su validación puede producir `NoAutenticado`/401. Esa respuesta no figura en el OpenAPI porque storage pertenece a `SIN_401`. Mantener la ruta sin autenticación obligatoria y documentar el 401 opcional. Hallazgo por inspección del camino de ejecución, no prueba HTTP con archivo real.

## Correcciones anteriores comprobadas

- Roles, legajo y estado del usuario se reconstruyen desde la base en cada request protegido. Roles desconocidos se rechazan.
- Un módulo obligatorio ausente impide el arranque.
- OpenAPI servido y versionado usan enriquecimiento común; comparación completa aprobada.
- Login y refresh documentan 401; URLs firmadas no requieren Bearer en el contrato.
- Respuestas de negocio antes genéricas ahora tienen modelos Pydantic. Esto resuelve el vacío estructural anterior, pero requiere validar los datos de todos los recorridos con PostgreSQL.
- Se evita acceso anticipado a la primera custodia futura. La transferencia sigue pendiente según A-01.

## Pruebas y alcance de evidencia

Dependencias instaladas desde ambos archivos lock en entorno Python 3.12 separado.

Comando ejecutado desde backend:

```sh
python -m pytest tests/test_casos_de_oro.py tests/test_openapi_versionado.py tests/test_arranque_falla_rapido.py tests/test_env_file.py tests/test_auditoria_credenciales.py -k 'not worker_arranca' -q
```

Resultado: **21 aprobadas, 1 excluida**, dos advertencias de deprecación. La prueba excluida necesita PostgreSQL. No se ejecutaron aquí la suite completa, migraciones, concurrencia ni RLS: no hay PostgreSQL disponible en este entorno.

La consulta del conector a workflows del commit devolvió lista vacía; ese conector filtra ejecuciones disparadas por pull_request, por lo que esto no prueba que no existan otras ejecuciones o pruebas locales de Claude.

La reproducción A-01 falló con la aserción esperada y mostró ambas listas vacías. Ese fallo es evidencia del defecto, no un test aprobado.

## Contrato e impacto frontend

Contra `98a9c5d`: 85 operaciones antes y después, ninguna agregada ni eliminada, 83 operaciones con cambios de definición. El nuevo documento contiene 182 schemas.

Las consultas `calendario_vigencias`, `proyeccion_documental_backlog` y `proyeccion_documental` siguen ausentes del OpenAPI. El documento de proyección dice explícitamente que todavía no está implementado.

No promover este contrato como referencia integrada ni cerrar API_GAPS todavía. Tras corregir A-01 y validar PostgreSQL, regenerar tipos desde el commit aprobado y ajustar consumidores. Las tres consultas propuestas requieren un contrato implementado posterior para integrarse.

No se modificó código de main, no se integraron pantallas ni se cambió el estado de la PR frontend #1. No se etiqueta versión final.
