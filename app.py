import streamlit as st
import pandas as pd
import ast

# Configuración inicial
st.set_page_config(layout="wide", page_title="Monitoreo Distrital")
st.title("📊 Panel de Monitoreo Distrital")

# --- 1. URLs DE GOOGLE SHEETS ---
# URL Original de la Base de Datos de Monitoreo Diario
url_diario = "https://docs.google.com/spreadsheets/d/1lYeaaQXr6nyqjOUO2gD_udNm30eKKXiWeUz3kG1Gm8I/export?format=csv&gid=1695625429"

# URLs del nuevo archivo de evaluaciones (Usando la API de Google Visualization)
sheet_id_evals = "1_jb56qjEFKyNWqwwqVbu80QiA9U6TSEZsPwzmHj2oII"
url_eval_dist = f"https://docs.google.com/spreadsheets/d/{sheet_id_evals}/gviz/tq?tqx=out:csv&sheet=Evaluacion_Distritales"
url_eval_sat = f"https://docs.google.com/spreadsheets/d/{sheet_id_evals}/gviz/tq?tqx=out:csv&sheet=Satisfaccion_COT_Distrital"
url_eval_cots = f"https://docs.google.com/spreadsheets/d/{sheet_id_evals}/gviz/tq?tqx=out:csv&sheet=Evaluacion_COTs"

# --- 2. DICCIONARIO DE DISTRITALES ---
dict_distritales = {
    'PUEBLA_8': 'DANIEL PALOMARES SOLARES', 'PUEBLA_7': 'MARCOANTONIO CAMPOS BARRALES',
    'PUEBLA_10': 'MARIBEL FLORES GARCIA', 'PUEBLA_1': 'ALVA JOCABED FLORENTINO LIRA',
    'PUEBLA_13': 'ALEXIS DANIEL ROSARIO PIEDRA', 'PUEBLA_14': 'TRINIDAD SALAS CASTILLO',
    'PUEBLA_12': 'IZTAC HERNANDEZ QUITERIO', 'PUEBLA_16': 'RENE ROSALES ZAVALETA',
    'PUEBLA_4': 'JOSE HUGO LOPEZ GARCIA', 'PUEBLA_6': 'MARTIN AGUILA CONDE',
    'PUEBLA_2': 'JESSSICA YARENI PEREZ SALAS', 'PUEBLA_9': 'TANIA ANDREA GUERRERO ESPINOSA',
    'PUEBLA_3': 'CRISTELA SANTIAGO HERNANDEZ', 'PUEBLA_15': 'ROSALBA ROSALES GALVEZ',
    'PUEBLA_5': 'MARIELA VERA SALGADO', 'PUEBLA_11': 'KAREN ITZEL ZONOTL GALLARDO',
    'HIDALGO_7': 'VICTOR HECTOR VALENZUELA GOMEZ', 'HIDALGO_2': 'YONATTAN ALVAREZ CRUZ',
    'HIDALGO_1': 'DESIDERIO QUIJANO ANGELES', 'HIDALGO_3': 'JOSE IGNACIO OLVERA CABALLERO',
    'HIDALGO_5': 'TANIA YVONNE PORRAS VEGA', 'HIDALGO_6': 'RUBEN HERNANDEZ MARTINEZ',
    'HIDALGO_4': 'MARIO MIGUEL HERNANDEZ ESCAMILLA', 'TLAXCALA_3': 'JORGE ISRAEL LARA LARA',
    'TLAXCALA_1': 'MARCO ANTONIO ROJAS GONZALEZ', 'TLAXCALA_2': 'ERICK FLORES VAZQUEZ'
}

# --- 3. FUNCIONES DE EXTRACCIÓN Y LIMPIEZA ---
def parse_list(val_str, expected_len):
    """Convierte el string de la lista de Google Sheets en una lista de Python."""
    try:
        lista = ast.literal_eval(str(val_str))
        if isinstance(lista, list):
            return (lista + [0]*expected_len)[:expected_len]
    except:
        pass
    return [0]*expected_len

def get_mean_arr(series, length):
    """Saca el promedio vertical de cada indicador específico de las listas."""
    lista_listas = [x for x in series.tolist() if isinstance(x, list) and len(x) == length]
    if not lista_listas: return [0]*length
    return [sum(col)/len(col) for col in zip(*lista_listas)]

