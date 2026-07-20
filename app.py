import os
import sys
import io
import ssl
import tempfile
import warnings
import requests
from urllib3.exceptions import InsecureRequestWarning

# Reconfigure stdout/stderr on Windows to support UTF-8 console output for Tamil/Telugu/Spanish
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Globally disable SSL certificate verification to handle corporate firewalls/proxies
warnings.simplefilter('ignore', InsecureRequestWarning)

original_request = requests.Session.request
def patched_request(self, method, url, **kwargs):
    kwargs['verify'] = False
    return original_request(self, method, url, **kwargs)
requests.Session.request = patched_request

ssl._create_default_https_context = ssl._create_unverified_context

import gradio as gr
from deep_translator import GoogleTranslator
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import google.generativeai as genai

# Supported Languages configurations
LANGUAGES = {
    "English": {"code": "en", "sr_code": "en-US"},
    "Telugu": {"code": "te", "sr_code": "te-IN"},
    "Tamil": {"code": "ta", "sr_code": "ta-IN"},
    "Spanish": {"code": "es", "sr_code": "es-ES"},
    "French": {"code": "fr", "sr_code": "fr-FR"}
}

def translate_text(text, source_lang, target_lang):
    """Translates text from source language to target language."""
    if not text or not text.strip():
        return ""
    src_code = LANGUAGES[source_lang]["code"]
    tgt_code = LANGUAGES[target_lang]["code"]
    try:
        translated = GoogleTranslator(source=src_code, target=tgt_code).translate(text)
        return translated
    except Exception as e:
        return f"Translation error: {str(e)}"

def text_to_speech(text, lang):
    """Converts text to speech and returns the path to the temporary audio file."""
    if not text or not text.strip() or "error" in text.lower():
        return None
    lang_code = LANGUAGES[lang]["code"]
    try:
        tts = gTTS(text=text, lang=lang_code, slow=False)
        fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        tts.save(temp_path)
        return temp_path
    except Exception as e:
        print(f"TTS error: {str(e)}")
        return None

def speech_to_text(audio_path, source_lang):
    """Transcribes an audio file in the source language to text."""
    if not audio_path:
        return "No audio recorded"
    
    sr_code = LANGUAGES[source_lang]["sr_code"]
    recognizer = sr.Recognizer()
    
    wav_path = audio_path
    temp_wav_created = False
    
    try:
        # Gradio microphone recordings can be WebM, OGG, or WAV depending on the browser.
        # We standardise to WAV using pydub so speech_recognition can read it.
        if not audio_path.lower().endswith(".wav"):
            temp_wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
            os.close(temp_wav_fd)
            audio = AudioSegment.from_file(audio_path)
            audio.export(wav_path, format="wav")
            temp_wav_created = True
            
        with sr.AudioFile(wav_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language=sr_code)
            return text
    except sr.UnknownValueError:
        return "Speech was unintelligible. Please speak clearly into the microphone."
    except sr.RequestError as e:
        return f"Could not request results from Speech Recognition service: {e}"
    except Exception as e:
        return f"Error during transcription: {str(e)}"
    finally:
        # Cleanup temporary WAV file if we converted it
        if temp_wav_created and os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception as e:
                print(f"Failed to delete temp WAV file: {e}")

def text_to_text_with_audio(text, source_lang, target_lang):
    """Helper to perform text translation and generate corresponding pronunciation audio."""
    translation = translate_text(text, source_lang, target_lang)
    if translation.startswith("Translation error:"):
        return translation, None
    audio_output = text_to_speech(translation, target_lang)
    return translation, audio_output

def voice_to_voice(audio_path, source_lang, target_lang):
    """Helper to transcribe source audio, translate the text, and generate target audio."""
    if not audio_path:
        return "No audio recorded", "No translation", None
    
    # 1. Transcribe source audio
    transcription = speech_to_text(audio_path, source_lang)
    
    # Stop processing if speech recognition failed with error or empty result
    if (transcription.startswith("Error") or 
        "unintelligible" in transcription.lower() or 
        "could not request" in transcription.lower()):
        return transcription, "Transcription failed, translation aborted.", None
        
    # 2. Translate text
    translation = translate_text(transcription, source_lang, target_lang)
    if translation.startswith("Translation error:"):
        return transcription, translation, None
        
    # 3. Generate translated speech
    audio_output = text_to_speech(translation, target_lang)
    
    return transcription, translation, audio_output

