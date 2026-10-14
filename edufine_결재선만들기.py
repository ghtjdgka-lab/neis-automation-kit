# -*- coding: utf-8 -*-
"""K-에듀파인 «나의결재선» 을 규정대로 만들어 저장한다 (결재경로설정 창 자동).

  .\\.venv\\Scripts\\python.exe -X utf8 edufine_결재선만들기.py 결재선.json            만들고 저장
  .\\.venv\\Scripts\\python.exe -X utf8 edufine_결재선만들기.py 결재선.json --미리보기  넣기만 하고 저장 안 함(캡처)
  .\\.venv\\Scripts\\python.exe -X utf8 edufine_결재선만들기.py 결재선.json --갱신      같은 이름이 있으면 새 내용으로 바꿈
  .\\.venv\\Scripts\\python.exe -X utf8 edufine_결재선만들기.py "결재선 이름" --확인    저장된 결재선의 결재경로 읽기만

결재선.json (학교 «위임 전결 규정» 표를 클로드가 읽어 만든다. 예시: 예시_결재선.json):
  [
    {"이름": "예산 30만원 미만",
     "결재자": [                                  ← 아래(첫 결재자)부터 위(마지막 결재자) 순서
        {"성명": "홍길동", "직위": "부장교사"},
        {"직위": "행정실장"},                      ← 성명을 비우면 조직도에서 그 직위를 찾는다 (교장·교감·행정실장)
        {"직위": "교감", "처리": "전결"}],         ← 맨 위 사람의 처리: 결재(기본) · 전결
    }
  ]
  가운데 사람은 에듀파인이 «검토» 로 넣는다.

★ 저장된 결재선을 지우는 [삭제] 는 절대 누르지 않는다. 같은 이름이 이미 있으면 --갱신 을 줄 때만 바꾸고, 아니면 멈춘다.
★ 결재자가 부재중이면(출장 등) «부재자 결재선» 창에서 «부재자가 복귀 후 결재처리» 를 고른다.
  대리결재자가 이미 경로에 있으면 «동일한 사용자» 로 막히므로, 위쪽(마지막) 결재자부터 넣고 순서를 뒤집는다.
★ 기안 창은 저장하지 않고 닫는다. 마지막 줄에 RESULT_JSON=
"""
import json
import sys
import time
from pathlib import Path

import edufine_common as E
import edufine_gian as G
import edufine_결재선목록 as L
from edufine_gian import Stop, keyboard, mouse, win32con, win32gui
from pywinauto import Desktop

TREE_DEPT = {"교장": "교장", "교감": "교감", "행정실장": "행정실"}


