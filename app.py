from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from datetime import datetime
from fpdf import FPDF  # Usaremos FPDF para generar el PDF
import pdfplumber
import re

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Diccionario global para almacenar los inventarios de los agentes
inventarios = {
    "Susana": {"inventario": {}, "ultima_modificacion": None, "historial": []},
    "Alicia": {"inventario": {}, "ultima_modificacion": None, "historial": []},
    "Agente 3": {"inventario": {}, "ultima_modificacion": None, "historial": []},
}

# Función para cargar el inventario desde un PDF
def cargar_inventario_desde_pdf(pdf_file):
    try:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"

        # Expresión regular para capturar productos y cantidades
        inventario_pattern = re.compile(r'(\d+\.\d+)\s+Unid\s+([^\n]+?)\s+Grav\s+\d+%')
        matches = inventario_pattern.findall(text)

        inventario = {}
        for match in matches:
            cantidad = float(match[0])  # Cantidad convertida a número decimal
            producto = match[1].strip()  # Nombre del producto
            inventario[producto] = cantidad

        return inventario
    except Exception as e:
        print(f"Error al cargar el inventario desde el PDF: {str(e)}")
        return {}

# Función para registrar en el historial
def registrar_historial(agente_nombre, tipo, producto, cantidad):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    inventarios[agente_nombre]["historial"].append({
        "fecha": fecha,
        "tipo": tipo,  # "agregado", "venta" o "auditoría"
        "producto": producto,
        "cantidad": cantidad
    })

# Función para generar el PDF de auditoría
def generar_pdf(agente_nombre, inventario, resultados_auditoria):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Encabezado
    pdf.cell(200, 10, txt=f"Reporte de Auditoría - {agente_nombre}", ln=True, align="C")
    pdf.ln(10)

    # Tabla de resultados
    pdf.set_font("Arial", size=10)
    pdf.cell(50, 10, "Producto", border=1)
    pdf.cell(40, 10, "Cantidad Actual", border=1)
    pdf.cell(40, 10, "Cantidad Reportada", border=1)
    pdf.cell(40, 10, "Resultado", border=1)
    pdf.ln()

    for producto, resultado in resultados_auditoria.items():
        pdf.cell(50, 10, producto, border=1)
        pdf.cell(40, 10, str(inventario[producto]), border=1)
        pdf.cell(40, 10, str(resultado["reportada"]), border=1)
        if resultado["diferencia"] == 0:
            pdf.cell(40, 10, "Cuadrado", border=1)
        else:
            pdf.cell(40, 10, f"Descuadre: {resultado['diferencia']}", border=1)
        pdf.ln()

    # Guardar el PDF en un archivo temporal
    pdf_output = pdf.output(dest="S")  # Devuelve un objeto bytes
    return pdf_output
# Ruta principal
@app.route('/')
def index():
    return render_template('index.html')

