"""
Gestor de Presupuestos - Multi Rubro
--------------------------------------------------------------
Pensada para cualquier oficio (aire acondicionado, electricidad,
plomería, albañilería, pintura, gasista, etc.), no solo climatización.

Ejecutar con:
    streamlit run app.py

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
"""

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px
import json
import os
import base64
from datetime import date, datetime
from urllib.parse import quote
from fpdf import FPDF

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
os.makedirs("datos", exist_ok=True)

def archivo_historial():
    return f"datos/historial_{st.session_state.codigo}.json"

def archivo_config():
    return f"datos/config_{st.session_state.codigo}.json"

NAVY_RGB = (11, 37, 69)
PALETA_GRAFICOS = ["#2F6FD6", "#1FA97A", "#E0972B", "#D1445C", "#8E6FD6", "#3FB6C9"]

ESTADOS = ["Pendiente", "Aprobado", "Rechazado", "Completado"]

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

# Adicionales rápidos: son genéricos para que sirvan en cualquier rubro
# (por eso usan la categoría "Otro", presente en todos los rubros de arriba).
ADICIONALES_RAPIDOS_GENERICOS = [
    {"categoria": "Otro", "descripcion": "Mano de obra adicional", "precio": 10000.0},
    {"categoria": "Otro", "descripcion": "Materiales extra", "precio": 6000.0},
    {"categoria": "Otro", "descripcion": "Traslado / zona alejada", "precio": 8000.0},
]

st.set_page_config(page_title="Gestor de Presupuestos", layout="centered")
codigo = st.text_input("Tu código personal (inventá uno, ej: juan2026)")
codigo = "".join(c for c in codigo if c.isalnum()).lower()
if len(codigo) < 4:
    st.info("Escribí un código de al menos 4 letras o números para empezar.")
    st.stop()
st.session_state.codigo = codigo


# ============================================================
# UTILIDADES DE TEXTO (evita errores de codificación en el PDF)
# ============================================================
def safe_txt(s: str) -> str:
    if s is None:
        return ""
    return str(s).encode("latin-1", "replace").decode("latin-1")


# ============================================================
# PERSISTENCIA - HISTORIAL DE PRESUPUESTOS
# ============================================================
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
    if not historial:
        return 1
    return max(p["id"] for p in historial) + 1


# ============================================================
# PERSISTENCIA - CONFIGURACIÓN DE LA EMPRESA
# ============================================================
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


# ============================================================
# GENERACIÓN DE PDF
# ============================================================
class PDFPresupuesto(FPDF):
    def __init__(self, empresa):
        super().__init__()
        self.empresa = empresa

    def header(self):
        logo_path = self.empresa.get("logo_path", "")
        if logo_path and os.path.exists(logo_path):
            try:
                self.image(logo_path, x=10, y=8, w=24)
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
        self.set_y(-20)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        firma = self.empresa.get("firma_texto", "")
        if firma:
            self.cell(0, 5, safe_txt(firma), ln=True, align="C")
        texto = f"Presupuesto generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} - Página {self.page_no()}"
        self.cell(0, 5, safe_txt(texto), ln=True, align="C")
        self.cell(0, 5, "Hecho con Paperlit - https://presupuestosclima.streamlit.app/", align="C")


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

    col_widths = [90, 20, 35, 35]
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
        pdf.cell(col_widths[0], 7, safe_txt(item["descripcion"])[:55], border=1, fill=fill)
        pdf.cell(col_widths[1], 7, str(item["cantidad"]), border=1, align="C", fill=fill)
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
        pdf.cell(x_label, 7, safe_txt(f"Descuento ({presupuesto['descuento_pct']}%)"), align="R")
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

    if presupuesto.get("notas"):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, safe_txt("Notas / Condiciones"), ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, safe_txt(presupuesto["notas"]))

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
    para poder ver cuánto facturamos por categoría de servicio."""
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
    )
    fig.update_xaxes(gridcolor="#26456F")
    fig.update_yaxes(gridcolor="#26456F")
    return fig


def kpi_card(label, value, color_class):
    # Todo en una sola línea: si el HTML queda indentado dentro de un
    # string multilínea, Streamlit lo puede interpretar como bloque de
    # código en vez de HTML real.
    return f'<div class="kpi-card {color_class}"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>'


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
    .kpi-card {
        flex: 1 1 140px;
        min-width: 140px;
        border-radius: 16px;
        padding: 16px;
        color: #FFFFFF;
        box-shadow: 0 6px 14px rgba(0,0,0,0.3);
    }
    .kpi-card .kpi-label { font-size: 0.75rem; opacity: 0.9; }
    .kpi-card .kpi-value { font-size: 1.35rem; font-weight: 700; margin-top: 4px; }
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
    </style>
    """,
    unsafe_allow_html=True,
)

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


