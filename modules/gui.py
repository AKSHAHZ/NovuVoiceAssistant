import customtkinter as ctk
import tkinter as tk
import math
import queue
import datetime
import os

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ── Palette ────────────────────────────────────────────────────────────────
BG       = "#0a0a1e"
PANEL    = "#111128"
ACCENT   = "#9d5cf6"
TEXT     = "#e2e2f4"
TEXT_DIM = "#55557a"

STATE_COL = {
    "sleeping":   "#3a3a6a",
    "awake":      "#22c55e",
    "listening":  "#38bdf8",
    "processing": "#f59e0b",
    "speaking":   "#c084fc",
}
STATE_HINT = {
    "sleeping":   'Say  "hi"  to wake me up',
    "awake":      "What's on your mind?",
    "listening":  "I'm all ears...",
    "processing": "Thinking...",
    "speaking":   "Novu is speaking...",
}
EMOTION_EMOJI = {
    "happy": "😊", "excited": "🤩", "neutral": "😐",
    "frustrated": "😤", "angry": "😠", "sad": "😢",
}
EMOTION_COL = {
    "happy":      "#4ade80",
    "excited":    "#fbbf24",
    "neutral":    "#818cf8",
    "frustrated": "#fb923c",
    "angry":      "#f87171",
    "sad":        "#60a5fa",
}
PERS_COL = {
    "friendly": "#f472b6",
    "formal":   "#818cf8",
    "calm":     "#34d399",
}

NUM_BARS = 11
BAR_W    = 5
BAR_GAP  = 4
BAR_MAX  = 60


