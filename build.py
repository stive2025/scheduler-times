import re

with open('app.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace imports
old_imports = '''import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path'''

new_imports = '''import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from pathlib import Path
from datetime import datetime

from backend.database import get_engine
from backend.sync import sync_from_excel, get_last_sync, get_total_records
from backend.justifications import add_justification, remove_justification, list_justifications
from backend.auth import authenticate_user, change_password, init_default_users'''

code = code.replace(old_imports, new_imports)

# Replace load_data
old_load_data_match = re.search(r'@st\.cache_data.*?def load_data.*?return df', code, re.DOTALL)
new_load_data = '''@st.cache_data(show_spinner="Cargando datos desde PostgreSQL...")
def load_data() -> pd.DataFrame:
    query = """
        SELECT 
            employee_id, employee_name as "Nombre", fecha as "Fecha", 
            horario_detectado as "Horario Detectado", jornada as "Jornada",
            entrada_manana as "Entrada Mañana", salida_manana as "Salida Mañana",
            entrada_tarde as "Entrada Tarde", salida_tarde as "Salida Tarde",
            atraso_manana as "atr_man", atraso_tarde as "atr_tar",
            atraso_total as "total_atraso", salida_anticipada as "total_sal_ant",
            horas_trabajadas as "horas_trab", evento as "Evento",
            estado_dia as "estado", tiene_olvido as "tiene_olvido", 
            dia_semana_es as "dia_es", mes, nombre_corto as "nom_corto"
        FROM attendance_daily
    """
    engine = get_engine()
    df = pd.read_sql(query, engine)
    
    if not df.empty:
        df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce")
        df["olvidos"] = df["tiene_olvido"].astype(int)
        df["employee_id"] = df["employee_id"].astype(str)
        df["employee_name"] = df["Nombre"]
    else:
        df["Fecha"] = pd.Series(dtype='datetime64[ns]')
        df["olvidos"] = pd.Series(dtype=int)
        df["employee_id"] = pd.Series(dtype=str)
        df["employee_name"] = pd.Series(dtype=str)

    return df'''
code = code.replace(old_load_data_match.group(0), new_load_data)

# Sidebar with sync and account
old_sidebar_match = re.search(r'def sidebar.*?return f_ini, f_fin, sel_emp, sel_jor, sel_est', code, re.DOTALL)
new_sidebar = '''def sidebar(df: pd.DataFrame):
    with st.sidebar:
        st.markdown("""
        <div style='text-align:center;padding:12px 0 20px'>
          <div style='font-size:2rem'><img src='app/img/icon.png' width='80'></div>
          <div style='font-size:1.05rem;font-weight:700;color:#3fb950'>SEFIL S.A.</div>
          <div style='font-size:.72rem;color:#8b949e;margin-top:3px'>Control de Asistencias</div>
        </div>""", unsafe_allow_html=True)
        
        st.markdown("### ⚙️ Mi Cuenta")
        st.info(f"👤 Usuario: **{st.session_state.username}**\\n\\n🛡️ Rol: **{st.session_state.role}**")
        
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
                st.caption(f"Última sync: {last_sync.strftime('%d/%m/%Y %H:%M')}")
            st.caption(f"Registros en BD: {total_records}")
            
            if st.button("🔄 Recargar Datos", use_container_width=True, type="secondary"):
                st.cache_data.clear()
                st.toast("Datos recargados desde la base de datos.", icon="🔄")
                st.rerun()
                
            if st.button("⚙️ Forzar Sincronización DB", use_container_width=True, type="primary"):
                with st.spinner("Sincronizando con Excel..."):
                    try:
                        added, updated = sync_from_excel()
                        st.cache_data.clear()
                        st.success(f"✅ Sync exitosa: {added} nuevos, {updated} actualizados.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        
            st.markdown("---")

        st.markdown("### 🗓 Rango de Fechas")
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
        estados = ["Todos", "A Tiempo", "Con Atraso", "Salida Anticipada", "Olvido"]
        sel_est = st.selectbox("Filtrar por estado", estados)

        st.markdown("---")
        st.caption("Sefil S.A. Todos los derechos reservados")

    return f_ini, f_fin, sel_emp, sel_jor, sel_est'''
code = code.replace(old_sidebar_match.group(0), new_sidebar)

# New Justifications and Calendar tabs logic
new_tabs = '''
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
                    st.markdown(f"**{j['fecha']}**\\n{j['tipo']}")
                with c2:
                    st.markdown(f"**{j['employee_name']}** (ID: {j['employee_id']})\\n*Motivo:* {j['reason']}")
                with c3:
                    if st.session_state.role != "rrhh":
                        if st.button("🗑️ Eliminar", key=f"del_{j['id']}"):
                            remove_justification(j['id'])
                            st.toast("🗑️ Justificación eliminada.")
                            st.cache_data.clear()
                            st.rerun()
                st.markdown("---")

def render_calendario(df: pd.DataFrame):
    st.markdown("### 📅 Calendario Mensual de Asignaciones")
    if df.empty:
        st.warning("No hay datos para mostrar en el calendario.")
        return
        
    df_cal = df[['employee_id', 'Nombre', 'Fecha', 'estado']].copy()
    df_cal['Fecha'] = df_cal['Fecha'].dt.strftime('%d/%m/%Y')
    df_pivot = df_cal.pivot_table(index=['employee_id', 'Nombre'], columns='Fecha', values='estado', aggfunc='first').reset_index()
    
    st.dataframe(df_pivot, use_container_width=True, hide_index=True)

# Replace the tabs logic
def main_render():
    df_raw = load_data()
    f_ini, f_fin, sel_emp, sel_jor, sel_est = sidebar(df_raw)

    if df_raw.empty:
        st.warning("La base de datos está vacía. Sincroniza los datos primero.")
        return

    df = df_raw[(df_raw["Fecha"].dt.date >= f_ini) & (df_raw["Fecha"].dt.date <= f_fin)].copy()

    if sel_emp:
        df = df[df["nom_corto"].isin(sel_emp)]
    if sel_jor != "Todas":
        df = df[df["Jornada"] == sel_jor]
    if sel_est != "Todos":
        df = df[df["estado"] == sel_est]

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
        if not df.empty:
            st.plotly_chart(fig_heatmap(df), use_container_width=True)
    with c4:
        f_olv = fig_olvidos(df)
        if f_olv:
            st.plotly_chart(f_olv, use_container_width=True)
        else:
            st.info("Sin olvidos de marcacion en el periodo seleccionado.")

    st.plotly_chart(fig_horas_empleado(df), use_container_width=True)

    st.markdown("---")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📅 Vista Diaria", "📊 Resumen", "📝 Justificaciones", "📆 Calendario Mensual"])
    with tab1:
        render_tabla(df)
    with tab2:
        render_resumen(df)
    with tab3:
        render_justificaciones(df_raw)
    with tab4:
        render_calendario(df)

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
'''
old_main_match = re.search(r'def main\(\):.*', code, re.DOTALL)
code = code.replace(old_main_match.group(0), new_tabs)

# Page configuration edits
code = code.replace('page_title="Registro de Asistencias · Sefil",', 'page_title="Registro Asistencia - Sefil",')
code = code.replace('page_icon="📊",', 'page_icon="app/img/icon.png",')

with open('app_dashboard.py', 'w', encoding='utf-8') as f:
    f.write(code)

print('Dashboard reconstructed successfully!')
