import subprocess
import time
import ollama
from config.settings import OLLAMA_MODEL

SUMMARY_TRIGGER = 24
KEEP_RECENT     = 12


def _ensure_ollama():
    try:
        ollama.list()
    except Exception:
        print("[Novu] Starting Ollama server...")
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)


class LLMEngine:
    def __init__(self):
        _ensure_ollama()
        self.model  = OLLAMA_MODEL
        self.client = ollama.Client(host="http://localhost:11434")
        self._warmup()
        print(f"[Novu] LLM ready — {self.model}")

    def _warmup(self):
        print(f"[Novu] Loading {self.model}...")
        try:
            self.client.chat(model=self.model,
                             messages=[{"role": "user", "content": "hi"}],
                             options={"num_predict": 4})
            print("[Novu] Model loaded.")
        except Exception as e:
            print(f"[Novu] Warmup warning: {e}")

    def _compress(self, history: list) -> list:
        if len(history) <= SUMMARY_TRIGGER:
            return history
        old, recent = history[:-KEEP_RECENT], history[-KEEP_RECENT:]
        convo = "\n".join(f"{m['role'].capitalize()}: {m['content']}" for m in old)
        try:
            resp    = self.client.chat(
                model=self.model,
                messages=[{"role": "user",
                           "content": f"Summarise this in 3 sentences:\n{convo}"}])
            summary = resp.message.content.strip()
            return [{"role": "system",
                     "content": f"Earlier in this conversation: {summary}"}] + recent
        except Exception:
            return recent

    def _build_messages(self, user_text, system_prompt, history):
        history  = self._compress(history or [])
        messages = [{"role": "system", "content": system_prompt}]
        messages += history
        messages.append({"role": "user", "content": user_text})
        return messages

    def generate(self, user_text: str, system_prompt: str,
                 history: list = None) -> str:
        """Blocking generation — returns full reply string."""
        try:
            resp = self.client.chat(model=self.model,
                                    messages=self._build_messages(
                                        user_text, system_prompt, history))
            return resp.message.content.strip()
        except Exception as e:
            print(f"[Novu] LLM error: {e}")
            return "Sorry, something went wrong on my end. Could you try again?"

    def generate_stream(self, user_text: str, system_prompt: str,
                        history: list = None):
        """Streaming generation — returns a token iterator."""
        try:
            return self.client.chat(
                model=self.model,
                messages=self._build_messages(user_text, system_prompt, history),
                stream=True,
            )
        except Exception as e:
            print(f"[Novu] LLM stream error: {e}")
            return iter([])   # empty iterator — TTS will speak nothing
