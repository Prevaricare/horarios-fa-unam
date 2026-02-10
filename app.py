import streamlit as st
import requests
import pandas as pd
from bs4 import BeautifulSoup
import re

# ==========================================
# 1. CONFIGURACIÓN Y CONSTANTES
# ==========================================

URL_BASE = "https://escolares.arq.unam.mx:8086/horario/arquitectura/plan17"
CICLO_ACTUAL = "20262"  # Ajustar según la fecha

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"{URL_BASE}/index.php"
}

# ==========================================
# 2. CATÁLOGOS DE DATOS (Diccionarios)
# ==========================================

CATALOGOS = {
    "TALLERES": {
        "- TODOS -": 0,  # <--- AGREGADO NUEVO
        "ANTONIO GARCÍA GAYOU": 3, "CARLOS LAZO BARREIRO": 8, "CARLOS LEDUC MONTAÑO": 11,
        "HANNES MEYER": 13, "JORGE GONZÁLEZ REYNA": 5, "JOSÉ VILLAGRÁN GARCÍA": 4,
        "JUAN O GORMAN": 16, "LUIS BARRAGÁN": 7, "MAX CETTO": 15, "TALLER UNO": 10,
        "DOMINGO GARCÍA RAMOS": 2, "EHECATL 21": 14, "FEDERICO MARISCAL Y PIÑA": 6,
        "JOSÉ REVUELTAS": 17, "RAMÓN MARCOS NORIEGA": 9, "TALLER TRES": 12
    },
    "AREAS_OPTATIVAS": {
        "- TODAS LAS ÁREAS -": 0, # <--- AGREGADO NUEVO
        "Extensión Universitaria": 40, "Proyecto": 41, "Tecnología": 42,
        "Teoría Historia": 43, "Urbano Ambiental": 44
    },
    "LIPS": {
        "- TODAS LAS LÍNEAS -": 0, # <--- AGREGADO NUEVO
        "CRITICA Y REFLEXION": 4110, "CULTURA Y CONSER.DEL PAT": 4111,
        "DISEÑO DEL HABIT.Y MED.AM": 4112, "ESTRUCT.Y TECNOL.CONSTRU": 4113,
        "EXPRESIVIDAD ARQUITECTONI": 4114, "GERENCIA DE PROYECTOS": 4115,
        "GEST.EN LA PROD.DEL HABIT": 4116, "PROCESO PROYECTUAL": 4117
    },
    # Nota: Para Asignaturas y Profesores, lo ideal es scrapear la lista completa al inicio.
    # Aquí pongo algunos ejemplos basados en tu input para que funcione el demo.
    "ASIGNATURAS_COMUNES": {
        "1135 - ARQUEOLOGIA DEL HABITAT I": 1135,
        "1137 - GEOMETRIA I": 1137,
        "1140 - TALLER INTEGRAL I": 1140,
        "1555 - TALLER INTEGRAL III": 1555,
        "1238 - SISTEMAS AMBIENTALES II": 1238
    },
    # Nota: El value del profesor debe ser exactamente el string largo (RFC|NOMBRE)
    "PROFESORES_EJEMPLO": {
        "ABUD RAMIREZ RAMON": "AURR6106285A0|ABUD RAMIREZ RAMON, MTRO.",
        "AGUADO VILLARCE ARTURO": "AUVA530411PQ0|AGUADO VILLARCE ARTURO, ARQ.",
        "CALDERON KLUCZYNSKI JOSE": "CAKJ6204196I5|CALDERON KLUCZYNSKI JOSE, MTRO.",
        "MIRANDA CRUZ JOSE": "MICJ510803UV6|MIRANDA CRUZ JOSE, ARQ."
    }
}

# ==========================================
# 3. FUNCIONES DE CONEXIÓN
# ==========================================

