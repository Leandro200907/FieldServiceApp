from app.modules.evidencia.motivos_usuario import motivo_validacion_para_usuario


def test_motivo_invalidacion_manual_sin_rol():
    m = motivo_validacion_para_usuario("invalidado manualmente por responsable_legajos: Evidencia demo invalidada")
    assert "responsable" not in m.lower()
    assert "Evidencia demo invalidada" in m


def test_motivo_formato_no_reconocible_es_entendible():
    m = motivo_validacion_para_usuario("el archivo no tiene un formato reconocible (PDF/JPEG/PNG/WEBP)")
    assert "dañado" in m.lower() or "válido" in m.lower()
    assert "foto" in m.lower()