def mostrar_banner():
    empresa = st.session_state.empresa
    logo_uri = logo_base64_uri(empresa.get("logo_path", ""))
    logo_html = f'<img src="{logo_uri}" />' if logo_uri else ""
    nombre = empresa.get("nombre", "")
    subtitulo = subtitulo_empresa(empresa)
    banner_html = f'<div class="header-banner">{logo_html}<h1>{nombre}</h1><p>{subtitulo}</p></div>'
    st.markdown(banner_html, unsafe_allow_html=True)


mostrar_banner()

tab_panel, tab_nuevo, tab_personalizar, tab_historial = st.tabs(
    ["Panel", "Nuevo Presupuesto", "Personalizar Factura", "Historial"]
)

# ------------------------------------------------------------
# TAB 0: PANEL (dashboard con pandas + plotly)
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
            + kpi_card("Facturado histórico", f"$ {total_historico:,.0f}", "kpi-blue")
            + kpi_card("Facturado este mes", f"$ {total_mes:,.0f}", "kpi-green")
            + kpi_card("Pendientes", str(cantidad_pendientes), "kpi-orange")
            + kpi_card("Aprobados", str(cantidad_aprobados), "kpi-green")
            + "</div>"
        )
        st.markdown(cards_html, unsafe_allow_html=True)

        st.write("")
        st.subheader("Facturación por mes")
        df_mensual = df_hist.groupby("mes", as_index=False)["total"].sum().sort_values("mes")
        fig_mensual = px.bar(df_mensual, x="mes", y="total", labels={"mes": "Mes", "total": "Total facturado"})
        fig_mensual.update_traces(marker_color="#2F6FD6")
        st.plotly_chart(estilizar_grafico(fig_mensual), use_container_width=True)

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("Por estado")
            df_estado = df_hist.groupby("estado", as_index=False).size().rename(columns={"size": "cantidad"})
            fig_estado = px.pie(
                df_estado, names="estado", values="cantidad", hole=0.55,
                color_discrete_sequence=PALETA_GRAFICOS,
            )
            st.plotly_chart(estilizar_grafico(fig_estado), use_container_width=True)

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
                st.plotly_chart(estilizar_grafico(fig_categoria), use_container_width=True)

        st.subheader("Top clientes")
        df_top_clientes = (
            df_hist.groupby("cliente", as_index=False)["total"]
            .sum()
            .sort_values("total", ascending=False)
            .head(5)
            .rename(columns={"cliente": "Cliente", "total": "Total facturado"})
        )
        st.dataframe(df_top_clientes, use_container_width=True, hide_index=True)

