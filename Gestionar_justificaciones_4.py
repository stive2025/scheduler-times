"""
=============================================================================
GESTOR DE JUSTIFICACIONES — SEFIL
=============================================================================
Permite marcar atrasos o salidas anticipadas como justificados para que
no afecten los KPIs del reporte. No modifica los archivos originales.

Flujo de uso:
  1. Ejecuta este script por primera vez → crea justificaciones.xlsx
  2. Abre justificaciones.xlsx y rellena los casos a justificar
  3. Vuelve a ejecutar → genera output_sefil_justificaciones/Reporte_SEFIL.xlsx

Columnas de justificaciones.xlsx:
  Empleado  — ID del empleado (igual que en reporte_asistencias.xlsx)
  Fecha     — Fecha del evento  (YYYY-MM-DD  o  DD/MM/YYYY)
  Tipo      — Atraso_Man | Atraso_Tar | Atraso | Salida_Anticipada | Todos
  Motivo    — Descripción libre (cita médica, permiso autorizado, etc.)

Tipos de justificación:
  Atraso_Man       — Justifica solo el atraso de entrada en la mañana
  Atraso_Tar       — Justifica solo el atraso de entrada en la tarde
  Atraso           — Justifica todos los atrasos del día (Man + Tar)
  Salida_Anticipada— Justifica la salida anticipada del día
  Todos            — Justifica atrasos + salida anticipada
=============================================================================
"""

import sys
import warnings
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
from openpyxl import load_workbook

warnings.filterwarnings("ignore")

# ── Importar pipeline principal ───────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
import Generar_informe_3 as G                  # noqa: E402  (import after sys.path)

# ── Rutas ─────────────────────────────────────────────────────────────────────
ARCHIVO_JUSTIF  = BASE_DIR / "justificaciones.xlsx"
OUTPUT_DIR_J    = BASE_DIR / "output_sefil_justificaciones"
OUTPUT_DIR_J.mkdir(exist_ok=True)
OUT_XLS         = OUTPUT_DIR_J / "Reporte_SEFIL.xlsx"
OUT_WORD        = OUTPUT_DIR_J / "Reporte_SEFIL.docx"
OUT_PDF         = OUTPUT_DIR_J / "Reporte_SEFIL.pdf"

TIPOS_VALIDOS = {"atraso_man", "atraso_tar", "atraso", "salida_anticipada", "todos"}


# =============================================================================
# PLANTILLA
# =============================================================================

def crear_plantilla():
    """Genera justificaciones.xlsx con instrucciones y una fila de ejemplo."""
    ejemplo = pd.DataFrame([
        {
            "Empleado": "1104393788",
            "Fecha":    "2026-01-15",
            "Tipo":     "Atraso",
            "Motivo":   "Cita médica — EJEMPLO, borra esta fila",
        },
        {
            "Empleado": "750055378",
            "Fecha":    "2026-02-10",
            "Tipo":     "Salida_Anticipada",
            "Motivo":   "Emergencia familiar — EJEMPLO, borra esta fila",
        },
        {
            "Empleado": "1102529755",
            "Fecha":    "2026-03-05",
            "Tipo":     "Todos",
            "Motivo":   "Permiso autorizado — EJEMPLO, borra esta fila",
        },
    ])
    ejemplo.to_excel(ARCHIVO_JUSTIF, index=False)

    # Ajustar anchos de columna para mejor legibilidad
    wb = load_workbook(ARCHIVO_JUSTIF)
    ws = wb.active
    ws.column_dimensions["A"].width = 16   # Empleado
    ws.column_dimensions["B"].width = 14   # Fecha
    ws.column_dimensions["C"].width = 22   # Tipo
    ws.column_dimensions["D"].width = 45   # Motivo
    wb.save(ARCHIVO_JUSTIF)

    print(f"  Plantilla creada: {ARCHIVO_JUSTIF.name}")
    print("  Tipos válidos: Atraso_Man | Atraso_Tar | Atraso | Salida_Anticipada | Todos")


# =============================================================================
# CARGA DE JUSTIFICACIONES
# =============================================================================

