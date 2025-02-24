from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from fpdf import FPDF
import pdfplumber
import re

app = Flask(__name__)
app.secret_key = 'tu_clave_secreta_aqui'

# Configuración de la base de datos SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///inventario.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Agente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(50), unique=True, nullable=False)
    inventario = db.relationship('Inventario', backref='agente', lazy=True)
    historial = db.relationship('Historial', backref='agente', lazy=True)

class Inventario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    agente_id = db.Column(db.Integer, db.ForeignKey('agente.id'), nullable=False)

class Historial(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.String(20), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)
    producto = db.Column(db.String(100), nullable=False)
    cantidad = db.Column(db.Float, nullable=False)
    agente_id = db.Column(db.Integer, db.ForeignKey('agente.id'), nullable=False)

with app.app_context():
    db.create_all()

def cargar_inventario_desde_pdf(pdf_file):
    try:
        text = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"

        inventario_pattern = re.compile(r'(\d+\.\d+)\s+Unid\s+([^\n]+?)\s+Grav\s+\d+%')
        matches = inventario_pattern.findall(text)

        inventario = {}
        for match in matches:
            cantidad = float(match[0])
            producto = match[1].strip()
            inventario[producto] = cantidad

        return inventario
    except Exception as e:
        print(f"Error al cargar el inventario desde el PDF: {str(e)}")
        return {}

# Función para registrar en el historial
def registrar_historial(agente_id, tipo, producto, cantidad):
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nuevo_registro = Historial(
        fecha=fecha,
        tipo=tipo,
        producto=producto,
        cantidad=cantidad,
        agente_id=agente_id
    )
    db.session.add(nuevo_registro)
    db.session.commit()

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

        # Buscar o crear el agente en la base de datos
        agente = Agente.query.filter_by(nombre=agente_nombre).first()
        if not agente:
            agente = Agente(nombre=agente_nombre)
            db.session.add(agente)
            db.session.commit()

        if 'inventarioFile' in request.files:
            pdf_file = request.files['inventarioFile']
            if pdf_file.filename != '':
                try:
                    inventario_pdf = cargar_inventario_desde_pdf(pdf_file)
                    for producto, cantidad in inventario_pdf.items():
                        # Buscar si el producto ya existe en el inventario del agente
                        item = Inventario.query.filter_by(producto=producto, agente_id=agente.id).first()
                        if item:
                            item.cantidad += cantidad
                        else:
                            nuevo_item = Inventario(producto=producto, cantidad=cantidad, agente_id=agente.id)
                            db.session.add(nuevo_item)
                        registrar_historial(agente.id, "agregado", producto, cantidad)
                    db.session.commit()
                    flash('Inventario cargado correctamente desde el PDF.', 'success')
                    return redirect(url_for('cargar_inventario'))
                except Exception as e:
                    flash(f'Error al procesar el PDF: {str(e)}', 'error')
                    return redirect(url_for('cargar_inventario'))

        # Carga manual
        producto = request.form.get('producto')
        cantidad = float(request.form.get('cantidad', 0))

        if producto and cantidad > 0:
            item = Inventario.query.filter_by(producto=producto, agente_id=agente.id).first()
            if item:
                item.cantidad += cantidad
            else:
                nuevo_item = Inventario(producto=producto, cantidad=cantidad, agente_id=agente.id)
                db.session.add(nuevo_item)
            registrar_historial(agente.id, "agregado", producto, cantidad)
            db.session.commit()
            flash('Inventario cargado correctamente de forma manual.', 'success')
            return redirect(url_for('cargar_inventario'))

    return render_template('cargar_inventario.html')

# Ruta para registrar ventas
@app.route('/ventas', methods=['GET', 'POST'])
def ventas():
    if request.method == 'POST':
        agente_nombre = request.form['agente_nombre']

        agente = Agente.query.filter_by(nombre=agente_nombre).first()
        if not agente:
            flash('Agente no encontrado.', 'error')
            return redirect(url_for('ventas'))

        if 'ventasFile' in request.files:
            pdf_file = request.files['ventasFile']
            if pdf_file.filename != '':
                try:
                    ventas_pdf = cargar_inventario_desde_pdf(pdf_file)  # <-- REVISAR ESTA FUNCIÓN
                    for producto, cantidad in ventas_pdf.items():
                        item = Inventario.query.filter_by(producto=producto, agente_id=agente.id).first()
                        if item:
                            if item.cantidad >= cantidad:
                                item.cantidad -= cantidad
                                registrar_historial(agente.id, "venta", producto, cantidad)
                                flash(f'Venta de {cantidad} unidades de {producto} registrada correctamente.', 'success')
                            else:
                                flash(f'No hay suficiente stock de {producto} para vender {cantidad} unidades.', 'error')
                        else:
                            flash(f'El producto {producto} no existe en el inventario del agente.', 'error')
                    db.session.commit()
                    return redirect(url_for('ventas'))
                except Exception as e:
                    flash(f'Error al procesar el PDF: {str(e)}', 'error')
                    return redirect(url_for('ventas'))

        # Carga manual
        producto = request.form.get('producto')
        cantidad = float(request.form.get('cantidad', 0))

        if producto and cantidad > 0:
            item = Inventario.query.filter_by(producto=producto, agente_id=agente.id).first()
            if item:
                if item.cantidad >= cantidad:
                    item.cantidad -= cantidad
                    registrar_historial(agente.id, "venta", producto, cantidad)
                    db.session.commit()
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

        agente = Agente.query.filter_by(nombre=agente_nombre).first()
        if not agente:
            flash('Agente no encontrado.', 'error')
            return redirect(url_for('auditoria'))

        # Obtener el inventario del agente
        inventario_actual = {item.producto: item.cantidad for item in Inventario.query.filter_by(agente_id=agente.id).all()}
        resultados_auditoria = {}

        # Procesar las cantidades reportadas
        for producto, cantidad_actual in inventario_actual.items():
            cantidad_reportada = float(request.form.get(f'cantidad_{producto}', 0))
            diferencia = cantidad_actual - cantidad_reportada
            resultados_auditoria[producto] = {
                "reportada": cantidad_reportada,
                "diferencia": diferencia
            }
            registrar_historial(agente.id, "auditoria", producto, cantidad_reportada)

        # Generar el PDF
        pdf_output = generar_pdf(agente_nombre, inventario_actual, resultados_auditoria)

        response = make_response(pdf_output)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=auditoria_{agente_nombre}.pdf'
        return response

    agente_nombre = request.args.get('agente_nombre')
    inventario = {}
    if agente_nombre:
        agente = Agente.query.filter_by(nombre=agente_nombre).first()
        if agente:
            inventario = {item.producto: item.cantidad for item in Inventario.query.filter_by(agente_id=agente.id).all()}

    return render_template('auditoria.html', inventario=inventario, agente_nombre=agente_nombre)

# Ruta para ver inventarios
@app.route('/ver_inventarios', methods=['GET', 'POST'])
def ver_inventarios():
    agente_nombre = request.form.get('agente_nombre')
    inventario = []
    ultima_modificacion = None
    historial = []

    if agente_nombre:
        agente = Agente.query.filter_by(nombre=agente_nombre).first()
        if agente:
            inventario = Inventario.query.filter_by(agente_id=agente.id).all()
            historial = Historial.query.filter_by(agente_id=agente.id).all()
            if historial:
                ultima_modificacion = historial[-1].fecha

    return render_template('ver_inventarios.html', inventario=inventario, agente_nombre=agente_nombre, ultima_modificacion=ultima_modificacion, historial=historial)

if __name__ == '__main__':
    app.run(debug=True)