# -*- coding: utf-8 -*-
"""바로가기 위젯 엔진 — 나이스·에듀파인을 인증서 자동 로그인까지 해서 맨 앞에 띄운다.

  python 바로가기_엔진.py neis open                 나이스 첫 화면 (로그인돼 있으면 1~2초, 아니면 로그인부터)
  python 바로가기_엔진.py neis warm [--launch]      미리 데워 두기 — 창은 꺼내지 않는다
  python 바로가기_엔진.py edufine main              K-에듀파인 첫 화면
  python 바로가기_엔진.py edufine open              문서등록대장
  python 바로가기_엔진.py edufine cnrs              공람대기
  python 바로가기_엔진.py edufine warm [--launch]   미리 데워 두기
  python 바로가기_엔진.py neis|edufine close        그 크롬 닫기

  출력은 STEP <하는 일> / READY / FAIL <이유> 줄 — 위젯이 이 줄만 읽는다.

왜 빠른가: 느린 건 «크롬을 새로 띄워 인증서 로그인하는 것»(15~35초)이다. 그래서 위젯이 뜰 때 크롬을
«최소화된 채로» 띄워 로그인해 두고(warm --launch), 5분마다 세션을 살려 둔다. 그다음 클릭은 창을 꺼내고
페이지만 옮기면 되니 1~2초다.

크롬은 «파이썬과 남남»인 프로세스로 띄워 스크립트가 끝나도 창이 남는다. 프로필·포트는 위젯 전용이다 —
출결·복무·품의 자동화가 쓰는 chrome_profile / chrome_profile_edufine 과 겹치면 «같은 프로필 크롬이 둘»이 돼서
자동화가 «프로필 사용 중»으로 막힌다. 그래서 따로 둔다.

로그인 코드는 키트의 것을 그대로 쓴다 — neis_session.login() · edufine_common.login().
"""
import asyncio
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT))
os.chdir(KIT)

import teacher_config  # noqa: E402  (stdout 을 UTF-8 로 돌려 준다)

BASE = teacher_config.CONFIG_DIR
SITES = {
    "neis": {"port": int(os.environ.get("WIDGET_NEIS_PORT", "9322")), "profile": BASE / "chrome_profile_widget_neis",
             "match": ("neis",)},
    "edufine": {"port": int(os.environ.get("WIDGET_EDUFINE_PORT", "9324")), "profile": BASE / "chrome_profile_widget_edufine",
                "match": ("klef", "eduptl")},
}
COMMON_ARGS = [
    "--profile-directory=Default",
    "--disable-blink-features=AutomationControlled",
    # 이 셋이 없으면 https 페이지가 127.0.0.1 보안모듈에 못 붙어 «보안프로그램 로딩중»에서 멈춘다
    "--disable-features=PrivateNetworkAccessForNavigations,PrivateNetworkAccessPermissionPrompt,PermissionChip",
    "--disable-web-security",
    "--allow-running-insecure-content",
    "--test-type", "--noerrdialogs", "--no-first-run", "--no-default-browser-check",
    # 최소화·가려진 창에서도 렌더러·타이머를 안 늦춘다 (뒤에서 로그인·새로고침하는 창용)
    "--disable-backgrounding-occluded-windows", "--disable-renderer-backgrounding",
]
T0 = time.time()


def step(msg):
    print("STEP %s  (%.1fs)" % (msg, time.time() - T0), flush=True)


# ───────────────────────── 설정 ─────────────────────────

def cfg_and_pw():
    """설정 파일(teacher_config.json)의 인증서 이름·나이스 주소 + 자격 증명 관리자의 암호.
    출결용 항목(학년·반·캘린더)은 없어도 된다 — 위젯은 로그인만 한다."""
    if not teacher_config.CONFIG_FILE.exists():
        raise RuntimeError("설정이 없어요 — 오른쪽 클릭 → «인증서 설정»을 먼저 해 주세요")
    cfg = {**teacher_config.DEFAULTS, **json.loads(teacher_config.CONFIG_FILE.read_text(encoding="utf-8"))}
    name = cfg.get("cert_name")
    if not name:
        raise RuntimeError("인증서 이름이 설정에 없어요 — «인증서 설정»을 다시 해 주세요")
    import keyring
    pw = keyring.get_password(teacher_config.KEYRING_SERVICE, name)
    if not pw:
        raise RuntimeError("'%s' 인증서 암호가 저장돼 있지 않아요 — «인증서 설정»을 다시 해 주세요" % name)
    return cfg, pw


