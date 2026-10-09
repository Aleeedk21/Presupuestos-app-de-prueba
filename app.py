"""
Gestor de Presupuestos - Multi Rubro (Presupify)
--------------------------------------------------------------
Pensada para cualquier oficio (aire acondicionado, electricidad,
plomería, albañilería, pintura, gasista, etc.), no solo climatización.

Ejecutar con:
    python -m streamlit run app.py

Instalar dependencias:
    pip install streamlit fpdf2 pandas plotly

Notas para quien esté aprendiendo Python con este código:
- RUBROS es un diccionario que funciona como "tabla de configuración":
  en vez de escribir un if/elif gigante por cada rubro, buscamos sus
  datos con RUBROS[nombre_del_rubro]. Es un patrón muy común.
- Los CONCEPTOS del presupuesto ya no son una tabla tipo Excel: cada uno
  es una "tarjeta" con campos redondeados. Para que eso funcione, cada
  concepto tiene un ID único (uid) y sus campos se guardan en
  st.session_state con claves como "c_desc_<uid>" (descripción),
  "c_cant_<uid>" (cantidad), "c_prec_<uid>" (precio) y "c_cat_<uid>"
  (categoría). La lista st.session_state.conceptos guarda solo los uid,
  en orden. Así, borrar un concepto del medio no mezcla los demás.
- En la pestaña "Panel" usamos pandas para transformar la lista de
  presupuestos (que es una lista de diccionarios) en una tabla, y
  poder agruparla y sumarla fácil con groupby().
- CALLBACKS (on_click / on_change): son funciones que Streamlit ejecuta
  ANTES de volver a correr el script, apenas el usuario toca un botón o
  cambia un campo. Son la forma correcta de modificar el valor de otros
  campos. Si intentás cambiar el valor de un campo después de que ya se
  dibujó en pantalla, Streamlit da error.
"""

import base64
import html
import json
import os
import shutil
import uuid
from datetime import date, datetime
from urllib.parse import quote

import pandas as pd
import plotly.express as px
import streamlit as st
from fpdf import FPDF

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
os.makedirs("datos", exist_ok=True)

# Links de Google Forms (pegá acá tus links entre las comillas)
URL_FORMULARIO_OPINION = "https://share.forms.app/garciaclima/contanos-que-te-parecio-paperlit"  # formulario de opiniones (3 preguntas)
URL_FORMULARIO_PRO = "https://share.forms.app/garciaclima/sumate-a-la-lista-de-espera-de-paperlit-pro"      # formulario de interés en el Plan Pro (mail)

# URL actual de la app: se imprime en el pie de página del PDF.
# Pegá acá la dirección vigente (ej: "https://tuapp.streamlit.app/").
# Si la dejás vacía, el pie muestra solo "Hecho con Presupify".
URL_APP = "https://presupify.streamlit.app/"

NAVY_RGB = (11, 37, 69)
PALETA_GRAFICOS = ["#2F6FD6", "#1FA97A", "#E0972B", "#D1445C", "#8E6FD6", "#3FB6C9"]

ESTADOS = ["Pendiente", "Aprobado", "Rechazado", "Completado"]

# Límites para las notas/condiciones: evitan que un texto larguísimo
# deforme el PDF o empuje contenido a una página extra.
MAX_CHARS_NOTAS = 600
MAX_LINEAS_NOTAS = 12

# Config de Plotly: sin barra de herramientas ni zoom con la rueda, para
# que en el celular el gráfico no "robe" el scroll de la página.
CONFIG_PLOTLY = {"displayModeBar": False, "scrollZoom": False}

# Texto de la primera opción del desplegable de servicios
OPCION_PERSONALIZADO = "Personalizado..."

# --------------------------------------------------------------
# RUBROS: acá vive toda la configuración por oficio. Agregar un
# rubro nuevo es simplemente sumar una entrada a este diccionario,
# el resto de la app lo toma automáticamente.
# --------------------------------------------------------------
RUBROS = {
    "Aire Acondicionado": {
        "categorias": [
            "Instalación Split", "Mantenimiento / Limpieza",
            "Detección / Reparación de Fugas", "Diagnóstico / Reparación Eléctrica",
            "Carga de Refrigerante", "Otro",
        ],
        "servicios": [
            {"categoria": "Instalación Split", "descripcion": "Instalación Split 3000 frigorías (mano de obra)", "precio": 45000.0},
            {"categoria": "Instalación Split", "descripcion": "Instalación Split 4500 frigorías (mano de obra)", "precio": 55000.0},
            {"categoria": "Mantenimiento / Limpieza", "descripcion": "Mantenimiento y limpieza profunda", "precio": 20000.0},
            {"categoria": "Detección / Reparación de Fugas", "descripcion": "Detección de fuga de gas", "precio": 25000.0},
            {"categoria": "Diagnóstico / Reparación Eléctrica", "descripcion": "Cambio de capacitor", "precio": 12000.0},
            {"categoria": "Carga de Refrigerante", "descripcion": "Carga de gas R410A", "precio": 30000.0},
        ],
    },
    "Electricidad": {
        "categorias": ["Instalación Eléctrica", "Tablero y Protecciones", "Reparación de Fallas", "Certificación", "Otro"],
        "servicios": [
            {"categoria": "Instalación Eléctrica", "descripcion": "Instalación de toma corriente", "precio": 8000.0},
            {"categoria": "Instalación Eléctrica", "descripcion": "Instalación de punto de luz", "precio": 7000.0},
            {"categoria": "Tablero y Protecciones", "descripcion": "Recambio de tablero eléctrico", "precio": 60000.0},
            {"categoria": "Reparación de Fallas", "descripcion": "Diagnóstico y reparación de cortocircuito", "precio": 15000.0},
        ],
    },
    "Plomería": {
        "categorias": ["Instalación de Agua", "Destapaciones", "Reparación de Pérdidas", "Sanitarios y Griferías", "Otro"],
        "servicios": [
            {"categoria": "Destapaciones", "descripcion": "Destapación de cañería", "precio": 18000.0},
            {"categoria": "Reparación de Pérdidas", "descripcion": "Reparación de pérdida de agua", "precio": 20000.0},
            {"categoria": "Sanitarios y Griferías", "descripcion": "Instalación de grifería", "precio": 15000.0},
        ],
    },
    "Albañilería": {
        "categorias": ["Construcción", "Revoque y Terminaciones", "Colocación de Pisos", "Demolición", "Otro"],
        "servicios": [
            {"categoria": "Construcción", "descripcion": "Levantamiento de pared (m2)", "precio": 25000.0},
            {"categoria": "Revoque y Terminaciones", "descripcion": "Revoque fino (m2)", "precio": 8000.0},
            {"categoria": "Colocación de Pisos", "descripcion": "Colocación de piso cerámico (m2)", "precio": 12000.0},
        ],
    },
    "Pintura": {
        "categorias": ["Pintura Interior", "Pintura Exterior", "Preparación de Superficie", "Otro"],
        "servicios": [
            {"categoria": "Pintura Interior", "descripcion": "Pintura de pared interior (m2)", "precio": 6000.0},
            {"categoria": "Pintura Exterior", "descripcion": "Pintura de fachada (m2)", "precio": 9000.0},
            {"categoria": "Preparación de Superficie", "descripcion": "Lijado y enduido (m2)", "precio": 4000.0},
        ],
    },
    "Gasista": {
        "categorias": ["Instalación de Gas", "Detección de Fugas", "Certificación", "Otro"],
        "servicios": [
            {"categoria": "Instalación de Gas", "descripcion": "Instalación de artefacto a gas", "precio": 25000.0},
            {"categoria": "Detección de Fugas", "descripcion": "Detección de fuga de gas", "precio": 18000.0},
        ],
    },
    "Otro / Personalizado": {
        "categorias": ["Mano de Obra", "Materiales", "Otro"],
        "servicios": [],
    },
}

# Adicionales rápidos POR DEFECTO. Cada negocio puede editarlos desde la
# pestaña "Configuración del Negocio" (se guardan en su configuración).
# Usan la categoría "Otro", presente en todos los rubros de arriba.
ADICIONALES_RAPIDOS_GENERICOS = [
    {"categoria": "Otro", "descripcion": "Mano de obra adicional", "precio": 10000.0},
    {"categoria": "Otro", "descripcion": "Materiales extra", "precio": 6000.0},
    {"categoria": "Otro", "descripcion": "Traslado / zona alejada", "precio": 8000.0},
]

# set_page_config tiene que ser el PRIMER comando de Streamlit del script.
st.set_page_config(
    page_title="Presupify",
    layout="centered",
    initial_sidebar_state="collapsed",  # la barra lateral (código personal) queda como opción secundaria
)

# Etiquetas de los campos de cada concepto (ver notas al inicio del archivo)
PREFIJOS_CONCEPTO = ("c_desc_", "c_cant_", "c_prec_", "c_cat_", "c_tot_")
PREFIJOS_ADICIONAL = ("a_desc_", "a_prec_")

# Categoría que existe en TODOS los rubros: se usa para conceptos nuevos en blanco.
CATEGORIA_POR_DEFECTO = "Otro"

# Clase CSS de la "píldora" de estado (historial)
CLASE_ESTADO = {
    "Pendiente": "estado-pendiente",
    "Aprobado": "estado-aprobado",
    "Rechazado": "estado-rechazado",
    "Completado": "estado-completado",
}


# ============================================================
# UTILIDADES GENERALES
# ============================================================
def safe_txt(s: str) -> str:
    """Evita errores de codificación en el PDF (Helvetica solo entiende latin-1)."""
    if s is None:
        return ""
    return str(s).encode("latin-1", "replace").decode("latin-1")


def esc(texto) -> str:
    """Escapa un texto para insertarlo dentro de HTML (evita que un nombre con
    símbolos como < o & rompa la página)."""
    return html.escape(str(texto if texto is not None else ""))