def cargar_justificaciones() -> pd.DataFrame:
    """Lee justificaciones.xlsx y valida su contenido."""
    if not ARCHIVO_JUSTIF.exists():
        print(f"  No existe {ARCHIVO_JUSTIF.name}. Creando plantilla de ejemplo...")
        crear_plantilla()
        print("\n  ► Edita el archivo y vuelve a ejecutar este script.")
        sys.exit(0)

    df = pd.read_excel(ARCHIVO_JUSTIF)
    df.columns = df.columns.str.strip()

    # Normalizar
    df["Empleado"] = df["Empleado"].astype(str).str.strip()
    df["Fecha"]    = pd.to_datetime(df["Fecha"], errors="coerce", dayfirst=True)
    df["Tipo"]     = df["Tipo"].astype(str).str.strip()
    df["Motivo"]   = df.get("Motivo", pd.Series([""] * len(df))).fillna("").astype(str).str.strip()

    # Advertir tipos no reconocidos
    invalidos = df[~df["Tipo"].str.lower().isin(TIPOS_VALIDOS)]
    if not invalidos.empty:
        for _, r in invalidos.iterrows():
            print(f"  ⚠  Tipo '{r['Tipo']}' no reconocido (fila ignorada). "
                  f"Válidos: {', '.join(sorted(TIPOS_VALIDOS))}")

    # Filtrar filas válidas
    df = df[
        df["Tipo"].str.lower().isin(TIPOS_VALIDOS) &
        df["Fecha"].notna() &
        (df["Empleado"] != "nan")
    ].copy()

    print(f"  {len(df)} justificaciones válidas cargadas")
    return df


# =============================================================================
# APLICACIÓN DE JUSTIFICACIONES
# =============================================================================

def aplicar_justificaciones(df_kpi: pd.DataFrame,
                            df_justif: pd.DataFrame) -> pd.DataFrame:
    """
    Pone en 0 los minutos de atraso / salida anticipada para cada registro
    justificado. Añade columna 'Justificacion' con el motivo.
    Devuelve una copia del df_kpi ajustado; el original no se modifica.
    """
    df = df_kpi.copy()
    df["Justificacion"] = ""

    if df_justif.empty:
        return df

    aplicados = 0
    for _, j in df_justif.iterrows():
        mask = (
            (df["Empleado"].astype(str) == j["Empleado"]) &
            (df["Fecha"].dt.date == j["Fecha"].date())
        )

        if not mask.any():
            print(f"  ⚠  Sin registro: empleado {j['Empleado']} · {j['Fecha'].date()}")
            continue

        tipo   = j["Tipo"].lower()
        motivo = j["Motivo"] or "—"

        if tipo in ("atraso_man", "atraso", "todos"):
            df.loc[mask, "Atraso_Man_min"] = 0.0
        if tipo in ("atraso_tar", "atraso", "todos"):
            df.loc[mask, "Atraso_Tar_min"] = 0.0
        if tipo in ("salida_anticipada", "todos"):
            df.loc[mask, "Salida_Ant_min"] = 0.0

        # Recalcular total de atraso
        df.loc[mask, "Atraso_Total_min"] = (
            df.loc[mask, "Atraso_Man_min"] + df.loc[mask, "Atraso_Tar_min"]
        )

        df.loc[mask, "Justificacion"] = motivo
        nombre = df.loc[mask, "Nombre"].iloc[0]
        print(f"  ✓  {nombre} · {j['Fecha'].date()} · {j['Tipo']}: {motivo}")
        aplicados += 1

    print(f"  → {aplicados} registros ajustados "
          f"({len(df_justif) - aplicados} sin coincidencia)")
    return df


# =============================================================================
# EXPORTACIÓN DEL REPORTE AJUSTADO
# =============================================================================

def exportar_justificado(df_kpi_j: pd.DataFrame,
                         df_resumen_j: pd.DataFrame,
                         df_mensual_j: pd.DataFrame):
    """
    Genera el Excel ajustado reutilizando las funciones de Generar_informe_3
    y añade una hoja extra con el detalle de justificaciones aplicadas.
    """
    # Parchear rutas de salida temporalmente
    orig_xls, orig_word, orig_pdf = G.OUT_EXCEL, G.OUT_WORD, G.OUT_PDF
    G.OUT_EXCEL = OUT_XLS
    G.OUT_WORD  = OUT_WORD
    G.OUT_PDF   = OUT_PDF

    try:
        G.exportar_excel(df_kpi_j, df_resumen_j, df_mensual_j)
        word_p = G.exportar_word(df_resumen_j, df_mensual_j)
        G.exportar_pdf_con_docx2pdf(word_p) or G.exportar_pdf_reportlab(
            df_resumen_j, df_mensual_j
        )
    finally:
        G.OUT_EXCEL = orig_xls
        G.OUT_WORD  = orig_word
        G.OUT_PDF   = orig_pdf

    # Añadir hoja "Justificaciones" al Excel ya generado
    _agregar_hoja_justificaciones(df_kpi_j)


