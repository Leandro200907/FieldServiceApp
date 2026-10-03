"""Salida final tabular del sembrado."""
from __future__ import annotations

from scripts.demo.contexto import EstadoTenant


PANTALLA_INICIO = {
    "configuracion": "configuracion",
    "responsable_legajos": "propuestas",
    "supervisor": "radar-documental",
    "tecnico": "mi-legajo",
}


def imprimir_tabla_usuarios(estados: list[EstadoTenant]) -> None:
    print("\n=== Usuarios demo (contraseña no se imprime) ===")
    print(f"{'Empresa':<22} {'Email':<42} {'Rol':<22} {'Inicio / notas'}")
    print("-" * 110)
    for est in estados:
        for u in sorted(est.usuarios, key=lambda x: (x.rol, x.email)):
            if not u.activo:
                continue
            inicio = PANTALLA_INICIO.get(u.rol, "perfil")
            extra = est.notas_supervisor.get(u.email, "")
            col = f"/{inicio}" + (f" — {extra}" if extra else "")
            print(f"{est.spec.slug:<22} {u.email:<42} {u.rol:<22} {col}")


def imprimir_paquetes(estados: list[EstadoTenant]) -> None:
    print("\n=== Paquetes de entrega vigentes ===")
    for est in estados:
        url = est.paquete_vigente_url or "(no generado)"
        print(f"{est.spec.slug}: {url}")


def imprimir_resumen(ctx_global) -> None:
    print("\n=== Notas ===")
    if not ctx_global.notas:
        print("(ninguna)")
    for n in ctx_global.notas:
        print(f"  - {n}")
    print("\n=== Pasos saltados o con fallas ===")
    if not ctx_global.fallas:
        print("(ninguno)")
    for f in ctx_global.fallas:
        print(f"  [falla] {f}")
    print("\n=== Hallazgos sobre la app ===")
    print("- POST /v1/comandos/asignar_supervisor no está expuesto; el sembrado usa legajos.asignar_supervisor.")
    print("  BITACORA/HANDOFF documentan el endpoint pero el código lo retiró (test_superficie_modulo1).")
    print("- definicion_requisito.plazo_aviso_dias no tiene comando que lo setee (solo configurar_alertas global).")
