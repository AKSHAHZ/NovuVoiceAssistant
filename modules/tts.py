import os
import re
import time
import subprocess
import tempfile
import threading
import queue
import numpy as np
import sounddevice as sd
from config.settings import TTS_RATE, TTS_VOICE

_SENT_RE        = re.compile(r'(?<=[.!?])\s+')
_INTERRUPT_RMS  = 0.022   # RMS level that counts as the user speaking
_INTERRUPT_HOLD = 5       # consecutive loud chunks needed to trigger interrupt

# Characters the macOS `say` command mishandles — map to safe equivalents
_CHAR_MAP = str.maketrans({
    '—': ' - ',   # em dash
    '–': ' - ',   # en dash
    '“': '"',     # left double quote
    '”': '"',     # right double quote
    '‘': "'",     # left single quote
    '’': "'",     # right single quote
    '…': '...',   # ellipsis
    '*':      '',      # markdown bold/italic
    '#':      '',      # markdown headers
    '_':      ' ',     # markdown underscores
    '\n':     ' ',     # newlines → space
})


def _clean(text: str) -> str:
    return text.translate(_CHAR_MAP).strip()


class TextToSpeech:
    def __init__(self):
        self.default_rate = TTS_RATE
        self._voice       = TTS_VOICE
        self._proc        = None
        self._speaking    = threading.Event()
        self._interrupted = False
        self._play_q      = queue.Queue()

        t = threading.Thread(target=self._player, daemon=True)
        t.start()
        print(f"[Novu] TTS ready (voice: {self._voice})")

    # ── Internal player ───────────────────────────────────────────────

    def _player(self):
        while True:
            item = self._play_q.get()
            if item is None:
                self._play_q.task_done()
                continue
            path = item
            try:
                if not self._interrupted:
                    self._proc = subprocess.Popen(["afplay", path])
                    self._proc.wait()
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                self._play_q.task_done()

    def _synth(self, text: str, rate: int) -> str | None:
        """Synthesise cleaned text to a temp AIFF via macOS say."""
        text = _clean(text)
        if not text:
            return None
        try:
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
                path = f.name
            subprocess.run(
                ["say", "-v", self._voice, "-r", str(rate), "-o", path, text],
                check=True, capture_output=True,
            )
            return path
        except Exception as e:
            print(f"[TTS] Synthesis error: {e}")
            return None

    @staticmethod
    def _split(text: str) -> list[str]:
        return [s.strip() for s in _SENT_RE.split(text) if s.strip()]

    # ── Interrupt monitor ─────────────────────────────────────────────

    def _start_interrupt_monitor(self):
        def _monitor():
            # Use the device's native rate — avoids AUHAL -50 sample-rate errors
            try:
                dev = sd.query_devices(kind="input")
                sr  = int(dev["default_samplerate"])
            except Exception:
                sr  = 44100
            bs         = int(sr * 0.1)   # 100 ms blocks
            hold_count = 0

            def _cb(indata, *_):
                nonlocal hold_count
                if self._interrupted:
                    raise sd.CallbackStop

                # ── Echo gate ─────────────────────────────────────────
                # If afplay is currently playing, Novu's own voice from the
                # speakers would be picked up and falsely trigger an interrupt.
                # Reset the hold counter and skip until the file finishes.
                proc = self._proc
                if proc is not None and proc.poll() is None:
                    hold_count = 0
                    return

                arr = np.frombuffer(bytes(indata), dtype=np.int16).astype(np.float32)
                rms = float(np.sqrt(np.mean((arr / 32768.0) ** 2)))
                if rms > _INTERRUPT_RMS:
                    hold_count += 1
                    if hold_count >= _INTERRUPT_HOLD:
                        print("[Novu] Interrupt detected — stopping speech")
                        self.interrupt()
                        raise sd.CallbackStop
                else:
                    hold_count = max(0, hold_count - 1)

            try:
                with sd.RawInputStream(samplerate=sr, blocksize=bs,
                                       dtype="int16", channels=1,
                                       callback=_cb):
                    while self._speaking.is_set() and not self._interrupted:
                        time.sleep(0.05)
            except Exception as e:
                if "CallbackStop" not in str(type(e)):
                    print(f"[TTS] Interrupt monitor: {e}")

        threading.Thread(target=_monitor, daemon=True).start()

    # ── Public API ────────────────────────────────────────────────────

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set()

    def interrupt(self):
        self._interrupted = True
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def speak(self, text: str, rate: int = None):
        if not text.strip():
            return
        self._interrupted = False
        self._speaking.set()
        r = rate or self.default_rate
        self._start_interrupt_monitor()

        sentences = self._split(text) or [text]
        print(f"[Novu] Speaking: '{text[:60]}{'...' if len(text) > 60 else ''}'")

        for s in sentences:
            if self._interrupted:
                break
            path = self._synth(s, r)
            if path:
                self._play_q.put(path)

        self._play_q.join()
        self._speaking.clear()

    def speak_stream(self, token_iter, rate: int = None) -> str:
        self._interrupted = False
        self._speaking.set()
        r = rate or self.default_rate
        self._start_interrupt_monitor()

        buffer     = ""
        full_reply = ""

        try:
            for chunk in token_iter:
                if self._interrupted:
                    break
                try:
                    token = chunk.message.content or ""
                except AttributeError:
                    token = chunk["message"]["content"]
                buffer     += token
                full_reply += token

                parts = _SENT_RE.split(buffer)
                if len(parts) > 1:
                    for s in parts[:-1]:
                        s = s.strip()
                        if s and not self._interrupted:
                            path = self._synth(s, r)
                            if path:
                                self._play_q.put(path)
                    buffer = parts[-1]
        except Exception as e:
            print(f"[TTS] Stream error: {e}")

        if buffer.strip() and not self._interrupted:
            path = self._synth(buffer.strip(), r)
            if path:
                self._play_q.put(path)

        self._play_q.join()
        self._speaking.clear()
        return full_reply.strip()
