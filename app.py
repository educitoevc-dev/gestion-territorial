import streamlit as st
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
import json
import re

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y CONEXIÓN
# ==========================================
st.set_page_config(layout="wide", page_title="Dashboard Territorial - MORENA", page_icon="🇲🇽")

if not firebase_admin._apps:
    try:
        key_dict = json.loads(st.secrets["FIREBASE_KEY"])
        cred = credentials.Certificate(key_dict)
    except Exception:
        cred = credentials.Certificate('firebase_cred.json')
        
    firebase_admin.initialize_app(cred)

db = firestore.client()

URL_EXCEL_CUANTITATIVO = "https://docs.google.com/spreadsheets/d/1HdameC4EE1_drytVlQKxtu-1q78PE0HRx0QNqeSXqLo/export?format=csv"

# Nombres de las etiquetas limpias para las gráficas
CLEAN_DIAS_S36 = ['31-ago', '01-sep', '02-sep', '03-sep', '04-sep', '05-sep', '06-sep']
CLEAN_DIAS_S37 = ['07-sep', '08-sep', '09-sep', '10-sep', '11-sep', '12-sep', '13-sep']
CLEAN_DIAS_S38 = ['14-sep', '15-sep', '16-sep', '17-sep', '18-sep', '19-sep', '20-sep']

