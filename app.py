import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y CONEXIÓN
# ==========================================
st.set_page_config(layout="wide", page_title="Dashboard Territorial", page_icon="📊")

import json

if not firebase_admin._apps:
    try:
        # Intenta leer la llave desde la bóveda secreta de Streamlit Cloud
        key_dict = json.loads(st.secrets["FIREBASE_KEY"])
        cred = credentials.Certificate(key_dict)
    except Exception:
        # Si no encuentra el secreto (porque estás en tu computadora), usa el archivo local
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
        
        if 'Distrito Federal' in df.columns:
            df = df.rename(columns={'Distrito Federal': 'Distrito'})

        if '% AVANCE' in df.columns:
            df['% AVANCE'] = df['% AVANCE'].astype(str).str.replace('%', '').str.replace(',', '').str.strip()
            df['% AVANCE'] = pd.to_numeric(df['% AVANCE'], errors='coerce').fillna(0)

        cols_numericas = ['META', 'CONVENCIDOS', 'AVANCE POR DÍA', 'Promedio Semenal', 
                          'Promedio al Mes', 'Total semana 1', 'Total semanal 2', 'Total semanal 3']
        
        for col in cols_numericas:
            if col in df.columns:
                if df[col].dtype == object:
                    df[col] = df[col].astype(str).str.replace(',', '')
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        if 'TENDENCIA SEMANA 3' in df.columns:
            df['TENDENCIA SEMANA 3'] = df['TENDENCIA SEMANA 3'].fillna('Sin Registro').astype(str)
                
        return df
    except Exception as e:
        st.error(f"Error al cargar el Excel Cuantitativo: {e}")
        return pd.DataFrame()

def calcular_promedio_lista(lista):
    if isinstance(lista, list) and len(lista) > 0:
        return sum(lista) / len(lista)
    return 0

@st.cache_data(ttl=60)
def cargar_datos_cualitativos():
    try:
        cots_ref = db.collection('evaluaciones_cots').get()
        evals_cots = []
        for doc in cots_ref:
            d = doc.to_dict()
            raw = d.get('raw', {})
            evals_cots.append({
                'Nombres': d.get('evaluado', ''),
                'Conocimientos': calcular_promedio_lista(raw.get('conocimientos', [])),
                'Comunicacion': calcular_promedio_lista(raw.get('comunicacion', [])),
                'Trabajo_Equipo': calcular_promedio_lista(raw.get('equipo', []))
            })
        df_cualitativo = pd.DataFrame(evals_cots)
        if not df_cualitativo.empty:
            df_cualitativo = df_cualitativo.groupby('Nombres').mean().reset_index()
        return df_cualitativo
    except Exception as e:
        st.error(f"Error al conectar con Firebase: {e}")
        return pd.DataFrame()

df_cuant = cargar_datos_cuantitativos()
df_cual = cargar_datos_cualitativos()

if not df_cuant.empty and not df_cual.empty:
    df_cuant['Nombres'] = df_cuant.get('Nombres', '').astype(str).str.upper().str.strip()
    df_cual['Nombres'] = df_cual['Nombres'].astype(str).str.upper().str.strip()
    df_master = pd.merge(df_cuant, df_cual, on='Nombres', how='left').fillna(0)
else:
    df_master = df_cuant.copy()

# Filtro de limpieza para eliminar el Estado "0" y vacíos
if not df_master.empty and 'Estado' in df_master.columns:
    df_master = df_master[~df_master['Estado'].astype(str).str.strip().isin(['0', '0.0', 'nan', 'NaN', ''])]

# ==========================================
# 3. FILTROS EN CASCADA (BUSCADORES INTELIGENTES)
# ==========================================
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/Morena_logo_%28Mexico%29.svg/2560px-Morena_logo_%28Mexico%29.svg.png", width=150)
st.sidebar.header("📍 Buscador Operativo")
st.sidebar.caption("🔍 Puedes teclear directamente en las cajas para buscar más rápido.")

if not df_master.empty:
    estructuras = ["Todas"] + sorted(df_master['Estructura'].dropna().astype(str).unique().tolist())
    sel_estructura = st.sidebar.selectbox("1. Estructura:", estructuras)
    if sel_estructura != "Todas":
        df_master = df_master[df_master['Estructura'].astype(str) == sel_estructura]

    estados = ["Todos"] + sorted(df_master['Estado'].dropna().astype(str).unique().tolist())
    sel_estado = st.sidebar.selectbox("2. Estado:", estados)
    if sel_estado != "Todos":
        df_master = df_master[df_master['Estado'].astype(str) == sel_estado]

    # ---> CORRECCIÓN: ORDENAMIENTO MATEMÁTICO DE DISTRITOS <---
    distritos_raw = df_master['Distrito'].dropna().unique().tolist()
    try:
        # Forzar orden matemático para que el 2 vaya antes que el 10
        distritos_sorted = sorted(distritos_raw, key=float)
    except ValueError:
        # Respaldo por si se coló un distrito con letras
        distritos_sorted = sorted(distritos_raw, key=str)
        
    # Limpiar los ".0" para la vista en el menú desplegable
    distritos_limpios = [str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x) for x in distritos_sorted]
    distritos = ["Todos"] + list(dict.fromkeys(distritos_limpios))
    
    sel_distrito = st.sidebar.selectbox("3. Distrito:", distritos)
    if sel_distrito != "Todos":
        # Asegurarnos de limpiar también la base original al comparar para que hagan "match"
        df_master = df_master[df_master['Distrito'].apply(lambda x: str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x)) == sel_distrito]

    st.sidebar.divider()
    st.sidebar.subheader("👤 Búsqueda Individual")
    
    sel_persona = "Todos"
    if sel_estado != "Todos":
        nombres_disponibles = ["Todos"] + sorted(df_master['Nombres'].dropna().astype(str).unique().tolist())
        sel_persona = st.sidebar.selectbox("Busca el nombre de un perfil:", nombres_disponibles)
        
        if sel_persona != "Todos":
            df_master = df_master[df_master['Nombres'].astype(str) == sel_persona]
    else:
        st.sidebar.info("Selecciona un Estado arriba para habilitar la búsqueda individual.")

