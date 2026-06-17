import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime

from backend.database import get_engine
from backend.sync import sync_from_excel, get_last_sync, get_total_records
from backend.justifications import add_justification, remove_justification, list_justifications
from backend.auth import authenticate_user, change_password, init_default_users

st.set_page_config(
    page_title="Registro Asistencia - Sefil",
    page_icon="app/img/icon.png",
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
  .cal-asistencia { background:#1a3a2a; color:#3fb950; text-align:center;
                    padding:6px 4px; border-radius:6px; font-size:.78rem; font-weight:600; }
  .cal-falta      { background:#3a1a1a; color:#f85149; text-align:center;
                    padding:6px 4px; border-radius:6px; font-size:.78rem; font-weight:600; }
  .cal-permiso    { background:#2a2a1a; color:#d29922; text-align:center;
                    padding:6px 4px; border-radius:6px; font-size:.78rem; font-weight:600; }
  .cal-nolaboral  { background:#1a1a2a; color:#8b949e; text-align:center;
                    padding:6px 4px; border-radius:6px; font-size:.78rem; font-weight:600; }
  .cal-header     { text-align:center; font-weight:700; color:#58a6ff;
                    padding:8px 4px; font-size:.8rem; border-bottom:2px solid #21262d; }
  .cal-day-label  { text-align:center; color:#8b949e; font-size:.68rem; padding:2px; }
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

@st.cache_data(show_spinner="Cargando datos desde PostgreSQL...")
def load_data() -> pd.DataFrame:
    query = """
        SELECT 
            employee_id, employee_name, date, 
            schedule_name, shift_type, shift_detail, shift_str,
            entry_morning, exit_morning, entry_afternoon, exit_afternoon,
            hours_morning, hours_afternoon, hours_total,
            delay_morning_min, delay_afternoon_min, delay_total_min,
            early_exit_min, overtime_hours, event, annotations, month_period
        FROM attendance_daily
    """
    engine = get_engine()
    df = pd.read_sql(query, engine)
    
    if df.empty:
        df["Fecha"] = pd.Series(dtype='datetime64[ns]')
        df["olvidos"] = pd.Series(dtype=int)
        df["employee_id"] = pd.Series(dtype=str)
        df["employee_name"] = pd.Series(dtype=str)
        df["nom_corto"] = pd.Series(dtype=str)
        df["Jornada"] = pd.Series(dtype=str)
        df["estado"] = pd.Series(dtype=str)
        df["Nombre"] = pd.Series(dtype=str)
        return df

    # Map directly expected columns
    df["Nombre"] = df["employee_name"]
    df["Fecha"] = pd.to_datetime(df["date"], errors="coerce")
    df["Horario Detectado"] = df["schedule_name"]
    df["Jornada"] = df["shift_type"]
    df["Entrada Mañana"] = df["entry_morning"]
    df["Salida Mañana"] = df["exit_morning"]
    df["Entrada Tarde"] = df["entry_afternoon"]
    df["Salida Tarde"] = df["exit_afternoon"]
    df["atr_man"] = df["delay_morning_min"].fillna(0).astype(float)
    df["atr_tar"] = df["delay_afternoon_min"].fillna(0).astype(float)
    df["total_atraso"] = df["delay_total_min"].fillna(0).astype(float)
    df["total_sal_ant"] = df["early_exit_min"].fillna(0).astype(float)
    df["horas_trab"] = df["hours_total"].fillna(0).astype(float)
    df["Evento"] = df["event"]

    # Calculated columns mapping
    df['dia_es'] = df['Fecha'].dt.dayofweek.map(DIAS_ES)
    df['mes'] = df['Fecha'].dt.strftime('%Y-%m')
    
    def _short_name(full_name):
        parts = str(full_name).strip().split()
        if len(parts) >= 2:
            return f"{parts[0]} {parts[1]}"
        return full_name
    df['nom_corto'] = df['Nombre'].apply(_short_name)
    
    # Calculate olvidos
    def _calc_olvido(row):
        return 1 if str(row['Evento']).strip() == 'Olvido' else 0
        
    df['tiene_olvido'] = df.apply(_calc_olvido, axis=1)
    df['olvidos'] = df['tiene_olvido']

    # Calculate estado
    def _calc_estado(row):
        is_medio_tiempo = str(row.get('Evento', '')).strip() == 'Medio Tiempo'
        is_falta = str(row.get('Evento', '')).strip() == 'Falta'
        
        # Primero revisamos si hay atrasos (Entradas)
        if row['total_atraso'] > 0:  
            return 'Con Atraso'
            
        # Segundo revisamos salidas anticipadas
        if row['total_sal_ant'] > 0: 
            return 'Salida Anticipada'
            
        # Tercero Olvidos
        if row['olvidos'] > 0: 
            return 'Olvido'
            
        # Cuarto Falta
        if is_falta: 
            return 'Falta'
        
        # Condicion Medio Tiempo
        if is_medio_tiempo:
            if row.get('horas_trab', 0) >= 4:
                return 'Medio Tiempo'
            
        # Prioridad Final: A Tiempo
        return 'A Tiempo'
    
    df['estado'] = df.apply(_calc_estado, axis=1)

    return df


# ── SIDEBAR ────────────────────────────────────────────────────────────────────

def sidebar(df: pd.DataFrame):
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:12px 0 20px'>
          <div style='font-size:2rem'><img src='app/img/icon.png' width='80'></div>
          <div style='font-size:1.05rem;font-weight:700;color:#3fb950'>SEFIL S.A.</div>
          <div style='font-size:.72rem;color:#8b949e;margin-top:3px'>Control de Asistencias</div>
        </div>""", unsafe_allow_html=True)

        # ── NAVEGACIÓN PRINCIPAL ───────────────────────────────────────────
        st.markdown("### 🧭 Navegación")
        vista = st.radio(
            "Selecciona la vista",
            ["📊 Atrasos / KPIs", "📅 Asistencias", "⚙️ Config. Empleados"],
            label_visibility="collapsed",
            horizontal=True,
        )
        st.markdown("---")

        st.markdown("### ⚙️ Mi Cuenta")
        st.info(f"👤 Usuario: **{st.session_state.username}**\n\n🛡️ Rol: **{st.session_state.role}**")
        
        with st.expander("🔑 Cambiar Contraseña"):
            with st.form("pwd_form"):
                old_pwd = st.text_input("Contraseña Actual", type="password")
                new_pwd = st.text_input("Nueva Contraseña", type="password")
                pwd_submit = st.form_submit_button("Actualizar")
                if pwd_submit:
                    if not old_pwd or not new_pwd:
                        st.error("Completa ambos campos.")
                    else:
                        res = change_password(st.session_state.username, old_pwd, new_pwd)
                        if res:
                            st.success("✅ Contraseña actualizada.")
                        else:
                            st.error("❌ Contraseña actual incorrecta.")
                            
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.username = None
            st.session_state.role = None
            st.rerun()
            
        st.markdown("---")

        if st.session_state.role != "rrhh":
            st.markdown("### 🔄 Sincronización")
            last_sync = get_last_sync()
            total_records = get_total_records()
            
            if last_sync:
                sync_time = last_sync.get('synced_at', '')
                try:
                    from datetime import datetime as _dt
                    parsed = _dt.strptime(sync_time.split('.')[0], '%Y-%m-%d %H:%M:%S')
                    sync_time = parsed.strftime('%d/%m/%Y %H:%M')
                except Exception:
                    pass
                st.caption(f"Última sync: {sync_time}")
            st.caption(f"Registros en BD: {total_records}")
            
            if st.button("🔄 Recargar Datos", use_container_width=True, type="secondary"):
                st.cache_data.clear()
                st.toast("Datos recargados desde la base de datos.", icon="🔄")
                st.rerun()
                
            if st.button("⚙️ Forzar Sincronización DB", use_container_width=True, type="primary"):
                with st.spinner("Conectando al biométrico y procesando... Esto puede tomar 1 a 2 minutos."):
                    try:
                        import subprocess
                        import sys
                        result = subprocess.run([sys.executable, "main_pipeline.py"], capture_output=True, text=True)
                        if result.returncode == 0:
                            st.cache_data.clear()
                            st.success("✅ Sincronización directa con biométrico exitosa.")
                            st.rerun()
                        else:
                            error_msg = (result.stderr or result.stdout or "Error desconocido")[-200:]
                            st.error(f"❌ Falló la sincronización:\n{error_msg}")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        
            st.markdown("---")

        st.markdown("### 🗓 Filtros de Tiempo")
        
        meses = ["Todos"] + sorted(df["mes"].dropna().unique(), reverse=True) if not df.empty else ["Todos"]
        sel_mes = st.selectbox("Mes Rápido", meses)
        
        if not df.empty:
            fmin, fmax = df["Fecha"].min().date(), df["Fecha"].max().date()
        else:
            fmin, fmax = datetime.now().date(), datetime.now().date()
            
        f_ini = st.date_input("Desde", value=fmin)
        f_fin = st.date_input("Hasta", value=fmax)

        st.markdown("---")
        st.markdown("### 👥 Empleados")
        empleados = sorted(df["nom_corto"].unique()) if not df.empty else []
        sel_emp = st.multiselect("Filtrar por empleado", options=empleados,
                                 default=[], placeholder="Todos los empleados")

        st.markdown("---")
        st.markdown("### 📋 Jornada")
        jornadas = ["Todas"] + sorted(df["Jornada"].dropna().unique()) if not df.empty else ["Todas"]
        sel_jor = st.selectbox("Tipo de jornada", jornadas)

        st.markdown("---")
        st.markdown("### 📊 Estado")
        estados = ["Todos", "A Tiempo", "Con Atraso", "Salida Anticipada", "Olvido", "Falta"]
        sel_est = st.selectbox("Filtrar por estado", estados)

        st.markdown("---")
        st.caption("Sefil S.A. Todos los derechos reservados")

    return f_ini, f_fin, sel_emp, sel_jor, sel_est, sel_mes, vista


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
            "Salida Anticipada": C["danger"], "Olvido": C["purple"],
            "Falta": "#e74c3c"}
    colors = [cmap.get(e, C["muted"]) for e in cnt["Estado"]]

    fig = go.Figure(go.Pie(
        labels=cnt["Estado"], values=cnt["Días"], hole=0.58,
        marker=dict(colors=colors, line=dict(color="#0e1117", width=2)),
        textinfo="percent+label", textfont=dict(size=12),
        hovertemplate="<b>%{label}</b><br>Días: %{value}<br>%{percent}<extra></extra>",
    ))
    fig.add_annotation(
        text=f"<b>{df['Fecha'].nunique()}</b><br><span style='font-size:12px'>días laborales</span>",
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
        "Medio Tiempo":      "color:#3498DB",
        "Falta":             "color:#e74c3c",
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


def render_justificaciones(df: pd.DataFrame):
    st.markdown("### 📝 Gestión de Justificaciones")
    
    if st.session_state.role != "rrhh":
        st.markdown("#### ➕ Agregar Nueva Justificación")
        with st.form("form_justificacion", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                if not df.empty:
                    emp_options = df[['employee_name', 'employee_id']].drop_duplicates().sort_values('employee_name')
                    emp_names = emp_options['employee_name'].tolist()
                    emp_ids = emp_options['employee_id'].tolist()
                    sel_emp_idx = st.selectbox("Empleado", range(len(emp_names)), format_func=lambda i: emp_names[i])
                    selected_emp_name = emp_names[sel_emp_idx]
                    selected_emp_id = emp_ids[sel_emp_idx]
                else:
                    st.warning("No hay datos de empleados disponibles.")
                    selected_emp_name = ""
                    selected_emp_id = ""

                just_date = st.date_input("Fecha")

            with col_b:
                just_types = ['Atraso_Man', 'Atraso_Tar', 'Atraso', 'Salida_Anticipada', 'Todos']
                just_type = st.selectbox("Tipo de Justificación", just_types)
                just_reason = st.text_input("Motivo / Razón", placeholder="Ej: Cita médica, permiso autorizado...")

            submitted = st.form_submit_button("✅ Registrar Justificación", use_container_width=True, type="primary")

            if submitted:
                if not selected_emp_name or not just_reason.strip():
                    st.error("❌ Selecciona un empleado y agrega un motivo.")
                else:
                    try:
                        res = add_justification(selected_emp_id, selected_emp_name, just_date, just_type, just_reason.strip())
                        if res.get("status") == "ok":
                            st.success("✅ Justificación registrada.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(f"❌ {res.get('message')}")
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

    st.markdown("#### 📜 Historial de Justificaciones")
    justs = list_justifications()
    if not justs:
        st.info("No hay justificaciones registradas.")
    else:
        for j in justs:
            with st.container():
                c1, c2, c3 = st.columns([1, 4, 1])
                with c1:
                    st.markdown(f"**{j['date']}**\n{j['type']}")
                with c2:
                    st.markdown(f"**{j['employee_name']}** (ID: {j['employee_id']})\n*Motivo:* {j['reason']}")
                with c3:
                    if st.session_state.role != "rrhh":
                        if st.button("🗑️ Eliminar", key=f"del_{j['id']}"):
                            remove_justification(j['id'])
                            st.toast("🗑️ Justificación eliminada.")
                            st.cache_data.clear()
                            st.rerun()
                st.markdown("---")

# ── CALENDARIO DINÁMICO DE ASISTENCIAS ─────────────────────────────────────────

CAL_STATES = ["Asistencia", "Falta", "Permiso", "No Laborable"]
CAL_CSS = {
    "Asistencia":    "cal-asistencia",
    "Falta":         "cal-falta",
    "Permiso":       "cal-permiso",
    "No Laborable":  "cal-nolaboral",
}
CAL_EMOJI = {
    "Asistencia":    "✅",
    "Falta":         "❌",
    "Permiso":       "📋",
    "No Laborable":  "🔘",
}


def _map_evento_to_cal_state(evento: str, estado: str) -> str:
    """Map internal event/estado to one of the 4 calendar states."""
    ev = str(evento).strip()
    est = str(estado).strip()
    
    if ev in ("Permiso",):
        return "Permiso"
    if ev in ("Falta",) or est == "Falta":
        # Note: 'Olvido' should NOT be a 'Falta' on the calendar, it should be 'Asistencia' 
        # since the employee came to work but forgot to punch in/out.
        if ev == "Olvido":
            return "Asistencia"
        return "Falta"
    return "Asistencia"


def render_calendario_asistencias(df: pd.DataFrame):
    """Full-page interactive attendance calendar."""
    import calendar as cal_mod

    st.markdown("""
    <div style='padding:6px 0 22px'>
      <span style='font-size:1.55rem;font-weight:700;color:#f0f6fc'>
        📅 Calendario de Asistencias
      </span>
      <span style='font-size:.85rem;color:#8b949e;margin-left:10px'>
        Control mensual · Sefil S.A.
      </span>
    </div>""", unsafe_allow_html=True)

    if df.empty:
        st.warning("No hay datos para mostrar. Sincroniza los datos primero.")
        return

    # ── Selector de Filtros y Leyenda ───────────────────────────────────────────
    st.markdown("### 🔍 Filtro de Resaltado")
    
    # State for active filter
    if "cal_filter" not in st.session_state:
        st.session_state.cal_filter = "Todos"
        
    cols = st.columns(5)
    
    def set_filter(f):
        st.session_state.cal_filter = f
        
    # Todos filter
    is_active = st.session_state.cal_filter == "Todos"
    css_class = "cal-nolaboral" if is_active else ""
    if cols[0].button("👁️ Todos", key="btn_Todos", use_container_width=True, type="primary" if is_active else "secondary"):
        set_filter("Todos")
        st.rerun()

    # Individual filters
    for i, state in enumerate(CAL_STATES):
        is_active = st.session_state.cal_filter == state
        # Create a visually distinct button based on state
        emoji = CAL_EMOJI[state]
        if cols[i+1].button(f"{emoji} {state}", key=f"btn_{state}", use_container_width=True, type="primary" if is_active else "secondary"):
            set_filter(state)
            st.rerun()
            
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Selector de mes / año ──────────────────────────────────────────────
    available_months = sorted(df["Fecha"].dt.to_period("M").unique())
    if not available_months:
        st.info("No hay meses disponibles.")
        return

    month_labels = [p.strftime("%B %Y").capitalize() for p in available_months]
    default_idx = len(month_labels) - 1

    sel_month_label = st.selectbox(
        "Selecciona el mes",
        month_labels,
        index=default_idx,
        key="cal_month_sel",
    )
    sel_period = available_months[month_labels.index(sel_month_label)]
    year, month = sel_period.year, sel_period.month

    # ── Filtrar datos del mes seleccionado ─────────────────────────────────
    mask = (df["Fecha"].dt.year == year) & (df["Fecha"].dt.month == month)
    df_month = df[mask].copy()

    # ── Calcular días laborables del mes (Lun-Vie + Sáb si hay data) ──────
    _, days_in_month = cal_mod.monthrange(year, month)
    all_days = [datetime(year, month, d).date() for d in range(1, days_in_month + 1)]
    # Consideramos laborables: L-V siempre + Sáb si al menos 1 empleado tiene registros en sábado
    has_sat_data = not df_month[df_month["Fecha"].dt.weekday == 5].empty
    work_days = [d for d in all_days if d.weekday() < 5 or (d.weekday() == 5 and has_sat_data)]
    non_work_days = set(all_days) - set(work_days)

    # ── Construir lookup: (employee_id, date) → cal_state ─────────────────
    employees = (
        df_month[["employee_id", "Nombre"]]
        .drop_duplicates()
        .sort_values("Nombre")
        .reset_index(drop=True)
    )

    lookup = {}
    for _, row in df_month.iterrows():
        key = (str(row["employee_id"]), row["Fecha"].date())
        estado = row.get("estado", "")
        lookup[key] = _map_evento_to_cal_state(row.get("Evento", ""), estado)

    # Override with manual_schedules from DB
    from backend.calendar_override import get_manual_overrides
    overrides = get_manual_overrides(year, month)
    for (emp_id, dt), status in overrides.items():
        lookup[(emp_id, dt)] = status

    # ── Generar tabla pivotada con los 4 estados ──────────────────────────
    rows_data = []
    for _, emp in employees.iterrows():
        emp_id = str(emp["employee_id"])
        emp_name = emp["Nombre"]
        row_dict = {"employee_id": emp_id, "Empleado": emp_name}
        for d in all_days:
            day_key = d.strftime("%d")
            key = (emp_id, d)
            if d in non_work_days:
                row_dict[day_key] = lookup.get(key, "No Laborable")
            elif key in lookup:
                row_dict[day_key] = lookup[key]
            else:
                # Día laborable sin registro = Falta
                row_dict[day_key] = "Falta"
        rows_data.append(row_dict)

    df_pivot = pd.DataFrame(rows_data)
    day_cols = [d.strftime("%d") for d in all_days]

    # ── Mostrar la tabla con data_editor ───────────────────────────────────
    is_editable = st.session_state.role != "rrhh"

    if is_editable:
        st.markdown("📝 *Haz clic en una celda para cambiar el estado. Solo puedes asignar: **Permiso** o **No Laborable** manualmente.*")

    # Column config con selectbox
    col_config = {
        "employee_id": st.column_config.TextColumn("ID", width="small", disabled=True),
        "Empleado": st.column_config.TextColumn("Empleado", width="medium", disabled=True),
    }
    for dc in day_cols:
        col_config[dc] = st.column_config.SelectboxColumn(
            dc,
            options=CAL_STATES,
            width="small",
            disabled=not is_editable,
        )

    # ── Función de Estilos Dinámicos ──────────────────────────────────────────
    def color_cells(val):
        """Aplica color a las celdas según el filtro seleccionado."""
        if pd.isna(val) or val not in CAL_STATES:
            return ""
            
        active_filter = st.session_state.get("cal_filter", "Todos")
        
        # Determine if we should highlight this cell
        should_highlight = (active_filter == "Todos") or (active_filter == val)
        
        if not should_highlight:
            return "color: rgba(255, 255, 255, 0.2);" # Dim text if not highlighted
            
        if val == "Asistencia":
            return "background-color: rgba(46, 160, 67, 0.2); color: #3fb950; font-weight: bold;"
        elif val == "Falta":
            return "background-color: rgba(248, 81, 73, 0.2); color: #f85149; font-weight: bold;"
        elif val == "Permiso":
            return "background-color: rgba(88, 166, 255, 0.2); color: #58a6ff; font-weight: bold;"
        elif val == "No Laborable":
            return "background-color: rgba(139, 148, 158, 0.2); color: #8b949e;"
        return ""

    # Aplicar estilos
    styled_df = df_pivot.style.map(color_cells, subset=day_cols)

    edited_df = st.data_editor(
        styled_df,
        column_config=col_config,
        key="cal_asist_editor",
        use_container_width=True,
        hide_index=True,
        disabled=["employee_id", "Empleado"] if is_editable else True,
        height=min(800, 56 + len(employees) * 38),
    )

    # ── Guardar cambios manuales ───────────────────────────────────────────
    if is_editable:
        if st.button("💾 Guardar Cambios del Calendario", type="primary", use_container_width=True):
            from backend.calendar_override import save_manual_override
            changes = st.session_state.get("cal_asist_editor", {}).get("edited_rows", {})
            if changes:
                saved = 0
                try:
                    for row_idx_str, cols_changed in changes.items():
                        row_idx = int(row_idx_str)
                        emp_id = df_pivot.iloc[row_idx]["employee_id"]
                        emp_name = df_pivot.iloc[row_idx]["Empleado"]
                        for day_col, new_val in cols_changed.items():
                            day_num = int(day_col)
                            dt = datetime(year, month, day_num).date()
                            save_manual_override(emp_id, emp_name, dt, new_val)
                            saved += 1
                    st.success(f"✅ {saved} cambio(s) guardado(s) correctamente.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")
            else:
                st.info("No hay cambios pendientes.")

    # ── Resumen del mes ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Resumen del Mes")
    summary_rows = []
    for _, emp in employees.iterrows():
        emp_id = str(emp["employee_id"])
        emp_name = emp["Nombre"]
        states = []
        for d in work_days:
            key = (emp_id, d)
            states.append(lookup.get(key, "Falta"))
        n_asist = states.count("Asistencia")
        n_falta = states.count("Falta")
        n_perm  = states.count("Permiso")
        summary_rows.append({
            "Empleado": emp_name,
            "Días Laborables": len(work_days),
            "Asistencias": n_asist,
            "Faltas": n_falta,
            "Permisos": n_perm,
            "% Asistencia": f"{n_asist / max(len(work_days), 1) * 100:.1f}%",
        })
    df_summary = pd.DataFrame(summary_rows)
    st.dataframe(df_summary, use_container_width=True, hide_index=True)

def render_config_empleados(df_raw: pd.DataFrame):
    """Pantalla de configuración para asignar horarios fijos a cada empleado."""
    st.markdown("""
    <div style='padding:6px 0 22px'>
      <span style='font-size:1.55rem;font-weight:700;color:#f0f6fc'>
        ⚙️ Configuración de Horarios de Empleados
      </span>
      <span style='font-size:.85rem;color:#8b949e;margin-left:10px'>
        Asignación de horarios fijos · Recursos Humanos · Sefil
      </span>
    </div>""", unsafe_allow_html=True)

    if df_raw.empty:
        st.warning("No hay datos de empleados disponibles. Sincroniza los datos primero o asegúrate de que la base de datos contenga registros.")
        return

    # Cargar horarios fijos de la base de datos
    from backend.schedules import get_all_employee_schedules, upsert_employee_schedule
    
    try:
        db_schedules = get_all_employee_schedules()
    except Exception as e:
        st.error(f"Error al cargar las configuraciones desde la base de datos: {e}")
        db_schedules = []

    db_map = {item["employee_id"]: item["schedule_name"] for item in db_schedules}

    # Obtener lista única de empleados (ID y Nombre)
    employees = df_raw[["employee_id", "Nombre"]].drop_duplicates().sort_values("Nombre").copy()
    
    # Construir lista para data_editor
    config_list = []
    for _, row in employees.iterrows():
        emp_id = str(row["employee_id"]).strip()
        emp_name = str(row["Nombre"]).strip()
        current_sched = db_map.get(emp_id, "Automático")
        config_list.append({
            "ID Empleado": emp_id,
            "Nombre Empleado": emp_name,
            "Horario Fijo": current_sched
        })
    
    df_editor = pd.DataFrame(config_list)
    
    # Lógica de permisos por rol
    is_editable = st.session_state.role != "rrhh"
    
    if is_editable:
        st.markdown("📝 *Modifica la columna **Horario Fijo** para cada empleado y haz clic en **💾 Guardar Configuración**.*")
    else:
        st.warning("⚠️ Tu rol (RRHH) solo permite visualizar la configuración. Los cambios están deshabilitados.")

    col_config = {
        "ID Empleado": st.column_config.TextColumn("ID", width="small", disabled=True),
        "Nombre Empleado": st.column_config.TextColumn("Empleado", width="large", disabled=True),
        "Horario Fijo": st.column_config.SelectboxColumn(
            "Horario Fijo",
            options=["Automático", "Horario A", "Horario B", "Horario C", "Horario D", "Medio Tiempo"],
            width="medium",
            disabled=not is_editable
        )
    }

    edited_df = st.data_editor(
        df_editor,
        column_config=col_config,
        key="emp_schedule_editor",
        use_container_width=True,
        hide_index=True,
        height=min(600, 56 + len(employees) * 38),
    )

    if is_editable:
        if st.button("💾 Guardar Configuración", type="primary", use_container_width=True):
            changes = st.session_state.get("emp_schedule_editor", {}).get("edited_rows", {})
            if changes:
                saved = 0
                try:
                    for row_idx_str, cols_changed in changes.items():
                        row_idx = int(row_idx_str)
                        emp_id = df_editor.iloc[row_idx]["ID Empleado"]
                        emp_name = df_editor.iloc[row_idx]["Nombre Empleado"]
                        for _, new_val in cols_changed.items():
                            upsert_employee_schedule(emp_id, emp_name, new_val)
                            saved += 1
                    st.success(f"✅ {saved} cambio(s) de horario guardado(s) correctamente.")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al guardar la configuración: {e}")
            else:
                st.info("No hay cambios pendientes por guardar.")

        st.markdown("---")
        st.markdown("### ⚠️ Re-procesar Datos Históricos")
        st.write("Si modificaste el horario fijo de algún empleado y deseas corregir las clasificaciones e informes del pasado, debes limpiar los datos calculados de asistencia en la base de datos y volver a procesar todas las marcaciones.")
        
        if st.button("🗑️ Limpiar y Re-sincronizar Datos Históricos", type="primary", use_container_width=True):
            with st.spinner("Limpiando base de datos y re-sincronizando marcaciones... Esto puede tomar 1 a 2 minutos."):
                try:
                    import subprocess
                    import sys
                    
                    # 1. Resetear DB
                    res_reset = subprocess.run([sys.executable, "reset_db.py"], capture_output=True, text=True)
                    if res_reset.returncode != 0:
                        st.error(f"❌ Falló la limpieza de la base de datos:\n{res_reset.stderr}")
                    else:
                        # 2. Ejecutar el pipeline completo para re-sincronizar todo
                        res_pipe = subprocess.run([sys.executable, "main_pipeline.py"], capture_output=True, text=True)
                        if res_pipe.returncode == 0:
                            st.cache_data.clear()
                            st.success("✅ Base de datos recreada y marcaciones históricas re-procesadas exitosamente.")
                            st.rerun()
                        else:
                            error_msg = (res_pipe.stderr or res_pipe.stdout or "Error desconocido")[-200:]
                            st.error(f"❌ Falló la re-sincronización del pipeline:\n{error_msg}")
                except Exception as e:
                    st.error(f"❌ Ocurrió un error inesperado: {e}")


# Replace the tabs logic
@st.dialog("Detalle de Asistencias", width="large")
def show_drilldown(df_context, estado_filter, emp_filter=None, dia_filter=None):
    filtered = df_context.copy()
    if estado_filter:
        filtered = filtered[filtered["estado"] == estado_filter]
    if emp_filter:
        filtered = filtered[filtered["nom_corto"] == emp_filter]
    if dia_filter:
        filtered = filtered[filtered["dia_es"] == dia_filter]
        
    st.markdown(f"### Detalle de Registros")
    cols_to_show = ["Nombre", "Fecha", "estado", "atr_man", "atr_tar", "total_atraso", "Evento"]
    filtered["Fecha"] = filtered["Fecha"].dt.strftime('%d/%m/%Y')
    st.dataframe(filtered[cols_to_show], hide_index=True, use_container_width=True)

def main_render():
    df_raw = load_data()
    f_ini, f_fin, sel_emp, sel_jor, sel_est, sel_mes, vista = sidebar(df_raw)

    if df_raw.empty:
        st.warning("La base de datos está vacía. Sincroniza los datos primero.")
        return

    # ── Filtrar datos según sidebar ────────────────────────────────────────
    if sel_mes != "Todos":
        df = df_raw[df_raw["mes"] == sel_mes].copy()
    else:
        df = df_raw[(df_raw["Fecha"].dt.date >= f_ini) & (df_raw["Fecha"].dt.date <= f_fin)].copy()

    if sel_emp:
        df = df[df["nom_corto"].isin(sel_emp)]
    if sel_jor != "Todas":
        df = df[df["Jornada"] == sel_jor]
    if sel_est != "Todos":
        df = df[df["estado"] == sel_est]

    # ── VISTA: CONFIGURACIÓN DE EMPLEADOS ──────────────────────────────────
    if vista == "⚙️ Config. Empleados":
        render_config_empleados(df_raw)
        return

    # ── VISTA: ASISTENCIAS (Calendario) ────────────────────────────────────
    if vista == "📅 Asistencias":
        render_calendario_asistencias(df)
        return

    # ── VISTA: ATRASOS / KPIs (contenido original) ────────────────────────
    st.markdown("""
    <div style='padding:6px 0 22px'>
      <span style='font-size:1.55rem;font-weight:700;color:#f0f6fc'>
        📊 Dashboard de Atrasos
      </span>
      <span style='font-size:.85rem;color:#8b949e;margin-left:10px'>
        Panel Gerencial · Recursos Humanos · Sefil
      </span>
    </div>""", unsafe_allow_html=True)

    tab_estadisticas, tab_diaria, tab_resumen, tab_justificaciones = st.tabs([
        "📈 Estadísticas", "📅 Vista Diaria", "📊 Resumen", "📝 Justificaciones"
    ])

    with tab_estadisticas:
        render_kpis(df)
        st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            ev_donut = st.plotly_chart(fig_donut(df), use_container_width=True, on_select="rerun", selection_mode="points", key="donut_sel")
            if ev_donut and ev_donut.selection.points:
                estado_click = ev_donut.selection.points[0]["label"]
                show_drilldown(df, estado_click)
        with c2:
            st.plotly_chart(fig_top_atrasos(df), use_container_width=True)

        st.plotly_chart(fig_evolucion(df), use_container_width=True)

        c3, c4 = st.columns([3, 2])
        with c3:
            if not df.empty:
                ev_heat = st.plotly_chart(fig_heatmap(df), use_container_width=True, on_select="rerun", selection_mode="points", key="heat_sel")
                if ev_heat and ev_heat.selection.points:
                    pt = ev_heat.selection.points[0]
                    emp_name = pt["y"]
                    dia_name = pt["x"]
                    show_drilldown(df, None, emp_name, dia_name)
        with c4:
            f_olv = fig_olvidos(df)
            if f_olv:
                st.plotly_chart(f_olv, use_container_width=True)
            else:
                st.info("Sin olvidos de marcación en el periodo seleccionado.")

        st.plotly_chart(fig_horas_empleado(df), use_container_width=True)

    with tab_diaria:
        render_tabla(df)
    with tab_resumen:
        render_resumen(df)
    with tab_justificaciones:
        render_justificaciones(df_raw)

# Login System
def show_login():
    st.markdown("<h1 style='text-align: center;'>Registro Asistencia - Sefil</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>🔐 Acceso Restringido</h3>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.markdown("#### Iniciar Sesión")
            username = st.text_input("Usuario", placeholder="admin / rrhh")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Ingresar", use_container_width=True, type="primary")
            
            if submitted:
                if not username or not password:
                    st.error("❌ Ingresa usuario y contraseña.")
                else:
                    success, role = authenticate_user(username, password)
                    if success:
                        st.session_state.authenticated = True
                        st.session_state.username = username
                        st.session_state.role = role
                        st.toast(f"✅ Bienvenido {username}!", icon="👋")
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas.")

def main():
    try:
        init_default_users()
    except Exception as e:
        pass

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        show_login()
    else:
        main_render()

if __name__ == "__main__":
    main()