def consultar_api(endpoint, payload_extra):
    """Función genérica para consultar cualquier PHP del sitio."""
    url = f"{URL_BASE}/hor/{endpoint}"
    
    payload = {
        "estu": 0,
        "qsemac": CICLO_ACTUAL
    }
    payload.update(payload_extra)

    try:
        response = requests.post(url, headers=HEADERS, data=payload, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None
# ==========================================
# AGREGAR ESTO EN LA SECCIÓN 3
# ==========================================

@st.cache_data(show_spinner=False) # Guardamos en caché para no cargarla cada vez
def obtener_catalogo_profesores():
    """
    Descarga la lista completa de profesores directamente desde el sitio web.
    Busca el elemento <select id="idprof"> mostrado en tu imagen.
    """
    url = f"{URL_BASE}/index.php" # Generalmente la lista está en el inicio
    
    try:
        # Hacemos una petición GET normal para ver el formulario
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "lxml")
        
        # Buscamos el dropdown por su ID (visto en tu imagen)
        select_profes = soup.find("select", {"id": "idprof"})
        
        if not select_profes:
            return {} # Si no lo encuentra, regresa vacío

        profesores = {}
        # Iteramos sobre cada <option> dentro del select
        for option in select_profes.find_all("option"):
            valor = option.get("value")
            texto = option.get_text(strip=True)
            
            # Filtramos la opción por defecto "--PROFESOR--" y valores vacíos
            if valor and "PROFESOR" not in valor and len(valor) > 2:
                profesores[texto] = valor
                
        return profesores

    except Exception as e:
        st.error(f"No se pudo cargar la lista de profesores: {e}")
        return {}
# ==========================================
# 4. PARSER INTELIGENTE Y VISUALIZADOR
# ==========================================

def limpiar_texto(texto):
    if not texto: return ""
    return texto.strip().replace("+ ", "").replace("\n", " ").replace("\r", "")

def extraer_horario(celda_html):
    etiquetas_b = celda_html.find_all("b")
    if not etiquetas_b:
        return celda_html.get_text(strip=True)
    return " / ".join([b.get_text(strip=True) for b in etiquetas_b])

def interpretar_horario(texto_horario):
    """
    Parser robusto para horarios complejos.
    Corrige el error de 'comerse' las comas y juntar días.
    """
    if not texto_horario: return []
    
    # 1. Normalización: Minúsculas
    texto = texto_horario.lower()
    
    # 2. LIMPIEZA CRÍTICA: Reemplazar separadores por ESPACIOS
    # El error anterior era reemplazarlos por "" (nada), lo que pegaba "14:00,MI" -> "14:00mi"
    for char in [",", ";", ".", " y ", " e ", " - "]: 
        texto = texto.replace(char, " ")
        
    # 3. Quitar los dos puntos SOLO de las horas (10:00 -> 1000)
    texto = texto.replace(":", "")
    
    # Mapa de días
    mapa_dias = {
        "lu": "Lunes", "ma": "Martes", "mi": "Miércoles", 
        "ju": "Jueves", "vi": "Viernes", "sa": "Sábado"
    }
    
    bloques = []
    tokens = texto.split() # Dividir por espacios
    
    dias_activos = [] # Memoria de qué días estamos leyendo
    
    for token in tokens:
        token = token.strip()
        if not token: continue

        # A) ¿Es un día? (ej: "lu", "ma")
        # Tomamos las primeras 2 letras por si viene "lunes" completo
        token_clean = token[:2] 
        if token_clean in mapa_dias:
            # Encontramos un nuevo día, actualizamos el "puntero"
            dias_activos = [mapa_dias[token_clean]]
            
        # B) ¿Es un horario? (ej: "0900-1400" o "9-14")
        elif "-" in token:
            horas = re.findall(r'(\d{1,4})-(\d{1,4})', token)
            if horas and dias_activos:
                inicio_raw, fin_raw = horas[0]
                
                # Función auxiliar para convertir hora texto a numero decimal
                def normalizar_hora(h_str):
                    val = int(h_str)
                    # Caso formato militar 1330 -> 13.5
                    if val > 24: 
                        horas = val // 100
                        minutos = val % 100
                        return horas + (0.5 if minutos >= 30 else 0)
                    # Caso formato simple 13 -> 13.0
                    return float(val) 
                
                inicio = normalizar_hora(inicio_raw)
                fin = normalizar_hora(fin_raw)
                
                # Agregar este horario a TODOS los días activos (ej: MI 7-12 y 13-15)
                for dia in dias_activos:
                    bloques.append({
                        "dia": dia,
                        "inicio": int(inicio), # Redondeamos a entero para el grid
                        "fin": int(fin) + (1 if fin % 1 > 0 else 0) # Asegurar que cubra la hora final
                    })
    
    return bloques

