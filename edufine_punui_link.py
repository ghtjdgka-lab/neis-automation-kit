# -*- coding: utf-8 -*-
"""구글 시트 [📮 품의 올리기] 링크 → 이 컴퓨터에서 에듀파인 품의를 올린다.

  .\\.venv\\Scripts\\python.exe -X utf8 edufine_punui_link.py 설치     edufine-punui:// 링크를 이 컴퓨터에 등록 (한 번만)
  .\\.venv\\Scripts\\python.exe -X utf8 edufine_punui_link.py 확인     등록됐는지 · 올린 기록 보기
  .\\.venv\\Scripts\\python.exe -X utf8 edufine_punui_link.py 지우기   등록 해제
  .\\.venv\\Scripts\\python.exe -X utf8 edufine_punui_link.py 시험 "<링크>"   링크만 풀어 보고 에듀파인은 안 연다

어떻게 이어지나:
  시트(앱스스크립트)는 구글 서버에서 돌아서 학교 컴퓨터의 에듀파인을 못 만진다.
  그래서 시트는 «주문서»만 만들어 링크 안에 담는다 → edufine-punui://run/<주문서>
  크롬에서 그 링크를 누르면 윈도우가 이 파일을 부르고, 이 파일이 edufine_punui.py 로 실제 입력을 한다.
  → 컴퓨터에 구글 로그인·토큰·웹앱이 필요 없다. 시트 주인이 누구든 같은 방식으로 된다.
  (조우열 연구위원님 «과학 물품 구매» 시트의 edufine-punui:// 방식을 따름. 그분은 숨은 탭에 주문서를 두고
   토큰으로 읽었고, 여기서는 링크에 담아 토큰을 없앴다)

안전장치 (두 번 올라가는 사고 막기):
  - 주문서마다 번호가 있고, 한 번 시작한 번호는 다시 안 돌린다 (%LOCALAPPDATA%\\neis-automation\\punui_link_done.json)
  - 미리보기 뒤 15분이 지난 링크는 안 돌린다 → 시트에서 메뉴를 다시 눌러 새 링크를 만든다
  - 업무포털이 바로 안 열리면(학교 밖) run_vpn.py 로 EVPN 을 붙였다가 끝나면 끊는다
"""
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import teacher_config

HERE = Path(__file__).resolve().parent
SCHEME = "edufine-punui"
KEY = r"Software\Classes\\" + SCHEME
DONE = teacher_config.CONFIG_DIR / "punui_link_done.json"
PLANS = teacher_config.CONFIG_DIR / "punui_link"
MAX_AGE_MIN = 15
SCOPE_ARGS = {"화면 채우기만": [], "저장까지": ["--저장"], "결재올림까지": ["--저장", "--결재요청"]}


def venv_python() -> str:
    p = HERE / ".venv" / "Scripts" / "python.exe"
    return str(p) if p.exists() else sys.executable


# ── 링크 등록 ───────────────────────────────────────────────
def install() -> int:
    import winreg
    cmd = '"%s" -X utf8 "%s" "%%1"' % (venv_python(), Path(__file__).resolve())
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY) as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "URL:에듀파인 품의 올리기")
        winreg.SetValueEx(k, "URL Protocol", 0, winreg.REG_SZ, "")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, KEY + r"\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    print("✅ 이 컴퓨터에 %s:// 링크를 등록했습니다 (지금 사용자만, 관리자 권한 필요 없음)" % SCHEME)
    print("   실행: " + cmd)
    print("   시트에서 [📮 품의 올리기] 를 누르면 크롬이 «열기» 를 묻습니다 → [열기]")
    return 0


def uninstall() -> int:
    import winreg
    for sub in (r"\shell\open\command", r"\shell\open", r"\shell", ""):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, KEY + sub)
        except FileNotFoundError:
            pass
    print("✅ %s:// 링크 등록을 지웠습니다" % SCHEME)
    return 0


def status() -> int:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY + r"\shell\open\command") as k:
            print("✅ 등록됨: " + winreg.QueryValueEx(k, "")[0])
    except Exception:
        print("❌ 등록 안 됨 — 설치 를 먼저 하세요")
    done = load_done()
    print("올린 기록 %d건" % len(done))
    for i, v in list(done.items())[-5:]:
        print("  %s  %s  %s  %s" % (i, v.get("시각", ""), v.get("상태", ""), v.get("품의번호", "")))
    print("RESULT_JSON=" + json.dumps({"등록": "확인", "기록": len(done)}, ensure_ascii=False))
    return 0


# ── 주문서 풀기 ─────────────────────────────────────────────
def decode(link: str) -> dict:
    m = re.match(r"^%s:/*run/([A-Za-z0-9_-]+)/?$" % SCHEME, link.strip())
    if not m:
        raise SystemExit("링크 모양이 다릅니다: %s…" % link[:60])
    raw = m.group(1)
    data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8"))
    if data.get("v") != 1 or not data.get("id") or not isinstance(data.get("plan"), dict):
        raise SystemExit("시트 버전이 이 프로그램과 맞지 않습니다 — 키트를 git pull 하거나 시트 사본을 새로 받으세요.")
    if data.get("범위") not in SCOPE_ARGS:
        raise SystemExit("올리기 범위가 이상합니다: %s" % data.get("범위"))
    return data


