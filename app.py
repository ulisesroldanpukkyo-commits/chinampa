import os
import io
import json
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify
import requests
from flask import Flask, render_template, send_from_directory, request, jsonify

# Carga de variables de entorno
load_dotenv()

# Configuración de API Key
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ ERROR: No se encontró la variable GEMINI_API_KEY en el archivo .env")
else:
    genai.configure(api_key=api_key)
    print("✅ API Key configurada correctamente")

# --- CONFIGURACIÓN ---
# Tu URL de Google Apps Script
URL_CONTADOR_SHEETS = "https://script.google.com/macros/s/AKfycbzdX28v04APfYA421OgZWrs0vujmdt_HV8xVNnDIXzPQ4su_KQ-YnXfrjhPsgvi-kQ/exec"

# Configuración del Modelo
model = genai.GenerativeModel('gemini-3-flash-preview') 

app = Flask(__name__)

# --- PROMPT MEJORADO: Modo Doctor y Validación de Plantas ---
PROMPT_PLANTAS = """
Analiza la imagen como un experto botánico y doctor de plantas de 'Chinampa'.

REGLA DE IDENTIFICACIÓN:
1. Si el objeto NO es una planta (es un animal, persona, objeto, etc.), responde ESTRICTAMENTE con este JSON:
{
  "error": "No es una planta",
  "identificado_como": "Nombre de lo que ves (ej. Un teclado, un gato, un humano)",
  "consejo_chinampa": "Un comentario breve y gracioso del Chinampero sobre por qué esto no es una planta."
}

2. Si SÍ es una planta, responde ESTRICTAMENTE en formato JSON con esta estructura:
{
  "nombre_cientifico": "Nombre en latín",
  "nombre_comun": "Nombre más popular",
  "salud": "Estado general (Sana, Enferma, Estresada, o Plaga)",
  "advertencias": "Analiza manchas, hongos o insectos. Si está sana, di que no se detectan plagas.",
  "sol": "Horas de sol o tipo de luz",
  "riego": "Frecuencia estimada",
  "sustrato": "Tipo de tierra recomendada",
  "consejos": [
    "Consejo de riego",
    "Consejo de ubicación",
    "Tip de experto Chinampa"
  ]
}

No añadas texto extra, ni bloques de código (```), solo el JSON puro.
"""

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/identify", methods=["POST"])
def identify():
    if "image" not in request.files: 
        return jsonify({"ok": False, "error": "No hay imagen"}), 400
    
    file = request.files["image"]
    
# --- DENTRO DE identify() EN app.py ---
    u_name = request.form.get("user_name", "N/A")
    u_email = request.form.get("user_email", "N/A")

    # Limpieza previa en Python
    if not u_name or u_name.strip() == "": u_name = "N/A"
    if not u_email or u_email.strip() == "": u_email = "N/A"
    try:
        # --- OPTIMIZACIÓN DE MEMORIA CON PILLOW ---
        img = Image.open(file)
        img.thumbnail((800, 800))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        img_byte_arr.seek(0)
        optimized_image = Image.open(img_byte_arr)

        # --- BLOQUE DE CONTROL DE ERRORES ---
        try:
            # Petición a la IA
            response = model.generate_content([PROMPT_PLANTAS, optimized_image])
            raw_text = response.text.strip()
            
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(raw_text)
            
            # Lógica Planta vs No Planta
            if "error" in data:
                return jsonify({
                    "ok": True, 
                    "es_planta": False, 
                    "mensaje": data.get("identificado_como", "Objeto desconocido"),
                    "bromita": data.get("consejo_chinampa", "¡Ups! Esto no necesita abono.")
                })
            
            # --- REGISTRO EN HISTÓRICO DE GOOGLE SHEETS ---
            try:
                payload = {
                    "user_name": u_name,
                    "user_email": u_email,
                    "nombre_comun": data.get("nombre_comun", "N/A"),
                    "nombre_cientifico": data.get("nombre_cientifico", "N/A"),
                    "sol": data.get("sol", "N/A"),
                    "riego": data.get("riego", "N/A"),
                    "sustrato": data.get("sustrato", "N/A"),
                    "consejos": " | ".join(data.get("consejos", [])) if isinstance(data.get("consejos"), list) else "N/A"
                }
                
                # Enviamos el payload con params para asegurar el tiro
                r = requests.post(URL_CONTADOR_SHEETS, json=payload, params=payload, timeout=10)
                print(f">>> GOOGLE RESPONDE: {r.text}")
            except Exception as e:
                print(f">>> ERROR EN ENVÍO: {e}")

            # Caso Éxito: SÍ es una planta
            return jsonify({
                "ok": True, 
                "es_planta": True, 
                "result": data
            })
        
        except Exception as e:
            error_str = str(e)
            print(f"DEBUG: Error detectado: {error_str}")
            if "429" in error_str or "quota" in error_str.lower():
                return jsonify({
                    "ok": False, 
                    "error": "Límite de la IA alcanzado. ¡Intenta en un momento!"
                }), 429
            return jsonify({"ok": False, "error": "Error al procesar con la IA."}), 500

    except Exception as e:
        print(f"Error de lectura: {e}")
        return jsonify({"ok": False, "error": "No se pudo leer la imagen"}), 400

       
# --- RUTA PARA VALIDACIÓN DE APP ANDROID ---
@app.route('/.well-known/assetlinks.json')
def serve_assetlinks():
    # Ruta absoluta hacia la carpeta .well-known dentro de static
    well_known_path = os.path.join(app.static_folder, '.well-known')
    return send_from_directory(well_known_path, 'assetlinks.json', mimetype='application/json')

# --- RUTA PARA EL MANIFEST (PWA) ---
@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(app.static_folder, 'manifest.json')
@app.route('/get_global_total')
def get_global_total():
    try:
        # Esto le pregunta a Google Sheets el número actual
        r = requests.get(URL_CONTADOR_SHEETS, timeout=10)
        return r.text
    except Exception as e:
        print(f"Error al consultar Google: {e}")
        return "0" # Valor por defecto si falla

if __name__ == "__main__":
    # Render asigna un puerto dinámico a través de la variable de entorno 'PORT'
    port = int(os.environ.get("PORT", 5000))
    # Importante: host 0.0.0.0 es obligatorio para que Render pueda redirigir el tráfico
    app.run(host="0.0.0.0", port=port)