def generar_paleta_colores(n):
    """Genera una lista de colores pastel bonitos"""
    colores_base = [
        "#FFB3BA", "#FFDFBA", "#FFFFBA", "#BAFFC9", "#BAE1FF", # Pastel Red, Orange, Yellow, Green, Blue
        "#E6B3FF", "#F0E68C", "#98FB98", "#DDA0DD", "#87CEFA"  # Purple, Khaki, PaleGreen, Plum, LightSkyBlue
    ]
    return colores_base * (n // len(colores_base) + 1)

def crear_grid_horario(lista_materias):
    """
    Genera dos DataFrames: Texto (visual) y Colores (fondo)
    """
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado"]
    horas = range(7, 22) # 7am a 10pm
    
    df_texto = pd.DataFrame("", index=horas, columns=dias)
    df_colores = pd.DataFrame("", index=horas, columns=dias)
    
    conflictos = []
    
    # Generamos colores pastel
    paleta = generar_paleta_colores(len(lista_materias))
    mapa_colores = {m['id']: paleta[i] for i, m in enumerate(lista_materias)}

    for materia in lista_materias:
        bloques = interpretar_horario(materia["Horario"])
        
        # Formato corto para que no ocupe tanto espacio
        nombre_display = f"{materia['Materia']}\n(G:{materia['Grupo']})"
        color = mapa_colores[materia['id']]
        
        for bloque in bloques:
            dia = bloque["dia"]
            h_inicio = bloque["inicio"]
            h_fin = bloque["fin"]
            
            # Iteramos sobre las horas del bloque
            for h in range(h_inicio, h_fin):
                if h in df_texto.index:
                    # VERIFICAR CONFLICTOS
                    # Si la celda ya tiene color, hay choque (a menos que sea la misma materia)
                    color_actual = df_colores.at[h, dia]
                    if color_actual and color_actual != color:
                        conflictos.append(f"Choque en {dia} a las {h}:00")
                        df_colores.at[h, dia] = "#ff4b4b" # Rojo intenso
                        df_texto.at[h, dia] = "⚠️ CHOQUE"
                    else:
                        # PINTAR
                        df_colores.at[h, dia] = color
                        
                        # LOGICA VISUAL: Solo poner texto en la primera hora
                        if h == h_inicio:
                            df_texto.at[h, dia] = nombre_display
                        # Las demás horas se quedan con texto vacío "" pero con fondo de color
                        
    return df_texto, df_colores, conflictos

# ==========================================
# AGREGAR ESTO AL FINAL DE LA SECCIÓN 4
# ==========================================

def parsear_html_generico(html, tipo_parseo="ESTANDAR"):
    """
    Parsea el HTML devuelto por el servidor y lo convierte en DataFrame.
    """
    soup = BeautifulSoup(html, "lxml")
    
    tablas = soup.find_all("table")
    if not tablas: return pd.DataFrame()
    
    # Tomamos la tabla más grande
    tabla = max(tablas, key=lambda t: len(t.find_all("tr")))
    filas = tabla.find_all("tr")
    
    datos = []
    
    # --- MEMORIA DE CONTEXTO ---
    contexto_actual = "General"
    turno_actual = "Indistinto"

    # Mapa de colores para detectar turno
    COLORES_TURNO = {
        "64C2FD": "Matutino",   # Azul
        "FFA97C": "Vespertino"  # Naranja
    }

    for fila in filas:
        celdas = fila.find_all("td")
        if not celdas: continue

        # ---------------------------------------------------------
        # 1. DETECCIÓN DE SEPARADORES (Encabezados)
        # ---------------------------------------------------------
        if not fila.get("class") or "sombreado" not in fila.get("class"):
            celda_header = celdas[0]
            if celda_header.get("colspan"):
                estilo_celda = celda_header.get("style", "").upper()
                texto_separador = celda_header.get_text(strip=True)

                # A) DETECTAR TURNO POR COLOR
                for hex_code, nombre_turno in COLORES_TURNO.items():
                    if hex_code in estilo_celda:
                        turno_actual = nombre_turno
                        break
                
                # B) ACTUALIZAR CONTEXTO (Nombre del Taller/LIP)
                if texto_separador:
                    if "Taller:" in texto_separador:
                        contexto_actual = texto_separador.replace("Taller:", "").strip()
                    elif "Cursos Optativos" in texto_separador:
                        contexto_actual = texto_separador.replace("Cursos Optativos Área", "").strip()
                        turno_actual = "Indistinto"
                    elif "LIP:" in texto_separador:
                         if "LIP:" in texto_separador:
                             contexto_actual = texto_separador.split("LIP:")[1].strip()
            continue

        # ---------------------------------------------------------
        # 2. EXTRACCIÓN DE DATOS (Filas 'sombreado')
        # ---------------------------------------------------------
        if "sombreado" in fila.get("class", []):
            if len(celdas) < 5: continue
            
            item = {}
            
            if tipo_parseo in ["ESTANDAR", "ASIGNATURA_CONTEXTO"]:
                item["Clave"] = limpiar_texto(celdas[0].text)
                
                raw_materia = celdas[1].text
                if "LIP:" in raw_materia:
                    item["Materia"] = limpiar_texto(raw_materia.split("LIP:")[0])
                else:
                    item["Materia"] = limpiar_texto(raw_materia)

                item["Grupo"] = limpiar_texto(celdas[2].text)
                item["Profesor"] = limpiar_texto(celdas[4].text)
                
                idx_horario = 5
                if len(celdas) > idx_horario:
                    item["Horario"] = extraer_horario(celdas[idx_horario])
                
                item["Agrupación"] = contexto_actual 
                item["Turno"] = turno_actual 

            elif tipo_parseo == "PROFESOR":
                item["Clave"] = limpiar_texto(celdas[0].text)
                item["Materia"] = limpiar_texto(celdas[1].text)
                item["Grupo"] = limpiar_texto(celdas[2].text)
                item["Agrupación"] = limpiar_texto(celdas[4].text) 
                item["Profesor"] = "BUSQUEDA PROFESOR"
                item["Horario"] = extraer_horario(celdas[5])
                item["Turno"] = "ND" 

            elif tipo_parseo == "GENERO":
                item["Clave"] = limpiar_texto(celdas[0].text)
                item["Materia"] = limpiar_texto(celdas[1].text)
                item["Grupo"] = limpiar_texto(celdas[2].text)
                item["Profesor"] = limpiar_texto(celdas[4].text)
                item["Horario"] = limpiar_texto(celdas[5].text)
                item["Agrupación"] = "Requisito Género"
                item["Turno"] = "Indistinto"

            if item:
                datos.append(item)

    return pd.DataFrame(datos)
    
# ==========================================
# 5. INTERFAZ DE USUARIO (STREAMLIT)
# ==========================================

st.set_page_config(page_title="UNAM Arq Scheduler", layout="wide", page_icon="🏛️")
# --- INICIALIZAR MOCHILA DE MATERIAS ---
if 'mi_horario' not in st.session_state:
    st.session_state.mi_horario = [] # Aquí guardaremos las materias

# --- CSS para mejorar apariencia ---
st.markdown("""
<style>
    .stDataFrame { border-radius: 10px; overflow: hidden; }
    thead tr th:first-child { display:none }
    tbody th { display:none }
    .stSelectbox label { font-weight: bold; font-size: 1.1em; color: #2e86c1;}
</style>
""", unsafe_allow_html=True)

# --- SIDEBAR: NAVEGACIÓN ---
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/c/ca/Escudo-UNAM-escalable.svg/1024px-Escudo-UNAM-escalable.svg.png", width=100)
    st.title("Buscador de Horarios")
    st.markdown("---")
    # ... (Dentro del sidebar)
    modo_busqueda = st.radio(
        "Selecciona modo:",
        ["Taller / Semestre", "Optativas", "Complementarios", "Asignatura", "Requisito de Género", "Profesor"]
    )
    st.info(f"Ciclo escolar: {CICLO_ACTUAL}")

# --- ÁREA PRINCIPAL ---
st.header(f"🏛️ Búsqueda por: {modo_busqueda}")

# 1. INICIALIZAR LA MEMORIA DE BÚSQUEDA
# Si no existe un lugar para guardar los resultados, lo creamos vacío
if 'resultados_busqueda' not in st.session_state:
    st.session_state.resultados_busqueda = pd.DataFrame()

# ==========================================
# LÓGICA POR MODO DE BÚSQUEDA
# ==========================================

if modo_busqueda == "Taller / Semestre":
    col1, col2 = st.columns(2)
    with col1:
        taller_nom = st.selectbox("Selecciona Taller", list(CATALOGOS["TALLERES"].keys()))
    with col2:
        semestre = st.selectbox("Semestre", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], index=1)
        if semestre == 0: st.caption("Mostrando todos los semestres")
    
    if st.button("Buscar"):
        html = consultar_api("taller.php", {"tal": CATALOGOS["TALLERES"][taller_nom], "talsem": semestre})
        if html:
            # GUARDAR EN SESSION_STATE
            st.session_state.resultados_busqueda = parsear_html_generico(html, "ESTANDAR")
        else:
            st.warning("No se encontraron datos.")

