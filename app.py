"""
App de Presupuestos - Servicio Técnico de Aire Acondicionado
--------------------------------------------------------------
Ejecutar con:
    streamlit run app.py

Instalar dependencias:
    pip install streamlit fpdf2 pandas plotly
"""

import base64
from datetime import date, datetime
import json
import os
from urllib.parse import quote
from fpdf import FPDF
import pandas as pd
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
DATA_FILE = "historial_presupuestos.json"
CONFIG_FILE = "config_empresa.json"

NAVY_RGB = (11, 37, 69)

CATEGORIAS = [
    "Instalación Split",
    "Mantenimiento / Limpieza",
    "Detección / Reparación de Fugas",
    "Diagnóstico / Reparación Eléctrica",
    "Carga de Refrigerante",
    "Otro",
]

ESTADOS = ["Pendiente", "Aprobado", "Rechazado", "Completado"]

SERVICIOS_PREDEFINIDOS = [
    {
        "categoria": "Instalación Split",
        "descripcion": "Instalación Split 3000 frigorías (mano de obra)",
        "precio": 45000.0,
    },
    {
        "categoria": "Instalación Split",
        "descripcion": "Instalación Split 4500 frigorías (mano de obra)",
        "precio": 55000.0,
    },
    {
        "categoria": "Mantenimiento / Limpieza",
        "descripcion": "Mantenimiento y limpieza profunda",
        "precio": 20000.0,
    },
    {
        "categoria": "Detección / Reparación de Fugas",
        "descripcion": "Detección de fuga de gas",
        "precio": 25000.0,
    },
    {
        "categoria": "Diagnóstico / Reparación Eléctrica",
        "descripcion": "Cambio de capacitor",
        "precio": 12000.0,
    },
    {
        "categoria": "Carga de Refrigerante",
        "descripcion": "Carga de gas R410A",
        "precio": 30000.0,
    },
    {
        "categoria": "Carga de Refrigerante",
        "descripcion": "Carga de gas R22",
        "precio": 28000.0,
    },
]

ADICIONALES_RAPIDOS = [
    {
        "categoria": "Otro",
        "descripcion": "Metro extra de cañería de cobre",
        "precio": 8000.0,
    },
    {
        "categoria": "Otro",
        "descripcion": "Materiales de aislación",
        "precio": 6000.0,
    },
    {
        "categoria": "Otro",
        "descripcion": "Trabajo en altura (adicional)",
        "precio": 15000.0,
    },
]

st.set_page_config(
    page_title="Presupuestos - Aire Acondicionado", layout="centered"
)


# ============================================================
# UTILIDADES DE TEXTO
# ============================================================
def safe_txt(s: str) -> str:
  if s is None:
    return ""
  return str(s).encode("latin-1", "replace").decode("latin-1")


# ============================================================
# PERSISTENCIA - HISTORIAL DE PRESUPUESTOS
# ============================================================
def cargar_historial():
  if os.path.exists(DATA_FILE):
    try:
      with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except (json.JSONDecodeError, OSError):
      return []
  return []


def guardar_historial(historial):
  with open(DATA_FILE, "w", encoding="utf-8") as f:
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
      "nombre": "Servicio Técnico de Aire Acondicionado",
      "telefono": "",
      "zona": "",
      "whatsapp": "",
      "validez_dias": 7,
      "firma_texto": "",
      "logo_path": "",
  }
  if os.path.exists(CONFIG_FILE):
    try:
      with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        default.update(data)
    except (json.JSONDecodeError, OSError):
      pass
  return default


def guardar_config(config):
  with open(CONFIG_FILE, "w", encoding="utf-8") as f:
    json.dump(config, f, ensure_ascii=False, indent=2)


def extension_archivo(nombre_archivo):
  return os.path.splitext(nombre_archivo)[1].lower()


