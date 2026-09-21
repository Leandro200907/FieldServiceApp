-- Crea la base con el owner correcto. Ejecutar después de crear_roles.sql:
--   psql -U postgres -h localhost -v ON_ERROR_STOP=1 -v db=modulo1 -f scripts/crear_base.sql
SELECT format('CREATE DATABASE %I OWNER modulo1_owner', :'db') WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'db') \gexec
