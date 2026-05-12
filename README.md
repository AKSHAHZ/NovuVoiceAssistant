# Novu — Emotion-Aware Voice Assistant

Novu is an offline, privacy-first voice assistant that detects and responds to human emotions in real time. It runs entirely on-device — no cloud APIs, no data leaving your machine.

Built as a final-year Computer Science Honours project.

---

## How It Works

Novu listens for a wake word, records your speech, infers your emotional state from both the words you say and the acoustics of how you say them, then generates a response calibrated to that emotion using a local large language model. The response is spoken back immediately using sentence-level streaming so there is no long pause before it starts talking.

```
Microphone → Wake Detection → VAD Recording → STT (Vosk)
    → Emotion Inference (text + acoustic) → LLM (Llama 3.1 8B via Ollama)
    → Streaming TTS (macOS say) → Speaker
```

---

## Features

- **Offline and private** — Vosk STT, Ollama LLM, and macOS TTS run entirely on-device
- **Emotion detection** — DistilRoBERTa (7-class) combined with Librosa acoustic energy for multi-modal inference
- **Adaptive personality** — three modes (Friendly, Formal, Calm) each with distinct system prompts and TTS pacing
- **Voice Activity Detection** — adaptive noise floor calibration before each listen so background noise is filtered out
- **Interrupt detection** — speak over Novu to stop it mid-sentence, with an echo gate that prevents self-interruption
- **Cross-session memory** — remembers your name and facts you tell it across sessions (stored locally in JSON)
- **Streaming TTS pipeline** — LLM tokens are split at sentence boundaries and synthesised in parallel so speech begins within ~1 second
- **Modern GUI** — customtkinter dark UI with animated orb, chat bubbles, live emotion/state indicators, and conversation export

---

## Tech Stack

| Component | Technology |
|---|---|
| Speech-to-Text | [Vosk](https://alphacephei.com/vosk/) (offline, KaldiRecognizer) |
| Emotion — Text | [j-hartmann/emotion-english-distilroberta-base](https://huggingface.co/j-hartmann/emotion-english-distilroberta-base) |
| Emotion — Acoustic | Librosa RMS energy |
| LLM | Llama 3.1 8B via [Ollama](https://ollama.com/) |
| Text-to-Speech | macOS `say` (neural Samantha voice) |
| GUI | customtkinter |
| Language | Python 3.11 |

---

## Installation

**Prerequisites:** macOS, Python 3.11, [Ollama](https://ollama.com/) installed and running.

```bash
git clone https://github.com/shahzadaakbar/Novu-Voice-Assistant.git
cd Novu-Voice-Assistant

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
brew install portaudio
```

Download the LLM:

```bash
ollama pull llama3.1:8b
```

Download the Vosk STT model and place it at `models/vosk-model-small-en-us-0.15/`:

```bash
mkdir -p models && cd models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip
cd ..
```

Grant microphone access when prompted (System Settings → Privacy & Security → Microphone → Terminal).

Then run:

```bash
python main.py
```

Say **"hi"**, **"hey Novu"**, or **"hello Novu"** to wake it up.

---

## Project Structure

```
novu/
├── main.py                    # Main pipeline and wake-word loop
├── modules/
│   ├── stt.py                 # Vosk STT + VAD with adaptive noise calibration
│   ├── tts.py                 # Streaming TTS pipeline with interrupt detection
│   ├── llm.py                 # Ollama LLM engine (streaming + history compression)
│   ├── emotion_inference.py   # Multi-modal emotion detection
│   ├── personality_engine.py  # Personality profiles and system prompt builder
│   ├── memory.py              # Cross-session memory (JSON, local only)
│   └── gui.py                 # customtkinter GUI
├── eval/
│   └── evaluate_emotion.py    # Emotion classifier evaluation (precision/recall/F1)
├── config/
│   └── settings.py            # Model paths, voice settings, constants
├── data/
│   └── memory.json            # Persisted user memory (local only)
└── requirements.txt
```

---

## Evaluation

An offline evaluation script tests the emotion classifier against 31 labelled phrases across 6 emotion classes:

```bash
python -m eval.evaluate_emotion
```

Reports per-class precision, recall, and F1 score, and saves a JSON report to `eval/`.

---

## Voice Commands

| Command | Effect |
|---|---|
| `hi` / `hey novu` / `hello novu` | Wake Novu up |
| `goodbye` / `exit` / `bye` | End the conversation |
| `start over` / `clear context` | Reset conversation history |
| `switch to friendly / formal / calm` | Change personality mode |
| `remember that [fact]` | Store a fact in long-term memory |
| `forget everything` | Clear all stored memory |
| `my name is [name]` | Save your name |

---

## Personality Modes

- **Friendly** — warm, conversational, encouraging
- **Formal** — professional, precise, structured
- **Calm** — soft, reassuring, measured

---

## Limitations

- macOS only (`say` and `afplay` are macOS-specific)
- Memory uses flat JSON — no semantic search or forgetting curve
- Emotion model is pre-trained, not fine-tuned on conversational audio
- Requires Ollama running locally (~5 GB disk for Llama 3.1 8B)
