import os
import io
import json
import google.generativeai as genai
from PIL import Image
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

# Carga de variables de entorno
load_dotenv()

# Configuración de API Key
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    print("❌ ERROR: No se encontró la variable GEMINI_API_KEY en el archivo .env")
else:
    genai.configure(api_key=api_key)
    print("✅ API Key configurada correctamente")

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
    
    try:
        # --- OPTIMIZACIÓN DE MEMORIA CON PILLOW ---
        # Abrimos la imagen y la redimensionamos para evitar el SIGKILL en Render
        img = Image.open(file.stream)
        img.thumbnail((800, 800))
        
        # Convertimos la imagen optimizada a bytes para enviarla a la IA
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=85)
        optimized_image = Image.open(img_byte_arr)

        # --- BLOQUE DE CONTROL DE ERRORES AJUSTADO ---
        try:
            # Petición a la IA con la imagen optimizada
            response = model.generate_content([PROMPT_PLANTAS, optimized_image])
            
            # Limpieza de la respuesta para asegurar que sea JSON válido
            raw_text = response.text.strip()
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
            data = json.loads(raw_text)
            
            # --- LÓGICA DE RESPUESTA DUAL (Planta vs No Planta) ---
            if "error" in data:
                return jsonify({
                    "ok": True, 
                    "es_planta": False, 
                    "mensaje": data.get("identificado_como", "Objeto desconocido"),
                    "bromita": data.get("consejo_chinampa", "¡Ups! Esto no necesita abono.")
                })
                
            # Caso: SÍ es una planta
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
                    "error": "La IA está saturada por hoy (Límite alcanzado). ¡Intenta de nuevo en un momento!"
                }), 429
            
            return jsonify({"ok": False, "error": "Error al procesar con la IA. Intenta de nuevo."}), 500

    except Exception as e:
        print(f"Error de lectura de archivo: {e}")
        return jsonify({"ok": False, "error": "No se pudo leer la imagen enviada"}), 400

if __name__ == "__main__":
    # Render asigna un puerto dinámico a través de la variable de entorno 'PORT'
    port = int(os.environ.get("PORT", 5000))
    # Importante: host 0.0.0.0 es obligatorio para que Render pueda redirigir el tráfico
    app.run(host="0.0.0.0", port=port)