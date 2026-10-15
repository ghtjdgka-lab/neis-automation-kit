# -*- coding: utf-8 -*-
"""나이스·에듀파인 바로가기 위젯 — 바탕화면에 떠 있는 작은 단추 넷.

  .\\.venv\\Scripts\\pythonw.exe widget\\바로가기위젯.pyw      (설정하면 바탕화면 바로가기가 생긴다)

  [나이스] [에듀파인] [문서등록대장] [공람]  — 누르면 인증서 자동 로그인까지 해서 그 화면을 맨 앞에 띄운다.
  위젯이 뜰 때 두 크롬을 «최소화된 채로» 미리 로그인해 두고 5분마다 세션을 살려 두므로, 클릭은 보통 1~2초.
  오른쪽 클릭: 인증서 설정 · 미리 열어두기 켜고 끄기 · 크롬 창 닫기 · 위젯 끄기.  끌어서 옮길 수 있다.

안 될 때: %LOCALAPPDATA%\\neis-automation\\widget.log 에 무슨 명령이 얼마 걸려 어떻게 끝났는지 한 줄씩 남는다.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "바로가기_엔진.py"
SETUP = HERE / "바로가기_설정.py"
PY = Path(sys.executable).with_name("python.exe")
BASE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "neis-automation"
STATE = BASE / "widget_state.json"
LOG = BASE / "widget.log"
CONFIG = BASE / "teacher_config.json"
NO_WINDOW = 0x08000000
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
WARM_EVERY = 5 * 60 * 1000
PORTS = {"neis": 9322, "edufine": 9324}

BG, INK, LINE = "#fffaf2", "#3b2f25", "#d9ccb8"
BTNS = [("나이스", "neis", "open", "#1b6fb5"), ("에듀파인", "edufine", "main", "#2f7d4f"),
        ("문서등록대장", "edufine", "open", "#8a5a2b"), ("공람", "edufine", "cnrs", "#6b4fb5")]


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(**kw):
    st = load_state()
    st.update(kw)
    BASE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def log(what, lines, t0):
    try:
        steps = " / ".join(ln[5:].split("  (")[0] for ln in lines if ln.startswith("STEP "))[:300]
        last = next((ln for ln in reversed(lines) if ln.startswith(("READY", "FAIL", "CLOSED"))), "(없음)")
        row = "%s  %s  %.1fs  %s  [%s]" % (datetime.now().strftime("%m-%d %H:%M:%S"), what, time.time() - t0, last[:100], steps)
        old = LOG.read_text(encoding="utf-8").splitlines()[-300:] if LOG.exists() else []
        BASE.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(old + [row]) + "\n", encoding="utf-8")
    except Exception:
        pass


def port_alive(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=1.5) as r:
            return bool(json.load(r).get("Browser"))
    except Exception:
        return False


def configured():
    try:
        return bool(json.loads(CONFIG.read_text(encoding="utf-8")).get("cert_name"))
    except Exception:
        return False


class Widget:
    def __init__(self):
        st = load_state()
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        sw = self.root.winfo_screenwidth()
        self.root.geometry("+%d+%d" % (st.get("x", sw - 470), st.get("y", 12)))
        self.prewarm = st.get("prewarm", True)
        self.locks = {"neis": threading.Lock(), "edufine": threading.Lock()}
        self.busy = None
        self.note = ("", INK)

        fr = tk.Frame(self.root, bg=BG, highlightbackground=LINE, highlightthickness=1)
        fr.pack()
        grip = tk.Label(fr, text="⋮", bg=BG, fg="#b5a593", font=("Malgun Gothic", 12), cursor="fleur", padx=4)
        grip.pack(side="left", fill="y")
        self.buttons = {}
        for text, site, cmd, color in BTNS:
            b = tk.Label(fr, text=text, bg=BG, fg=color, font=("Malgun Gothic", 10, "bold"), padx=9, pady=6, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, s=site, c=cmd, t=text: self.click(s, c, t))
            b.bind("<Enter>", lambda e, w=b: w.configure(bg="#f3e9da"))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=BG))
            self.buttons[text] = b
        self.status = tk.Label(fr, text="", bg=BG, fg="#8a7a68", font=("Malgun Gothic", 9), padx=6)
        self.status.pack(side="left")
        for w in (fr, grip):
            w.bind("<ButtonPress-1>", self.press)
            w.bind("<B1-Motion>", self.drag)
            w.bind("<ButtonRelease-1>", self.release)
        for w in (fr, grip, self.status, *self.buttons.values()):
            w.bind("<Button-3>", self.menu)

        self.m = tk.Menu(self.root, tearoff=0, font=("Malgun Gothic", 9))
        self.m.add_command(label="인증서 설정 (처음 한 번)", command=self.open_setup)
        self.prewarm_var = tk.BooleanVar(value=self.prewarm)
        self.m.add_checkbutton(label="미리 열어두기 (빠른 클릭)", variable=self.prewarm_var, command=self.toggle_prewarm)
        self.m.add_command(label="지금 미리 열어두기", command=lambda: self.warm_all(True))
        self.m.add_separator()
        self.m.add_command(label="위젯용 크롬 창 닫기", command=self.close_chrome)
        self.m.add_command(label="위젯 끄기", command=self.root.destroy)

    # ── 끌기 ──
    def press(self, e):
        self.sx, self.sy = e.x_root, e.y_root
        self.wx, self.wy = self.root.winfo_x(), self.root.winfo_y()

    def drag(self, e):
        self.root.geometry("+%d+%d" % (self.wx + e.x_root - self.sx, self.wy + e.y_root - self.sy))

    def release(self, e):
        save_state(x=self.root.winfo_x(), y=self.root.winfo_y())

    def menu(self, e):
        self.m.tk_popup(e.x_root, e.y_root)

    # ── 말풍선 ──
    def say(self, text, color=INK, ms=4000):
        self.status.configure(text=text, fg=color)
        self.root.after(ms, lambda: self.status.configure(text="") if self.status.cget("text") == text else None)

    def tick(self):
        if self.busy:
            dots = "." * (int(time.time() * 2) % 3 + 1)
            self.status.configure(text=self.busy + dots, fg="#8a7a68")
        self.root.after(400, self.tick)

    # ── 엔진 부르기 ──
    def run(self, site, cmd, extra=(), what=None, on_step=None):
        t0 = time.time()
        seen, last = [], ""
        with self.locks[site]:
            p = subprocess.Popen([str(PY), "-X", "utf8", str(ENGINE), site, cmd, *extra], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                 env=ENV, cwd=str(HERE), creationflags=NO_WINDOW)
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(p.pid)   # 클릭을 받은 건 위젯 — 창 꺼낼 권한을 넘긴다
            except Exception:
                pass
            for line in p.stdout:
                line = line.strip()
                seen.append(line)
                if line.startswith("STEP ") and on_step:
                    on_step(line[5:].split("  (")[0])
                elif line.startswith(("READY", "FAIL", "CLOSED")):
                    last = line
            p.wait()
        log(what or "%s %s" % (site, cmd), seen, t0)
        return last

    def click(self, site, cmd, text):
        if self.busy:
            return
        if not configured():
            self.say("먼저 오른쪽 클릭 → 인증서 설정", "#c0392b", 6000)
            return
        self.busy = text + " 여는 중"

        def fn():
            try:
                last = self.run(site, cmd, what="click " + text, on_step=lambda s: setattr(self, "busy", s))
            finally:
                self.busy = None
            if last.startswith("READY"):
                self.root.after(0, self.say, "짠! 열렸어요", "#2f7d4f")
            else:
                self.root.after(0, self.say, "앗, 실패: " + (last[5:] or "알 수 없는 오류"), "#c0392b", 10000)
        threading.Thread(target=fn, daemon=True).start()

    # ── 미리 열어두기 ──
    def warm(self, site, launch):
        if not configured() or not self.locks[site].acquire(blocking=False):
            return
        self.locks[site].release()
        self.run(site, "warm", ["--launch"] if launch else [], what="warm %s%s" % (site, " --launch" if launch else ""))

    def warm_all(self, launch):
        for site in ("neis", "edufine"):
            threading.Thread(target=self.warm, args=(site, launch), daemon=True).start()

    def loop_warm(self):
        if self.prewarm and not self.busy:
            self.warm_all(False)
        self.root.after(WARM_EVERY, self.loop_warm)

    def toggle_prewarm(self):
        self.prewarm = bool(self.prewarm_var.get())
        save_state(prewarm=self.prewarm)
        self.say("미리 열어둘게요" if self.prewarm else "미리 안 열어요")
        if self.prewarm:
            self.warm_all(True)

    # ── 설정·닫기 ──
    def open_setup(self):
        subprocess.Popen([str(PY), "-X", "utf8", str(SETUP)], cwd=str(HERE), env=ENV, creationflags=0x00000010)  # CREATE_NEW_CONSOLE
        self.say("검은 창에서 설정을 마쳐 주세요", INK, 8000)

    def close_chrome(self):
        def fn():
            for site in ("neis", "edufine"):
                self.run(site, "close", what="close " + site)
            self.root.after(0, self.say, "닫았어요")
        threading.Thread(target=fn, daemon=True).start()

    def mainloop(self):
        self.tick()
        self.root.after(WARM_EVERY, self.loop_warm)
        if not configured():
            self.root.after(800, lambda: self.say("오른쪽 클릭 → 인증서 설정부터 해 주세요", "#c0392b", 15000))
        elif self.prewarm:
            self.root.after(1500, lambda: self.warm_all(True))
        self.root.mainloop()


if __name__ == "__main__":
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "neis-edufine-widget")
    if ctypes.windll.kernel32.GetLastError() == 183:      # 이미 떠 있다
        sys.exit(0)
    Widget().mainloop()