def load_done() -> dict:
    try:
        return json.loads(DONE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def mark(job_id: str, **kw) -> None:
    d = load_done()
    d.setdefault(job_id, {}).update(kw)
    DONE.parent.mkdir(parents=True, exist_ok=True)
    DONE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def show(data: dict) -> None:
    p = data["plan"]
    print("━" * 60)
    print("품의 주문서 %s  (올리기 범위: %s)" % (data["id"], data["범위"]))
    print("제목  " + p.get("제목", ""))
    print("예산  %s · 과제카드 %s · %s · 결재선 %s" % (p.get("예산"), p.get("과제카드") or "-",
                                                p.get("공개여부"), p.get("결재선") or "-"))
    tot = 0
    for it in p.get("품목", []):
        tot += it["수량"] * it["단가"]
        print("  · %s %s  %d개 × %s원" % (it["내용"], it.get("규격", ""), it["수량"], "{:,}".format(it["단가"])))
    print("합계  %s원" % "{:,}".format(tot))
    print("━" * 60)


def portal_direct() -> bool:
    """업무포털이 VPN 없이 열리면 학교 안이다."""
    import urllib.request
    import evpn
    try:
        return urllib.request.urlopen(evpn.portal_url(), timeout=8).status == 200
    except Exception:
        return False


def run(link: str, dry: bool = False) -> int:
    data = decode(link)
    show(data)
    job = data["id"]
    if dry:
        print("🧪 시험 — 링크를 풀어 보기만 했습니다. 에듀파인은 열지 않았습니다.")
        return 0

    age = (time.time() * 1000 - float(data.get("ts", 0))) / 60000
    if age > MAX_AGE_MIN:
        print("⛔ 미리보기를 띄운 지 %d분이 지났습니다. 시트에서 메뉴를 다시 눌러 새로 올려 주세요." % age)
        return 1
    prev = load_done().get(job)
    if prev:
        print("⛔ 이 주문서(%s)는 이미 %s 에 시작했습니다 (상태: %s). 두 번 올라가지 않게 멈춥니다."
              % (job, prev.get("시각"), prev.get("상태")))
        print("   다시 올려야 하면 에듀파인 품의목록을 먼저 보고, 시트에서 메뉴를 다시 눌러 새 링크로 올리세요.")
        return 1
    mark(job, 시각=datetime.now().strftime("%m-%d %H:%M"), 상태="진행중", 제목=data["plan"].get("제목"))

    PLANS.mkdir(parents=True, exist_ok=True)
    plan_file = PLANS / ("품의_%s.json" % job)
    plan_file.write_text(json.dumps(data["plan"], ensure_ascii=False, indent=1), encoding="utf-8")

    work = [venv_python(), "-X", "utf8", str(HERE / "edufine_punui.py"), "채우기", str(plan_file)] + SCOPE_ARGS[data["범위"]]
    if portal_direct():
        print("🏫 업무포털이 바로 열립니다 — VPN 없이 갑니다")
        cmd = work
    else:
        print("🌐 학교 밖입니다 — EVPN 을 붙였다가 끝나면 끊습니다 (2차 인증이 뜨면 직접 해 주세요)")
        cmd = [venv_python(), "-X", "utf8", str(HERE / "run_vpn.py"), "--minutes", "10", "--"] + work
    print("\n지금부터 몇 분 동안 창이 뜨고 마우스가 저절로 움직입니다.")
    print("그동안 마우스·키보드를 건드리지 말고 기다려 주세요.\n", flush=True)

    result = {}
    p = subprocess.Popen(cmd, cwd=str(HERE), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
    for line in p.stdout:
        print(line, end="", flush=True)
        if line.startswith("RESULT_JSON="):
            try:
                result = json.loads(line.split("=", 1)[1])
            except Exception:
                pass
    p.wait()

    num = result.get("품의번호", "")
    if result.get("결재요청") == "완료" or (data["범위"] == "저장까지" and result.get("저장") == "완료"):
        state = "✅"
    elif result.get("저장") in ("완료", "모름") or result.get("결재요청") in ("모름", "멈춤"):
        state = "⚠️"           # 저장은 됐을 수 있다 — 다시 돌리면 두 번 올라간다
    elif data["범위"] == "화면 채우기만" and result.get("채움"):
        state = "✅"
    else:
        state = "❌"
    mark(job, 상태=state, 품의번호=num, 결과=result)
    print("\n" + "━" * 60)
    if state == "✅":
        print("✅ 끝났습니다%s. 시트 «결과» 칸에 ✅ %s 를 적어 두세요." % (" — 품의번호 " + num if num else "", num))
    elif state == "⚠️":
        print("⚠️ 결과가 확실하지 않습니다%s. 다시 올리지 말고 에듀파인 품의목록부터 보세요." % (" (품의번호 " + num + ")" if num else ""))
    else:
        print("❌ 저장 전에 멈췄습니다: %s" % (result.get("이유") or result.get("오류") or "위 기록을 보세요"))
        print("   시트에서 고친 뒤 메뉴를 다시 누르면 새 링크로 다시 올릴 수 있습니다.")
    print("RESULT_JSON=" + json.dumps({"주문서": job, "상태": state, "품의번호": num}, ensure_ascii=False))
    return 0 if state == "✅" else 1


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    a = args[0]
    if a.startswith(SCHEME + ":"):
        try:
            code = run(a)
        except SystemExit as e:
            print("⛔ %s" % e)
            code = 1
        except Exception as e:
            print("❌ %s: %s" % (type(e).__name__, e))
            code = 1
        if os.environ.get("PUNUI_NO_PAUSE") != "1":
            input("\n엔터를 누르면 이 창이 닫힙니다…")
        return code
    if a == "설치":
        return install()
    if a == "지우기":
        return uninstall()
    if a == "확인":
        return status()
    if a == "시험" and len(args) > 1:
        return run(args[1], dry=True)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
