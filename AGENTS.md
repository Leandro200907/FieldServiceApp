# Reglas para agentes de IA

Las reglas vinculantes viven en `.cursor/rules/reglas-proyecto.mdc`. Este archivo es un resumen
de las críticas. **Si este archivo y `.cursor/rules/` difieren, gana `.cursor/rules/`.**

`backend/docs/BRIEF_SUBAGENTES.md` está **obsoleto** (brief de la etapa de piezas en paralelo);
no usarlo como guía.

## Bases de datos y tests

- `fsm_demo` es la demo del usuario: **solo lectura**. Prohibido migrar, sembrar, escribir o
  correr pytest contra ella.
- Tests solo con `ENV_FILE=.env.test` y `--ignore=tests/test_sembrar_demo.py`. El sembrado demo
  se prueba solo en CI.
- Host siempre `127.0.0.1`.

## Calidad

- Si algo falla: listarlo y parar. No seguir adelante tapando el error.
- No aflojar tests: no borrar asserts, no `skip`/`xfail`, no asserts de «uno u otro resultado».
- Todo lo visible en pantalla tiene un test por el camino real (API real, no atajos).
- Reloj congelado: nada de `datetime.now()` / `date.today()` fuera de `app/comun/reloj.py`.

## Diseño

- El backend calcula estados, conteos y textos; el frontend solo los muestra.
- Todo dato entra por comandos de dominio que emiten eventos (el seed incluido).
- Todo problema visible en pantalla tiene una acción para resolverlo.

## Git y trabajo

- `git status` limpio al terminar.
- No mergear sin OK explícito del usuario.
- Un solo agente a la vez sobre el repo.
