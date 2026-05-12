import json
import os
from datetime import datetime

_MEMORY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "memory.json")

_DEFAULT = {
    "name": None,
    "facts": [],
    "preferences": [],
    "last_session": None,
    "session_count": 0,
}

# Phrases that signal the user wants Novu to forget something
_FORGET_TRIGGERS = [
    "forget everything", "forget what you know", "clear your memory",
    "delete my memory", "reset memory",
]


class MemoryEngine:
    def __init__(self):
        self._path = _MEMORY_PATH
        self.data  = self._load()
        self.data["session_count"] = self.data.get("session_count", 0) + 1
        self._save()
        print(f"[Novu] Memory loaded — session #{self.data['session_count']}")

    # ── Load / save ───────────────────────────────────────────────────

    def _load(self) -> dict:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    d = json.load(f)
                    # Back-fill any keys added since last run
                    for k, v in _DEFAULT.items():
                        d.setdefault(k, v)
                    return d
            except Exception:
                pass
        return dict(_DEFAULT)

    def _save(self):
        self.data["last_session"] = datetime.now().isoformat()
        with open(self._path, "w") as f:
            json.dump(self.data, f, indent=2)

    # ── Public API ────────────────────────────────────────────────────

    @property
    def name(self) -> str | None:
        return self.data.get("name")

    def remember_fact(self, fact: str):
        fact = fact.strip()
        if fact and fact not in self.data["facts"]:
            self.data["facts"].append(fact)
            self._save()

    def forget_all(self):
        self.data.update({"name": None, "facts": [], "preferences": []})
        self._save()

    def returning_user(self) -> bool:
        return self.data["session_count"] > 1

    def last_session_date(self) -> str | None:
        raw = self.data.get("last_session")
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            return dt.strftime("%-d %b")
        except Exception:
            return None

    def build_context(self) -> str:
        """Return a memory context string to inject into the system prompt."""
        lines = []
        if self.data.get("name"):
            lines.append(f"The user's name is {self.data['name']}. Use it naturally in conversation.")
        facts = self.data.get("facts", [])
        if facts:
            lines.append("Things you know about this user: " + "; ".join(facts[-12:]))
        prefs = self.data.get("preferences", [])
        if prefs:
            lines.append("User preferences: " + "; ".join(prefs[-6:]))
        if self.data["session_count"] > 1 and self.data.get("last_session"):
            lines.append(f"This is session #{self.data['session_count']}. "
                         f"Last spoke on {self.last_session_date()}. "
                         "Reference the ongoing relationship naturally.")
        return "\n".join(lines)

    def detect_and_store(self, text: str) -> str | None:
        """
        Scan user speech for memory/forget commands.
        Returns a spoken confirmation string if something was stored/cleared,
        or None if nothing was detected.
        """
        t = text.lower().strip()

        # Forget
        if any(p in t for p in _FORGET_TRIGGERS):
            self.forget_all()
            return "Done, I've cleared everything I knew about you. Fresh start."

        # Name detection
        for trigger in ("my name is", "i am called", "call me", "i'm called"):
            if trigger in t:
                after = t.split(trigger, 1)[-1].strip()
                name  = after.split()[0].strip(".,!?").capitalize() if after else None
                if name:
                    self.data["name"] = name
                    self._save()
                    return f"Got it — I'll call you {name} from now on."

        # Generic fact storage — only fire on explicit store commands
        for trigger in ("remember that", "remember this", "don't forget that",
                        "note that", "keep in mind that", "please remember"):
            if trigger in t:
                fact = t.split(trigger, 1)[-1].strip().strip(".,")
                if len(fact) > 3:
                    self.remember_fact(fact)
                    return "Got it, I'll keep that in mind."

        return None