@st.cache_data(ttl=5) 
def cargar_datos_diarios():
    try:
        df = pd.read_csv(url_diario, header=1)
        df['Fecha'] = pd.to_datetime(df['Fecha'], errors='coerce')
        cols_numericas = ['Convencidos Hoy', 'Horas totales de brigadeo Hoy', 'Visitas en conjunto Hoy', 'Meta de convencidos Total ', 'No. de Visitas Planificadas', 'No. de Visitas Cumplidas']
        for col in cols_numericas:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        return df.dropna(subset=['Fecha']) 
    except:
        return pd.DataFrame()

@st.cache_data(ttl=5)
def cargar_eval_distritales():
    try:
        df = pd.read_csv(url_eval_dist, header=None)
        if df.empty: return pd.DataFrame()
        df.columns = ['Fecha', 'Timestamp', 'Evaluador', 'Evaluado', 'Distrito', 'Conviccion', 'Conocimientos', 'Equipo', 'Territorio', 'Regional']
        
        df['Conviccion_Arr'] = df['Conviccion'].apply(lambda x: parse_list(x, 2))
        df['Conocimientos_Arr'] = df['Conocimientos'].apply(lambda x: parse_list(x, 2))
        df['Equipo_Arr'] = df['Equipo'].apply(lambda x: parse_list(x, 6))
        df['Territorio_Arr'] = df['Territorio'].apply(lambda x: parse_list(x, 7))
        df['Regional_Arr'] = df['Regional'].apply(lambda x: parse_list(x, 5))
        
        for col in ['Conviccion', 'Conocimientos', 'Equipo', 'Territorio', 'Regional']:
            df[col] = df[f'{col}_Arr'].apply(lambda x: sum(x)/len(x) if x else 0)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=5)
def cargar_eval_satisfaccion():
    try:
        df = pd.read_csv(url_eval_sat, header=None)
        if df.empty: return pd.DataFrame()
        df.columns = ['Fecha', 'Timestamp', 'CURP_COT', 'Distrital_Nombre', 'Distrito', 'Puntaje_Total', 'Indice', 'Detalle_Puntajes']
        df['Indice'] = pd.to_numeric(df['Indice'], errors='coerce').fillna(0)
        df['Puntajes_Arr'] = df['Detalle_Puntajes'].apply(lambda x: parse_list(x, 5))
        return df
    except:
        return pd.DataFrame()

# Cargar las bases
df_diario = cargar_datos_diarios()
df_dist = cargar_eval_distritales()
df_sat = cargar_eval_satisfaccion()

# --- 4. BARRA LATERAL (FILTROS) ---
st.sidebar.header("📍 Filtros Territoriales")

# Construir opciones del menú desplegable
opciones_formateadas = {"Todos": "Todos"}
for dist_id, nombre in dict_distritales.items():
    texto = f"{dist_id.replace('_', ' - Distrito ')}: {nombre}"
    opciones_formateadas[dist_id] = texto

lista_opciones = ["Todos"] + sorted(list(dict_distritales.keys()))

distrito_seleccionado = st.sidebar.selectbox(
    "Selecciona un Enlace Distrital:",
    options=lista_opciones,
    format_func=lambda x: opciones_formateadas.get(x, x)
)

# Aplicar filtros
if distrito_seleccionado != "Todos":
    num_distrito = distrito_seleccionado.split('_')[-1]
    
    if not df_diario.empty and 'Distrito' in df_diario.columns:
        df_filt_diario = df_diario[df_diario['Distrito'].astype(str) == num_distrito]
    else:
        df_filt_diario = df_diario.copy()
        
    if not df_dist.empty and 'Distrito' in df_dist.columns:
        df_filt_dist = df_dist[df_dist['Distrito'].astype(str) == distrito_seleccionado]
    else:
        df_filt_dist = df_dist.copy()
        
    if not df_sat.empty and 'Distrito' in df_sat.columns:
        df_filt_sat = df_sat[df_sat['Distrito'].astype(str) == distrito_seleccionado]
    else:
        df_filt_sat = df_sat.copy()
        
    st.subheader(f"Resultados para: {opciones_formateadas[distrito_seleccionado]}")
else:
    df_filt_diario = df_diario.copy()
    df_filt_dist = df_dist.copy()
    df_filt_sat = df_sat.copy()
    st.subheader("Resultados Globales Nacionales")

# --- 5. ORGANIZACIÓN EN PESTAÑAS (TABS) ---
tab1, tab2, tab3 = st.tabs(["📅 Monitoreo Diario", "📈 Desempeño Distritales", "⭐ Satisfacción COT a Distrital"])

