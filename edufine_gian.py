# -*- coding: utf-8 -*-
"""K-에듀파인 «기안기» 창 (WXSClient.exe) — 품의 [결재요청] 뒤에 뜨는 창을 채우고 [결재올림] 까지.

품의 화면에서 [결재요청] → «결재요청 하시겠습니까?» [확인] 을 누르면 브라우저가 아니라
컴퓨터에 깔린 에듀파인 기안기 창(«문서관리카드기안»)이 뜬다. 여기서 필수 세 칸을 채워야 실제로 올라간다.
  * 과제카드   — 비어서 온다
  * 대국민공개여부 — 아무것도 안 골라져서 온다
  * 결재경로   — 기안자 한 줄뿐이다 → «나의결재선» 에 저장해 둔 이름으로 고른다

순서 (2026-09-21 서울 중학교 실측, 연습 품의로 끝까지 올려 봄):
  [결재올림] → «수신자를 지정하지 않으면 내부결재로 처리됩니다» [확인]
            → 「결재올림」 창(IE 대화상자) [확인]      ← 여기부터 되돌릴 수 없다. [결재올림] 을 다시 누르지 않는다
            → «원문공개 문서는 바로 국민에게 공개됩니다» [확인] (공개일 때)
            → «정상적으로 처리되었습니다» [확인] → 기안기가 스스로 닫힌다
모르는 창·문구가 뜨면 누르지 않고 멈춘다 (창도 닫지 않는다 — 선생님이 이어서 손으로 할 수 있게).
"""
import ctypes
import ctypes.wintypes as W
import re
import time

import edufine_common as E

try:
    import win32api
    import win32clipboard
    import win32con
    import win32gui
    import win32process
    from pywinauto import Desktop, keyboard, mouse
except ImportError:                                  # 예전에 설치한 폴더에는 없다
    raise SystemExit(
        "기안기 창을 다루는 부품(pywinauto)이 아직 안 깔려 있습니다. 한 번만 깔아 주세요:\n"
        "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt")

IE_DLG = "Internet Explorer_TridentDlgFrame"
MSG_TITLE = "웹 페이지 메시지"
DISCLOSURE = {"공개": "othbcLmtt1", "비공개": "othbcLmtt3"}    # 부분공개는 제한근거를 골라야 해서 자동으로 안 한다


class Stop(Exception):
    """누르지 않고 멈춘다 — 기안기 창은 그대로 둔다."""


# ── 창 찾기 ─────────────────────────────────────────────────────
def wxs_pids():
    out = set()
    def f(h, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(h)
            hp = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            buf = ctypes.create_unicode_buffer(260)
            n = W.DWORD(260)
            if hp and ctypes.windll.kernel32.QueryFullProcessImageNameW(hp, 0, buf, ctypes.byref(n)):
                if buf.value.lower().endswith("wxsclient.exe"):
                    out.add(pid)
            if hp:
                ctypes.windll.kernel32.CloseHandle(hp)
        except Exception:
            pass
    win32gui.EnumWindows(f, None)
    return out


def windows(cls=None, title=None, pids=None):
    out = []
    def f(h, _):
        if not win32gui.IsWindowVisible(h):
            return
        if cls and win32gui.GetClassName(h) != cls:
            return
        if title and title not in win32gui.GetWindowText(h):
            return
        if pids is not None and win32process.GetWindowThreadProcessId(h)[1] not in pids:
            return
        out.append(h)
    win32gui.EnumWindows(f, None)
    return out


def gian_hwnd():
    hs = windows("#32770", "기안기", wxs_pids())
    return hs[-1] if hs else None


def wait_gian(timeout=60):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        h = gian_hwnd()
        if h:
            return h
        time.sleep(0.5)
    return None


def gian_window(h):
    return Desktop(backend="uia").window(handle=h)


# ── 누르기·붙여넣기 ──────────────────────────────────────────────
def focus(h):
    win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)       # Alt 를 한 번 눌러야 SetForegroundWindow 가 먹는다
    try:
        win32gui.SetForegroundWindow(h)
    except Exception:
        pass
    win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.3)


