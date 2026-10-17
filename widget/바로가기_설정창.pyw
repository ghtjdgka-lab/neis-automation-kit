# -*- coding: utf-8 -*-
"""바로가기 위젯 — 설정 «창» (검은 창 없이 마우스로).

  .\\.venv\\Scripts\\pythonw.exe widget\\바로가기_설정창.pyw

클로드 없이 설치하는 선생님용(설치_바로가기위젯.cmd 가 마지막에 띄운다)이고, 위젯 오른쪽 클릭 «인증서 설정»도 이 창을 연다.
묻는 것은 검은 창(바로가기_설정.py)과 같다 — 지역 · 인증서 이름 · 암호 · 출근·퇴근 시각 · 연락처.
지역은 17개 시도 목록에서 고른다(오타가 날 수 없게). 저장은 바로가기_설정.save_settings() 그대로.
"""
import os
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import keyring  # noqa: E402
import teacher_config  # noqa: E402
from setup_wizard import REGION_CODES, gpki_names  # noqa: E402
import 바로가기_설정 as S  # noqa: E402

INK, SUB, RED, GREEN = "#1f2937", "#6b7280", "#c0392b", "#15803d"
FONT = ("맑은 고딕", 11)


def current_region(old):
    if old.get("region") in REGION_CODES:
        return old["region"]
    for name, code in REGION_CODES.items():
        if "//%s.neis" % code in (old.get("neis_url") or ""):
            return name
    return "서울"


def main():
    old = S.load_old()
    names = gpki_names()

    root = tk.Tk()
    root.title("나이스·에듀파인 바로가기 — 설정")
    root.configure(bg="white")
    root.resizable(False, False)
    pad = {"padx": 18, "pady": 5}

    tk.Label(root, text="처음 한 번만 넣으면 됩니다", font=("맑은 고딕", 14, "bold"), fg=INK, bg="white").grid(
        row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(16, 2))
    tk.Label(root, text="인증서 암호는 이 컴퓨터의 «Windows 자격 증명 관리자»에만 저장되고, 파일에는 남지 않아요.",
             font=("맑은 고딕", 9), fg=SUB, bg="white").grid(row=1, column=0, columnspan=2, sticky="w", padx=18, pady=(0, 10))

    def label(r, text, hint=""):
        tk.Label(root, text=text, font=FONT, fg=INK, bg="white").grid(row=r, column=0, sticky="w", **pad)
        if hint:
            tk.Label(root, text=hint, font=("맑은 고딕", 9), fg=SUB, bg="white").grid(
                row=r + 1, column=1, sticky="w", padx=18, pady=(0, 4))

    r = 2
    label(r, "① 지역 (교육청)", "나이스에 접속하는 교육청이에요")
    region = ttk.Combobox(root, values=list(REGION_CODES), state="readonly", width=24, font=FONT)
    region.set(current_region(old))
    region.grid(row=r, column=1, sticky="w", **pad)

    r += 2
    label(r, "② 인증서 이름",
          "이 컴퓨터에서 찾은 인증서예요" if names else "⚠ 이 컴퓨터에서 교육행정 인증서를 못 찾았어요 (C:\\GPKI)")
    cert = ttk.Combobox(root, values=names, width=24, font=FONT)
    cert.set(old.get("cert_name") or (names[0] if names else ""))
    cert.grid(row=r, column=1, sticky="w", **pad)

    r += 2
    saved_pw = bool(old.get("cert_name") and keyring.get_password(teacher_config.KEYRING_SERVICE, old["cert_name"]))
    label(r, "③ 인증서 암호", "이미 저장돼 있어요 — 바꿀 때만 넣으세요" if saved_pw else "나이스 로그인할 때 넣는 그 암호")
    pw = tk.Entry(root, show="●", width=26, font=FONT, relief="solid", bd=1)
    pw.grid(row=r, column=1, sticky="w", **pad)

    r += 2
    label(r, "④ 출근 시각", "지각 신청할 때 시작 시각 기본값 (학교마다 달라요)")
    ws = tk.Entry(root, width=10, font=FONT, relief="solid", bd=1)
    ws.insert(0, old.get("work_start", "08:40"))
    ws.grid(row=r, column=1, sticky="w", **pad)

    r += 2
    label(r, "⑤ 퇴근 시각", "조퇴 신청할 때 끝 시각 기본값")
    we = tk.Entry(root, width=10, font=FONT, relief="solid", bd=1)
    we.insert(0, old.get("work_end", "16:20"))
    we.grid(row=r, column=1, sticky="w", **pad)

    r += 2
    label(r, "⑥ 연락처 (선택)", "복무 신청서에 적히는 번호. 비워 둬도 돼요")
    phone = tk.Entry(root, width=20, font=FONT, relief="solid", bd=1)
    phone.insert(0, old.get("contact", ""))
    phone.grid(row=r, column=1, sticky="w", **pad)

    r += 2
    msg = tk.Label(root, text="", font=FONT, fg=RED, bg="white", wraplength=460, justify="left")
    msg.grid(row=r, column=0, columnspan=2, sticky="w", padx=18, pady=(8, 0))

    def save():
        name = cert.get().strip()
        p = pw.get()
        t1, t2 = ws.get().strip(), we.get().strip()
        if not name:
            return msg.config(text="② 인증서 이름을 넣어 주세요. 나이스 로그인 창에 뜨는 이름이에요.", fg=RED)
        if not p and not (saved_pw and name == old.get("cert_name")):
            return msg.config(text="③ 인증서 암호를 넣어 주세요.", fg=RED)
        for v, what in ((t1, "④ 출근 시각"), (t2, "⑤ 퇴근 시각")):
            if not re.fullmatch(r"\d{1,2}:\d{2}", v):
                return msg.config(text="%s은 08:40 처럼 적어 주세요." % what, fg=RED)
        url = "https://%s.neis.go.kr/jsp/main.jsp" % REGION_CODES[region.get()]
        try:
            S.save_settings(url, name, p, t1, t2, phone.get().strip())
            S.make_shortcuts()
        except Exception as e:
            return msg.config(text="저장하지 못했어요: %s" % str(e)[:120], fg=RED)
        msg.config(text="✅ 저장했어요. 바탕화면에 «나이스 에듀파인 바로가기»가 생겼고, 위젯을 띄웁니다.\n"
                        "처음 한 번은 로그인하느라 20~30초 걸리고, 그다음부터는 누르면 1~2초예요.", fg=GREEN)
        pyw = Path(sys.executable).with_name("pythonw.exe")
        subprocess.Popen([str(pyw), str(HERE / "바로가기위젯.pyw")], cwd=str(HERE), close_fds=True)
        btn.config(text="닫기", command=root.destroy)

    btn = tk.Button(root, text="저장하고 위젯 켜기", font=("맑은 고딕", 12, "bold"), fg="white", bg="#2563eb",
                    activebackground="#1d4ed8", activeforeground="white", relief="flat", padx=16, pady=6, command=save)
    btn.grid(row=r + 1, column=0, columnspan=2, pady=(10, 18))
    root.bind("<Return>", lambda e: btn.invoke())

    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    root.geometry("+%d+%d" % ((root.winfo_screenwidth() - w) // 2, (root.winfo_screenheight() - h) // 3))
    root.lift()
    root.attributes("-topmost", True)
    root.after(500, lambda: root.attributes("-topmost", False))
    (pw if not saved_pw else region).focus_set()
    root.mainloop()


if __name__ == "__main__":
    os.chdir(HERE)
    main()
