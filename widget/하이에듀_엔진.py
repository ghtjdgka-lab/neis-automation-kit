# -*- coding: utf-8 -*-
"""상벌점 위젯(하이에듀) 엔진 — 하이에듀(hiedu.kr)에 아이디·비밀번호 → 교육행정 인증서까지 자동 로그인.

  python 하이에듀_엔진.py open      하이에듀 첫 화면 (상벌점 전용 크롬, 포트 9326)
  python 하이에듀_엔진.py class     우리 반 상벌점 현황을 크롬으로 (자료조회 및 통계 → 학생별 누계자료, 학년·반만)
  python 하이에듀_엔진.py data      같은 현황을 «안 보이는 크롬»(headless)으로 읽어 DATA <json> 한 줄로 (위젯 안의 표용)
  python 하이에듀_엔진.py check     안 보이는 크롬으로 로그인만 시험
  python 하이에듀_엔진.py ready     설정이 다 있나만 확인
  python 하이에듀_엔진.py setup     설정 창 — 하이에듀 아이디·비밀번호, 인증서·인증서 암호, 학년·반 (전부 자격 증명 관리자)
  python 하이에듀_엔진.py close     상벌점 크롬 닫기

  출력은 STEP <하는 일> / DATA <json> / READY / FAIL <이유> 줄 — 위젯이 이 줄만 읽는다.
  크롬 띄우기·붙기·창 꺼내기는 바로가기_엔진.py 의 것을 그대로 쓴다. 학생 점수는 파일로 남기지 않는다.
"""
import json
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import 바로가기_엔진 as B  # noqa: E402  (키트 경로·teacher_config 도 여기서 잡힌다)
from 바로가기_엔진 import (BASE, COMMON_ARGS, SITES, chrome_exe, close_cmd, connect_sync, ensure_chrome,  # noqa: E402
                      goto, step, teacher_config, to_front_sync, watchdog)

SITES["hiedu"] = {"port": int(B.os.environ.get("WIDGET_HIEDU_PORT", "9326")), "profile": BASE / "chrome_profile_widget_hiedu",
                  "match": ("hiedu",)}


HIEDU = "https://www.hiedu.kr/"
HIEDU_KEYRING = "neis-automation-hiedu"


