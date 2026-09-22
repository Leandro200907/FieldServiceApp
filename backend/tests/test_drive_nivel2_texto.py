"""Reauditoría Fase 2 punto 4: extracción Drive en dos niveles. Nivel 1 (nombre de
archivo) ya está cubierto en test_h01_capacidades_v1.py; acá el nivel 2 (texto embebido
del PDF), conservador — sujeto, requisito y fecha tienen que resolver a EXACTAMENTE uno
cada uno, cualquier ambigüedad va a bandeja — y el caso "sin capa de texto" (escaneado)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import text

from app.db import tenant_session
from app.modules.drive.proveedor import ArchivoRemoto, ProveedorEnMemoria
from app.modules.drive.servicio import _extraer_de_texto, _fechas_en_texto, _texto_pdf, extraer


def _pdf_con_texto(texto: str) -> bytes:
    """PDF mínimo válido, a mano (sin dependencias nuevas para tests): un objeto de
    contenido con un único `Tj` — suficiente para que `pypdf` extraiga texto real."""
    contenido = f"BT /F1 12 Tf 72 712 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
    ]
    cuerpo = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objetos, start=1):
        offsets.append(len(cuerpo))
        cuerpo += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref_offset = len(cuerpo)
    n = len(objetos) + 1
    xref = f"xref\n0 {n}\n0000000000 65535 f \n".encode()
    for off in offsets:
        xref += f"{off:010d} 00000 n \n".encode()
    cuerpo += xref
    cuerpo += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return bytes(cuerpo)


def _remoto(id_, nombre, mime="application/pdf"):
    return ArchivoRemoto(id_, nombre, mime, datetime(2026, 9, 1, tzinfo=timezone.utc), f"h-{id_}", 100)


# --------------------------------------------------------------------------- helpers puros


def test_texto_pdf_extrae_contenido_real():
    assert "hola mundo" in _texto_pdf(_pdf_con_texto("hola mundo")).lower()


def test_texto_pdf_vacio_ante_bytes_no_validos():
    assert _texto_pdf(b"esto no es un pdf") == ""


def test_fechas_en_texto_reconoce_iso_y_dma_sin_duplicar():
    assert _fechas_en_texto("vence el 2027-06-30, o sea 30/06/2027") == [date(2027, 6, 30)]
    assert _fechas_en_texto("emitido 01/03/2026, vence 30/06/2027") == [date(2026, 3, 1), date(2027, 6, 30)]
    assert _fechas_en_texto("sin fechas acá") == []
    assert _fechas_en_texto("fecha imposible: 2027-13-40") == []


# --------------------------------------------------------------------------- nivel 2 end-to-end (extraer)


def test_pdf_sin_convencion_de_nombre_se_resuelve_por_texto(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) VALUES (:t, 'persona_x', 'persona', 'DNI 40111222')"),
                  {"t": t.tenant_id})
        req = s.execute(text("INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                             "VALUES (:t, 'Apto médico', 'documento', 'persona') RETURNING requisito_definicion_id"), {"t": t.tenant_id}).scalar()
    contenido = _pdf_con_texto("Certificado de Apto medico. Titular: DNI 40111222. Vence: 30/06/2027.")
    prov = ProveedorEnMemoria(carpetas={"c": []}, contenidos={"x1": contenido})
    archivo = _remoto("x1", "certificado_sin_convencion.pdf")

    with tenant_session(t.tenant_id) as s:
        confianza, ext, motivo = extraer(s, t.tenant_id, archivo, prov)
    assert confianza == "alta" and ext["nivel"] == "texto_pdf" and motivo is None
    assert ext["sujeto_id"] == "persona_x" and ext["requisito_definicion_id"] == str(req)
    assert ext["vigente_hasta"] == "2027-06-30"


def test_dos_fechas_en_el_texto_queda_en_bandeja_no_se_adivina(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) VALUES (:t, 'persona_x', 'persona', 'DNI 40111222')"),
                  {"t": t.tenant_id})
        s.execute(text("INSERT INTO modulo1.definicion_requisito (tenant_id, nombre, categoria, tipo_sujeto_aplicable) "
                       "VALUES (:t, 'Apto médico', 'documento', 'persona')"), {"t": t.tenant_id})
    contenido = _pdf_con_texto("Apto medico DNI 40111222. Emitido 01/07/2026. Vence: 30/06/2027.")
    prov = ProveedorEnMemoria(carpetas={"c": []}, contenidos={"x1": contenido})
    archivo = _remoto("x1", "certificado_sin_convencion.pdf")

    with tenant_session(t.tenant_id) as s:
        confianza, ext, motivo = extraer(s, t.tenant_id, archivo, prov)
    assert confianza == "media" and "no se sabe cuál es el vencimiento" in motivo
    assert len(ext["fechas_candidatas"]) == 2


def test_dos_sujetos_reconocibles_en_el_texto_queda_en_bandeja(tenant_de_prueba):
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) VALUES "
                       "(:t, 'persona_x', 'persona', 'Juan Perez'), (:t, 'persona_y', 'persona', 'Juan Perez Gomez')"),
                  {"t": t.tenant_id})
    contenido = _pdf_con_texto("A nombre de Juan Perez Gomez, vence 30/06/2027")
    prov = ProveedorEnMemoria(carpetas={"c": []}, contenidos={"x1": contenido})
    archivo = _remoto("x1", "cert.pdf")

    with tenant_session(t.tenant_id) as s:
        confianza, ext, motivo = extraer(s, t.tenant_id, archivo, prov)
    assert confianza in ("media", "baja") and "sujeto" in motivo
    assert len(ext["sujetos_candidatos"]) == 2


def test_pdf_sin_capa_de_texto_queda_en_bandeja_con_aviso_de_ocr(tenant_de_prueba):
    """Simula un PDF escaneado: bytes que no son un PDF real (pypdf no extrae nada) —
    mismo resultado observable que un PDF-imagen sin texto: cadena vacía, nunca lanza."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        s.execute(text("INSERT INTO modulo1.legajo (tenant_id, sujeto_id, tipo_sujeto, identificador_natural) VALUES (:t, 'persona_x', 'persona', 'Juan Perez')"),
                  {"t": t.tenant_id})
    prov = ProveedorEnMemoria(carpetas={"c": []}, contenidos={"x1": b"no es un pdf de verdad"})
    archivo = _remoto("x1", "escaneo.pdf")

    with tenant_session(t.tenant_id) as s:
        confianza, ext, motivo = extraer(s, t.tenant_id, archivo, prov)
    assert confianza == "baja" and "requiere OCR" in motivo and "no sigue la convención" in motivo


def test_sin_proveedor_solo_nivel_1_como_antes(tenant_de_prueba):
    """Sin `proveedor` (p. ej. un llamador que sólo quiere reclasificar por nombre), el
    nivel 2 ni se intenta — comportamiento idéntico al que había antes de este punto."""
    t = tenant_de_prueba
    with tenant_session(t.tenant_id) as s:
        confianza, ext, motivo = extraer(s, t.tenant_id, _remoto("x1", "no_seguido_de_convencion.pdf"))
    assert confianza == "baja" and motivo == "el nombre no sigue la convención"


def test_pdf_que_no_es_pdf_por_extension_ni_mime_no_activa_nivel_2(tenant_de_prueba):
    t = tenant_de_prueba
    prov = ProveedorEnMemoria(carpetas={"c": []}, contenidos={})
    archivo = _remoto("x1", "foto.jpg", mime="image/jpeg")
    with tenant_session(t.tenant_id) as s:
        confianza, ext, motivo = extraer(s, t.tenant_id, archivo, prov)
    assert confianza == "baja" and motivo == "el nombre no sigue la convención"
    assert prov.descargas == []  # nunca se intentó bajar algo que no es PDF
