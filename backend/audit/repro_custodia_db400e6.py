"""Reproduce el predicado temporal de custodia; no valida PostgreSQL ni RLS.
Ejecutar desde backend con PYTHONPATH=. python audit/repro_custodia_db400e6.py.
"""
from datetime import date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.auth.alcance import recursos_bajo_custodia

engine = create_engine('sqlite://')
with Session(engine) as session:
    session.execute(text("ATTACH DATABASE ':memory:' AS modulo1"))
    session.execute(text('CREATE TABLE modulo1.custodia_recurso (tenant_id TEXT, custodia_id TEXT, recurso_id TEXT)'))
    session.execute(text('CREATE TABLE modulo1.periodo_custodia (tenant_id TEXT, custodia_id TEXT, custodio_id TEXT, estado TEXT, desde DATE, hasta DATE)'))
    session.execute(text("INSERT INTO modulo1.custodia_recurso VALUES ('t', 'c', 'vehiculo')"))
    # Estado producido por cambiar_custodia al programar para el 1 de octubre.
    session.execute(text("INSERT INTO modulo1.periodo_custodia VALUES ('t', 'c', 'persona_actual', 'cerrado', '2026-09-01', '2026-09-30'), ('t', 'c', 'persona_futura', 'vigente', '2026-10-01', NULL)"))
    actual = recursos_bajo_custodia(session, 'persona_actual', date(2026, 9, 22))
    futura = recursos_bajo_custodia(session, 'persona_futura', date(2026, 9, 22))
    print({'fecha': '2026-09-22', 'custodio_actual': actual, 'custodio_futuro': futura})
    assert actual == ['vehiculo'], 'REGRESION: el custodio actual pierde acceso antes del 2026-10-01'