elif modo_busqueda == "Optativas":
    tipo_opt = st.radio("Filtrar por:", ["Área de Conocimiento", "Línea de Interés (LIP)"], horizontal=True)
    tal_fijo = 19
    val_select = 0
    endpoint = ""

    if tipo_opt == "Área de Conocimiento":
        area = st.selectbox("Selecciona Área", list(CATALOGOS["AREAS_OPTATIVAS"].keys()))
        val_select = CATALOGOS["AREAS_OPTATIVAS"][area]
        endpoint = "taller.php"
    else:
        lip = st.selectbox("Selecciona LIP", list(CATALOGOS["LIPS"].keys()))
        val_select = CATALOGOS["LIPS"][lip]
        endpoint = "LipHorarios.php"

    if st.button("Buscar Optativas"):
        html = consultar_api(endpoint, {"tal": tal_fijo, "talsem": val_select})
        if html:
            # GUARDAR EN SESSION_STATE
            st.session_state.resultados_busqueda = parsear_html_generico(html, "ESTANDAR")

elif modo_busqueda == "Complementarios":
    semestre_comp = st.slider("Semestre", 1, 10, 1)
    if st.button("Buscar Complementarios"):
        html = consultar_api("taller.php", {"tal": 18, "talsem": semestre_comp})
        if html:
            # GUARDAR EN SESSION_STATE
            st.session_state.resultados_busqueda = parsear_html_generico(html, "ESTANDAR")

