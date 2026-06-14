"""
VideoMind — AI Video Summarizer + Chat Assistant
================================================
Requirements:
    pip install openai-whisper yt-dlp groq python-dotenv

System:
    macOS:   brew install ffmpeg
    Ubuntu:  sudo apt install ffmpeg
    Windows: https://ffmpeg.org/download.html

.env file (place next to this script):
    GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
"""

# ─────────────────────────────────────────────────────────────────────────────
import os, sqlite3, tempfile, subprocess, threading, webbrowser, uuid, textwrap, shutil, sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime

# ── .env ─────────────────────────────────────────────────────────────────────
# Handle paths for PyInstaller (Frozen) vs Development
if getattr(sys, 'frozen', False):
    # Internal bundle path (where --add-data files are extracted)
    BUNDLE_PATH = Path(sys._MEIPASS)
    # External path (where the EXE actually lives)
    EXE_PATH = Path(sys.executable).parent
    BASE_PATH = BUNDLE_PATH
else:
    BASE_PATH = Path(__file__).parent
    EXE_PATH = BASE_PATH

# Determine paths for bundled binaries (FFmpeg/FFprobe)
FFMPEG_BIN  = "ffmpeg"
FFPROBE_BIN = "ffprobe"
if getattr(sys, 'frozen', False):
    # Check external folder first (next to EXE), then internal bundle
    ffmpeg_path = EXE_PATH / "ffmpeg.exe"
    ffprobe_path = EXE_PATH / "ffprobe.exe"
    if not ffmpeg_path.exists(): ffmpeg_path = BUNDLE_PATH / "ffmpeg.exe"
    if not ffprobe_path.exists(): ffprobe_path = BUNDLE_PATH / "ffprobe.exe"

    if ffmpeg_path.exists(): FFMPEG_BIN = str(ffmpeg_path)
    if ffprobe_path.exists(): FFPROBE_BIN = str(ffprobe_path)

try:
    from dotenv import load_dotenv
    # Check external EXE folder first (allows user to override), then internal bundle
    env_ext = EXE_PATH / ".env"
    env_int = BASE_PATH / ".env"
    
    if env_ext.exists():
        load_dotenv(str(env_ext))
    elif env_int.exists():
        load_dotenv(str(env_int))
except ImportError:
    pass

# ── optional deps ─────────────────────────────────────────────────────────────
MISSING = []
for pkg, imp in [("openai-whisper","whisper"),("yt-dlp","yt_dlp"),
                 ("groq","groq"),("python-dotenv","dotenv")]:
    try: __import__(imp)
    except ImportError: MISSING.append(pkg)

try: import whisper
except ImportError: whisper = None
try: import yt_dlp
except ImportError: yt_dlp = None
try: from groq import Groq
except ImportError: Groq = None

# ─────────────────────────────────────────────────────────────────────────────
# PALETTE  (Google Material)
# ─────────────────────────────────────────────────────────────────────────────
BG       = "#F8F9FA"
SURFACE  = "#FFFFFF"
SURF2    = "#F1F3F4"
OUTLINE  = "#DADCE0"
SIDEBAR  = "#F8F9FA"

BLUE     = "#1A73E8"
BLUE_DK  = "#1557B0"
BLUE_BG  = "#E8F0FE"
RED      = "#EA4335"
GREEN    = "#34A853"
YELLOW   = "#FBBC04"
PURPLE   = "#8430CE"

TXT      = "#202124"
TXT2     = "#5F6368"
TXT3     = "#80868B"

# safe cross-platform fonts
FH2   = ("Helvetica", 13, "bold")
FBODY = ("Helvetica", 11)
FSMALL= ("Helvetica", 9)
FMONO = ("Courier",   10)
FTINY = ("Helvetica", 8)

MODELS = ["llama-3.3-70b-versatile","llama-3.1-8b-instant",
          "llama3-70b-8192","gemma2-9b-it"]

QUICK_ACTIONS = [
    ("📝 Captions",    "Write punchy social-media captions (3 variations) for this video."),
    ("# Hashtags",     "Generate 20 viral hashtags for this video. Group them by theme."),
    ("📌 Key Points",  "List the top 5 key points from this video as bullet points."),
    ("🐦 Tweet",       "Write a viral tweet thread (5 tweets) summarising this video."),
    ("📧 Email Brief", "Write a professional email briefing a colleague about this video."),
    ("❓ Quiz",        "Create a 5-question multiple-choice quiz based on this video."),
]

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE  (SQLite, lives next to the script)
# ─────────────────────────────────────────────────────────────────────────────
# For installed apps, we must store data in the user's AppData folder.
if getattr(sys, 'frozen', False):
    DATA_DIR = Path(os.path.expandvars(r"%LOCALAPPDATA%")) / "VideoMind"
else:
    DATA_DIR = BASE_PATH

DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "videomind.db"

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def db_init():
    with db_connect() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                source      TEXT,
                transcript  TEXT,
                summary     TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
        """)

def db_new_session(title, source, transcript, summary):
    sid = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    with db_connect() as c:
        c.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?)",
                  (sid, title, source, transcript, summary, now))
    return sid

def db_save_message(sid, role, content):
    now = datetime.now().isoformat(timespec="seconds")
    with db_connect() as c:
        c.execute("INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                  (sid, role, content, now))

def db_get_messages(sid):
    with db_connect() as c:
        return c.execute(
            "SELECT role,content FROM messages WHERE session_id=? ORDER BY id",
            (sid,)).fetchall()

def db_get_session(sid):
    with db_connect() as c:
        return c.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()

def db_list_sessions():
    with db_connect() as c:
        return c.execute(
            "SELECT id,title,created_at FROM sessions ORDER BY created_at DESC"
        ).fetchall()

def db_delete_session(sid):
    with db_connect() as c:
        c.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        c.execute("DELETE FROM sessions WHERE id=?", (sid,))

# ─────────────────────────────────────────────────────────────────────────────
# WIDGETS
# ─────────────────────────────────────────────────────────────────────────────
class MaterialEntry(tk.Frame):
    def __init__(self, parent, label="", show=None, var=None, **kw):
        super().__init__(parent, bg=SURFACE, **kw)
        self._var = var or tk.StringVar()
        tk.Label(self, text=label, font=FSMALL, bg=SURFACE, fg=TXT3
                 ).pack(anchor="w", pady=(0,2))
        self._box = tk.Frame(self, bg=SURF2, highlightthickness=1,
                             highlightbackground=OUTLINE)
        self._box.pack(fill="x")
        self._e = tk.Entry(self._box, textvariable=self._var, show=show or "",
                           font=FBODY, bg=SURF2, fg=TXT,
                           relief="flat", bd=0, insertbackground=BLUE)
        self._e.pack(fill="x", ipady=9, ipadx=10)
        self._e.bind("<FocusIn>",  lambda _: self._box.configure(
            highlightbackground=BLUE, highlightthickness=2))
        self._e.bind("<FocusOut>", lambda _: self._box.configure(
            highlightbackground=OUTLINE, highlightthickness=1))
    def get(self): return self._var.get()

class Chip(tk.Button):
    def __init__(self, parent, text, var, value, **kw):
        super().__init__(parent, text=text, font=FSMALL,
                         relief="flat", bd=0, padx=12, pady=5,
                         cursor="hand2", command=lambda: var.set(value), **kw)
        var.trace_add("write", lambda *_: self._refresh(var, value))
        self._refresh(var, value)
    def _refresh(self, var, value):
        sel = var.get() == value
        self.configure(bg=BLUE_BG if sel else SURF2,
                       fg=BLUE    if sel else TXT2,
                       highlightthickness=1,
                       highlightbackground=BLUE if sel else OUTLINE)

class Stepper(tk.Frame):
    STEPS = ["Extract","Transcribe","Summarize"]
    def __init__(self, parent, **kw):
        super().__init__(parent, bg=SURFACE, **kw)
        self._dots, self._lbls = [], []
        for i, s in enumerate(self.STEPS):
            f = tk.Frame(self, bg=SURFACE); f.pack(side="left", expand=True)
            d = tk.Label(f, text=str(i+1), font=("Helvetica",10,"bold"),
                         width=3, bg=OUTLINE, fg="white"); d.pack()
            l = tk.Label(f, text=s, font=FSMALL, bg=SURFACE, fg=TXT3); l.pack(pady=(2,0))
            self._dots.append(d); self._lbls.append(l)
            if i < 2:
                tk.Frame(self, bg=OUTLINE, height=2, width=30
                         ).pack(side="left", expand=True, fill="x", pady=10)
        self.reset()
    def set_step(self, n):
        for i,(d,l) in enumerate(zip(self._dots, self._lbls)):
            if n==-1 or i<n-1: d.configure(bg=GREEN,text="✓"); l.configure(fg=GREEN)
            elif i==n-1:        d.configure(bg=BLUE, text=str(i+1)); l.configure(fg=BLUE)
            else:               d.configure(bg=OUTLINE,text=str(i+1)); l.configure(fg=TXT3)
    def reset(self): self.set_step(0)

# ─────────────────────────────────────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────────────────────────────────────
class VideoMind(tk.Tk):
    def __init__(self):
        super().__init__()
        db_init()

        self.title("VideoMind")
        self.geometry("1100x820")
        self.minsize(900, 680)
        self.configure(bg=BG)

        # ── app state ──────────────────────────────────────────────────────────
        self.source_var = tk.StringVar(value="🔗  YouTube / URL")
        self.url_var    = tk.StringVar()
        self.model_var  = tk.StringVar(value=MODELS[0])
        self.detail_var = tk.StringVar(value="Standard")
        self.file_path  = None
        self._processing = False

        self._session_id  = None   # active session UUID
        self._transcript  = ""     # cached for chat context
        self._summary     = ""     # cached
        self._chat_history= []     # [{"role":…,"content":…}]

        self._api_key_env = os.environ.get("GROQ_API_KEY", "")

        self._style_ttk()
        self._build_ui()
        self._refresh_sidebar()
        self._check_deps()

    # ── TTK style ─────────────────────────────────────────────────────────────
    def _style_ttk(self):
        s = ttk.Style(); s.theme_use("default")
        s.configure("TCombobox", fieldbackground=SURF2, background=SURF2,
                    foreground=TXT, selectbackground=BLUE,
                    selectforeground="white", borderwidth=0)
        s.configure("TProgressbar", troughcolor=SURF2,
                    background=BLUE, borderwidth=0)
        s.configure("Sidebar.TFrame", background=SIDEBAR)

    # ─────────────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # ── top bar ───────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=SURFACE, height=52,
                       highlightthickness=1, highlightbackground=OUTLINE)
        bar.pack(fill="x"); bar.pack_propagate(False)

        brand = tk.Frame(bar, bg=SURFACE)
        brand.place(relx=0, rely=0.5, anchor="w", x=16)
        for c in [BLUE, RED, YELLOW, GREEN]:
            tk.Label(brand, text="●", font=("Arial",11), bg=SURFACE, fg=c
                     ).pack(side="left")
        tk.Label(brand, text="  VideoMind", font=FH2,
                 bg=SURFACE, fg=TXT).pack(side="left")

        if self._api_key_env:
            tk.Label(bar, text="🔒 .env", font=FSMALL,
                     bg=BLUE_BG, fg=BLUE, padx=6, pady=2
                     ).place(relx=1, rely=0.5, anchor="e", x=-16)

        # ── body: sidebar + notebook ───────────────────────────────────────────
        body = tk.Frame(self, bg=BG); body.pack(fill="both", expand=True)

        # SIDEBAR
        self._sidebar = tk.Frame(body, bg=SIDEBAR, width=210,
                                 highlightthickness=1, highlightbackground=OUTLINE)
        self._sidebar.pack(side="left", fill="y"); self._sidebar.pack_propagate(False)
        self._build_sidebar()

        # MAIN (notebook tabs)
        main = tk.Frame(body, bg=BG); main.pack(side="left", fill="both", expand=True)

        nb = ttk.Notebook(main)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        # Tab 1 – Summarizer
        self._tab_sum = tk.Frame(nb, bg=BG)
        nb.add(self._tab_sum, text="  📹 Summarizer  ")
        self._build_summarizer(self._tab_sum)

        # Tab 2 – Chat
        self._tab_chat = tk.Frame(nb, bg=BG)
        nb.add(self._tab_chat, text="  💬 Chat Assistant  ")
        self._build_chat(self._tab_chat)

        self._nb = nb

    # ── SIDEBAR ───────────────────────────────────────────────────────────────
    def _build_sidebar(self):
        hdr = tk.Frame(self._sidebar, bg=SIDEBAR, pady=10)
        hdr.pack(fill="x", padx=12)
        tk.Label(hdr, text="Chat History", font=("Helvetica",11,"bold"),
                 bg=SIDEBAR, fg=TXT).pack(side="left")

        tk.Button(hdr, text="＋ New", font=FSMALL,
                  bg=BLUE, fg="white", relief="flat", bd=0,
                  padx=8, pady=3, cursor="hand2",
                  command=self._new_session).pack(side="right")

        sep = tk.Frame(self._sidebar, bg=OUTLINE, height=1)
        sep.pack(fill="x")

        # scrollable list
        self._hist_canvas = tk.Canvas(self._sidebar, bg=SIDEBAR,
                                       highlightthickness=0)
        vsb = ttk.Scrollbar(self._sidebar, orient="vertical",
                             command=self._hist_canvas.yview)
        self._hist_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._hist_canvas.pack(side="left", fill="both", expand=True)

        self._hist_frame = tk.Frame(self._hist_canvas, bg=SIDEBAR)
        self._hist_win = self._hist_canvas.create_window(
            (0,0), window=self._hist_frame, anchor="nw")
        self._hist_canvas.bind("<Configure>",
            lambda e: self._hist_canvas.itemconfig(self._hist_win, width=e.width))
        self._hist_frame.bind("<Configure>",
            lambda e: self._hist_canvas.configure(
                scrollregion=self._hist_canvas.bbox("all")))

    def _refresh_sidebar(self):
        for w in self._hist_frame.winfo_children():
            w.destroy()

        sessions = db_list_sessions()
        if not sessions:
            tk.Label(self._hist_frame,
                     text="No sessions yet.\nProcess a video\nto get started.",
                     font=FSMALL, bg=SIDEBAR, fg=TXT3,
                     justify="center").pack(pady=24)
            return

        for row in sessions:
            sid, title, created = row["id"], row["title"], row["created_at"]
            date_str = created[:10]
            active   = (sid == self._session_id)
            item_bg  = BLUE_BG if active else SURFACE

            item = tk.Frame(self._hist_frame, bg=item_bg, cursor="hand2",
                            highlightthickness=1,
                            highlightbackground=BLUE if active else OUTLINE)
            item.pack(fill="x", padx=8, pady=3)

            txt_col = tk.Frame(item, bg=item_bg)
            txt_col.pack(side="left", fill="x", expand=True, padx=(10,4), pady=6)
            tk.Label(txt_col, text=textwrap.shorten(title, 26),
                     font=("Helvetica", 9, "bold"), bg=item_bg,
                     fg=BLUE if active else TXT, anchor="w").pack(anchor="w")
            tk.Label(txt_col, text=date_str, font=FTINY,
                     bg=item_bg, fg=TXT3, anchor="w").pack(anchor="w")

            # always-visible delete button that turns red on hover
            del_btn = tk.Button(item, text="🗑", font=FTINY,
                                bg=item_bg, fg=TXT3,
                                relief="flat", bd=0, padx=6, pady=4,
                                cursor="hand2",
                                command=lambda s=sid: self._delete_session(s))
            del_btn.pack(side="right", padx=(0,6))
            del_btn.bind("<Enter>", lambda e, b=del_btn: b.configure(fg=RED, bg="#FDECEA"))
            del_btn.bind("<Leave>", lambda e, b=del_btn, bg=item_bg: b.configure(fg=TXT3, bg=bg))

            # click row to load session
            for w in [item, txt_col] + list(txt_col.winfo_children()):
                w.bind("<Button-1>", lambda e, s=sid: self._load_session(s))
            # row hover highlight
            for w in [item, txt_col] + list(txt_col.winfo_children()):
                w.bind("<Enter>", lambda e, f=item, bg=item_bg:
                       f.configure(bg="#EEF3FD" if bg != BLUE_BG else BLUE_BG))
                w.bind("<Leave>", lambda e, f=item, bg=item_bg: f.configure(bg=bg))

    # ── SUMMARIZER TAB ────────────────────────────────────────────────────────
    def _build_summarizer(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        vsb    = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        P   = tk.Frame(canvas, bg=BG)
        win = canvas.create_window((0,0), window=P, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        P.bind("<Configure>",
               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def _wheel(e):
            canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _wheel)
        canvas.bind_all("<Button-4>",   lambda e: canvas.yview_scroll(-1,"units"))
        canvas.bind_all("<Button-5>",   lambda e: canvas.yview_scroll( 1,"units"))

        pad = dict(padx=24, pady=6)

        # ── API card ──────────────────────────────────────────────────────────
        c = self._card(P); c.pack(fill="x", **pad)
        inner = tk.Frame(c, bg=SURFACE, padx=16, pady=14); inner.pack(fill="x")

        h = tk.Frame(inner, bg=SURFACE); h.pack(fill="x")
        tk.Label(h, text="🔑  API Key", font=FH2, bg=SURFACE, fg=TXT).pack(side="left")

        if not self._api_key_env:
            lk = tk.Label(h, text="Get free key →", font=FSMALL,
                          bg=SURFACE, fg=BLUE, cursor="hand2")
            lk.pack(side="right")
            lk.bind("<Button-1>", lambda e: webbrowser.open("https://console.groq.com"))
            self._api_entry = MaterialEntry(inner, label="Groq API Key", show="•")
            self._api_entry.pack(fill="x", pady=(10,0))
            tk.Label(inner,
                     text="Tip: add GROQ_API_KEY to a .env file to skip this.",
                     font=FSMALL, bg=SURFACE, fg=TXT3).pack(anchor="w", pady=(4,0))
        else:
            self._api_entry = None
            box = tk.Frame(inner, bg=BLUE_BG,
                           highlightthickness=1, highlightbackground=BLUE)
            box.pack(fill="x", pady=(10,0))
            tk.Label(box, text="✅  API key loaded from .env",
                     font=FSMALL, bg=BLUE_BG, fg=BLUE,
                     padx=10, pady=6).pack(anchor="w")

        # ── Source card ───────────────────────────────────────────────────────
        c2 = self._card(P); c2.pack(fill="x", **pad)
        s2 = tk.Frame(c2, bg=SURFACE, padx=16, pady=14); s2.pack(fill="x")
        tk.Label(s2, text="📹  Video Source", font=FH2, bg=SURFACE, fg=TXT).pack(anchor="w")

        cg = tk.Frame(s2, bg=SURFACE); cg.pack(anchor="w", pady=(8,12))
        for label, val in [("🔗  YouTube / URL","🔗  YouTube / URL"),
                           ("📁  Local file","📁  Local file")]:
            Chip(cg, label, self.source_var, val).pack(side="left", padx=(0,6))

        # URL input
        self._url_panel = tk.Frame(s2, bg=SURFACE)
        self._url_panel.pack(fill="x")
        MaterialEntry(self._url_panel, label="Paste a YouTube or video URL",
                      var=self.url_var).pack(fill="x")

        # File input
        self._file_panel = tk.Frame(s2, bg=SURFACE)
        self._file_panel.pack(fill="x")
        fr = tk.Frame(self._file_panel, bg=SURF2,
                      highlightthickness=1, highlightbackground=OUTLINE)
        fr.pack(fill="x")
        self._file_lbl = tk.Label(fr, text="No file chosen", font=FBODY,
                                   bg=SURF2, fg=TXT3, anchor="w", padx=10)
        self._file_lbl.pack(side="left", fill="x", expand=True, ipady=9)
        tk.Button(fr, text="Browse", font=("Helvetica",10,"bold"),
                  bg=BLUE, fg="white", activebackground=BLUE_DK,
                  activeforeground="white", relief="flat", bd=0,
                  padx=14, cursor="hand2",
                  command=self._browse).pack(side="right", padx=4, pady=4)

        self.source_var.trace_add("write", lambda *_: self._toggle_src())
        self._toggle_src()

        # ── Options card ──────────────────────────────────────────────────────
        c3 = self._card(P); c3.pack(fill="x", **pad)
        o3 = tk.Frame(c3, bg=SURFACE, padx=16, pady=14); o3.pack(fill="x")
        tk.Label(o3, text="⚙️  Options", font=FH2, bg=SURFACE, fg=TXT
                 ).pack(anchor="w", pady=(0,10))
        row = tk.Frame(o3, bg=SURFACE); row.pack(fill="x")

        lf = tk.Frame(row, bg=SURFACE); lf.pack(side="left", fill="x", expand=True, padx=(0,14))
        tk.Label(lf, text="Model", font=FSMALL, bg=SURFACE, fg=TXT3).pack(anchor="w")
        mf = tk.Frame(lf, bg=SURF2, highlightthickness=1, highlightbackground=OUTLINE)
        mf.pack(fill="x", pady=(4,0))
        ttk.Combobox(mf, textvariable=self.model_var, values=MODELS,
                     state="readonly", font=FBODY).pack(fill="x", ipady=6, ipadx=8)

        rf = tk.Frame(row, bg=SURFACE); rf.pack(side="left", fill="x", expand=True)
        tk.Label(rf, text="Summary length", font=FSMALL, bg=SURFACE, fg=TXT3).pack(anchor="w")
        cg2 = tk.Frame(rf, bg=SURFACE); cg2.pack(anchor="w", pady=(6,0))
        for lbl in ["Brief","Standard","Detailed"]:
            Chip(cg2, lbl, self.detail_var, lbl).pack(side="left", padx=(0,5))

        # ── Generate button ───────────────────────────────────────────────────
        bf = tk.Frame(P, bg=BG); bf.pack(fill="x", padx=24, pady=(4,6))
        self._run_btn = tk.Button(bf, text="▶   Generate Summary",
                                  font=("Helvetica",13,"bold"),
                                  bg=BLUE, fg="white",
                                  activebackground=BLUE_DK, activeforeground="white",
                                  relief="flat", bd=0, pady=13, cursor="hand2",
                                  command=self._start)
        self._run_btn.pack(fill="x")

        # ── Progress card ─────────────────────────────────────────────────────
        c4 = self._card(P); c4.pack(fill="x", **pad)
        p4 = tk.Frame(c4, bg=SURFACE, padx=16, pady=14); p4.pack(fill="x")
        self._stepper = Stepper(p4); self._stepper.pack(fill="x", pady=(0,10))
        self._prog = ttk.Progressbar(p4, mode="indeterminate"); self._prog.pack(fill="x")
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(p4, textvariable=self._status_var, font=FSMALL,
                 bg=SURFACE, fg=TXT3).pack(anchor="w", pady=(6,0))

        # ── Summary output card ───────────────────────────────────────────────
        c5 = self._card(P); c5.pack(fill="x", padx=24, pady=(6,24))
        o5 = tk.Frame(c5, bg=SURFACE, padx=16, pady=14); o5.pack(fill="x")

        oh = tk.Frame(o5, bg=SURFACE); oh.pack(fill="x")
        tk.Label(oh, text="📄  Summary", font=FH2, bg=SURFACE, fg=TXT).pack(side="left")
        brow = tk.Frame(oh, bg=SURFACE); brow.pack(side="right")
        tk.Button(brow, text="📋 Copy", font=FSMALL, bg=SURF2, fg=TXT2,
                  relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                  highlightthickness=1, highlightbackground=OUTLINE,
                  command=self._copy_summary).pack(side="left", padx=(0,6))
        tk.Button(brow, text="💬 Open Chat", font=FSMALL, bg=BLUE_BG, fg=BLUE,
                  relief="flat", bd=0, padx=8, pady=3, cursor="hand2",
                  highlightthickness=1, highlightbackground=BLUE,
                  command=lambda: self._nb.select(self._tab_chat)
                  ).pack(side="left")

        self._sum_box = scrolledtext.ScrolledText(
            o5, font=FMONO, bg=SURF2, fg=TXT,
            insertbackground=BLUE, relief="flat", bd=0,
            wrap="word", padx=12, pady=10, state="disabled", height=10,
            highlightthickness=1, highlightbackground=OUTLINE)
        self._sum_box.pack(fill="both", expand=True, pady=(10,0))

    # ── CHAT TAB ──────────────────────────────────────────────────────────────
    def _build_chat(self, parent):
        # top info bar
        self._chat_info_var = tk.StringVar(value="No session loaded — generate a summary first.")
        info_bar = tk.Frame(parent, bg=BLUE_BG, pady=6)
        info_bar.pack(fill="x")
        tk.Label(info_bar, textvariable=self._chat_info_var,
                 font=FSMALL, bg=BLUE_BG, fg=BLUE, padx=14).pack(side="left")

        # session management buttons in the chat bar
        mgmt = tk.Frame(info_bar, bg=BLUE_BG)
        mgmt.pack(side="right", padx=10)
        tk.Button(mgmt, text="🗑  Delete Session", font=FSMALL,
                  bg="#FDECEA", fg=RED, relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  highlightthickness=1, highlightbackground=RED,
                  command=self._delete_current_session).pack(side="left", padx=(0,6))
        tk.Button(mgmt, text="🧹 Clear Chat", font=FSMALL,
                  bg=SURF2, fg=TXT2, relief="flat", bd=0,
                  padx=10, pady=3, cursor="hand2",
                  highlightthickness=1, highlightbackground=OUTLINE,
                  command=self._clear_chat_display).pack(side="left")

        # quick-action bar
        qa_bar = tk.Frame(parent, bg=SURF2, pady=6)
        qa_bar.pack(fill="x")
        tk.Label(qa_bar, text="Quick:", font=FSMALL, bg=SURF2, fg=TXT3,
                 padx=10).pack(side="left")
        for label, prompt in QUICK_ACTIONS:
            tk.Button(qa_bar, text=label, font=FTINY,
                      bg=SURFACE, fg=TXT2, relief="flat", bd=0,
                      padx=8, pady=4, cursor="hand2",
                      highlightthickness=1, highlightbackground=OUTLINE,
                      command=lambda p=prompt: self._quick_action(p)
                      ).pack(side="left", padx=(0,5))

        # chat display (read-only scrolled text with tags)
        self._chat_box = scrolledtext.ScrolledText(
            parent, font=FBODY, bg=BG, fg=TXT,
            relief="flat", bd=0, wrap="word",
            padx=16, pady=12, state="disabled",
            highlightthickness=0)
        self._chat_box.pack(fill="both", expand=True)
        self._chat_box.tag_configure("user",      foreground=BLUE_DK,
                                      font=("Helvetica",11,"bold"))
        self._chat_box.tag_configure("user_text", foreground=TXT,
                                      lmargin1=24, lmargin2=24)
        self._chat_box.tag_configure("bot",       foreground=GREEN,
                                      font=("Helvetica",11,"bold"))
        self._chat_box.tag_configure("bot_text",  foreground=TXT,
                                      lmargin1=24, lmargin2=24)
        self._chat_box.tag_configure("sys",       foreground=TXT3,
                                      font=("Helvetica",9,"italic"),
                                      justify="center")
        self._chat_box.tag_configure("thinking",  foreground=PURPLE,
                                      font=("Helvetica",10,"italic"))

        # input row
        inp_row = tk.Frame(parent, bg=SURFACE,
                           highlightthickness=1, highlightbackground=OUTLINE)
        inp_row.pack(fill="x")
        self._chat_input = tk.Text(inp_row, font=FBODY, bg=SURFACE, fg=TXT,
                                    relief="flat", bd=0, height=3,
                                    insertbackground=BLUE, wrap="word",
                                    padx=12, pady=8)
        self._chat_input.pack(side="left", fill="both", expand=True)
        self._chat_input.bind("<Return>",       self._on_enter)
        self._chat_input.bind("<Shift-Return>", lambda e: None)  # allow newline

        send_col = tk.Frame(inp_row, bg=SURFACE); send_col.pack(side="right", padx=8, pady=8)
        self._send_btn = tk.Button(send_col, text="Send ➤",
                                   font=("Helvetica",11,"bold"),
                                   bg=BLUE, fg="white",
                                   activebackground=BLUE_DK, activeforeground="white",
                                   relief="flat", bd=0, padx=14, pady=8,
                                   cursor="hand2", command=self._send_message)
        self._send_btn.pack()
        tk.Label(send_col, text="Shift+↵ = newline", font=FTINY,
                 bg=SURFACE, fg=TXT3).pack(pady=(4,0))

    # ─────────────────────────────────────────────────────────────────────────
    # SUMMARIZER LOGIC
    # ─────────────────────────────────────────────────────────────────────────
    def _start(self):
        if self._processing: return
        if MISSING:
            messagebox.showerror("Missing packages",
                f"Install:\n  pip install {' '.join(MISSING)}")
            return
        if not self._api_key():
            messagebox.showerror("No API Key",
                "Enter your Groq API key above or add GROQ_API_KEY to .env")
            return
        src = self.source_var.get()
        if "URL" in src and not self.url_var.get().strip():
            messagebox.showerror("No URL", "Please paste a video URL.")
            return
        if "file" in src.lower() and not self.file_path:
            messagebox.showerror("No File", "Please browse and select a video file.")
            return

        self._processing = True
        self._run_btn.configure(state="disabled", text="Processing…")
        self._prog.start(12)
        self._set_summary("")
        self._stepper.reset()
        threading.Thread(target=self._pipeline, daemon=True).start()

    def _pipeline(self):
        tmp = None
        try:
            self._status("Extracting audio…")
            self._stepper.set_step(1)
            tmp = self._extract_audio()

            self._status("Transcribing with Whisper…")
            self._stepper.set_step(2)
            transcript = whisper.load_model("base").transcribe(tmp)["text"]
            if not transcript.strip():
                raise ValueError("Empty transcript — is there speech in the video?")

            self._status("Generating summary with Groq ⚡…")
            self._stepper.set_step(3)
            summary = self._ai_summarize(transcript)

            self._stepper.set_step(-1)

            # save session
            source_label = (self.url_var.get().strip() if "URL" in self.source_var.get()
                            else os.path.basename(self.file_path or ""))
            title = source_label[:60] or "Video session"
            sid = db_new_session(title, source_label, transcript, summary)

            self._transcript   = transcript
            self._summary      = summary
            self._session_id   = sid
            self._chat_history = []

            # seed chat with summary as system context
            db_save_message(sid, "system",
                f"[Video transcript loaded. Summary: {summary[:500]}…]")

            self._set_summary(summary)
            self._status("✅  Done!")
            self.after(0, self._on_session_ready)

        except Exception as e:
            self._stepper.reset()
            self._set_summary(f"❌  Error\n\n{e}\n\nCommon fixes:\n"
                              "• Check internet connection\n"
                              "• Verify Groq API key\n"
                              "• Ensure ffmpeg is installed")
            self._status("Failed — see output above.")
        finally:
            if tmp and os.path.exists(tmp):
                try: os.remove(tmp)
                except: pass
            self.after(0, self._reset_ui)

    def _on_session_ready(self):
        self._refresh_sidebar()
        self._chat_info_var.set(
            f"Session: {self._session_id[:8]}…  |  "
            f"{len(self._transcript.split())} words transcribed  |  "
            "Ask anything about this video ↓")
        self._append_chat("sys",
            "✅  Video processed! Ask me anything about it, or use Quick Actions above.")

    def _extract_audio(self):
        _, tmp = tempfile.mkstemp(suffix=".wav")
        if "URL" in self.source_var.get():
            url = self.url_var.get().strip()
            base = tmp[:-4]
            opts = {"format":"bestaudio/best",
                    "outtmpl": base+".%(ext)s",
                    "postprocessors":[{"key":"FFmpegExtractAudio",
                                       "preferredcodec":"wav"}],
                    "quiet":True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            os.remove(tmp)
            for ext in (".wav",".m4a",".mp3",".webm",".ogg"):
                if os.path.exists(base+ext): return base+ext
            raise FileNotFoundError("Audio file not found after download.")
        else:
            # close & remove the initial mkstemp placeholder
            try: os.close(_); os.remove(tmp)
            except: pass

            # Copy to ASCII-safe temp path with correct extension
            src_ext = Path(self.file_path).suffix or ".mp4"
            fd1, safe_src = tempfile.mkstemp(suffix=src_ext)
            os.close(fd1)

            fd2, out_wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd2); os.remove(out_wav)  # ffmpeg must create this itself

            try:
                shutil.copy2(self.file_path, safe_src)

                # ── Step 1: probe for audio streams ───────────────────────────
                probe = subprocess.run(
                [FFPROBE_BIN, "-v", "error",
                     "-select_streams", "a",
                     "-show_entries", "stream=codec_type",
                     "-of", "default=noprint_wrappers=1",
                     safe_src],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                has_audio = b"codec_type=audio" in probe.stdout

                if not has_audio:
                    raise RuntimeError(
                        "This video file has no audio track.\n\n"
                        "The file appears to be video-only (no speech to transcribe).\n"
                        "Tips:\n"
                        "• Try a different video that has spoken audio\n"
                        "• If you downloaded it, try re-downloading with audio included\n"
                        "• YouTube videos: make sure you're not using a video-only format")

                # ── Step 2: extract audio ─────────────────────────────────────
                result = subprocess.run(
                    [FFMPEG_BIN, "-y",
                     "-i",      safe_src,
                     "-vn",                    # drop video
                     "-acodec", "pcm_s16le",   # PCM WAV
                     "-ar",     "16000",        # 16 kHz for Whisper
                     "-ac",     "1",            # mono
                     out_wav],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE)

                if result.returncode != 0:
                    err   = result.stderr.decode(errors="replace").strip()
                    brief = "\n".join(err.splitlines()[-4:])
                    raise RuntimeError(
                        f"ffmpeg failed (code {result.returncode}):\n{brief}\n\n"
                        "Run  ffmpeg -version  in a terminal to confirm it is installed.")
            finally:
                try: os.remove(safe_src)
                except: pass
            return out_wav

    def _ai_summarize(self, transcript):
        hint = {"brief":"2-3 concise sentences",
                "standard":"5-6 sentences covering all key points",
                "detailed":"a well-structured 2-3 paragraph summary"
                }.get(self.detail_var.get().lower(), "5-6 sentences")
        r = Groq(api_key=self._api_key()).chat.completions.create(
            model=self.model_var.get(), max_tokens=1024,
            messages=[
                {"role":"system","content":"You summarize video transcripts clearly and accurately."},
                {"role":"user","content":
                 f"Summarize this transcript in {hint}. "
                 f"Focus on main topic, key points, takeaways.\n\nTRANSCRIPT:\n{transcript[:14000]}"}
            ])
        return r.choices[0].message.content

    # ─────────────────────────────────────────────────────────────────────────
    # CHAT LOGIC
    # ─────────────────────────────────────────────────────────────────────────
    def _on_enter(self, event):
        """Send on Enter, newline on Shift+Enter."""
        if event.state & 0x1:   # Shift held
            return               # let tkinter insert newline
        self._send_message()
        return "break"

    def _send_message(self):
        if not self._session_id:
            messagebox.showinfo("No session",
                "Generate a video summary first — then chat about it!")
            return
        msg = self._chat_input.get("1.0","end").strip()
        if not msg: return
        self._chat_input.delete("1.0","end")
        self._chat_input.configure(state="disabled")
        self._send_btn.configure(state="disabled")
        threading.Thread(target=self._chat_pipeline, args=(msg,), daemon=True).start()

    def _quick_action(self, prompt):
        if not self._session_id:
            messagebox.showinfo("No session",
                "Generate a video summary first — then use Quick Actions!")
            return
        self._chat_input.delete("1.0","end")
        self._chat_input.insert("end", prompt)
        self._send_message()

    def _chat_pipeline(self, user_msg):
        try:
            self._append_chat("user", user_msg)
            db_save_message(self._session_id, "user", user_msg)

            self.after(0, lambda: self._append_chat("thinking", "⏳ Thinking…"))

            # build context
            system_ctx = (
                "You are VideoMind, an expert AI assistant. "
                "The user has processed a video. "
                "Here is the transcript (may be truncated):\n\n"
                f"{self._transcript[:12000]}\n\n"
                f"Summary:\n{self._summary}\n\n"
                "Answer the user's questions about this video accurately. "
                "If asked to generate captions, hashtags, tweets, emails, or quizzes, "
                "do so based on the video content."
            )

            # full history for context
            history = [{"role":r["role"],"content":r["content"]}
                       for r in db_get_messages(self._session_id)
                       if r["role"] in ("user","assistant")]
            history.append({"role":"user","content":user_msg})

            resp = Groq(api_key=self._api_key()).chat.completions.create(
                model=self.model_var.get(), max_tokens=2048,
                messages=[{"role":"system","content":system_ctx}] + history[-20:])

            reply = resp.choices[0].message.content
            db_save_message(self._session_id, "assistant", reply)

            self._remove_thinking()
            self._append_chat("bot", reply)

        except Exception as e:
            self._remove_thinking()
            self._append_chat("sys", f"❌ Error: {e}")
        finally:
            self.after(0, self._reset_chat_input)

    def _append_chat(self, role, text):
        def _do():
            self._chat_box.configure(state="normal")
            if role == "user":
                self._chat_box.insert("end", "\nYou\n", "user")
                self._chat_box.insert("end", text+"\n", "user_text")
            elif role == "bot":
                self._chat_box.insert("end", "\nVideoMind\n", "bot")
                self._chat_box.insert("end", text+"\n", "bot_text")
            elif role == "thinking":
                self._chat_box.insert("end", text+"\n", "thinking")
            else:
                self._chat_box.insert("end", f"\n{text}\n", "sys")
            self._chat_box.configure(state="disabled")
            self._chat_box.see("end")
        self.after(0, _do)

    def _remove_thinking(self):
        def _do():
            self._chat_box.configure(state="normal")
            ranges = self._chat_box.tag_ranges("thinking")
            if ranges:
                self._chat_box.delete(ranges[0], ranges[-1])
            self._chat_box.configure(state="disabled")
        self.after(0, _do)

    def _reset_chat_input(self):
        self._chat_input.configure(state="normal")
        self._send_btn.configure(state="normal")
        self._chat_input.focus_set()

    # ─────────────────────────────────────────────────────────────────────────
    # SESSION MANAGEMENT
    # ─────────────────────────────────────────────────────────────────────────
    def _load_session(self, sid):
        row = db_get_session(sid)
        if not row: return
        self._session_id  = sid
        self._transcript  = row["transcript"] or ""
        self._summary     = row["summary"]    or ""
        self._chat_history= []

        self._set_summary(self._summary)
        self._chat_info_var.set(
            f"Session: {sid[:8]}…  |  Source: {(row['source'] or '')[:40]}")

        # reload chat messages
        self._chat_box.configure(state="normal")
        self._chat_box.delete("1.0","end")
        self._chat_box.configure(state="disabled")
        for msg in db_get_messages(sid):
            if msg["role"] == "user":
                self._append_chat("user", msg["content"])
            elif msg["role"] == "assistant":
                self._append_chat("bot", msg["content"])

        self._refresh_sidebar()
        self._nb.select(self._tab_chat)

    def _new_session(self):
        self._session_id  = None
        self._transcript  = ""
        self._summary     = ""
        self._chat_history= []
        self._set_summary("")
        self._chat_box.configure(state="normal")
        self._chat_box.delete("1.0","end")
        self._chat_box.configure(state="disabled")
        self._chat_info_var.set("New session — generate a summary to begin.")
        self._refresh_sidebar()
        self._nb.select(self._tab_sum)

    def _delete_current_session(self):
        """Delete button inside the chat tab — deletes the active session."""
        if not self._session_id:
            messagebox.showinfo("Nothing to delete", "No session is currently active.")
            return
        self._delete_session(self._session_id)

    def _clear_chat_display(self):
        """Wipe the visible chat bubbles without deleting the saved session."""
        self._chat_box.configure(state="normal")
        self._chat_box.delete("1.0", "end")
        self._chat_box.configure(state="disabled")

    def _delete_session(self, sid):
        if not messagebox.askyesno("Delete Session",
                "This will permanently delete this session and all its chat history.\n\nContinue?"):
            return
        db_delete_session(sid)
        if self._session_id == sid:
            self._new_session()
        else:
            self._refresh_sidebar()

    # ─────────────────────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────────────────────
    def _card(self, parent):
        return tk.Frame(parent, bg=SURFACE,
                        highlightthickness=1, highlightbackground=OUTLINE,
                        relief="flat")

    def _toggle_src(self):
        if "URL" in self.source_var.get():
            self._url_panel.lift()
        else:
            self._file_panel.lift()

    def _browse(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video","*.mp4 *.mkv *.mov *.avi *.webm *.flv"),
                       ("All","*.*")])
        if p:
            self.file_path = p
            self._file_lbl.configure(text=os.path.basename(p), fg=TXT)

    def _api_key(self):
        if self._api_key_env: return self._api_key_env
        if self._api_entry:   return self._api_entry.get().strip()
        return ""

    def _copy_summary(self):
        t = self._sum_box.get("1.0","end").strip()
        if t: self.clipboard_clear(); self.clipboard_append(t)

    def _check_deps(self):
        if MISSING:
            self._set_summary(
                f"⚠️  Missing packages: {', '.join(MISSING)}\n\n"
                f"Run:\n    pip install {' '.join(MISSING)}\n\n"
                "Also install ffmpeg:\n"
                "  macOS:   brew install ffmpeg\n"
                "  Ubuntu:  sudo apt install ffmpeg\n"
                "  Windows: https://ffmpeg.org/download.html")

    def _status(self, msg):
        self.after(0, lambda: self._status_var.set(msg))

    def _set_summary(self, text):
        def _do():
            self._sum_box.configure(state="normal")
            self._sum_box.delete("1.0","end")
            self._sum_box.insert("end", text)
            self._sum_box.configure(state="disabled")
        self.after(0, _do)

    def _reset_ui(self):
        self._processing = False
        self._prog.stop()
        self._run_btn.configure(state="normal", text="▶   Generate Summary")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = VideoMind()
    app.mainloop()