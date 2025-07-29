#pip install streamlit pydub openai-whisper googletrans==4.0.0-rc1 gtts

import streamlit as st
import tempfile
import os

from typing import List
from pydub import AudioSegment

# You can use openai-whisper, transformers, or any cloud API for STT and TTS
import whisper
from googletrans import Translator

# Supported languages (ISO codes and names)
LANGUAGES = {
    "English": "en",
    "Hindi": "hi",
    "Spanish": "es",
    "French": "fr",
    "German": "de"
}

st.title("🎤 Voice Translator")

st.write("Translate your voice from one language to another. You can record or upload an audio file.")

# Language selection
col1, col2 = st.columns(2)
with col1:
    input_lang = st.selectbox("Select input language", list(LANGUAGES.keys()), key="input_lang")
with col2:
    output_lang = st.selectbox(
        "Select output language",
        [lang for lang in LANGUAGES.keys() if lang != input_lang],
        key="output_lang"
    )

# Audio input
st.subheader("Step 1: Provide your speech")
audio_file = st.file_uploader("Upload an audio file (wav/mp3/m4a)", type=["wav", "mp3", "m4a"])
recorded_audio = st.audio_input("Or record your voice", key="recorder")

audio_bytes = None
if audio_file is not None:
    audio_bytes = audio_file.read()
    st.audio(audio_bytes, format="audio/wav")
elif recorded_audio is not None:
    audio_bytes = recorded_audio
    st.audio(audio_bytes, format="audio/wav")

if audio_bytes:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    # Step 2: Speech to Text
    st.subheader("Step 2: Transcribe speech")
    st.info("Transcribing...")
    model = whisper.load_model("base")
    result = model.transcribe(tmp_path, language=LANGUAGES[input_lang])
    text = result["text"]
    st.success(f"Transcribed Text: {text}")

    # Step 3: Translate
    st.subheader("Step 3: Translate text")
    translator = Translator()
    translated = translator.translate(text, src=LANGUAGES[input_lang], dest=LANGUAGES[output_lang])
    st.success(f"Translated Text: {translated.text}")

    # Step 4: Text to Speech (TTS)
    st.subheader("Step 4: Listen to translation")
    try:
        from gtts import gTTS
        tts = gTTS(translated.text, lang=LANGUAGES[output_lang])
        tts_fp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        tts.save(tts_fp.name)
        st.audio(tts_fp.name, format="audio/mp3")
    except Exception as e:
        st.warning("Text-to-speech not available for this language.")

    # Cleanup
    os.remove(tmp_path)
else:
    st.info("Please upload or record an audio file to translate.")