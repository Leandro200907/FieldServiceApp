"""Helpers E-97: certificado de respaldo + registro inducción/competencia."""
from __future__ import annotations

from tests.test_comandos_legajos import _ok, _post
from tests.test_storage import _subir_completo


def certificado_subido(cliente_api, storage, tenant, persona_id: str, *, validar: bool = True) -> str:
    cert = _ok(
        _post(
            cliente_api,
            tenant,
            "responsable_legajos",
            "crear_certificado_respaldo",
            {"persona_id": persona_id},
        )
    )
    cert_id = cert["certificado_documento_id"]
    _subir_completo(cliente_api, storage, tenant, cert_id, validar=validar)
    return cert_id
