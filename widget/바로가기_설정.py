# -*- coding: utf-8 -*-
"""바로가기 위젯 — 인증서 설정 (검은 창에서 한 번만).

  .\\.venv\\Scripts\\python.exe widget\\바로가기_설정.py

묻는 것은 여섯: ① 지역(나이스 주소) ② 인증서 이름(C:\\GPKI\\Certificate\\class2 에서 찾아 보여 준다)
③ 인증서 암호(화면에 안 보인다 — 별표도 안 찍히는 게 정상) ④ 출근 시각(복무 지각 시작 기본값)
⑤ 퇴근 시각(복무 조퇴 종료 기본값) — 둘 다 학교마다 다르다 ⑥ 연락처(선택). 암호는 파일이 아니라 Windows 자격 증명 관리자에만 들어간다.
출결·복무 자동화(setup_wizard.py)와 «같은 설정»을 쓰므로, 그쪽을 이미 했으면 이걸 또 할 필요가 없다.
"""
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT))

import keyring  # noqa: E402
import teacher_config  # noqa: E402
from setup_wizard import REGION_CODES, gpki_names, to_neis_url  # noqa: E402


def ask(label, default=""):
    suffix = " [%s]" % default if default else ""
    return input("%s%s: " % (label, suffix)).strip() or default


def load_old():
    """기존 설정. 파일이 깨져 있으면(저장 중 꺼짐 등) 빈 설정으로 시작한다 — 저장하면 새로 써진다."""
    try:
        if teacher_config.CONFIG_FILE.exists():
            data = json.loads(teacher_config.CONFIG_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def save_settings(neis_url, cert_name, pw, work_start, work_end, contact=""):
    """검은 창(main)과 설정 창(바로가기_설정창.pyw)이 같이 쓴다. 암호는 자격 증명 관리자에만."""
    if pw:
        keyring.set_password(teacher_config.KEYRING_SERVICE, cert_name, pw)
    cfg = {**load_old(), "neis_url": neis_url, "cert_name": cert_name, "work_start": work_start, "work_end": work_end}
    # 복무 스크립트(main_bokmu.py)는 출결용 항목이 «있기만» 하면 된다 — 설정 마법사도 담임이 아니면 비워 둔다 (10/16 실측: 없으면 ConfigMissingError)
    for k, v in (("grade", ""), ("class", ""), ("calendars", {})):
        cfg.setdefault(k, v)
    cfg["contact"] = contact            # 비우고 저장하면 지워진다
    region = ""
    for name, code in __import__("setup_wizard").REGION_CODES.items():
        if "//%s.neis" % code in neis_url:
            region = name
    if region:
        cfg["region"] = region          # 에듀파인 주소(klef.<지역>.go.kr)는 이걸로 정한다
    teacher_config.save_config(cfg)
    return cfg


def main():
    print("=" * 56)
    print("  바로가기 위젯 — 인증서 설정")
    print("=" * 56)
    old = load_old()
    if old:
        print("\n(기존 설정을 찾았습니다. 그대로 두려면 그냥 Enter)")

    print("\n── 1. 지역 ──  (서울이면 그냥 Enter. 아니면 아래 이름 중 하나를 치세요)")
    print("   " + " · ".join(REGION_CODES))
    while True:
        neis_url = to_neis_url(ask("지역", old.get("neis_url", teacher_config.DEFAULTS["neis_url"])))
        if re.match(r"https://[a-z]+\.neis\.go\.kr/", neis_url):
            break
        print("   ⚠️ 모르는 지역입니다. 위 목록의 이름(예: 경기)으로 다시 쳐 주세요.")

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

    def ask_time(label, default):
        while True:
            v = ask(label, default)
            if re.fullmatch(r"\d{1,2}:\d{2}", v):
                return v
            print("   %s 처럼 적어 주세요." % default)
    print("\n── 4. 출근 시각 ──  (위젯 [복무]에서 지각 시작 시각의 기본값. 학교마다 달라요. 예: 08:30 / 08:40)")
    work_start = ask_time("출근 시각", old.get("work_start", "08:40"))
    print("\n── 5. 퇴근 시각 ──  (위젯 [복무]에서 조퇴 종료 시각의 기본값. 학교마다 달라요. 예: 16:20 / 16:30)")
    work_end = ask_time("퇴근 시각", old.get("work_end", "16:20"))
    print("\n── 6. 연락처 ──  (복무 상신 때 적히는 휴대폰 번호. 안 쓰면 그냥 Enter)")
    contact = ask("연락처 (예: 010-1234-5678)", old.get("contact", ""))

    save_settings(neis_url, cert_name, pw, work_start, work_end, contact)

    print("\n✅ 저장했습니다.")
    print("   나이스 주소   " + neis_url)
    print("   인증서 이름   " + cert_name[:1] + "*" * (len(cert_name) - 1))
    print("   인증서 암호   Windows 자격 증명 관리자에 저장됨 (파일엔 없음)")
    print("   출근·퇴근     " + work_start + " ~ " + work_end + (" · 연락처 " + contact if contact else ""))

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


def known_folder(guid):
    """윈도우가 실제로 쓰는 폴더 위치 (SHGetKnownFolderPath). 못 구하면 None."""
    try:
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]
        u = uuid.UUID(guid)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        path = out.value
        ctypes.windll.ole32.CoTaskMemFree(out)
        return Path(path)
    except Exception:
        return None


def make_shortcuts():
    pyw = Path(sys.executable).with_name("pythonw.exe")
    target = HERE / "바로가기위젯.pyw"
    # 학교 PC는 바탕화면이 OneDrive(«OneDrive - ○○학교\바탕 화면»)로 옮겨져 있는 일이 많다 — %USERPROFILE%\Desktop 을 쓰면 안 보이는 곳에 만든다
    desktop = known_folder("{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}") or Path(os.environ["USERPROFILE"]) / "Desktop"
    startup = known_folder("{B97D20BB-F46A-4C97-BA10-5E3608430854}") or         Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
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