class NovuGUI:
    W, H = 440, 700

    def __init__(self):
        self._state       = "sleeping"
        self._emotion     = "neutral"
        self._rms         = 0.0
        self._q           = queue.Queue()
        self._log_lines   = []
        self._active_pers = "friendly"
        self.on_personality_change = None

        self.root = ctk.CTk()
        self.root.title("Novu")
        self.root.geometry(f"{self.W}x{self.H}")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(fg_color=BG)

        self._build()
        self._place()
        self._t    = 0.0
        self._bars = [0.0] * NUM_BARS
        self._dx   = self._dy = 0
        self._tick()
        self._poll()

    # ── Layout ────────────────────────────────────────────────────────────

    def _build(self):
        root = self.root

        # Purple accent stripe
        tk.Frame(root, bg=ACCENT, height=3).pack(fill="x")

        # ── Header ────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(root, height=50, fg_color=PANEL, corner_radius=0)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        hdr.bind("<ButtonPress-1>", self._drag_start)
        hdr.bind("<B1-Motion>",     self._drag_motion)

        logo = ctk.CTkLabel(hdr, text="✦  NOVU",
                            font=ctk.CTkFont("Helvetica Neue", 15, "bold"),
                            text_color=ACCENT)
        logo.pack(side="left", padx=16)
        logo.bind("<ButtonPress-1>", self._drag_start)
        logo.bind("<B1-Motion>",     self._drag_motion)

        ctk.CTkButton(hdr, text="×", width=34, height=34,
                      fg_color="transparent", text_color=TEXT_DIM,
                      hover_color="#6b0000",
                      font=ctk.CTkFont("Helvetica Neue", 20),
                      corner_radius=8,
                      command=root.destroy).pack(side="right", padx=8, pady=8)

        ctk.CTkButton(hdr, text="💾", width=34, height=34,
                      fg_color="transparent", text_color=TEXT_DIM,
                      hover_color="#1e1e44",
                      font=ctk.CTkFont("Helvetica Neue", 13),
                      corner_radius=8,
                      command=self._save_conversation).pack(side="right", padx=2, pady=8)

        self._status_lbl = ctk.CTkLabel(
            hdr, text="●  Sleeping",
            font=ctk.CTkFont("Helvetica Neue", 10, "bold"),
            text_color=STATE_COL["sleeping"],
            fg_color="#0e0e2a", corner_radius=20)
        self._status_lbl.pack(side="right", padx=10, pady=12,
                              ipadx=12, ipady=4)

        # ── Orb ───────────────────────────────────────────────────────────
        orb_wrap = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
        orb_wrap.pack(fill="x", pady=(16, 6))

        self.canvas = tk.Canvas(orb_wrap, width=200, height=200,
                                bg=BG, highlightthickness=0)
        self.canvas.pack()

        self._hint_lbl = ctk.CTkLabel(
            orb_wrap, text=STATE_HINT["sleeping"],
            font=ctk.CTkFont("Helvetica Neue", 13, slant="italic"),
            text_color=TEXT_DIM)
        self._hint_lbl.pack(pady=(10, 4))

        self._emo_lbl = ctk.CTkLabel(
            orb_wrap, text="😐  neutral",
            font=ctk.CTkFont("Helvetica Neue", 11),
            text_color=EMOTION_COL["neutral"],
            fg_color="#0e0e2a", corner_radius=20)
        self._emo_lbl.pack(pady=(0, 10), ipadx=16, ipady=6)

        # ── Divider ───────────────────────────────────────────────────────
        ctk.CTkFrame(root, height=1, fg_color="#1a1a3a",
                     corner_radius=0).pack(fill="x")

        # ── Chat header ───────────────────────────────────────────────────
        ch = ctk.CTkFrame(root, fg_color=BG, corner_radius=0, height=32)
        ch.pack(fill="x", padx=14, pady=(8, 2))
        ch.pack_propagate(False)
        ctk.CTkLabel(ch, text="CONVERSATION",
                     font=ctk.CTkFont("Helvetica Neue", 8, "bold"),
                     text_color="#202048").pack(side="left", anchor="s", pady=4)
        ctk.CTkButton(ch, text="clear", width=44, height=22,
                      fg_color="transparent", text_color=TEXT_DIM,
                      hover_color="#1a1a3c",
                      font=ctk.CTkFont("Helvetica Neue", 9),
                      corner_radius=6,
                      command=self._clear_log).pack(side="right", anchor="s", pady=4)

        # ── Chat area ─────────────────────────────────────────────────────
        self._chat = ctk.CTkScrollableFrame(
            root, fg_color="#08081c",
            scrollbar_button_color="#1e1e42",
            scrollbar_button_hover_color="#2e2e60",
            corner_radius=0)
        self._chat.pack(fill="both", expand=True)

        # ── Divider ───────────────────────────────────────────────────────
        ctk.CTkFrame(root, height=1, fg_color="#1a1a3a",
                     corner_radius=0).pack(fill="x")

        # ── Personality bar ───────────────────────────────────────────────
        pbar = ctk.CTkFrame(root, height=52, fg_color=PANEL, corner_radius=0)
        pbar.pack(fill="x", side="bottom")
        pbar.pack_propagate(False)

        self._pers_btns   = {}
        self._pers_inds   = {}
        for p in ["friendly", "formal", "calm"]:
            pf  = ctk.CTkFrame(pbar, fg_color=PANEL, corner_radius=0)
            pf.pack(side="left", expand=True, fill="both")

            ind = tk.Frame(pf, bg=PANEL, height=2)
            ind.pack(fill="x")
            self._pers_inds[p] = ind

            btn = ctk.CTkButton(
                pf, text=p.capitalize(), height=50,
                fg_color="transparent", text_color=TEXT_DIM,
                hover_color="#1a1a38",
                font=ctk.CTkFont("Helvetica Neue", 11),
                corner_radius=0,
                command=lambda p=p: self._click_personality(p))
            btn.pack(fill="both", expand=True)
            self._pers_btns[p] = btn

        self._highlight_personality("friendly")

    def _place(self):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{sw - self.W - 28}+{sh - self.H - 56}")

    # ── Chat bubble factory ───────────────────────────────────────────────

    def _add_bubble(self, speaker: str, text: str, ts: str):
        row = ctk.CTkFrame(self._chat, fg_color="transparent", corner_radius=0)
        row.pack(fill="x", padx=10, pady=3)

        if speaker == "you":
            bubble = ctk.CTkFrame(row, fg_color="#0d2040", corner_radius=16)
            bubble.pack(anchor="e", padx=(64, 0))
            ctk.CTkLabel(bubble,
                         text=f"You  ·  {ts}",
                         font=ctk.CTkFont("Helvetica Neue", 8, "bold"),
                         text_color="#4a88cc",
                         anchor="w").pack(padx=14, pady=(8, 1), anchor="w")
            ctk.CTkLabel(bubble,
                         text=text,
                         font=ctk.CTkFont("Helvetica Neue", 10),
                         text_color="#bae6fd",
                         wraplength=260, justify="left",
                         anchor="w").pack(padx=14, pady=(0, 10), anchor="w")

        elif speaker == "novu":
            bubble = ctk.CTkFrame(row, fg_color="#130d2e", corner_radius=16)
            bubble.pack(anchor="w", padx=(0, 64))
            ctk.CTkLabel(bubble,
                         text=f"Novu  ·  {ts}",
                         font=ctk.CTkFont("Helvetica Neue", 8, "bold"),
                         text_color="#9060cc",
                         anchor="w").pack(padx=14, pady=(8, 1), anchor="w")
            ctk.CTkLabel(bubble,
                         text=text,
                         font=ctk.CTkFont("Helvetica Neue", 10),
                         text_color="#e9d5ff",
                         wraplength=260, justify="left",
                         anchor="w").pack(padx=14, pady=(0, 10), anchor="w")

        else:   # system
            ctk.CTkLabel(row, text=text,
                         font=ctk.CTkFont("Helvetica Neue", 8, slant="italic"),
                         text_color=TEXT_DIM).pack(anchor="center", pady=2)

        # Scroll to bottom
        try:
            self._chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    # ── Animation ─────────────────────────────────────────────────────────

    def _tick(self):
        self._t += 0.05
        target = min(1.0, self._rms / 0.04)
        for i in range(NUM_BARS):
            phase   = math.sin(self._t * 3.8 + i * 0.72) * 0.5 + 0.5
            desired = target * phase if self._state == "listening" else 0.0
            self._bars[i] += (desired - self._bars[i]) * 0.28
        self._draw_orb(self._t)
        self.root.after(40, self._tick)

    def _draw_orb(self, t):
        c  = self.canvas
        cx = cy = 100
        c.delete("all")
        col = STATE_COL.get(self._state, "#3a3a6a")

        if self._state == "listening":
            total = NUM_BARS * (BAR_W + BAR_GAP) - BAR_GAP
            x0    = cx - total // 2
            for i, lv in enumerate(self._bars):
                h   = max(4, int(lv * BAR_MAX))
                x   = x0 + i * (BAR_W + BAR_GAP)
                cb  = self._lerp(col, "#ffffff", lv * 0.28)
                c.create_rectangle(x, cy - h // 2, x + BAR_W, cy + h // 2,
                                   fill=cb, outline="")

        elif self._state == "processing":
            for i in range(3):
                ang = math.radians((t * 130) % 360 + i * 120)
                px  = cx + math.cos(ang) * 36
                py  = cy + math.sin(ang) * 36
                sz  = 10 - i * 2
                c.create_oval(px - sz, py - sz, px + sz, py + sz,
                              fill=self._lerp(col, BG, i * 0.35), outline="")

        else:
            speed = 1.6 if self._state == "speaking" else 0.7
            pulse = (math.sin(t * speed) + 1) / 2
            base  = 46

            for i in range(7, 0, -1):
                r     = base + pulse * 16 + i * 10
                alpha = (8 - i) / 7 * 0.22
                c.create_oval(cx - r, cy - r, cx + r, cy + r,
                              fill=self._lerp(BG, col, alpha), outline="")

            r = base + pulse * 12
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=col, outline="")

            if self._state == "speaking":
                for i in range(1, 5):
                    rr    = r + 8 + i * 15
                    alpha = max(0.0, 0.38 - i * 0.08)
                    c.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                  outline=self._lerp(BG, col, alpha),
                                  width=2, fill="")

            hr = r * 0.30
            c.create_oval(cx - hr - 9, cy - hr - 13,
                          cx + hr - 9, cy + hr - 13,
                          fill=self._lerp(col, "#ffffff", 0.45), outline="")

    def _lerp(self, c1: str, c2: str, t: float) -> str:
        t  = max(0.0, min(1.0, t))
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        return (f"#{int(r1 + (r2-r1)*t):02x}"
                f"{int(g1 + (g2-g1)*t):02x}"
                f"{int(b1 + (b2-b1)*t):02x}")

    # ── Queue poll ────────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                cmd, val = self._q.get_nowait()
                if cmd == "state":
                    self._state = val
                    col = STATE_COL.get(val, "#3a3a6a")
                    self._status_lbl.configure(
                        text=f"●  {val.capitalize()}", text_color=col)
                    self._hint_lbl.configure(text=STATE_HINT.get(val, ""))
                elif cmd == "emotion":
                    self._emotion = val
                    col = EMOTION_COL.get(val, "#818cf8")
                    self._emo_lbl.configure(
                        text=f"{EMOTION_EMOJI.get(val, '😐')}  {val}",
                        text_color=col)
                elif cmd == "rms":
                    self._rms = val
                elif cmd == "log":
                    speaker, text = val
                    ts = datetime.datetime.now().strftime("%H:%M")
                    self._log_lines.append((ts, speaker, text))
                    self._add_bubble(speaker, text, ts)
                elif cmd == "clear_log":
                    self._log_lines = []
                    for w in self._chat.winfo_children():
                        w.destroy()
                elif cmd == "personality":
                    self._highlight_personality(val)
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    # ── Public API ────────────────────────────────────────────────────────

    def update_state(self, s):       self._q.put(("state", s))
    def update_emotion(self, e):     self._q.put(("emotion", e))
    def update_rms(self, rms):       self._q.put(("rms", rms))
    def log_you(self, text):         self._q.put(("log", ("you",  text)))
    def log_novu(self, text):        self._q.put(("log", ("novu", text)))
    def log_sys(self, text):         self._q.put(("log", ("sys",  text)))
    def update_personality(self, p): self._q.put(("personality", p))
    def clear_log(self):             self._q.put(("clear_log", None))

    # ── Save ──────────────────────────────────────────────────────────────

    def _save_conversation(self):
        if not self._log_lines:
            return
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.expanduser(f"~/Desktop/novu_{ts}.txt")
        with open(path, "w") as f:
            f.write("Novu Conversation\n")
            f.write(f"Saved {datetime.datetime.now().strftime('%d %b %Y  %H:%M')}\n")
            f.write("=" * 48 + "\n\n")
            for ts_s, spk, txt in self._log_lines:
                label = {"you": "You", "novu": "Novu"}.get(spk)
                if label:
                    f.write(f"[{ts_s}] {label}: {txt}\n\n")
        self.log_sys(f"Saved → Desktop/novu_{ts}.txt")

    def _clear_log(self):
        self.clear_log()

    # ── Personality ───────────────────────────────────────────────────────

    def _click_personality(self, p):
        self._highlight_personality(p)
        if self.on_personality_change:
            self.on_personality_change(p)

    def _highlight_personality(self, active):
        self._active_pers = active
        for p in ["friendly", "formal", "calm"]:
            col = PERS_COL[p]
            btn = self._pers_btns[p]
            ind = self._pers_inds[p]
            if p == active:
                btn.configure(text_color=col,
                              font=ctk.CTkFont("Helvetica Neue", 11, "bold"))
                ind.configure(bg=col)
            else:
                btn.configure(text_color=TEXT_DIM,
                              font=ctk.CTkFont("Helvetica Neue", 11))
                ind.configure(bg=PANEL)

    # ── Drag ──────────────────────────────────────────────────────────────

    def _drag_start(self, e): self._dx, self._dy = e.x, e.y
    def _drag_motion(self, e):
        self.root.geometry(
            f"+{self.root.winfo_x() + e.x - self._dx}"
            f"+{self.root.winfo_y() + e.y - self._dy}")

    def run(self): self.root.mainloop()