# ==========================================
# 4. TABLEROS VISUALES (FRONTEND)
# ==========================================
st.title("Panel de Rendimiento Territorial")

if df_master.empty:
    st.info("No hay datos disponibles para la búsqueda actual.")
else:
    if sel_persona != "Todos":
        st.subheader(f"Radiografía de: {sel_persona}")
        
        datos_perfil = df_master.iloc[0]
        # Limpiar el distrito aquí para que no se vea el ".0"
        distrito_limpio = str(datos_perfil.get('Distrito', 'N/A'))
        if distrito_limpio.replace('.', '', 1).isdigit():
            distrito_limpio = str(int(float(distrito_limpio)))
            
        st.caption(f"📍 **Estado:** {datos_perfil.get('Estado', 'N/A')} | **Distrito:** {distrito_limpio}")
        
        kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
        
        kpi1.metric("META Total", f"{datos_perfil.get('META', 0):,.0f}")
        kpi2.metric("Convencidos", f"{datos_perfil.get('CONVENCIDOS', 0):,.0f}")
        kpi3.metric("% Avance", f"{datos_perfil.get('% AVANCE', 0):.1f} %")
        kpi4.metric("Avance por Día", f"{datos_perfil.get('AVANCE POR DÍA', 0):.1f}")
        
        tendencia_actual = str(datos_perfil.get('TENDENCIA SEMANA 3', 'Sin Registro'))
        kpi5.metric("Tendencia (Sem. 3)", tendencia_actual)
        
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
                st.caption("- **Escala 1 a 4**: 4 es Destacado, 1 Requiere Mejorar.")
                st.caption("- Si sus **Convencidos** son bajos pero su **Persuasión** es alta, el problema es su zona geográfica, no su talento.")
                st.caption("- Si su **Tendencia** es decreciente pero sus rúbricas son buenas, verifica si no se le agotaron los sectores fáciles.")
        else:
            st.info("Aún no hay evaluaciones cualitativas registradas en Firebase para este perfil.")

    else:
        st.subheader("Diagnóstico Estructural de la Región")
        
        k_col1, k_col2, k_col3, k_col4 = st.columns(4)
        k_col1.metric("Elementos Activos", f"{len(df_master)}")
        k_col2.metric("Total Convencidos (Región)", f"{df_master.get('CONVENCIDOS', pd.Series([0])).sum():,.0f}")
        k_col3.metric("Meta Global (Región)", f"{df_master.get('META', pd.Series([0])).sum():,.0f}")
        meta_total = df_master.get('META', pd.Series([1])).sum()
        progreso = (df_master.get('CONVENCIDOS', pd.Series([0])).sum() / meta_total * 100) if meta_total > 0 else 0
        k_col4.metric("Progreso Global", f"{progreso:.1f} %")
        
        st.divider()
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🎯 Síndrome de la Meta Inalcanzable")
            st.write("Relación entre Metas altas y el Porcentaje de Cumplimiento.")
            if 'META' in df_master.columns and '% AVANCE' in df_master.columns:
                st.scatter_chart(df_master, x='META', y='% AVANCE', size='CONVENCIDOS', color='#880615')
                
        with c2:
            st.markdown("### 📉 Índice de Volatilidad (Tendencia Semanal)")
            st.write("Comparativa de la Semana 1 contra la Semana 3.")
            if 'Total semana 1' in df_master.columns and 'Total semanal 3' in df_master.columns and 'TENDENCIA SEMANA 3' in df_master.columns:
                st.scatter_chart(df_master, x='Total semana 1', y='Total semanal 3', color='TENDENCIA SEMANA 3')

        st.divider()
        
        st.markdown("### 🏆 Ranking General de Convencidos")
        st.write("Lista de todo el equipo ordenado por número de convencidos de mayor a menor.")
        if 'CONVENCIDOS' in df_master.columns:
            columnas_tabla = ['Nombres', 'Distrito', 'META', 'CONVENCIDOS', '% AVANCE', 'TENDENCIA SEMANA 3']
            columnas_existentes = [col for col in columnas_tabla if col in df_master.columns]
            
            df_ranking = df_master[columnas_existentes].sort_values(by='CONVENCIDOS', ascending=False)
            
            # Limpiar también la columna de la tabla para que no muestre 1.0, 2.0...
            if 'Distrito' in df_ranking.columns:
                df_ranking['Distrito'] = df_ranking['Distrito'].apply(lambda x: str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x))
                
            st.dataframe(df_ranking, use_container_width=True, hide_index=True)