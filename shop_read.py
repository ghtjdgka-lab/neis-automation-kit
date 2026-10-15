# -*- coding: utf-8 -*-
"""쇼핑몰 상품 링크 → 품명·가격 (품의 품목 칸 채우기용). 로그인 없음, 읽기만.

  .\\.venv\\Scripts\\python.exe -X utf8 shop_read.py "<상품 링크>" ["<상품 링크>" …]
  .\\.venv\\Scripts\\python.exe -X utf8 shop_read.py --찾기 쿠팡 "우드락 5T"       검색 결과 첫 상품 링크만 보기
      (지마켓 검색 페이지는 «잠시만 기다리십시오» 403 으로 막힌다 — 상품 페이지·홈만 열린다, 2026-10-16)
  --headless   창 없이 (지마켓만 됨 — 쿠팡 상품은 403)

마지막 줄에 RESULT_JSON= 을 찍는다: [{링크, 몰, 품명, 할인가, 1개당가격, 응답코드, 초}]

왜 이렇게 띄우나 (docs/rules/에듀파인-품의.md «쇼핑몰 링크에서 품명·가격 읽기», 2026-09-11 실측):
  - playwright 가 띄운 크롬(headless)은 쿠팡·지마켓 둘 다 403
  - 이 컴퓨터의 «진짜 크롬»을 직접 띄우고 CDP 로 붙는다. 9/11엔 --headless=new + UA 덮기로 됐지만
    10/16엔 쿠팡 상품이 그 방식으로 403 → 지금은 화면 밖 창으로 띄운다(마우스·화면은 안 건드린다)
  - 쿠팡은 상품 페이지로 바로 가면 403 → 쿠팡 홈을 먼저 열고 간다
  - 쿠팡 가격은 «묶음 가격»과 «1개당 가격»이 같이 나온다 → 둘 다 돌려주고, 품의 단가를 어느 쪽으로 할지는 선생님께 묻는다
  - 끝나면 임시 프로필로 띄운 chrome.exe 를 모두 끈다(남은 헤드리스 크롬이 링크 열기를 망가뜨린 사고가 있었다)
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROMES = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
           r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
           os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
PROFILE_TAG = "shop_read_profile"

JS_GMARKET = r"""() => {
  const t = s => { const e = document.querySelector(s); return e ? e.innerText.trim() : ''; };
  let name = '';
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { const j = JSON.parse(s.textContent); const o = Array.isArray(j) ? j[0] : j; if (o && o.name) { name = o.name; break; } } catch (e) {}
  }
  return {name: name || t('h1.itemtit') || document.title, price: t('.price_real'), orig: t('.price_original')};
}"""

JS_COUPANG = r"""() => {
  const t = s => { const e = document.querySelector(s); return e ? e.innerText.trim() : ''; };
  const og = (document.querySelector('meta[property="og:title"]') || {}).content || '';
  const box = ['.price-container', '.prod-price', '.prod-price-container', '.total-price']
      .map(t).find(x => /원/.test(x)) || '';
  return {name: t('h1') || og, og: og, price: box, title: document.title};
}"""


def find_chrome():
    for c in CHROMES:
        if Path(c).exists():
            return c
    raise SystemExit("구글 크롬을 못 찾았습니다.")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def won(s):
    m = re.search(r"(\d{1,3}(?:,\d{3})+|\d+)\s*원", s or "")
    return int(m.group(1).replace(",", "")) if m else None


def mall(url):
    return "쿠팡" if "coupang.com" in url else "지마켓" if "gmarket.co.kr" in url else "기타"


def kill_profile(prof):
    """임시 프로필로 뜬 chrome.exe 를 모두 끈다 (윈도우)."""
    if os.name != "nt":
        return
    ps = ("Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
          "Where-Object { $_.CommandLine -like '*%s*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % PROFILE_TAG)
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True)


def count_profile():
    if os.name != "nt":
        return 0
    ps = ("(Get-CimInstance Win32_Process -Filter \"name='chrome.exe'\" | "
          "Where-Object { $_.CommandLine -like '*%s*' }).Count" % PROFILE_TAG)
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout.strip()
    return int(out or 0)


def read_one(page, url):
    t0 = time.time()
    m = mall(url)
    res = {"링크": url, "몰": m}
    if m == "쿠팡":
        page.goto("https://www.coupang.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)
    r = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    res["응답코드"] = r.status if r else None
    page.wait_for_timeout(3000)

    def ev(js):
        # 쿠팡은 열린 뒤 한 번 더 넘어갈 때가 있다 → «Execution context was destroyed» 면 기다렸다 다시
        for i in range(4):
            try:
                page.wait_for_load_state("domcontentloaded", timeout=15000)
                return page.evaluate(js)
            except Exception as e:
                if "context was destroyed" not in str(e) or i == 3:
                    raise
                page.wait_for_timeout(2000)

    if m == "지마켓":
        d = ev(JS_GMARKET)
        res.update({"품명": d["name"], "할인가": won(d["price"]), "정가": won(d["orig"]), "가격글자": d["price"]})
    elif m == "쿠팡":
        d = ev(JS_COUPANG)
        # h1 이 상품명 전체다. og:title 은 «[..., 1개 - 기타소품» 처럼 잘리고 분류가 붙는다 (10/16)
        name = (d["name"] if d["name"] and d["name"] != d["og"] else "") or re.sub(r"\s*\|\s*쿠팡\s*$", "", d["og"]).strip()
        unit = re.search(r"1\s*개당\s*([\d,]+)\s*원", d["price"])
        res.update({"품명": name, "할인가": won(d["price"]), "1개당가격": int(unit.group(1).replace(",", "")) if unit else None,
                    "가격글자": re.sub(r"\s+", " ", d["price"])[:120]})
    else:
        res.update({"품명": page.title(), "할인가": None})
    if (res["응답코드"] and res["응답코드"] >= 400) or "Access Denied" in (res.get("품명") or "") \
            or "기다리십시오" in (res.get("품명") or ""):
        res["막힘"] = True                         # 막힌 화면도 200 으로 올 때가 있다 — 제목으로도 본다
    res["초"] = round(time.time() - t0, 1)
    return res


def search_first(page, shop, q):
    if shop == "지마켓":
        page.goto("https://www.gmarket.co.kr/n/search?keyword=" + q, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        return page.evaluate("() => { const a = [...document.querySelectorAll('a[href*=\"item.gmarket.co.kr/Item\"]')][0]; return a ? a.href : ''; }")
    page.goto("https://www.coupang.com/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2500)
    page.goto("https://www.coupang.com/np/search?q=" + q, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    return page.evaluate("() => { const a = [...document.querySelectorAll('a[href*=\"/vp/products/\"]')][0]; return a ? a.href : ''; }")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    prof = Path(tempfile.gettempdir()) / PROFILE_TAG
    shutil.rmtree(prof, ignore_errors=True)
    port = free_port()
    # ★ 2026-10-16 실측: 쿠팡 상품 페이지는 --headless=new 로는 이제 403(Access Denied) — 홈은 200.
    #   창 있는 크롬을 화면 밖(-2400,-2400)에 띄우면 200. 지마켓은 둘 다 200. → 기본은 화면 밖 창
    headless = "--headless" in args
    args = [a for a in args if a != "--headless"]
    mode = ["--headless=new"] if headless else ["--window-position=-2400,-2400"]
    proc = subprocess.Popen([find_chrome(), *mode, "--remote-debugging-port=%d" % port,
                             "--user-data-dir=%s" % prof, "--no-first-run", "--no-default-browser-check",
                             "--window-size=1280,900", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    out = []
    try:
        with sync_playwright() as p:
            for _ in range(30):
                try:
                    br = p.chromium.connect_over_cdp("http://127.0.0.1:%d" % port)
                    break
                except Exception:
                    time.sleep(0.5)
            else:
                raise SystemExit("크롬에 붙지 못했습니다.")
            ctx = br.contexts[0]
            page = ctx.new_page()
            ua = page.evaluate("navigator.userAgent")
            if "HeadlessChrome" in ua:
                ctx.new_cdp_session(page).send("Network.setUserAgentOverride", {
                    "userAgent": ua.replace("HeadlessChrome", "Chrome"), "acceptLanguage": "ko-KR,ko;q=0.9"})
            if args[0] == "--찾기" and len(args) >= 3:
                link = search_first(page, args[1], args[2])
                print("첫 상품: %s" % (link or "(못 찾음)"))
                out = [{"찾기": args[1], "검색어": args[2], "링크": link}]
            else:
                for url in args:
                    try:
                        r = read_one(page, url)
                    except Exception as e:
                        r = {"링크": url, "몰": mall(url), "오류": str(e)[:200]}
                    out.append(r)
                    print("· %s %s | %s | 할인가 %s%s | %s초" % (
                        r.get("몰"), r.get("응답코드"), (r.get("품명") or "")[:60], r.get("할인가"),
                        " | 1개당 %s" % r["1개당가격"] if r.get("1개당가격") else "", r.get("초")), flush=True)
            br.close()
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except Exception:
            pass
        kill_profile(prof)
        time.sleep(1)
        left = count_profile()
        print("남은 임시 프로필 크롬: %d개" % left)
        shutil.rmtree(prof, ignore_errors=True)
    print("RESULT_JSON=" + json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