def center(ctrl):
    r = ctrl.rectangle()
    return ((r.left + r.right) // 2, (r.top + r.bottom) // 2)


def rel_click(h, x, y, wait=0.4):
    left, top, _, _ = win32gui.GetWindowRect(h)
    mouse.click(coords=(left + x, top + y))
    time.sleep(wait)


def paste(text):
    """한글은 type_keys 로 못 친다 — 클립보드로 붙인다."""
    win32clipboard.OpenClipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()
    keyboard.send_keys("^a^v")
    time.sleep(0.3)


def msg_text(h):
    parts = []
    win32gui.EnumChildWindows(
        h, lambda c, _: parts.append(win32gui.GetWindowText(c)) if win32gui.GetClassName(c) == "Static" else None, None)
    return " ".join(p for p in parts if p).replace("\n", " ")


def press_msg(h, button="확인"):
    focus(h)
    b = win32gui.FindWindowEx(h, 0, "Button", button)
    if not b:
        raise Stop("알림창에 [%s] 단추가 없습니다: %s" % (button, msg_text(h)))
    left, top, right, bottom = win32gui.GetWindowRect(b)
    mouse.click(coords=((left + right) // 2, (top + bottom) // 2))
    time.sleep(0.6)


def shot(h, name):
    try:
        from PIL import ImageGrab
        E.OUT_DIR.mkdir(parents=True, exist_ok=True)
        p = E.OUT_DIR / name
        ImageGrab.grab(bbox=win32gui.GetWindowRect(h), all_screens=True).save(p)
        E.log("  📸 캡처: %s" % p)
    except Exception:
        pass


def norm(s):
    return re.sub(r"\s+", "", s or "")


# ── 칸 채우기 ────────────────────────────────────────────────────
def card_text(w):
    """과제카드 칸에 들어간 글자."""
    for c in w.descendants(control_type="Text"):
        t = c.window_text() or ""
        if t.startswith("[") and "]" in t and "(" in t:
            r = c.rectangle()
            if 140 < r.left < 700:
                return t
    return ""


def card_rows(pop):
    """과제카드 창 결과 줄 — [(글자, 화면 y)]. 못 읽으면 None, «조회 결과가 없습니다» 면 []."""
    try:
        d = Desktop(backend="uia").window(handle=pop)
        _, top, _, _ = win32gui.GetWindowRect(pop)
        out, empty = [], False
        for c in d.descendants(control_type="Text"):
            t = (c.window_text() or "").strip()
            r = c.rectangle()
            if not (270 <= r.top - top <= 515):
                continue
            if "조회 결과가 없습니다" in t:
                empty = True
            elif t.startswith("[") and "]" in t:
                out.append((t, (r.top + r.bottom) // 2))
        return out if (out or empty) else None
    except Exception:
        return None


def close_card_popup(pop):
    try:
        for b in Desktop(backend="uia").window(handle=pop).descendants(control_type="Button"):
            aid = b.element_info.automation_id or ""
            if aid.endswith("form.btnOk") or aid.endswith("btnClose00"):
                mouse.click(coords=center(b))
                time.sleep(0.8)
    except Exception:
        pass


def set_card(h, card):
    w = gian_window(h)
    if norm(card) in norm(card_text(w)):
        return card_text(w)
    img = [c for c in w.descendants(control_type="Image") if "과제카드선택" in (c.window_text() or "")]
    if not img:
        raise Stop("과제카드 돋보기를 못 찾았습니다")
    before = set(windows(IE_DLG))
    mouse.click(coords=center(img[0]))
    pop = None
    end = time.monotonic() + 40                          # 실측: 뜨는 데 12초 넘게 걸렸다
    while time.monotonic() < end and not pop:
        time.sleep(0.4)
        new = [x for x in windows(IE_DLG) if x not in before]
        pop = new[-1] if new else None
    if not pop:
        raise Stop("과제카드선택 창이 40초 안에 안 떴습니다")
    time.sleep(1.2)                                      # 목록이 그려질 시간
    focus(pop)
    # 카드 이름이 «[단위과제] 카드명» 꼴이면 검색은 대괄호 안(단위과제)으로 하고, 줄은 카드명까지 맞는 것을 고른다
    m = re.match(r"\s*\[([^\]]+)\]\s*(.*)", card)
    query, want = (m.group(1), card) if m else (card, card)
    rel_click(pop, 350, 176)                             # 단위과제카드명 칸
    paste(query)
    rel_click(pop, 734, 131, 3.0)                        # [조회]
    rows = card_rows(pop)                                # 창 안 글자를 읽어 맞는 줄을 고른다 (2026-10-06: 과제카드 창은 UIA 로 읽힌다)
    hit = [] if rows is None else (
        [r for r in rows if norm(want) in norm(r[0])] or ([] if m else [r for r in rows if norm(query) in norm(r[0])]))
    if rows is not None and not hit:
        shot(pop, "과제카드_없음.png")
        close_card_popup(pop)
        raise Stop("과제카드 '%s' 가 내 목록에 없습니다. 검색 결과: %s\n"
                   "  (과제카드 창에는 «내가 쓸 수 있는» 카드만 나옵니다 — 지난 내 공문에 쓰인 카드 이름을 적어 주세요)"
                   % (card, " / ".join(r[0] for r in rows) or "없음"))
    left, top, _, _ = win32gui.GetWindowRect(pop)
    if hit:
        mouse.click(coords=(left + 44, hit[0][1]))       # 그 줄의 선택 칸
        time.sleep(0.5)
    else:
        rel_click(pop, 44, 281, 0.5)                     # 글자를 못 읽으면 예전처럼 첫 줄
    shot(pop, "과제카드.png")
    rel_click(pop, 714, 531, 1.0)                        # [확인]
    for _ in range(20):
        if not win32gui.IsWindow(pop) or not win32gui.IsWindowVisible(pop):
            break
        time.sleep(0.3)
    got = card_text(gian_window(h))
    if norm(card) not in norm(got):
        raise Stop("과제카드가 '%s' 로 안 들어갔습니다 (지금: '%s'). 이름을 에듀파인 목록 글자 그대로 적어 주세요" % (card, got))
    return got


def click_label(h, label):
    """라디오·체크박스는 크기가 0 이라 옆 글자의 왼쪽 끝을 누른다 (맨 위 줄 = 문서정보 칸)."""
    texts = [c for c in gian_window(h).descendants(control_type="Text") if (c.window_text() or "") == label]
    if not texts:
        raise Stop("'%s' 글자를 못 찾았습니다" % label)
    t = min(texts, key=lambda c: (c.rectangle().top, c.rectangle().left)).rectangle()
    mouse.click(coords=(t.left + 7, (t.top + t.bottom) // 2))
    time.sleep(1.0)


def set_partial(h, what, reason=""):
    """부분공개(6) · 비공개(5) 처럼 «호» 가 붙은 값. 정보공개법 제9조 제1항 — 5호 의사결정 과정 · 6호 개인정보 · 7호 영업비밀.
    호 체크박스와 공개제한사유 칸은 «부분공개/비공개» 를 고른 뒤에만 쓸 수 있다 (2026-10-06 공용서식 실측)."""
    m = re.fullmatch(r"(부분공개|비공개)\((\d)\)", norm(what))
    if not m:
        raise Stop("공개여부 '%s' 를 모르겠습니다 — 공개 · 비공개 · 부분공개(6) · 비공개(5) 꼴로 적어 주세요" % what)
    kind, ho = m.groups()
    click_label(h, kind)
    want = {"부분공개": "othbcLmtt2", "비공개": "othbcLmtt3"}[kind]
    w = gian_window(h)
    if not any(c.element_info.automation_id == want and c.is_selected() for c in w.descendants(control_type="RadioButton")):
        raise Stop("공개여부가 '%s' 로 안 골라졌습니다" % kind)
    box = [c for c in w.descendants(control_type="CheckBox") if c.element_info.automation_id == "othbcAt" + ho]
    if not box:
        raise Stop("공개제한근거 %s호 칸을 못 찾았습니다" % ho)
    if box[0].get_toggle_state() != 1:
        click_label(h, "%s호" % ho)
    box = [c for c in gian_window(h).descendants(control_type="CheckBox") if c.element_info.automation_id == "othbcAt" + ho]
    if box[0].get_toggle_state() != 1:
        raise Stop("공개제한근거 %s호에 체크가 안 됐습니다" % ho)
    if reason:
        e = [c for c in gian_window(h).descendants(control_type="Edit") if c.element_info.automation_id == "othbcLmttResn"]
        if e:
            e[0].click_input()
            paste(reason)


def set_disclosure(h, what, reason=""):
    if "(" in what:
        return set_partial(h, what, reason)
    if what not in DISCLOSURE:
        raise Stop("공개여부 '%s' 는 자동으로 고르지 않습니다 (공개·비공개·부분공개(6) 꼴)" % what)
    w = gian_window(h)
    texts = [c for c in w.descendants(control_type="Text") if (c.window_text() or "") == what]
    if not texts:
        raise Stop("공개여부 '%s' 글자를 못 찾았습니다" % what)
    t = min(texts, key=lambda c: c.rectangle().top).rectangle()    # 맨 위 줄이 문서정보의 공개여부 (아래는 첨부 줄)
    mouse.click(coords=(t.left + 7, (t.top + t.bottom) // 2))       # 라디오 자체는 크기가 0 이라 글자 왼쪽 끝
    time.sleep(1.0)
    for c in gian_window(h).descendants(control_type="RadioButton"):
        if c.element_info.automation_id == DISCLOSURE[what] and c.is_selected():
            return
    raise Stop("공개여부가 '%s' 로 안 골라졌습니다" % what)


def preset_value(w):
    cb = [c for c in w.descendants(control_type="ComboBox") if c.element_info.automation_id == "streReportCours"]
    if not cb:
        raise Stop("나의결재선 칸을 못 찾았습니다")
    return cb[0], (cb[0].legacy_properties().get("Value") or "")


def absent_notice():
    """결재선에 부재중인 결재자(출장 등)가 있으면 에듀파인이 «결재경로설정» 창 + «…부재중입니다» 알림을 저절로 띄운다.
    그 알림 글자를 돌려준다 (없으면 None). 창은 건드리지 않는다 — 이 창의 [삭제] 는 저장된 결재선을 지운다."""
    for m in windows("#32770", MSG_TITLE, wxs_pids()):
        t = msg_text(m)
        if "부재" in t:
            return t
    return None


def set_preset(h, name):
    """나의결재선 목록은 그림으로 떠서 글자를 못 읽는다 → 닫힌 채로 ↓ 를 눌러 한 칸씩 내려가며 값이 맞는지 본다."""
    cb, cur = preset_value(gian_window(h))
    if norm(cur) == norm(name):
        return
    r = cb.rectangle()
    mouse.click(coords=(r.left + 30, (r.top + r.bottom) // 2))      # 열리면서 포커스
    time.sleep(0.5)
    keyboard.send_keys("{ESC}")                                     # 닫고 포커스만 남긴다
    time.sleep(0.3)
    keyboard.send_keys("{HOME}")
    time.sleep(0.8)
    seen = []
    same = 0
    for _ in range(40):
        t = absent_notice()
        if t:          # 부재 알림이 뜨면 ↓ 가 그 창에 먹어서 엉뚱한 결재선이 골라질 수 있다 → 멈춘다 (2026-10-14 교감 출장일 실측)
            raise Stop("결재선을 고르다가 «부재중» 알림이 떴습니다: %s — "
                       "  결재자가 출장·휴가 중인 날은 자동으로 고르지 않습니다. 기안 창에서 직접 고르시거나 복귀 뒤 다시 해 주세요." % t[:120])
        _, cur = preset_value(gian_window(h))
        if norm(cur) == norm(name):
            time.sleep(2.0)                                         # 결재경로 표가 다시 그려질 시간
            t = absent_notice()
            if t:
                raise Stop("고른 결재선에 부재중인 결재자가 있습니다: %s — 기안 창에서 확인해 주세요" % t[:120])
            return
        if seen and cur == seen[-1]:
            same += 1                                               # ↓ 가 가끔 안 먹는다 (2026-10-06 실측) — 세 번 같아야 맨 아래
            if same >= 3:
                break
        else:
            same = 0
            seen.append(cur)
        keyboard.send_keys("{DOWN}")
        time.sleep(0.8)
    raise Stop("나의결재선에 '%s' 가 없습니다. 있는 것: %s" % (name, " / ".join(seen)))


def route_rows(h):
    """결재경로 표의 줄들 — [순번, 처리방법, 직위, 처리자, 상태, …]."""
    w = gian_window(h)
    ts = [(c.rectangle(), (c.window_text() or "").strip()) for c in w.descendants(control_type="Text")]
    head = [r.top for r, t in ts if t == "순번"]
    tail = [r.top for r, t in ts if t == "시행정보"]
    if not head or not tail:
        return []
    top, bottom = min(head) + 10, min(tail) - 5
    rows = {}
    for r, t in ts:
        if t and top < r.top < bottom and r.left < 760 and "결재경로표" not in t and t != "\xa0":
            rows.setdefault(r.top, []).append(t)
    return [rows[k] for k in sorted(rows) if len(rows[k]) >= 4]     # «수신자지정» 같은 단추 글자는 뺀다


# ── 결재올림 ─────────────────────────────────────────────────────
def submit(h, timeout=90):
    w = gian_window(h)
    btn = [c for c in w.descendants(control_type="Hyperlink") if c.element_info.automation_id == "sanctn"]
    if not btn:
        raise Stop("[결재올림] 단추를 못 찾았습니다")
    pids = wxs_pids()
    focus(h)
    mouse.click(coords=center(btn[0]))
    done = set()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        time.sleep(0.3)
        for m in windows("#32770", MSG_TITLE, pids):
            txt = msg_text(m)
            E.log("  알림: %s" % txt[:90])
            if "수신자를 지정하지 않으면 내부결재로 처리" in txt and "내부결재" not in done:
                done.add("내부결재"); press_msg(m); break
            if "원문공개 문서는 바로 국민에게 공개" in txt and "원문공개" not in done:
                done.add("원문공개"); press_msg(m); break
            if "정상적으로 처리되었습니다" in txt:
                press_msg(m)
                for _ in range(30):                         # 기안기가 스스로 닫힌다
                    if not win32gui.IsWindow(h):
                        break
                    time.sleep(0.3)
                return True
            shot(m, "품의_모르는알림.png")
            raise Stop("모르는 알림이라 누르지 않았습니다: %s" % txt[:150])
        for d in windows(IE_DLG, None, pids):
            t = win32gui.GetWindowText(d)
            if "문서처리" in t:
                if "문서처리" in done:
                    continue                                # 누른 창이 닫히는 중
                done.add("문서처리")
                time.sleep(0.8)
                shot(d, "품의_결재올림창.png")
                focus(d)
                rel_click(d, 712, 129, 1.0)                 # 「결재올림」 창 [확인] — 이 뒤로 [결재올림] 재클릭 금지
                E.log("  「결재올림」 창 [확인]")
                continue
            shot(d, "품의_모르는창.png")
            raise Stop("모르는 창이라 누르지 않았습니다: %s" % t)
    if "문서처리" in done:
        raise Stop("올리긴 했는데 %d초 안에 «정상적으로 처리» 를 못 봤습니다. "
                   "다시 누르지 말고 품의목록 상태를 봐 주세요 (두 번 올라갈 수 있습니다)" % timeout)
    raise Stop("%d초 동안 «결재올림» 창이 안 떴습니다 — 아직 안 올라갔습니다" % timeout)


def fill_and_submit(plan, wait_timeout=60):
    """기안기가 뜨기를 기다려 과제카드·공개여부·결재선을 채우고 [결재올림]. 결과 dict 를 돌려준다."""
    h = wait_gian(wait_timeout)
    if not h:
        raise Stop("기안기 창이 %d초 안에 안 떴습니다 (기안기 프로그램 Kedufine 이 깔려 있는지 보세요)" % wait_timeout)
    E.log("기안기 창이 떴습니다 — 과제카드·공개여부·결재선을 채웁니다")
    time.sleep(1.5)
    try:
        gian_window(h).maximize()
    except Exception:
        pass
    focus(h)
    got = set_card(h, plan["과제카드"])
    E.log("  과제카드: %s" % got)
    set_disclosure(h, plan["공개여부"])
    E.log("  공개여부: %s" % plan["공개여부"])
    set_preset(h, plan["결재선"])
    rows = route_rows(h)
    for r in rows:
        E.log("  결재경로: %s" % " | ".join(r[:5]))
    if len(rows) < 2:
        raise Stop("결재경로에 기안자 말고는 아무도 없습니다 — '%s' 결재선을 확인해 주세요" % plan["결재선"])
    shot(h, "품의_결재올림전.png")
    E.log("\n⚠️  [결재올림] 을 누릅니다")
    submit(h)
    return {"결재경로": [" ".join(r[:4]) for r in rows]}
