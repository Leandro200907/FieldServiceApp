"""D16: paquete público no expone propuestas sin confirmar como vigentes."""
from __future__ import annotations

from tests.test_comandos_legajos import _alta_def, _alta_persona, _cargar, _ok, _post


def _token_paquete(cliente_api, t, persona: str) -> str:
    r = _ok(_post(cliente_api, t, "responsable_legajos", "generar_paquete_entrega", {"sujeto_id": persona}))
    return r["url"].rsplit("/", 1)[1]


def _estados_paquete(cliente_api, token: str) -> dict[str, str]:
    pub = cliente_api.get(f"/v1/publico/paquete/{token}")
    assert pub.status_code == 200, pub.text
    cuerpo = pub.json()
    return {x["requisito"]: x["estado"] for x in cuerpo["requisitos"]}, cuerpo


def test_d16_paquete_publico_usa_confirmada_si_hay_propuesta(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Licencia paquete D16")
    persona = _alta_persona(cliente_api, t, "DNI-PKG-D16-A", t.sujeto_tecnico)
    _cargar(cliente_api, t, persona, req, desde="2026-09-01", hasta="2026-12-31")
    _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2027-01-01",
                "vigente_hasta": "2028-01-01",
            },
        )
    )
    token = _token_paquete(cliente_api, t, persona)
    estados, cuerpo = _estados_paquete(cliente_api, token)
    assert estados["Licencia paquete D16"] == "vigente"
    item = next(x for x in cuerpo["requisitos"] if x["requisito"] == "Licencia paquete D16")
    assert item["vigente_hasta"] == "2026-12-31"
    assert cuerpo["resumen"]["pendiente_revision"] == 0


def test_d16_paquete_publico_solo_propuesta_pendiente_de_revision(cliente_api, tenant_de_prueba):
    t = tenant_de_prueba
    req = _alta_def(cliente_api, t, "Solo propuesta paquete D16")
    persona = _alta_persona(cliente_api, t, "DNI-PKG-D16-B", t.sujeto_tecnico)
    _ok(
        _post(
            cliente_api,
            t,
            "tecnico",
            "proponer_documento",
            {
                "sujeto_id": persona,
                "requisito_definicion_id": req,
                "vigente_desde": "2026-09-01",
                "vigente_hasta": "2027-09-01",
            },
        )
    )
    token = _token_paquete(cliente_api, t, persona)
    estados, cuerpo = _estados_paquete(cliente_api, token)
    assert estados["Solo propuesta paquete D16"] == "pendiente_de_revision"
    assert cuerpo["resumen"]["pendiente_revision"] == 1
    assert cuerpo["resumen"]["vigentes"] == 0
