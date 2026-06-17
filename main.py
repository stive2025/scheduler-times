"""
=============================================================================
PIPELINE COMPLETO SEFIL
=============================================================================
Ejecuta los 4 pasos en orden, deteniendo la cadena si alguno falla:

  1. Obtener_eventos_1.py     → accesos_validos.xlsx
  2. Ordenar_eventos_2.py     → reporte_asistencias.xlsx
  3. Generar_informe_3.py     → output_sefil/
  4. Gestionar_justificaciones_4.py → output_sefil_justificaciones/

Nota: el paso 4 crea justificaciones.xlsx la primera vez que no existe;
edita ese archivo y vuelve a ejecutar este script (o solo el paso 4).
=============================================================================
"""

import sys
import subprocess
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).parent

PASOS = [
    ("1/4", "Obtener_eventos_1.py",          "Descargando eventos del dispositivo"),
    ("2/4", "Ordenar_eventos_2.py",           "Ordenando y clasificando marcaciones"),
    ("3/4", "Generar_informe_3.py",           "Generando informe de asistencias"),
    ("4/4", "Gestionar_justificaciones_4.py", "Aplicando justificaciones"),
]


def ejecutar_paso(paso: str, script: str, descripcion: str) -> None:
    print(f"\n{'═' * 65}")
    print(f"   PASO [{paso}]  {descripcion}")
    print(f"   → {script}")
    print("═" * 65 + "\n")

    result = subprocess.run(
        [sys.executable, BASE_DIR / script],
        cwd=BASE_DIR,
    )

    if result.returncode not in (0, None):
        print(f"\n  ❌  {script} terminó con error (código {result.returncode}).")
        print("      Pipeline detenido.\n")
        sys.exit(result.returncode)


def main():
    print("\n" + "═" * 65)
    print("   PIPELINE COMPLETO SEFIL")
    print("═" * 65)

    for paso, script, desc in PASOS:
        ejecutar_paso(paso, script, desc)

    print("\n" + "═" * 65)
    print("   ✅  TODOS LOS PASOS COMPLETADOS")
    print("═" * 65 + "\n")


if __name__ == "__main__":
    main()
