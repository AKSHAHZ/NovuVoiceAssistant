import os
import sys
import threading
import logging
from datetime import datetime

os.environ["TOKENIZERS_PARALLELISM"] = "false"
sys.path.insert(0, os.path.dirname(__file__))

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(_LOG_DIR, "novu.log"),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

from modules.gui              import NovuGUI
from modules.stt              import SpeechToText
from modules.tts              import TextToSpeech
from modules.emotion_inference import EmotionInference
from modules.personality_engine import PersonalityEngine
from modules.llm              import LLMEngine
from modules.memory           import MemoryEngine

WAKE_WORDS    = {"hi", "hey novu", "hello novu", "novu", "hey nova"}
EXIT_PHRASES  = {"exit", "quit", "goodbye", "bye", "stop", "go to sleep", "sleep", "power off"}
CLEAR_PHRASES = {"start over", "clear context", "reset conversation", "new conversation"}

PERSONALITY_REPLIES = {
    "friendly": "Switching to friendly mode — let's have some fun!",
    "formal":   "Switching to formal mode. How may I assist you?",
    "calm":     "Switching to calm mode. Take a breath. I'm right here.",
}

HELP_TEXT = (
    "I can chat about anything, answer your questions, tell jokes or stories, "
    "play games like twenty questions, give you a pep talk, help you think things through, "
    "or just listen when you need to vent. I also remember things you tell me across sessions. "
    "What do you need?"
)


def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 12:  return "morning"
    if h < 17:  return "afternoon"
    return "evening"


def _contains(text: str, phrases) -> bool:
    t = text.lower()
    return any(p in t for p in phrases)


def pipeline(gui: NovuGUI, shared: dict):
    logging.info("Novu starting up")

    stt     = SpeechToText()
    tts     = TextToSpeech()
    emotion = EmotionInference()
    persona = PersonalityEngine()
    llm     = LLMEngine()
    memory  = MemoryEngine()

    history = []
    active  = False
    tod     = _time_of_day()

    # ── Personalised greeting ──────────────────────────────────────────
    if memory.returning_user() and memory.name:
        greeting = (f"Novu online. {memory.name}, whatever's on your mind today, "
                    f"I'm here for it. Just say hi.")
    elif memory.returning_user():
        greeting = ("Novu online. Whatever's on your mind today, "
                    "I'm here for it. Just say hi.")
    else:
        greeting = ("Novu online. Whatever's on your mind today, "
                    "I'm here for it. Just say hi.")

    gui.update_state("sleeping")
    gui.log_sys(f"Session #{memory.data['session_count']} — good {tod}")
    tts.speak(greeting)

    while True:
        try:
            # Pick up GUI personality button presses
            if shared.get("personality_changed"):
                persona.set_profile(shared["personality"])
                shared["personality_changed"] = False

            # ── Wake detection (fast 2 s window) ──────────────────────
            if not active:
                gui.update_state("sleeping")
                triggered, wake_text = stt.listen_for_wake(WAKE_WORDS)
                if not triggered:
                    continue
                active = True
                gui.update_state("awake")
                name_part  = f", {memory.name}" if memory.name else ""
                wake_reply = f"Hey{name_part}! I'm here. What's up?"
                gui.log_novu(wake_reply)
                tts.speak(wake_reply)

                # If the user said more after the wake word, process it
                leftover = wake_text.lower()
                for w in WAKE_WORDS:
                    leftover = leftover.replace(w, "").strip()
                if leftover and len(leftover) > 3:
                    # Feed leftover into the main loop as a user utterance
                    shared["_pending"] = leftover
                continue

            # ── Pending text from wake phrase ──────────────────────────
            if shared.get("_pending"):
                text        = shared.pop("_pending")
                audio_array = None
            else:
                gui.update_state("listening")
                text, audio_array = stt.listen(on_level=gui.update_rms)
                gui.update_rms(0.0)

            if not text:
                continue

            logging.info(f"User: {text}")

            # ── Exit ───────────────────────────────────────────────────
            if _contains(text, EXIT_PHRASES):
                farewell = (f"Goodbye{', ' + memory.name if memory.name else ''}! "
                            f"Take care of yourself.")
                gui.log_you(text)
                gui.log_novu(farewell)
                gui.update_state("sleeping")
                tts.speak(farewell)
                active  = False
                history = []
                continue

            # ── Clear ──────────────────────────────────────────────────
            if _contains(text, CLEAR_PHRASES):
                history = []
                gui.log_you(text)
                gui.clear_log()
                gui.log_sys("Conversation cleared — fresh start")
                reply = "Fresh start! What do you want to talk about?"
                gui.log_novu(reply)
                tts.speak(reply)
                continue

            # ── Help ───────────────────────────────────────────────────
            if _contains(text, {"what can you do", "help me", "who are you",
                                 "what are you", "capabilities"}):
                gui.log_you(text)
                gui.log_novu(HELP_TEXT)
                tts.speak(HELP_TEXT)
                continue

            # ── Memory commands ────────────────────────────────────────
            mem_reply = memory.detect_and_store(text)
            if mem_reply:
                gui.log_you(text)
                gui.log_novu(mem_reply)
                tts.speak(mem_reply)
                continue

            # ── Personality switch ─────────────────────────────────────
            switched = False
            for p in PERSONALITY_REPLIES:
                if f"switch to {p}" in text.lower() or f"{p} mode" in text.lower():
                    persona.set_profile(p)
                    shared["personality"] = p
                    gui.update_personality(p)
                    reply = PERSONALITY_REPLIES[p]
                    gui.log_you(text)
                    gui.log_novu(reply)
                    tts.speak(reply)
                    switched = True
                    break
            if switched:
                continue

            # ── Core pipeline ──────────────────────────────────────────
            gui.log_you(text)
            gui.update_state("processing")

            emo           = emotion.infer(text, audio_array, stt.sample_rate)
            mem_ctx        = memory.build_context()
            system_prompt  = persona.build_system_prompt(emo, mem_ctx, text)
            tts_adj        = persona.get_tts_adjustments(emo)

            gui.update_emotion(emo)

            # Streaming generation + pipelined TTS
            token_stream = llm.generate_stream(text, system_prompt, history)
            gui.update_state("speaking")
            reply = tts.speak_stream(token_stream, **tts_adj)

            if not reply:   # fallback if stream failed
                reply = llm.generate(text, system_prompt, history)
                tts.speak(reply, **tts_adj)

            if reply:
                history.append({"role": "user",      "content": text})
                history.append({"role": "assistant", "content": reply})
                if len(history) > 30:
                    history = history[-30:]
                gui.log_novu(reply)
                logging.info(f"Emotion: {emo} | Novu: {reply[:80]}")

        except KeyboardInterrupt:
            logging.info("Shutdown")
            break
        except Exception as e:
            logging.error(f"Pipeline error: {e}", exc_info=True)
            print(f"[Novu] Error: {e}")


def main():
    shared = {"personality": "friendly", "personality_changed": False}

    gui = NovuGUI()

    def on_personality_change(p):
        shared["personality"] = p
        shared["personality_changed"] = True

    gui.on_personality_change = on_personality_change

    t = threading.Thread(target=pipeline, args=(gui, shared), daemon=True)
    t.start()
    gui.run()


if __name__ == "__main__":
    main()
