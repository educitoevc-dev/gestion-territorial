import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import json
import re

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y CONEXIÓN
# ==========================================
st.set_page_config(layout="wide", page_title="Dashboard Territorial", page_icon="📊")

if not firebase_admin._apps:
    try:
        key_dict = json.loads(st.secrets["FIREBASE_KEY"])
        cred = credentials.Certificate(key_dict)
    except Exception:
        cred = credentials.Certificate('firebase_cred.json')
        
    firebase_admin.initialize_app(cred)

db = firestore.client()

URL_EXCEL_CUANTITATIVO = "https://docs.google.com/spreadsheets/d/1HdameC4EE1_drytVlQKxtu-1q78PE0HRx0QNqeSXqLo/export?format=csv"

# ==========================================
# 2. MOTOR DE EXTRACCIÓN DE DATOS (ETL)
# ==========================================
@st.cache_data(ttl=300)
def cargar_datos_cuantitativos():
    try:
        df = pd.read_csv(URL_EXCEL_CUANTITATIVO)
        
        # Búsqueda dinámica de encabezados reales
        if 'Estructura' not in df.columns:
            for i, row in df.head(15).iterrows():
                row_str = [str(x) for x in row.values]
                if 'Estructura' in row_str or 'Nombres' in row_str:
                    df.columns = row.values
                    df = df.iloc[i+1:].reset_index(drop=True)
                    break
                    
        # Limpiar saltos de línea (\n) y dobles espacios de los títulos
        df.columns = df.columns.astype(str).str.replace('\n', ' ', regex=False).str.replace(r'\s+', ' ', regex=True).str.strip()
        
        if 'Distrito Federal' in df.columns:
            df = df.rename(columns={'Distrito Federal': 'Distrito'})

        if '% AVANCE' in df.columns:
            df['% AVANCE'] = df['% AVANCE'].astype(str).str.replace('%', '').str.replace(',', '').str.strip()
            df['% AVANCE'] = pd.to_numeric(df['% AVANCE'], errors='coerce').fillna(0)

        cols_numericas = ['META', 'CONVENCIDOS A LA FECHA', 'CONVENCIDOS', 'AVANCE POR DÍA', 'SEPTIEMBRE 01-20', 'AGOSTO 17 - 31',
                          'Total semana 1', 'Total semanal 2', 'Total semanal 3', 
                          'TOTAL S36', 'TOTAL S37', 'TOTAL S38']
        
        for col in cols_numericas:
            if col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        for col_tend in ['TENDENCIA SEMANA 3', 'TENDENCIA S38']:
            if col_tend in df.columns:
                df[col_tend] = df[col_tend].fillna('Sin Registro').astype(str)
            
        return df
    except Exception as e:
        st.error(f"Error al cargar el Excel Cuantitativo: {e}")
        return pd.DataFrame()

def calcular_promedio_lista(lista):
    if isinstance(lista, list) and len(lista) > 0:
        return sum(lista) / len(lista)
    return 0

@st.cache_data(ttl=60)
def cargar_datos_cualitativos_cots():
    try:
        cots_ref = db.collection('evaluaciones_cots').get()
        evals_cots = []
        for doc in cots_ref:
            d = doc.to_dict()
            raw = d.get('raw', {})
            evals_cots.append({
                'Nombres': str(d.get('evaluado', '')).strip(),
                'Conocimientos': calcular_promedio_lista(raw.get('conocimientos', [])),
                'Comunicacion': calcular_promedio_lista(raw.get('comunicacion', [])),
                'Trabajo_Equipo': calcular_promedio_lista(raw.get('equipo', []))
            })
        df_cualitativo = pd.DataFrame(evals_cots)
        if not df_cualitativo.empty:
            df_cualitativo = df_cualitativo.groupby('Nombres').mean().reset_index()
        return df_cualitativo
    except Exception as e:
        st.error(f"Error al conectar con Firebase (COTs): {e}")
        return pd.DataFrame()

