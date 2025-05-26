import os
import shutil
import zipfile
import streamlit as st
from pathlib import Path
from docx import Document
import pdfplumber
import google.generativeai as genai
import tempfile
from io import BytesIO

# Definir modelo global (se configurará dinámicamente)
model = None

def extraer_texto_pdf(path, max_paginas=5):
    texto = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages[:max_paginas]:
            texto += page.extract_text() or ""
            texto += "\n\n"
    return texto.strip()

def extraer_texto_docx_from_bytes(bytes_data):
    try:
        file_stream = BytesIO(bytes_data)
        doc = Document(file_stream)
        return "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception:
        return "[Error: no se pudo leer el archivo DOCX correctamente]"

def analizar_con_gemini(nombre_archivo, contenido):
    prompt = f"""
Eres un asistente técnico especializado en BIM. Estás colaborando en la creación de un repositorio de proyectos históricos para el análisis y redacción automatizada de documentos Pre-BEP.

Analiza el contenido completo del siguiente archivo. Extrae y describe con claridad los puntos clave, conceptos técnicos, roles, entregables, condiciones o estructura que pueda ser relevante. No te limites a un resumen breve, enfócate en información útil que pueda alimentar una base vectorial consultable por IA.

Archivo: {nombre_archivo}
Contenido:
{contenido[:8000]}
"""
    respuesta = model.generate_content(prompt)
    return respuesta.text.strip()

def guardar_estructura(nombre_proyecto, archivos_en_memoria, archivo_output, metadata):
    base_path = Path(f"proyectos_temporales/{nombre_proyecto}")
    inputs_path = base_path / "inputs"
    inputs_path.mkdir(parents=True, exist_ok=True)

    for nombre_archivo, contenido in archivos_en_memoria:
        archivo_path = inputs_path / nombre_archivo
        with open(archivo_path, "wb") as f:
            f.write(contenido)

    output_path = base_path / "prebep_final.docx"
    with open(output_path, "wb") as f:
        f.write(archivo_output.read())

    resumen_path = base_path / "resumen.txt"
    with open(resumen_path, "w", encoding="utf-8") as f:
        f.write(metadata)

    zip_path = Path("proyectos_exportados") / f"{nombre_proyecto}.zip"
    shutil.make_archive(zip_path.with_suffix("" ).as_posix(), "zip", base_path)

    return zip_path

def app():
    global model

    st.title("Asistente de indexación Pre-BEP con Gemini")

    st.sidebar.header("Configuración de Gemini")
    api_key = st.sidebar.text_input("Introduce tu API Key de Gemini", type="password")

    if api_key:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-1.5-pro-latest")
            st.sidebar.success("Gemini configurado correctamente ✅")
        except Exception as e:
            st.sidebar.error(f"Error al configurar Gemini: {e}")
            return
    else:
        st.stop()

    nombre_proyecto = st.text_input("Nombre del proyecto (único y corto):")

    st.header("Paso 1: Sube los archivos de entrada del Pre-BEP")
    archivos_input = st.file_uploader("Archivos PDF/DOCX de entrada", type=["pdf", "docx"], accept_multiple_files=True)

    st.header("Paso 2: Completa el formulario del resumen.txt")
    cliente = st.text_input("Cliente")
    tipo = st.text_input("Tipo de proyecto")
    ubicacion = st.text_input("Ubicación")
    nivel_bim = st.selectbox("Nivel BIM", [1, 2, 3])
    usos_bim = st.text_area("Usos BIM (separados por coma)")
    paginas = st.number_input("Páginas deseadas en el Pre-BEP", min_value=1, max_value=50, value=6)

    st.header("Paso 3: Sube el Pre-BEP final")
    archivo_output = st.file_uploader("Archivo DOCX resultado final", type="docx")

    if st.button("✅ Generar estructura indexada"):
        if not nombre_proyecto or not archivos_input or not archivo_output:
            st.error("Faltan datos obligatorios.")
            return

        resumen = f"""cliente: {cliente}
tipo: {tipo}
ubicacion: {ubicacion}
nivel_bim: {nivel_bim}
usos_bim: {usos_bim}
n_paginas_deseadas: {paginas}
archivos:
"""
        archivos_en_memoria = []
        for archivo in archivos_input:
            nombre = archivo.name
            contenido_archivo = archivo.read()
            archivos_en_memoria.append((nombre, contenido_archivo))

            if nombre.endswith(".pdf"):
                from io import BytesIO
                with pdfplumber.open(BytesIO(contenido_archivo)) as pdf:
                    contenido = ""
                    for page in pdf.pages[:5]:
                        contenido += page.extract_text() or ""
                        contenido += "\n\n"

"
            else:
                contenido = extraer_texto_docx_from_bytes(contenido_archivo)

            resumen_gemini = analizar_con_gemini(nombre, contenido)
            resumen += f"  - {nombre}: {resumen_gemini}\n"

        # Analizar el documento final y reiniciar su contenido para escritura
        contenido_output = archivo_output.read()
        resumen_final = analizar_con_gemini("prebep_final.docx", extraer_texto_docx_from_bytes(contenido_output))
        resumen += f"\nResumen del documento final (prebep_final.docx):\n{resumen_final}\n"

        from io import BytesIO
        archivo_output = BytesIO(contenido_output)

        zip_path = guardar_estructura(nombre_proyecto, archivos_en_memoria, archivo_output, resumen)
        st.success("Proyecto preparado y empaquetado correctamente.")
        with open(zip_path, "rb") as f:
            st.download_button(
                label="⬇️ Descargar ZIP",
                data=f,
                file_name=os.path.basename(zip_path),
                mime="application/zip"
            )

if __name__ == "__main__":
    os.makedirs("proyectos_temporales", exist_ok=True)
    os.makedirs("proyectos_exportados", exist_ok=True)
    app()
