"""Constantes de la base de demo (tenants, catálogos, requisitos)."""
from __future__ import annotations

from dataclasses import dataclass

ZONA_TENANT = "America/Argentina/Buenos_Aires"

ROLES = ("configuracion", "responsable_legajos", "supervisor", "tecnico")

OPERADORAS = ("YPF", "Vista", "Tecpetrol", "Pluspetrol")
LOCACIONES_POR_OPERADORA = 2
TIPOS_SERVICIO = ("Wireline", "Slickline", "Cementación")

# Nombres locales (tenants que no copian del global)
REQUISITOS_LOCALES: list[dict] = [
    {"nombre": "Apto médico", "categoria": "documento", "tipo_sujeto_aplicable": "persona"},
    {"nombre": "Constancia ART", "categoria": "documento", "tipo_sujeto_aplicable": "persona"},
    {"nombre": "Licencia de conducir", "categoria": "documento", "tipo_sujeto_aplicable": "persona"},
    {"nombre": "Curso de manejo defensivo", "categoria": "competencia", "tipo_sujeto_aplicable": "persona"},
    {"nombre": "Inducción operadora", "categoria": "induccion", "tipo_sujeto_aplicable": "persona"},
    {"nombre": "VTV", "categoria": "documento", "tipo_sujeto_aplicable": "vehiculo"},
    {"nombre": "Seguro automotor", "categoria": "documento", "tipo_sujeto_aplicable": "vehiculo"},
    {"nombre": "Certificación de equipo", "categoria": "documento", "tipo_sujeto_aplicable": "equipo"},
    {"nombre": "ART empresa", "categoria": "documento", "tipo_sujeto_aplicable": "empresa"},
    {"nombre": "Seguro de responsabilidad civil", "categoria": "documento", "tipo_sujeto_aplicable": "empresa"},
]

# Mapeo nombre demo → nombre en plataforma.definicion_requisito_global (base_v1.json)
GLOBAL_A_DEMO: dict[str, str] = {
    "Apto médico": "Apto médico",
    "Constancia ART": "Constancia de cobertura ART (nómina)",
    "Licencia de conducir": "Licencia de conducir",
    "Curso de manejo defensivo": "Manejo defensivo",
    "Inducción operadora": "Inducción HSE de la operadora",
    "VTV": "VTV / RTO",
    "Seguro automotor": "Seguro del vehículo",
    "Certificación de equipo": "Certificación de arnés / línea de vida",
    "ART empresa": "Certificado de cobertura ART",
    "Seguro de responsabilidad civil": "Seguro de responsabilidad civil",
}

NOMBRES_PERSONA = (
    ("María", "Acosta"),
    ("Lucas", "Benítez"),
    ("Camila", "Cáceres"),
    ("Diego", "Domínguez"),
    ("Florencia", "Espinoza"),
    ("Gonzalo", "Fernández"),
    ("Helena", "Giménez"),
    ("Iván", "Herrera"),
    ("Julieta", "Ibarra"),
    ("Kevin", "Juárez"),
    ("Laura", "Klein"),
    ("Martín", "López"),
    ("Nadia", "Mansilla"),
    ("Oscar", "Navarro"),
)


@dataclass(frozen=True)
class TenantDemo:
    slug: str
    nombre: str
    copiar_globales: bool


TENANTS: tuple[TenantDemo, ...] = (
    TenantDemo("patagonia-demo", "Patagonia Servicios Demo SA", True),
    TenantDemo("anelo-demo", "Añelo Field Demo SRL", False),
    TenantDemo("neuquen-demo", "Neuquén Wells Demo SA", False),
)