# ───────────────────────── 크롬 ─────────────────────────

def chrome_exe():
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            p = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if p.exists():
                return str(p)
    raise RuntimeError("구글 크롬(chrome.exe)을 못 찾았어요 — 크롬을 설치해 주세요")


def alive(port):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d/json/version" % port, timeout=2) as r:
            return json.load(r).get("Browser")
    except Exception:
        return None


def profile_locked(profile):
    """이 프로필로 크롬이 (디버깅 포트 없이) 떠 있나 — 떠 있는 동안 lockfile 을 쥐고 있다."""
    lock = Path(profile) / "lockfile"
    if not lock.exists():
        return False
    try:
        lock.unlink()
        return False
    except OSError:
        return True


def fix_prefs(profile):
    """크롬이 꺼져 있을 때만 고쳐진다 — 띄우기 직전에 부른다.
    ① «비밀번호를 저장하시겠습니까?» 말풍선 끄기 (인증서 암호를 넣을 때 뜬다)
    ② «지난번에 최대화였다» 기억 끄기 — 이게 켜져 있으면 최소화로 띄워도 최대화로 뜬다 (2026-10-15 실측)"""
    pref = Path(profile) / "Default" / "Preferences"
    try:
        d = json.loads(pref.read_text(encoding="utf-8")) if pref.exists() else {}
        d["credentials_enable_service"] = False
        d.setdefault("profile", {})["password_manager_enabled"] = False
        d.setdefault("browser", {}).setdefault("window_placement", {})["maximized"] = False
        pref.parent.mkdir(parents=True, exist_ok=True)
        pref.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def launch(site, minimized):
    cfg = SITES[site]
    fix_prefs(cfg["profile"])
    args = [chrome_exe(), "--user-data-dir=%s" % cfg["profile"], "--remote-debugging-port=%d" % cfg["port"],
            *COMMON_ARGS] + ([] if minimized else ["--start-maximized"]) + ["about:blank"]
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if minimized:
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 7              # SW_SHOWMINNOACTIVE — 최소화된 채, 앞 창의 포커스도 안 뺏는다
        kw["startupinfo"] = si
    base = 0x00000008 | 0x00000200      # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen(args, creationflags=base | 0x01000000, **kw)   # CREATE_BREAKAWAY_FROM_JOB
    except OSError:
        subprocess.Popen(args, creationflags=base, **kw)
    for _ in range(60):
        if alive(cfg["port"]):
            return True
        time.sleep(0.5)
    return False


def ensure_chrome(site, minimized=False):
    """크롬이 없으면 띄운다. 돌려주는 값: 방금 띄웠으면 True (= 빈 창, 마음대로 해도 된다)."""
    cfg = SITES[site]
    if alive(cfg["port"]):
        return False
    if profile_locked(cfg["profile"]):
        raise RuntimeError("위젯용 크롬이 이상한 상태예요 — 그 창을 닫고 다시 눌러 주세요")
    step("크롬 띄우는 중")
    if not launch(site, minimized):
        raise RuntimeError("크롬이 안 떴어요")
    return True


def pick_page(ctx, site):
    for pg in ctx.pages:
        if any(k in pg.url for k in SITES[site]["match"]):
            return pg
    return ctx.pages[0] if ctx.pages else None


def connect_sync(p, port):
    """막 띄운 크롬(특히 새 프로필 첫 실행)은 포트가 열린 뒤에도 붙기가 한 번 튕긴다 (10/16 엔드투엔드 실측: 15초 타임아웃) → 3번."""
    last = None
    for i in range(3):
        try:
            return p.chromium.connect_over_cdp("http://127.0.0.1:%d" % port, timeout=15_000)
        except Exception as e:
            last = e
            step("붙기 실패, 다시 (%d/3)" % (i + 1))
            time.sleep(2)
    raise last


