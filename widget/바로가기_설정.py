# -*- coding: utf-8 -*-
"""바로가기 위젯 — 인증서 설정 (검은 창에서 한 번만).

  .\\.venv\\Scripts\\python.exe widget\\바로가기_설정.py

묻는 것은 셋뿐이다: ① 지역(나이스 주소) ② 인증서 이름(C:\\GPKI\\Certificate\\class2 에서 찾아 보여 준다)
③ 인증서 암호(화면에 안 보인다 — 별표도 안 찍히는 게 정상). 암호는 파일이 아니라 Windows 자격 증명 관리자에만 들어간다.
출결·복무 자동화(setup_wizard.py)와 «같은 설정»을 쓰므로, 그쪽을 이미 했으면 이걸 또 할 필요가 없다.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT))

import keyring  # noqa: E402
import teacher_config  # noqa: E402
from setup_wizard import gpki_names, to_neis_url  # noqa: E402


def ask(label, default=""):
    suffix = " [%s]" % default if default else ""
    return input("%s%s: " % (label, suffix)).strip() or default


def main():
    print("=" * 56)
    print("  바로가기 위젯 — 인증서 설정")
    print("=" * 56)
    old = {}
    if teacher_config.CONFIG_FILE.exists():
        old = json.loads(teacher_config.CONFIG_FILE.read_text(encoding="utf-8"))
        print("\n(기존 설정을 찾았습니다. 그대로 두려면 그냥 Enter)")

    print("\n── 1. 지역 ──  (서울이면 그냥 Enter. 경기·부산처럼 지역 이름만 치면 됩니다)")
    neis_url = to_neis_url(ask("지역 또는 나이스 주소", old.get("neis_url", teacher_config.DEFAULTS["neis_url"])))

    print("\n── 2. 교육행정 인증서 이름 ──")
    names = gpki_names()
    if names:
        print("   이 컴퓨터에서 찾은 인증서: " + ", ".join(names))
    else:
        print("   ⚠️ C:\\GPKI\\Certificate\\class2 에 인증서 파일이 없습니다. 평소 나이스가 되던 컴퓨터인지 확인하세요.")
    cert_name = ask("인증서 이름 (나이스 로그인 창에 뜨는 이름)", old.get("cert_name") or (names[0] if names else ""))
    if not cert_name:
        print("❌ 인증서 이름이 비어 있습니다.")
        sys.exit(1)

    print("\n── 3. 인증서 암호 ──  (화면에 아무것도 안 보이는 게 정상입니다. 치고 Enter)")
    pw = teacher_config.secret_input("인증서 암호: ")
    if not pw:
        print("❌ 암호가 비어 있습니다.")
        sys.exit(1)
    keyring.set_password(teacher_config.KEYRING_SERVICE, cert_name, pw)

    cfg = {**old, "neis_url": neis_url, "cert_name": cert_name}
    region = ""
    for name, code in __import__("setup_wizard").REGION_CODES.items():
        if "//%s.neis" % code in neis_url:
            region = name
    if region:
        cfg["region"] = region          # 에듀파인 주소(klef.<지역>.go.kr)는 이걸로 정한다
    teacher_config.save_config(cfg)

    print("\n✅ 저장했습니다.")
    print("   나이스 주소   " + neis_url)
    print("   인증서 이름   " + cert_name[:1] + "*" * (len(cert_name) - 1))
    print("   인증서 암호   Windows 자격 증명 관리자에 저장됨 (파일엔 없음)")

    # 바탕화면 바로가기 + 로그인할 때 자동 시작
    try:
        make_shortcuts()
    except Exception as e:
        print("   (바로가기 만들기는 건너뜀: %s)" % str(e)[:80])
    print("\n이제 바탕화면의 «나이스 에듀파인 바로가기» 를 더블클릭하면 위젯이 뜹니다.")
    try:
        input("\n닫으려면 Enter...")
    except EOFError:
        pass


def make_shortcuts():
    pyw = Path(sys.executable).with_name("pythonw.exe")
    target = HERE / "바로가기위젯.pyw"
    desktop = Path(os.path.join(os.environ["USERPROFILE"], "Desktop"))
    startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    ps = []
    for folder in (desktop, startup):
        if not folder.exists():
            continue
        lnk = folder / "나이스 에듀파인 바로가기.lnk"
        ps.append('$s=(New-Object -ComObject WScript.Shell).CreateShortcut("%s"); $s.TargetPath="%s"; '
                  '$s.Arguments=\'"%s"\'; $s.WorkingDirectory="%s"; $s.IconLocation="%s,0"; $s.Save()'
                  % (lnk, pyw, target, HERE, pyw))
    if ps:
        import subprocess
        subprocess.run(["powershell", "-NoProfile", "-Command", "; ".join(ps)], check=True, capture_output=True)
        print("   바탕화면·시작프로그램에 «나이스 에듀파인 바로가기» 를 만들었습니다 (로그인하면 저절로 뜹니다).")


if __name__ == "__main__":
    main()