elif modo_busqueda == "Asignatura":
    asig_nom = st.selectbox("Selecciona Asignatura (Ejemplo)", list(CATALOGOS["ASIGNATURAS_COMUNES"].keys()))
    asig_id = CATALOGOS["ASIGNATURAS_COMUNES"][asig_nom]
    
    if st.button("Buscar por Materia"):
        html = consultar_api("asignatura.php", {"asig": asig_id})
        if html:
            # GUARDAR EN SESSION_STATE
            st.session_state.resultados_busqueda = parsear_html_generico(html, "ASIGNATURA_CONTEXTO")

elif modo_busqueda == "Requisito de Género":
    st.markdown("Busca los grupos disponibles para el requisito de género.")
    if st.button("Consultar Grupos"):
        html = consultar_api("genero.php", {"tal": 18, "talsem": 20})
        if html:
            # GUARDAR EN SESSION_STATE
            st.session_state.resultados_busqueda = parsear_html_generico(html, "GENERO")

elif modo_busqueda == "Profesor":
    # 1. Cargamos la lista completa (solo tarda un poco la primera vez)
    with st.spinner("Cargando catálogo completo de profesores..."):
        catalogo_profes = obtener_catalogo_profesores()
    
    if catalogo_profes:
        # 2. Creamos el selector con la lista descargada
        # Usamos orden alfabético para facilitar la búsqueda
        nombres_ordenados = sorted(list(catalogo_profes.keys()))
        
        prof_nom = st.selectbox(
            "Selecciona Profesor", 
            nombres_ordenados,
            index=None, # Deja el campo vacío al principio
            placeholder="Escribe el nombre del profesor..."
        )
        
        if prof_nom: # Solo si el usuario seleccionó algo
            prof_id = catalogo_profes[prof_nom]
            
            if st.button("Ver Horario del Profesor"):
                html = consultar_api("profe.php", {"idprof": prof_id})
                if html:
                    st.session_state.resultados_busqueda = parsear_html_generico(html, "PROFESOR")
    else:
        st.warning("No se pudo descargar la lista de profesores. Intenta recargar la página.")
        
# ==========================================
# 6. RESULTADOS Y SELECCIÓN (MODO VERTICAL)
# ==========================================

st.markdown("---")

# 1. RECUPERAR DE LA MEMORIA
# Importante para que no se borre la tabla al dar click
if 'resultados_busqueda' not in st.session_state:
    st.session_state.resultados_busqueda = pd.DataFrame()

df_resultado = st.session_state.resultados_busqueda

# ---------------------------------------------------------
# PARTE SUPERIOR: RESULTADOS DE BÚSQUEDA
# ---------------------------------------------------------
st.subheader("📋 Resultados de la Búsqueda")