async def connect_async(p, port):
    last = None
    for i in range(3):
        try:
            return await p.chromium.connect_over_cdp("http://127.0.0.1:%d" % port, timeout=15_000)
        except Exception as e:
            last = e
            step("붙기 실패, 다시 (%d/3)" % (i + 1))
            await asyncio.sleep(2)
    raise last


def other_clients(port):
    """이 포트에 CDP 로 붙어 있는 «다른» 프로세스 (내 자식인 playwright 드라이버는 뺀다)."""
    try:
        import psutil
        conns = [c for c in psutil.net_connections(kind="tcp") if c.status == "ESTABLISHED"]
        peers = {c.raddr.port for c in conns if c.laddr.port == port}
        mine = {os.getpid()} | {c.pid for c in psutil.Process(os.getpid()).children(recursive=True)}
        return sorted({c.pid for c in conns if c.raddr.port == port and c.laddr.port in peers and c.pid not in mine})
    except Exception:
        return []


def watchdog(sec):
    def kill():
        print("FAIL 시간 초과 (%d초)" % sec, flush=True)
        os._exit(2)
    t = threading.Timer(sec, kill)
    t.daemon = True
    t.start()


# ───────────────────────── 창 앞뒤 ─────────────────────────

def _bounds(cdp):
    wid = cdp("Browser.getWindowForTarget")["windowId"]
    return wid, cdp("Browser.getWindowBounds", {"windowId": wid})["bounds"]


def window_minimized_sync(page):
    try:
        s = page.context.new_cdp_session(page)
        return _bounds(lambda m, p=None: s.send(m, p or {}))[1].get("windowState") == "minimized"
    except Exception:
        return False


async def window_minimized_async(page):
    try:
        s = await page.context.new_cdp_session(page)
        wid = (await s.send("Browser.getWindowForTarget"))["windowId"]
        return (await s.send("Browser.getWindowBounds", {"windowId": wid}))["bounds"].get("windowState") == "minimized"
    except Exception:
        return False


def _foreground(title):
    """다른 프로그램이 앞에 있으면 윈도우가 포커스 이동을 막는다 → Alt 를 한 번 눌렀다 떼면 풀린다."""
    try:
        u = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum(hwnd, _):
            n = u.GetWindowTextLengthW(hwnd)
            if n and u.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                if title and buf.value.startswith(title) and "Chrome" in buf.value:
                    found.append(hwnd)
            return True
        u.EnumWindows(enum, 0)
        if found:
            u.keybd_event(0x12, 0, 0, 0)
            u.keybd_event(0x12, 0, 2, 0)
            u.SetForegroundWindow(found[0])
    except Exception:
        pass


def to_front_sync(page):
    try:
        s = page.context.new_cdp_session(page)
        wid = s.send("Browser.getWindowForTarget")["windowId"]
        s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
        s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "maximized"}})
    except Exception:
        pass
    page.bring_to_front()
    _foreground(page.title())


async def to_front_async(page):
    try:
        s = await page.context.new_cdp_session(page)
        wid = (await s.send("Browser.getWindowForTarget"))["windowId"]
        await s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
        await s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "maximized"}})
    except Exception:
        pass
    await page.bring_to_front()
    _foreground(await page.title())


def minimize_sync(page):
    try:
        if window_minimized_sync(page):
            return
        s = page.context.new_cdp_session(page)
        wid = s.send("Browser.getWindowForTarget")["windowId"]
        s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "minimized"}})
    except Exception:
        pass


async def minimize_async(page):
    try:
        if await window_minimized_async(page):
            return
        s = await page.context.new_cdp_session(page)
        wid = (await s.send("Browser.getWindowForTarget"))["windowId"]
        await s.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "minimized"}})
    except Exception:
        pass


# ───────────────────────── 나이스 (async — 키트 neis_session 이 async) ─────────────────────────