@st.cache_data(ttl=60)
def cargar_datos_cualitativos_distritales():
    try:
        dist_ref = db.collection('evaluaciones_distritales').get()
        evals_dist = []
        for doc in dist_ref:
            d = doc.to_dict()
            raw = d.get('raw', {})
            
            # ---> EXTRACCIÓN INTELIGENTE DEL DISTRITO (Soporta "PUEBLA_3", "3", etc.) <---
            dist_raw = str(d.get('distrito', ''))
            match = re.search(r'_(\d+)$', dist_raw)
            if match:
                dist_limpio = match.group(1)
            else:
                dist_limpio = dist_raw.replace('Distrito', '').replace('distrito', '').strip()
                if dist_limpio.replace('.','',1).isdigit():
                    dist_limpio = str(int(float(dist_limpio)))

            # ---> LIMPIEZA DEL NOMBRE (Soporta "Distrito 3 - CRISTELA SANTIAGO" -> "CRISTELA SANTIAGO") <---
            evaluado_raw = str(d.get('evaluado', '')).upper().strip()
            if '-' in evaluado_raw:
                evaluado_limpio = evaluado_raw.split('-')[-1].strip()
            else:
                evaluado_limpio = evaluado_raw

            evals_dist.append({
                'Enlace Distrital': evaluado_limpio,
                'Distrito': dist_limpio,
                'Conviccion': calcular_promedio_lista(raw.get('conviccion', [])),
                'Conocimientos': calcular_promedio_lista(raw.get('conocimientos', [])),
                'Equipo': calcular_promedio_lista(raw.get('equipo', [])),
                'Territorio': calcular_promedio_lista(raw.get('territorio', [])),
                'Regional': calcular_promedio_lista(raw.get('regional', []))
            })
            
        df_dist = pd.DataFrame(evals_dist)
        if not df_dist.empty:
            df_dist = df_dist.groupby(['Distrito', 'Enlace Distrital']).mean().reset_index()
            df_dist['Evaluacion Global'] = df_dist[['Conviccion', 'Conocimientos', 'Equipo', 'Territorio', 'Regional']].mean(axis=1)
        return df_dist
    except Exception as e:
        st.error(f"Error al conectar con Firebase (Distritales): {e}")
        return pd.DataFrame()

# Carga paralela
df_cuant = cargar_datos_cuantitativos()
df_cual_cots = cargar_datos_cualitativos_cots()
df_cual_dist = cargar_datos_cualitativos_distritales()

if not df_cuant.empty and 'Nombres' in df_cuant.columns:
    df_cuant['Nombres'] = df_cuant['Nombres'].astype(str).str.upper().str.strip()

if not df_cual_cots.empty and 'Nombres' in df_cual_cots.columns:
    df_cual_cots['Nombres'] = df_cual_cots['Nombres'].astype(str).str.upper().str.strip()

if not df_cuant.empty and not df_cual_cots.empty and 'Nombres' in df_cuant.columns and 'Nombres' in df_cual_cots.columns:
    df_master = pd.merge(df_cuant, df_cual_cots, on='Nombres', how='left').fillna(0)
else:
    df_master = df_cuant.copy()

# Identificación dinámica de columnas
col_meta = 'META' if 'META' in df_master.columns else None
if 'CONVENCIDOS A LA FECHA' in df_master.columns:
    col_conv = 'CONVENCIDOS A LA FECHA'
elif 'SEPTIEMBRE 01-20' in df_master.columns:
    col_conv = 'SEPTIEMBRE 01-20'
elif 'CONVENCIDOS' in df_master.columns:
    col_conv = 'CONVENCIDOS'
else:
    col_conv = None