# Ruta para cargar inventario
@app.route('/cargar_inventario', methods=['GET', 'POST'])
def cargar_inventario():
    if request.method == 'POST':
        agente_nombre = request.form['agente_nombre']

        if agente_nombre not in inventarios:
            flash('Agente no encontrado.', 'error')
            return redirect(url_for('cargar_inventario'))

        # Verificar si se cargó un archivo PDF
        if 'inventarioFile' in request.files:
            pdf_file = request.files['inventarioFile']
            if pdf_file.filename != '':
                try:
                    inventario_pdf = cargar_inventario_desde_pdf(pdf_file)
                    for producto, cantidad in inventario_pdf.items():
                        if producto in inventarios[agente_nombre]["inventario"]:
                            inventarios[agente_nombre]["inventario"][producto] += cantidad
                        else:
                            inventarios[agente_nombre]["inventario"][producto] = cantidad
                        # Registrar en el historial
                        registrar_historial(agente_nombre, "agregado", producto, cantidad)
                    # Actualizar la fecha de la última modificación
                    inventarios[agente_nombre]["ultima_modificacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    flash('Inventario cargado correctamente desde el PDF.', 'success')
                    return redirect(url_for('cargar_inventario'))
                except Exception as e:
                    flash(f'Error al procesar el PDF: {str(e)}', 'error')
                    return redirect(url_for('cargar_inventario'))

        # Carga manual
        producto = request.form.get('producto')
        cantidad = float(request.form.get('cantidad', 0))

        if producto and cantidad > 0:
            if producto in inventarios[agente_nombre]["inventario"]:
                inventarios[agente_nombre]["inventario"][producto] += cantidad
            else:
                inventarios[agente_nombre]["inventario"][producto] = cantidad
            # Registrar en el historial
            registrar_historial(agente_nombre, "agregado", producto, cantidad)
            # Actualizar la fecha de la última modificación
            inventarios[agente_nombre]["ultima_modificacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            flash('Inventario cargado correctamente de forma manual.', 'success')
            return redirect(url_for('cargar_inventario'))

    return render_template('cargar_inventario.html')

# Ruta para registrar ventas
@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if request.method == 'POST':
        agente_nombre = request.form['agente_nombre']

        if agente_nombre not in inventarios:
            flash('Agente no encontrado.', 'error')
            return redirect(url_for('ventas'))

        # Verificar si se cargó un archivo PDF
        if 'ventasFile' in request.files:
            pdf_file = request.files['ventasFile']
            if pdf_file.filename != '':
                try:
                    ventas_pdf = cargar_inventario_desde_pdf(pdf_file)
                    for producto, cantidad in ventas_pdf.items():
                        if producto in inventarios[agente_nombre]["inventario"]:
                            if inventarios[agente_nombre]["inventario"][producto] >= cantidad:
                                inventarios[agente_nombre]["inventario"][producto] -= cantidad
                                # Registrar en el historial
                                registrar_historial(agente_nombre, "venta", producto, cantidad)
                                # Actualizar la fecha de la última modificación
                                inventarios[agente_nombre]["ultima_modificacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                flash(f'Venta de {cantidad} unidades de {producto} registrada correctamente.', 'success')
                            else:
                                flash(f'No hay suficiente stock de {producto} para vender {cantidad} unidades.', 'error')
                        else:
                            flash(f'El producto {producto} no existe en el inventario del agente.', 'error')
                    return redirect(url_for('ventas'))
                except Exception as e:
                    flash(f'Error al procesar el PDF: {str(e)}', 'error')
                    return redirect(url_for('ventas'))

        # Si no se cargó un archivo PDF, procesar la venta manualmente
        producto = request.form.get('producto')
        cantidad = float(request.form.get('cantidad', 0))

        if producto and cantidad > 0:
            if producto in inventarios[agente_nombre]["inventario"]:
                if inventarios[agente_nombre]["inventario"][producto] >= cantidad:
                    inventarios[agente_nombre]["inventario"][producto] -= cantidad
                    # Registrar en el historial
                    registrar_historial(agente_nombre, "venta", producto, cantidad)
                    # Actualizar la fecha de la última modificación
                    inventarios[agente_nombre]["ultima_modificacion"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    flash(f'Venta de {cantidad} unidades de {producto} registrada correctamente.', 'success')
                else:
                    flash(f'No hay suficiente stock de {producto} para vender {cantidad} unidades.', 'error')
            else:
                flash(f'El producto {producto} no existe en el inventario del agente.', 'error')
            return redirect(url_for('ventas'))

    return render_template('ventas.html')

# Ruta para realizar auditorías
@app.route('/auditoria', methods=['GET', 'POST'])
def auditoria():
    if request.method == 'POST':
        agente_nombre = request.form['agente_nombre']

        if agente_nombre not in inventarios:
            flash('Agente no encontrado.', 'error')
            return redirect(url_for('auditoria'))

        # Obtener el inventario del agente
        inventario_actual = inventarios[agente_nombre]["inventario"]
        resultados_auditoria = {}

        # Procesar las cantidades reportadas
        for producto, cantidad_actual in inventario_actual.items():
            cantidad_reportada = float(request.form.get(f'cantidad_{producto}', 0))
            diferencia = cantidad_actual - cantidad_reportada
            resultados_auditoria[producto] = {
                "reportada": cantidad_reportada,
                "diferencia": diferencia
            }

            # Registrar la auditoría en el historial
            registrar_historial(agente_nombre, "auditoria", producto, cantidad_reportada)

        # Generar el PDF
        pdf_output = generar_pdf(agente_nombre, inventario_actual, resultados_auditoria)

        # Devolver el PDF como respuesta
        response = make_response(pdf_output)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=auditoria_{agente_nombre}.pdf'
        return response

    # Si es GET, mostrar el formulario de auditoría
    agente_nombre = request.args.get('agente_nombre')
    inventario = {}
    if agente_nombre and agente_nombre in inventarios:
        inventario = inventarios[agente_nombre]["inventario"]

    return render_template('auditoria.html', inventario=inventario, agente_nombre=agente_nombre)

# Ruta para ver inventarios
@app.route('/ver_inventarios', methods=['GET', 'POST'])
def ver_inventarios():
    agente_nombre = request.form.get('agente_nombre')
    inventario = {}
    ultima_modificacion = None
    historial = []

    if agente_nombre:
        if agente_nombre in inventarios:
            inventario = inventarios[agente_nombre]["inventario"]
            ultima_modificacion = inventarios[agente_nombre]["ultima_modificacion"]
            historial = inventarios[agente_nombre]["historial"]

    return render_template('ver_inventarios.html', inventario=inventario, agente_nombre=agente_nombre, ultima_modificacion=ultima_modificacion, historial=historial)

if __name__ == '__main__':
    app.run(debug=True)