async def neis_logged_in(page, ms=1500):
    if "neis" not in page.url:
        return False
    try:
        import neis_session as NS
        end = time.time() + ms / 1000
        while time.time() < end:
            if await NS.is_logged_in(page):
                return True
            await page.wait_for_timeout(200)
    except Exception:
        pass
    return False


async def neis_login(ctx, page):
    import neis_session as NS
    cfg, pw = cfg_and_pw()
    from urllib.parse import urlsplit
    try:
        sp = urlsplit(cfg["neis_url"])
        await ctx.grant_permissions(["notifications"], origin="%s://%s" % (sp.scheme, sp.netloc))
    except Exception:
        pass
    step("나이스 여는 중")
    await NS.login(page, cfg, pw)       # 인증서 고르기·암호·막히면 손 로그인 기다리기까지 키트 그대로
    step("로그인 확인 중")
    await NS.close_notice(page)


async def neis_cmd(cmd, launch_ok):
    from playwright.async_api import async_playwright
    site = "neis"
    if cmd == "warm" and not alive(SITES[site]["port"]) and not launch_ok:
        print("READY", flush=True)      # 닫아 둔 창은 다시 띄우지 않는다
        return
    fresh = ensure_chrome(site, minimized=(cmd == "warm"))
    async with async_playwright() as p:
        browser = await connect_async(p, SITES[site]["port"])
        ctx = browser.contexts[0]
        page = pick_page(ctx, site) or await ctx.new_page()
        if cmd == "open":
            if await neis_logged_in(page):
                step("이미 로그인돼 있음")
            else:
                await neis_login(ctx, page)
            await to_front_async(page)
            print("READY", flush=True)
            return
        # warm — 사용자 창은 ① 최소화돼 있고 ② 다른 자동화가 안 붙어 있을 때만 건드린다
        page.on("dialog", lambda d: None)
        if fresh:
            await minimize_async(page)
        else:
            if not await window_minimized_async(page):
                step("창을 쓰는 중이라 건드리지 않음")
                print("READY", flush=True)
                return
            if other_clients(SITES[site]["port"]):
                step("다른 자동화가 붙어 있어 건드리지 않음")
                print("READY", flush=True)
                return
            if await neis_logged_in(page):
                step("세션 확인 (새로고침)")   # 나이스 메인은 가만히 두면 서버에 아무것도 안 보낸다 → 새로고침이 곧 세션 연장
                await page.reload(wait_until="domcontentloaded")
                if await neis_logged_in(page, 25_000):
                    print("READY", flush=True)
                    return
                step("세션이 끊겨 있었음")
            # 여기까지 왔으면 창은 최소화돼 있고 아무도 안 붙어 있다 → 남아 있는 인증서 창은 지난 실패의 찌꺼기다.
            # 그걸 «누가 로그인 중»으로 보고 건너뛰면 영영 로그인이 안 된다 (10/16 엔드투엔드 실측) → 그냥 다시 로그인한다
        await neis_login(ctx, page)
        print("READY", flush=True)


# ───────────────────────── 에듀파인 (sync — 키트 edufine_common 이 sync) ─────────────────────────

def goto(page, url, **kw):
    """SSO 직후엔 리다이렉트가 아직 도는 중이라 «interrupted by another navigation» 으로 끊긴다 (10/15 실측) → 한 번 더."""
    for i in range(3):
        try:
            page.goto(url, **kw)
            return
        except Exception as e:
            if "interrupted" not in str(e) or i == 2:
                raise
            page.wait_for_timeout(1500)


def edufine_urls():
    import edufine_common as E
    k = E.KLEF.rstrip("/") + "/"
    return E, {"main": k + "keris_ui/main.do",
               "open": k + "bms/cz/cb/dbx/retrieveDocRegistRegstrList.do?leftMenu=1",
               "cnrs": k + "bms/cz/cb/viw/retrieveCnrsWaitDocList.do?leftMenu=1"}