# ==========================================
# PESTAÑA 1: OPERACIÓN DIARIA
# ==========================================
with tab1:
    if df_filt_diario.empty:
        st.warning("No hay datos diarios cargados para este distrito todavía.")
    else:
        # Metas y Ritmo
        st.markdown("### 🎯 Metas y Ritmo de Trabajo")
        col1, col2, col3, col4 = st.columns(4)
        
        meta_total = df_filt_diario['Meta de convencidos Total '].max()
        convencidos_totales = df_filt_diario['Convencidos Hoy'].sum()
        faltan = meta_total - convencidos_totales if meta_total > 0 else 0
        promedio_diario = df_filt_diario['Convencidos Hoy'].replace(0, pd.NA).dropna().mean()
        
        if pd.isna(promedio_diario): promedio_diario = 0
        ritmo = "Bajo 🔴"
        if promedio_diario >= 15: ritmo = "Óptimo 🟢"
        elif promedio_diario >= 10: ritmo = "Competente 🟡"

        col1.metric("Meta Total", f"{meta_total:,.0f}")
        col2.metric("Avance Total", f"{convencidos_totales:,.0f}", f"Faltan: {faltan:,.0f}")
        col3.metric("Promedio por Día", f"{promedio_diario:.1f}")
        col4.metric("Ritmo de Trabajo", ritmo)

        st.divider()

        # Avance temporal
        st.markdown("### 📈 Avance a través del tiempo")
        df_tiempo = df_filt_diario.groupby('Fecha')[['Convencidos Hoy', 'Visitas en conjunto Hoy']].sum().reset_index().set_index('Fecha')
        
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.markdown("**Afiliaciones por día (Convencidos Hoy)**")
            st.line_chart(df_tiempo['Convencidos Hoy'])
        with col_t2:
            st.markdown("**Presencia en Territorio (Visitas en Conjunto)**")
            st.line_chart(df_tiempo['Visitas en conjunto Hoy'])

        st.divider()

        # Correlación y Planeación
        st.markdown("### 🔍 Correlaciones y Planeación Operativa")
        col_c1, col_c2 = st.columns(2)
        
        with col_c1:
            st.markdown("**Esfuerzo vs Resultados (Horas vs Convencidos)**")
            if 'Horas totales de brigadeo Hoy' in df_filt_diario.columns and 'Convencidos Hoy' in df_filt_diario.columns:
                st.scatter_chart(df_filt_diario, x='Horas totales de brigadeo Hoy', y='Convencidos Hoy', size='Visitas en conjunto Hoy')
                
        with col_c2:
            st.markdown("**Eficiencia de Planeación**")
            visitas_plan = df_filt_diario['No. de Visitas Planificadas'].sum()
            visitas_cump = df_filt_diario['No. de Visitas Cumplidas'].sum()
            porcentaje_cump = (visitas_cump / visitas_plan * 100) if visitas_plan > 0 else 0
            
            st.metric("Cumplimiento de Planes", f"{porcentaje_cump:.1f}%")
            st.write(f"Visitas Planificadas: **{visitas_plan:,.0f}** | Cumplidas: **{visitas_cump:,.0f}**")

