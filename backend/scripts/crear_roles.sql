-- Roles de Módulo 1 (8.1 de arquitectura-tecnica, decisiones 1-2). Se ejecuta UNA vez por
-- servidor, con un superusuario o un rol con CREATEROLE, ANTES de `alembic upgrade head`.
-- Las contraseñas entran como variables de psql y son obligatorias — no hay default:
--
--   psql -U postgres -h localhost -v ON_ERROR_STOP=1 \
--        -v owner_password='...' -v app_password='...' -f scripts/crear_roles.sql
--
-- Si falta una variable, psql deja el literal `:'owner_password'` y el script falla.
\set ON_ERROR_STOP on

-- Las variables de psql no se expanden dentro de bloques DO: se pasan por set_config
-- (solo esta sesión, nunca persisten) y se leen con current_setting.
SELECT set_config('modulo1.owner_password', :'owner_password', false),
       set_config('modulo1.app_password', :'app_password', false);

DO $$
DECLARE
    pw_owner text := current_setting('modulo1.owner_password');
    pw_app   text := current_setting('modulo1.app_password');
BEGIN
    IF length(pw_owner) < 12 OR length(pw_app) < 12 THEN
        RAISE EXCEPTION 'owner_password y app_password deben tener al menos 12 caracteres';
    END IF;
    IF pw_owner = pw_app THEN
        RAISE EXCEPTION 'owner_password y app_password deben ser distintas';
    END IF;

    -- Owner de schemas y tablas: corre migraciones, NO tiene BYPASSRLS ni es superusuario.
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'modulo1_owner') THEN
        EXECUTE format('CREATE ROLE modulo1_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %L', pw_owner);
    ELSE
        EXECUTE format('ALTER ROLE modulo1_owner WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', pw_owner);
    END IF;

    -- Rol de aplicación: nunca owner, nunca BYPASSRLS. Los GRANT los hace cada migración.
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'modulo1_app') THEN
        EXECUTE format('CREATE ROLE modulo1_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %L', pw_app);
    ELSE
        EXECUTE format('ALTER ROLE modulo1_app WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD %L', pw_app);
    END IF;
END $$;

SELECT set_config('modulo1.owner_password', '', false), set_config('modulo1.app_password', '', false);