def edufine_login(E, ctx, page, urls):
    E.grant_local_network(ctx)
    step("로그인 확인 중")
    cfg, pw = cfg_and_pw()
    E.login(page, cfg["cert_name"], pw)   # 업무포털 → 인증서 → 암호. 막히면 손 로그인 기다리기까지 키트 그대로
    step("에듀파인 들어가는 중")
    try:    # 업무포털 → 에듀파인 SSO. klef 의 main.do 가 200 으로 오면 세션이 생긴 것
        with page.expect_response(lambda r: r.url.startswith(urls["main"]) and r.status == 200, timeout=15000):
            page.goto(urls["main"], wait_until="commit")
    except Exception:
        page.wait_for_timeout(3000)


def edufine_session_ok(page, urls):
    """세션이 살아 있나 — 문서등록대장을 fetch 해 본다 (화면은 안 움직인다)."""
    if "klef." not in page.url:
        return False
    try:
        page.wait_for_load_state("domcontentloaded")
        r = page.evaluate("""async (u) => { const r = await fetch(u, {credentials: 'include'}); const h = await r.text();
            return {url: r.url, ok: h.includes('tbList')}; }""", urls["open"])
        return bool(r and r["ok"] and "klef." in r["url"])
    except Exception:
        return False


def edufine_cmd(cmd, launch_ok):
    from playwright.sync_api import sync_playwright
    site = "edufine"
    E, urls = edufine_urls()
    if cmd == "warm" and not alive(SITES[site]["port"]) and not launch_ok:
        print("READY", flush=True)
        return
    fresh = ensure_chrome(site, minimized=(cmd == "warm"))
    with sync_playwright() as p:
        browser = connect_sync(p, SITES[site]["port"])
        ctx = browser.contexts[0]
        page = pick_page(ctx, site) or ctx.new_page()
        page.set_default_timeout(30_000)
        if cmd == "warm":
            page.on("dialog", lambda d: None)
            if fresh:
                minimize_sync(page)
            if edufine_session_ok(page, urls):
                print("READY", flush=True)
                return
            if not fresh and not window_minimized_sync(page):
                step("창을 쓰는 중이라 건드리지 않음")
                print("READY", flush=True)
                return
            edufine_login(E, ctx, page, urls)
            goto(page, urls["open"], wait_until="domcontentloaded")   # 문서등록대장에 세워 둔다 (nexacro 메인은 오래 두면 알림창이 뜬다)
            print("READY", flush=True)
            return
        page.on("dialog", E.on_dialog)      # «다른 IP 에서 접속 중» 창만 [확인], 나머지는 «아니오» — 키트 규칙
        target = urls[cmd]
        key = target.split("?")[0].rsplit("/", 1)[-1]
        if key in page.url:
            to_front_sync(page)             # 창부터 보여 주고 그다음 새로고침
            step("새로 불러오는 중")
            page.reload(wait_until="domcontentloaded")
        elif "klef." in page.url and edufine_session_ok(page, urls):
            to_front_sync(page)
            step("여는 중")
            goto(page, target, wait_until="domcontentloaded")
        else:
            edufine_login(E, ctx, page, urls)
            step("여는 중")
            goto(page, target, wait_until="domcontentloaded")
        if cmd != "main":
            try:
                page.wait_for_selector("#tbList tbody tr", timeout=20_000)
            except Exception:
                pass
        to_front_sync(page)
        print("READY", flush=True)


def close_cmd(site):
    port = SITES[site]["port"]
    if not alive(port):
        print("CLOSED", flush=True)
        return
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:%d" % port, timeout=8000)
        b.new_browser_cdp_session().send("Browser.close")
    print("CLOSED", flush=True)


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "neis"
    cmd = sys.argv[2] if len(sys.argv) > 2 else "open"
    launch_ok = "--launch" in sys.argv
    watchdog(900 if cmd != "warm" else 300)     # 손 로그인 기다리기(최대 10분)까지 감안
    try:
        if cmd == "close":
            close_cmd(site)
        elif site == "neis":
            asyncio.run(neis_cmd(cmd, launch_ok))
        else:
            edufine_cmd(cmd, launch_ok)
    except BaseException as e:
        msg = (str(e).splitlines() or [type(e).__name__])[0][:140]
        print("FAIL " + msg, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