def ask_gemini_ai(api_key, text_query, voice_query, input_mode, communication_lang):
    """Queries Gemini AI, gets response in selected language, and generates speech audio."""
    # 1. Determine which API key to use
    effective_key = api_key.strip() if api_key else os.environ.get("GEMINI_API_KEY")
    if not effective_key:
        return (
            "API Key missing",
            "Please configure your Gemini API Key in the field above or set it as a GEMINI_API_KEY environment variable. Get a free key at https://aistudio.google.com/",
            None
        )
    
    # 2. Get User Prompt
    transcription = ""
    if input_mode == "Voice Input":
        if not voice_query:
            return "No audio recorded", "Please record your voice first by clicking on the microphone.", None
        transcription = speech_to_text(voice_query, communication_lang)
        if (transcription.startswith("Error") or 
            "unintelligible" in transcription.lower() or 
            "could not request" in transcription.lower()):
            return transcription, "Transcription failed. Could not ask AI.", None
        prompt = transcription
    else:
        if not text_query or not text_query.strip():
            return "", "Please type a question first.", None
        prompt = text_query
        transcription = prompt

    # 3. Query Gemini
    try:
        genai.configure(api_key=effective_key)
        
        # System instructions to enforce language constraints
        system_instruction = (
            f"You are a helpful AI assistant. The user is communicating in {communication_lang}. "
            f"You MUST answer their question directly, accurately, and ONLY in {communication_lang}. "
            f"Do not translate your response to English or any other language unless explicitly requested. "
            f"Keep your answers concise, clear, and natural."
        )
        
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=system_instruction
        )
        
        response = model.generate_content(prompt)
        ai_response_text = response.text.strip()
    except Exception as e:
        return transcription, f"Gemini API Error: {str(e)}", None

    # 4. Convert AI response text to speech
    audio_output = text_to_speech(ai_response_text, communication_lang)
    
    return transcription, ai_response_text, audio_output

# Gradio Interface Styling
theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="blue",
    neutral_hue="slate"
)

css = """
.title-container {
    text-align: center;
    background: linear-gradient(135deg, #4f46e5 0%, #2563eb 100%);
    padding: 30px;
    border-radius: 12px;
    color: white;
    margin-bottom: 25px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}
.title-container h1 {
    font-size: 2.8rem;
    font-weight: 800;
    margin: 0;
    letter-spacing: -0.025em;
}
.title-container p {
    font-size: 1.2rem;
    margin-top: 10px;
    opacity: 0.95;
    font-weight: 400;
}
"""

