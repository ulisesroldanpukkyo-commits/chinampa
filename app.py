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
# Nota: He cambiado a gemini-1.5-flash porque tiene una cuota gratuita más amplia que gemini-3
model = genai.GenerativeModel('gemini-3-flash-preview') 

app = Flask(__name__)

# --- PROMPT MEJORADO: Modo Doctor y Cuidados Rápidos ---
PROMPT_PLANTAS = """
Analiza la imagen de esta planta como un experto botánico y doctor de plantas. 
Si el objeto no es una planta, responde únicamente con {"error": "No se detectó una planta en la imagen"}.

Si es una planta, responde ESTRICTAMENTE en formato JSON con esta estructura:
{
  "nombre_cientifico": "Nombre en latín",
  "nombre_comun": "Nombre más popular",
  "salud": "Estado general (Sana, Enferma, Estresada, o Plaga detectada)",
  "advertencias": "Analiza manchas, hongos o insectos. Si está sana, di que no se detectan plagas.",
  "sol": "Horas de sol o tipo de luz (ej. Sol directo 6h)",
  "riego": "Frecuencia estimada (ej. Cada 10 días)",
  "sustrato": "Tipo de tierra recomendada (ej. Sustrato drenante mineral)",
  "consejos": [
    "Consejo de riego",
    "Consejo de ubicación",
    "Tip de experto Chinampa"
  ]
}
No añadas texto extra, solo el JSON puro.
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
        # Abrimos la imagen
        img = Image.open(file.stream)
        
        # --- BLOQUE DE CONTROL DE ERRORES AJUSTADO ---
        try:
            # Petición a la IA
            response = model.generate_content([PROMPT_PLANTAS, img])
            
            # Limpieza de la respuesta para asegurar que sea JSON válido
            raw_text = response.text.strip()
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
            plant_data = json.loads(raw_text)
            
            # Si la IA responde con un error de "No es planta"
            if "error" in plant_data:
                return jsonify({"ok": False, "error": plant_data["error"]})
                
            return jsonify({"ok": True, "result": plant_data})

        except Exception as e:
            error_str = str(e)
            print(f"DEBUG: Error detectado: {error_str}")
            
            # Control específico para el error 429 (Cuota excedida)
            if "429" in error_str or "quota" in error_str.lower():
                return jsonify({
                    "ok": False, 
                    "error": "La IA está saturada por hoy (Límite alcanzado). ¡Intenta de nuevo en un momento o mañana!"
                }), 429
            
            return jsonify({"ok": False, "error": "La IA está saturada por hoy. ¡Intenta de nuevo en un momento o mañana!"}), 500
        # --------------------------------------------

    except Exception as e:
        print(f"Error de lectura de archivo: {e}")
        return jsonify({"ok": False, "error": "No se pudo leer la imagen enviada"}), 400

if __name__ == "__main__":
    # Importante: host 0.0.0.0 para que sea visible en tu red local y ngrok
    app.run(host="0.0.0.0", port=5000, debug=True)