# ==========================================
# 2. MOTOR DE EXTRACCIÓN DE DATOS (ETL)
# ==========================================
@st.cache_data(ttl=300)
def cargar_datos_cuantitativos():
    try:
        df = pd.read_csv(URL_EXCEL_CUANTITATIVO)
        
        if 'Estructura' not in df.columns:
            for i, row in df.head(15).iterrows():
                row_str = [str(x) for x in row.values]
                if 'Estructura' in row_str or 'Nombres' in row_str:
                    df.columns = row.values
                    df = df.iloc[i+1:].reset_index(drop=True)
                    break
                    
        df.columns = df.columns.astype(str).str.replace('\n', ' ', regex=False).str.replace(r'\s+', ' ', regex=True).str.strip()
        
        if 'Distrito Federal' in df.columns:
            df = df.rename(columns={'Distrito Federal': 'Distrito'})

        if '% AVANCE' in df.columns:
            df['% AVANCE'] = df['% AVANCE'].astype(str).str.replace('%', '').str.replace(',', '').str.strip()
            df['% AVANCE'] = pd.to_numeric(df['% AVANCE'], errors='coerce').fillna(0)

        # Extracción dinámica de días para evitar errores por cambios de formato de fecha en Excel
        cols = df.columns.tolist()
        dias_s38, dias_s37, dias_s36 = [], [], []
        
        try: dias_s38 = cols[cols.index('TENDENCIA SEPTIEMBRE')+1 : cols.index('TOTAL S38')]
        except: pass
        try: dias_s37 = cols[cols.index('TENDENCIA S38')+1 : cols.index('TOTAL S37')]
        except: pass
        try: dias_s36 = cols[cols.index('TENDENCIA S372')+1 : cols.index('TOTAL S36')]
        except: pass

        dias_dinamicos = dias_s36 + dias_s37 + dias_s38

        # --- MODIFICACIÓN 1: Se añadieron 'METAS' y 'META GLOBAL' a la lista de columnas numéricas ---
        cols_numericas = ['META', 'METAS', 'META GLOBAL', 'CONVENCIDOS A LA FECHA', 'CONVENCIDOS', 'AVANCE POR DÍA', 'SEPTIEMBRE 01-20', 'AGOSTO 17 - 31',
                          'Total semana 1', 'Total semanal 2', 'Total semanal 3', 
                          'TOTAL S36', 'TOTAL S37', 'TOTAL S38',
                          'PROMEDIO S36', 'PROMEDIO S372', 'PROMEDIO S38'] + dias_dinamicos
        
        for col in cols_numericas:
            if col in df.columns:
                if df[col].dtype == object:
                    # --- MODIFICACIÓN 2: Expresión regular para eliminar comas, espacios y símbolos ---
                    df[col] = df[col].astype(str).str.replace(r'[$,\s]', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
                
        text_cols = ['TENDENCIA SEMANA 3', 'TENDENCIA S38', 'TENDENCIA S372', 'TENDENCIA S36', 
                     'ESTADO S36', 'ESTADO S372', 'ESTADO S38']
        for col_t in text_cols:
            if col_t in df.columns:
                df[col_t] = df[col_t].fillna('Sin Registro').astype(str).str.strip()
                if 'ESTADO' in col_t:
                    df[col_t] = df[col_t].str.replace('●', '').str.strip()
            
        return df, dias_s36, dias_s37, dias_s38
    except Exception as e:
        st.error(f"Error al cargar el Excel Cuantitativo: {e}")
        return pd.DataFrame(), [], [], []

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
            
            dist_raw = str(d.get('distrito', ''))
            match = re.search(r'_(\d+)$', dist_raw)
            if match:
                dist_limpio = match.group(1)
            else:
                dist_limpio = dist_raw.replace('Distrito', '').replace('distrito', '').strip()
                if dist_limpio.replace('.','',1).isdigit():
                    dist_limpio = str(int(float(dist_limpio)))

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

# Carga paralela y mapeo de variables
df_cuant, dias_raw_s36, dias_raw_s37, dias_raw_s38 = cargar_datos_cuantitativos()
df_cual_cots = cargar_datos_cualitativos_cots()
df_cual_dist = cargar_datos_cualitativos_distritales()

dias_raw_totales = dias_raw_s36 + dias_raw_s37 + dias_raw_s38
dias_clean_totales = CLEAN_DIAS_S36[:len(dias_raw_s36)] + CLEAN_DIAS_S37[:len(dias_raw_s37)] + CLEAN_DIAS_S38[:len(dias_raw_s38)]

if not df_cuant.empty and 'Nombres' in df_cuant.columns:
    df_cuant['Nombres'] = df_cuant['Nombres'].astype(str).str.upper().str.strip()

if not df_cual_cots.empty and 'Nombres' in df_cual_cots.columns:
    df_cual_cots['Nombres'] = df_cual_cots['Nombres'].astype(str).str.upper().str.strip()

if not df_cuant.empty and not df_cual_cots.empty and 'Nombres' in df_cuant.columns and 'Nombres' in df_cual_cots.columns:
    df_master = pd.merge(df_cuant, df_cual_cots, on='Nombres', how='left').fillna(0)
else:
    df_master = df_cuant.copy()

# --- MODIFICACIÓN 3: Búsqueda flexible del nombre de la columna Meta ---
if 'META' in df_master.columns: 
    col_meta = 'META'
elif 'METAS' in df_master.columns: 
    col_meta = 'METAS'
elif 'META GLOBAL' in df_master.columns: 
    col_meta = 'META GLOBAL'
else: 
    col_meta = None

if 'CONVENCIDOS A LA FECHA' in df_master.columns: col_conv = 'CONVENCIDOS A LA FECHA'
elif 'SEPTIEMBRE 01-20' in df_master.columns: col_conv = 'SEPTIEMBRE 01-20'
elif 'CONVENCIDOS' in df_master.columns: col_conv = 'CONVENCIDOS'
else: col_conv = None

col_s1 = 'TOTAL S36' if 'TOTAL S36' in df_master.columns else ('Total semana 1' if 'Total semana 1' in df_master.columns else None)
col_s2 = 'TOTAL S37' if 'TOTAL S37' in df_master.columns else ('Total semanal 2' if 'Total semanal 2' in df_master.columns else None)
col_s3 = 'TOTAL S38' if 'TOTAL S38' in df_master.columns else ('Total semanal 3' if 'Total semanal 3' in df_master.columns else None)

if 'TENDENCIA S38' in df_master.columns: col_tendencia = 'TENDENCIA S38'
elif 'TENDENCIA S372' in df_master.columns: col_tendencia = 'TENDENCIA S372'
elif 'TENDENCIA SEMANA 3' in df_master.columns: col_tendencia = 'TENDENCIA SEMANA 3'
else: col_tendencia = None

if not df_master.empty and 'Estado' in df_master.columns:
    df_master = df_master[~df_master['Estado'].astype(str).str.strip().isin(['0', '0.0', 'nan', 'NaN', ''])]

if not df_master.empty and 'Estructura' in df_master.columns:
    df_master['Estructura'] = df_master['Estructura'].fillna('Sin Asignar').replace({'nan': 'Sin Asignar', 'NaN': 'Sin Asignar', '': 'Sin Asignar'})

if 'Distrito' in df_master.columns:
    df_master['Distrito'] = df_master['Distrito'].apply(lambda x: str(int(float(x))) if str(x).replace('.','',1).isdigit() else str(x))

def get_color_estado(estado_texto):
    txt = str(estado_texto).upper()
    if "EXCELENTE" in txt: return "#065f46", "#d1fae5" 
    if "ALTO" in txt: return "#1e40af", "#dbeafe" 
    if "MEDIO" in txt: return "#b45309", "#fef3c7" 
    if "BAJO" in txt: return "#c2410c", "#ffedd5" 
    if "CRITICO" in txt or "CRÍTICO" in txt: return "#991b1b", "#fee2e2" 
    return "#4b5563", "#f3f4f6" 

def get_color_tendencia(tendencia_texto):
    txt = str(tendencia_texto).upper()
    if "CRECIENTE" in txt: return "#065f46", "#d1fae5"
    if "DECRECIENTE" in txt: return "#991b1b", "#fee2e2"
    if "ESTABLE" in txt: return "#1e40af", "#dbeafe"
    return "#4b5563", "#f3f4f6"

# ==========================================
# 3. FILTROS EN CASCADA CON ESTILO MORENA
# ==========================================
st.sidebar.markdown(
    """
    <div style="text-align: center; padding: 10px 0 20px 0;">
        <h1 style="color: #880615; font-size: 2.2rem; font-weight: 800; margin: 0; line-height: 1;">morena</h1>
        <p style="color: #6b7280; font-size: 0.9rem; margin-top: 4px; font-weight: 500;">La esperanza de México</p>
    </div>
    """, 
    unsafe_allow_html=True
)

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
        df_master['Filtro_Nombre_Visual'] = df_master['Nombres'].astype(str).str.upper().str.strip() + " (D" + df_master['Distrito'].astype(str) + ")"
        nombres_disponibles = ["Todos"] + sorted(df_master['Filtro_Nombre_Visual'].dropna().unique().tolist())
        sel_persona_visual = st.sidebar.selectbox("Busca el nombre de un perfil:", nombres_disponibles)
        
        if sel_persona_visual != "Todos":
            df_master = df_master[df_master['Filtro_Nombre_Visual'] == sel_persona_visual]
            sel_persona = sel_persona_visual
        else:
            sel_persona = "Todos"
    elif 'Nombres' not in df_master.columns:
        st.sidebar.warning("Columna 'Nombres' no detectada en el Excel.")
    else:
        st.sidebar.info("Selecciona un Estado arriba para habilitar la búsqueda individual.")

OPCIONES_SEMANALES = {
    "Semana 38 (Actual)": {"tot": "TOTAL S38", "prom": "PROMEDIO S38", "est": "ESTADO S38", "tend": "TENDENCIA S38", "raw_dias": dias_raw_s38, "clean_dias": CLEAN_DIAS_S38},
    "Semana 37": {"tot": "TOTAL S37", "prom": "PROMEDIO S372", "est": "ESTADO S372", "tend": "TENDENCIA S372", "raw_dias": dias_raw_s37, "clean_dias": CLEAN_DIAS_S37},
    "Semana 36": {"tot": "TOTAL S36", "prom": "PROMEDIO S36", "est": "ESTADO S36", "tend": "TENDENCIA S36", "raw_dias": dias_raw_s36, "clean_dias": CLEAN_DIAS_S36}
}

# ==========================================
# 4. FRONTEND CON PESTAÑAS (TABS)
# ==========================================
st.title("Panel de Rendimiento Territorial")

if df_master.empty:
    st.info("No hay datos disponibles para la búsqueda actual.")
else:
    tab_cots, tab_distritales = st.tabs(["👥 Operación por COT", "👑 Análisis de Enlaces Distritales"])

    # ----------------------------------------------------
    # TAB 1: RENDIMIENTO DE COTs
    # ----------------------------------------------------
    with tab_cots:
        if sel_persona != "Todos":
            st.subheader(f"Radiografía de: {sel_persona}")
            datos_perfil = df_master.iloc[0]
            distrito_limpio = str(datos_perfil.get('Distrito', 'N/A'))
            st.caption(f"📍 **Estado:** {datos_perfil.get('Estado', 'N/A')} | **Distrito:** {distrito_limpio}")
            
            telefono_raw = str(datos_perfil.get('Telefono', ''))
            telefono_limpio = re.sub(r'\D', '', telefono_raw)
            
            if len(telefono_limpio) >= 10:
                if not telefono_limpio.startswith('52'):
                    telefono_limpio = '52' + telefono_limpio
                url_whatsapp = f"https://wa.me/{telefono_limpio}"
                st.markdown(f'<a href="{url_whatsapp}" target="_blank"><button style="background-color:#25D366; color:white; padding:8px 16px; border:none; border-radius:6px; font-weight:bold; cursor:pointer; margin-bottom:15px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">💬 Contactar por WhatsApp ({telefono_raw})</button></a>', unsafe_allow_html=True)
            else:
                st.info("ℹ️ Teléfono no disponible para enlace directo de WhatsApp.")
                
            st.divider()

            # Cálculo de promedio histórico general (Considera todos los días de S36, S37 y S38)
            val_dias_historicos = [datos_perfil.get(raw, 0) for raw in dias_raw_totales if raw in df_master.columns]
            prom_historico_general = sum(val_dias_historicos) / len(val_dias_historicos) if len(val_dias_historicos) > 0 else 0

            kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
            meta_val = datos_perfil.get(col_meta, 0) if col_meta else 0
            conv_val = datos_perfil.get(col_conv, 0) if col_conv else 0
            
            kpi1.metric("META Total", f"{meta_val:,.0f}")
            kpi2.metric("Convencidos", f"{conv_val:,.0f}")
            kpi3.metric("% Avance", f"{datos_perfil.get('% AVANCE', 0):.1f} %")
            kpi4.metric("Avance por Día (Promedio Histórico)", f"{prom_historico_general:.1f}")
            kpi5.metric("Tendencia Actual", str(datos_perfil.get(col_tendencia, 'Sin Registro')))
            
            st.divider()

            st.markdown("### 📅 Analizador de Desempeño por Semana")
            st.caption("Selecciona una fecha para visualizar el rendimiento y el nivel de estado correspondiente a esa semana.")
            
            semanas_validas = {k: v for k, v in OPCIONES_SEMANALES.items() if v["est"] in df_master.columns and v["tend"] in df_master.columns}
            
            if semanas_validas:
                sel_sem_indiv = st.radio("Selecciona la semana a evaluar:", list(semanas_validas.keys()), horizontal=True)
                
                cfg_sem = semanas_validas[sel_sem_indiv]
                val_prom = datos_perfil.get(cfg_sem["prom"], 0)
                val_est = str(datos_perfil.get(cfg_sem["est"], 'Sin Registro')).strip()
                val_tend = str(datos_perfil.get(cfg_sem["tend"], 'Sin Registro')).strip()
                
                cE_text, cE_bg = get_color_estado(val_est)
                cT_text, cT_bg = get_color_tendencia(val_tend)
                
                met1, met2, met3 = st.columns(3)
                met1.metric(f"Promedio Diario ({sel_sem_indiv})", f"{val_prom:.1f}")
                
                met2.markdown(f"**Estado de Desempeño:**")
                if val_est != 'Sin Registro':
                    met2.markdown(f'<div style="background-color:{cE_bg}; color:{cE_text}; padding:8px 12px; border-radius:6px; font-weight:bold; display:inline-block; border: 1px solid {cE_text};">{val_est.upper()}</div>', unsafe_allow_html=True)
                else:
                    met2.info("Sin Registro")
                    
                met3.markdown(f"**Tendencia Operativa:**")
                if val_tend != 'Sin Registro':
                    met3.markdown(f'<div style="background-color:{cT_bg}; color:{cT_text}; padding:8px 12px; border-radius:6px; font-weight:bold; display:inline-block; border: 1px solid {cT_text};">{val_tend.upper()}</div>', unsafe_allow_html=True)
                else:
                    met3.info("Sin Registro")
                    
                st.divider()
            
            # ---> GRÁFICA HISTÓRICA COMPLETA DE LÍNEAS (Las 3 semanas corridas) <---
            st.markdown("### 📈 Evolución Diaria de Resultados (S36, S37 y S38)")
            st.caption("Gráfica continua que muestra el esfuerzo de captura día por día durante todo el mes.")
            
            valores_dias = []
            nombres_dias = []
            
            for raw, clean in zip(dias_raw_totales, dias_clean_totales):
                if raw in df_master.columns:
                    nombres_dias.append(clean)
                    valores_dias.append(datos_perfil.get(raw, 0))

            if len(nombres_dias) > 0:
                col_tl_chart, col_tl_info = st.columns([2, 1])
                df_tiempo = pd.DataFrame({
                    'Día': nombres_dias,
                    'Registros Validados': valores_dias
                }).set_index('Día')
                
                with col_tl_chart:
                    st.line_chart(df_tiempo, color='#880615')
                
                with col_tl_info:
                    st.markdown("**Resumen de Actividad**")
                    total_periodo = sum(valores_dias)
                    pico_maximo = max(valores_dias) if valores_dias else 0
                    st.success(f"**{total_periodo:,.0f}** registros históricos validados.")
                    st.info(f"Pico de esfuerzo: **{pico_maximo:,.0f}** registros en un solo día.")
            else:
                st.info("No se detectaron los días en el reporte para generar la gráfica.")

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
            
            sum_conv = df_master[col_conv].sum() if col_conv and col_conv in df_master.columns else 0
            sum_meta = df_master[col_meta].sum() if col_meta and col_meta in df_master.columns else 0
            
            k_col2.metric("Total Convencidos", f"{sum_conv:,.0f}")
            k_col3.metric("Meta Global", f"{sum_meta:,.0f}")
            progreso = (sum_conv / sum_meta * 100) if sum_meta > 0 else 0
            k_col4.metric("Progreso Global", f"{progreso:.1f} %")
            
            st.divider()
            
            st.markdown("### Estatus Oficial")
            st.caption("Selecciona la fecha para visualizar el nivel de desempeño global y la tendencia de la fuerza de trabajo.")
            
            semanas_validas_glob = {k: v for k, v in OPCIONES_SEMANALES.items() if v["est"] in df_master.columns and v["tend"] in df_master.columns}
            
            if semanas_validas_glob:
                sel_sem_glob = st.radio("Filtro Semanal de Salud Operativa:", list(semanas_validas_glob.keys()), horizontal=True)
                cfg_glob = semanas_validas_glob[sel_sem_glob]
                
                cg1, cg2 = st.columns(2)
                with cg1:
                    st.markdown(f"**Distribución de Desempeño ({sel_sem_glob})**")
                    df_salud_est = df_master[cfg_glob["est"]].value_counts().reset_index()
                    df_salud_est.columns = ['Estado de Desempeño', 'Cantidad de COTs']
                    df_salud_est = df_salud_est[df_salud_est['Estado de Desempeño'] != 'Sin Registro']
                    st.bar_chart(df_salud_est.set_index('Estado de Desempeño'), color='#1e40af')
                    
                with cg2:
                    st.markdown(f"**Tendencia Dominante ({sel_sem_glob})**")
                    df_salud_tend = df_master[cfg_glob["tend"]].value_counts().reset_index()
                    df_salud_tend.columns = ['Tendencia', 'Cantidad de COTs']
                    df_salud_tend = df_salud_tend[df_salud_tend['Tendencia'] != 'Sin Registro']
                    st.bar_chart(df_salud_tend.set_index('Tendencia'), color='#880615')
            else:
                st.warning("No se encontraron las columnas de Estado y Tendencia para mostrar la salud de la región.")

            st.divider()
            
            # ---> GRÁFICA GLOBAL HISTÓRICA COMPLETA DE LÍNEAS (Las 3 semanas corridas) <---
            st.markdown("### 📈 Tendencia de Rendimiento Global (S36, S37 y S38)")
            st.caption("Ritmo de captura consolidado a lo largo de todo el mes, día por día.")
            
            dias_presentes_global = []
            nombres_dias_global = []
            valores_globales = []
            
            for raw, clean in zip(dias_raw_totales, dias_clean_totales):
                if raw in df_master.columns:
                    dias_presentes_global.append(raw)
                    nombres_dias_global.append(clean)
                    valores_globales.append(df_master[raw].sum())
                    
            if len(dias_presentes_global) > 0:
                df_tendencia_global = pd.DataFrame({
                    'Día': nombres_dias_global,
                    'Registros Validados': valores_globales
                }).set_index('Día')
                st.line_chart(df_tendencia_global, color='#880615')
            else:
                st.info("Faltan las columnas diarias en el Excel para graficar la evolución.")

            st.divider()
            
            st.markdown("### 🏆 Ranking General de Convencidos")
            col_est_default = 'ESTADO S38' if 'ESTADO S38' in df_master.columns else None
            if col_conv in df_master.columns:
                col_tab = ['Filtro_Nombre_Visual', 'Distrito', col_meta, col_conv]
                if col_est_default: col_tab.append(col_est_default)
                if col_tendencia: col_tab.append(col_tendencia)
                
                col_ex = [col for col in col_tab if col and col in df_master.columns]
                
                df_ranking_view = df_master[col_ex].sort_values(by=col_conv, ascending=False).reset_index(drop=True)
                st.dataframe(df_ranking_view, use_container_width=True, hide_index=True)
            else:
                st.info("No se encontró la columna de convencidos.")

    # ----------------------------------------------------
    # TAB 2: RENDIMIENTO Y EVALUACIÓN DE DISTRITALES
    # ----------------------------------------------------
    with tab_distritales:
        st.subheader("Análisis de Liderazgo Distrital")
        st.write("Cruce de la Evaluación Institucional (Cualitativa) vs el Avance Real de su Distrito (Cuantitativo).")
        
        if sel_persona != "Todos":
            st.info("⚠️ Para ver el análisis de Enlaces Distritales, debes quitar el filtro de búsqueda individual de COT en el menú lateral.")
        else:
            col_tend_s372 = 'TENDENCIA S372' if 'TENDENCIA S372' in df_master.columns else col_tendencia
            
            if col_tend_s372:
                def moda_tendencia(serie):
                    s = serie.dropna()
                    s = s[s != 'Sin Registro']
                    if s.empty: return 'Sin Registro'
                    return s.mode().iloc[0] if not s.mode().empty else s.iloc[0]

                agg_dict = {
                    'Nombres': 'count',
                    col_tend_s372: lambda x: moda_tendencia(x)
                }
                if col_meta: agg_dict[col_meta] = 'sum'
                if col_conv: agg_dict[col_conv] = 'sum'
                
                df_distrito_cuant = df_master.groupby('Distrito').agg(agg_dict).reset_index()
                df_distrito_cuant = df_distrito_cuant.rename(columns={'Nombres': 'COTs_Activos', col_tend_s372: 'Tendencia Predominante'})
                
                meta_col_name = col_meta if col_meta else 'COTs_Activos'
                conv_col_name = col_conv if col_conv else 'COTs_Activos'
                
                df_distrito_cuant['% Avance Distrito'] = df_distrito_cuant.apply(
                    lambda row: (row[conv_col_name] / row[meta_col_name] * 100) if meta_col_name in row and row[meta_col_name] > 0 else 0, axis=1
                )
                
                st.markdown("### 🏅 Ranking Operativo por Distrito (Meta vs Convencidos)")
                st.caption("Compara el volumen total de captura consolidado frente a la meta asignada a nivel distrital.")
                if meta_col_name in df_distrito_cuant.columns and conv_col_name in df_distrito_cuant.columns:
                    df_ranking_dist = df_distrito_cuant[['Distrito', meta_col_name, conv_col_name]].copy()
                    df_ranking_dist['Distrito'] = "Distrito " + df_ranking_dist['Distrito'].astype(str)
                    df_ranking_dist = df_ranking_dist.set_index('Distrito').sort_values(by=conv_col_name, ascending=False)
                    st.bar_chart(df_ranking_dist, color=["#d3d3d3", "#880615"])
                else:
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
                    
                    df_analisis['Etiqueta Distrital'] = df_analisis['Enlace Distrital'] + " (D" + df_analisis['Distrito'].astype(str) + ")"
                    enlaces_disponibles = sorted(df_analisis['Etiqueta Distrital'].unique().tolist())
                    
                    sel_enlace_etiqueta = st.selectbox("Selecciona un Enlace Distrital para ver su radiografía:", enlaces_disponibles)
                    
                    datos_enlace = df_analisis[df_analisis['Etiqueta Distrital'] == sel_enlace_etiqueta].iloc[0]
                    
                    kcol1, kcol2, kcol3, kcol4 = st.columns(4)
                    kcol1.metric("Distrito a Cargo", f"D - {datos_enlace['Distrito']}")
                    kcol2.metric("Evaluación Global (Web)", f"{datos_enlace['Evaluacion Global']:.2f} / 4.0")
                    kcol3.metric("Avance Operativo (COTs)", f"{datos_enlace['% Avance Distrito']:.1f} %")
                    
                    val_t_dist = str(datos_enlace['Tendencia Predominante'])
                    cT_text_d, cT_bg_d = get_color_tendencia(val_t_dist)
                    
                    kcol4.markdown("**Tendencia Oficial del Distrito**")
                    if val_t_dist != 'Sin Registro':
                        kcol4.markdown(f'<div style="background-color:{cT_bg_d}; color:{cT_text_d}; padding:4px 8px; border-radius:4px; font-weight:bold; display:inline-block; border: 1px solid {cT_text_d};">{val_t_dist.upper()}</div>', unsafe_allow_html=True)
                    else:
                        kcol4.info("Sin Registro")
                    
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
                    st.markdown("### 🏆 Ranking Analítico de Enlaces Distritales")
                    st.caption("Incluye el promedio general de sus evaluaciones en la web y la tendencia oficial de su distrito.")
                    
                    columnas_tabla_dist = ['Enlace Distrital', 'Distrito', 'COTs_Activos', conv_col_name, '% Avance Distrito', 'Tendencia Predominante', 'Evaluacion Global']
                    
                    df_final_view = df_analisis[columnas_tabla_dist].sort_values(by='Evaluacion Global', ascending=False).reset_index(drop=True)
                    
                    def color_semaforo_dist(val):
                        if isinstance(val, (int, float)):
                            if val >= 3.0: return 'background-color: #d1fae5; color: #065f46;'
                            elif val >= 2.0: return 'background-color: #fef3c7; color: #92400e;'
                            else: return 'background-color: #fee2e2; color: #991b1b;'
                        return ''

                    st.dataframe(
                        df_final_view.style.map(color_semaforo_dist, subset=['Evaluacion Global']), 
                        use_container_width=True, 
                        hide_index=True
                    )
            else:
                st.error("Faltan las columnas de tendencia en el Excel para mostrar este análisis.")