# ==========================================
# PESTAÑA 2: EVALUACIÓN DISTRITALES
# ==========================================
with tab2:
    if df_filt_dist.empty:
        st.info("Aún no hay evaluaciones de desempeño registradas para este Enlace Distrital en la nube.")
    else:
        st.markdown("### 📈 Desempeño General del Enlace Distrital")
        st.write("Escala de 1 a 4. Evaluación realizada por Coordinación de Monitoreo Central.")
        
        # Promedios generales por variable
        cols_metricas = ['Conviccion', 'Conocimientos', 'Equipo', 'Territorio', 'Regional']
        promedios = {col: df_filt_dist[col].mean() for col in cols_metricas}
        
        # Desglose de arreglos por indicador
        conv_arr = get_mean_arr(df_filt_dist['Conviccion_Arr'], 2)
        conoc_arr = get_mean_arr(df_filt_dist['Conocimientos_Arr'], 2)
        eq_arr = get_mean_arr(df_filt_dist['Equipo_Arr'], 6)
        terr_arr = get_mean_arr(df_filt_dist['Territorio_Arr'], 7)
        reg_arr = get_mean_arr(df_filt_dist['Regional_Arr'], 5)

        st.divider()
        cols = st.columns(5)
        
        with cols[0]:
            st.metric("🔥 Convicción", f"{promedios['Conviccion']:.1f}")
            st.caption(f"Principios: **{conv_arr[0]:.1f}**")
            st.caption(f"Congruencia Narrativa: **{conv_arr[1]:.1f}**")
            
        with cols[1]:
            st.metric("🧠 Conocimientos", f"{promedios['Conocimientos']:.1f}")
            st.caption(f"Derechos Const.: **{conoc_arr[0]:.1f}**")
            st.caption(f"Territorio: **{conoc_arr[1]:.1f}**")
            
        with cols[2]:
            st.metric("🤝 Trabajo Equipo", f"{promedios['Equipo']:.1f}")
            st.caption(f"Liderazgo Partic.: **{eq_arr[0]:.1f}**")
            st.caption(f"Monitoreo COT: **{eq_arr[1]:.1f}**")
            st.caption(f"Organización: **{eq_arr[2]:.1f}**")
            st.caption(f"Decisiones: **{eq_arr[3]:.1f}**")
            st.caption(f"Comunicación: **{eq_arr[4]:.1f}**")
            st.caption(f"Escucha Activa: **{eq_arr[5]:.1f}**")
            
        with cols[3]:
            st.metric("🗺️ Territorio", f"{promedios['Territorio']:.1f}")
            st.caption(f"Herramientas: **{terr_arr[0]:.1f}**")
            st.caption(f"Rev. Bitácoras: **{terr_arr[1]:.1f}**")
            st.caption(f"Rev. Recorridos: **{terr_arr[2]:.1f}**")
            st.caption(f"Kilometraje: **{terr_arr[3]:.1f}**")
            st.caption(f"Solicitudes: **{terr_arr[4]:.1f}**")
            st.caption(f"Presencia: **{terr_arr[5]:.1f}**")
            st.caption(f"Inconsistencias: **{terr_arr[6]:.1f}**")
            
        with cols[4]:
            st.metric("📋 Op. Regional", f"{promedios['Regional']:.1f}")
            st.caption(f"Comprensión Tareas: **{reg_arr[0]:.1f}**")
            st.caption(f"Tiempos Resp.: **{reg_arr[1]:.1f}**")
            st.caption(f"Capacitaciones: **{reg_arr[2]:.1f}**")
            st.caption(f"Uso Herramientas: **{reg_arr[3]:.1f}**")
            st.caption(f"Retroalimentación: **{reg_arr[4]:.1f}**")

        st.divider()
        df_radar = pd.DataFrame(list(promedios.values()), index=promedios.keys(), columns=['Calificación Promedio'])
        st.bar_chart(df_radar, horizontal=True)

# ==========================================
# PESTAÑA 3: SATISFACCIÓN COT A DISTRITAL
# ==========================================
with tab3:
    if df_filt_sat.empty:
        st.info("Los COTs aún no han enviado evaluaciones de satisfacción para este Enlace Distrital.")
    else:
        st.markdown("### ⭐ Nivel de Satisfacción y Clima Laboral")
        st.write("Índice de 0% a 100% que refleja cómo evalúan los COTs el liderazgo de su Enlace Distrital.")
        
        indice_promedio = df_filt_sat['Indice'].mean()
        total_respuestas = len(df_filt_sat)
        
        estado = "Crítico 🔴"
        if indice_promedio >= 90: estado = "Sobresaliente 🌟"
        elif indice_promedio >= 75: estado = "Satisfactorio 🟢"
        elif indice_promedio >= 60: estado = "Regular 🟡"
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Índice de Satisfacción Promedio", f"{indice_promedio:.1f}%")
        col2.metric("Nivel de Desempeño General", estado)
        col3.metric("Evaluaciones de COTs Recibidas", total_respuestas)
        
        st.divider()
        
        st.markdown("### 🔍 Desglose por Indicador de Satisfacción")
        st.write("Promedio de calificación de cada indicador específico en una escala de 1 al 4:")
        
        sat_arr = get_mean_arr(df_filt_sat['Puntajes_Arr'], 5)
        
        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        sc1.metric("Acompañamiento", f"{sat_arr[0]:.1f}")
        sc2.metric("Claridad Asignación", f"{sat_arr[1]:.1f}")
        sc3.metric("Clima y Cohesión", f"{sat_arr[2]:.1f}")
        sc4.metric("Receptividad Feedback", f"{sat_arr[3]:.1f}")
        sc5.metric("Satisfacción Global", f"{sat_arr[4]:.1f}")
        
        st.divider()
        st.markdown("**Tabla Resumen por Enlace Distrital:**")
        
        # Agrupar por Distrital
        df_agrupado = df_filt_sat.groupby(['Distrito', 'Distrital_Nombre'])['Indice'].agg(['mean', 'count']).reset_index()
        df_agrupado.columns = ['Distrito (ID)', 'Enlace Distrital', 'Índice Promedio (%)', 'Evaluaciones Recibidas']
        st.dataframe(df_agrupado.style.format({'Índice Promedio (%)': '{:.1f}%'}), use_container_width=True, hide_index=True)