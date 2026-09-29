"""Los secretos inseguros deben impedir el arranque, también en desarrollo."""
import pytest
from pydantic import ValidationError

from app.config import Settings


BASE = {
    "database_url": "postgresql+psycopg://app:clave@localhost/modulo1",
    "jwt_secret": "jwt-seguro-abcdefghijklmnopqrstuvwxyz-123456",
    "storage_secret": "storage-seguro-abcdefghijklmnopqrstuvwxyz-654321",
}


def crear(**cambios):
    return Settings(_env_file=None, **{**BASE, **cambios})


@pytest.mark.parametrize("campo", ["jwt_secret", "storage_secret"])
def test_rechaza_secretos_cortos(campo):
    with pytest.raises(ValidationError):
        crear(**{campo: "demasiado-corto"})


@pytest.mark.parametrize("campo", ["jwt_secret", "storage_secret"])
def test_rechaza_placeholders(campo):
    with pytest.raises(ValidationError):
        crear(**{campo: "CAMBIAR-por-un-secreto-aleatorio-largo"})


def test_rechaza_el_mismo_secreto_para_jwt_y_storage():
    with pytest.raises(ValidationError):
        crear(storage_secret=BASE["jwt_secret"])


def test_outbox_solo_admite_modo_deshabilitado_hasta_tener_transporte_real():
    with pytest.raises(ValidationError):
        crear(outbox_transport="log")
