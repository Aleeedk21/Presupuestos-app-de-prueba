"""
Gestor de Presupuestos - Multi Rubro
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
- En la pestaña "Panel" usamos pandas para transformar la lista de
  presupuestos (que es una lista de diccionarios) en una tabla, y
  poder agruparla y sumarla fácil con groupby(). Fijate que en la
  pestaña "Nuevo Presupuesto" hacemos ese mismo tipo de resumen a
  mano con un diccionario común (ver `resumen_por_categoria`) — es
  la misma idea, pandas simplemente lo hace más cómodo cuando hay
  muchos datos.
- CALLBACKS (on_click / on_change): son funciones que Streamlit ejecuta
  ANTES de volver a correr el script, apenas el usuario toca un botón o
  cambia un campo. Son la forma correcta de modificar el valor de otros
  campos (por ejemplo, rellenar la descripción al elegir un servicio).
  Si intentás cambiar el valor de un campo después de que ya se dibujó
  en pantalla, Streamlit da error.
"""

import http

import streamlit as st
import pandas as pd
import plotly.express as px
import json
import os
import shutil
import uuid
import base64
from datetime import date, datetime
from urllib.parse import quote
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
    page_title="Gestor de Presupuestos",
    layout="centered",
    initial_sidebar_state="collapsed",  # la barra lateral (código personal) queda como opción secundaria
)


# ============================================================
# UTILIDADES GENERALES
# ============================================================
def safe_txt(s: str) -> str:
    """Evita errores de codificación en el PDF (Helvetica solo entiende latin-1)."""
    if s is None:
        return ""
    return str(s).encode("latin-1", "replace").decode("latin-1")


def dinero(valor) -> str:
    """Formatea un monto para mostrarlo en texto Markdown.
    La barra invertida evita que Streamlit tome dos signos $ como una fórmula."""
    return f"\\$ {valor:,.2f}"


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
        "telefono": "",
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
        self.cell(0, 10, safe_txt(self.empresa.get("nombre", "")), ln=True, align="C")

        partes_info = [x for x in [
            f"Tel: {self.empresa.get('telefono', '')}" if self.empresa.get("telefono") else "",
            self.empresa.get("rubro", ""),
            self.empresa.get("zona", ""),
        ] if x]
        self.set_font("Helvetica", "", 10)
        self.set_text_color(90, 90, 90)
        self.cell(0, 6, safe_txt("   |   ".join(partes_info)), ln=True, align="C")

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
            self.cell(0, 5, safe_txt(firma), ln=True, align="C")
        texto = f"Presupuesto generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} - Página {self.page_no()}"
        self.cell(0, 5, safe_txt(texto), ln=True, align="C")
        marca = "Hecho con Presupify" + (f" - {URL_APP}" if URL_APP else "")
        self.cell(0, 5, safe_txt(marca), align="C")


def ajustar_texto(pdf, texto, ancho):
    texto = safe_txt(texto)
    if pdf.get_string_width(texto) <= ancho - 2:
        return texto
    while texto and pdf.get_string_width(texto + "...") > ancho - 2:
        texto = texto[:-1]
    return texto + "..."