# ── 결재경로설정 창 ──────────────────────────────────────────────
class Route:
    def __init__(self, h):
        self.h = h
        self.D = Desktop(backend="uia").window(handle=h)
        try:
            G.focus(h)                                       # 기안 창 뒤에 깔리면 좌표 클릭이 기안 창에 떨어진다
        except Exception:
            pass

    def els(self, ctype=None, text=None, aid=None):
        out = []
        for c in self.D.descendants(control_type=ctype) if ctype else self.D.descendants():
            if text is not None and (c.window_text() or "").strip() != text:
                continue
            if aid is not None and c.element_info.automation_id != aid:
                continue
            out.append(c)
        return out

    def click(self, c, dx=0, wait=0.8):
        r = c.rectangle()
        mouse.click(coords=((r.left + r.right) // 2 + dx, (r.top + r.bottom) // 2))
        time.sleep(wait)

    # 결재경로 표 — 처리방법 콤보 기준으로 줄을 읽는다 (위 = 마지막 결재자)
    def combos(self):
        return [c for c in self.D.descendants(control_type="ComboBox")
                if c.element_info.automation_id.startswith("draft")]       # 화면 밖 줄(보통 맨 아래 기안)은 칸이 0 — 값은 읽힌다

    def row_of(self, cb):
        r = cb.rectangle()
        mid = (r.top + r.bottom) // 2
        return [t for rr, t in sorted(((c.rectangle(), (c.window_text() or "").strip())
                                       for c in self.D.descendants(control_type="Text")), key=lambda x: x[0].left)
                if t and rr.top - 6 <= mid <= rr.bottom + 6 and rr.left > r.left - 700]

    def rows(self):
        """[(콤보aid, 처리방법, 처리자 글자)] 위에서 아래로."""
        out = []
        for cb in sorted(self.combos(), key=lambda c: c.rectangle().top or 10 ** 6):
            who = [t for t in self.row_of(cb) if "(" in t and "*" in t]
            out.append((cb.element_info.automation_id, cb.legacy_properties().get("Value"), who[0] if who else ""))
        return out

    def set_method(self, aid, want):
        def cur():
            return [c for c in self.combos() if c.element_info.automation_id == aid][0]
        self.click(cur()); keyboard.send_keys("{ESC}"); time.sleep(0.3)
        keyboard.send_keys("{HOME}"); time.sleep(0.7)
        for _ in range(6):
            if cur().legacy_properties().get("Value") == want:
                return True
            keyboard.send_keys("{DOWN}"); time.sleep(0.7)
        return False

    def select_row(self, name):
        _, _, _, dlg_bottom = win32gui.GetWindowRect(self.h)
        for _ in range(6):                                   # 창 아래로 잘린 줄이면 창 안을 굴려서 보이게
            cb = [c for c in self.combos() if any(t.startswith(name + "(") for t in self.row_of(c))]
            if not cb:
                raise Stop("결재경로 표에서 %s 줄을 못 찾았습니다" % name)
            r = cb[0].rectangle()
            if r.bottom and r.bottom < dlg_bottom - 25:
                break
            mouse.scroll(coords=(r.left if r.left else 900, dlg_bottom - 120), wheel_dist=-3)
            time.sleep(0.8)
        r = cb[0].rectangle()
        mouse.click(coords=(r.left - 150, (r.top + r.bottom) // 2))      # 같은 줄 직위 칸
        time.sleep(0.6)

    def userlist(self):
        t = self.els("Table", aid="orgnztUserList")
        return [] if not t else t[0].descendants(control_type="RadioButton")

    def tree_names(self, dept):
        """조직도에서 부서를 눌러 그 부서 사람 «이름(직위)» 목록."""
        def nodes():
            return [c for c in self.D.descendants(control_type="Group")
                    if "frmPartOrgTree" in c.element_info.automation_id and (c.window_text() or "").strip().endswith(" " + dept)]
        g = nodes()
        for _ in range(3):                                   # 학교 줄을 펼친다 — 한 번에 안 펼쳐질 때가 있다
            if g:
                break
            imgs = [c for c in self.D.descendants(control_type="Image")
                    if "frmPartOrgTree" in c.element_info.automation_id and c.element_info.automation_id.endswith("Img")]
            if imgs:
                self.click(imgs[0], wait=1.0)
            for _ in range(10):
                time.sleep(0.5)
                g = nodes()
                if g:
                    break
        if not g:
            raise Stop("조직도에 «%s» 부서가 없습니다" % dept)
        before = [(r.window_text() or "").strip() for r in self.userlist()]
        self.click(g[0], wait=1.0)
        names = []
        for _ in range(16):                                  # 오른쪽 표가 그 부서로 바뀔 때까지 (늦게 그려진다)
            names = [(r.window_text() or "").strip() for r in self.userlist()]
            if names and names != before:
                break
            time.sleep(0.5)
        return names

    def resolve(self, who):
        if who.get("성명"):
            return who["성명"], who["직위"]
        dept = TREE_DEPT.get(who["직위"])
        if not dept:
            raise Stop("«%s» 는 성명을 같이 적어 주세요 (조직도에서 자동으로 찾는 건 교장·교감·행정실장뿐)" % who["직위"])
        cand = [n for n in self.tree_names(dept) if n.endswith("(%s)" % who["직위"])]
        if len(cand) != 1:
            raise Stop("조직도 «%s» 에서 %s 를 하나로 못 정했습니다: %s" % (dept, who["직위"], cand))
        return cand[0].split("(")[0], who["직위"]

    def search_add(self, name, role):
        ed = self.els("Edit", aid="userNm")[0]
        self.click(ed); G.paste(name); time.sleep(0.3)
        q = [c for c in self.els("Hyperlink", text="조회") if c.rectangle().left > ed.rectangle().right]
        self.click(q[0], wait=2.5)
        rb = [r for r in self.userlist() if (r.window_text() or "").strip().startswith("%s(%s)" % (name, role))]
        if len(rb) != 1:
            raise Stop("%s(%s) 를 하나로 못 골랐습니다: %s" % (name, role, [r.window_text() for r in self.userlist()]))
        self.click(rb[0], wait=0.4)
        self.click(self.els("Image", aid="btnAdd")[0], wait=2.5)
        return self.absent()

    def absent(self):
        """부재자 결재선 창이 뜨면 «부재자가 복귀 후 결재처리» → [확인]. 부재였으면 부재 정보를 돌려준다."""
        ab = G.windows(G.IE_DLG, "부재자", G.wxs_pids())
        if not ab:
            return None
        A = Desktop(backend="uia").window(handle=ab[0])
        info = [(c.window_text() or "").strip() for c in A.descendants(control_type="Text")][:14]
        rb = [c for c in A.descendants(control_type="RadioButton")
              if (c.window_text() or "").strip() == "부재자가 복귀 후 결재처리"]
        if not rb:
            raise Stop("부재자 창에 «부재자가 복귀 후 결재처리» 가 없습니다")
        rb[0].select()
        time.sleep(0.6)
        ok = [c for c in A.descendants(control_type="Hyperlink") if (c.window_text() or "").strip() == "확인"][0]
        self.click(ok, wait=2.0)
        ms = [(m, G.msg_text(m)) for m in G.windows("#32770", G.MSG_TITLE, G.wxs_pids())]
        if ms:
            raise Stop("부재자 창 [확인] 뒤 알림: %s" % " / ".join(t for _, t in ms))
        return " ".join(info)

    def remove_all_but_draft(self):
        """기안자(맨 아래 줄) 말고 다 뺀다. 기안자 혼자면 처리방법이 «전결» 로 보인다 — 본인은 못 지운다."""
        for _ in range(10):
            rs = self.rows()
            if len(rs) <= 1:
                return
            others = [w for aid, v, w in rs if v != "기안" and w]
            if not others:
                return
            self.select_row(others[0].split("(")[0])
            self.click(self.els("Image", aid="btnDel")[0], wait=1.5)

    def order(self):
        """위→아래 처리자 이름 (기안 제외)."""
        return [w.split("(")[0] for aid, v, w in self.rows() if v != "기안" and w]

    def move(self, name, up):
        self.select_row(name)
        self.click(self.els("Image", aid="btnUp" if up else "btnDown")[0], wait=1.2)

    def reorder(self, want_top_down):
        for _ in range(30):
            cur = self.order()
            if cur == want_top_down:
                return
            for i, n in enumerate(want_top_down):           # 위에서부터 첫 어긋난 자리에 와야 할 사람을 올린다
                if cur[i] != n:
                    self.move(n, up=True)
                    break
        raise Stop("결재 순서를 못 맞췄습니다: %s" % self.order())

    def save(self, name, update=False):
        cb = self.els("ComboBox", aid="streReportCours")[0]
        ed = self.els("Edit", aid="streReportCoursEdit")[0]
        self.click(ed); G.paste(name); time.sleep(0.4)
        self.click(self.els("Hyperlink", aid="myapprSave")[0], wait=2.0)
        log = []
        for _ in range(4):
            ms = [(m, G.msg_text(m)) for m in G.windows("#32770", G.MSG_TITLE, G.wxs_pids())]
            if not ms:
                break
            for m, t in ms:
                log.append(t)
                if "저장하시겠습니까" in t or "저장되었습니다" in t or "갱신되었습니다" in t:
                    G.press_msg(m, "확인")
                elif "갱신하시겠습니까" in t and update:          # --갱신 을 준 때만 같은 이름을 새 내용으로 바꾼다
                    G.press_msg(m, "확인")
                elif "이미" in t or "덮어" in t or "존재" in t:
                    G.press_msg(m, "취소") if win32gui.FindWindowEx(m, 0, "Button", "취소") else G.press_msg(m, "확인")
                    raise Stop("같은 이름의 결재선이 이미 있어 저장하지 않았습니다: %s" % t)
                else:
                    raise Stop("저장 때 모르는 알림: %s" % t)
                time.sleep(1.2)
        if not any("저장되었습니다" in t or "갱신되었습니다" in t for t in log):
            raise Stop("«결재선이 저장되었습니다» 를 못 봤습니다: %s" % log)
        return log

    def close(self):
        if not win32gui.IsWindow(self.h) or not win32gui.IsWindowVisible(self.h):
            return
        c = [x for x in self.D.descendants() if (x.window_text() or "").strip() == "닫기"
             and x.element_info.control_type in ("Image", "Hyperlink")]
        if c:
            self.click(c[0], wait=1.5)
        for m in G.windows("#32770", G.MSG_TITLE, G.wxs_pids()):
            G.press_msg(m, "확인")


def open_route(h):
    w = G.gian_window(h)
    b = [c for c in w.descendants() if (c.window_text() or "").strip() == "결재경로지정"]
    if not b:
        raise Stop("기안 창에서 [결재경로지정] 을 못 찾았습니다")
    r = b[0].rectangle()
    mouse.click(coords=((r.left + r.right) // 2, (r.top + r.bottom) // 2))
    for _ in range(30):
        time.sleep(0.5)
        d = G.windows(G.IE_DLG, "결재경로설정", G.wxs_pids())
        if d:
            time.sleep(1.5)
            return Route(d[0])
    raise Stop("결재경로설정 창이 안 떴습니다")


def pick_preset(h, name):
    """기안 창 «나의결재선» 에서 name 을 고른다 — 부재 알림이 떠도 닫고 계속 (키트 set_preset 은 여기서 멈췄다)."""
    G.focus(h)
    cb, cur = G.preset_value(G.gian_window(h))
    r = cb.rectangle()
    mouse.click(coords=(r.left + 30, (r.top + r.bottom) // 2)); time.sleep(0.5)
    keyboard.send_keys("{ESC}"); time.sleep(0.3); keyboard.send_keys("{HOME}"); time.sleep(2.0)
    seen, same = [], 0
    for _ in range(60):
        if L.handle_absent():
            L.refocus_preset(h)
        _, cur = G.preset_value(G.gian_window(h))
        if cur.strip() == name:
            time.sleep(2.0)
            if L.handle_absent():
                pass
            return True
        if seen and cur == seen[-1]:
            same += 1
            if same >= 3:
                break
        else:
            same = 0
            seen.append(cur)
        keyboard.send_keys("{DOWN}"); time.sleep(0.9)
    raise Stop("나의결재선에 «%s» 가 없습니다. 본 것: %s" % (name, " / ".join(seen)))


def build(R, spec, preview, update=False):
    R.remove_all_but_draft()
    people = [R.resolve(w) for w in spec["결재자"]]                    # 아래→위
    absent = {}
    for (name, role) in reversed(people):                                # 위(마지막 결재자)부터 넣는다
        a = R.search_add(name, role)
        if a:
            absent[name] = a
        E.log("  + %s(%s)%s" % (name, role, "  ⚠️ 부재중 → 복귀 후 결재처리" if a else ""))
    want = [n for n, _ in reversed(people)]                               # 위→아래
    R.reorder(want)
    top = R.rows()[0]
    method = spec["결재자"][-1].get("처리", "결재")
    if top[1] != method and not R.set_method(top[0], method):
        raise Stop("맨 위 처리방법을 «%s» 로 못 바꿨습니다" % method)
    got = [(v, w) for _, v, w in R.rows()]
    E.log("  결재경로(위→아래): " + " / ".join("%s %s" % (w, v) for v, w in got))
    if [w.split("(")[0] for v, w in got if v != "기안" and w] != want:
        raise Stop("넣은 순서가 다릅니다: %s" % got)
    saved = None if preview else R.save(spec["이름"], update)
    return {"이름": spec["이름"], "결재경로": ["%s %s" % (w, v) for v, w in got], "부재중": list(absent), "저장": bool(saved)}


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    preview = "--미리보기" in sys.argv
    check = "--확인" in sys.argv                 # --확인 «결재선 이름»  : 저장된 결재선을 골라 결재경로를 읽기만
    if not a:
        raise SystemExit("결재선.json 경로(또는 --확인 결재선이름)를 주세요")
    specs = [] if check else json.loads(Path(a[0]).read_text(encoding="utf-8-sig"))
    L.open_form()
    L.clear_autosave(10)
    hs = L.form_hwnds()
    if len(hs) != 1:
        raise Stop("기안 창이 %d개입니다" % len(hs))
    h = hs[0]
    win32gui.ShowWindow(h, win32con.SW_MAXIMIZE)
    time.sleep(2)
    L.clear_autosave(3)
    done = []
    try:
        if check:
            pick_preset(h, a[0])
            R = open_route(h)
            try:
                for m in G.windows("#32770", G.MSG_TITLE, G.wxs_pids()):     # 창 안의 부재 알림만 닫는다 (창 자체는 두고)
                    if "부재" in G.msg_text(m):
                        G.press_msg(m, "확인")
                time.sleep(1.0)
                got = ["%s %s" % (w, v) for _, v, w in R.rows()]
                E.log("  «%s» 결재경로(위→아래): %s" % (a[0], " / ".join(got)))
                done.append({"이름": a[0], "결재경로": got})
            finally:
                R.close()
        for spec in specs:
            E.log("\n📝 «%s» 만드는 중%s" % (spec["이름"], " (미리보기 — 저장 안 함)" if preview else ""))
            R = open_route(h)
            try:
                done.append(build(R, spec, preview, "--갱신" in sys.argv))
                E.log("  ✅ %s" % ("저장했습니다" if not preview else "넣기까지 됐습니다 (저장 안 함)"))
            finally:
                R.close()
                L.handle_absent()
    finally:
        L.handle_absent()
        closed = L.close_without_save(h)
    print("RESULT_JSON=" + json.dumps({"할일": "결재선만들기", "결과": done, "기안창닫힘": closed}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Stop as e:
        E.log("⛔ %s" % e)
        print("RESULT_JSON=" + json.dumps({"할일": "결재선만들기", "멈춤": str(e)[:300]}, ensure_ascii=False))
        sys.exit(1)
