from flask import Flask, render_template, request, jsonify, session, url_for
import requests
import os
import re
import json
import pyttsx3
import time

# --- Configuración de Gemini ---
API_KEY = "AIzaSyDPdkgtN6KvgwqmnVZ__x1h7XlkOxRCc6s" # <--- YOUR PROVIDED API KEY
GEMINI_MODEL = 'gemini-2.0-flash'
API_ENDPOINT_GEMINI = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={API_KEY}'

DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL = 512
MAX_CONTINUATION_ATTEMPTS = 10

app = Flask(__name__)
app.secret_key = os.urandom(24)

if not os.path.exists('static'):
    os.makedirs('static')
if not os.path.exists('static/audio'):
    os.makedirs('static/audio')

tts_engine = None
try:
    tts_engine = pyttsx3.init()
except Exception as e:
    print(f"Error al inicializar pyttsx3 globalmente: {e}. TTS no disponible.")
    tts_engine = None

def clean_gemini_response(text):
    text = text.strip()
    text = re.sub(r"^---\s*INICIO DEL GUION\s*---\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\n?---\s*FIN DEL GUION\s*---$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^\s*SEGMENTO\s*\d*[:\-\s]*.*?\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^\s*(INTRODUCCIÓN|CONCLUSIÓN|OUTRO)[:\-\s]*.*?\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\((INTRO|TRANSICIÓN|OUTRO) MUSICAL.*?\)\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\[SFX:.*?\]\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"\(SFX:.*?.\)\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"Como modelo de lenguaje AI,?.*?útil\.\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"Como IA,?.*?útil\.\n?", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"Claro, aquí tienes.*?podcast.*?\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"Aquí tienes un borrador.*?\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"Espero que esto te sirva.*?\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"Este es solo un ejemplo.*?\n", "", text, flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r'\n\s*\n', '\n\n', text)
    text = text.strip()
    return text

def generate_audio_file(text_to_speak, filename_base="podcast_script"):
    global tts_engine
    if not tts_engine:
        print("Motor TTS no inicializado. Intentando reinicializar...")
        try:
            tts_engine = pyttsx3.init()
            if not tts_engine:
                 print("Fallo al reinicializar motor TTS.")
                 return None
            print("Motor TTS reinicializado con éxito para generar audio.")
        except Exception as e:
            print(f"Error al reinicializar pyttsx3 en generate_audio_file: {e}")
            tts_engine = None
            return None
    try:
        timestamp = int(time.time())
        safe_filename_base = re.sub(r'[^\w\s-]', '', filename_base).strip().replace(' ', '_')
        if not safe_filename_base: safe_filename_base = "podcast_audio"
        audio_filename = f"{safe_filename_base}_{timestamp}.mp3"
        audio_filepath = os.path.join('static', 'audio', audio_filename)
        print(f"Generando audio: {audio_filepath} con {len(text_to_speak.split())} palabras.")
        text_to_speak_cleaned_for_tts = ''.join(c for c in text_to_speak if c.isprintable() or c in '\n\r\t')
        tts_engine.save_to_file(text_to_speak_cleaned_for_tts, audio_filepath)
        tts_engine.runAndWait()
        print(f"Audio guardado: {audio_filepath}")
        return url_for('static', filename=f'audio/{audio_filename}', _external=True)
    except RuntimeError as re_err:
        print(f"RuntimeError al generar audio: {re_err}")
        try:
            print("Intentando reinicialización completa del motor TTS por RuntimeError...")
            tts_engine = pyttsx3.init() # Re-inicializar
            print("Motor TTS reinicializado tras RuntimeError.")
        except Exception as init_e:
            print(f"Error crítico al reinicializar motor TTS tras RuntimeError: {init_e}")
            tts_engine = None
        return None
    except Exception as e:
        print(f"Error general al generar audio: {e}")
        return None