def generar_pdf(presupuesto, empresa) -> bytes:
    pdf = PDFPresupuesto(empresa)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, safe_txt(f"Presupuesto N° {presupuesto['id']:04d}"), ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 6, safe_txt(f"Fecha: {presupuesto['fecha']}"), ln=True)
    pdf.cell(0, 6, safe_txt(f"Estado: {presupuesto.get('estado', 'Pendiente')}"), ln=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Datos del Cliente", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, safe_txt(f"Cliente: {presupuesto['cliente_nombre']}"), ln=True)
    pdf.cell(0, 6, safe_txt(f"Dirección: {presupuesto['cliente_direccion']}"), ln=True)
    pdf.cell(0, 6, safe_txt(f"Teléfono: {presupuesto['cliente_telefono']}"), ln=True)
    pdf.ln(4)

    col_widths = [85, 15, 38, 42]
    headers = ["Concepto", "Cant.", "P. Unit.", "Subtotal"]

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(*NAVY_RGB)
    pdf.set_text_color(255, 255, 255)
    for w, h in zip(col_widths, headers):
        pdf.cell(w, 8, h, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    fill = False
    for item in presupuesto["items"]:
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(col_widths[0], 7, ajustar_texto(pdf, item["descripcion"], col_widths[0]), border=1, fill=fill)
        pdf.cell(col_widths[1], 7, f"{item['cantidad']:g}", border=1, align="C", fill=fill)
        pdf.cell(col_widths[2], 7, f"${item['precio_unitario']:,.2f}", border=1, align="R", fill=fill)
        pdf.cell(col_widths[3], 7, f"${item['subtotal']:,.2f}", border=1, align="R", fill=fill)
        pdf.ln()
        fill = not fill

    pdf.ln(2)

    x_label = sum(col_widths[:3])
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(x_label, 7, "Subtotal", align="R")
    pdf.cell(col_widths[3], 7, f"${presupuesto['subtotal']:,.2f}", align="R", ln=True)

    if presupuesto.get("descuento_pct", 0) > 0:
        pdf.cell(x_label, 7, safe_txt(f"Descuento ({presupuesto['descuento_pct']:g}%)"), align="R")
        pdf.cell(col_widths[3], 7, f"-${presupuesto['descuento_monto']:,.2f}", align="R", ln=True)

    if presupuesto.get("envio", 0) > 0:
        pdf.cell(x_label, 7, safe_txt("Envío / Desplazamiento"), align="R")
        pdf.cell(col_widths[3], 7, f"${presupuesto['envio']:,.2f}", align="R", ln=True)

    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(*NAVY_RGB)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(x_label, 9, "TOTAL", align="R", fill=True)
    pdf.cell(col_widths[3], 9, f"${presupuesto['total']:,.2f}", align="R", fill=True, ln=True)
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
        pdf.cell(0, 7, safe_txt("Notas / Condiciones"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, safe_txt(notas))

    return bytes(pdf.output())


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


def estilizar_grafico(fig):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#EAF1FB",
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
        dragmode=False,  # sin arrastre: en el celular no interfiere con el scroll
    )
    # fixedrange=True desactiva el zoom y el desplazamiento de los ejes.
    fig.update_xaxes(gridcolor="#26456F", fixedrange=True)
    fig.update_yaxes(gridcolor="#26456F", fixedrange=True)
    return fig


def kpi_card(label, value, color_class):
    # Todo en una sola línea: si el HTML queda indentado dentro de un
    # string multilínea, Streamlit lo puede interpretar como bloque de
    # código en vez de HTML real.
    return f'<div class="kpi-card {color_class}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>'


# ============================================================
# CALLBACKS (se ejecutan ANTES de redibujar la pantalla)
# ============================================================
def reiniciar_campos_item():
    """Deja el formulario de ítem en blanco, con la primera categoría del rubro."""
    categorias = config_del_rubro(st.session_state.empresa.get("rubro"))["categorias"]
    st.session_state.servicio_sel = OPCION_PERSONALIZADO
    st.session_state.item_categoria = categorias[0]
    st.session_state.item_descripcion = ""
    st.session_state.item_cantidad = 1
    st.session_state.item_precio = 0.0


def al_cambiar_rubro():
    """Guarda el rubro elegido arriba de todo y limpia el formulario de ítem
    (las categorías y servicios cambian con el rubro)."""
    st.session_state.empresa["rubro"] = st.session_state.rubro_selector
    guardar_config(st.session_state.empresa)
    reiniciar_campos_item()


def al_elegir_servicio():
    """Al elegir un servicio predefinido, rellena categoría, descripción y
    precio. Con 'Personalizado...' deja descripción y precio en blanco."""
    seleccion = st.session_state.servicio_sel
    servicios = config_del_rubro(st.session_state.empresa.get("rubro"))["servicios"]
    servicio = next((s for s in servicios if s["descripcion"] == seleccion), None)

    if servicio is None:
        st.session_state.item_descripcion = ""
        st.session_state.item_precio = 0.0
        return

    st.session_state.item_categoria = servicio["categoria"]
    st.session_state.item_descripcion = servicio["descripcion"]
    st.session_state.item_precio = float(servicio["precio"])


def agregar_item():
    """Valida el formulario y agrega el ítem a la lista. Los avisos se
    guardan en session_state y se muestran debajo del botón."""
    descripcion = st.session_state.item_descripcion.strip()
    cantidad = st.session_state.item_cantidad
    precio = st.session_state.item_precio

    if not descripcion:
        st.session_state.aviso_item = ("error", "La descripción no puede estar vacía.")
        return
    if precio <= 0:
        st.session_state.aviso_item = ("error", "El precio unitario debe ser mayor a 0.")
        return

    st.session_state.lista_items.append(
        {
            "categoria": st.session_state.item_categoria,
            "descripcion": descripcion,
            "cantidad": cantidad,
            "precio_unitario": precio,
            "subtotal": cantidad * precio,
        }
    )
    st.session_state.reset_counter += 1  # refresca la tabla editable
    reiniciar_campos_item()
    st.session_state.aviso_item = ("ok", "Ítem agregado.")


def agregar_adicional(adicional):
    """Agrega con un clic uno de los adicionales rápidos."""
    st.session_state.lista_items.append(
        {
            "categoria": adicional.get("categoria", "Otro"),
            "descripcion": adicional["descripcion"],
            "cantidad": 1,
            "precio_unitario": float(adicional["precio"]),
            "subtotal": float(adicional["precio"]),
        }
    )
    st.session_state.reset_counter += 1


def duplicar_presupuesto(presupuesto):
    """Copia cliente e ítems de un presupuesto viejo al formulario nuevo."""
    st.session_state.cliente_nombre_input = presupuesto["cliente_nombre"]
    st.session_state.cliente_direccion_input = presupuesto.get("cliente_direccion", "")
    st.session_state.cliente_telefono_input = presupuesto.get("cliente_telefono", "")
    st.session_state.lista_items = [dict(item) for item in presupuesto["items"]]
    st.session_state.reset_counter += 1
    st.toast('Datos copiados. Andá a la pestaña "Nuevo Presupuesto".')


def limpiar_items():
    """Borra todos los ítems cargados (por si se cargaron de más)."""
    st.session_state.lista_items = []
    st.session_state.reset_counter += 1
    st.session_state.aviso_item = ("info", "Lista de ítems vaciada.")


def eliminar_filas_vacias():
    """Elimina las filas sin descripción (o sin precio/cantidad útiles) para
    limpiar las casillas que el usuario agregó sin querer."""
    antes = len(st.session_state.lista_items)
    st.session_state.lista_items = [
        it for it in st.session_state.lista_items
        if str(it.get("descripcion", "")).strip()
        and float(it.get("precio_unitario", 0) or 0) > 0
    ]
    st.session_state.reset_counter += 1
    eliminadas = antes - len(st.session_state.lista_items)
    if eliminadas > 0:
        st.session_state.aviso_item = ("ok", f"Se eliminaron {eliminadas} fila(s) vacía(s).")
    else:
        st.session_state.aviso_item = ("info", "No había filas vacías para borrar.")


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
    for clave in ("empresa", "pdf_actual", "pdf_actual_info", "pdf_actual_nombre", "rubro_selector"):
        st.session_state.pop(clave, None)
    st.session_state.lista_items = []
    st.session_state.reset_counter += 1
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
if "lista_items" not in st.session_state:
    st.session_state.lista_items = []

if "empresa" not in st.session_state:
    st.session_state.empresa = cargar_config()

if "pdf_actual" not in st.session_state:
    st.session_state.pdf_actual = None

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

# Valores iniciales de los campos del formulario de ítem
st.session_state.setdefault("servicio_sel", OPCION_PERSONALIZADO)
st.session_state.setdefault("item_descripcion", "")
st.session_state.setdefault("item_cantidad", 1)
st.session_state.setdefault("item_precio", 0.0)


# ============================================================
# ESTILOS (paleta azul marino / blanco, sin emojis, más profundidad)
# ============================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

    :root {
        --navy: #0B2545;
        --navy-light: #163A6B;
        --accent: #2F6FD6;
        --accent-hover: #4C8CF0;
        --text-light: #EAF1FB;
        --border: #26456F;
        --green: #1FA97A;
        --orange: #E0972B;
        --red: #D1445C;
    }
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    h1, h2, h3, h4 { color: var(--text-light) !important; }

    div.stButton > button, div.stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {
        background-color: var(--accent);
        color: #FFFFFF !important;
        border-radius: 10px;
        border: none;
        padding: 0.55em 1.2em;
        font-weight: 600;
        transition: transform 0.05s ease-in;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: var(--accent-hover);
        color: #FFFFFF !important;
    }
    div.stButton > button:active { transform: scale(0.98); }

    [data-testid="stMetric"] {
        background-color: var(--navy-light);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 10px 16px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.25);
    }
    [data-testid="stMetricValue"] { color: var(--text-light) !important; }
    [data-testid="stMetricLabel"] { color: var(--text-light) !important; }

    div[data-testid="stExpander"], div[data-testid="stForm"] {
        border-radius: 12px;
        border: 1px solid var(--border);
        background-color: var(--navy-light);
    }

    /* Campos de texto, número, lista desplegable y fecha con borde visible
       (incluye selectores para versiones nuevas y viejas de Streamlit) */
    div[data-baseweb="input"],
    div[data-baseweb="textarea"],
    div[data-baseweb="select"] > div,
    [data-testid="stTextInputRootElement"],
    [data-testid="stNumberInputContainer"],
    [data-testid="stTextAreaRootElement"],
    [data-testid="stDateInputField"],
    [data-testid="stSelectbox"] div[role="group"] {
        border: 1.5px solid #5B82BE !important;
        border-radius: 10px !important;
        background-color: rgba(11, 37, 69, 0.6) !important;
        box-shadow: inset 0 1px 2px rgba(0,0,0,0.18);
        min-height: 44px;
    }
    /* Texto dentro de los inputs: padding y color legible */
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stNumberInputContainer"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    [data-testid="stDateInputField"] input {
        color: var(--text-light) !important;
        padding: 8px 12px !important;
        font-size: 0.95rem !important;
        font-family: 'Inter', sans-serif !important;
    }
    /* Placeholder más suave */
    div[data-baseweb="input"] input::placeholder,
    div[data-baseweb="textarea"] textarea::placeholder,
    [data-testid="stTextInputRootElement"] input::placeholder,
    [data-testid="stTextAreaRootElement"] textarea::placeholder {
        color: #89A7CC !important;
        opacity: 0.85;
    }
    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="textarea"]:focus-within,
    div[data-baseweb="select"] > div:focus-within,
    [data-testid="stTextInputRootElement"]:focus-within,
    [data-testid="stNumberInputContainer"]:focus-within,
    [data-testid="stTextAreaRootElement"]:focus-within,
    [data-testid="stDateInputField"]:focus-within,
    [data-testid="stSelectbox"] div[role="group"]:focus-within {
        border-color: var(--accent-hover) !important;
        box-shadow: 0 0 0 2px rgba(76, 140, 240, 0.22), inset 0 1px 2px rgba(0,0,0,0.18) !important;
    }

    /* Pestañas (tabs): estilo más limpio, tipo tarjeta */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background-color: rgba(11, 37, 69, 0.5);
        padding: 6px;
        border-radius: 14px;
        border: 1px solid var(--border);
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 10px 16px !important;
        color: #A7C2E6 !important;
        font-weight: 500;
        font-family: 'Inter', sans-serif !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: rgba(47, 111, 214, 0.18) !important;
        color: #FFFFFF !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: var(--accent) !important;
        color: #FFFFFF !important;
        font-weight: 600;
        box-shadow: 0 3px 8px rgba(47, 111, 214, 0.4);
    }

    /* Containers con borde: suaves y con sombra */
    div[data-testid="stVerticalBlockBorderWrapper"] > div,
    div[data-testid="stContainer"] [data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 14px !important;
        border: 1px solid var(--border) !important;
        background-color: rgba(22, 58, 107, 0.35) !important;
        box-shadow: 0 3px 10px rgba(0,0,0,0.2);
    }

    .header-banner {
        background: linear-gradient(135deg, var(--navy-light), var(--accent));
        padding: 22px 16px;
        border-radius: 16px;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 0 6px 16px rgba(0,0,0,0.3);
    }
    .header-banner img { max-height: 60px; margin-bottom: 6px; }
    .header-banner h1 { color: #FFFFFF !important; margin: 0; font-size: 1.6rem; }
    .header-banner p { color: #D7E0EC !important; margin: 4px 0 0 0; font-size: 0.9rem; }

    .wa-button {
        display: inline-block;
        width: 100%;
        box-sizing: border-box;
        text-align: center;
        background-color: var(--accent);
        color: #FFFFFF !important;
        border-radius: 10px;
        padding: 0.55em 1.2em;
        font-weight: 600;
        text-decoration: none;
        margin-top: 8px;
    }
    .wa-button:hover { background-color: var(--accent-hover); }

    /* Tarjetas de resumen estilo "Money Manager" */
    .kpi-row {
        display: flex;
        gap: 12px;
        overflow-x: auto;
        padding-bottom: 6px;
        margin-bottom: 8px;
    }
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        margin-bottom: 8px;
    }
    @media (max-width: 600px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .kpi-card .kpi-value { font-size: 1.1rem; }
    }
    .kpi-card {
        flex: 1 1 140px;
        min-width: 140px;
        border-radius: 16px;
        padding: 16px;
        color: #FFFFFF;
        box-shadow: 0 6px 14px rgba(0,0,0,0.3);
    }
    .kpi-grid .kpi-card {
        flex: unset;
        min-width: 0;
    }
    .kpi-card .kpi-label { font-size: 0.75rem; opacity: 0.9; }
    .kpi-card .kpi-value {
        font-size: 1.35rem;
        font-weight: 700;
        margin-top: 4px;
        word-break: break-word;
        overflow-wrap: break-word;
    }
    .kpi-blue { background: linear-gradient(135deg, var(--navy-light), var(--accent)); }
    .kpi-green { background: linear-gradient(135deg, #0F6A4C, var(--green)); }
    .kpi-orange { background: linear-gradient(135deg, #8A5A12, var(--orange)); }
    .kpi-red { background: linear-gradient(135deg, #7A1F2B, var(--red)); }

    /* Chips de resumen por categoría */
    .chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 4px 0; }
    .chip {
        background: var(--navy-light);
        border: 1px solid var(--border);
        color: var(--text-light);
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.78rem;
    }

    /* ===== Tablas: st.data_editor y st.dataframe (estilo "no-Excel", más prolijo) ===== */
    [data-testid="stDataEditor"],
    [data-testid="stDataFrame"] {
        border: 1.5px solid var(--border) !important;
        border-radius: 14px !important;
        background-color: var(--navy-light) !important;
        padding: 4px 4px 6px 4px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.22);
        overflow: hidden;
    }
    /* Encabezados (fila superior) */
    [data-testid="stDataEditor"] [data-testid="stTableStyledTableHeader"],
    [data-testid="stDataFrame"] [data-testid="stTableStyledTableHeader"],
    [data-testid="stDataEditor"] .glideDataEditor .dvn-scroller .gde-header,
    [data-testid="stDataFrame"] .glideDataEditor .dvn-scroller .gde-header {
        background: linear-gradient(180deg, #1F4A83, #12335E) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        font-size: 0.95rem !important;
        border-bottom: 2px solid var(--accent) !important;
    }
    /* Celdas: altura, padding y bordes suaves */
    [data-testid="stDataEditor"] .glideDataEditor .dvn-scroller,
    [data-testid="stDataFrame"] .glideDataEditor .dvn-scroller,
    [data-testid="stDataEditor"] [data-testid="stTableStyledTableCellContent"],
    [data-testid="stDataFrame"] [data-testid="stTableStyledTableCellContent"] {
        font-family: 'Inter', sans-serif !important;
        font-size: 0.92rem !important;
    }
    /* Filas alternadas para no perder de vista la línea */
    [data-testid="stDataEditor"] .gdt-Row:nth-child(even),
    [data-testid="stDataFrame"] .gdt-Row:nth-child(even) {
        background-color: rgba(47, 111, 214, 0.08) !important;
    }
    [data-testid="stDataEditor"] .gdt-Row:hover,
    [data-testid="stDataFrame"] .gdt-Row:hover {
        background-color: rgba(76, 140, 240, 0.14) !important;
    }
    /* Bordes interiores entre celdas */
    [data-testid="stDataEditor"] .gdt-Cell,
    [data-testid="stDataFrame"] .gdt-Cell {
        border-bottom: 1px solid rgba(88, 124, 173, 0.35) !important;
        border-right: 1px solid rgba(88, 124, 173, 0.25) !important;
        padding: 6px 10px !important;
        min-height: 44px !important;
    }
    /* Celda seleccionada (borde azul fuerte y claro) */
    [data-testid="stDataEditor"] .gdt-Cell[aria-selected="true"],
    [data-testid="stDataFrame"] .gdt-Cell[aria-selected="true"],
    [data-testid="stDataEditor"] .gde-selected,
    [data-testid="stDataFrame"] .gde-selected {
        outline: 2px solid var(--accent-hover) !important;
        outline-offset: -2px;
        background-color: rgba(47, 111, 214, 0.18) !important;
        border-radius: 4px;
    }
    /* Inputs DENTRO de la tabla cuando estás editando */
    [data-testid="stDataEditor"] input,
    [data-testid="stDataEditor"] textarea,
    [data-testid="stDataEditor"] select {
        border-radius: 8px !important;
        padding: 6px 10px !important;
    }
    /* Scrollbar más limpio dentro de tablas */
    [data-testid="stDataEditor"] .dvn-scroll-inner::-webkit-scrollbar,
    [data-testid="stDataFrame"] .dvn-scroll-inner::-webkit-scrollbar {
        width: 10px;
        height: 10px;
    }
    [data-testid="stDataEditor"] .dvn-scroll-inner::-webkit-scrollbar-thumb,
    [data-testid="stDataFrame"] .dvn-scroll-inner::-webkit-scrollbar-thumb {
        background: #2A5A9A;
        border-radius: 999px;
    }
    [data-testid="stDataEditor"] .dvn-scroll-inner::-webkit-scrollbar-track,
    [data-testid="stDataFrame"] .dvn-scroll-inner::-webkit-scrollbar-track {
        background: rgba(11, 37, 69, 0.6);
    }
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
    nombre = empresa.get("nombre", "")
    subtitulo = subtitulo_empresa(empresa)
    banner_html = f'<div class="header-banner">{logo_html}<h1>{nombre}</h1><p>{subtitulo}</p></div>'
    st.markdown(banner_html, unsafe_allow_html=True)


mostrar_banner()

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

    # Si la categoría guardada ya no pertenece al rubro, vuelve a la primera.
    if st.session_state.get("item_categoria") not in categorias_actuales:
        st.session_state.item_categoria = categorias_actuales[0]

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
    st.subheader("Detalle del Trabajo")

    # Al elegir un servicio, al_elegir_servicio() rellena los campos de abajo.
    opciones_serv = [OPCION_PERSONALIZADO] + [s["descripcion"] for s in servicios_actuales]
    if st.session_state.servicio_sel not in opciones_serv:
        st.session_state.servicio_sel = OPCION_PERSONALIZADO
    st.selectbox(
        "Servicio predefinido (opcional)",
        opciones_serv,
        key="servicio_sel",
        on_change=al_elegir_servicio,
    )

    st.selectbox("Categoría", categorias_actuales, key="item_categoria")
    st.text_input("Descripción del concepto", key="item_descripcion", max_chars=80)
    col1, col2 = st.columns(2)
    with col1:
        st.number_input("Cantidad", min_value=1, max_value=50, step=1, key="item_cantidad")
    with col2:
        st.number_input(
            "Precio unitario ($)",
            min_value=0.0,
            max_value=100000000.0,
            step=100.0,
            format="%.2f",
            key="item_precio",
        )
    st.button("Agregar ítem", on_click=agregar_item, width="stretch")

    aviso_item = st.session_state.pop("aviso_item", None)
    if aviso_item:
        tipo, texto = aviso_item
        (st.success if tipo == "ok" else st.error)(texto)

    # --- Adicionales rápidos (se editan en "Configuración del Negocio") ---
    st.caption("Adicionales rápidos")
    adicionales = st.session_state.empresa.get("adicionales", [])
    if adicionales:
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
        st.caption('No hay adicionales cargados. Podés crearlos en "Configuración del Negocio".')

    # --- Tabla editable de ítems ---
    st.write("Ítems del presupuesto (editable directamente en la tabla)")
    columnas_items = ["categoria", "descripcion", "cantidad", "precio_unitario", "subtotal"]
    if st.session_state.lista_items:
        df_items_edit = pd.DataFrame(st.session_state.lista_items)[columnas_items]
    else:
        df_items_edit = pd.DataFrame(columns=columnas_items)

    # Si hay ítems de otro rubro (ej: se cambió el rubro a mitad de presupuesto),
    # sus categorías se suman a las opciones para que la tabla no las pierda.
    categorias_en_uso = {i["categoria"] for i in st.session_state.lista_items}
    opciones_categoria = categorias_actuales + sorted(c for c in categorias_en_uso if c not in categorias_actuales)

    # Anchos fijos adaptados: descripción y categoría con más espacio,
    # cantidad angosta, precios con ancho suficiente para no cortar.
    edited_df = st.data_editor(
        df_items_edit,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"editor_items_{st.session_state.reset_counter}",
        column_config={
            "categoria": st.column_config.SelectboxColumn(
                "Categoría", options=opciones_categoria, width="medium", required=True,
            ),
            "descripcion": st.column_config.TextColumn(
                "Descripción", width="large", required=True, max_chars=100,
            ),
            "cantidad": st.column_config.NumberColumn(
                "Cant.", min_value=1, step=1, width="small", required=True,
            ),
            "precio_unitario": st.column_config.NumberColumn(
                "P. Unitario ($)", min_value=0.0, format="$ %.2f", width="medium", required=True,
            ),
            "subtotal": st.column_config.NumberColumn(
                "Subtotal", format="$ %.2f", disabled=True, width="medium",
            ),
        },
    )

    # Se completan los vacíos (filas nuevas) y se recalcula el subtotal.
    edited_df["cantidad"] = pd.to_numeric(edited_df["cantidad"], errors="coerce").fillna(1).clip(lower=1).astype(int)
    edited_df["precio_unitario"] = pd.to_numeric(edited_df["precio_unitario"], errors="coerce").fillna(0.0)
    edited_df["subtotal"] = edited_df["cantidad"] * edited_df["precio_unitario"]
    edited_df["categoria"] = edited_df["categoria"].fillna(categorias_actuales[0]).replace({"None": categorias_actuales[0], None: categorias_actuales[0]})
    edited_df["descripcion"] = edited_df["descripcion"].fillna("").replace({"None": "", None: ""}).astype(str)
    edited_df["descripcion"] = edited_df["descripcion"].str.strip()
    st.session_state.lista_items = edited_df.to_dict("records")

    # Botones de limpieza / eliminación de filas (por si agregaste filas sin querer)
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        st.button(
            "🧹 Quitar filas vacías",
            on_click=eliminar_filas_vacias,
            width="stretch",
            help="Elimina las filas que tienen descripción vacía o precio 0.",
            disabled=not st.session_state.lista_items,
        )
    with col_btn2:
        st.button(
            "🗑️ Limpiar todos los ítems",
            on_click=limpiar_items,
            width="stretch",
            help="Borra TODOS los ítems de la lista (no se puede deshacer).",
            disabled=not st.session_state.lista_items,
        )
    st.caption(
        "Tip: en la tabla también podés seleccionar una fila y apretar la tecla Supr/Delete "
        "para borrarla directamente."
    )

    # Resumen por categoría hecho "a mano" con un diccionario común.
    # (En la pestaña Panel hacemos lo mismo con pandas groupby, que
    # conviene cuando hay muchos datos acumulados en el historial).
    if st.session_state.lista_items:
        resumen_por_categoria = {}
        for it in st.session_state.lista_items:
            resumen_por_categoria[it["categoria"]] = resumen_por_categoria.get(it["categoria"], 0) + it["subtotal"]

        chips_html = "".join(
            f'<span class="chip">{cat}: $ {monto:,.0f}</span>'
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

    subtotal = sum(i["subtotal"] for i in st.session_state.lista_items)
    descuento_monto = subtotal * (descuento_pct / 100)
    total = subtotal - descuento_monto + envio

    st.divider()
    metrics_html = (
        '<div class="kpi-grid">'
        + kpi_card("Subtotal", f"$ {subtotal:,.2f}", "kpi-blue")
        + kpi_card("Descuento", f"$ {descuento_monto:,.2f}", "kpi-orange")
        + kpi_card("Envío", f"$ {envio:,.2f}", "kpi-green")
        + kpi_card("Total Cotizado", f"$ {total:,.2f}", "kpi-red")
        + "</div>"
    )
    st.markdown(metrics_html, unsafe_allow_html=True)

    st.divider()

    if st.button("Generar PDF", type="primary", width="stretch"):
        errores = []
        if not cliente_nombre.strip():
            errores.append("Falta el nombre del cliente.")
        if not st.session_state.lista_items:
            errores.append("Agregá al menos un ítem al presupuesto.")
        elif any(not str(i["descripcion"]).strip() for i in st.session_state.lista_items):
            errores.append("Hay ítems sin descripción: completalos o borrá esas filas.")

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
                    "descripcion": str(i["descripcion"]).strip(),
                    "cantidad": int(i["cantidad"]),
                    "precio_unitario": float(i["precio_unitario"]),
                    "subtotal": float(i["subtotal"]),
                }
                for i in st.session_state.lista_items
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
                st.session_state.lista_items = []
                st.session_state.reset_counter += 1
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

        telefono_cliente_wa = limpiar_telefono(st.session_state.get("pdf_actual_info", {}).get("cliente_telefono", ""))
        if telefono_cliente_wa:
            mensaje = (
                f"Hola {info['cliente']}, te comparto el presupuesto N° {info['id']:04d} "
                f"por un total de $ {info['total']:,.2f}. Cualquier consulta quedo a disposición."
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
            + kpi_card("Total cotizado histórico", f"$ {total_historico:,.0f}", "kpi-blue")
            + kpi_card("Cotizado este mes", f"$ {total_mes:,.0f}", "kpi-green")
            + kpi_card("Pendientes", str(cantidad_pendientes), "kpi-orange")
            + kpi_card("Aprobados", str(cantidad_aprobados), "kpi-green")
            + "</div>"
        )
        st.markdown(cards_html, unsafe_allow_html=True)

        st.write("")
        st.subheader("Presupuestado por mes")
        df_mensual = df_hist.groupby("mes", as_index=False)["total"].sum().sort_values("mes")
        fig_mensual = px.bar(df_mensual, x="mes", y="total", labels={"mes": "Mes", "total": "Total presupuestado"})
        fig_mensual.update_traces(marker_color="#2F6FD6")
        fig_mensual.update_xaxes(type="category")
        st.plotly_chart(estilizar_grafico(fig_mensual), width="stretch", config=CONFIG_PLOTLY)

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
                st.plotly_chart(estilizar_grafico(fig_categoria), width="stretch", config=CONFIG_PLOTLY)

        st.subheader("Top clientes")
        df_top_clientes = (
            df_hist.groupby("cliente", as_index=False)["total"]
            .sum()
            .sort_values("total", ascending=False)
            .head(5)
            .rename(columns={"cliente": "Cliente", "total": "Total presupuestado"})
        )
        st.dataframe(df_top_clientes, width="stretch", hide_index=True)

# ------------------------------------------------------------
# TAB 2: CONFIGURACIÓN DEL NEGOCIO
# ------------------------------------------------------------
with tab_config:
    st.subheader("Datos del Negocio")
    empresa = st.session_state.empresa

    nombre_emp = st.text_input("Nombre / Marca", value=empresa.get("nombre", ""))
    st.caption('El rubro se elige arriba de todo, en la pestaña "Nuevo Presupuesto".')

    col1, col2 = st.columns(2)
    with col1:
        telefono_emp = st.text_input("Teléfono", value=empresa.get("telefono", ""))
    with col2:
        zona_emp = st.text_input("Zona de cobertura", value=empresa.get("zona", ""))

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
        "Editá las celdas, agregá filas al final o borrá las que no uses."
    )
    adicionales_guardados = empresa.get("adicionales", ADICIONALES_RAPIDOS_GENERICOS)
    df_adicionales = pd.DataFrame(
        [{"descripcion": a["descripcion"], "precio": float(a["precio"])} for a in adicionales_guardados],
        columns=["descripcion", "precio"],
    )
    adicionales_editados = st.data_editor(
        df_adicionales,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"editor_adicionales_{st.session_state.reset_counter}",
        column_config={
            "descripcion": st.column_config.TextColumn(
                "Descripción", max_chars=80, width="large", required=True,
            ),
            "precio": st.column_config.NumberColumn(
                "Precio ($)", min_value=0.0, format="$ %.2f", width="medium", required=True,
            ),
        },
    )

    st.subheader("Logo del Negocio")
    logo_actual = empresa.get("logo_path", "")
    if logo_actual and os.path.exists(logo_actual):
        st.image(logo_actual, width=140, caption="Logo actual")
    logo_nuevo = st.file_uploader("Subir logo (PNG o JPG)", type=["png", "jpg", "jpeg"])

    if st.button("Guardar cambios", type="primary", width="stretch"):
        empresa["nombre"] = nombre_emp.strip()
        empresa["telefono"] = telefono_emp.strip()
        empresa["zona"] = zona_emp.strip()
        empresa["whatsapp"] = whatsapp_emp.strip()
        empresa["validez_dias"] = validez_emp
        empresa["firma_texto"] = firma_emp.strip()

        # Se descartan las filas sin descripción; precio vacío = 0.
        adicionales_nuevos = []
        for _, fila in adicionales_editados.iterrows():
            descripcion_ad = str(fila["descripcion"]).strip() if pd.notna(fila["descripcion"]) else ""
            precio_ad = float(fila["precio"]) if pd.notna(fila["precio"]) else 0.0
            if descripcion_ad:
                adicionales_nuevos.append({"categoria": "Otro", "descripcion": descripcion_ad, "precio": precio_ad})
        empresa["adicionales"] = adicionales_nuevos

        if logo_nuevo is not None:
            empresa["logo_path"] = guardar_logo(logo_nuevo)

        st.session_state.empresa = empresa
        guardar_config(empresa)
        st.session_state.reset_counter += 1  # refresca las tablas editables
        st.success("Datos del negocio actualizados.")
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
            with st.container(border=True):
                st.write(f"N° {p['id']:04d} — {p['cliente_nombre']}")
                st.write(f"{p['fecha']}  |  {dinero(p['total'])}  |  {p.get('estado', 'Pendiente')}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    nuevo_estado = st.selectbox(
                        "Estado",
                        ESTADOS,
                        index=ESTADOS.index(p.get("estado", "Pendiente")),
                        key=f"estado_{p['id']}",
                        label_visibility="collapsed",
                    )
                    if nuevo_estado != p.get("estado", "Pendiente"):
                        for item_h in historial:
                            if item_h["id"] == p["id"]:
                                item_h["estado"] = nuevo_estado
                        guardar_historial(historial)
                        st.rerun()

                with col2:
                    try:
                        pdf_bytes_hist = generar_pdf(p, st.session_state.empresa)
                        st.download_button(
                            "Descargar PDF",
                            data=pdf_bytes_hist,
                            file_name=f"presupuesto_{p['id']:04d}_{p['cliente_nombre'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"desc_{p['id']}",
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

                with st.expander("Ver ítems"):
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
