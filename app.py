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
# 4. PARSER INTELIGENTE
# ==========================================

def limpiar_texto(texto):
    """Limpia espacios, saltos de línea y el símbolo '+' de los profesores."""
    if not texto: return ""
    return texto.strip().replace("+ ", "").replace("\n", " ").replace("\r", "")

def extraer_horario(celda_html):
    """Busca las etiquetas <b> donde suele estar el horario."""
    etiquetas_b = celda_html.find_all("b")
    if not etiquetas_b:
        return celda_html.get_text(strip=True) # Fallback
    return " / ".join([b.get_text(strip=True) for b in etiquetas_b])

def parsear_html_generico(html, tipo_parseo="ESTANDAR"):
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

    # Mapa de colores (OJO: BeautifulSoup a veces normaliza los estilos, así que buscamos substring)
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
        # Las filas separadoras NO tienen la clase 'sombreado'
        if not fila.get("class") or "sombreado" not in fila.get("class"):
            
            # Verificamos si es una celda ancha (típico de encabezados)
            celda_header = celdas[0]
            if celda_header.get("colspan"):
                
                # --- CORRECCIÓN AQUÍ: Leemos el estilo de la CELDA, no de la fila ---
                estilo_celda = celda_header.get("style", "").upper()
                texto_separador = celda_header.get_text(strip=True)

                # A) DETECTAR TURNO POR COLOR
                # Buscamos el código de color dentro del estilo de la celda
                encontro_color = False
                for hex_code, nombre_turno in COLORES_TURNO.items():
                    if hex_code in estilo_celda:
                        turno_actual = nombre_turno
                        encontro_color = True
                        break
                
                # Si no encontró color (ej. encabezados amarillos de "Semestre"), 
                # mantenemos el turno anterior o lo reseteamos si es un cambio mayor.
                # En este caso, solo actualizamos turno si encontramos color explícito.

                # B) ACTUALIZAR CONTEXTO (Nombre del Taller)
                if texto_separador:
                    if "Taller:" in texto_separador:
                        contexto_actual = texto_separador.replace("Taller:", "").strip()
                    elif "Cursos Optativos" in texto_separador:
                        contexto_actual = texto_separador.replace("Cursos Optativos Área", "").strip()
                        turno_actual = "Indistinto" # Las optativas no suelen tener turno fijo por color aquí
                    elif "LIP:" in texto_separador:
                         # A veces el LIP viene aquí
                         if "LIP:" in texto_separador:
                             contexto_actual = texto_separador.split("LIP:")[1].strip()

            continue # Pasamos a la siguiente fila

        # ---------------------------------------------------------
        # 2. EXTRACCIÓN DE DATOS (Filas 'sombreado')
        # ---------------------------------------------------------
        if "sombreado" in fila.get("class", []):
            if len(celdas) < 5: continue
            
            item = {}
            
            # --- PARSEO ESTÁNDAR / TALLER ---
            if tipo_parseo in ["ESTANDAR", "ASIGNATURA_CONTEXTO"]:
                item["Clave"] = limpiar_texto(celdas[0].text)
                
                raw_materia = celdas[1].text
                if "LIP:" in raw_materia:
                    # Limpiamos el texto sucio del LIP dentro de la materia
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

            # --- PARSEO PROFESOR ---
            elif tipo_parseo == "PROFESOR":
                item["Clave"] = limpiar_texto(celdas[0].text)
                item["Materia"] = limpiar_texto(celdas[1].text)
                item["Grupo"] = limpiar_texto(celdas[2].text)
                item["Agrupación"] = limpiar_texto(celdas[4].text) 
                item["Profesor"] = "BUSQUEDA PROFESOR"
                item["Horario"] = extraer_horario(celdas[5])
                item["Turno"] = "ND" 

            # --- PARSEO GÉNERO ---
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
    modo_busqueda = st.radio(
        "Selecciona modo:",
        ["Taller / Semestre", "Optativas", "Complementarios", "Asignatura", "Requisito de Género", "Profesor"]
    )
    st.info(f"Ciclo escolar: {CICLO_ACTUAL}")

# --- ÁREA PRINCIPAL ---
st.header(f"🏛️ Búsqueda por: {modo_busqueda}")

df_resultado = pd.DataFrame()

# ==========================================
# LÓGICA POR MODO DE BÚSQUEDA
# ==========================================