if not df_resultado.empty:
    # Añadimos columna de selección
    # Usamos .copy() para evitar advertencias de pandas
    df_resultado = df_resultado.copy()
    if "Seleccionar" not in df_resultado.columns:
        df_resultado.insert(0, "Seleccionar", False)
    
    # Configuramos columnas visibles
    columnas_visibles = ["Seleccionar", "Materia", "Grupo", "Horario", "Profesor", "Turno"]
    cols_final = [c for c in columnas_visibles if c in df_resultado.columns]

    # Tabla editable (ocupa todo el ancho disponible)
    df_editado = st.data_editor(
        df_resultado[cols_final],
        hide_index=True,
        width="stretch",  # <--- PONER ESTA NUEVA LÍNEA
        key="editor_resultados"
    )
    # Botón de agregar
    if st.button("➕ Agregar seleccionadas a Mi Horario", type="primary"):
        materias_a_agregar = df_editado[df_editado["Seleccionar"] == True]
        
        if not materias_a_agregar.empty:
            count_nuevas = 0
            for index, row in materias_a_agregar.iterrows():
                id_unico = f"{row['Materia']}-{row['Grupo']}"
                
                # Verificar duplicados
                existe = any(m['id'] == id_unico for m in st.session_state.mi_horario)
                
                if not existe:
                    st.session_state.mi_horario.append({
                        "id": id_unico,
                        "Materia": row["Materia"],
                        "Grupo": row["Grupo"],
                        "Horario": row.get("Horario", ""),
                        "Profesor": row.get("Profesor", "")
                    })
                    count_nuevas += 1
            
            if count_nuevas > 0:
                st.success(f"✅ Se agregaron {count_nuevas} materias.")
                st.rerun()
            else:
                st.warning("⚠️ Esas materias ya estaban en tu horario.")
        else:
            st.warning("⚠️ Selecciona primero la casilla de alguna materia.")
else:
    st.info("🔍 Realiza una búsqueda arriba para ver opciones disponibles.")

# ---------------------------------------------------------
# SEPARADOR VISUAL
# ---------------------------------------------------------
st.markdown("---")

# ---------------------------------------------------------
# PARTE INFERIOR: TU HORARIO ARMADO
# ---------------------------------------------------------
st.subheader("📅 Tu Horario Armado")

if len(st.session_state.mi_horario) > 0:
    # 1. Lista de materias (ahora en un expander para ahorrar espacio si son muchas)
    with st.expander("Ver lista de materias agregadas y eliminar", expanded=False):
        for i, materia in enumerate(st.session_state.mi_horario):
            c1, c2 = st.columns([0.9, 0.1])
            c1.text(f"• {materia['Materia']} (Grupo: {materia['Grupo']})")
            if c2.button("🗑️", key=f"del_{i}"):
                st.session_state.mi_horario.pop(i)
                st.rerun()

    # 2. Generar Grid Visual y Colores
    grid_texto, grid_colores, conflictos = crear_grid_horario(st.session_state.mi_horario)
    
    if conflictos:
        for conf in set(conflictos): 
            st.error(f"⛔ {conf}")
    
    # --- FUNCIÓN DE ESTILO MEJORADA ---
    def aplicar_estilos(df_val):
        """
        Aplica estilos CSS a todo el dataframe basado en grid_colores
        """
        # df_val es el dataframe de textos. No lo usamos, usamos grid_colores por índice
        df_styles = pd.DataFrame('', index=df_val.index, columns=df_val.columns)
        
        for col in df_val.columns:
            for idx in df_val.index:
                color_bg = grid_colores.at[idx, col]
                
                if color_bg:
                    # Estilo Base: Fondo de color + Texto Negro
                    estilo = f'background-color: {color_bg}; color: #000000;'
                    
                    # Truco visual: Bordes
                    # Si hay texto en esta celda, es el inicio del bloque -> Borde superior blanco
                    if df_val.at[idx, col] != "":
                        estilo += 'border-top: 2px solid white; vertical-align: top; font-weight: bold; font-size: 12px;'
                    else:
                        # Si no hay texto, es continuación -> Sin bordes internos para que parezca unido
                        estilo += 'border-top: none; color: transparent;' 
                    
                    df_styles.at[idx, col] = estilo
                    
        return df_styles

    # Mostrar la tabla
    st.markdown("### Vista Semanal")
    st.dataframe(
        grid_texto.style.apply(aplicar_estilos, axis=None),
        width="stretch",
        height=700 
    )
    
else:
    st.caption("Tu horario está vacío. Busca materias arriba y agrégalas con el botón ➕.")