# ------------------------------------------------------------
# TAB 1: NUEVO PRESUPUESTO
# ------------------------------------------------------------
with tab_nuevo:
    rubro_actual = st.session_state.empresa.get("rubro", "Aire Acondicionado")
    config_rubro = RUBROS.get(rubro_actual, RUBROS["Otro / Personalizado"])
    categorias_actuales = config_rubro["categorias"]
    servicios_actuales = config_rubro["servicios"]

    st.caption(f"Rubro actual: {rubro_actual} (se cambia en \"Personalizar Factura\")")

    st.subheader("Datos del Cliente")
    cliente_nombre = st.text_input("Nombre y Apellido", key="cliente_nombre_input")
    col1, col2 = st.columns(2)
    with col1:
        cliente_direccion = st.text_input("Dirección / Ubicación", key="cliente_direccion_input")
    with col2:
        cliente_telefono = st.text_input("Teléfono del cliente", key="cliente_telefono_input")
    fecha = st.date_input("Fecha", value=date.today())

    st.divider()
    st.subheader("Detalle del Trabajo")

    opciones_serv = ["Personalizado..."] + [s["descripcion"] for s in servicios_actuales]
    seleccion = st.selectbox("Servicio predefinido (opcional)", opciones_serv)
    servicio_sugerido = next((s for s in servicios_actuales if s["descripcion"] == seleccion), None)

    with st.form("form_item", clear_on_submit=True):
        categoria_default = servicio_sugerido["categoria"] if servicio_sugerido else categorias_actuales[0]
        categoria = st.selectbox("Categoría", categorias_actuales, index=categorias_actuales.index(categoria_default))
        descripcion = st.text_input(
            "Descripción del concepto",
            value=servicio_sugerido["descripcion"] if servicio_sugerido else "",
        )
        col1, col2 = st.columns(2)
        with col1:
            cantidad = st.number_input("Cantidad", min_value=1, value=1, step=1)
        with col2:
            precio_unitario = st.number_input(
                "Precio unitario ($)",
                min_value=0.0,
                value=float(servicio_sugerido["precio"]) if servicio_sugerido else 0.0,
                step=100.0,
                format="%.2f",
            )
        agregar = st.form_submit_button("Agregar ítem")

        if agregar:
            if not descripcion.strip():
                st.error("La descripción no puede estar vacía.")
            elif precio_unitario <= 0:
                st.error("El precio unitario debe ser mayor a 0.")
            else:
                st.session_state.lista_items.append(
                    {
                        "categoria": categoria,
                        "descripcion": descripcion.strip(),
                        "cantidad": cantidad,
                        "precio_unitario": precio_unitario,
                        "subtotal": cantidad * precio_unitario,
                    }
                )
                st.success("Ítem agregado.")

    st.caption("Adicionales rápidos")
    cols_add = st.columns(len(ADICIONALES_RAPIDOS_GENERICOS))
    for c, ad in zip(cols_add, ADICIONALES_RAPIDOS_GENERICOS):
        with c:
            if st.button(ad["descripcion"], key=f"add_{ad['descripcion']}", use_container_width=True):
                st.session_state.lista_items.append(
                    {
                        "categoria": ad["categoria"],
                        "descripcion": ad["descripcion"],
                        "cantidad": 1,
                        "precio_unitario": ad["precio"],
                        "subtotal": ad["precio"],
                    }
                )
                st.rerun()

    st.write("Ítems del presupuesto (editable directamente en la tabla)")
    columnas_items = ["categoria", "descripcion", "cantidad", "precio_unitario", "subtotal"]
    if st.session_state.lista_items:
        df_items_edit = pd.DataFrame(st.session_state.lista_items)[columnas_items]
    else:
        df_items_edit = pd.DataFrame(columns=columnas_items)

    edited_df = st.data_editor(
        df_items_edit,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key=f"editor_items_{st.session_state.reset_counter}",
        column_config={
            "categoria": st.column_config.SelectboxColumn("Categoría", options=categorias_actuales),
            "descripcion": st.column_config.TextColumn("Descripción", width="large"),
            "cantidad": st.column_config.NumberColumn("Cant.", min_value=1, step=1),
            "precio_unitario": st.column_config.NumberColumn("P. Unit.", min_value=0.0, format="$ %.2f"),
            "subtotal": st.column_config.NumberColumn("Subtotal", format="$ %.2f", disabled=True),
        },
    )

    edited_df["cantidad"] = edited_df["cantidad"].fillna(1)
    edited_df["precio_unitario"] = edited_df["precio_unitario"].fillna(0.0)
    edited_df["subtotal"] = edited_df["cantidad"] * edited_df["precio_unitario"]
    edited_df["categoria"] = edited_df["categoria"].fillna(categorias_actuales[0])
    edited_df["descripcion"] = edited_df["descripcion"].fillna("")
    st.session_state.lista_items = edited_df.to_dict("records")

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
        envio = st.number_input("Envío / Desplazamiento ($)", min_value=0.0, value=0.0, step=100.0)

    st.subheader("Estado y Notas")
    estado = st.selectbox("Estado del presupuesto", ESTADOS, index=0)

    validez = st.session_state.empresa.get("validez_dias", 7)
    notas_default = (
        f"Presupuesto válido por {validez} días.\n"
        "No incluye materiales no especificados.\n"
        "Garantía del trabajo realizado: 6 meses."
    )
    notas = st.text_area("Notas / Condiciones", value=notas_default, height=100)

    subtotal = sum(i["subtotal"] for i in st.session_state.lista_items)
    descuento_monto = subtotal * (descuento_pct / 100)
    total = subtotal - descuento_monto + envio

    st.divider()
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Subtotal", f"$ {subtotal:,.2f}")
    with col2:
        st.metric("Descuento", f"$ {descuento_monto:,.2f}")
    with col3:
        st.metric("Envío", f"$ {envio:,.2f}")
    with col4:
        st.metric("Total", f"$ {total:,.2f}")

    st.divider()

    if st.button("Generar PDF", type="primary", use_container_width=True):
        errores = []
        if not cliente_nombre.strip():
            errores.append("Falta el nombre del cliente.")
        if not st.session_state.lista_items:
            errores.append("Agregá al menos un ítem al presupuesto.")

        if errores:
            for e in errores:
                st.error(e)
        else:
            historial = cargar_historial()
            nuevo_id = siguiente_id(historial)

            presupuesto = {
                "id": nuevo_id,
                "fecha": fecha.strftime("%d/%m/%Y"),
                "cliente_nombre": cliente_nombre.strip(),
                "cliente_direccion": cliente_direccion.strip(),
                "cliente_telefono": cliente_telefono.strip(),
                "items": st.session_state.lista_items,
                "subtotal": subtotal,
                "descuento_pct": descuento_pct,
                "descuento_monto": descuento_monto,
                "envio": envio,
                "total": total,
                "notas": notas.strip(),
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
                    "total": total,
                    "id": nuevo_id,
                }
                st.session_state.lista_items = []
                st.session_state.reset_counter += 1
                st.success(f"Presupuesto N° {nuevo_id:04d} generado y guardado.")

    if st.session_state.get("pdf_actual"):
        info = st.session_state.pdf_actual_info
        st.download_button(
            "Descargar PDF",
            data=st.session_state.pdf_actual,
            file_name=st.session_state.pdf_actual_nombre,
            mime="application/pdf",
            use_container_width=True,
            key="descarga_pdf_actual",
        )

        with st.expander("Vista previa del PDF"):
            b64_pdf = base64.b64encode(st.session_state.pdf_actual).decode()
            components.html(
                f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%" height="500" '
                f'style="border:none;"></iframe>',
                height=520,
            )

        telefono_wa = st.session_state.empresa.get("whatsapp", "").strip()
        if telefono_wa:
            mensaje = (
                f"Hola {info['cliente']}, te comparto el presupuesto N° {info['id']:04d} "
                f"por un total de $ {info['total']:,.2f}. Cualquier consulta quedo a disposición."
            )
            wa_url = f"https://wa.me/{telefono_wa}?text={quote(mensaje)}"
            st.markdown(
                f'<a href="{wa_url}" target="_blank" class="wa-button">Enviar aviso por WhatsApp</a>',
                unsafe_allow_html=True,
            )
        else:
            st.caption('Cargá un número de WhatsApp en "Personalizar Factura" para enviar el aviso directo.')