def guardar_logo(uploaded_file):
  ext = extension_archivo(uploaded_file.name) or ".png"
  ruta = f"logo_empresa{ext}"
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
        self.image(logo_path, x=12, y=10, w=18)
      except Exception:
        pass

    self.set_font("Helvetica", "B", 16)
    self.set_text_color(*NAVY_RGB)
    self.cell(
        0, 10, safe_txt(self.empresa.get("nombre", "")), ln=True, align="C"
    )
    self.set_font("Helvetica", "", 10)
    self.set_text_color(90, 90, 90)
    info = (
        f"Tel: {self.empresa.get('telefono', '')}   |   Zona:"
        f" {self.empresa.get('zona', '')}"
    )
    self.cell(0, 6, safe_txt(info), ln=True, align="C")
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
    texto = (
        f"Presupuesto generado el {datetime.now().strftime('%d/%m/%Y %H:%M')} -"
        f" Página {self.page_no()}"
    )
    self.cell(0, 5, safe_txt(texto), align="C")


def generar_pdf(presupuesto, empresa) -> bytes:
  pdf = PDFPresupuesto(empresa)
  pdf.add_page()

  pdf.set_font("Helvetica", "B", 12)
  pdf.set_text_color(0, 0, 0)
  pdf.cell(0, 8, safe_txt(f"Presupuesto N° {presupuesto['id']:04d}"), ln=True)
  pdf.set_font("Helvetica", "", 11)
  pdf.cell(0, 6, safe_txt(f"Fecha: {presupuesto['fecha']}"), ln=True)
  pdf.cell(
      0,
      6,
      safe_txt(f"Estado: {presupuesto.get('estado', 'Pendiente')}"),
      ln=True,
  )
  pdf.ln(2)

  pdf.set_font("Helvetica", "B", 11)
  pdf.cell(0, 7, "Datos del Cliente", ln=True)
  pdf.set_font("Helvetica", "", 10)
  pdf.cell(
      0, 6, safe_txt(f"Cliente: {presupuesto['cliente_nombre']}"), ln=True
  )
  pdf.cell(
      0, 6, safe_txt(f"Dirección: {presupuesto['cliente_direccion']}"), ln=True
  )
  pdf.cell(
      0, 6, safe_txt(f"Teléfono: {presupuesto['cliente_telefono']}"), ln=True
  )
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
    texto_concepto = safe_txt(item["descripcion"])
    y_inicio = pdf.get_y()
    x_inicio = pdf.get_x()

    # Concepto con multilínea completo
    pdf.multi_cell(
        col_widths[0], 6, texto_concepto, border=1, fill=fill, align="L"
    )
    altura_fila = pdf.get_y() - y_inicio

    # Alinear el resto de las celdas a la misma altura
    pdf.set_xy(x_inicio + col_widths[0], y_inicio)
    pdf.cell(
        col_widths[1],
        altura_fila,
        str(item["cantidad"]),
        border=1,
        align="C",
        fill=fill,
    )
    pdf.cell(
        col_widths[2],
        altura_fila,
        f"${item['precio_unitario']:,.2f}",
        border=1,
        align="R",
        fill=fill,
    )
    pdf.cell(
        col_widths[3],
        altura_fila,
        f"${item['subtotal']:,.2f}",
        border=1,
        align="R",
        fill=fill,
    )

    pdf.ln(altura_fila)
    fill = not fill
  pdf.ln(2)

  x_label = sum(col_widths[:3])
  pdf.set_font("Helvetica", "", 10)
  pdf.cell(x_label, 7, "Subtotal", align="R")
  pdf.cell(
      col_widths[3], 7, f"${presupuesto['subtotal']:,.2f}", align="R", ln=True
  )

  if presupuesto.get("descuento_pct", 0) > 0:
    pdf.cell(
        x_label,
        7,
        safe_txt(f"Descuento ({presupuesto['descuento_pct']}%)"),
        align="R",
    )
    pdf.cell(
        col_widths[3],
        7,
        f"-${presupuesto['descuento_monto']:,.2f}",
        align="R",
        ln=True,
    )

  if presupuesto.get("envio", 0) > 0:
    pdf.cell(x_label, 7, safe_txt("Envío / Desplazamiento"), align="R")
    pdf.cell(
        col_widths[3], 7, f"${presupuesto['envio']:,.2f}", align="R", ln=True
    )

  pdf.set_font("Helvetica", "B", 12)
  pdf.set_fill_color(*NAVY_RGB)
  pdf.set_text_color(255, 255, 255)
  pdf.cell(x_label, 9, "TOTAL", align="R", fill=True)
  pdf.cell(
      col_widths[3],
      9,
      f"${presupuesto['total']:,.2f}",
      align="R",
      fill=True,
      ln=True,
  )
  pdf.set_text_color(0, 0, 0)
  pdf.ln(6)

  if presupuesto.get("notas"):
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, safe_txt("Notas / Condiciones"), ln=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.multi_cell(0, 5, safe_txt(presupuesto["notas"]))

  return bytes(pdf.output())