if modo_busqueda == "Taller / Semestre":
    col1, col2 = st.columns(2)
    with col1:
        taller_nom = st.selectbox("Selecciona Taller", list(CATALOGOS["TALLERES"].keys()))
    with col2:
        # Nota: El semestre 0 también existe para ver TODOS los semestres de un taller
        semestre = st.selectbox("Semestre", [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10], index=1)
        if semestre == 0: st.caption("Mostrando todos los semestres")
    
    if st.button("Buscar"):
        # Llamada normal, el ID 0 de "TODOS" se maneja solo
        html = consultar_api("taller.php", {"tal": CATALOGOS["TALLERES"][taller_nom], "talsem": semestre})
        
        if html:
            # Usamos el parser ESTANDAR, que ahora captura la "Agrupación" (Nombre del Taller o Semestre)
            df_resultado = parsear_html_generico(html, "ESTANDAR")

elif modo_busqueda == "Optativas":
    tipo_opt = st.radio("Filtrar por:", ["Área de Conocimiento", "Línea de Interés (LIP)"], horizontal=True)
    
    tal_fijo = 19 # Siempre es 19 para optativas
    val_select = 0
    
    if tipo_opt == "Área de Conocimiento":
        area = st.selectbox("Selecciona Área", list(CATALOGOS["AREAS_OPTATIVAS"].keys()))
        val_select = CATALOGOS["AREAS_OPTATIVAS"][area]
        endpoint = "taller.php" # Usa taller.php
    else:
        lip = st.selectbox("Selecciona LIP", list(CATALOGOS["LIPS"].keys()))
        val_select = CATALOGOS["LIPS"][lip]
        endpoint = "LipHorarios.php" # Usa endpoint distinto

    if st.button("Buscar Optativas"):
        html = consultar_api(endpoint, {"tal": tal_fijo, "talsem": val_select})
        if html:
            df_resultado = parsear_html_generico(html, "ESTANDAR")

elif modo_busqueda == "Complementarios":
    semestre_comp = st.slider("Semestre", 1, 10, 1)
    if st.button("Buscar Complementarios"):
        # Taller fijo 18 para complementarios
        html = consultar_api("taller.php", {"tal": 18, "talsem": semestre_comp})
        if html:
            df_resultado = parsear_html_generico(html, "ESTANDAR")

elif modo_busqueda == "Asignatura":
    # Nota: Aquí deberíamos tener un input de texto con autocompletado si tuviéramos todas las materias
    asig_nom = st.selectbox("Selecciona Asignatura (Ejemplo)", list(CATALOGOS["ASIGNATURAS_COMUNES"].keys()))
    asig_id = CATALOGOS["ASIGNATURAS_COMUNES"][asig_nom]
    
    if st.button("Buscar por Materia"):
        html = consultar_api("asignatura.php", {"asig": asig_id})
        if html:
            # Usamos el parser especial con contexto
            df_resultado = parsear_html_generico(html, "ASIGNATURA_CONTEXTO")

elif modo_busqueda == "Requisito de Género":
    st.markdown("Busca los grupos disponibles para el requisito de género.")
    if st.button("Consultar Grupos"):
        # Parámetros fijos observados en el código fuente
        html = consultar_api("genero.php", {"tal": 18, "talsem": 20})
        if html:
            df_resultado = parsear_html_generico(html, "GENERO")

elif modo_busqueda == "Profesor":
    # Nota: Igual que asignatura, requiere un catálogo completo o un buscador de texto
    prof_nom = st.selectbox("Selecciona Profesor (Ejemplo)", list(CATALOGOS["PROFESORES_EJEMPLO"].keys()))
    prof_id = CATALOGOS["PROFESORES_EJEMPLO"][prof_nom]
    
    if st.button("Ver Horario del Profesor"):
        html = consultar_api("profe.php", {"idprof": prof_id})
        if html:
            df_resultado = parsear_html_generico(html, "PROFESOR")

# ==========================================
# 6. RESULTADOS
# ==========================================

st.markdown("---")

if not df_resultado.empty:
    st.success(f"✅ Se encontraron {len(df_resultado)} registros.")
    
    # AÑADÍ "Turno" y "Agrupación" a la lista de columnas
    cols_order = ["Clave", "Materia", "Agrupación", "Turno", "Grupo", "Horario", "Profesor"]
    
    # Filtramos para mostrar solo las columnas que existan en el dataframe
    cols_final = [c for c in cols_order if c in df_resultado.columns]
    
    st.dataframe(
        df_resultado[cols_final], 
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("Esperando búsqueda o no se encontraron resultados.")