col_s1 = 'TOTAL S36' if 'TOTAL S36' in df_master.columns else ('Total semana 1' if 'Total semana 1' in df_master.columns else None)
col_s2 = 'TOTAL S37' if 'TOTAL S37' in df_master.columns else ('Total semanal 2' if 'Total semanal 2' in df_master.columns else None)
col_s3 = 'TOTAL S38' if 'TOTAL S38' in df_master.columns else ('Total semanal 3' if 'Total semanal 3' in df_master.columns else None)
col_tendencia = 'TENDENCIA S38' if 'TENDENCIA S38' in df_master.columns else ('TENDENCIA SEMANA 3' if 'TENDENCIA SEMANA 3' in df_master.columns else None)

# Limpieza de Estados y rescate de celdas vacías en "Estructura"
if not df_master.empty and 'Estado' in df_master.columns:
    df_master = df_master[~df_master['Estado'].astype(str).str.strip().isin(['0', '0.0', 'nan', 'NaN', ''])]

if not df_master.empty and 'Estructura' in df_master.columns:
    df_master['Estructura'] = df_master['Estructura'].fillna('Sin Asignar').replace({'nan': 'Sin Asignar', 'NaN': 'Sin Asignar', '': 'Sin Asignar'})

if 'Distrito' in df_master.columns:
    df_master['Distrito'] = df_master['Distrito'].apply(lambda x: str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x))

# ==========================================
# 3. FILTROS EN CASCADA
# ==========================================
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Morena_logo_%28Mexico%29.svg/2560px-Morena_logo_%28Mexico%29.svg.png", width=150)
st.sidebar.header("📍 Buscador Operativo")

if not df_master.empty:
    estructuras = ["Todas"] + sorted(df_master['Estructura'].astype(str).unique().tolist())
    sel_estructura = st.sidebar.selectbox("1. Estructura:", estructuras)
    if sel_estructura != "Todas":
        df_master = df_master[df_master['Estructura'].astype(str) == sel_estructura]

    estados = ["Todos"] + sorted(df_master['Estado'].dropna().astype(str).unique().tolist())
    sel_estado = st.sidebar.selectbox("2. Estado:", estados)
    if sel_estado != "Todos":
        df_master = df_master[df_master['Estado'].astype(str) == sel_estado]

    distritos_raw = df_master['Distrito'].dropna().unique().tolist()
    try:
        distritos_sorted = sorted(distritos_raw, key=float)
    except ValueError:
        distritos_sorted = sorted(distritos_raw, key=str)
        
    distritos_limpios = [str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x) for x in distritos_sorted]
    distritos = ["Todos"] + list(dict.fromkeys(distritos_limpios))
    
    sel_distrito = st.sidebar.selectbox("3. Distrito:", distritos)
    if sel_distrito != "Todos":
        df_master = df_master[df_master['Distrito'] == sel_distrito]

    st.sidebar.divider()
    st.sidebar.subheader("👤 Búsqueda Individual de COT")
    
    sel_persona = "Todos"
    if sel_estado != "Todos" and 'Nombres' in df_master.columns:
        nombres_disponibles = ["Todos"] + sorted(df_master['Nombres'].dropna().astype(str).unique().tolist())
        sel_persona = st.sidebar.selectbox("Busca el nombre de un perfil:", nombres_disponibles)
        if sel_persona != "Todos":
            df_master = df_master[df_master['Nombres'].astype(str) == sel_persona]
    elif 'Nombres' not in df_master.columns:
        st.sidebar.warning("Columna 'Nombres' no detectada en el Excel.")
    else:
        st.sidebar.info("Selecciona un Estado arriba para habilitar la búsqueda individual.")

# ==========================================
# 4. FRONTEND CON PESTAÑAS (TABS)
# ==========================================
st.title("Panel de Rendimiento Territorial")

if df_master.empty:
    st.info("No hay datos disponibles para la búsqueda actual.")
