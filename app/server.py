from flask import Flask, request, jsonify, abort
from flask_cors import CORS  # Importar CORS
from flasgger import Swagger
from app import create_app, db
from app.models import User, Task
from twilio.rest import Client
import threading
import time
import os
from dotenv import load_dotenv  # Importar dotenv para cargar .env
import jwt  # Importar JWT para manejo de tokens
from werkzeug.security import generate_password_hash, check_password_hash  # Para encriptar y verificar contraseñas

# Cargar las variables de entorno desde el archivo .env
load_dotenv()
SECRET_KEY = os.getenv('SECRET_KEY')

# Crear la aplicación Flask
app = create_app()

# Habilitar CORS para todas las rutas
CORS(app, resources={r"/*": {"origins": "*"}})  # Permitir todas las rutas y todos los orígenes

# Configurar Swagger con categorías organizadas
swagger = Swagger(app, template={
    "swagger": "2.0",
    "info": {
        "title": "Reporte.IA",
        "description": "API para gestionar usuarios, tareas y mensajes SMS.",
        "version": "1.0.0"
    },
    "host": "localhost:5000",
    "basePath": "/",
    "schemes": ["http"],
    "tags": [
        {"name": "Usuarios", "description": "Gestión de usuarios"},
        {"name": "Tareas", "description": "Gestión de tareas y countdown"},
        {"name": "Mensajes", "description": "Gestión y envío de mensajes SMS"},
        {"name": "Default", "description": "Rutas por defecto"}
    ]
})

# Diccionario para manejar los hilos activos
active_timers = {}

# Servicio real de envío de SMS usando Twilio
def send_sms(phone_number, message):
    """Envía un mensaje SMS utilizando Twilio."""
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        messaging_service_sid = os.getenv('TWILIO_MESSAGING_SERVICE_SID')

        client = Client(account_sid, auth_token)

        message_response = client.messages.create(
            messaging_service_sid=messaging_service_sid,
            body=message,
            to=phone_number
        )

        print(f"Mensaje enviado exitosamente con SID: {message_response.sid}")
        return message_response.sid
    except Exception as e:
        print(f"Error al enviar el mensaje: {e}")
        raise

# Función para manejar la cuenta regresiva
def countdown_timer(task_id):
    """Cuenta regresiva para enviar un mensaje SMS."""
    task = Task.query.get(task_id)
    if not task:
        return
    while task.countdown > 0:
        time.sleep(1)
        task.countdown -= 1
        db.session.commit()
    if task.countdown == 0:
        send_sms(task.user.phone_number, task.message)
        print(f"Mensaje enviado: {task.message}")

# Default: Ruta raíz
@app.route('/')
def home():
    """Endpoint de inicio de la API."""
    return jsonify({"message": "Bienvenido a la API de Reporte.IA"}), 200

# Usuarios: Crear un usuario
@app.route('/users', methods=['POST'])
def create_user():
    """Crear un nuevo usuario
    ---
    tags:
      - Usuarios
    parameters:
      - in: body
        name: body
        description: Datos necesarios para crear un usuario
        required: true
        schema:
          type: object
          properties:
            email:
              type: string
              example: usuario@example.com
            username:
              type: string
              example: usuario123
            password:
              type: string
              example: password123
            phone_number:
              type: string
              example: +123456789
    responses:
      201:
        description: Usuario creado exitosamente
      400:
        description: Faltan datos requeridos
    """
    data = request.get_json()
    if not data or 'email' not in data or 'username' not in data or 'password' not in data or 'phone_number' not in data:
        abort(400, "Faltan datos requeridos")
    hashed_password = generate_password_hash(data['password'], method='sha256')
    user = User(email=data['email'], username=data['username'], password=hashed_password, phone_number=data['phone_number'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201

# Usuarios: Inicio de sesión de usuario
@app.route('/login', methods=['POST'])
def login_user():
    """Iniciar sesión de usuario
    ---
    tags:
      - Usuarios
    """
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        abort(400, "Faltan datos requeridos")
    user = User.query.filter_by(username=data['username']).first()
    if not user or not check_password_hash(user.password, data['password']):
        abort(401, "Usuario o contraseña incorrectos")
    
    token = jwt.encode({"username": user.username}, SECRET_KEY, algorithm='HS256')
    return jsonify({"access_token": token, "token_type": "bearer"}), 200

# Mensajes: Enviar mensaje directo
@app.route('/messages', methods=['POST', 'OPTIONS'])
def send_message():
    """Enviar mensaje directo
    ---
    tags:
      - Mensajes
    """
    if request.method == 'OPTIONS':
        response = jsonify({"message": "OPTIONS habilitado."})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST, GET, OPTIONS, PUT, DELETE')
        return response, 200
    
    data = request.get_json()
    if not data or 'phone_number' not in data or 'message' not in data:
        abort(400, "Faltan datos requeridos (phone_number, message)")
    
    phone_number = data['phone_number']
    message_content = data['message']

    try:
        message_sid = send_sms(phone_number, message_content)
        return jsonify({"message": "Mensaje enviado exitosamente", "sid": message_sid}), 201
    except Exception as e:
        print(f"Error al enviar mensaje: {e}")
        abort(500, "Error interno al enviar el mensaje")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
