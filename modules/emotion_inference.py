import numpy as np
from transformers import pipeline
from config.settings import EMOTION_MODEL

# Maps the 7-class model labels → Novu emotion labels
_LABEL_MAP = {
    "joy":      "happy",
    "surprise": "excited",
    "neutral":  "neutral",
    "fear":     "frustrated",
    "disgust":  "frustrated",
    "sadness":  "sad",
    "anger":    "angry",
}

# Acoustic RMS thresholds
_ENERGY_HIGH = 0.055   # loud speech → intensify emotion
_ENERGY_LOW  = 0.008   # very quiet → soften emotion

# Intensity upgrades: (base_emotion, condition) → upgraded_emotion
_INTENSIFY = {
    ("happy",      "high"): "excited",
    ("frustrated", "high"): "angry",
}

# Intensity softens: (base_emotion, condition) → softened_emotion
_SOFTEN = {
    ("angry",   "low"): "frustrated",
    ("excited", "low"): "happy",
}


class EmotionInference:
    def __init__(self):
        print("[Novu] Loading emotion model...")
        self.pipe = pipeline(
            "text-classification",
            model=EMOTION_MODEL,
            top_k=1,
            truncation=True,
        )
        print("[Novu] Emotion model ready.")

    def _acoustic_energy(self, audio_array: np.ndarray) -> str:
        """Return 'high', 'low', or 'normal' based on RMS energy."""
        if audio_array is None or len(audio_array) == 0:
            return "normal"
        rms = float(np.sqrt(np.mean(audio_array ** 2)))
        if rms > _ENERGY_HIGH:
            return "high"
        if rms < _ENERGY_LOW:
            return "low"
        return "normal"

    def infer(self, text: str,
              audio_array: np.ndarray = None,
              sample_rate: int = 16000) -> str:
        if not text.strip():
            return "neutral"

        # Text-based classification
        result    = self.pipe(text)[0][0]
        raw_label = result["label"].lower()
        score     = result["score"]
        emotion   = _LABEL_MAP.get(raw_label, "neutral")

        # High-confidence joy → excited
        if emotion == "happy" and score > 0.82:
            emotion = "excited"

        # Acoustic modifier — adjusts intensity based on how loudly they spoke
        energy = self._acoustic_energy(audio_array)
        if energy != "normal":
            emotion = _INTENSIFY.get((emotion, energy),
                      _SOFTEN.get((emotion, energy), emotion))

        print(f"[Novu] Emotion: {emotion}  "
              f"({raw_label} {score:.2f}, energy={energy})")
        return emotion