# ------------------------------------------------------------
# TAB 2: PERSONALIZAR FACTURA
# ------------------------------------------------------------
with tab_personalizar:
    st.subheader("Datos de la Empresa")
    empresa = st.session_state.empresa

    nombre_emp = st.text_input("Nombre / Marca", value=empresa.get("nombre", ""))

    opciones_rubro = list(RUBROS.keys())
    rubro_guardado = empresa.get("rubro", "Aire Acondicionado")
    rubro_emp = st.selectbox(
        "Rubro / Actividad",
        opciones_rubro,
        index=opciones_rubro.index(rubro_guardado) if rubro_guardado in opciones_rubro else 0,
    )

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

    st.subheader("Logo de la Empresa")
    logo_actual = empresa.get("logo_path", "")
    if logo_actual and os.path.exists(logo_actual):
        st.image(logo_actual, width=140, caption="Logo actual")
    logo_nuevo = st.file_uploader("Subir logo (PNG o JPG)", type=["png", "jpg", "jpeg"])

    if st.button("Guardar cambios", type="primary", use_container_width=True):
        empresa["nombre"] = nombre_emp.strip()
        empresa["rubro"] = rubro_emp
        empresa["telefono"] = telefono_emp.strip()
        empresa["zona"] = zona_emp.strip()
        empresa["whatsapp"] = whatsapp_emp.strip()
        empresa["validez_dias"] = validez_emp
        empresa["firma_texto"] = firma_emp.strip()

        if logo_nuevo is not None:
            empresa["logo_path"] = guardar_logo(logo_nuevo)

        st.session_state.empresa = empresa
        guardar_config(empresa)
        st.success("Datos de la empresa actualizados.")
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
                st.write(f"{p['fecha']}  |  $ {p['total']:,.2f}  |  {p.get('estado', 'Pendiente')}")

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
                    if st.button("Duplicar", key=f"dup_{p['id']}", use_container_width=True):
                        st.session_state.cliente_nombre_input = p["cliente_nombre"]
                        st.session_state.cliente_direccion_input = p["cliente_direccion"]
                        st.session_state.cliente_telefono_input = p["cliente_telefono"]
                        st.session_state.lista_items = [dict(item) for item in p["items"]]
                        st.session_state.reset_counter += 1
                        st.success('Datos copiados. Andá a la pestaña "Nuevo Presupuesto".')

                with st.expander("Ver ítems"):
                    for item in p["items"]:
                        st.write(
                            f"- {item['descripcion']} — {item['cantidad']} x "
                            f"$ {item['precio_unitario']:,.2f} = $ {item['subtotal']:,.2f}"
                        )
                    if p.get("notas"):
                        st.caption(p["notas"])
