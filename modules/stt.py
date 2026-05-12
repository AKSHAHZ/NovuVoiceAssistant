import json
import queue
import numpy as np
import sounddevice as sd
from vosk import Model, KaldiRecognizer
from config.settings import VOSK_MODEL_PATH, VOSK_SAMPLE_RATE

# VAD constants — full conversation listening
_CHUNK_S        = 0.08
_MAX_CHUNKS     = 250      # hard cap ~20 s
_SILENCE_CHUNKS = 38       # ~3 s of silence → stop

# Adaptive noise calibration
_CALIB_CHUNKS   = 3        # ~240 ms ambient sample before each listen
_SPEECH_MULT    = 3.5      # voice must be this × noise floor to count as speech
_SILENCE_MULT   = 2.0      # below this × noise floor = silence
_SPEECH_MIN     = 0.018    # absolute minimum speech threshold (quiet rooms)
_SILENCE_MIN    = 0.010    # absolute minimum silence threshold

# Wake detection constants — lightweight, fast window
_WAKE_WINDOW_S  = 2.0
_WAKE_BLOCKSIZE_S = 0.08


class SpeechToText:
    def __init__(self):
        print("[Novu] Loading STT model...")
        self.model       = Model(VOSK_MODEL_PATH)
        self.sample_rate = VOSK_SAMPLE_RATE
        self._blocksize  = int(self.sample_rate * _CHUNK_S)
        print("[Novu] STT ready.")

    # ── Wake detection ────────────────────────────────────────────────

    def listen_for_wake(self, wake_words: set) -> tuple[bool, str]:
        """
        Fast 2-second window to detect wake words.
        Returns (triggered: bool, full_text: str).
        The full text is returned so any content after the wake word
        is not lost (e.g. "hi what time is it").
        """
        blocksize = int(self.sample_rate * _WAKE_BLOCKSIZE_S)
        n_chunks  = int(_WAKE_WINDOW_S / _WAKE_BLOCKSIZE_S)
        audio_q   = queue.Queue()

        def _cb(indata, *_):
            audio_q.put(bytes(indata))

        recognizer = KaldiRecognizer(self.model, self.sample_rate)

        with sd.RawInputStream(samplerate=self.sample_rate, blocksize=blocksize,
                               dtype="int16", channels=1, callback=_cb):
            for _ in range(n_chunks):
                recognizer.AcceptWaveform(audio_q.get())

        text = json.loads(recognizer.FinalResult()).get("text", "").strip()
        if text:
            print(f"[Novu] Wake check: '{text}'")
        triggered = any(w in text.lower() for w in wake_words)
        return triggered, text

    # ── Full conversation listening (VAD) ─────────────────────────────

    def listen(self, on_level=None) -> tuple[str, np.ndarray]:
        """
        Record until the speaker stops (VAD) or the hard cap is hit.
        Calibrates to ambient noise before listening so background sounds
        are ignored and only the user's voice triggers detection.
        """
        audio_q    = queue.Queue()
        raw_chunks = []
        f32_chunks = []

        def _cb(indata, *_):
            audio_q.put(bytes(indata))

        recognizer = KaldiRecognizer(self.model, self.sample_rate)

        print("[Novu] Listening (VAD)...")
        with sd.RawInputStream(samplerate=self.sample_rate,
                               blocksize=self._blocksize,
                               dtype="int16", channels=1, callback=_cb):

            # ── Calibrate ambient noise (~400 ms) ────────────────────
            calib = []
            for _ in range(_CALIB_CHUNKS):
                data = audio_q.get()
                arr  = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                calib.append(float(np.sqrt(np.mean(arr ** 2))))
            noise_floor   = float(np.mean(calib))
            speech_thresh = max(noise_floor * _SPEECH_MULT,  _SPEECH_MIN)
            silence_thresh = max(noise_floor * _SILENCE_MULT, _SILENCE_MIN)
            print(f"[Novu] Noise floor: {noise_floor:.4f} | "
                  f"voice threshold: {speech_thresh:.4f}")

            # ── VAD loop ──────────────────────────────────────────────
            silence_cnt = 0
            speech_seen = False

            while len(raw_chunks) < _MAX_CHUNKS:
                data = audio_q.get()
                raw_chunks.append(data)

                arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
                f32_chunks.append(arr)
                rms = float(np.sqrt(np.mean(arr ** 2)))

                if on_level:
                    on_level(rms)

                if rms > speech_thresh:
                    speech_seen = True
                    silence_cnt = 0
                elif speech_seen and rms < silence_thresh:
                    silence_cnt += 1
                    if silence_cnt >= _SILENCE_CHUNKS:
                        break

        if not speech_seen:
            return "", np.array([])

        for chunk in raw_chunks:
            recognizer.AcceptWaveform(chunk)

        text        = json.loads(recognizer.FinalResult()).get("text", "").strip()
        audio_array = np.concatenate(f32_chunks) if f32_chunks else np.array([])

        print(f"[Novu] Heard: '{text}'")
        return text, audio_array