def _agregar_hoja_justificaciones(df_kpi_j: pd.DataFrame):
    """Inserta una hoja con el resumen de justificaciones en el Excel generado."""
    justificados = df_kpi_j[df_kpi_j["Justificacion"] != ""][[
        "Empleado", "Nombre", "Fecha", "Justificacion",
        "Atraso_Man_min", "Atraso_Tar_min", "Atraso_Total_min", "Salida_Ant_min",
    ]].copy()

    if justificados.empty:
        return

    justificados["Fecha"] = justificados["Fecha"].dt.strftime("%Y-%m-%d")

    wb = load_workbook(OUT_XLS)

    # Eliminar hoja anterior si existe (re-ejecuciones)
    if "Justificaciones" in wb.sheetnames:
        del wb["Justificaciones"]

    ws = wb.create_sheet("Justificaciones")

    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    fill_hdr = PatternFill("solid", fgColor="1F3864")
    font_hdr = Font(bold=True, color="FFFFFF", size=10, name="Arial")
    font_dat = Font(size=9, name="Arial")
    aln_c    = Alignment(horizontal="center", vertical="center")
    border   = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    headers = ["Empleado", "Nombre", "Fecha", "Motivo",
               "Atr. Mañ (min)", "Atr. Tar (min)", "Atr. Total (min)", "Sal. Ant (min)"]

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=ci, value=h)
        cell.font = font_hdr
        cell.fill = fill_hdr
        cell.alignment = aln_c
        cell.border = border

    for ri, row in enumerate(justificados.itertuples(index=False), 2):
        for ci, val in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=val)
            cell.font = font_dat
            cell.alignment = aln_c
            cell.border = border

    col_widths = [16, 32, 13, 40, 15, 15, 16, 15]
    for ci, w in enumerate(col_widths, 1):
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(ci)].width = w

    ws.row_dimensions[1].height = 22
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A2"

    wb.save(OUT_XLS)
    print(f"     → Hoja 'Justificaciones' añadida ({len(justificados)} registros)")


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def main():
    print("\n" + "═" * 65)
    print("   GESTOR DE JUSTIFICACIONES SEFIL")
    print("═" * 65 + "\n")

    if not G.ARCHIVO_ASIST.exists():
        print(f"  ❌ No encontrado: {G.ARCHIVO_ASIST}")
        sys.exit(1)

    print("  [1/4] Cargando justificaciones...")
    df_justif = cargar_justificaciones()

    print("\n  [2/4] Ejecutando pipeline de asistencias...")
    df_asist  = G.cargar_asistencias(G.ARCHIVO_ASIST)
    df_cruz   = G.inferir_y_asignar_horarios(df_asist)
    df_kpi    = G.calcular_kpis(df_cruz)

    print("\n  [3/4] Aplicando justificaciones...")
    df_kpi_j  = aplicar_justificaciones(df_kpi, df_justif)

    print("\n  [4/4] Generando reportes ajustados...")
    df_res_j  = G.generar_resumen_general(df_kpi_j)
    df_mes_j  = G.generar_kpi_mensual(df_kpi_j)
    exportar_justificado(df_kpi_j, df_res_j, df_mes_j)

    atraso_orig = df_kpi["Atraso_Total_min"].sum()
    atraso_just = df_kpi_j["Atraso_Total_min"].sum()

    G.generar_bat(OUTPUT_DIR_J)

    print("\n" + "═" * 65)
    print("   ✅  REPORTE JUSTIFICADO GENERADO")
    print("═" * 65)
    print(f"\n  📊  Excel     → {OUT_XLS.name}")
    print(f"  📝  Word      → {OUT_WORD.name}")
    print(f"  📄  PDF       → {OUT_PDF.name}")
    print(f"  🚀  Dashboard → Lanzar_Dashboard.bat")
    print(f"\n  Atraso original   : {atraso_orig:.0f} min")
    print(f"  Atraso justificado: {atraso_just:.0f} min")
    print(f"  Diferencia        : -{atraso_orig - atraso_just:.0f} min justificados")
    print(f"\n  Carpeta: {OUTPUT_DIR_J}/")
    print("═" * 65 + "\n")


if __name__ == "__main__":
    main()