else:
    tab_cots, tab_distritales = st.tabs(["👥 Operación por COT", "👑 Análisis de Enlaces Distritales"])

    with tab_cots:
        if sel_persona != "Todos":
            st.subheader(f"Radiografía de: {sel_persona}")
            datos_perfil = df_master.iloc[0]
            distrito_limpio = str(datos_perfil.get('Distrito', 'N/A'))
            st.caption(f"📍 **Estado:** {datos_perfil.get('Estado', 'N/A')} | **Distrito:** {distrito_limpio}")
            
            kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
            meta_val = datos_perfil.get(col_meta, 0) if col_meta else 0
            conv_val = datos_perfil.get(col_conv, 0) if col_conv else 0
            
            kpi1.metric("META Total", f"{meta_val:,.0f}")
            kpi2.metric("Convencidos", f"{conv_val:,.0f}")
            kpi3.metric("% Avance", f"{datos_perfil.get('% AVANCE', 0):.1f} %")
            kpi4.metric("Avance por Día", f"{datos_perfil.get('AVANCE POR DÍA', 0):.1f}")
            kpi5.metric("Tendencia Actual", str(datos_perfil.get(col_tendencia, 'Sin Registro')))
            
            st.divider()
            
            st.markdown("### 📈 Línea de Tiempo: Evolución de Resultados")
            if col_s1 and col_s2 and col_s3:
                col_tl_chart, col_tl_info = st.columns([2, 1])
                datos_tiempo = {
                    'Semana': ['Semana 1', 'Semana 2', 'Semana Actual'],
                    'Registros Validados': [
                        datos_perfil.get(col_s1, 0),
                        datos_perfil.get(col_s2, 0),
                        datos_perfil.get(col_s3, 0)
                    ]
                }
                df_tiempo = pd.DataFrame(datos_tiempo).set_index('Semana')
                
                with col_tl_chart:
                    st.line_chart(df_tiempo, color='#880615')
                
                with col_tl_info:
                    st.markdown("**Resumen de Avance**")
                    crecimiento = datos_perfil.get(col_s3, 0) - datos_perfil.get(col_s1, 0)
                    if crecimiento > 0:
                        st.success(f"Crecimiento neto de **+{crecimiento:,.0f}** convencidos.")
                    elif crecimiento < 0:
                        st.error(f"Caída neta de **{crecimiento:,.0f}** convencidos.")
                    else:
                        st.info("Sin variaciones.")
            else:
                st.info("Faltan columnas semanales para graficar la evolución.")

            st.divider()
            
            st.markdown("### 🧠 Radiografía de Habilidades (Evaluaciones de Campo)")
            if 'Comunicacion' in df_master.columns:
                col_chart, col_context = st.columns([2, 1])
                habilidades = {
                    'Comunicación y Persuasión': datos_perfil.get('Comunicacion', 0),
                    'Conocimiento del Territorio': datos_perfil.get('Conocimientos', 0),
                    'Trabajo en Equipo / Actitud': datos_perfil.get('Trabajo_Equipo', 0)
                }
                df_habs = pd.DataFrame(list(habilidades.values()), index=habilidades.keys(), columns=['Calificación (1 a 4)'])
                with col_chart:
                    st.bar_chart(df_habs, horizontal=True)
                with col_context:
                    st.markdown("**Guía de Análisis Rápido**")
                    st.caption("- Escala 1 a 4: 4 es Destacado, 1 Requiere Mejorar.")
            else:
                st.info("Aún no hay evaluaciones cualitativas en Firebase para este perfil.")
        else:
            st.subheader("Diagnóstico Estructural de la Región")
            k_col1, k_col2, k_col3, k_col4 = st.columns(4)
            k_col1.metric("Elementos Activos", f"{len(df_master)}")
            
            sum_conv = df_master[col_conv].sum() if col_conv in df_master.columns else 0
            sum_meta = df_master[col_meta].sum() if col_meta in df_master.columns else 0
            
            k_col2.metric("Total Convencidos", f"{sum_conv:,.0f}")
            k_col3.metric("Meta Global", f"{sum_meta:,.0f}")
            progreso = (sum_conv / sum_meta * 100) if sum_meta > 0 else 0
            k_col4.metric("Progreso Global", f"{progreso:.1f} %")
            
            st.divider()
            
            st.markdown("### 📈 Tendencia de Rendimiento Global (Evolución Semanal)")
            st.caption("Muestra el ritmo de captura de convencidos de toda la región seleccionada a lo largo del tiempo.")
            if col_s1 and col_s2 and col_s3:
                df_tendencia_global = pd.DataFrame({
                    'Semana 1': [df_master[col_s1].sum()],
                    'Semana 2': [df_master[col_s2].sum()],
                    'Semana Actual': [df_master[col_s3].sum()]
                }).T
                df_tendencia_global.columns = ['Registros Validados']
                st.line_chart(df_tendencia_global, color='#880615')
            else:
                st.info("Faltan las columnas semanales en el Excel para graficar la evolución.")

            st.divider()

            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("### 📊 Cumplimiento Promedio por Distrito")
                st.caption("Porcentaje de avance real promedio logrado por los COTs.")
                if '% AVANCE' in df_master.columns:
                    df_avance_dist = df_master.groupby('Distrito')['% AVANCE'].mean().reset_index()
                    df_avance_dist['Distrito'] = "Dist. " + df_avance_dist['Distrito'].astype(str)
                    df_avance_dist = df_avance_dist.sort_values(by='% AVANCE', ascending=False)
                    st.bar_chart(df_avance_dist.set_index('Distrito'), color='#880615')
                else:
                    st.info("No se encontró la columna de avance.")
                    
            with c2:
                st.markdown("### 🚦 Salud de la Fuerza Operativa")
                st.caption("Volumen de COTs agrupados por su ritmo de trabajo reciente.")
                if col_tendencia and col_tendencia in df_master.columns:
                    df_salud = df_master[col_tendencia].value_counts().reset_index()
                    df_salud.columns = ['Estatus', 'Cantidad de COTs']
                    df_salud = df_salud[df_salud['Estatus'] != 'Sin Registro']
                    st.bar_chart(df_salud.set_index('Estatus'), color='#4b5563')
                else:
                    st.info("No se encontraron las columnas de tendencia.")

            st.divider()
            st.markdown("### 🏆 Ranking General de Convencidos")
            if col_conv in df_master.columns:
                col_tab = ['Nombres', 'Distrito', col_meta, col_conv, '% AVANCE', col_tendencia]
                col_ex = [col for col in col_tab if col and col in df_master.columns]
                st.dataframe(df_master[col_ex].sort_values(by=col_conv, ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info("No se encontró la columna de convencidos.")

    with tab_distritales:
        st.subheader("Análisis de Liderazgo Distrital")
        st.write("Cruce de la Evaluación Institucional (Cualitativa) vs el Avance Real de su Distrito (Cuantitativo).")
        
        if sel_persona != "Todos":
            st.info("⚠️ Para ver el análisis de Enlaces Distritales, debes quitar el filtro de búsqueda individual de COT en el menú lateral.")
        else:
            if col_s1 and col_s3:
                agg_dict = {
                    'Nombres': 'count',
                    col_s1: 'mean',
                    col_s3: 'mean'
                }
                if col_meta: agg_dict[col_meta] = 'sum'
                if col_conv: agg_dict[col_conv] = 'sum'
                
                df_distrito_cuant = df_master.groupby('Distrito').agg(agg_dict).reset_index()
                df_distrito_cuant = df_distrito_cuant.rename(columns={'Nombres': 'COTs_Activos'})
                
                meta_col_name = col_meta if col_meta else 'COTs_Activos'
                conv_col_name = col_conv if col_conv else 'COTs_Activos'
                
                df_distrito_cuant['% Avance Distrito'] = df_distrito_cuant.apply(
                    lambda row: (row[conv_col_name] / row[meta_col_name] * 100) if meta_col_name in row and row[meta_col_name] > 0 else 0, axis=1
                )
                
                df_distrito_cuant['Tendencia Neta (S3 - S1)'] = df_distrito_cuant[col_s3] - df_distrito_cuant[col_s1]
                
                st.markdown("### 🏅 Ranking Operativo por Distrito (Convencidos Totales)")
                st.caption("Muestra el volumen total de captura consolidado a nivel distrital.")
                df_ranking_dist = df_distrito_cuant[['Distrito', conv_col_name]].copy()
                df_ranking_dist['Distrito'] = "Distrito " + df_ranking_dist['Distrito'].astype(str)
                df_ranking_dist = df_ranking_dist.set_index('Distrito').sort_values(by=conv_col_name, ascending=False)
                
                st.bar_chart(df_ranking_dist, color="#880615")
                
                st.divider()
                
                df_analisis = pd.merge(df_distrito_cuant, df_cual_dist, on='Distrito', how='inner') if not df_cual_dist.empty else pd.DataFrame()
                
                if df_analisis.empty:
                    st.info("Aún no hay evaluaciones cualitativas registradas en Firebase que coincidan con los distritos seleccionados.")
                else:
                    st.markdown("### 📊 Desglose de Evaluación y Tendencia por Distrito")
                    
                    # ---> FORMATO SOLICITADO: Nombre del Distrital con su número de distrito (D#) <---
                    df_analisis['Etiqueta Distrital'] = df_analisis['Enlace Distrital'] + " (D" + df_analisis['Distrito'].astype(str) + ")"
                    enlaces_disponibles = sorted(df_analisis['Etiqueta Distrital'].unique().tolist())
                    
                    sel_enlace_etiqueta = st.selectbox("Selecciona un Enlace Distrital para ver su radiografía:", enlaces_disponibles)
                    
                    datos_enlace = df_analisis[df_analisis['Etiqueta Distrital'] == sel_enlace_etiqueta].iloc[0]
                    
                    kcol1, kcol2, kcol3, kcol4 = st.columns(4)
                    kcol1.metric("Distrito a Cargo", f"D - {datos_enlace['Distrito']}")
                    kcol2.metric("Evaluación Global (Web)", f"{datos_enlace['Evaluacion Global']:.2f} / 4.0")
                    kcol3.metric("Avance Operativo (COTs)", f"{datos_enlace['% Avance Distrito']:.1f} %")
                    kcol4.metric("Tendencia Promedio", f"{datos_enlace['Tendencia Neta (S3 - S1)']:.1f} registros")
                    
                    st.write("")
                    
                    col_chart_dist, col_ctx_dist = st.columns([2, 1])
                    
                    vars_dist = {
                        '1. Convicción y Principios': datos_enlace['Conviccion'],
                        '2. Conocimientos y Derechos': datos_enlace['Conocimientos'],
                        '3. Gestión de Equipo': datos_enlace['Equipo'],
                        '4. Gestión de Territorio': datos_enlace['Territorio'],
                        '5. Operación Regional': datos_enlace['Regional']
                    }
                    df_vars_dist = pd.DataFrame(list(vars_dist.values()), index=vars_dist.keys(), columns=['Calificación'])
                    
                    with col_chart_dist:
                        st.bar_chart(df_vars_dist, horizontal=True)
                        
                    with col_ctx_dist:
                        st.info("**Variables Evaluadas:**\n\n- **Convicción:** Alineación a la narrativa.\n- **Equipo:** Manejo de conflictos.\n- **Territorio:** Auditoría de bitácoras y kilometraje.\n- **Regional:** Adaptabilidad táctica.")
                    
                    st.divider()
                    st.markdown("### Ranking Analítico de Distritales")
                    columnas_tabla_dist = ['Enlace Distrital', 'Distrito', 'COTs_Activos', conv_col_name, '% Avance Distrito', 'Tendencia Neta (S3 - S1)', 'Evaluacion Global']
                    
                    df_final_view = df_analisis[columnas_tabla_dist].sort_values(by='Evaluacion Global', ascending=False)
                    st.dataframe(df_final_view, use_container_width=True, hide_index=True)
            else:
                st.error("Faltan las columnas de métricas semanales en el Excel para calcular las tendencias del distrito.")