def construct_podcast_prompt_ultra_simplified(title, theme, word_count):
    prompt = f"Actúa como un locutor de radio profesional y guionista de podcasts experto. Tu tarea es crear el contenido hablado para un episodio de podcast. El resultado debe ser un texto limpio, natural, coherente y listo para ser leído en voz alta sin ninguna modificación adicional.\n\n"
    prompt += f"**Título de Referencia (no lo anuncies explícitamente al inicio a menos que encaje orgánicamente en una introducción natural):** \"{title}\"\n"
    prompt += f"**Tema Principal a Desarrollar en Profundidad:**\n{theme}\n\n"
    prompt += f"**Longitud del Contenido Hablado:** El objetivo es generar un monólogo o narración de aproximadamente **{word_count} palabras**. Es CRUCIAL que te esfuerces por alcanzar esta longitud desarrollando el tema con suficiente detalle, ejemplos, y elaboración. La extensión es un requisito primordial.\n\n"
    prompt += f"**Directrices Esenciales para el Guion (Solo el Texto Hablado):**\n"
    prompt += f"1.  **ABSOLUTAMENTE NINGUNA ETIQUETA, ANOTACIÓN O METATEXTO:** No incluyas 'SEGMENTO X', 'INTRO', 'OUTRO', 'TRANSICIÓN', '[SFX...]', '(Música...)', 'FIN DEL GUION', o cualquier otra indicación que no sea parte del diálogo o narración real que una persona diría.\n"
    prompt += f"2.  **INICIO DIRECTO Y ATRAPANTE:** Comienza el guion como si ya estuvieras en el aire, captando el interés del oyente desde la primera frase. Evita introducciones genéricas de 'bienvenidos al podcast'.\n"
    prompt += f"3.  **LENGUAJE FLUIDO Y CONVERSACIONAL:** Utiliza un tono natural y un lenguaje que suene como una conversación, no como un texto formal leído. Adapta el tono al tema de forma natural.\n"
    prompt += f"4.  **ESTRUCTURA ORGÁNICA Y COHERENTE:** Desarrolla el tema principal con un flujo lógico y natural. Utiliza párrafos para marcar pausas o cambios de idea en el habla, asegurando transiciones suaves entre las ideas principales.\n"
    prompt += f"5.  **CONCLUSIÓN NATURAL E INTEGRADA:** Finaliza el contenido de manera coherente y satisfactoria, sin frases abruptas como 'Fin del guion'.\n\n"
    prompt += f"Genera AHORA el contenido hablado para este episodio de podcast, enfocándote en la naturalidad, la longitud solicitada y la pureza del texto para una lectura directa:\n"
    return prompt

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/generate_podcast', methods=['POST'])
def generate_podcast_route():
    data = request.get_json()
    print(f"Datos recibidos para generar podcast: {data}")

    podcast_title = data.get('title', 'Podcast Generado')
    podcast_theme = data.get('theme')
    podcast_words_str = data.get('words', '800')

    if not podcast_theme:
        return jsonify({'error': "El tema del podcast es obligatorio."}), 400
    try:
        podcast_words_int = int(podcast_words_str)
        if not (50 <= podcast_words_int <= 20000):
            return jsonify({'error': "La cantidad de palabras debe estar entre 50 y 20000."}), 400
    except ValueError:
        return jsonify({'error': "La cantidad de palabras debe ser un número."}), 400

    user_constructed_prompt = construct_podcast_prompt_ultra_simplified(
        podcast_title, podcast_theme, podcast_words_int
    )
    print(f"Prompt Ultra-Simplificado (primeros 500 chars):\n{user_constructed_prompt[:500]}...")

    full_bot_reply_parts = []
    history_for_this_gemini_sequence = [{"role": "user", "parts": [{"text": user_constructed_prompt}]}]
    attempts = 0
    last_finish_reason = None
    audio_url_for_response = None

    while attempts < MAX_CONTINUATION_ATTEMPTS:
        attempts += 1
        print(f"Attempt {attempts}/{MAX_CONTINUATION_ATTEMPTS} to Gemini (Max tokens: {DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL})...")
        payload = {
            "contents": history_for_this_gemini_sequence,
            "generationConfig": { "temperature": 0.7, "maxOutputTokens": DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL, "topP": 0.95, "topK": 40 },
            "safetySettings": [ {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                               {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                               {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                               {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}]
        }
        headers = {'Content-Type': 'application/json'}

        try:
            response = requests.post(API_ENDPOINT_GEMINI, headers=headers, json=payload, timeout=240)
            response.raise_for_status()
            response_json = response.json()

            if response_json.get("candidates") and len(response_json["candidates"]) > 0:
                candidate = response_json["candidates"][0]
                last_finish_reason = candidate.get("finishReason")
                print(f"Candidate finishReason: {last_finish_reason}")

                if candidate.get("content") and candidate["content"].get("parts") and \
                   len(candidate["content"]["parts"]) > 0 and candidate["content"]["parts"][0].get("text"):
                    bot_reply_chunk_raw = candidate["content"]["parts"][0]["text"]
                    full_bot_reply_parts.append(bot_reply_chunk_raw.strip())
                    print(f"Chunk received (reason: {last_finish_reason}): {bot_reply_chunk_raw.strip()[:100]}...")
                    history_for_this_gemini_sequence.append({"role": "model", "parts": [{"text": bot_reply_chunk_raw}]})

                    if last_finish_reason == "MAX_TOKENS":
                        continuation_instruction = "Perfecto, continúa la narración o el diálogo del podcast exactamente desde donde lo dejaste, manteniendo el mismo flujo y el objetivo de longitud total. La transición debe ser imperceptible. No repitas nada. Proporciona la siguiente porción del contenido hablado."
                        history_for_this_gemini_sequence.append({"role": "user", "parts": [{"text": continuation_instruction}]})
                        print("Automatically asking to continue due to MAX_TOKENS...")
                    else:
                        print(f"Model stopped for reason: {last_finish_reason}. Ending continuation loop.")
                        break
                else: 
                    print(f"Warning: Candidate received but no text content. Finish reason: {last_finish_reason}.")
                    if last_finish_reason != "MAX_TOKENS": break
            elif response_json.get("promptFeedback") and response_json["promptFeedback"].get("blockReason"):
                return jsonify({'error': f"Generación bloqueada por seguridad: {response_json['promptFeedback']['blockReason']}"}), 400
            else: 
                return jsonify({'error': "Respuesta inesperada o vacía de la IA."}), 500
        except requests.exceptions.HTTPError as http_err:
             error_detail = http_err.response.text if http_err.response else "No details"
             print(f"HTTP Error from Gemini: {http_err} - {error_detail}")
             return jsonify({'error': f"Error de API Gemini (HTTP {http_err.response.status_code if http_err.response else 'N/A'})."}), 500
        except requests.exceptions.RequestException as e:
            print(f"Request Exception: {e}")
            return jsonify({'error': "Error de conexión con el servicio de IA."}), 500
        except Exception as e:
            print(f"Error inesperado durante la generación: {e}")
            import traceback; traceback.print_exc()
            return jsonify({'error': "Error interno del servidor durante la generación."}), 500

    raw_joined_script = "\n\n".join(full_bot_reply_parts)
    final_script_text = clean_gemini_response(raw_joined_script)

    if not final_script_text.strip():
        return jsonify({'script': "No se pudo generar el guion. Intenta ajustar tu solicitud.", 'audio_url': None, 'word_count_generated': 0, 'title': podcast_title})

    audio_url_for_response = None
    if final_script_text.strip() and tts_engine: # Solo generar audio si hay texto y tts_engine está ok
        audio_url_for_response = generate_audio_file(final_script_text, filename_base=podcast_title[:30])
    elif not tts_engine:
        print("No se generó audio porque el motor TTS no está disponible.")


    generated_word_count = len(final_script_text.split())
    print(f"Guion final generado. Palabras: {generated_word_count}. Audio: {audio_url_for_response}")

    return jsonify({
        'script': final_script_text,
        'audio_url': audio_url_for_response,
        'word_count_generated': generated_word_count,
        'title': podcast_title
    })

if __name__ == '__main__':
    print("===================================================================")
    print("          🎙️  GEMINI PODCAST PRO (ULTRA-SIMPLE) - FLASK 🎙️    ")
    print("===================================================================")
    api_key_display = API_KEY
    if len(api_key_display) > 8: api_key_display = f"{api_key_display[:4]}...{api_key_display[-4:]}"
    print(f"API Key de Gemini: {api_key_display}")
    if not tts_engine: print("ADVERTENCIA: Motor TTS (pyttsx3) no inicializado. El audio no se generará.")
    else: print("Motor TTS (pyttsx3) inicializado con éxito.")
    print(f"Modelo Gemini: {GEMINI_MODEL}")
    print(f"Max Tokens/Llamada: {DEFAULT_MAX_OUTPUT_TOKENS_PER_CALL}, Max Continuaciones: {MAX_CONTINUATION_ATTEMPTS}")
    print("Servidor iniciado en http://127.0.0.1:5000")
    print("-------------------------------------------------------------------")
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
