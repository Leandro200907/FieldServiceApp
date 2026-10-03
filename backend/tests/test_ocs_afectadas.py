"""OCs afectadas por vencimiento durante el período de la OC."""
from datetime import date

from app.modules.consultas.ocs_afectadas import oc_en_curso, ordenar_ocs_afectadas, referencia_oc


def test_ordenar_ocs_en_curso_primero():
    hoy = date(2026, 10, 3)
    ocs = [
        referencia_oc({"clave_origen": "OC-B", "oc_id": "2", "vigencia_desde": date(2026, 10, 16), "vigencia_hasta": date(2026, 10, 22)}),
        referencia_oc({"clave_origen": "OC-A", "oc_id": "1", "vigencia_desde": date(2026, 9, 28), "vigencia_hasta": date(2026, 11, 2)}),
    ]
    ordenadas = ordenar_ocs_afectadas(ocs, hoy)
    assert [o["clave_origen"] for o in ordenadas] == ["OC-A", "OC-B"]
    assert oc_en_curso(ordenadas[0], hoy)

