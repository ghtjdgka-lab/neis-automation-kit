# -*- coding: utf-8 -*-
"""상벌점(하이에듀) 위젯 — 나이스·에듀파인 위젯과 따로 떠 있는 캐릭터 하나. 마우스를 대면 옆에 단추 둘이 뜬다.

  .\\.venv\\Scripts\\pythonw.exe widget\\하이에듀_위젯.pyw      (설치: 하이에듀위젯_설치.cmd)

  [상벌점]  하이에듀 첫 화면 (아이디·암호 → 인증서까지 자동 로그인)
  [우리반]  우리 반 상벌점 현황을 하이에듀에서 읽어 와 위젯 아래로 표를 펼친다 (안 보이는 크롬, 약 9초).
            다시 누르면 접고, 10분 안에 또 누르면 다시 안 읽고 바로 편다. [사이트에서 보기] 는 크롬으로 우리 반만 띄운다.
  크롬은 상벌점 전용(포트 9326)이라 나이스·에듀파인 위젯 크롬과 섞이지 않는다. 일은 하이에듀_엔진.py 가 한다.
  캐릭터 = widget 폴더의 «상벌점_그림.png»(없으면 «상벌점» 글자). 오른쪽 클릭 «캐릭터 그림 바꾸기…» 로 아무 그림이나 고르면
  바탕을 지우고(모눈종이 도트 그림은 칸마다 한 점으로) 바로 바꿔 끼운다.
  캐릭터를 누르면 [우리반]과 같고, 끌면 옮겨진다. 오른쪽 클릭: 상벌점 설정 · 항상 위에 띄우기 · 캐릭터 그림 · 상벌점 크롬 닫기 · 위젯 끄기.
  처음 켤 때 설정이 비어 있으면 설정 창(하이에듀 아이디·비밀번호, 인증서·인증서 암호, 학년·반)이 뜬다. 전부 자격 증명 관리자에만 저장.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE = HERE / "하이에듀_엔진.py"
PY = Path(sys.executable).with_name("python.exe")
BASE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "neis-automation"
STATE = BASE / "hiedu_widget_state.json"
NO_WINDOW = 0x08000000
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

BG, INK, LINE = "#fffaf2", "#3b2f25", "#d9ccb8"
ART_H = 54          # 캐릭터 높이
KEY = "#ff00fe"      # 투명으로 뚫을 색 — 그림에 안 쓰이는 색
BTNS = [("상벌점", "open", "#b07a00"), ("우리반", "data", "#2f7d4f")]


def _grid_lines(means):
    """한 줄로 늘어선 밝기에서 모눈 선(주변보다 어두운 골)을 찾아 (첫 선, 간격) — 고르게 반복될 때만."""
    avg = sum(means) / len(means)
    pos = [i for i in range(1, len(means) - 1) if means[i] < avg - 25 and means[i] <= means[i - 1] and means[i] <= means[i + 1]]
    pos = [x for i, x in enumerate(pos) if i == 0 or x - pos[i - 1] > 2]          # 두 픽셀짜리 선은 하나로
    if len(pos) < 8:
        return None
    gaps = sorted(b - a for a, b in zip(pos, pos[1:]))
    step = gaps[len(gaps) // 2]
    if step < 6 or sum(abs(g - step) <= 2 for g in gaps) < 0.7 * len(gaps):
        return None
    step = (pos[-1] - pos[0]) / round((pos[-1] - pos[0]) / step)                    # 소수 간격까지 (예: 23.6)
    return pos[0], step


def make_sprite(src):
    """아무 그림 → 바탕이 투명한 캐릭터 그림. ① 이미 바탕이 투명하면 그대로 ② 모눈종이 위 도트 그림이면 칸마다 한 점
    ③ 그 밖에는 가장자리와 이어진 바탕색만 지운다 (캐릭터 안쪽 흰색은 남는다). 끝으로 캐릭터만 남게 자른다."""
    from collections import Counter, deque
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    W, H = im.size
    corners = [im.getpixel(c)[3] for c in ((0, 0), (W - 1, 0), (0, H - 1), (W - 1, H - 1))]
    if max(corners) < 128:
        return im.crop(im.getbbox())
    rgb = im.convert("RGB")
    if max(W, H) > 1600:
        rgb.thumbnail((1600, 1600))
        W, H = rgb.size
    px = rgb.load()
    band = max(4, H // 10)
    ys = range(0, band, 2)
    gx = _grid_lines([sum(sum(px[x, y]) for y in ys) / len(ys) for x in range(W)])     # 위쪽 띠(보통 바탕)의 세로 선
    xs = range(0, max(4, W // 10), 2)
    gy = _grid_lines([sum(sum(px[x, y]) for x in xs) / len(xs) for y in range(H)])     # 왼쪽 띠의 가로 선
    if gx and gy:       # 모눈 한 칸 = 도트 한 점
        (x0, sx), (y0, sy) = gx, gy
        x0, y0 = x0 % sx, y0 % sy
        cols, rows = int((W - x0) // sx), int((H - y0) // sy)
        d = max(1, int(min(sx, sy) / 5))
        small = Image.new("RGB", (cols, rows))
        for r in range(rows):
            for c in range(cols):
                cx, cy = int(x0 + (c + .5) * sx), int(y0 + (r + .5) * sy)
                pts = [px[min(W - 1, cx + a), min(H - 1, cy + b)] for a in (-d, 0, d) for b in (-d, 0, d)]
                small.putpixel((c, r), Counter(pts).most_common(1)[0][0])
        rgb = small
    elif max(W, H) > 300:
        rgb = rgb.resize((max(1, W * 300 // max(W, H)), max(1, H * 300 // max(W, H))), Image.BOX)
    W, H = rgb.size
    px = rgb.load()
    edge = [px[x, y] for x in range(W) for y in (0, H - 1)] + [px[x, y] for y in range(H) for x in (0, W - 1)]
    bgc = Counter(edge).most_common(1)[0][0]
    pale = sum(bgc) > 600       # 흰 바탕이면 연회색(모눈 선·그림자)도 바탕으로 — 바깥과 이어진 것만 지우니 캐릭터 안 흰색은 남는다
    near = lambda c: sum(abs(a - b) for a, b in zip(c, bgc)) < 60 or (pale and min(c) > 185 and max(c) - min(c) < 20)
    out = rgb.convert("RGBA")
    seen = [[False] * W for _ in range(H)]
    q = deque((x, y) for x in range(W) for y in (0, H - 1)) + deque((x, y) for y in range(H) for x in (0, W - 1))
    while q:
        x, y = q.popleft()
        if not (0 <= x < W and 0 <= y < H) or seen[y][x] or not near(px[x, y]):
            continue
        seen[y][x] = True
        out.putpixel((x, y), (0, 0, 0, 0))
        q.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    # 캐릭터와 떨어진 작은 점(워터마크 글씨·모눈 얼룩)은 지운다 — 가장 큰 덩어리의 3% 보다 작은 덩어리
    alpha = out.load()
    comp, sizes = {}, []
    for y in range(H):
        for x in range(W):
            if alpha[x, y][3] and (x, y) not in comp:
                q, members = deque([(x, y)]), []
                comp[(x, y)] = len(sizes)
                while q:
                    cx, cy = q.popleft()
                    members.append((cx, cy))
                    for nx in (cx - 1, cx, cx + 1):
                        for ny in (cy - 1, cy, cy + 1):
                            if 0 <= nx < W and 0 <= ny < H and alpha[nx, ny][3] and (nx, ny) not in comp:
                                comp[(nx, ny)] = len(sizes)
                                q.append((nx, ny))
                sizes.append(members)
    if not sizes:
        raise ValueError("그림에서 캐릭터를 못 찾았어요")
    big = max(len(m) for m in sizes)
    for members in sizes:
        if len(members) < 0.03 * big:
            for xy in members:
                out.putpixel(xy, (0, 0, 0, 0))
    return out.crop(out.getbbox())


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(**kw):
    st = load_state()
    st.update(kw)
    BASE.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st), encoding="utf-8")


class Widget:
    def __init__(self):
        st = load_state()
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        # 기본은 «항상 위» 가 아니다 — PPT·크롬 같은 창을 띄우면 그 아래로 가려지고, 바탕화면이 보일 때만 보인다.
        # 오른쪽 클릭 «항상 위에 띄우기» 를 켜면 늘 위에 뜬다 (hiedu_widget_state.json 에 기억)
        self.topmost = st.get("topmost", False)
        self.root.attributes("-topmost", self.topmost)
        self.root.configure(bg=KEY)
        self.root.attributes("-transparentcolor", KEY)     # 캐릭터만 보이고 바탕은 비친다
        self.root.geometry("+%d+%d" % (st.get("x", self.root.winfo_screenwidth() - 160), st.get("y", 60)))
        self.busy = None
        self.lock = threading.Lock()
        self.table = None
        self.data_at = 0
        self.away = 0

        self.pic = tk.Label(self.root, bd=0, cursor="hand2")
        self.load_art()
        self.pic.pack(anchor="w")
        self.pic.bind("<ButtonPress-1>", self.press)
        self.pic.bind("<B1-Motion>", self.drag)
        self.pic.bind("<ButtonRelease-1>", self.release)
        self.pic.bind("<Button-3>", lambda e: self.m.tk_popup(e.x_root, e.y_root))

        # 마우스를 대면 옆에 뜨는 단추 막대
        self.pop = tk.Toplevel(self.root)
        self.pop.overrideredirect(True)
        self.pop.attributes("-topmost", True)
        self.pop.withdraw()
        fr = tk.Frame(self.pop, bg=BG, highlightbackground=LINE, highlightthickness=1)
        fr.pack()
        row = tk.Frame(fr, bg=BG)
        row.pack()
        for text, cmd, color in BTNS:
            b = tk.Label(row, text=text, bg=BG, fg=color, font=("Malgun Gothic", 10, "bold"), padx=9, pady=6, cursor="hand2")
            b.pack(side="left")
            b.bind("<Button-1>", lambda e, c=cmd, t=text: self.toggle_table() if c == "data" else self.click(c, t))
            b.bind("<Enter>", lambda e, w=b: w.configure(bg="#f3e9da"))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=BG))
        self.tip = tk.Toplevel(self.root)      # 안내 글씨 — 따로 떠서 화면 남는 쪽에 붙는다 (place_tip)
        self.tip.overrideredirect(True)
        self.tip.attributes("-topmost", True)
        self.tip.withdraw()
        self.status = tk.Label(self.tip, text="", bg=BG, fg="#8a7a68", font=("Malgun Gothic", 9), padx=6, pady=2,
                               highlightbackground=LINE, highlightthickness=1)
        self.status.pack()

        self.m = tk.Menu(self.root, tearoff=0, font=("Malgun Gothic", 9))
        self.m.add_command(label="상벌점 설정 (아이디·인증서·학년반)", command=self.open_setup)
        self.top_var = tk.BooleanVar(value=self.topmost)
        self.m.add_checkbutton(label="항상 위에 띄우기", variable=self.top_var, command=self.toggle_topmost)
        self.m.add_command(label="캐릭터 그림 바꾸기…", command=self.pick_art)
        self.m.add_command(label="캐릭터 그림 지우기 (글자로)", command=lambda: self.set_art(None))
        self.m.add_command(label="상벌점 크롬 닫기", command=lambda: threading.Thread(target=self.run, args=("close",), daemon=True).start())
        self.m.add_separator()
        self.m.add_command(label="위젯 끄기", command=self.root.destroy)

    # ── 캐릭터 그림 (widget\\상벌점_그림.png) ──
    def load_art(self):
        self.art = None
        art = next(iter(sorted(HERE.glob("상벌점_그림.*"))), None)
        if art:
            try:
                from PIL import Image, ImageTk
                im = Image.open(art).convert("RGBA")
                w = max(1, round(im.width * ART_H / im.height))
                if im.height <= 128:    # 픽셀 그림 — 정수 배로 각지게 키운 뒤 줄여야 칸이 고르다 (1.5배 같은 크기)
                    k = -(-ART_H // im.height)
                    im = im.resize((im.width * k, im.height * k), Image.NEAREST)
                im = im.resize((w, ART_H), Image.LANCZOS)
                im.putalpha(im.getchannel("A").point(lambda a: 255 if a >= 128 else 0))   # 반투명 테두리는 분홍(KEY)이 비친다 → 0/255 로
                self.art = ImageTk.PhotoImage(im)
            except Exception:
                pass
        if self.art:
            self.pic.configure(image=self.art, text="", bg=KEY, padx=0, pady=0)
        else:
            self.pic.configure(image="", text="상벌점", bg=BG, fg="#b07a00", font=("Malgun Gothic", 10, "bold"), padx=8, pady=6)

    def pick_art(self):
        from tkinter import filedialog
        f = filedialog.askopenfilename(parent=self.root, title="캐릭터 그림 고르기",
                                       filetypes=[("그림", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"), ("모든 파일", "*.*")])
        if f:
            self.set_art(f)

    def set_art(self, src):
        """고른 그림을 바탕 투명한 캐릭터로 만들어 widget\\상벌점_그림.png 로 저장하고 바로 바꿔 끼운다 (None = 글자로)."""
        x, y = self.pic.winfo_rootx(), self.pic.winfo_rooty()
        try:
            sprite = make_sprite(src) if src else None
        except Exception as e:
            self.say("앗, 그림을 못 바꿨어요: " + str(e)[:40], "#c0392b", 8000)
            return
        for old in HERE.glob("상벌점_그림.*"):
            old.unlink()
        if sprite:
            sprite.save(HERE / "상벌점_그림.png")
        self.load_art()
        self.relayout(x, y)
        self.say("캐릭터를 바꿨어요" if sprite else "글자로 바꿨어요", "#2f7d4f")

    # ── 끌기 (조금만 움직였으면 클릭 = 우리 반 표 펴기/접기) ──
    def press(self, e):
        self.sx, self.sy = e.x_root, e.y_root
        self.wx, self.wy = self.root.winfo_x(), self.root.winfo_y()

    def drag(self, e):
        self.root.geometry("+%d+%d" % (self.wx + e.x_root - self.sx, self.wy + e.y_root - self.sy))
        self.place_pop()
        self.place_tip()

    def release(self, e):
        if abs(e.x_root - self.sx) + abs(e.y_root - self.sy) < 5:
            self.toggle_table()
            return
        save_state(x=self.pic.winfo_rootx(), y=self.pic.winfo_rooty())   # 캐릭터 자리 (표가 위·왼쪽으로 펴져 있어도)

    def toggle_topmost(self):
        self.topmost = bool(self.top_var.get())
        self.root.attributes("-topmost", self.topmost)
        save_state(topmost=self.topmost)
        self.say("늘 위에 떠요" if self.topmost else "다른 창 아래로 가려져요")

    # ── 단추 막대 보이기·숨기기 ──
    def place_pop(self):
        self.pop.update_idletasks()
        px, py, pw, ph = self.pic.winfo_rootx(), self.pic.winfo_rooty(), self.pic.winfo_width(), self.pic.winfo_height()
        w, h = self.pop.winfo_reqwidth(), self.pop.winfo_reqheight()
        x = px + pw + 2 if px + pw + 2 + w <= self.root.winfo_screenwidth() else px - w - 2
        self.pop.geometry("+%d+%d" % (x, py + max(0, (ph - h) // 2)))

    def mine_at(self, mx, my):
        """마우스 밑에 실제로 보이는 창이 이 위젯인가 — 다른 창에 가려진 캐릭터 자리를 지나가도 단추가 뜨지 않게."""
        from ctypes import wintypes
        u = ctypes.windll.user32
        u.WindowFromPoint.argtypes, u.WindowFromPoint.restype = [wintypes.POINT], ctypes.c_void_p
        u.GetAncestor.argtypes, u.GetAncestor.restype = [ctypes.c_void_p, ctypes.c_uint], ctypes.c_void_p
        top = u.GetAncestor(u.WindowFromPoint(wintypes.POINT(mx, my)), 2)
        return top in (u.GetAncestor(self.root.winfo_id(), 2), u.GetAncestor(self.pop.winfo_id(), 2))

    def hover(self):
        mx, my = self.root.winfo_pointerxy()

        def inside(w):
            return w.winfo_viewable() and w.winfo_rootx() <= mx < w.winfo_rootx() + w.winfo_width()                 and w.winfo_rooty() <= my < w.winfo_rooty() + w.winfo_height()
        want = (inside(self.pic) or inside(self.pop)) and self.mine_at(mx, my)
        self.away = 0 if want else self.away + 1
        if want and not self.pop.winfo_viewable():
            self.place_pop()
            self.pop.deiconify()
        elif self.away >= 2 and self.pop.winfo_viewable():     # 마우스를 떼면 곧 숨긴다 (맹구↔막대 사이를 건널 틈만 0.2초)
            self.pop.withdraw()
        self.root.after(200, self.hover)

    # ── 말풍선 ──
    def show_status(self, text, color):
        self.status.configure(text=text, fg=color)
        if text:
            self.tip.deiconify()
            self.place_tip()
        else:
            self.tip.withdraw()
        if self.pop.winfo_viewable():
            self.place_pop()

    def say(self, text, color=INK, ms=4000):
        self.show_status(text, color)
        self.root.after(ms, lambda: self.show_status("", color) if self.status.cget("text") == text else None)

    def tick(self):
        if self.busy:
            self.show_status(self.busy + "." * (int(time.time() * 2) % 3 + 1), "#8a7a68")
        self.root.after(400, self.tick)

    # ── 엔진 ──
    def run(self, cmd):
        last, self.data = "", None
        with self.lock:
            p = subprocess.Popen([str(PY), "-X", "utf8", str(ENGINE), cmd], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                 env=ENV, cwd=str(HERE), creationflags=NO_WINDOW)
            try:
                ctypes.windll.user32.AllowSetForegroundWindow(p.pid)   # 크롬 창을 맨 앞에 꺼낼 권한을 넘긴다
            except Exception:
                pass
            for line in p.stdout:
                line = line.strip()
                if line.startswith("STEP ") and self.busy:
                    self.busy = line[5:].split("  (")[0]
                elif line.startswith("DATA "):
                    self.data = json.loads(line[5:])
                elif line.startswith(("READY", "FAIL", "CLOSED")):
                    last = line
            p.wait()
        return last

    def click(self, cmd, text):
        if self.busy:
            return
        self.busy = text + (" 읽는 중" if cmd == "data" else " 여는 중")

        def fn():
            try:
                last = self.run(cmd)
            finally:
                self.busy = None
            if last.startswith("READY") and cmd == "data" and self.data:
                self.root.after(0, self.show_table, self.data)
                self.root.after(0, self.show_status, "", INK)     # «읽는 중…» 마지막 단계 글씨가 남지 않게
            elif last.startswith("READY"):
                self.root.after(0, self.say, "짠! 열렸어요", "#2f7d4f")
            else:
                self.root.after(0, self.say, "앗, 실패: " + (last[5:] or "알 수 없는 오류"), "#c0392b", 10000)
        threading.Thread(target=fn, daemon=True).start()

    # ── 우리 반 표 (위젯 아래로 펼친다) ──
    def toggle_table(self):
        if self.table and self.table.winfo_ismapped():
            self.close_table()
        elif self.data_at and time.time() - self.data_at < 10 * 60:   # 10분 안에 읽은 건 바로 다시 편다
            self.open_table()
        else:
            self.click("data", "우리반")

    def show_table(self, d):
        self.data_at = time.time()
        if self.table:
            self.table.destroy()
        t = self.table = tk.Frame(self.root, bg=BG, highlightbackground=LINE, highlightthickness=1)
        tk.Label(t, text="%s학년 %s반 · %s ~ %s · %s 읽음" % (d["grade"], d["class"], d["from"][5:].replace("-", "/"),
                 d["to"][5:].replace("-", "/"), datetime.now().strftime("%H:%M")),
                 bg=BG, fg=INK, font=("Malgun Gothic", 9, "bold")).pack(padx=8, pady=(6, 4), anchor="w")
        cols = ("번호", "이름", "상점", "벌점", "상쇄점", "이월", "누계")
        st = ttk.Style(t)
        st.configure("H.Treeview", font=("Malgun Gothic", 9), rowheight=20)
        st.configure("H.Treeview.Heading", font=("Malgun Gothic", 9, "bold"))
        box = tk.Frame(t, bg=BG)
        box.pack(padx=8)
        tv = ttk.Treeview(box, columns=cols, show="headings", height=min(len(d["rows"]), 15), style="H.Treeview")
        for c, w in zip(cols, (40, 70, 44, 44, 50, 40, 46)):
            tv.heading(c, text=c)
            tv.column(c, width=w, anchor="w" if c == "이름" else "center")
        tv.tag_configure("minus", foreground="#c0392b")
        for r in d["rows"]:
            try:
                minus = float(r[-1]) < 0
            except ValueError:
                minus = False
            tv.insert("", "end", values=r, tags=("minus",) if minus else ())
        tv.pack(side="left")
        if len(d["rows"]) > 15:
            sb = ttk.Scrollbar(box, orient="vertical", command=tv.yview)
            tv.configure(yscrollcommand=sb.set)
            sb.pack(side="left", fill="y")
        bar = tk.Frame(t, bg=BG)
        bar.pack(pady=6)
        for text, fn in (("새로고침", lambda: self.click("data", "우리반")),
                         ("사이트에서 보기", lambda: self.click("class", "우리반")), ("접기", self.close_table)):
            tk.Button(bar, text=text, font=("Malgun Gothic", 9), command=fn, padx=6).pack(side="left", padx=3)
        self.open_table()

    def open_table(self):
        """아래로 펴면 화면 밑(작업 표시줄)에 걸리면 위로 편다. 좌우는 relayout 이 정한다."""
        x, y = self.pic.winfo_rootx(), self.pic.winfo_rooty()
        self.table.update_idletasks()
        if y + self.pic.winfo_height() + self.table.winfo_reqheight() <= self.root.winfo_screenheight() - 48:
            self.table.pack(fill="x", after=self.pic)
        else:
            self.table.pack(fill="x", before=self.pic)
        self.relayout(x, y)

    def close_table(self):
        x, y = self.pic.winfo_rootx(), self.pic.winfo_rooty()
        self.table.pack_forget()
        self.relayout(x, y)

    def place_tip(self):
        """안내 글씨: 맹구 아래 → 위 → 옆 중 화면 안에 들어가고 표와 안 겹치는 첫 자리. 좌우는 화면 안쪽으로 뻗게."""
        if not self.tip.winfo_viewable():
            return
        self.tip.update_idletasks()
        px, py, pw, ph = self.pic.winfo_rootx(), self.pic.winfo_rooty(), self.pic.winfo_width(), self.pic.winfo_height()
        w, h = self.tip.winfo_reqwidth(), self.tip.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight() - 48
        x = px if px + w <= sw - 8 else max(0, px + pw - w)
        side = px + pw + 2 if px + pw + 2 + w <= sw - 8 else max(0, px - w - 2)
        table_up = self.table is not None and self.table.winfo_ismapped() and self.table.winfo_rooty() < py
        table_down = self.table is not None and self.table.winfo_ismapped() and not table_up
        spots = [(x, py + ph + 2, not table_down and py + ph + 2 + h <= sh),      # 아래
                 (x, py - h - 2, not table_up and py - h - 2 >= 0),                # 위
                 (side, py + max(0, (ph - h) // 2), True)]                         # 옆 (표는 위·아래로만 펴진다)
        sx, sy, _ = next(sp for sp in spots if sp[2])
        self.tip.geometry("+%d+%d" % (sx, sy))

    def relayout(self, x, y):
        """표가 펴지거나 접힐 때마다 — 캐릭터는 (x, y) 제자리에 두고, 오른쪽이 모자라면 표를 왼쪽으로 편다."""
        self.root.update_idletasks()
        w = self.root.winfo_reqwidth()
        right = x + w > self.root.winfo_screenwidth() - 8
        self.pic.pack_configure(anchor="e" if right else "w")
        up = self.table is not None and self.table.winfo_ismapped() and self.table.winfo_y() < self.pic.winfo_y()
        rx = x + self.pic.winfo_width() - w if right else x
        ry = y - self.table.winfo_reqheight() if up else y
        self.root.geometry("+%d+%d" % (rx, ry))
        self.root.update_idletasks()
        self.place_tip()

    def open_setup(self):
        subprocess.Popen([str(PY.with_name("pythonw.exe")), "-X", "utf8", str(ENGINE), "setup"], cwd=str(HERE), env=ENV)

    def first_run(self):
        """설정(아이디·암호·인증서·학년반)이 하나라도 비었으면 설정 창부터 띄운다."""
        def fn():
            if self.run("ready").startswith("FAIL"):
                self.root.after(0, self.open_setup)
        threading.Thread(target=fn, daemon=True).start()

    def mainloop(self):
        self.root.after(500, self.first_run)
        self.tick()
        self.hover()
        self.root.mainloop()


def breakaway():
    """클로드가 띄우면 «잡(job)»에 묶여 클로드와 같이 죽는다 — 잡 밖으로 다시 띄운다 (바로가기위젯.pyw 와 같은 이유)."""
    if "--unjobbed" in sys.argv:
        return False
    try:
        k = ctypes.windll.kernel32
        injob = ctypes.c_int(0)
        if not k.IsProcessInJob(k.GetCurrentProcess(), None, ctypes.byref(injob)) or not injob.value:
            return False
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--unjobbed"], cwd=str(HERE),
                         creationflags=0x01000000 | 0x00000008 | 0x00000200, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    if breakaway():
        sys.exit(0)
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "hiedu-widget")
    if ctypes.windll.kernel32.GetLastError() == 183:      # 이미 떠 있다
        sys.exit(0)
    Widget().mainloop()