# ============================================================
# ESTILOS
# ============================================================
st.markdown(
    """
    <style>
    :root {
        --navy: #0B2545;
        --navy-light: #163A6B;
        --accent: #2F6FD6;
        --accent-hover: #4C8CF0;
        --text-light: #EAF1FB;
        --border: #26456F;
    }
    h1, h2, h3, h4 { color: var(--text-light) !important; }
    div.stButton > button, div.stDownloadButton > button, div[data-testid="stFormSubmitButton"] > button {
        background-color: var(--accent);
        color: #FFFFFF !important;
        border-radius: 10px;
        border: none;
        padding: 0.55em 1.2em;
        font-weight: 600;
        transition: transform 0.15s ease, background-color 0.15s ease;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: var(--accent-hover);
        color: #FFFFFF !important;
        transform: translateY(-2px);
    }
    [data-testid="stMetric"] {
        background-color: var(--navy-light);
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 10px 16px;
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
        border-radius: 14px;
        text-align: center;
        margin-bottom: 22px;
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
    zona = empresa.get("zona", "")
    banner_html = f'<div class="header-banner">{logo_html}<h1>{nombre}</h1><p>{zona}</p></div>'
    st.markdown(banner_html, unsafe_allow_html=True)


mostrar_banner()

tab_nuevo, tab_calculadora, tab_personalizar, tab_historial = st.tabs([
    "Nuevo Presupuesto",
    "Calculadora de Frigorías",
    "Personalizar Factura",
    "Historial y Métricas",
])

# ------------------------------------------------------------
# TAB 1: NUEVO PRESUPUESTO
# ------------------------------------------------------------
with tab_nuevo:
  st.subheader("Datos del Cliente")
  cliente_nombre = st.text_input("Nombre y Apellido", key="cliente_nombre_input")
  col1, col2 = st.columns(2)
  with col1:
    cliente_direccion = st.text_input(
        "Dirección / Ubicación", key="cliente_direccion_input"
    )
  with col2:
    cliente_telefono = st.text_input(
        "Teléfono del cliente", key="cliente_telefono_input"
    )
  fecha = st.date_input("Fecha", value=date.today())

  st.divider()
  st.subheader("Detalle del Trabajo")

  opciones_serv = ["Personalizado..."] + [
      s["descripcion"] for s in SERVICIOS_PREDEFINIDOS
  ]
  seleccion = st.selectbox("Servicio predefinido (opcional)", opciones_serv)
  servicio_sugerido = next(
      (s for s in SERVICIOS_PREDEFINIDOS if s["descripcion"] == seleccion), None
  )

  with st.form("form_item", clear_on_submit=True):
    categoria_default = (
        servicio_sugerido["categoria"] if servicio_sugerido else CATEGORIAS[0]
    )
    categoria = st.selectbox(
        "Categoría", CATEGORIAS, index=CATEGORIAS.index(categoria_default)
    )
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
          value=(
              float(servicio_sugerido["precio"]) if servicio_sugerido else 0.0
          ),
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
        st.session_state.lista_items.append({
            "categoria": categoria,
            "descripcion": descripcion.strip(),
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "subtotal": cantidad * precio_unitario,
        })
        st.toast("Ítem agregado correctamente", icon="✔")

  st.caption("Adicionales rápidos")
  cols_add = st.columns(len(ADICIONALES_RAPIDOS))
  for c, ad in zip(cols_add, ADICIONALES_RAPIDOS):
    with c:
      if st.button(
          ad["descripcion"],
          key=f"add_{ad['descripcion']}",
          use_container_width=True,
      ):
        st.session_state.lista_items.append({
            "categoria": ad["categoria"],
            "descripcion": ad["descripcion"],
            "cantidad": 1,
            "precio_unitario": ad["precio"],
            "subtotal": ad["precio"],
        })
        st.toast(f"Agregado: {ad['descripcion']}", icon="➕")
        st.rerun()

  st.write("Ítems del presupuesto (editable directamente en la tabla)")
  columnas_items = [
      "categoria",
      "descripcion",
      "cantidad",
      "precio_unitario",
      "subtotal",
  ]
  if st.session_state.lista_items:
    df_items = pd.DataFrame(st.session_state.lista_items)[columnas_items]
  else:
    df_items = pd.DataFrame(columns=columnas_items)

  edited_df = st.data_editor(
      df_items,
      num_rows="dynamic",
      use_container_width=True,
      hide_index=True,
      key=f"editor_items_{st.session_state.reset_counter}",
      column_config={
          "categoria": st.column_config.SelectboxColumn(
              "Categoría", options=CATEGORIAS
          ),
          "descripcion": st.column_config.TextColumn(
              "Descripción", width="large"
          ),
          "cantidad": st.column_config.NumberColumn(
              "Cant.", min_value=1, step=1
          ),
          "precio_unitario": st.column_config.NumberColumn(
              "P. Unit.", min_value=0.0, format="$ %.2f"
          ),
          "subtotal": st.column_config.NumberColumn(
              "Subtotal", format="$ %.2f", disabled=True
          ),
      },
  )

  edited_df["cantidad"] = edited_df["cantidad"].fillna(1)
  edited_df["precio_unitario"] = edited_df["precio_unitario"].fillna(0.0)
  edited_df["subtotal"] = edited_df["cantidad"] * edited_df["precio_unitario"]
  edited_df["categoria"] = edited_df["categoria"].fillna(CATEGORIAS[0])
  edited_df["descripcion"] = edited_df["descripcion"].fillna("")
  st.session_state.lista_items = edited_df.to_dict("records")

  st.divider()
  st.subheader("Descuento y Envío")
  col1, col2 = st.columns(2)
  with col1:
    descuento_pct = st.number_input(
        "Descuento (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0
    )
  with col2:
    envio = st.number_input(
        "Envío / Desplazamiento ($)", min_value=0.0, value=0.0, step=100.0
    )

  st.subheader("Estado y Notas")
  estado = st.selectbox("Estado del presupuesto", ESTADOS, index=0)

  validez = st.session_state.empresa.get("validez_dias", 7)
  notas_default = (
      f"Presupuesto válido por {validez} días.\n"
      "No incluye trabajo de albañilería.\n"
      "Garantía de instalación: 6 meses."
  )
  notas = st.text_area("Notas / Condiciones", value=notas_default, height=100)

  subtotal = sum(i["subtotal"] for i in st.session_state.lista_items)
  descuento_monto = subtotal * (descuento_pct / 100)
  total = subtotal - descuento_monto + envio

  st.divider()
  col1, col2, col3 = st.columns(3)
  with col1:
    st.metric("Subtotal", f"$ {subtotal:,.2f}")
  with col2:
    st.metric("Descuento", f"$ {descuento_monto:,.2f}")
  with col3:
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
        st.toast(f"Presupuesto N° {nuevo_id:04d} generado con éxito", icon="📄")
        st.balloons()
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
          f'<iframe src="data:application/pdf;base64,{b64_pdf}" width="100%"'
          ' height="500" style="border:none;"></iframe>',
          height=520,
      )

    telefono_wa = st.session_state.empresa.get("whatsapp", "").strip()
    if telefono_wa:
      mensaje = (
          f"Hola {info['cliente']}, te comparto el presupuesto N° {info['id']:04d}"
          f" por un total de $ {info['total']:,.2f}. Cualquier consulta quedo a"
          " disposición."
      )
      wa_url = f"https://wa.me/{telefono_wa}?text={quote(mensaje)}"
      st.markdown(
          f'<a href="{wa_url}" target="_blank" class="wa-button">Enviar aviso'
          " por WhatsApp</a>",
          unsafe_allow_html=True,
      )
    else:
      st.caption(
          'Cargá un número de WhatsApp en "Personalizar Factura" para enviar el'
          " aviso directo."
      )

# ------------------------------------------------------------
# TAB 2: CALCULADORA INTERACTIVA DE FRIGORÍAS
# ------------------------------------------------------------
with tab_calculadora:
  st.subheader("Calculadora Térmica de Frigorías")
  st.write(
      "Calculá rápidamente las frigorías recomendadas según las dimensiones y"
      " condiciones del ambiente."
  )

  col_a, col_b = st.columns(2)
  with col_a:
    largo = st.number_input(
        "Largo del ambiente (m)", min_value=1.0, value=4.0, step=0.5
    )
    ancho = st.number_input(
        "Ancho del ambiente (m)", min_value=1.0, value=3.5, step=0.5
    )
    alto = st.number_input(
        "Alto del ambiente (m)", min_value=2.0, value=2.6, step=0.1
    )
  with col_b:
    personas = st.number_input(
        "Cantidad de personas habituales", min_value=1, value=2, step=1
    )
    sol_directo = st.checkbox(
        "¿Le da el sol directo a las paredes o ventanas durante el día?"
    )
    equipos_electr = st.checkbox(
        "¿Hay muchos aparatos electrónicos encendidos (PCs, TV, etc.)?"
    )

  volumen = largo * ancho * alto
  base_frig = volumen * 50  # Estimación promedio de 50 frigorías por m3

  if personas > 2:
    base_frig += (personas - 2) * 150
  if sol_directo:
    base_frig *= 1.15
  if equipos_electr:
    base_frig += 200

  frig_recomendadas = int(round(base_frig, -2))

  st.divider()
  st.metric("Frigorías Recomendadas", f"{frig_recomendadas:,} fg")

  if frig_recomendadas <= 2700:
    equipo_sugerido = "Split 2250 / 2500 frigorías"
  elif frig_recomendadas <= 3500:
    equipo_sugerido = "Split 3000 / 3200 frigorías"
  elif frig_recomendadas <= 5000:
    equipo_sugerido = "Split 4500 frigorías"
  else:
    equipo_sugerido = "Split 6000 frigorías o superior"

  st.info(
      f"💡 Sugerencia técnica: Para este espacio de **{volumen:.1f} m³**, se"
      f" recomienda instalar un equipo **{equipo_sugerido}**."
  )

  if st.button(
      "Cargar sugerencia al presupuesto actual", use_container_width=True
  ):
    st.session_state.lista_items.append({
        "categoria": "Instalación Split",
        "descripcion": (
            f"Instalación {equipo_sugerido} (Sugerido por cálculo de"
            f" {frig_recomendadas:,} fg)"
        ),
        "cantidad": 1,
        "precio_unitario": 50000.0,
        "subtotal": 50000.0,
    })
    st.toast("Sugerencia cargada en la lista de ítems", icon="📥")

# ------------------------------------------------------------
# TAB 3: PERSONALIZAR FACTURA
# ------------------------------------------------------------
with tab_personalizar:
  st.subheader("Datos de la Empresa")
  empresa = st.session_state.empresa

  nombre_emp = st.text_input("Nombre / Marca", value=empresa.get("nombre", ""))
  col1, col2 = st.columns(2)
  with col1:
    telefono_emp = st.text_input("Teléfono", value=empresa.get("telefono", ""))
  with col2:
    zona_emp = st.text_input("Zona de cobertura", value=empresa.get("zona", ""))

  whatsapp_emp = st.text_input(
      "Número de WhatsApp para envíos (con código de país, sin +, ej:"
      " 5491122334455)",
      value=empresa.get("whatsapp", ""),
  )

  opciones_validez = [7, 15, 30]
  validez_actual = empresa.get("validez_dias", 7)
  validez_emp = st.selectbox(
      "Validez del presupuesto (días)",
      opciones_validez,
      index=(
          opciones_validez.index(validez_actual)
          if validez_actual in opciones_validez
          else 0
      ),
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
  logo_nuevo = st.file_uploader(
      "Subir logo (PNG o JPG)", type=["png", "jpg", "jpeg"]
  )

  if st.button("Guardar cambios", type="primary", use_container_width=True):
    empresa["nombre"] = nombre_emp.strip()
    empresa["telefono"] = telefono_emp.strip()
    empresa["zona"] = zona_emp.strip()
    empresa["whatsapp"] = whatsapp_emp.strip()
    empresa["validez_dias"] = validez_emp
    empresa["firma_texto"] = firma_emp.strip()

    if logo_nuevo is not None:
      empresa["logo_path"] = guardar_logo(logo_nuevo)

    st.session_state.empresa = empresa
    guardar_config(empresa)
    st.toast("Configuración guardada", icon="⚙️")
    st.success("Datos de la empresa actualizados.")
    st.rerun()

# ------------------------------------------------------------
# TAB 4: HISTORIAL Y MÉTRICAS INTERACTIVAS
# ------------------------------------------------------------
with tab_historial:
  st.subheader("Historial de Presupuestos & Analytics")
  historial = cargar_historial()

  if not historial:
    st.info("Todavía no hay presupuestos guardados.")
  else:
    # Métricas principales
    df_hist = pd.DataFrame(historial)
    total_monto = df_hist["total"].sum()
    presupuestos_aprobados = df_hist[df_hist["estado"] == "Aprobado"]
    monto_aprobado = presupuestos_aprobados["total"].sum()

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
      st.metric("Total Presupuestado", f"$ {total_monto:,.2f}")
    with col_m2:
      st.metric("Total Aprobado", f"$ {monto_aprobado:,.2f}")
    with col_m3:
      st.metric("Presupuestos Emitidos", len(df_hist))

    st.divider()

    # Gráfico interactivo Plotly
    st.subheader("Distribución por Estado")
    fig_estado = px.pie(
        df_hist,
        names="estado",
        values="total",
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    fig_estado.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#EAF1FB"),
        margin=dict(t=20, b=20, l=20, r=20),
    )
    st.plotly_chart(fig_estado, use_container_width=True)

    st.divider()

    col_busq, col_estado = st.columns([2, 1])
    with col_busq:
      busqueda = st.text_input("Buscar por nombre de cliente")
    with col_estado:
      filtro_estado = st.selectbox("Estado", ["Todos"] + ESTADOS)

    filtrados = historial
    if busqueda:
      filtrados = [
          p
          for p in filtrados
          if busqueda.lower().strip() in p["cliente_nombre"].lower()
      ]
    if filtro_estado != "Todos":
      filtrados = [
          p
          for p in filtrados
          if p.get("estado", "Pendiente") == filtro_estado
      ]

    filtrados = sorted(filtrados, key=lambda p: p["id"], reverse=True)

    df_export = pd.DataFrame([
        {
            "ID": p["id"],
            "Fecha": p["fecha"],
            "Cliente": p["cliente_nombre"],
            "Total": p["total"],
            "Estado": p.get("estado", "Pendiente"),
        }
        for p in historial
    ])
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
        st.write(f"**N° {p['id']:04d} — {p['cliente_nombre']}**")
        st.write(
            f"Fecha: {p['fecha']}  |  Total: **$ {p['total']:,.2f}**  | "
            f" Estado: **{p.get('estado', 'Pendiente')}**"
        )

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
            if nuevo_estado == "Aprobado":
              st.balloons()
            st.toast(f"Estado actualizado a {nuevo_estado}", icon="🔄")
            st.rerun()

        with col2:
          try:
            pdf_bytes_hist = generar_pdf(p, st.session_state.empresa)
            st.download_button(
                "Descargar PDF",
                data=pdf_bytes_hist,
                file_name=(
                    f"presupuesto_{p['id']:04d}_{p['cliente_nombre'].replace(' ', '_')}.pdf"
                ),
                mime="application/pdf",
                key=f"desc_{p['id']}",
            )
          except Exception as e:
            st.error(f"No se pudo generar el PDF: {e}")

        with col3:
          if st.button(
              "Duplicar", key=f"dup_{p['id']}", use_container_width=True
          ):
            st.session_state.cliente_nombre_input = p["cliente_nombre"]
            st.session_state.cliente_direccion_input = p["cliente_direccion"]
            st.session_state.cliente_telefono_input = p["cliente_telefono"]
            st.session_state.lista_items = [dict(item) for item in p["items"]]
            st.session_state.reset_counter += 1
            st.toast("Datos duplicados en el formulario", icon="📋")
            st.success(
                'Datos copiados. Andá a la pestaña "Nuevo Presupuesto".'
            )

        with st.expander("Ver ítems"):
          for item in p["items"]:
            st.write(
                f"- {item['descripcion']} — {item['cantidad']} x $"
                f" {item['precio_unitario']:,.2f} = $ {item['subtotal']:,.2f}"
            )
          if p.get("notas"):
            st.caption(p["notas"])