def hiedu_conf():
    """상벌점 위젯 설정은 전부 자격 증명 관리자(neis-automation-hiedu)에 둔다 — 파일·로그·화면에는 안 남긴다.
    비어 있는 인증서·학년·반은 나이스 위젯 설정(teacher_config + 'neis-automation' 암호)에서 빌려 온다."""
    import keyring
    c = {k: keyring.get_password(HIEDU_KEYRING, k) or "" for k in ("id", "pw", "cert_name", "cert_pw", "grade", "class")}
    try:
        tc = json.loads(teacher_config.CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        tc = {}
    for k in ("grade", "class", "cert_name"):
        c[k] = c[k] or str(tc.get(k) or "")
    if c["cert_name"] and not c["cert_pw"]:
        c["cert_pw"] = keyring.get_password(teacher_config.KEYRING_SERVICE, c["cert_name"]) or ""
    return c


def hiedu_missing():
    names = {"id": "하이에듀 아이디", "pw": "하이에듀 비밀번호", "cert_name": "인증서", "cert_pw": "인증서 암호", "grade": "학년", "class": "반"}
    c = hiedu_conf()
    return [v for k, v in names.items() if not c[k]]


def hiedu_setup():
    """처음 켤 때(또는 오른쪽 클릭 «상벌점 설정») 뜨는 창 — 하이에듀 아이디·비밀번호, 인증서·인증서 암호, 학년·반.
    암호 칸은 «*» 로 가리고, 저장된 암호는 다시 채워 보여 주지 않는다(비우면 그대로 둔다). 저장하면 안 보이는 크롬으로 로그인을 시험한다."""
    import re
    import keyring
    import tkinter as tk
    from tkinter import ttk
    from setup_wizard import gpki_names
    c = hiedu_conf()
    try:
        neis_cert = json.loads(teacher_config.CONFIG_FILE.read_text(encoding="utf-8")).get("cert_name") or ""
    except Exception:
        neis_cert = ""
    root = tk.Tk()
    root.title("상벌점 위젯 설정")
    root.attributes("-topmost", True)
    root.resizable(False, False)
    f, fs = ("Malgun Gothic", 10), ("Malgun Gothic", 9)
    rows = []

    def field(label, widget, hint=""):
        r = len(rows)
        tk.Label(root, text=label, font=f).grid(row=r, column=0, padx=(14, 8), pady=4, sticky="e")
        widget.grid(row=r, column=1, padx=(0, 8), pady=4, sticky="w")
        if hint:
            tk.Label(root, text=hint, font=fs, fg="#6b7280").grid(row=r, column=2, padx=(0, 14), sticky="w")
        rows.append(widget)
        return widget

    uid = field("하이에듀 아이디", tk.Entry(root, font=f, width=22))
    uid.insert(0, keyring.get_password(HIEDU_KEYRING, "id") or "")
    has_pw = bool(keyring.get_password(HIEDU_KEYRING, "pw"))
    pw = field("하이에듀 비밀번호", tk.Entry(root, font=f, width=22, show="*"), "저장돼 있음 — 바꿀 때만" if has_pw else "")
    names = gpki_names()
    cert = field("인증서", ttk.Combobox(root, font=f, width=20, values=names),
                 "이 컴퓨터에서 찾은 인증서" if names else "⚠ C:\\GPKI 에서 인증서를 못 찾았어요")
    cert.set(c["cert_name"] or (names[0] if len(names) == 1 else ""))
    has_cpw = bool(keyring.get_password(HIEDU_KEYRING, "cert_pw"))
    cpw = field("인증서 암호", tk.Entry(root, font=f, width=22, show="*"),
                "저장돼 있음 — 바꿀 때만" if has_cpw else ("비우면 나이스 위젯 암호를 씀" if c["cert_pw"] else ""))
    grade = field("학년", tk.Entry(root, font=f, width=6))
    grade.insert(0, c["grade"])
    klass = field("반", tk.Entry(root, font=f, width=6))
    klass.insert(0, c["class"])
    btn = tk.Button(root, text="저장하고 로그인 확인", font=f, padx=10)
    btn.grid(row=len(rows), column=0, columnspan=3, pady=(10, 2))
    msg = tk.Label(root, text="암호는 윈도우 «자격 증명 관리자»에만 저장돼요 (파일에 안 남아요)", font=fs, fg="#6b7280")
    msg.grid(row=len(rows) + 1, column=0, columnspan=3, padx=14, pady=(2, 12))

    def say(text, color):
        msg.config(text=text, fg=color)

    def save(_=None):
        g, k = re.sub(r"\D", "", grade.get()), re.sub(r"\D", "", klass.get())
        name = cert.get().strip()
        neis_pw = name == neis_cert and keyring.get_password(teacher_config.KEYRING_SERVICE, name)
        if not uid.get().strip() or not (pw.get() or has_pw) or not name or not (cpw.get() or has_cpw or neis_pw) or not g or not k:
            return say("빈 칸을 채워 주세요 (암호는 저장돼 있으면 비워도 돼요)", "#c0392b")
        keyring.set_password(HIEDU_KEYRING, "id", uid.get().strip())
        if pw.get():
            keyring.set_password(HIEDU_KEYRING, "pw", pw.get())
        keyring.set_password(HIEDU_KEYRING, "cert_name", name)
        if cpw.get():
            keyring.set_password(HIEDU_KEYRING, "cert_pw", cpw.get())
        keyring.set_password(HIEDU_KEYRING, "grade", g)
        keyring.set_password(HIEDU_KEYRING, "class", k)
        pw.delete(0, "end")             # 화면에 암호를 남겨 두지 않는다
        cpw.delete(0, "end")
        btn.config(state="disabled")
        say("저장했어요. 하이에듀 로그인 확인 중… (10초쯤)", "#6b7280")

        def check():
            r = subprocess.run([str(Path(sys.executable).with_name("python.exe")), "-X", "utf8", str(Path(__file__).resolve()), "check"],
                               capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
            last = next((ln for ln in reversed(r.stdout.splitlines()) if ln.startswith(("READY", "FAIL"))), "FAIL 알 수 없는 오류")
            if last.startswith("READY"):
                root.after(0, say, "✅ 로그인 확인됨 — 창을 닫을게요", "#15803d")
                root.after(1500, root.destroy)
            else:
                root.after(0, say, "❌ " + last[5:] + " — 고쳐서 다시 저장해 주세요", "#c0392b")
                root.after(0, lambda: btn.config(state="normal"))
        threading.Thread(target=check, daemon=True).start()

    btn.config(command=save)
    root.bind("<Return>", save)
    (pw if uid.get() and not has_pw else uid).focus_force()
    root.mainloop()


def hiedu_cmd(cmd):
    from playwright.sync_api import sync_playwright
    if cmd == "ready":      # 위젯이 처음 뜰 때 — 설정이 다 있나
        miss = hiedu_missing()
        print("FAIL 설정 필요: " + ", ".join(miss) if miss else "READY", flush=True)
        return
    if cmd in ("data", "check"):    # 화면에 아무것도 안 띄운다 — 따로 된 프로필의 headless 크롬으로 로그인~읽기 (약 9초, 10/23 실측)
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(BASE / "chrome_profile_widget_hiedu_data"), executable_path=chrome_exe(),
                                                       headless=True, args=COMMON_ARGS)
            try:
                ctx.grant_permissions(["local-network-access"], origin="https://www.hiedu.kr")
                hiedu_open(ctx, cmd)
            finally:
                ctx.close()
        return
    ensure_chrome("hiedu")
    with sync_playwright() as p:
        ctx = connect_sync(p, SITES["hiedu"]["port"]).contexts[0]
        try:    # 인증서 창이 127.0.0.1 보안프로그램에 닿게 «이 기기의 다른 앱» 허용을 미리 (edufine_common.grant_local_network 와 같은 이유)
            ctx.grant_permissions(["local-network-access"], origin="https://www.hiedu.kr")
        except Exception:
            pass
        hiedu_open(ctx, cmd)


def hiedu_goto(page, url):
    """«비밀번호를 주기적으로 변경하세요»(view.do?no=80) 가 가로채면 [다음에변경] 을 누르고 다시 간다 (10/23 실측 — 6개월마다 뜬다)."""
    goto(page, url, wait_until="domcontentloaded")
    later = page.get_by_text("다음에변경", exact=True)
    if "no=80" in page.url and later.count():
        step("비밀번호 변경 안내 — 다음에변경")
        later.first.click()
        page.wait_for_url(lambda u: "no=80" not in u, timeout=15_000)   # 누른 뒤 저절로 넘어가는 중에 goto 하면 ERR_ABORTED
        page.wait_for_load_state("domcontentloaded")
        goto(page, url, wait_until="domcontentloaded")


def hiedu_class(page, data=False):
    """자료조회 및 통계 → 학생별 누계자료 → 표(jqxGrid #grid-inquiry)를 설정의 학년·반으로 거른다.
    표는 전교생을 한 번에 싣고(학년 category1 · 반 category2, 둘 다 «2» 같은 숫자 문자열), 기간은 3/1~오늘이 기본 (10/23 실측)."""
    import re
    c = hiedu_conf()
    grade, klass = (re.sub(r"\D", "", c[k]) for k in ("grade", "class"))
    if not grade or not klass:
        raise RuntimeError("학년·반이 없어요 — 오른쪽 클릭 → «상벌점 설정»")
    step("우리 반 여는 중")
    hiedu_goto(page, HIEDU + "view.do?no=65")
    page.get_by_text("학생별 누계자료", exact=True).first.click()
    page.wait_for_function("""() => { try { return $('#grid-inquiry').jqxGrid('getrows').length > 0 } catch (e) { return false } }""",
                           timeout=20_000)     # 표가 아직 안 만들어졌을 땐 getrows 가 undefined — 오류 말고 «아직»으로
    if data:
        rows = page.evaluate("""([g, c]) => $('#grid-inquiry').jqxGrid('getrows')
            .filter(r => String(r.category1) == g && String(r.category2) == c)
            .map(r => [String(r.category3), String(r.name), ...['bpoint', 'rpoint', 'gpoint', 'kpoint', 'accumulate'].map(k => String(r[k] ?? ''))])""",
                             [grade, klass])
        rows.sort(key=lambda r: int(r[0]) if r[0].isdigit() else 999)
        step("%s학년 %s반 %s명 읽음" % (grade, klass, len(rows)))
        print("DATA " + json.dumps({"grade": grade, "class": klass, "from": page.input_value("#symd1"),
                                    "to": page.input_value("#symd2"), "rows": rows}, ensure_ascii=False), flush=True)
        return
    n = page.evaluate("""([g, c]) => { const grid = $('#grid-inquiry');
        for (const [f, v] of [['category1', g], ['category2', c]]) {
            const fg = new $.jqx.filter();
            fg.addfilter(1, fg.createfilter('stringfilter', v, 'EQUAL'));
            grid.jqxGrid('addfilter', f, fg);
        }
        grid.jqxGrid('applyfilters');
        return grid.jqxGrid('getdatainformation').rowscount; }""", [grade, klass])
    step("%s학년 %s반 %s명" % (grade, klass, n))


def hiedu_open(ctx, cmd="open"):
    quiet = cmd in ("data", "check")    # 표만 읽거나 로그인만 시험 — 보고 있는 탭은 안 건드리고 새 탭에서 하고 닫는다, 창도 안 꺼낸다
    if quiet:
        page = ctx.new_page()
    else:
        page = next((pg for pg in ctx.pages if "hiedu.kr" in pg.url), None) or (ctx.pages[0] if ctx.pages else ctx.new_page())
    page.set_default_timeout(30_000)
    msgs = []
    page.on("dialog", lambda d: (msgs.append(d.message), d.accept()))
    if not quiet:
        to_front_sync(page)
    step("여는 중")
    goto(page, HIEDU, wait_until="domcontentloaded")
    form = page.locator("#login_form #i")
    if form.count() and form.is_visible():
        c = hiedu_conf()
        uid, pw = c["id"], c["pw"]
        if not uid or not pw:
            raise RuntimeError("하이에듀 아이디가 없어요 — 오른쪽 클릭 → «상벌점 설정»")
        step("로그인 중")
        form.fill(uid)
        page.fill("#login_form #p", pw)
        page.click("#login_form button:has-text('로그인')")
        hiedu_cert(page, msgs)
    if cmd in ("class", "data"):
        hiedu_class(page, data=(cmd == "data"))
    if quiet:
        page.close()
    else:
        to_front_sync(page)
    print("READY", flush=True)


def hiedu_cert(page, msgs):
    """아이디·암호 다음에 뜨는 «인증서 입력 (전자서명)» 창 — 나이스와 같은 인증서·암호(자격 증명 관리자)를 넣는다.
    업무포털과 다른 인증서 창이다: 목록 #kc_cert_list, 암호칸 #certPassword, [확인] .kc-btn-blue (10/22 실측)."""
    step("인증서 기다리는 중")
    c = hiedu_conf()
    cert_name, cert_pw = c["cert_name"], c["cert_pw"]
    if not cert_name or not cert_pw:
        raise RuntimeError("인증서 설정이 없어요 — 오른쪽 클릭 → «상벌점 설정»")
    pwd = page.locator("#certPassword")
    for _ in range(40):
        if not page.locator("#login_form #i").is_visible():
            return                                  # 인증서 없이 들어가졌다
        if pwd.is_visible():
            break
        if msgs and "IP" in msgs[-1]:   # 학교 인터넷이 나가는 주소가 여럿이라, 하이에듀에 등록 안 된 주소로 나갈 때가 있다 (10/23 실측)
            raise RuntimeError("하이에듀가 지금 학교 인터넷 주소(IP)를 막았어요 — 잠시 뒤 다시 눌러 보세요")
        if msgs:
            raise RuntimeError("하이에듀 로그인 안 됨 — " + msgs[-1][:60])
        page.wait_for_timeout(500)
    else:
        raise RuntimeError("하이에듀 인증서 창이 안 떴어요")
    step("인증서 고르는 중")
    row = page.locator("#kc_cert_list tbody tr").filter(has_text=cert_name)
    try:
        row.first.wait_for(timeout=15_000)
        row.first.click()
    except Exception:
        raise RuntimeError("인증서 목록에서 설정된 인증서를 못 찾았어요")
    pwd.fill(cert_pw)
    page.locator(".kc-dialog button.kc-btn-blue:visible").first.click()
    try:
        page.wait_for_selector("#login_form #i", state="hidden", timeout=20_000)
    except Exception:
        raise RuntimeError("하이에듀 로그인 안 됨" + (" — " + msgs[-1][:60] if msgs else ""))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "open"
    watchdog(300)
    try:
        if cmd == "setup":
            hiedu_setup()
        elif cmd == "close":
            close_cmd("hiedu")
        else:
            hiedu_cmd(cmd)
    except BaseException as e:
        msg = (str(e).splitlines() or [type(e).__name__])[0][:140]
        print("FAIL " + msg, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
