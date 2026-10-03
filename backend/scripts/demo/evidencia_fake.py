"""PDF/JPG de demo con marca DEMO – SIN VALIDEZ."""
from __future__ import annotations


def pdf_demo(recurso: str, requisito: str) -> bytes:
    texto = f"DEMO – SIN VALIDEZ | {recurso} | {requisito}"
    contenido = f"BT /F1 12 Tf 72 712 Td ({texto[:120]}) Tj ET".encode("latin-1", errors="replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 612 792] /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
    ]
    cuerpo = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
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


def jpg_demo(recurso: str, requisito: str) -> bytes:
    import base64

    _ = f"DEMO – SIN VALIDEZ | {recurso} | {requisito}"
    return base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wCEAAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
        "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQH/"
        "wAARCAABAAEDAREAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAA"
        "AAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA"
        "/9oADAMBAAIQAxAAAAGAAP/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAQUCf//EABQRAQ"
        "AAAAAAAAAAAAAAAAAAAAD/2gAIAQMBAT8Bf//EABQRAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQIE"
        "AT8Bf//EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEABj8Cf//Z"
    )
