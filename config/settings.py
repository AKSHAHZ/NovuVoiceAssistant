# config/settings.py
# Central configuration for Novu

# --- Personality Profiles ---
# Each profile shapes how Novu responds tonally and stylistically.
PERSONALITY_PROFILES = {
    "friendly": {
        "tone": "warm and conversational",
        "traits": "encouraging, empathetic, uses casual language",
    },
    "formal": {
        "tone": "professional and precise",
        "traits": "structured, neutral, avoids contractions",
    },
    "calm": {
        "tone": "soft and reassuring",
        "traits": "slow-paced, gentle, avoids overwhelming the user",
    },
}

# Active personality (can be changed at runtime)
ACTIVE_PERSONALITY = "friendly"

# --- Emotion Detection ---
EMOTION_MODEL = "j-hartmann/emotion-english-distilroberta-base"

# --- Speech-to-Text ---
VOSK_MODEL_PATH = "models/vosk-model-small-en-us"
VOSK_SAMPLE_RATE = 16000

# --- Text-to-Speech ---
TTS_RATE  = 195          # default words per minute (say -r flag)
TTS_VOICE = "Samantha"   # macOS voice — run: say -v '?' to list all

# --- Local LLM (Ollama) ---
OLLAMA_MODEL = "llama3.1:8b"   # run: ollama pull llama3.1:8b  (better quality, ~5 GB)

# --- Audio (VAD handles recording length automatically) ---
AUDIO_CHANNELS = 1