def moneda(valor, decimales=2) -> str:
    """Formato argentino: $ 1.234,56 (punto para los miles, coma para los decimales)."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0
    texto = f"{abs(numero):,.{decimales}f}"
    # Intercambia , y . pasando por un símbolo temporal para no pisarlos.
    texto = texto.replace(",", "#").replace(".", ",").replace("#", ".")
    return f"-$ {texto}" if numero < 0 else f"$ {texto}"


def dinero(valor) -> str:
    """Igual que moneda(), pero para texto Markdown: la barra invertida evita
    que Streamlit tome dos signos $ como una fórmula."""
    return moneda(valor).replace("$", "\\$")


def normalizar_codigo(texto) -> str:
    """Deja solo letras y números, en minúscula (así el código sirve como nombre de archivo)."""
    return "".join(c for c in str(texto) if c.isalnum()).lower()


def config_del_rubro(rubro):
    """Devuelve categorías y servicios del rubro (o los genéricos si no existe)."""
    return RUBROS.get(rubro, RUBROS["Otro / Personalizado"])


def limpiar_notas(texto) -> str:
    """Prepara las notas para el PDF: sin líneas vacías repetidas ni espacios
    al final (causan páginas en blanco) y con un tope de líneas y caracteres."""
    lineas = []
    for linea in str(texto or "").strip().splitlines():
        linea = linea.rstrip()
        if not linea and (not lineas or not lineas[-1]):
            continue
        lineas.append(linea)
    texto = "\n".join(lineas[:MAX_LINEAS_NOTAS]).strip()
    if len(texto) > MAX_CHARS_NOTAS:
        texto = texto[:MAX_CHARS_NOTAS].rstrip() + "..."
    return texto


def limpiar_telefono(texto) -> str:
    """Deja solo dígitos en un número de teléfono (remueve espacios, guiones, +)."""
    return "".join(c for c in str(texto or "") if c.isdigit())

# ============================================================
# PERSISTENCIA - ARCHIVOS POR CÓDIGO DE SESIÓN
# ============================================================
def archivo_historial(codigo=None):
    return f"datos/historial_{codigo or st.session_state.codigo}.json"


def archivo_config(codigo=None):
    return f"datos/config_{codigo or st.session_state.codigo}.json"


def cargar_historial():
    if os.path.exists(archivo_historial()):
        try:
            with open(archivo_historial(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []
    return []


def guardar_historial(historial):
    with open(archivo_historial(), "w", encoding="utf-8") as f:
        json.dump(historial, f, ensure_ascii=False, indent=2)


def siguiente_id(historial):
    """Número sugerido para el próximo presupuesto (el usuario puede cambiarlo)."""
    if not historial:
        return 1
    return max(p["id"] for p in historial) + 1


def cargar_config():
    default = {
        "nombre": "Mi Negocio de Servicios",
        "rubro": "Aire Acondicionado",
        "email": "",
        "web": "",
        "zona": "",
        "whatsapp": "",
        "validez_dias": 7,
        "firma_texto": "",
        "logo_path": "",
        "adicionales": [dict(a) for a in ADICIONALES_RAPIDOS_GENERICOS],
    }
    if os.path.exists(archivo_config()):
        try:
            with open(archivo_config(), "r", encoding="utf-8") as f:
                data = json.load(f)
                default.update(data)
        except (json.JSONDecodeError, OSError):
            pass
    return default


def guardar_config(config):
    with open(archivo_config(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def extension_archivo(nombre_archivo):
    return os.path.splitext(nombre_archivo)[1].lower()


def guardar_logo(uploaded_file):
    ext = extension_archivo(uploaded_file.name) or ".png"
    ruta = f"datos/logo_{st.session_state.codigo}{ext}"
    with open(ruta, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return ruta


def logo_base64_uri(path):
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            data = f.read()
        ext = extension_archivo(path).replace(".", "") or "png"
        mime = "jpeg" if ext in ("jpg", "jpeg") else ext
        return f"data:image/{mime};base64,{base64.b64encode(data).decode()}"
    return None


def subtitulo_empresa(empresa):
    partes = [p for p in [empresa.get("rubro", ""), empresa.get("zona", "")] if p]
    return " · ".join(partes)


def migrar_datos(codigo_origen, codigo_destino, config_actual):
    """Copia historial, configuración y logo de un código a otro.
    Se usa cuando alguien que venía con la sesión automática elige un código
    personal: así no pierde lo que ya cargó."""
    if os.path.exists(archivo_historial(codigo_origen)):
        shutil.copy(archivo_historial(codigo_origen), archivo_historial(codigo_destino))

    config = dict(config_actual)
    logo = config.get("logo_path", "")
    if logo and os.path.exists(logo):
        nuevo_logo = f"datos/logo_{codigo_destino}{extension_archivo(logo)}"
        shutil.copy(logo, nuevo_logo)
        config["logo_path"] = nuevo_logo
    with open(archivo_config(codigo_destino), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ============================================================
# GENERACIÓN DE PDF
# ============================================================
class PDFPresupuesto(FPDF):
    def __init__(self, empresa):
        super().__init__()
        self.empresa = empresa
        # El margen inferior de 25 mm deja lugar al pie de página: el contenido
        # nunca se superpone con el footer ni genera páginas sobrantes.
        self.set_auto_page_break(auto=True, margin=25)

    def header(self):
        logo_path = self.empresa.get("logo_path", "")
        if logo_path and os.path.exists(logo_path):
            try:
                self.image(logo_path, x=10, y=8, w=18, h=18, keep_aspect_ratio=True)
            except Exception:
                pass

        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*NAVY_RGB)
        self.cell(0, 10, safe_txt(self.empresa.get("nombre", "")), new_x="LMARGIN", new_y="NEXT", align="C")

        # Dos renglones chicos: actividad y zona / email y página web (los vacíos no se muestran).
        self.set_font("Helvetica", "", 10)
        self.set_text_color(90, 90, 90)
        for partes in (
            [self.empresa.get("rubro", ""), self.empresa.get("zona", "")],
            [self.empresa.get("email", ""), self.empresa.get("web", "")],
        ):
            partes = [x for x in partes if x]
            if partes:
                self.cell(0, 6, safe_txt("   |   ".join(partes)), new_x="LMARGIN", new_y="NEXT", align="C")

        self.set_draw_color(*NAVY_RGB)
        self.set_line_width(0.6)
        self.line(10, self.get_y() + 2, 200, self.get_y() + 2)
        self.ln(8)

    def footer(self):
        self.set_y(-22)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        firma = self.empresa.get("firma_texto", "")
        if firma:
            self.cell(0, 5, safe_txt(firma), new_x="LMARGIN", new_y="NEXT", align="C")
        texto = f"Presupuesto generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} - Página {self.page_no()}"
        self.cell(0, 5, safe_txt(texto), new_x="LMARGIN", new_y="NEXT", align="C")
        marca = "Hecho con Presupify" + (f" - {URL_APP}" if URL_APP else "")
        self.cell(0, 5, safe_txt(marca), align="C")

# Anchos de las columnas de la tabla del PDF (suman 180 mm = ancho útil de la hoja)
PDF_ANCHOS = [85, 15, 38, 42]
PDF_ENCABEZADOS = ["Concepto", "Cant.", "P. Unit.", "Subtotal"]
PDF_ALTO_LINEA = 5  # alto (mm) de cada renglón de texto dentro de una fila


def partir_texto(pdf, texto, ancho):
    """Divide un texto en renglones que entren en 'ancho' mm, cortando por palabras.
    Así las descripciones largas se ven completas (en vez de cortarse con '...')."""
    texto = safe_txt(texto)
    ancho_util = ancho - 3
    renglones = []
    actual = ""
    for palabra in texto.split():
        # Una palabra más larga que toda la celda se corta por letras.
        while pdf.get_string_width(palabra) > ancho_util:
            corte = len(palabra)
            while corte > 1 and pdf.get_string_width(palabra[:corte]) > ancho_util:
                corte -= 1
            if actual:
                renglones.append(actual)
                actual = ""
            renglones.append(palabra[:corte])
            palabra = palabra[corte:]
        prueba = f"{actual} {palabra}".strip()
        if pdf.get_string_width(prueba) <= ancho_util:
            actual = prueba
        else:
            renglones.append(actual)
            actual = palabra
    if actual:
        renglones.append(actual)
    return renglones or [""]


def dibujar_encabezado_tabla(pdf):
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(*NAVY_RGB)
    pdf.set_draw_color(*NAVY_RGB)
    pdf.set_line_width(0.2)
    pdf.set_text_color(255, 255, 255)
    for ancho, titulo in zip(PDF_ANCHOS, PDF_ENCABEZADOS):
        pdf.cell(ancho, 8, titulo, border=1, align="C", fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.set_draw_color(190, 198, 210)


def dibujar_fila_tabla(pdf, item, con_fondo):
    """Dibuja una fila de la tabla. Su alto depende de cuántos renglones
    ocupa la descripción."""
    renglones = partir_texto(pdf, item["descripcion"], PDF_ANCHOS[0])
    alto_texto = PDF_ALTO_LINEA * len(renglones)
    alto = max(7, alto_texto + 2)

    # Si la fila no entra en lo que queda de la hoja, pasa a la página siguiente
    # (repitiendo el encabezado de la tabla).
    if pdf.get_y() + alto > pdf.page_break_trigger:
        pdf.add_page()
        dibujar_encabezado_tabla(pdf)

    x0, y0 = pdf.l_margin, pdf.get_y()
    if con_fondo:
        pdf.set_fill_color(240, 243, 248)
    estilo = "DF" if con_fondo else "D"
    x = x0
    for ancho in PDF_ANCHOS:
        pdf.rect(x, y0, ancho, alto, style=estilo)
        x += ancho

    # Descripción (varios renglones, centrados verticalmente en la fila)
    y_texto = y0 + (alto - alto_texto) / 2
    for k, renglon in enumerate(renglones):
        pdf.set_xy(x0 + 1, y_texto + k * PDF_ALTO_LINEA)
        pdf.cell(PDF_ANCHOS[0] - 2, PDF_ALTO_LINEA, renglon)

    # Cantidad, precio unitario y subtotal (centrados verticalmente)
    x = x0 + PDF_ANCHOS[0]
    for ancho, texto, alineado in (
        (PDF_ANCHOS[1], f"{item['cantidad']:g}", "C"),
        (PDF_ANCHOS[2], moneda(item["precio_unitario"]), "R"),
        (PDF_ANCHOS[3], moneda(item["subtotal"]), "R"),
    ):
        pdf.set_xy(x + (0 if alineado == "C" else 1), y0)
        pdf.cell(ancho - (0 if alineado == "C" else 2), alto, texto, align=alineado)
        x += ancho
    pdf.set_xy(x0, y0 + alto)


def generar_pdf(presupuesto, empresa) -> bytes:
    pdf = PDFPresupuesto(empresa)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, safe_txt(f"Presupuesto N° {presupuesto['id']:04d}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, safe_txt(f"Fecha: {presupuesto['fecha']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, safe_txt(f"Estado: {presupuesto.get('estado', 'Pendiente')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Datos del Cliente", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, safe_txt(f"Cliente: {presupuesto['cliente_nombre']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, safe_txt(f"Dirección: {presupuesto['cliente_direccion']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, safe_txt(f"Teléfono: {presupuesto['cliente_telefono']}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    dibujar_encabezado_tabla(pdf)
    for indice, item in enumerate(presupuesto["items"]):
        dibujar_fila_tabla(pdf, item, con_fondo=(indice % 2 == 1))

    pdf.ln(3)

    x_label = sum(PDF_ANCHOS[:3])
    ancho_monto = PDF_ANCHOS[3]
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(x_label, 7, "Subtotal", align="R")
    pdf.cell(ancho_monto, 7, moneda(presupuesto["subtotal"]), align="R", new_x="LMARGIN", new_y="NEXT")

    if presupuesto.get("descuento_pct", 0) > 0:
        pdf.cell(x_label, 7, safe_txt(f"Descuento ({presupuesto['descuento_pct']:g}%)"), align="R")
        pdf.cell(ancho_monto, 7, "-" + moneda(presupuesto["descuento_monto"]), align="R", new_x="LMARGIN", new_y="NEXT")

    if presupuesto.get("envio", 0) > 0:
        pdf.cell(x_label, 7, safe_txt("Envío / Desplazamiento"), align="R")
        pdf.cell(ancho_monto, 7, moneda(presupuesto["envio"]), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(*NAVY_RGB)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(x_label, 9, "TOTAL", align="R", fill=True)
    pdf.cell(ancho_monto, 9, moneda(presupuesto["total"]), align="R", fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(6)

    # Las notas pasan por limpiar_notas(): tope de caracteres y de líneas.
    notas = limpiar_notas(presupuesto.get("notas", ""))
    if notas:
        # Se calcula cuántas líneas ocupa el texto para no dejar el título
        # "Notas / Condiciones" solo al final de una página.
        pdf.set_font("Helvetica", "", 9)
        try:
            lineas_notas = len(pdf.multi_cell(0, 5, safe_txt(notas), dry_run=True, output="LINES"))
        except Exception:
            lineas_notas = len(notas.splitlines()) + 2  # estimación si la versión de fpdf2 no soporta dry_run
        espacio_libre = pdf.h - pdf.b_margin - pdf.get_y()
        if espacio_libre < 7 + lineas_notas * 5:
            pdf.add_page()

        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, safe_txt("Notas / Condiciones"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, safe_txt(notas))

    return bytes(pdf.output())


@st.cache_data(show_spinner=False, max_entries=100)
def pdf_en_cache(presupuesto_json: str, empresa_json: str, logo_mtime: float) -> bytes:
    """Versión con caché de generar_pdf(), para el Historial: evita rearmar
    todos los PDF viejos cada vez que se toca cualquier botón de la app.
    (logo_mtime cambia si se sube un logo nuevo, así el caché se renueva.)"""
    return generar_pdf(json.loads(presupuesto_json), json.loads(empresa_json))


def pdf_del_historial(presupuesto, empresa) -> bytes:
    logo = empresa.get("logo_path", "")
    logo_mtime = os.path.getmtime(logo) if logo and os.path.exists(logo) else 0.0
    return pdf_en_cache(
        json.dumps(presupuesto, sort_keys=True),
        json.dumps(empresa, sort_keys=True),
        logo_mtime,
    )

# ============================================================
# DATOS PARA EL PANEL (pandas)
# ============================================================
def construir_dataframe_historial(historial):
    """Convierte la lista de presupuestos (lista de diccionarios) en una
    tabla de pandas, para poder agrupar y sumar fácil."""
    filas = []
    for p in historial:
        fecha_dt = datetime.strptime(p["fecha"], "%d/%m/%Y")
        filas.append({
            "id": p["id"],
            "fecha": fecha_dt,
            "mes": fecha_dt.strftime("%Y-%m"),
            "cliente": p["cliente_nombre"],
            "estado": p.get("estado", "Pendiente"),
            "total": p["total"],
        })
    return pd.DataFrame(filas)


def construir_dataframe_items(historial):
    """Aplana los ítems de todos los presupuestos en una sola tabla,
    para poder ver cuánto presupuestamos por categoría de servicio."""
    filas = []
    for p in historial:
        for item in p["items"]:
            filas.append({"categoria": item["categoria"], "subtotal": item["subtotal"]})
    return pd.DataFrame(filas)

def estilizar_grafico(fig, prefijo_eje=None):
    """Aplica los colores del tema activo a un gráfico de Plotly.
    prefijo_eje: "x" o "y" si ese eje muestra dinero (agrega el signo $)."""
    p = PALETAS[st.session_state.tema_actual]
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color=p["text"],
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        dragmode=False,  # sin arrastre: en el celular no interfiere con el scroll
        separators=",.",  # formato argentino: coma decimal, punto de miles
    )
    # fixedrange=True desactiva el zoom y el desplazamiento de los ejes.
    fig.update_xaxes(gridcolor=p["border"], fixedrange=True)
    fig.update_yaxes(gridcolor=p["border"], fixedrange=True)
    if prefijo_eje == "x":
        fig.update_xaxes(tickprefix="$ ")
    elif prefijo_eje == "y":
        fig.update_yaxes(tickprefix="$ ")
    return fig


def kpi_card(label, value, color_class):
    # Todo en una sola línea: si el HTML queda indentado dentro de un
    # string multilínea, Streamlit lo puede interpretar como bloque de
    # código en vez de HTML real.
    return f'<div class="kpi-card {color_class}"><div class="kpi-label">{esc(label)}</div><div class="kpi-value">{esc(value)}</div></div>'


def estado_pill(estado):
    """HTML de la píldora de color con el estado de un presupuesto."""
    clase = CLASE_ESTADO.get(estado, "estado-pendiente")
    return f'<span class="estado-pill {clase}">{esc(estado)}</span>'


# ============================================================
# CALLBACKS (se ejecutan ANTES de redibujar la pantalla)
# ============================================================
def nuevo_concepto(categoria=CATEGORIA_POR_DEFECTO, descripcion="", cantidad=1.0, precio=0.0):
    """Crea un concepto nuevo: genera su uid y deja cargados sus campos en
    session_state. Devuelve el uid (el llamador lo agrega a la lista)."""
    uid = uuid.uuid4().hex[:8]
    st.session_state[f"c_desc_{uid}"] = str(descripcion)
    st.session_state[f"c_cant_{uid}"] = max(0.01, float(cantidad or 1))
    st.session_state[f"c_prec_{uid}"] = max(0.0, float(precio or 0))
    st.session_state[f"c_cat_{uid}"] = categoria
    return uid


def agregar_concepto_vacio():
    st.session_state.conceptos.append(nuevo_concepto())


def quitar_concepto(uid):
    if uid in st.session_state.conceptos:
        st.session_state.conceptos.remove(uid)
    for prefijo in PREFIJOS_CONCEPTO:
        st.session_state.pop(prefijo + uid, None)


def vaciar_conceptos():
    for uid in list(st.session_state.conceptos):
        quitar_concepto(uid)


def al_cambiar_rubro():
    """Guarda el rubro elegido arriba de todo. Los conceptos cuya categoría no
    existe en el rubro nuevo pasan a 'Otro' (que existe en todos los rubros)."""
    st.session_state.empresa["rubro"] = st.session_state.rubro_selector
    guardar_config(st.session_state.empresa)
    st.session_state.servicio_sel = None
    categorias = config_del_rubro(st.session_state.empresa["rubro"])["categorias"]
    for uid in st.session_state.conceptos:
        if st.session_state.get(f"c_cat_{uid}") not in categorias:
            st.session_state[f"c_cat_{uid}"] = CATEGORIA_POR_DEFECTO


def agregar_servicio_predefinido():
    """Al elegir un servicio del desplegable, se suma como concepto nuevo
    (con su categoría y precio) y el desplegable vuelve a quedar vacío."""
    nombre = st.session_state.servicio_sel
    st.session_state.servicio_sel = None
    if not nombre:
        return
    servicios = config_del_rubro(st.session_state.empresa.get("rubro"))["servicios"]
    servicio = next((s for s in servicios if s["descripcion"] == nombre), None)
    if servicio:
        st.session_state.conceptos.append(
            nuevo_concepto(servicio["categoria"], servicio["descripcion"], 1, servicio["precio"])
        )


def agregar_adicional(adicional):
    """Agrega con un clic uno de los adicionales rápidos."""
    st.session_state.conceptos.append(
        nuevo_concepto(adicional.get("categoria", CATEGORIA_POR_DEFECTO), adicional["descripcion"], 1, adicional["precio"])
    )


def duplicar_presupuesto(presupuesto):
    """Copia cliente e ítems de un presupuesto viejo al formulario nuevo."""
    st.session_state.cliente_nombre_input = presupuesto["cliente_nombre"]
    st.session_state.cliente_direccion_input = presupuesto.get("cliente_direccion", "")
    st.session_state.cliente_telefono_input = presupuesto.get("cliente_telefono", "")
    vaciar_conceptos()
    for item in presupuesto["items"]:
        st.session_state.conceptos.append(
            nuevo_concepto(
                item.get("categoria", CATEGORIA_POR_DEFECTO),
                item["descripcion"],
                item.get("cantidad", 1),
                item.get("precio_unitario", 0),
            )
        )
    st.toast('Datos copiados. Andá a la pestaña "Nuevo Presupuesto".')


# --- Adicionales rápidos (pestaña Configuración): mismas tarjetas, sin tabla ---
def nueva_fila_adicional(descripcion="", precio=0.0):
    uid = uuid.uuid4().hex[:8]
    st.session_state[f"a_desc_{uid}"] = str(descripcion)
    st.session_state[f"a_prec_{uid}"] = max(0.0, float(precio or 0))
    return uid


def agregar_fila_adicional():
    st.session_state.adicionales_ids.append(nueva_fila_adicional())


def quitar_fila_adicional(uid):
    if uid in st.session_state.adicionales_ids:
        st.session_state.adicionales_ids.remove(uid)
    for prefijo in PREFIJOS_ADICIONAL:
        st.session_state.pop(prefijo + uid, None)


def cargar_filas_adicionales(adicionales):
    """Descarta las filas actuales y arma una fila por cada adicional guardado."""
    for uid in list(st.session_state.get("adicionales_ids", [])):
        quitar_fila_adicional(uid)
    st.session_state.adicionales_ids = [
        nueva_fila_adicional(a["descripcion"], a["precio"]) for a in adicionales
    ]


def aplicar_codigo():
    """Usa un código personal elegido por el usuario (opcional).
    - Si ya existen datos con ese código: los recupera.
    - Si no existen: copia los datos actuales a ese código para no perderlos."""
    nuevo = normalizar_codigo(st.session_state.codigo_input)
    anterior = st.session_state.codigo

    if len(nuevo) < 4:
        st.session_state.aviso_codigo = ("error", "Escribí un código de al menos 4 letras o números.")
        return
    if nuevo == anterior:
        st.session_state.aviso_codigo = ("info", "Ya estás usando ese código.")
        return

    if os.path.exists(archivo_historial(nuevo)) or os.path.exists(archivo_config(nuevo)):
        mensaje = "Datos recuperados."
    else:
        migrar_datos(anterior, nuevo, st.session_state.empresa)
        mensaje = "Listo: tus datos actuales quedaron guardados con ese código."

    st.session_state.codigo = nuevo
    st.query_params["codigo"] = nuevo

    # Se descarta todo lo que pertenecía a la sesión anterior.
    vaciar_conceptos()
    for uid in list(st.session_state.get("adicionales_ids", [])):
        quitar_fila_adicional(uid)
    for clave in ("empresa", "pdf_actual", "pdf_actual_info", "pdf_actual_nombre", "rubro_selector", "adicionales_ids"):
        st.session_state.pop(clave, None)
    st.session_state.codigo_input = ""
    st.session_state.aviso_codigo = ("ok", mensaje)

# ============================================================
# SESIÓN: SE USA DE INMEDIATO, SIN PEDIR CÓDIGO
# ============================================================
# Si el link ya trae un código (?codigo=...), se usa. Si no, se genera uno
# temporal único para esta visita. Se deja en el link para que, si la página
# se recarga, la persona siga con sus datos.
if "codigo" not in st.session_state:
    codigo_url = normalizar_codigo(st.query_params.get("codigo", ""))
    if len(codigo_url) >= 4:
        st.session_state.codigo = codigo_url
    else:
        st.session_state.codigo = "inv" + uuid.uuid4().hex[:10]
st.query_params["codigo"] = st.session_state.codigo

# ============================================================
# ESTADO INICIAL DE LA SESIÓN
# ============================================================
if "conceptos" not in st.session_state:
    st.session_state.conceptos = []  # lista de uid, en orden (ver notas al inicio del archivo)

if "empresa" not in st.session_state:
    st.session_state.empresa = cargar_config()

if "adicionales_ids" not in st.session_state:
    cargar_filas_adicionales(st.session_state.empresa.get("adicionales", []))

if "pdf_actual" not in st.session_state:
    st.session_state.pdf_actual = None

# ======== TEMAS: Azul Marino (por defecto) y Oscuro ========
# El modo claro se quitó. Si más adelante hace falta, se agrega una paleta
# "light" nueva en PALETAS y una entrada en TEMAS_DISPONIBLES.
TEMAS_DISPONIBLES = {
    "navy": {"label": "Azul Marino"},
    "dark": {"label": "Oscuro"},
}
# Cada paleta define directamente los colores que se inyectan como CSS variables en :root
# (no usamos data-tema ni JS observers: es 100% CSS plano — más robusto, no hay FOUC)
PALETAS = {
    "navy": {
        "bg_page":    "#0B2545",
        "bg_surface": "#163A6B",
        "bg_soft":    "#1B4379",
        "bg_card":    "#14325E",
        "border":     "#26456F",
        "accent":     "#2F6FD6",
        "accent_hover": "#4C8CF0",
        "accent_bg":  "rgba(47,111,214,0.18)",
        "text":       "#EAF1FB",
        "text_soft":  "#A7C2E6",
        "text_muted": "#89A7CC",
        "input_bg":   "rgba(11, 37, 69, 0.60)",
        "green":      "#1FA97A",
        "orange":     "#E0972B",
        "red":        "#D1445C",
        "shadow_lg":  "0 10px 30px rgba(0,0,0,0.32)",
        "shadow_sm":  "0 4px 12px rgba(0,0,0,0.22)",
    },
    "dark": {
        "bg_page":    "#14141B",
        "bg_surface": "#1C1C26",
        "bg_soft":    "#22222F",
        "bg_card":    "#1A1A23",
        "border":     "#2E2E3C",
        "accent":     "#6E7CF7",
        "accent_hover": "#8E9AFF",
        "accent_bg":  "rgba(110,124,247,0.22)",
        "text":       "#F2F2F7",
        "text_soft":  "#B8B8CC",
        "text_muted": "#88889C",
        "input_bg":   "#101017",
        "green":      "#2BBF8B",
        "orange":     "#EBA945",
        "red":        "#DC5A70",
        "shadow_lg":  "0 10px 30px rgba(0,0,0,0.55)",
        "shadow_sm":  "0 4px 12px rgba(0,0,0,0.40)",
    },
}
# Si la sesión traía un tema que ya no existe (ej: "light"), vuelve al azul marino.
if st.session_state.get("tema_actual") not in PALETAS:
    st.session_state.tema_actual = "navy"

# Desplegable de servicios predefinidos (arranca sin selección)
st.session_state.setdefault("servicio_sel", None)


# ============================================================
# ESTILOS — 2 TEMAS (inyectados por f-string, SIN data-tema ni JS)
# ============================================================
_TEMA_ACTUAL = st.session_state.tema_actual
_P = PALETAS[_TEMA_ACTUAL]  # paleta activa

st.markdown(
    f"""
    <style>

    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* ===== Base común ===== */
    html, body, [class*="css"] {{
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}
    h1, h2, h3, h4, h5, h6 {{ font-family: 'Inter', sans-serif; letter-spacing: -0.01em; }}

    /* VARIABLES DEL TEMA ACTIVO (inyectadas al arrancar, siempre ganan) */
    :root {{
        --bg-page:        {_P['bg_page']};
        --bg-surface:     {_P['bg_surface']};
        --bg-soft:        {_P['bg_soft']};
        --bg-card:        {_P['bg_card']};
        --border:         {_P['border']};
        --accent:         {_P['accent']};
        --accent-hover:   {_P['accent_hover']};
        --accent-bg:      {_P['accent_bg']};
        --text:           {_P['text']};
        --text-soft:      {_P['text_soft']};
        --text-muted:     {_P['text_muted']};
        --input-bg:       {_P['input_bg']};
        --green:          {_P['green']};
        --orange:         {_P['orange']};
        --red:            {_P['red']};
        --shadow-lg:      {_P['shadow_lg']};
        --shadow-sm:      {_P['shadow_sm']};
    }}

    /* Fondo de página + container principal (más ancho) */
    .stApp,
    section.main,
    .block-container,
    [data-testid="stAppViewContainer"],
    [data-testid="stApp"] {{
        background: var(--bg-page) !important;
        color: var(--text) !important;
    }}
    .block-container {{
        max-width: 880px !important;
        padding-top: 1.2rem !important;
        padding-bottom: 3rem !important;
    }}
    [data-testid="stHeader"] {{ background: transparent !important; }}
    [data-testid="stToolbar"] {{ color: var(--text-soft) !important; }}
    p, span, label, li, div {{ color: var(--text) !important; }}
    small {{ color: var(--text-muted) !important; }}
    h1, h2, h3, h4, h5, h6 {{ color: var(--text) !important; }}

    /* ==================== BOTONES ==================== */
    div.stButton > button,
    div.stDownloadButton > button,
    div[data-testid="stFormSubmitButton"] > button,
    div.stLinkButton > a {{
        background-color: var(--accent) !important;
        color: #FFFFFF !important;
        border-radius: 999px;
        border: none !important;
        padding: 0.65em 1.3em;
        font-weight: 600;
        font-family: 'Inter', sans-serif;
        letter-spacing: 0.005em;
        transition: all 0.15s ease;
        box-shadow: 0 3px 8px var(--accent-bg);
    }}
    div.stButton > button:hover,
    div.stDownloadButton > button:hover,
    div.stLinkButton > a:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {{
        background-color: var(--accent-hover) !important;
        transform: translateY(-1px);
        box-shadow: 0 6px 14px var(--accent-bg);
        color: #FFFFFF !important;
    }}
    div.stButton > button:active,
    div.stDownloadButton > button:active {{ transform: scale(0.98); }}

    /* Botones SECONDARY (botones de tema no-activo, etc.) */
    div.stButton > button[kind="secondary"],
    div.stDownloadButton > button[kind="secondary"],
    div[data-testid="stBaseButton-secondary"] {{
        background-color: var(--bg-soft) !important;
        color: var(--text) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 999px !important;
        box-shadow: none !important;
    }}
    div.stButton > button[kind="secondary"]:hover,
    div[data-testid="stBaseButton-secondary"]:hover {{
        background-color: var(--accent-bg) !important;
        color: var(--text) !important;
        border-color: var(--accent) !important;
        transform: translateY(-1px);
    }}

    /* ==================== TÍTULOS / SUBTÍTULOS (estilo PÍLDORA minimalista) ==================== */
    h2, h3 {{
        display: inline-block !important;
        background: transparent !important;
        padding: 0.15em 0.15em 0.35em 0.15em !important;
        margin-top: 0.4em !important;
        margin-bottom: 0.8em !important;
        border: none !important;
        border-radius: 14px !important;
        border-bottom: 3px solid var(--accent) !important;
        letter-spacing: -0.01em;
    }}
    h2 {{ border-bottom-width: 3.5px !important; }}
    h3 {{ border-bottom-width: 2.5px !important; }}

    /* ==================== MÉTRICAS (st.metric) ==================== */
    [data-testid="stMetric"] {{
        background-color: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 12px 18px;
        box-shadow: var(--shadow-sm);
    }}
    [data-testid="stMetricValue"] {{ color: var(--text) !important; font-weight: 700; }}
    [data-testid="stMetricLabel"] {{ color: var(--text-soft) !important; font-weight: 500; }}

    /* ==================== EXPANDERS / FORMS ==================== */
    div[data-testid="stExpander"],
    div[data-testid="stForm"] {{
        border-radius: 14px;
        border: 1px solid var(--border) !important;
        background-color: var(--bg-card);
        box-shadow: var(--shadow-sm);
    }}
    details > summary {{ color: var(--text) !important; font-weight: 600; }}
    div[data-testid="stExpander"]:hover {{ border-color: var(--accent) !important; }}

    /* Inputs / selectores con borde visible */
    div[data-baseweb="input"],
    div[data-baseweb="textarea"],
    div[data-baseweb="select"] > div,
    [data-testid="stTextInputRootElement"],
    [data-testid="stNumberInputContainer"],
    [data-testid="stTextAreaRootElement"],
    [data-testid="stDateInputField"],
    [data-testid="stSelectbox"] div[role="group"] {{
        border: 1.5px solid var(--border) !important;
        border-radius: 12px !important;
        background-color: var(--input-bg) !important;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.08);
        min-height: 46px;
        transition: border-color .15s ease, box-shadow .15s ease;
    }}
    /* Texto dentro de inputs */
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stNumberInputContainer"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    [data-testid="stDateInputField"] input {{
        color: var(--text) !important;
        padding: 10px 14px !important;
        font-size: 0.95rem !important;
        font-family: 'Inter', sans-serif !important;
    }}
    /* Placeholder adaptado */
    div[data-baseweb="input"] input::placeholder,
    div[data-baseweb="textarea"] textarea::placeholder,
    [data-testid="stTextInputRootElement"] input::placeholder,
    [data-testid="stTextAreaRootElement"] textarea::placeholder {{
        color: var(--text-muted) !important;
        opacity: 0.9;
    }}
    /* Foco con glow del accent */
    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="textarea"]:focus-within,
    div[data-baseweb="select"] > div:focus-within,
    [data-testid="stTextInputRootElement"]:focus-within,
    [data-testid="stNumberInputContainer"]:focus-within,
    [data-testid="stTextAreaRootElement"]:focus-within,
    [data-testid="stDateInputField"]:focus-within,
    [data-testid="stSelectbox"] div[role="group"]:focus-within {{
        border-color: var(--accent-hover) !important;
        box-shadow: 0 0 0 2px var(--accent-bg), inset 0 1px 2px rgba(0,0,0,0.10) !important;
    }}

    /* Pestañas (tabs): estilo PÍLDORA minimalista 100% adaptable al tema */
    /* Contenedor exterior (la "barra" de las tabs) */
    .stTabs [role="tablist"],
    [data-testid="stTabs"] [role="tablist"],
    .stTabs [data-baseweb="tab-list"],
    [data-testid="stTabs"] [data-baseweb="tab-list"] {{
        gap: 8px !important;
        background-color: var(--bg-soft) !important;
        padding: 8px !important;
        border-radius: 999px !important;
        border: 1px solid var(--border) !important;
        box-shadow: var(--shadow-sm) !important;
        display: flex;
        overflow: hidden;
    }}
    /* Cada pestaña individual (no seleccionada) */
    .stTabs [role="tab"],
    [data-testid="stTabs"] [role="tab"],
    [data-testid="stTab"],
    .stTabs [data-baseweb="tab"] {{
        border-radius: 999px !important;
        padding: 12px 22px !important;
        color: var(--text-soft) !important;
        font-weight: 500 !important;
        font-family: 'Inter', sans-serif !important;
        border: none !important;
        border-bottom: none !important;
        background: transparent !important;
        background-image: none !important;
        box-shadow: none !important;
        transition: all .18s ease !important;
        white-space: nowrap;
    }}
    /* Hover en pestaña no-activa */
    .stTabs [role="tab"]:hover,
    [data-testid="stTabs"] [role="tab"]:hover,
    [data-testid="stTab"]:hover,
    .stTabs [data-baseweb="tab"]:hover {{
        background-color: var(--accent-bg) !important;
        color: var(--text) !important;
        border: none !important;
        border-bottom: none !important;
        background-image: none !important;
    }}
    /* Pestaña ACTIVA (color del tema) */
    .stTabs [role="tab"][aria-selected="true"],
    [data-testid="stTabs"] [role="tab"][aria-selected="true"],
    [data-testid="stTab"][aria-selected="true"],
    .stTabs [data-baseweb="tab"][aria-selected="true"] {{
        background-color: var(--accent) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
        border: none !important;
        border-bottom: none !important;
        background-image: none !important;
        box-shadow: 0 4px 12px var(--accent-bg) !important;
        border-radius: 999px !important;
    }}
    /* Quitar la barrita inferior azul dura que Streamlit agrega por defecto */
    .stTabs [role="tab"]::after,
    .stTabs [data-baseweb="tab"]::after,
    [data-testid="stTab"]::after,
    [role="tablist"] > *::after {{
        display: none !important;
        content: none !important;
        background: transparent !important;
        border: none !important;
    }}

    /* Containers con borde */
    div[data-testid="stVerticalBlockBorderWrapper"] > div,
    div[data-testid="stContainer"] [data-testid="stVerticalBlockBorderWrapper"] {{
        border-radius: 16px !important;
        border: 1px solid var(--border) !important;
        background-color: var(--bg-card) !important;
        box-shadow: var(--shadow-sm);
    }}

    /* Banner principal */
    .header-banner {{
        background: linear-gradient(135deg, var(--bg-surface), var(--accent));
        padding: 22px 16px;
        border-radius: 18px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: var(--shadow-lg);
    }}
    .header-banner img {{ max-height: 60px; margin-bottom: 6px; }}
    .header-banner h1 {{ color: #FFFFFF !important; margin: 0; font-size: 1.7rem; font-weight: 700; }}
    .header-banner p {{ color: rgba(255,255,255,0.90) !important; margin: 4px 0 0 0; font-size: 0.92rem; }}

    /* Botón de WhatsApp */
    .wa-button {{
        display: inline-block;
        width: 100%;
        box-sizing: border-box;
        text-align: center;
        background-color: var(--accent);
        color: #FFFFFF !important;
        border-radius: 999px;
        padding: 0.65em 1.3em;
        font-weight: 600;
        text-decoration: none;
        margin-top: 8px;
        transition: background-color .15s ease, transform .15s ease;
    }}
    .wa-button:hover {{ background-color: var(--accent-hover); transform: translateY(-1px); }}

    /* Tarjetas KPI */
    .kpi-row {{
        display: flex;
        gap: 12px;
        overflow-x: auto;
        padding-bottom: 6px;
        margin-bottom: 8px;
    }}
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        margin-bottom: 8px;
    }}
    @media (max-width: 600px) {{
        .kpi-grid {{ grid-template-columns: repeat(2, 1fr); gap: 10px; }}
        .kpi-card .kpi-value {{ font-size: 1.08rem; }}
    }}
    .kpi-card {{
        flex: 1 1 140px;
        min-width: 140px;
        border-radius: 18px;
        padding: 16px 18px;
        color: #FFFFFF;
        box-shadow: var(--shadow-sm);
    }}
    .kpi-grid .kpi-card {{ flex: unset; min-width: 0; }}
    .kpi-card .kpi-label {{ font-size: 0.78rem; opacity: 0.92; font-weight: 500; }}
    .kpi-card .kpi-value {{
        font-size: 1.45rem;
        font-weight: 700;
        margin-top: 6px;
        word-break: break-word;
        overflow-wrap: break-word;
    }}
    .kpi-blue   {{ background: linear-gradient(135deg, #1E4E94, #2F6FD6); }}
    .kpi-green  {{ background: linear-gradient(135deg, #10714F, #2BBF8B); }}
    .kpi-orange {{ background: linear-gradient(135deg, #8F5E10, #EBA945); }}
    .kpi-red    {{ background: linear-gradient(135deg, #7E2131, #DC5A70); }}

    /* Chips de categorías */
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 4px 0; }}
    .chip {{
        background: var(--bg-soft);
        border: 1px solid var(--border);
        color: var(--text);
        padding: 6px 14px;
        border-radius: 999px;
        font-size: 0.80rem;
        font-weight: 500;
    }}

    /* Alertas / Toasts adaptados al tema */
    [data-testid="stAlert"] {{
        overflow: hidden;
        border-radius: 14px !important;
        border: 1px solid var(--border) !important;
        box-shadow: var(--shadow-sm) !important;
    }}
    [data-testid="stAlertContainer"],
    [data-testid="stAlertContainer"] > div {{
        border: none !important;
        box-shadow: none !important;
    }}
    [data-testid="stToast"] {{
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
    }}

    /* Divisor minimalista */
    [data-testid="stMarkdownContainer"] hr,
    hr {{
        border: none !important;
        border-top: 1px solid var(--border) !important;
        background: none !important;
        margin: 1.2em 0 !important;
    }}

    /* Checkbox / radio */
    [data-testid="stCheckbox"] label,
    [data-testid="stRadio"] label {{ color: var(--text) !important; }}

    /* Radio HORIZONTAL del selector de tema */
    div[data-testid="stRadio"] [role="radiogroup"] {{
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        background: var(--bg-soft);
        padding: 6px;
        border: 1px solid var(--border);
        border-radius: 999px;
        box-shadow: var(--shadow-sm);
    }}
    div[data-testid="stRadio"] [role="radiogroup"] label {{
        flex: 1;
        min-width: 0;
        padding: 6px 10px !important;
        border-radius: 999px;
        cursor: pointer;
        font-weight: 500 !important;
        transition: all .15s ease;
    }}
    div[data-testid="stRadio"] [role="radiogroup"] label:hover {{
        background-color: var(--accent-bg) !important;
        color: var(--text) !important;
    }}
    /* Radio SELECCIONADO */
    div[data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {{
        background: var(--accent) !important;
        color: #FFFFFF !important;
        box-shadow: 0 3px 8px var(--accent-bg);
        font-weight: 600 !important;
    }}
    /* Ocultar el círculo nativo del radio (estilo píldora) */
    div[data-testid="stRadio"] [role="radiogroup"] input[type="radio"] {{
        display: none !important;
    }}

    /* ==================== PÍLDORAS: inputs y selectores ==================== */
    /* Todos los campos de una línea son redondeados (el área de texto, menos). */
    div[data-baseweb="input"],
    div[data-baseweb="select"] > div,
    [data-testid="stTextInputRootElement"],
    [data-testid="stNumberInputContainer"],
    [data-testid="stDateInputField"],
    [data-testid="stSelectbox"] div[role="group"] {{ border-radius: 999px !important; }}
    div[data-baseweb="textarea"],
    [data-testid="stTextAreaRootElement"] {{ border-radius: 20px !important; }}
    div[data-baseweb="input"] input,
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stNumberInputContainer"] input,
    [data-testid="stDateInputField"] input {{ padding-left: 18px !important; padding-right: 18px !important; }}

    /* ==================== CONCEPTOS: tarjetas con campos tipo píldora ==================== */
    /* Cada concepto es una tarjeta (st.container con key "concepto_<uid>") con dos
       filas: [descripción | quitar] y [cantidad | precio | total]. Las filas NO se
       apilan en el celular: se fuerza flex-wrap: nowrap. */
    [class*="st-key-concepto_"],
    [class*="st-key-concepto_"] [data-testid="stVerticalBlock"] {{ gap: 0.55rem !important; }}

    [class*="st-key-cdesc_"] [data-testid="stHorizontalBlock"],
    [class*="st-key-cnums_"] [data-testid="stHorizontalBlock"],
    [class*="st-key-adic_"] [data-testid="stHorizontalBlock"] {{
        flex-wrap: nowrap !important;
        gap: 0.6rem !important;
    }}
    [class*="st-key-cdesc_"] [data-testid="stColumn"],
    [class*="st-key-cnums_"] [data-testid="stColumn"],
    [class*="st-key-adic_"] [data-testid="stColumn"] {{ min-width: 0 !important; }}

    /* Descripción: ocupa todo el ancho. Botón quitar: ancho fijo. */
    [class*="st-key-cdesc_"] [data-testid="stColumn"]:first-child,
    [class*="st-key-adic_"] [data-testid="stColumn"]:first-child {{ flex: 1 1 0 !important; width: auto !important; }}
    [class*="st-key-cdesc_"] [data-testid="stColumn"]:last-child,
    [class*="st-key-adic_"] [data-testid="stColumn"]:last-child {{ flex: 0 0 3rem !important; width: 3rem !important; }}
    /* Cantidad angosta; precio y total más anchos. */
    [class*="st-key-cnums_"] [data-testid="stColumn"]:nth-child(1) {{ flex: 0.8 1 0 !important; width: auto !important; }}
    [class*="st-key-cnums_"] [data-testid="stColumn"]:nth-child(2),
    [class*="st-key-cnums_"] [data-testid="stColumn"]:nth-child(3) {{ flex: 1.5 1 0 !important; width: auto !important; }}
    /* Adicionales (Configuración): precio con ancho fijo. */
    [class*="st-key-adic_"] [data-testid="stColumn"]:nth-child(2) {{ flex: 0 0 8.5rem !important; width: 8.5rem !important; }}

    /* Sin botones +/- dentro de las tarjetas: más lugar para escribir. */
    [class*="st-key-concepto_"] [data-testid="stNumberInputStepUp"],
    [class*="st-key-concepto_"] [data-testid="stNumberInputStepDown"],
    [class*="st-key-adic_"] [data-testid="stNumberInputStepUp"],
    [class*="st-key-adic_"] [data-testid="stNumberInputStepDown"] {{ display: none !important; }}

    /* Etiquetas chicas y discretas */
    [class*="st-key-concepto_"] [data-testid="stWidgetLabel"] p,
    [class*="st-key-adic_"] [data-testid="stWidgetLabel"] p {{
        font-size: 0.76rem !important;
        color: var(--text-muted) !important;
        margin-bottom: 0 !important;
    }}

    /* Total de cada concepto (campo de solo lectura, alineado a la derecha) */
    [class*="st-key-c_tot_"] input {{
        text-align: right;
        font-weight: 700 !important;
        opacity: 1 !important;
        -webkit-text-fill-color: var(--text) !important;
    }}
    [class*="st-key-c_tot_"] div[data-baseweb="input"],
    [class*="st-key-c_tot_"] [data-testid="stTextInputRootElement"] {{ background-color: var(--accent-bg) !important; }}
    @media (max-width: 640px) {{
        [class*="st-key-c_tot_"] input {{ font-size: 0.86rem !important; padding-left: 8px !important; padding-right: 12px !important; }}
    }}

    /* Botón de quitar (solo el ícono, rojo, sin fondo) */
    [class*="st-key-quitar"] [data-testid="stMarkdownContainer"] {{ display: none !important; }}
    div[class*="st-key-quitar"] div.stButton button[kind] {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        min-height: 46px;
        width: 100%;
        padding: 0 !important;
        border-radius: 999px !important;
    }}
    div[class*="st-key-quitar"] div.stButton button[kind] * {{ color: var(--red) !important; }}
    div[class*="st-key-quitar"] div.stButton button[kind]:hover {{
        background: rgba(209, 68, 92, 0.16) !important;
        transform: none !important;
    }}

    /* Botón de "añadir": contorno punteado */
    div[class*="st-key-btn_add"] div.stButton button[kind] {{
        background: transparent !important;
        border: 1.5px dashed var(--accent) !important;
        box-shadow: none !important;
    }}
    div[class*="st-key-btn_add"] div.stButton button[kind]:hover {{ background: var(--accent-bg) !important; }}

    /* Mensaje de lista vacía */
    .vacio {{
        border: 1.5px dashed var(--border);
        border-radius: 18px;
        padding: 22px 16px;
        text-align: center;
        font-size: 0.92rem;
        margin-bottom: 0.6rem;
    }}
    .vacio, .vacio * {{ color: var(--text-muted) !important; }}

    /* ==================== RESUMEN DEL PRESUPUESTO ==================== */
    .resumen {{
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 20px;
        padding: 16px 20px 20px 20px;
        box-shadow: var(--shadow-sm);
    }}
    .resumen-fila {{ display: flex; justify-content: space-between; padding: 6px 4px; font-size: 0.95rem; }}
    .resumen-fila, .resumen-fila * {{ color: var(--text-soft) !important; }}
    .resumen-total {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        margin-top: 10px;
        padding: 14px 22px;
        border-radius: 999px;
        background: var(--accent);
        font-size: 1.15rem;
        font-weight: 700;
    }}
    .resumen-total, .resumen-total * {{ color: #FFFFFF !important; }}

    /* ==================== ESTADOS (píldoras de color) ==================== */
    .estado-pill {{
        display: inline-block;
        padding: 3px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        border: 1px solid transparent;
        vertical-align: middle;
    }}
    .estado-pendiente  {{ background: rgba(224, 151, 43, 0.16); border-color: rgba(224, 151, 43, 0.55); }}
    .estado-pill.estado-pendiente, .estado-pill.estado-pendiente * {{ color: var(--orange) !important; }}
    .estado-aprobado   {{ background: rgba(31, 169, 122, 0.16); border-color: rgba(31, 169, 122, 0.55); }}
    .estado-pill.estado-aprobado, .estado-pill.estado-aprobado * {{ color: var(--green) !important; }}
    .estado-rechazado  {{ background: rgba(209, 68, 92, 0.16); border-color: rgba(209, 68, 92, 0.55); }}
    .estado-pill.estado-rechazado, .estado-pill.estado-rechazado * {{ color: var(--red) !important; }}
    .estado-completado {{ background: var(--accent-bg); border-color: var(--accent); }}
    .estado-pill.estado-completado, .estado-pill.estado-completado * {{ color: var(--accent-hover) !important; }}

    .hist-titulo {{ font-weight: 600; font-size: 1.02rem; margin-bottom: 2px; }}
    .hist-detalle {{ font-size: 0.88rem; }}
    .hist-detalle, .hist-detalle * {{ color: var(--text-soft) !important; }}

    /* ==================== RANKING (Top clientes) ==================== */
    .rank-row {{
        display: flex;
        align-items: center;
        gap: 12px;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 9px 20px 9px 10px;
        margin-bottom: 8px;
    }}
    .rank-pos {{
        width: 30px;
        height: 30px;
        border-radius: 999px;
        background: var(--accent-bg);
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: 700;
        font-size: 0.85rem;
        flex: 0 0 30px;
    }}
    .rank-name {{ flex: 1; min-width: 0; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .rank-total {{ font-weight: 700; white-space: nowrap; }}

    /* ==================== ARREGLOS DE COMPONENTES NATIVOS ==================== */
    /* Botones con tooltip (help=) quedan envueltos y perdían el estilo: se reafirma por data-testid. */
    button[data-testid="stBaseButton-secondary"] {{
        background-color: var(--bg-soft) !important;
        color: var(--text) !important;
        border: 1.5px solid var(--border) !important;
        border-radius: 999px !important;
        box-shadow: none !important;
    }}
    button[data-testid="stBaseButton-secondary"]:hover:not(:disabled) {{
        background-color: var(--accent-bg) !important;
        border-color: var(--accent) !important;
    }}
    button[data-testid="stBaseButton-primary"] {{
        background-color: var(--accent) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 999px !important;
    }}
    button[data-testid="stBaseButton-primary"]:hover:not(:disabled) {{ background-color: var(--accent-hover) !important; }}
    button:disabled {{ opacity: 0.45 !important; }}

    /* Texto de campos y desplegables siempre legible (no depende del tema base de Streamlit). */
    input, textarea {{ color: var(--text) !important; caret-color: var(--text); }}

    /* Pestañas: sin la rayita roja de la pestaña activa (la píldora ya la marca). */
    [data-testid="stTab"] > div:not([data-testid="stMarkdownContainer"]) {{ display: none !important; }}

    /* Selector de tema: sin círculos de radio, solo píldoras. */
    div[data-testid="stRadio"] label[data-testid="stRadioOption"] > div > div:first-child {{ display: none !important; }}
    div[data-testid="stRadio"] label[data-testid="stRadioOption"] {{ justify-content: center; }}

    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# BARRA LATERAL: CÓDIGO PERSONAL (OPCIONAL)
# ============================================================
with st.sidebar:
    st.subheader("Guardar o recuperar tus datos")
    st.caption(
        "Opcional. Podés usar la app sin código. Si querés recuperar tus presupuestos "
        "desde otro dispositivo, elegí un código fácil de recordar."
    )
    st.write("Código de esta sesión:")
    st.code(st.session_state.codigo, language=None)

    st.text_input("Código personal (ej: juan2026)", key="codigo_input")
    st.button("Usar este código", on_click=aplicar_codigo, width="stretch")

    aviso_codigo = st.session_state.pop("aviso_codigo", None)
    if aviso_codigo:
        tipo, texto = aviso_codigo
        {"ok": st.success, "error": st.error, "info": st.info}[tipo](texto)

    st.caption("El código no es una contraseña: cualquiera que lo conozca puede ver esos datos.")

# ============================================================
# ENCABEZADO
# ============================================================
def mostrar_banner():
    empresa = st.session_state.empresa
    logo_uri = logo_base64_uri(empresa.get("logo_path", ""))
    logo_html = f'<img src="{logo_uri}" />' if logo_uri else ""
    nombre = esc(empresa.get("nombre", ""))
    subtitulo = esc(subtitulo_empresa(empresa))
    banner_html = f'<div class="header-banner">{logo_html}<h1>{nombre}</h1><p>{subtitulo}</p></div>'
    st.markdown(banner_html, unsafe_allow_html=True)


mostrar_banner()

# ============================================================
# SELECTOR DE TEMA (Azul Marino / Oscuro)
# st.radio horizontal estilizado a píldora (sin JS observers). Los colores se
# toman de session_state.tema_actual en cada rerun y se inyectan via f-string
# en :root (el bloque CSS de arriba).
# ============================================================
_claves_temas = list(TEMAS_DISPONIBLES.keys())
_etiquetas_temas = [TEMAS_DISPONIBLES[k]["label"] for k in _claves_temas]

# Si quedó guardada una opción vieja (ej: "Claro" de una versión anterior), se descarta.
if st.session_state.get("selector_tema_radio") not in _etiquetas_temas:
    st.session_state.pop("selector_tema_radio", None)

_, col_tema = st.columns([2, 3])
with col_tema:
    _sel_label = st.radio(
        "Diseño visual",
        _etiquetas_temas,
        index=_claves_temas.index(_TEMA_ACTUAL),
        label_visibility="collapsed",
        horizontal=True,
        key="selector_tema_radio",
    )
    # Si cambió la opción -> actualizamos y forzamos rerun para que el
    # bloque CSS (arriba del todo) re-injecte las variables del nuevo tema.
    _nuevo_tema = _claves_temas[_etiquetas_temas.index(_sel_label)]
    if _nuevo_tema != _TEMA_ACTUAL:
        st.session_state.tema_actual = _nuevo_tema
        st.rerun()

st.divider()

st.info(
    "Versión de prueba: usá datos de ejemplo, no de clientes reales. "
    "Tus datos quedan asociados al enlace de esta página (guardala en favoritos) y podrían "
    "borrarse si el servidor se reinicia."
)
if URL_FORMULARIO_OPINION:
    st.link_button("Dejar mi opinión (2 minutos)", URL_FORMULARIO_OPINION, width="stretch")

# "Nuevo Presupuesto" va primero para que sea lo que se ve al entrar.
tab_nuevo, tab_panel, tab_config, tab_historial, tab_pro = st.tabs(
    ["Nuevo Presupuesto", "Panel", "Configuración del Negocio", "Historial", "Plan Pro"]
)

# ------------------------------------------------------------
# TAB 0: NUEVO PRESUPUESTO
# ------------------------------------------------------------
with tab_nuevo:
    # Si el presupuesto anterior se generó, se vacía la lista de conceptos acá,
    # ANTES de dibujar los campos (después de dibujarlos Streamlit no deja tocarlos).
    if st.session_state.pop("vaciar_conceptos_pendiente", False):
        vaciar_conceptos()

    # --- Rubro / Actividad: visible de entrada, arriba de todo ---
    opciones_rubro = list(RUBROS.keys())
    rubro_guardado = st.session_state.empresa.get("rubro", "Aire Acondicionado")
    st.selectbox(
        "Rubro / Actividad",
        opciones_rubro,
        index=opciones_rubro.index(rubro_guardado) if rubro_guardado in opciones_rubro else 0,
        key="rubro_selector",
        on_change=al_cambiar_rubro,
        help="Cambia las categorías y los servicios predefinidos disponibles.",
    )

    rubro_actual = st.session_state.empresa.get("rubro", "Aire Acondicionado")
    config_rubro = config_del_rubro(rubro_actual)
    categorias_actuales = config_rubro["categorias"]
    servicios_actuales = config_rubro["servicios"]

    st.subheader("Datos del Cliente")
    cliente_nombre = st.text_input("Nombre y Apellido", key="cliente_nombre_input")
    col1, col2 = st.columns(2)
    with col1:
        cliente_direccion = st.text_input("Dirección / Ubicación", key="cliente_direccion_input")
    with col2:
        cliente_telefono = st.text_input("Teléfono del cliente", key="cliente_telefono_input")

    # N° de presupuesto: viene prellenado con el siguiente, pero se puede
    # editar para llevar una secuencia propia. La clave incluye el número
    # sugerido: cuando se guarda un presupuesto, el campo se vuelve a prellenar.
    historial_actual = cargar_historial()
    numero_sugerido = siguiente_id(historial_actual)
    col_num, col_fecha = st.columns(2)
    with col_num:
        numero_presupuesto = st.number_input(
            "N° de presupuesto",
            min_value=1,
            max_value=999999,
            value=numero_sugerido,
            step=1,
            key=f"numero_presupuesto_{numero_sugerido}",
            help="Se completa solo con el siguiente número, pero podés cambiarlo.",
        )
    with col_fecha:
        fecha = st.date_input("Fecha", value=date.today())

    st.divider()
    st.subheader("Conceptos")

    # --- Una tarjeta por concepto (campos redondeados, sin tabla tipo Excel) ---
    # Los valores se leen de los propios campos: `items` es la lista "real" del
    # presupuesto en esta pasada del script.
    items = []
    if not st.session_state.conceptos:
        st.markdown(
            '<div class="vacio">Todavía no hay conceptos. Sumá uno con el botón '
            '"Añadir concepto" o elegí un servicio predefinido.</div>',
            unsafe_allow_html=True,
        )

    for uid in list(st.session_state.conceptos):
        # Si la categoría del concepto no existe en este rubro (ej: se duplicó un
        # presupuesto de otro rubro), se suma a las opciones para no perderla.
        categoria_guardada = st.session_state.get(f"c_cat_{uid}", CATEGORIA_POR_DEFECTO)
        opciones_categoria = list(categorias_actuales)
        if categoria_guardada not in opciones_categoria:
            opciones_categoria.append(categoria_guardada)

        with st.container(border=True, key=f"concepto_{uid}"):
            with st.container(key=f"cdesc_{uid}"):
                col_desc, col_quitar = st.columns([8, 1], vertical_alignment="bottom")
                with col_desc:
                    descripcion = st.text_input(
                        "Descripción",
                        key=f"c_desc_{uid}",
                        max_chars=100,
                        placeholder="Descripción del concepto",
                        label_visibility="collapsed",
                    )
                with col_quitar:
                    st.button(
                        "Quitar",
                        key=f"quitar_{uid}",
                        icon=":material/close:",
                        type="tertiary",
                        on_click=quitar_concepto,
                        args=(uid,),
                    )

            with st.container(key=f"cnums_{uid}"):
                col_cant, col_prec, col_tot = st.columns([1, 2, 2])
                with col_cant:
                    cantidad = st.number_input(
                        "Cant.", min_value=0.01, max_value=100000.0, step=1.0, format="%g", key=f"c_cant_{uid}",
                    )
                with col_prec:
                    precio = st.number_input(
                        "Precio unitario ($)", min_value=0.0, max_value=100000000.0, step=100.0,
                        format="%.2f", key=f"c_prec_{uid}",
                    )
                # Si el campo queda vacío, Streamlit devuelve None: se toma el valor mínimo.
                cantidad = float(cantidad or 1.0)
                precio = float(precio or 0.0)
                subtotal_fila = cantidad * precio
                with col_tot:
                    # Campo de solo lectura: se actualiza solo con cantidad x precio.
                    st.session_state[f"c_tot_{uid}"] = moneda(subtotal_fila)
                    st.text_input("Total", key=f"c_tot_{uid}", disabled=True)

            categoria = st.selectbox(
                "Categoría", opciones_categoria, key=f"c_cat_{uid}", label_visibility="collapsed",
            )

        items.append({
            "categoria": categoria,
            "descripcion": (descripcion or "").strip(),
            "cantidad": cantidad,
            "precio_unitario": precio,
            "subtotal": subtotal_fila,
        })

    col_agregar, col_vaciar = st.columns([3, 1])
    with col_agregar:
        st.button(
            "Añadir concepto",
            key="btn_add_concepto",
            icon=":material/add:",
            on_click=agregar_concepto_vacio,
            width="stretch",
        )
    with col_vaciar:
        st.button(
            "Vaciar lista",
            key="btn_vaciar",
            on_click=vaciar_conceptos,
            width="stretch",
            help="Quita todos los conceptos de la lista (no se puede deshacer).",
            disabled=not items,
        )

    # --- Agregar más rápido: servicios predefinidos y adicionales ---
    if servicios_actuales:
        st.selectbox(
            "Agregar un servicio predefinido",
            [s["descripcion"] for s in servicios_actuales],
            index=None,
            placeholder="Elegí un servicio para sumarlo a la lista",
            key="servicio_sel",
            on_change=agregar_servicio_predefinido,
        )

    adicionales = st.session_state.empresa.get("adicionales", [])
    if adicionales:
        st.caption("Adicionales rápidos (se editan en \"Configuración del Negocio\")")
        # Se acomodan de a 3 por fila, sin importar cuántos haya.
        for inicio in range(0, len(adicionales), 3):
            fila = adicionales[inicio:inicio + 3]
            for offset, (col, ad) in enumerate(zip(st.columns(len(fila)), fila)):
                with col:
                    st.button(
                        ad["descripcion"],
                        key=f"add_rapido_{inicio + offset}",
                        on_click=agregar_adicional,
                        args=(ad,),
                        width="stretch",
                    )
    else:
        st.caption('No hay adicionales rápidos cargados. Podés crearlos en "Configuración del Negocio".')

    aviso_item = st.session_state.pop("aviso_item", None)
    if aviso_item:
        (st.success if aviso_item[0] == "ok" else st.error)(aviso_item[1])

    # Resumen por categoría hecho "a mano" con un diccionario común.
    # (En la pestaña Panel hacemos lo mismo con pandas groupby, que
    # conviene cuando hay muchos datos acumulados en el historial).
    if items:
        resumen_por_categoria = {}
        for it in items:
            resumen_por_categoria[it["categoria"]] = resumen_por_categoria.get(it["categoria"], 0) + it["subtotal"]

        chips_html = "".join(
            f'<span class="chip">{esc(cat)}: {moneda(monto, 0)}</span>'
            for cat, monto in resumen_por_categoria.items()
        )
        st.markdown(f'<div class="chip-row">{chips_html}</div>', unsafe_allow_html=True)

    st.divider()
    st.subheader("Descuento y Envío")
    col1, col2 = st.columns(2)
    with col1:
        descuento_pct = st.number_input("Descuento (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
    with col2:
        envio = st.number_input("Envío / Desplazamiento ($)", min_value=0.0, max_value=100000000.0, value=0.0, step=100.0)

    st.subheader("Estado y Notas")
    estado = st.selectbox("Estado del presupuesto", ESTADOS, index=0)

    validez = st.session_state.empresa.get("validez_dias", 7)
    notas_default = (
        f"Presupuesto válido por {validez} días.\n"
        "No incluye materiales no especificados.\n"
        "Garantía del trabajo realizado: 6 meses."
    )
    notas = st.text_area(
        "Notas / Condiciones",
        value=notas_default,
        height=100,
        max_chars=MAX_CHARS_NOTAS,
        help=f"Máximo {MAX_CHARS_NOTAS} caracteres, para que el PDF quede prolijo.",
    )

    subtotal = sum(i["subtotal"] for i in items)
    descuento_monto = subtotal * (descuento_pct / 100)
    total = subtotal - descuento_monto + envio

    st.divider()
    st.subheader("Resumen")
    # Todo en una sola línea (sin sangrías) para que Streamlit lo tome como HTML.
    resumen_html = (
        '<div class="resumen">'
        f'<div class="resumen-fila"><span>Subtotal</span><span>{moneda(subtotal)}</span></div>'
    )
    if descuento_monto > 0:
        resumen_html += (
            f'<div class="resumen-fila"><span>Descuento ({descuento_pct:g}%)</span>'
            f'<span>-{moneda(descuento_monto)}</span></div>'
        )
    if envio > 0:
        resumen_html += f'<div class="resumen-fila"><span>Envío / Desplazamiento</span><span>{moneda(envio)}</span></div>'
    resumen_html += (
        f'<div class="resumen-total"><span>Total cotizado</span><span>{moneda(total)}</span></div>'
        '</div>'
    )
    st.markdown(resumen_html, unsafe_allow_html=True)

    st.write("")

    if st.button("Generar PDF", type="primary", width="stretch"):
        errores = []
        if not cliente_nombre.strip():
            errores.append("Falta el nombre del cliente.")
        if not items:
            errores.append("Agregá al menos un concepto al presupuesto.")
        else:
            if any(not i["descripcion"] for i in items):
                errores.append("Hay conceptos sin descripción: completalos o quitalos.")
            if subtotal <= 0:
                errores.append("Cargá el precio de al menos un concepto.")

        historial = cargar_historial()
        nuevo_id = int(numero_presupuesto)
        if any(p["id"] == nuevo_id for p in historial):
            errores.append(f"Ya existe el presupuesto N° {nuevo_id:04d}. Elegí otro número.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            # Se guardan tipos simples de Python (int/float/str) para que el JSON no falle.
            items_limpios = [
                {
                    "categoria": str(i["categoria"]),
                    "descripcion": i["descripcion"],
                    "cantidad": float(i["cantidad"]),
                    "precio_unitario": float(i["precio_unitario"]),
                    "subtotal": float(i["subtotal"]),
                }
                for i in items
            ]

            presupuesto = {
                "id": nuevo_id,
                "fecha": fecha.strftime("%d/%m/%Y"),
                "cliente_nombre": cliente_nombre.strip(),
                "cliente_direccion": cliente_direccion.strip(),
                "cliente_telefono": cliente_telefono.strip(),
                "items": items_limpios,
                "subtotal": float(subtotal),
                "descuento_pct": float(descuento_pct),
                "descuento_monto": float(descuento_monto),
                "envio": float(envio),
                "total": float(total),
                "notas": limpiar_notas(notas),
                "estado": estado,
            }

            try:
                pdf_bytes = generar_pdf(presupuesto, st.session_state.empresa)
            except Exception as e:
                st.error(f"Ocurrió un error al generar el PDF: {e}")
                pdf_bytes = None

            if pdf_bytes:
                historial.append(presupuesto)
                guardar_historial(historial)

                st.session_state.pdf_actual = pdf_bytes
                st.session_state.pdf_actual_nombre = (
                    f"presupuesto_{nuevo_id:04d}_{cliente_nombre.strip().replace(' ', '_')}.pdf"
                )
                st.session_state.pdf_actual_info = {
                    "cliente": cliente_nombre.strip(),
                    "cliente_telefono": cliente_telefono.strip(),
                    "total": total,
                    "id": nuevo_id,
                }
                # La lista de conceptos se vacía en la próxima pasada (ver el inicio de esta pestaña).
                st.session_state.vaciar_conceptos_pendiente = True
                # Se guarda el aviso y se recarga: así el campo "N° de presupuesto"
                # ya muestra el número siguiente. El aviso se muestra tras el botón.
                st.session_state.aviso_generado = f"Presupuesto N° {nuevo_id:04d} generado y guardado."
                st.rerun()

    aviso_generado = st.session_state.pop("aviso_generado", None)
    if aviso_generado:
        st.success(aviso_generado)

    if st.session_state.get("pdf_actual"):
        info = st.session_state.pdf_actual_info
        st.download_button(
            "Descargar PDF",
            data=st.session_state.pdf_actual,
            file_name=st.session_state.pdf_actual_nombre,
            mime="application/pdf",
            width="stretch",
            key="descarga_pdf_actual",
        )

        telefono_cliente_wa = limpiar_telefono(info.get("cliente_telefono", ""))
        if telefono_cliente_wa:
            mensaje = (
                f"Hola {info['cliente']}, te comparto el presupuesto N° {info['id']:04d} "
                f"por un total de {moneda(info['total'])}. Cualquier consulta quedo a disposición."
            )
            wa_url = f"https://wa.me/{telefono_cliente_wa}?text={quote(mensaje)}"
            st.markdown(
                f'<a href="{wa_url}" target="_blank" class="wa-button">Enviar aviso por WhatsApp</a>',
                unsafe_allow_html=True,
            )
            st.caption("El mensaje se envía al teléfono del cliente cargado en Datos del Cliente.")
        else:
            st.caption("Para enviar el aviso por WhatsApp, cargá el teléfono del cliente en la sección Datos del Cliente.")

# ------------------------------------------------------------
# TAB 1: PANEL (dashboard con pandas + plotly)
# ------------------------------------------------------------
with tab_panel:
    historial_panel = cargar_historial()

    if not historial_panel:
        st.info("Todavía no generaste ningún presupuesto. Los indicadores van a aparecer acá a medida que cargues datos.")
    else:
        df_hist = construir_dataframe_historial(historial_panel)
        df_items = construir_dataframe_items(historial_panel)

        mes_actual = date.today().strftime("%Y-%m")
        total_historico = df_hist["total"].sum()
        total_mes = df_hist.loc[df_hist["mes"] == mes_actual, "total"].sum()
        cantidad_pendientes = int((df_hist["estado"] == "Pendiente").sum())
        cantidad_aprobados = int((df_hist["estado"] == "Aprobado").sum())

        cards_html = (
            '<div class="kpi-row">'
            + kpi_card("Total cotizado histórico", moneda(total_historico, 0), "kpi-blue")
            + kpi_card("Cotizado este mes", moneda(total_mes, 0), "kpi-green")
            + kpi_card("Pendientes", str(cantidad_pendientes), "kpi-orange")
            + kpi_card("Aprobados", str(cantidad_aprobados), "kpi-green")
            + "</div>"
        )
        st.markdown(cards_html, unsafe_allow_html=True)

        st.write("")
        st.subheader("Presupuestado por mes")
        df_mensual = df_hist.groupby("mes", as_index=False)["total"].sum().sort_values("mes")
        fig_mensual = px.bar(df_mensual, x="mes", y="total", labels={"mes": "Mes", "total": "Total presupuestado"})
        fig_mensual.update_traces(marker_color=_P["accent"])
        fig_mensual.update_xaxes(type="category")
        st.plotly_chart(estilizar_grafico(fig_mensual, prefijo_eje="y"), width="stretch", config=CONFIG_PLOTLY)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Por estado")
            df_estado = df_hist.groupby("estado", as_index=False).size().rename(columns={"size": "cantidad"})
            fig_estado = px.pie(
                df_estado, names="estado", values="cantidad", hole=0.55,
                color_discrete_sequence=PALETA_GRAFICOS,
            )
            st.plotly_chart(estilizar_grafico(fig_estado), width="stretch", config=CONFIG_PLOTLY)

        with col_b:
            st.subheader("Por categoría")
            if not df_items.empty:
                df_categoria = (
                    df_items.groupby("categoria", as_index=False)["subtotal"]
                    .sum()
                    .sort_values("subtotal", ascending=True)
                )
                fig_categoria = px.bar(
                    df_categoria, x="subtotal", y="categoria", orientation="h",
                    color_discrete_sequence=PALETA_GRAFICOS,
                    labels={"subtotal": "Total", "categoria": ""},
                )
                st.plotly_chart(
                    estilizar_grafico(fig_categoria, prefijo_eje="x"), width="stretch", config=CONFIG_PLOTLY,
                )

        st.subheader("Top clientes")
        df_top_clientes = (
            df_hist.groupby("cliente", as_index=False)["total"]
            .sum()
            .sort_values("total", ascending=False)
            .head(5)
        )
        # Ranking en filas redondeadas (en vez de una tabla tipo planilla).
        filas_ranking = "".join(
            f'<div class="rank-row"><div class="rank-pos">{posicion}</div>'
            f'<div class="rank-name">{esc(fila.cliente)}</div>'
            f'<div class="rank-total">{moneda(fila.total)}</div></div>'
            for posicion, fila in enumerate(df_top_clientes.itertuples(index=False), start=1)
        )
        st.markdown(filas_ranking, unsafe_allow_html=True)

# ------------------------------------------------------------
# TAB 2: CONFIGURACIÓN DEL NEGOCIO
# ------------------------------------------------------------
with tab_config:
    # Tras guardar, se vuelven a armar las filas de adicionales desde lo guardado
    # (así desaparecen las vacías). Va ANTES de dibujar los campos.
    if st.session_state.pop("recargar_adicionales_pendiente", False):
        cargar_filas_adicionales(st.session_state.empresa.get("adicionales", []))

    aviso_config = st.session_state.pop("aviso_config", None)
    if aviso_config:
        st.success(aviso_config)

    st.subheader("Datos del Negocio")
    empresa = st.session_state.empresa

    nombre_emp = st.text_input("Nombre / Marca", value=empresa.get("nombre", ""))
    st.caption('El rubro se elige arriba de todo, en la pestaña "Nuevo Presupuesto".')

    col1, col2 = st.columns(2)
    with col1:
        email_emp = st.text_input("Email de la empresa", value=empresa.get("email", ""), placeholder="Ej: tuempresa@gmail.com")
    with col2:
        zona_emp = st.text_input("Zona de cobertura", value=empresa.get("zona", ""))

    web_emp = st.text_input(
        "Página web (opcional)",
        value=empresa.get("web", ""),
        placeholder="Ej: www.tuempresa.com.ar",
    )

    whatsapp_emp = st.text_input(
        "Número de WhatsApp para envíos (con código de país, sin +, ej: 5491122334455)",
        value=empresa.get("whatsapp", ""),
    )

    opciones_validez = [7, 15, 30]
    validez_actual = empresa.get("validez_dias", 7)
    validez_emp = st.selectbox(
        "Validez del presupuesto (días)",
        opciones_validez,
        index=opciones_validez.index(validez_actual) if validez_actual in opciones_validez else 0,
    )

    firma_emp = st.text_input(
        "Texto de firma / pie de página (opcional)",
        value=empresa.get("firma_texto", ""),
        placeholder="Ej: Juan Pérez - Técnico Matriculado",
    )

    st.subheader("Adicionales rápidos")
    st.caption(
        "Son los botones de un clic de la pestaña \"Nuevo Presupuesto\". "
        "Editalos, agregá los que quieras o quitá los que no uses, y después tocá \"Guardar cambios\"."
    )
    for uid in list(st.session_state.adicionales_ids):
        with st.container(key=f"adic_{uid}"):
            col_ad_desc, col_ad_prec, col_ad_quitar = st.columns([5, 3, 1], vertical_alignment="bottom")
            with col_ad_desc:
                st.text_input(
                    "Descripción", key=f"a_desc_{uid}", max_chars=80,
                    placeholder="Descripción del adicional", label_visibility="collapsed",
                )
            with col_ad_prec:
                st.number_input(
                    "Precio ($)", min_value=0.0, max_value=100000000.0, step=100.0, format="%.2f",
                    key=f"a_prec_{uid}", label_visibility="collapsed",
                )
            with col_ad_quitar:
                st.button(
                    "Quitar", key=f"quitarad_{uid}", icon=":material/close:", type="tertiary",
                    on_click=quitar_fila_adicional, args=(uid,),
                )
    st.button(
        "Añadir adicional", key="btn_add_adicional", icon=":material/add:",
        on_click=agregar_fila_adicional, width="stretch",
    )

    st.subheader("Logo del Negocio")
    logo_actual = empresa.get("logo_path", "")
    if logo_actual and os.path.exists(logo_actual):
        st.image(logo_actual, width=140, caption="Logo actual")
    logo_nuevo = st.file_uploader("Subir logo (PNG o JPG)", type=["png", "jpg", "jpeg"])

    if st.button("Guardar cambios", type="primary", width="stretch"):
        empresa["nombre"] = nombre_emp.strip()
        empresa["email"] = email_emp.strip()
        empresa["web"] = web_emp.strip()
        empresa["zona"] = zona_emp.strip()
        empresa["whatsapp"] = whatsapp_emp.strip()
        empresa["validez_dias"] = validez_emp
        empresa["firma_texto"] = firma_emp.strip()

        # Se descartan las filas sin descripción; precio vacío = 0.
        adicionales_nuevos = []
        for uid in st.session_state.adicionales_ids:
            descripcion_ad = str(st.session_state.get(f"a_desc_{uid}") or "").strip()
            precio_ad = float(st.session_state.get(f"a_prec_{uid}") or 0.0)
            if descripcion_ad:
                adicionales_nuevos.append({"categoria": CATEGORIA_POR_DEFECTO, "descripcion": descripcion_ad, "precio": precio_ad})
        empresa["adicionales"] = adicionales_nuevos

        if logo_nuevo is not None:
            empresa["logo_path"] = guardar_logo(logo_nuevo)

        st.session_state.empresa = empresa
        guardar_config(empresa)
        # Se hace en la próxima pasada, porque ahora los campos ya están dibujados.
        st.session_state.recargar_adicionales_pendiente = True
        st.session_state.aviso_config = "Datos del negocio actualizados."
        st.rerun()

# ------------------------------------------------------------
# TAB 3: HISTORIAL
# ------------------------------------------------------------
with tab_historial:
    st.subheader("Historial de Presupuestos")
    historial = cargar_historial()

    if not historial:
        st.info("Todavía no hay presupuestos guardados.")
    else:
        col_busq, col_estado = st.columns([2, 1])
        with col_busq:
            busqueda = st.text_input("Buscar por nombre de cliente")
        with col_estado:
            filtro_estado = st.selectbox("Estado", ["Todos"] + ESTADOS)

        filtrados = historial
        if busqueda:
            filtrados = [p for p in filtrados if busqueda.lower().strip() in p["cliente_nombre"].lower()]
        if filtro_estado != "Todos":
            filtrados = [p for p in filtrados if p.get("estado", "Pendiente") == filtro_estado]

        filtrados = sorted(filtrados, key=lambda p: p["id"], reverse=True)

        df_export = pd.DataFrame(
            [
                {
                    "ID": p["id"],
                    "Fecha": p["fecha"],
                    "Cliente": p["cliente_nombre"],
                    "Total": p["total"],
                    "Estado": p.get("estado", "Pendiente"),
                }
                for p in historial
            ]
        )
        st.download_button(
            "Exportar historial a CSV",
            data=df_export.to_csv(index=False).encode("utf-8-sig"),
            file_name="historial_presupuestos.csv",
            mime="text/csv",
        )

        if not filtrados:
            st.warning("No se encontraron presupuestos con esos filtros.")

        for p in filtrados:
            estado_p = p.get("estado", "Pendiente")
            with st.container(border=True):
                st.markdown(
                    f'<div class="hist-titulo">N° {p["id"]:04d} — {esc(p["cliente_nombre"])}</div>'
                    f'<div class="hist-detalle">{esc(p["fecha"])} &nbsp;|&nbsp; <strong>{moneda(p["total"])}</strong>'
                    f' &nbsp; {estado_pill(estado_p)}</div>',
                    unsafe_allow_html=True,
                )

                col1, col2, col3 = st.columns(3)
                with col1:
                    nuevo_estado = st.selectbox(
                        "Estado",
                        ESTADOS,
                        index=ESTADOS.index(estado_p) if estado_p in ESTADOS else 0,
                        key=f"estado_{p['id']}",
                        label_visibility="collapsed",
                    )
                    if nuevo_estado != estado_p:
                        for item_h in historial:
                            if item_h["id"] == p["id"]:
                                item_h["estado"] = nuevo_estado
                        guardar_historial(historial)
                        st.rerun()

                with col2:
                    try:
                        pdf_bytes_hist = pdf_del_historial(p, st.session_state.empresa)
                        st.download_button(
                            "Descargar PDF",
                            data=pdf_bytes_hist,
                            file_name=f"presupuesto_{p['id']:04d}_{p['cliente_nombre'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"desc_{p['id']}",
                            width="stretch",
                        )
                    except Exception as e:
                        st.error(f"No se pudo generar el PDF: {e}")

                with col3:
                    st.button(
                        "Duplicar",
                        key=f"dup_{p['id']}",
                        on_click=duplicar_presupuesto,
                        args=(p,),
                        width="stretch",
                    )

                with st.expander("Ver conceptos"):
                    for item in p["items"]:
                        st.write(
                            f"- {item['descripcion']} — {item['cantidad']:g} x "
                            f"{dinero(item['precio_unitario'])} = {dinero(item['subtotal'])}"
                        )

                    # Desglose explícito: el Total coincide con Subtotal - Descuento + Envío.
                    # (.get con valor por defecto: sirve también para presupuestos viejos).
                    subtotal_h = p.get("subtotal", sum(i["subtotal"] for i in p["items"]))
                    descuento_pct_h = p.get("descuento_pct", 0)
                    descuento_h = p.get("descuento_monto", 0.0)
                    envio_h = p.get("envio", 0.0)

                    st.divider()
                    st.write(f"Subtotal: {dinero(subtotal_h)}")
                    st.write(f"Descuento ({descuento_pct_h:g}%): -{dinero(descuento_h)}")
                    st.write(f"Envío / Desplazamiento: {dinero(envio_h)}")
                    st.write(f"**Total: {dinero(p['total'])}**")

                    if p.get("notas"):
                        st.caption(p["notas"])

# ------------------------------------------------------------
# TAB 4: PLAN PRO (mide interés, todavía no cobra)
# ------------------------------------------------------------
with tab_pro:
    st.subheader("Plan Pro")
    st.write(
        "Hoy la app es gratis. Estamos evaluando un plan Pro y queremos saber si "
        "te interesaría antes de armarlo. **Todavía no se cobra nada.**"
    )

    col_gratis, col_pro = st.columns(2)
    with col_gratis:
        with st.container(border=True):
            st.markdown("**Gratis (hoy)**")
            st.markdown(
                "- Presupuestos en PDF\n"
                "- Historial y panel de métricas\n"
                "- Tu logo y tus datos\n"
                "- Marca \"Hecho con Presupify\" en el PDF"
            )
    with col_pro:
        with st.container(border=True):
            st.markdown("**Pro (en estudio)**")
            st.markdown(
                "- PDF sin la marca de Presupify\n"
                "- Presupuestos ilimitados\n"
                "- Cuenta con contraseña y datos guardados\n"
                "- Soporte por WhatsApp"
            )

    st.write("")
    if URL_FORMULARIO_PRO:
        st.link_button("Quiero probar el Plan Pro", URL_FORMULARIO_PRO, type="primary", width="stretch")
    else:
        st.caption("Pronto vas a poder anotarte acá.")