with gr.Blocks() as demo:
    gr.HTML("""
        <div class="title-container">
            <h1>🌐 PolyGlot Voice & Text AI Translator</h1>
            <p>Translate languages & ask AI questions instantly in English, Telugu (తెలుగు), Tamil (தமிழ்), Spanish (Español), and French (Français)</p>
        </div>
    """)
    
    with gr.Tabs():
        # Tab 1: Text Translation
        with gr.Tab("📝 Text Translator"):
            with gr.Row():
                with gr.Column(scale=1):
                    src_lang_text = gr.Dropdown(
                        choices=list(LANGUAGES.keys()),
                        value="English",
                        label="Source Language"
                    )
                    input_text = gr.Textbox(
                        lines=5,
                        placeholder="Type text here to translate...",
                        label="Enter Text"
                    )
                with gr.Column(scale=1):
                    tgt_lang_text = gr.Dropdown(
                        choices=list(LANGUAGES.keys()),
                        value="Spanish",
                        label="Target Language"
                    )
                    output_text = gr.Textbox(
                        lines=5,
                        label="Translated Text",
                        interactive=False
                    )
                    output_audio_text = gr.Audio(
                        label="Listen to Translation",
                        type="filepath",
                        interactive=False
                    )
            
            with gr.Row():
                btn_translate = gr.Button("Translate Text", variant="primary", size="lg")
                btn_clear_text = gr.Button("Clear All", size="lg")
                
            btn_translate.click(
                fn=text_to_text_with_audio,
                inputs=[input_text, src_lang_text, tgt_lang_text],
                outputs=[output_text, output_audio_text]
            )
            
            def clear_text_fields():
                return "", "", None
                
            btn_clear_text.click(
                fn=clear_text_fields,
                inputs=[],
                outputs=[input_text, output_text, output_audio_text]
            )
            
        # Tab 2: Voice Translation (Voice-to-Voice)
        with gr.Tab("🎙️ Voice Translator"):
            with gr.Row():
                with gr.Column(scale=1):
                    src_lang_voice = gr.Dropdown(
                        choices=list(LANGUAGES.keys()),
                        value="English",
                        label="Source Language (Language you are speaking)"
                    )
                    input_voice = gr.Audio(
                        sources=["microphone"],
                        type="filepath",
                        label="Record Voice (Click microphone, speak, and click stop)"
                    )
                    transcribed_text = gr.Textbox(
                        lines=3,
                        label="Transcribed Text (Detected from Voice)",
                        interactive=False
                    )
                with gr.Column(scale=1):
                    tgt_lang_voice = gr.Dropdown(
                        choices=list(LANGUAGES.keys()),
                        value="Spanish",
                        label="Target Language (Language to translate to)"
                    )
                    output_translated_voice = gr.Textbox(
                        lines=3,
                        label="Translated Text",
                        interactive=False
                    )
                    output_audio_voice = gr.Audio(
                        label="Listen to Translated Voice",
                        type="filepath",
                        interactive=False
                    )
            
            with gr.Row():
                btn_voice = gr.Button("Translate Voice", variant="primary", size="lg")
                btn_clear_voice = gr.Button("Clear All", size="lg")
                
            btn_voice.click(
                fn=voice_to_voice,
                inputs=[input_voice, src_lang_voice, tgt_lang_voice],
                outputs=[transcribed_text, output_translated_voice, output_audio_voice]
            )
            
            def clear_voice_fields():
                return None, "", "", None
                
            btn_clear_voice.click(
                fn=clear_voice_fields,
                inputs=[],
                outputs=[input_voice, transcribed_text, output_translated_voice, output_audio_voice]
            )

        # Tab 3: AI Assistant (Question answering in selected language)
        with gr.Tab("🤖 AI Assistant"):
            gr.Markdown("### Ask Gemini AI anything by typing or speaking in your preferred language and get answers read back to you!")
            
            with gr.Row():
                with gr.Column(scale=1):
                    api_key_input = gr.Textbox(
                        label="Gemini API Key (Leave blank if already set in system environment variables)",
                        placeholder="Paste your Gemini API key (AIzaSy...) here...",
                        type="password"
                    )
                    ai_lang = gr.Dropdown(
                        choices=list(LANGUAGES.keys()),
                        value="English",
                        label="Communication Language (Speak/Type and Receive answers in this language)"
                    )
                    ai_input_mode = gr.Radio(
                        choices=["Text Input", "Voice Input"],
                        value="Text Input",
                        label="Choose Input Mode"
                    )
                    
                    text_input_group = gr.Textbox(
                        lines=4,
                        placeholder="Type your question here...",
                        label="Type Your Question",
                        visible=True
                    )
                    
                    voice_input_group = gr.Audio(
                        sources=["microphone"],
                        type="filepath",
                        label="Record Your Question (Click mic to record, stop when done)",
                        visible=False
                    )
                
                with gr.Column(scale=1):
                    ai_transcription_output = gr.Textbox(
                        label="Transcribed Question (Detected from Voice)",
                        interactive=False
                    )
                    ai_text_output = gr.Textbox(
                        lines=6,
                        label="AI Response Text",
                        interactive=False
                    )
                    ai_audio_output = gr.Audio(
                        label="Listen to AI Response Voice",
                        type="filepath",
                        interactive=False
                    )
            
            with gr.Row():
                btn_ask_ai = gr.Button("Ask AI", variant="primary", size="lg")
                btn_clear_ai = gr.Button("Clear All", size="lg")
                
            # Manage toggle visibility between text input and voice input
            def toggle_input_visibility(mode):
                if mode == "Text Input":
                    return gr.update(visible=True), gr.update(visible=False)
                else:
                    return gr.update(visible=False), gr.update(visible=True)
            
            ai_input_mode.change(
                fn=toggle_input_visibility,
                inputs=[ai_input_mode],
                outputs=[text_input_group, voice_input_group]
            )
            
            btn_ask_ai.click(
                fn=ask_gemini_ai,
                inputs=[api_key_input, text_input_group, voice_input_group, ai_input_mode, ai_lang],
                outputs=[ai_transcription_output, ai_text_output, ai_audio_output]
            )
            
            def clear_ai_fields():
                return "", None, "", "", None
                
            btn_clear_ai.click(
                fn=clear_ai_fields,
                inputs=[],
                outputs=[text_input_group, voice_input_group, ai_transcription_output, ai_text_output, ai_audio_output]
            )

if __name__ == "__main__":
    # Launch Gradio server
    demo.launch(server_name="127.0.0.1", server_port=7860, share=False, theme=theme, css=css)
