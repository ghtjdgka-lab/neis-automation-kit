# -*- coding: utf-8 -*-
"""e알리미 상벌점 — 바로가기 위젯의 [상벌점] 단추가 부르는 엔진 (클로드·Node 없이).

  python widget\\상벌점_엔진.py login           창을 띄워 로그인 (처음 한 번 — 폰 승인까지)
  python widget\\상벌점_엔진.py sync            명렬·벌점표 받기 (창 없음, 1~2분)
  python widget\\상벌점_엔진.py give --sid 10701,10702 --type 벌점 --point 1 --item "과제 이행 상태 불량" [--dry]
  python widget\\상벌점_엔진.py status          연결돼 있는지·받아 둔 명렬 수

출력은 위젯이 읽는 한 줄 신호: STEP … / READY … / FAIL …  (바로가기_엔진.py 와 같은 모양)

왜 이렇게 하나:
  · 등록 버튼이 실제로 보내는 건 /PenaltyV2/SetPenaltyPoint 폼 전송 하나뿐이라(2026-10-06 확인)
    등록은 브라우저 없이 HTTP 로 1초 안에 끝난다. 브라우저는 로그인·명렬/벌점표 받기에만 쓴다.
  · e알리미는 «처음 보는 브라우저 프로필»로 로그인하면 폰 승인을 요구한다 — 이건 사람이 해야 해서
    login 만 창을 띄운다. 같은 프로필로 다시 로그인할 때는 승인 없이 넘어가므로 그다음부터는 창 없이 다시 로그인한다.
  · 아이디·비밀번호는 «Windows 자격 증명 관리자»(keyring, 서비스 ealimi-kit)에만 둔다.
  · ⚠️ 학생 명렬(이름·반·번호)은 이 컴퓨터의 %LOCALAPPDATA%\\neis-automation\\ealimi\\ 에만 쓴다.
    키트 폴더·깃에는 절대 들어가지 않는다. 화면·로그에도 이름을 찍지 않는다(개수만).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

BASE_URL = "https://www.ealimi.com"
SIGNIN_URL = BASE_URL + "/Member/SignIn"
PROBE_URL = BASE_URL + "/penaltyV2/PointsWrite"
SERVICE = "ealimi-kit"
DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "neis-automation" / "ealimi"
COOKIES = DATA / "cookies.json"
ROSTER = DATA / "roster.json"
CATALOG = DATA / "catalog.json"
PROFILE = DATA / "chrome-profile"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
# 위젯이 «상 / 벌 / 상쇄» 만 고르면 들어가는 기본 항목 (방배중 벌점표 기준 — 없으면 그 점수가 되는 첫 항목)
DEFAULTS = {"상점": "수업 태도가 바람직하여 다른 학생의 모범이 될 때", "벌점": "과제 이행 상태 불량",
            "벌점차감": "벌점상쇄"}
T0 = time.time()


def out(kind, msg=""):
    print("%s %s  (%.1fs)" % (kind, msg, time.time() - T0) if kind == "STEP" else "%s %s" % (kind, msg), flush=True)


class SessionDead(Exception):
    pass


# ── 저장소 ──
def save_json(p, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def load_json(p, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def credentials():
    import keyring
    c = keyring.get_credential(SERVICE, None)
    return (c.username, c.password) if c and c.username and c.password else (None, None)


def set_credentials(uid, pw):
    import keyring
    old, _ = credentials()
    if old and old != uid:
        try:
            keyring.delete_password(SERVICE, old)
        except Exception:
            pass
    keyring.set_password(SERVICE, uid, pw)


def cookie_header():
    cs = load_json(COOKIES, [])
    return "; ".join("%s=%s" % (c["name"], c["value"]) for c in cs if "ealimi" in c.get("domain", ""))


# ── 브라우저 ──
def browser(pw, profile=None, headless=True):
    """채널 크롬(설치된 크롬) 우선, 없으면 키트가 받은 크로미움."""
    args = ["--no-first-run", "--no-default-browser-check", "--disable-blink-features=AutomationControlled"]
    opts = dict(headless=headless, args=args, ignore_default_args=["--enable-automation"],
                viewport={"width": 1280, "height": 900})
    for ch in ("chrome", None):
        try:
            if profile:
                return pw.chromium.launch_persistent_context(str(profile), channel=ch, **opts)
            b = pw.chromium.launch(channel=ch, headless=headless, args=args, ignore_default_args=["--enable-automation"])
            return b.new_context(viewport=opts["viewport"])
        except Exception:
            if ch is None:
                raise


def save_ctx_cookies(ctx):
    cs = [c for c in ctx.cookies() if "ealimi" in c.get("domain", "")]
    if not cs:
        raise RuntimeError("e알리미 쿠키가 없어요")
    save_json(COOKIES, cs)
    return len(cs)


def probe(ctx):
    """새 탭에서 상벌점 입력 화면이 열리면 = 교사 로그인 + 기기 인증 끝."""
    tab = ctx.new_page()
    try:
        tab.goto(PROBE_URL, wait_until="domcontentloaded", timeout=20000)
        tab.wait_for_selector("#selGroup1", state="attached", timeout=12000)
        return "SignIn" not in tab.url
    except Exception:
        return False
    finally:
        tab.close()


def fill_login(page, uid, pw):
    page.goto(SIGNIN_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1000)
    if "SignIn" not in page.url:
        return
    page.wait_for_selector("#id", timeout=10000)
    page.fill("#id", uid)
    page.fill("#pw", pw)
    keep = page.query_selector("#rememberMe")
    if keep and not keep.is_checked():
        keep.click()
    page.click("#signInSubmitBtn")


def cmd_login(a):
    """창을 띄워 로그인. 아이디·암호가 저장돼 있으면 채워서 누르고, 폰 승인은 선생님이 한다. 9분 기다린다."""
    from playwright.sync_api import sync_playwright
    uid, pw_ = credentials()
    DATA.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = browser(p, PROFILE, headless=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("dialog", lambda d: None)          # 알림창은 선생님이 보게 둔다
            page.bring_to_front()
            if uid:
                out("STEP", "아이디·암호 넣고 로그인 누름")
                try:
                    fill_login(page, uid, pw_)
                except Exception:
                    pass
            else:
                page.goto(SIGNIN_URL, wait_until="domcontentloaded")
            out("STEP", "폰으로 «인증 요청»이 오면 승인해 주세요")
            end = time.time() + 9 * 60
            while time.time() < end:
                time.sleep(3)
                if page.is_closed():
                    out("FAIL", "로그인 창이 닫혔어요")
                    return 1
                if "SignIn" in page.url:
                    continue
                if probe(ctx):
                    n = save_ctx_cookies(ctx)
                    out("READY", "e알리미 연결 완료 (쿠키 %d개)" % n)
                    return 0
            out("FAIL", "9분 안에 로그인이 끝나지 않았어요")
            return 1
        finally:
            ctx.close()


def relogin_headless():
    """같은 프로필(이미 기기 승인된)로 창 없이 다시 로그인해 쿠키를 새로 받는다."""
    from playwright.sync_api import sync_playwright
    uid, pw_ = credentials()
    if not uid:
        raise SessionDead("e알리미 아이디·암호가 저장돼 있지 않아요 — 오른쪽 클릭 → «상벌점(e알리미) 연결»")
    with sync_playwright() as p:
        ctx = browser(p, PROFILE, headless=True)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("dialog", lambda d: d.accept())
            fill_login(page, uid, pw_)
            try:
                page.wait_for_function("() => !/Member\\/SignIn/i.test(location.href)", timeout=20000)
            except Exception:
                pass
            if re.search(r"/Ce/cert", page.url, re.I):
                raise SessionDead("e알리미가 폰 승인을 다시 요구해요 — 오른쪽 클릭 → «상벌점(e알리미) 연결»")
            if "SignIn" in page.url or not probe(ctx):
                raise SessionDead("e알리미 로그인이 안 돼요 (암호가 바뀌었나요?) — 오른쪽 클릭 → «상벌점(e알리미) 연결»")
            save_ctx_cookies(ctx)
        finally:
            ctx.close()


# ── 명렬·벌점표 ──
SCAN_JS_ITEM = """() => {
  const $ = window.jQuery, vis = $('#divMessageArea').is(':visible');
  return { code: $('input[name="penaltyCode"]:checked').val(), piId: $('#penaltyItem').val(),
    subject: $('#penaltyItem').find('option:selected').text(),
    points: [...document.querySelectorAll('#penaltyPoint option')].map(o => o.value).filter(Boolean),
    push: { push_alrim: vis ? $('input[name="push_alrim"]:checked').val() : 0,
            push_target: vis ? $('input[data-elementtype="push_target"]:checked').map(function(){return $(this).val();}).get().join(',') : '',
            push_useSms: vis ? $('#push_useSms').is(':checked') : false,
            push_isFirstMember: true, smsPhone: $('#smsPhone').val() } };
}"""


def close_popups(page):
    page.evaluate("""() => document.querySelectorAll('a').forEach(a => {
        if (a.innerText.trim() === '닫기' && a.offsetParent) a.click(); })""")


def scan(page):
    page.goto(PROBE_URL, wait_until="domcontentloaded")
    if "SignIn" in page.url:
        raise SessionDead("세션 만료")
    page.wait_for_selector("#selGroup1", timeout=15000)
    grades = page.eval_on_selector_all("#selGroup1 option", "os => os.map(o => o.value).filter(v => /\\d\\s*학년/.test(v))")

    # 벌점표 — 유형 → 분류 → 항목마다 허용 점수와 «등록 요청에 실제로 들어갈 값»
    types = page.evaluate("""() => [...document.querySelectorAll('label')]
        .filter(x => /^penaltyCode\\d$/.test(x.getAttribute('for') || '')).map(x => x.innerText.trim())""")
    opts = lambda sel: page.eval_on_selector_all(sel + " option",
                                                 "os => os.filter(o => o.value).map(o => ({v: o.value, t: o.text.replace(/^_/, '').trim()}))")
    cat = {"at": date.today().isoformat(), "grades": grades, "types": {}}
    for t in types:
        out("STEP", "벌점표 받는 중 — " + t)
        page.evaluate("""t => [...document.querySelectorAll('label')].find(x =>
            /^penaltyCode\\d$/.test(x.getAttribute('for') || '') && x.innerText.trim() === t).click()""", t)
        page.wait_for_timeout(1200)
        cat["types"][t] = []
        for c in opts("#itemCategory"):
            page.evaluate("v => window.jQuery('#itemCategory').val(v).trigger('change')", c["v"])
            page.wait_for_timeout(900)
            for it in opts("#penaltyItem"):
                page.evaluate("v => window.jQuery('#penaltyItem').val(v).trigger('change')", it["v"])
                page.wait_for_timeout(350)
                d = page.evaluate(SCAN_JS_ITEM)
                d.update(category=c["t"], item=it["t"])
                cat["types"][t].append(d)

    # 명렬 — 학년마다 반을 돌며 학생 체크박스의 반ㆍ번호ㆍ이름·주소록 id(pm)를 모은다
    page.goto(PROBE_URL, wait_until="domcontentloaded")
    page.wait_for_selector("#selGroup1", timeout=15000)
    students = []
    for g in grades:
        gd = (re.search(r"(\d)\s*학년", g) or [None, "0"])[1]
        out("STEP", "명렬 받는 중 — %s학년" % gd)
        page.select_option("#selGroup1", g)
        close_popups(page)
        page.wait_for_function("""g => [...document.querySelectorAll('#selGroup2 option')]
            .some(o => o.dataset.group1num === g)""", arg=g, timeout=15000)
        classes = page.evaluate("""g => [...document.querySelectorAll('#selGroup2 option')]
            .filter(o => o.dataset.group1num === g && /^\\d+반$/.test(o.text.trim())).map(o => o.text.trim())""", g)
        for k in classes:
            page.select_option("#selGroup2", k)
            close_popups(page)
            want = g + "ㆍ" + k + "ㆍ"
            try:
                page.wait_for_function("""w => [...document.querySelectorAll('input[type=checkbox][data-addrname]')]
                    .some(i => (i.getAttribute('data-discription') || '').startsWith(w))""", arg=want, timeout=15000)
            except Exception:
                continue                                  # 학생이 없는 반
            got = page.evaluate("""w => [...document.querySelectorAll('input[type=checkbox][data-addrname]')]
                .map(i => [i.getAttribute('data-discription') || '', i.getAttribute('data-addrid')])
                .filter(([d]) => d.startsWith(w))
                .map(([d, pm]) => { const p = d.split('ㆍ'); return {klass: p[1], no: +p[2], name: p[3], pm: +pm || null}; })
                .filter(s => s.name && Number.isInteger(s.no) && s.pm)""", want)
            for s in got:
                s["sid"] = "%s%02d%02d" % (gd, int(re.sub(r"\D", "", s["klass"]) or 0), s["no"])
            students.extend(got)
    return cat, students


def cmd_sync(a):
    from playwright.sync_api import sync_playwright
    for attempt in (1, 2):
        if not COOKIES.exists():
            relogin_headless()
        try:
            with sync_playwright() as p:
                ctx = browser(p, headless=True)
                try:
                    ctx.add_cookies(load_json(COOKIES, []))
                    page = ctx.new_page()
                    cat, students = scan(page)
                finally:
                    ctx.close()
            break
        except SessionDead:
            if attempt == 2:
                raise
            out("STEP", "다시 로그인하는 중")
            relogin_headless()
    save_json(CATALOG, cat)
    save_json(ROSTER, {"at": date.today().isoformat(), "students": students})
    n = {t: len(v) for t, v in cat["types"].items()}
    by = {}
    for s in students:
        by[s["sid"][0]] = by.get(s["sid"][0], 0) + 1
    out("READY", "명렬 %d명 (%s) · 벌점표 %s" % (len(students), ", ".join("%s학년 %d" % kv for kv in sorted(by.items())) or "없음",
                                            " ".join("%s %d" % kv for kv in n.items())))
    return 0 if students else 1


# ── 등록 (HTTP) ──
def http(path, data=None):
    h = {"cookie": cookie_header(), "x-requested-with": "XMLHttpRequest", "user-agent": UA,
         "referer": PROBE_URL}
    body = None
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        h.update({"content-type": "application/x-www-form-urlencoded; charset=UTF-8",
                  "accept": "application/json, text/javascript, */*; q=0.01", "origin": BASE_URL})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kw):
            return None
    req = urllib.request.Request(BASE_URL + path, data=body, headers=h, method="POST" if body else "GET")
    try:
        r = urllib.request.build_opener(NoRedirect).open(req, timeout=20)
        return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:                   # 로그인이 풀리면 어디론가 돌려보낸다 (쿠키가 없으면 SignIn 이 아닌 곳으로도 — 실측)
            raise SessionDead("세션 만료")
        raise


def strip(h):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", h).replace("&nbsp;", " ")).strip()


def points_list():
    st, html = http("/PenaltyV2/PointsList?pageNum=0&pageSize=50&pss_id=0&codes=&pic_id=0&pi_id=00&")
    rows = []
    for tr in re.split(r"<tr[\s>]", html)[1:]:
        m = re.search(r'data-ppid="(\d+)"', tr)
        if m:
            rows.append((m.group(1), [strip(x) for x in re.findall(r"<td[^>]*>([\s\S]*?)</td>", tr)][1:]))
    return rows


def find_item(cat, typ, point, item=None):
    items = cat.get("types", {}).get(typ, [])
    want = item or DEFAULTS.get(typ)
    ok = [x for x in items if str(point) in x["points"]]
    for x in ok:
        if x["item"] == want:
            return x
    if item:                                   # 직접 고른 항목인데 그 점수가 안 되면 멈춘다
        return None
    return ok[0] if ok else None


def cmd_give(a):
    cat, ros = load_json(CATALOG, {}), load_json(ROSTER, {})
    if not cat or not ros:
        out("FAIL", "명렬·벌점표가 없어요 — 오른쪽 클릭 → «상벌점 명렬 다시 받기»")
        return 1
    people = {s["sid"]: s for s in ros.get("students", [])}
    sids = [s for s in re.split(r"[,\s]+", a.sid) if s]
    miss = [s for s in sids if s not in people]
    if miss:
        out("FAIL", "명렬에 없는 학번: " + ", ".join(miss))
        return 1
    it = find_item(cat, a.type, a.point, a.item)
    if not it:
        out("FAIL", "%s %s점이 되는 항목이 없어요" % (a.type, a.point))
        return 1
    day = a.date or date.today().isoformat()
    body = []
    for i, s in enumerate(sids):
        p = "pp[%d]" % i
        st = people[s]
        body += [(p + "[CODE]", it["code"]), (p + "[PM_ID]", str(st["pm"])), (p + "[PI_ID]", it["piId"]),
                 (p + "[SUBJECT]", it["subject"]), (p + "[POINT]", str(a.point)), (p + "[ETC]", ""),
                 (p + "[FINISHDATE]", day)]
    body += [(k, "" if v is None else (str(v).lower() if isinstance(v, bool) else str(v))) for k, v in it["push"].items()]

    for attempt in (1, 2):                      # 세션 확인은 «아무것도 안 보낸» 이 자리에서만 다시 한다
        try:
            before = {pp for pp, _ in points_list()}
            break
        except SessionDead:
            if attempt == 2:
                raise
            out("STEP", "다시 로그인하는 중")
            relogin_headless()
    if a.dry:
        out("READY", "dry — %d명 · %s %s점 · %s · %s" % (len(sids), a.type, a.point, it["item"][:30], day))
        return 0

    # ── 여기부터는 되돌릴 수 없다. 실패해도 다시 보내지 않는다 (중복 등록)
    st, txt = http("/PenaltyV2/SetPenaltyPoint", body)
    try:
        res = json.loads(txt)
    except ValueError:
        out("FAIL", "등록 응답을 못 읽었어요 — e알리미 부여내역에서 들어갔는지 확인해 주세요")
        return 1
    if not res.get("IsSuccess"):
        out("FAIL", "등록 실패: " + str(res.get("message") or txt[:100]))
        return 1
    new = [c for pp, c in points_list() if pp not in before]
    hit = 0
    for s in sids:
        st_ = people[s]
        if any(len(c) >= 10 and c[1] == st_["klass"] and c[2] == str(st_["no"]) and c[3] == st_["name"]
               and c[4] == a.type and c[7] == str(a.point) and c[9] == day for c in new):
            hit += 1
    if hit >= len(sids):
        out("READY", "%d명 등록 · %s %s점 · %s" % (hit, a.type, a.point, it["item"][:30]))
        return 0
    out("FAIL", "보냈는데 목록에서 %d/%d명만 보여요 — e알리미 부여내역을 확인해 주세요" % (hit, len(sids)))
    return 1


def cmd_status(a):
    ros, cat = load_json(ROSTER, {}), load_json(CATALOG, {})
    uid, _ = credentials()
    out("READY", json.dumps({"id": bool(uid), "cookies": COOKIES.exists(), "students": len(ros.get("students", [])),
                             "roster_at": ros.get("at"), "catalog_at": cat.get("at")}, ensure_ascii=False))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("login")
    sp.add_parser("sync")
    sp.add_parser("status")
    g = sp.add_parser("give")
    g.add_argument("--sid", required=True)
    g.add_argument("--type", required=True, choices=["상점", "벌점", "벌점차감"])
    g.add_argument("--point", type=int, required=True)
    g.add_argument("--item")
    g.add_argument("--date")
    g.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    try:
        return {"login": cmd_login, "sync": cmd_sync, "give": cmd_give, "status": cmd_status}[a.cmd](a)
    except SessionDead as e:
        out("FAIL", str(e))
        return 2
    except Exception as e:
        out("FAIL", "%s: %s" % (type(e).__name__, str(e)[:200]))
        return 1


if __name__ == "__main__":
    sys.exit(main())
