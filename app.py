import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path

st.set_page_config(
    page_title="Registro de Asistencias · Sefil",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── DARK THEME CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color:#0e1117; color:#fafafa; }
  [data-testid="stSidebar"] {
    background-color:#161b22;
    border-right:1px solid #30363d;
  }
  .kpi-card {
    background:linear-gradient(135deg,#1a1f2e 0%,#16213e 100%);
    border:1px solid #30363d;
    border-radius:12px;
    padding:18px 12px;
    text-align:center;
    box-shadow:0 4px 15px rgba(0,0,0,.35);
    height:130px;
    display:flex; flex-direction:column; justify-content:center;
  }
  .kpi-icon { font-size:1.4rem; margin-bottom:4px; }
  .kpi-value { font-size:1.9rem; font-weight:700; line-height:1.15; }
  .kpi-label { font-size:0.72rem; color:#8b949e; text-transform:uppercase;
               letter-spacing:.6px; margin-top:4px; }
  .section-hdr { font-size:1rem; font-weight:600; color:#58a6ff;
                 border-bottom:2px solid #21262d; padding-bottom:6px;
                 margin-bottom:14px; }
  hr { border-color:#30363d; }
  ::-webkit-scrollbar { width:5px; }
  ::-webkit-scrollbar-track { background:#0e1117; }
  ::-webkit-scrollbar-thumb { background:#30363d; border-radius:3px; }
</style>
""", unsafe_allow_html=True)

# ── PALETA ─────────────────────────────────────────────────────────────────────
C = dict(
    primary="#58a6ff", success="#3fb950", warning="#d29922",
    danger="#f85149", purple="#bc8cff", teal="#39d353", muted="#8b949e",
)

DARK = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter,sans-serif", color="#c9d1d9"),
    margin=dict(l=16, r=16, t=42, b=16),
)

DIAS_ES = {0:"Lunes",1:"Martes",2:"Miércoles",3:"Jueves",
           4:"Viernes",5:"Sábado",6:"Domingo"}

# ── HELPERS ────────────────────────────────────────────────────────────────────

def _is_null(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def fmt_time(v) -> str:
    """'HH:MM:SS' string, time object, or NaN → 'HH:MM'. Empty/null → ''."""
    if _is_null(v):
        return ""
    s = str(v).strip()
    return s[:5] if len(s) >= 5 else s


# ── CARGA Y PROCESAMIENTO ──────────────────────────────────────────────────────

@st.cache_data(show_spinner="Cargando datos de asistencia…")
def load_data() -> pd.DataFrame:
    # Buscar Reporte_SEFIL.xlsx en la carpeta actual o en output_sefil/
    for candidate in ["Reporte_SEFIL.xlsx",
                      "output_sefil/Reporte_SEFIL.xlsx",
                      "output_sefil_justificaciones/Reporte_SEFIL.xlsx"]:
        p = Path(candidate)
        if p.exists():
            archivo = p
            break
    else:
        st.error("❌ No se encontró Reporte_SEFIL.xlsx. "
                 "Colócalo en la misma carpeta que este script.")
        st.stop()

    try:
        df = pd.read_excel(archivo, sheet_name="Detalle_Diario", header=1)
    except Exception as e:
        st.error(f"❌ Error al leer {archivo.name}: {e}")
        st.stop()

    # Limpiar nombres de columna (los headers tienen \n para ajuste de texto)
    df.columns = df.columns.str.replace("\n", " ").str.strip()
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
    df = df.dropna(subset=["Fecha"])

    # Renombrar columnas KPI a nombres internos
    df = df.rename(columns={
        "Atraso Man(min)":   "atr_man",
        "Atraso Tar(min)":   "atr_tar",
        "Atraso Total(min)": "total_atraso",
        "Salida Ant(min)":   "total_sal_ant",
        "Horas Total":       "horas_trab",
    })

    for col in ["atr_man", "atr_tar", "total_atraso", "total_sal_ant", "horas_trab"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Formatear tiempos para visualización
    for col in ["Entrada Mañana", "Salida Mañana", "Entrada Tarde", "Salida Tarde"]:
        if col in df.columns:
            df[col] = df[col].apply(fmt_time)

    # Olvidos: Evento == "Olvido"
    df["olvidos"]      = (df["Evento"].astype(str).str.strip() == "Olvido").astype(int)
    df["tiene_olvido"] = df["olvidos"] > 0

    # Estado del día
    def estado(row) -> str:
        if row["olvidos"]:
            return "Olvido"
        if row["total_atraso"] > 0:
            return "Con Atraso"
        if row["total_sal_ant"] > 0:
            return "Salida Anticipada"
        return "A Tiempo"

    df["estado"] = df.apply(estado, axis=1)

    # Columnas auxiliares
    df["dia_es"]    = df["Fecha"].dt.dayofweek.map(DIAS_ES)
    df["mes"]       = df["Fecha"].dt.to_period("M").astype(str)
    df["nom_corto"] = df["Nombre"].str.split().str[:2].str.join(" ")

    return df


# ── SIDEBAR ────────────────────────────────────────────────────────────────────

def sidebar(df: pd.DataFrame):
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:12px 0 20px'>
          <div style='font-size:2rem'><img src='/img/sefil.webp' width='180'></div>
          <div style='font-size:1.05rem;font-weight:700;color:#58a6ff'>Panel de Asistencias</div>
          <div style='font-size:.72rem;color:#8b949e;margin-top:3px'>Control de Asistencias · Sefil</div>
        </div>""", unsafe_allow_html=True)

        st.markdown("### 🗓 Rango de Fechas")
        fmin, fmax = df["Fecha"].min().date(), df["Fecha"].max().date()
        f_ini = st.date_input("Desde", value=fmin, min_value=fmin, max_value=fmax)
        f_fin = st.date_input("Hasta", value=fmax, min_value=fmin, max_value=fmax)

        st.markdown("---")
        st.markdown("### 👥 Empleados")
        empleados = sorted(df["nom_corto"].unique())
        sel_emp = st.multiselect("Filtrar por empleado", options=empleados,
                                 default=[], placeholder="Todos los empleados")

        st.markdown("---")
        st.markdown("### 📋 Jornada")
        jornadas = ["Todas"] + sorted(df["Jornada"].dropna().unique())
        sel_jor = st.selectbox("Tipo de jornada", jornadas)

        st.markdown("---")
        st.markdown("### 📊 Estado")
        estados = ["Todos", "A Tiempo", "Con Atraso", "Salida Anticipada", "Olvido"]
        sel_est = st.selectbox("Filtrar por estado", estados)

        st.markdown("---")
        st.caption("Sefil · Dashboard v1.0 · 2026")

    return f_ini, f_fin, sel_emp, sel_jor, sel_est


# ── KPI CARDS ──────────────────────────────────────────────────────────────────

def kpi(icon, val, label, color=C["primary"]) -> str:
    return f"""
    <div class="kpi-card">
      <div class="kpi-icon">{icon}</div>
      <div class="kpi-value" style="color:{color}">{val}</div>
      <div class="kpi-label">{label}</div>
    </div>"""


def render_kpis(df: pd.DataFrame):
    n_emp    = df["Nombre"].nunique()
    tot_h    = df["horas_trab"].sum()
    tot_atr  = int(df["total_atraso"].sum())
    tot_sal  = int(df["total_sal_ant"].sum())
    n_olv    = int(df["tiene_olvido"].sum())
    pct_ok   = (df["estado"] == "A Tiempo").sum() / max(len(df), 1) * 100

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.markdown(kpi("👥", n_emp,                "Empleados"),                    unsafe_allow_html=True)
    c2.markdown(kpi("⏱", f"{tot_h:,.1f} h",   "Horas Trabajadas", C["success"]), unsafe_allow_html=True)
    c3.markdown(kpi("⏰", f"{tot_atr:,} min",  "Min. de Atraso",   C["warning"]), unsafe_allow_html=True)
    c4.markdown(kpi("🚪", f"{tot_sal:,} min",  "Sal. Anticipadas", C["danger"]),  unsafe_allow_html=True)
    c5.markdown(kpi("❓", n_olv,               "Días con Olvido",  C["purple"]),  unsafe_allow_html=True)
    c6.markdown(kpi("✅", f"{pct_ok:.1f}%",   "Asist. A Tiempo",  C["teal"]),    unsafe_allow_html=True)


# ── GRÁFICOS ───────────────────────────────────────────────────────────────────

def fig_donut(df: pd.DataFrame) -> go.Figure:
    cnt = df["estado"].value_counts().reset_index()
    cnt.columns = ["Estado", "Días"]
    cmap = {"A Tiempo": C["success"], "Con Atraso": C["warning"],
            "Salida Anticipada": C["danger"], "Olvido": C["purple"]}
    colors = [cmap.get(e, C["muted"]) for e in cnt["Estado"]]

    fig = go.Figure(go.Pie(
        labels=cnt["Estado"], values=cnt["Días"], hole=0.58,
        marker=dict(colors=colors, line=dict(color="#0e1117", width=2)),
        textinfo="percent+label", textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>Días: %{value}<br>%{percent}<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{len(df)}</b><br><span style='font-size:12px'>días</span>",
        x=0.5, y=0.5, font=dict(size=20, color="#c9d1d9"), showarrow=False,
    )
    fig.update_layout(
        **DARK, height=350,
        title=dict(text="Estado Global de Asistencias", font=dict(size=14), x=0),
        legend=dict(orientation="h", yanchor="bottom", y=-0.18, xanchor="center", x=0.5),
    )
    return fig


def fig_top_atrasos(df: pd.DataFrame) -> go.Figure:
    top = (
        df.groupby("nom_corto")["total_atraso"]
        .sum().sort_values(ascending=False).head(5).reset_index()
    )
    top.columns = ["Empleado", "Minutos"]

    fig = go.Figure(go.Bar(
        x=top["Minutos"], y=top["Empleado"], orientation="h",
        marker=dict(
            color=top["Minutos"],
            colorscale=[[0, "#1f3a5f"], [0.5, "#d29922"], [1, "#f85149"]],
            showscale=False,
        ),
        text=top["Minutos"].apply(lambda x: f"{x} min"),
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Atraso total: %{x} min<extra></extra>",
    ))
    fig.update_layout(
        **DARK, height=350,
        title=dict(text="Top 5 — Mayores Atrasos Acumulados", font=dict(size=14), x=0),
        xaxis=dict(title="Minutos de Atraso", gridcolor="#21262d"),
        yaxis=dict(autorange="reversed", gridcolor="#21262d"),
    )
    return fig


def fig_evolucion(df: pd.DataFrame) -> go.Figure:
    daily = (
        df.groupby("Fecha")
        .agg(atraso=("total_atraso", "sum"), horas=("horas_trab", "sum"))
        .reset_index().sort_values("Fecha")
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scatter(
        x=daily["Fecha"], y=daily["atraso"], name="Min. Atraso",
        line=dict(color=C["warning"], width=2),
        fill="tozeroy", fillcolor="rgba(210,153,34,.15)",
        hovertemplate="%{x|%d/%m/%Y}<br>Atraso: <b>%{y} min</b><extra></extra>",
    ), secondary_y=False)
    fig.add_trace(go.Scatter(
        x=daily["Fecha"], y=daily["horas"], name="Horas Trabajadas",
        mode="lines+markers", line=dict(color=C["primary"], width=2),
        marker=dict(size=5),
        hovertemplate="%{x|%d/%m/%Y}<br>Horas: <b>%{y:.1f} h</b><extra></extra>",
    ), secondary_y=True)

    fig.update_layout(
        **DARK, height=370,
        title=dict(text="Evolución Temporal — Atrasos vs. Horas Trabajadas", font=dict(size=14), x=0),
        legend=dict(orientation="h", y=-0.18, x=0),
        xaxis=dict(gridcolor="#21262d"),
    )
    fig.update_yaxes(title_text="Min. Atraso",      secondary_y=False, gridcolor="#21262d")
    fig.update_yaxes(title_text="Horas Trabajadas", secondary_y=True,  gridcolor="#21262d", showgrid=False)
    return fig


def fig_heatmap(df: pd.DataFrame) -> go.Figure:
    ORDER = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    pivot = (
        df.groupby(["nom_corto", "dia_es"])["total_atraso"]
        .sum().unstack(fill_value=0)
    )
    cols = [d for d in ORDER if d in pivot.columns]
    pivot = pivot[cols]

    fig = go.Figure(go.Heatmap(
        z=pivot.values, x=pivot.columns.tolist(), y=pivot.index.tolist(),
        colorscale=[
            [0.00, "#0d1117"], [0.12, "#1a3a5c"],
            [0.45, "#d29922"], [1.00, "#f85149"],
        ],
        text=pivot.values, texttemplate="%{text}", textfont=dict(size=11),
        hovertemplate="<b>%{y}</b><br>%{x}<br>Atraso total: %{z} min<extra></extra>",
        showscale=True,
        colorbar=dict(title="Min", thickness=12, len=0.85, tickfont=dict(size=10)),
    ))
    fig.update_layout(
        **DARK,
        title=dict(text="Mapa de Calor — Atrasos por Empleado y Día", font=dict(size=14), x=0),
        xaxis=dict(side="top"),
        height=max(330, len(pivot) * 46 + 90),
    )
    return fig


def fig_olvidos(df: pd.DataFrame) -> "go.Figure | None":
    olv = (
        df.groupby("nom_corto")["olvidos"]
        .sum().sort_values(ascending=False).head(10).reset_index()
    )
    olv.columns = ["Empleado", "Olvidos"]
    olv = olv[olv["Olvidos"] > 0]
    if olv.empty:
        return None

    fig = px.bar(olv, x="Empleado", y="Olvidos",
                 color="Olvidos",
                 color_continuous_scale=["#21262d", "#bc8cff", "#f85149"],
                 text="Olvidos")
    fig.update_traces(textposition="outside")
    fig.update_layout(
        **DARK, height=330,
        title=dict(text="Olvidos de Marcación por Empleado", font=dict(size=14), x=0),
        xaxis=dict(title="", tickangle=-30),
        yaxis=dict(title="Marcaciones faltantes", gridcolor="#21262d"),
        showlegend=False, coloraxis_showscale=False,
    )
    return fig


def fig_horas_empleado(df: pd.DataFrame) -> go.Figure:
    hrs = (
        df.groupby("nom_corto")["horas_trab"]
        .sum().sort_values(ascending=False).reset_index()
    )
    hrs.columns = ["Empleado", "Horas"]

    fig = px.bar(hrs, x="Empleado", y="Horas",
                 color="Horas",
                 color_continuous_scale=[[0, "#1a3a5c"], [1, "#58a6ff"]],
                 text=hrs["Horas"].apply(lambda h: f"{h:.1f}h"))
    fig.update_traces(textposition="outside")
    fig.update_layout(
        **DARK, height=330,
        title=dict(text="Total Horas Trabajadas por Empleado", font=dict(size=14), x=0),
        xaxis=dict(title="", tickangle=-30),
        yaxis=dict(title="Horas", gridcolor="#21262d"),
        showlegend=False, coloraxis_showscale=False,
    )
    return fig


# ── TABLA DETALLE ──────────────────────────────────────────────────────────────

def render_tabla(df: pd.DataFrame):
    COLS = {
        "nom_corto":         "Empleado",
        "Fecha":             "Fecha",
        "Horario Detectado": "Horario",
        "Jornada":           "Jornada",
        "Entrada Mañana":    "Ent. Mañana",
        "Salida Mañana":     "Sal. Mañana",
        "Entrada Tarde":     "Ent. Tarde",
        "Salida Tarde":      "Sal. Tarde",
        "atr_man":           "Atr. Mañ (min)",
        "atr_tar":           "Atr. Tarde (min)",
        "total_atraso":      "Total Atraso",
        "total_sal_ant":     "Sal. Ant. (min)",
        "horas_trab":        "Horas Trab.",
        "olvidos":           "Olvidos",
        "estado":            "Estado",
    }
    available = {k: v for k, v in COLS.items() if k in df.columns}
    tbl = df[list(available.keys())].rename(columns=available).copy()
    tbl["Fecha"]       = tbl["Fecha"].dt.strftime("%d/%m/%Y")
    tbl["Horas Trab."] = tbl["Horas Trab."].apply(lambda x: f"{x:.2f} h")

    ESTADO_COLOR = {
        "A Tiempo":          "color:#3fb950",
        "Con Atraso":        "color:#d29922",
        "Salida Anticipada": "color:#f85149",
        "Olvido":            "color:#bc8cff",
    }
    styled = tbl.style.map(lambda v: ESTADO_COLOR.get(v, ""), subset=["Estado"])
    st.dataframe(styled, use_container_width=True, height=400)


def render_resumen(df: pd.DataFrame):
    resumen = df.groupby("nom_corto").agg(
        Días=("Fecha", "count"),
        Horas_Trabajadas=("horas_trab", "sum"),
        Min_Atraso=("total_atraso", "sum"),
        Días_Con_Atraso=("total_atraso", lambda x: (x > 0).sum()),
        Sal_Anticipadas_min=("total_sal_ant", "sum"),
        Olvidos=("olvidos", "sum"),
        Días_A_Tiempo=("estado", lambda x: (x == "A Tiempo").sum()),
    ).reset_index().rename(columns={"nom_corto": "Empleado"})

    resumen["% A Tiempo"] = (
        resumen["Días_A_Tiempo"] / resumen["Días"] * 100
    ).round(1).astype(str) + " %"
    resumen["Horas_Trabajadas"] = resumen["Horas_Trabajadas"].round(2)
    st.dataframe(resumen.drop(columns=["Días_A_Tiempo"]), use_container_width=True)


# ── MAIN ───────────────────────────────────────────────────────────────────────

def main():
    df_raw = load_data()

    f_ini, f_fin, sel_emp, sel_jor, sel_est = sidebar(df_raw)

    df = df_raw[
        (df_raw["Fecha"].dt.date >= f_ini) &
        (df_raw["Fecha"].dt.date <= f_fin)
    ].copy()

    if sel_emp:
        df = df[df["nom_corto"].isin(sel_emp)]
    if sel_jor != "Todas":
        df = df[df["Jornada"] == sel_jor]
    if sel_est != "Todos":
        df = df[df["estado"] == sel_est]

    if df.empty:
        st.warning("No hay datos para los filtros seleccionados.")
        st.stop()

    st.markdown("""
    <div style='padding:6px 0 22px'>
      <span style='font-size:1.55rem;font-weight:700;color:#f0f6fc'>
        📊 Dashboard de Asistencias
      </span>
      <span style='font-size:.85rem;color:#8b949e;margin-left:10px'>
        Panel Gerencial · Recursos Humanos · Sefil
      </span>
    </div>""", unsafe_allow_html=True)

    render_kpis(df)
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(fig_donut(df), use_container_width=True)
    with c2:
        st.plotly_chart(fig_top_atrasos(df), use_container_width=True)

    st.plotly_chart(fig_evolucion(df), use_container_width=True)

    c3, c4 = st.columns([3, 2])
    with c3:
        st.plotly_chart(fig_heatmap(df), use_container_width=True)
    with c4:
        f_olv = fig_olvidos(df)
        if f_olv:
            st.plotly_chart(f_olv, use_container_width=True)
        else:
            st.info("Sin olvidos de marcacion en el periodo seleccionado.")

    st.plotly_chart(fig_horas_empleado(df), use_container_width=True)

    st.markdown("---")
    st.markdown("<div class='section-hdr'>📋 Detalle por Empleado y Día</div>",
                unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["📅 Vista Diaria", "📊 Resumen por Empleado"])
    with tab1:
        render_tabla(df)
    with tab2:
        render_resumen(df)

    st.markdown("---")
    export_cols = {
        "Nombre": "Nombre", "Fecha": "Fecha",
        "Horario Detectado": "Horario", "Jornada": "Jornada",
        "Entrada Mañana": "Ent. Mañana", "Salida Mañana": "Sal. Mañana",
        "Entrada Tarde": "Ent. Tarde",   "Salida Tarde": "Sal. Tarde",
        "atr_man": "Atr. Mañana (min)", "atr_tar": "Atr. Tarde (min)",
        "total_atraso": "Total Atraso (min)", "total_sal_ant": "Sal. Anticipada (min)",
        "horas_trab": "Horas Trabajadas", "olvidos": "Olvidos", "estado": "Estado",
    }
    available_exp = {k: v for k, v in export_cols.items() if k in df.columns}
    export = df[list(available_exp.keys())].rename(columns=available_exp).copy()
    export["Fecha"] = export["Fecha"].dt.strftime("%d/%m/%Y")
    st.download_button(
        label="Descargar reporte CSV",
        data=export.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="reporte_asistencias_procesado.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
