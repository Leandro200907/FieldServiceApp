"""Worker de Módulo 1 (8.5/8.6): cola nativa en Postgres, drenaje del outbox hacia
Módulo 2 y procesos de reloj. Proceso de sistema: itera tenants con
`modulo1.listar_tenants()` y abre una `tenant_session` por tenant — nunca BYPASSRLS.
"""
