"""나이스 교육정보 개방 포털(open.neis.go.kr)에서 우리 학교 학사일정을 읽어 휴업일을 찾는다.

키 없이 된다. 다만 키 없이 부르면 한 번에 5줄까지만 돌려주고 쪽 넘기기(pIndex)도 무시된다
(2026-10-16 실측) — 그래서 기간으로 한꺼번에 묻지 않고 «하루씩» 묻는다. 하루에 일정이 5개를 넘는 날은 없다.
휴업일 = 그날 일정 중 수업공제일 구분(SBTR_DD_SC_NM)이 «휴업일» 또는 «공휴일»인 것이 하나라도 있으면.
(재량휴업일 · 방학 · 공휴일 · 토요휴업일이 여기에 든다)
"""
import json
import urllib.parse
import urllib.request
from datetime import date

HUB = "https://open.neis.go.kr/hub/"

# 나이스 주소 앞글자 → 교육청 코드 (17개 모두 2026-10-16 schoolInfo 로 확인)
OFFICE_BY_NEIS = {
    "sen": "B10", "pen": "C10", "dge": "D10", "ice": "E10", "gen": "F10",
    "dje": "G10", "use": "H10", "sje": "I10", "goe": "J10", "gwe": "K10",
    "cbe": "M10", "cne": "N10", "jbe": "P10", "jne": "Q10", "gbe": "R10",
    "gne": "S10", "jje": "T10",
}


def _get(service: str, **params) -> list:
    url = HUB + service + "?" + urllib.parse.urlencode({"Type": "json", **params})
    req = urllib.request.Request(url, headers={"User-Agent": "neis-automation-kit"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode("utf-8"))
    block = data.get(service)
    if not block:
        return []   # INFO-200 = 해당 자료 없음
    return block[1].get("row", [])


def office_from_neis_url(neis_url: str) -> str:
    host = urllib.parse.urlsplit(neis_url).netloc.split(".")[0]
    return OFFICE_BY_NEIS.get(host, "")


def find_school(name: str, office: str = "") -> list:
    """학교 이름(일부도 됨)으로 찾는다. [{office, code, name, office_name, addr}]"""
    params = {"SCHUL_NM": name.strip()}
    if office:
        params["ATPT_OFCDC_SC_CODE"] = office
    return [{
        "office": r["ATPT_OFCDC_SC_CODE"], "code": r["SD_SCHUL_CODE"], "name": r["SCHUL_NM"],
        "office_name": r["ATPT_OFCDC_SC_NM"], "addr": (r.get("ORG_RDNMA") or "").strip(),
    } for r in _get("schoolInfo", **params)]


def is_holiday(office: str, code: str, d: date) -> bool:
    rows = _get("SchoolSchedule", ATPT_OFCDC_SC_CODE=office, SD_SCHUL_CODE=code,
                AA_YMD=d.strftime("%Y%m%d"))
    return any(r.get("SBTR_DD_SC_NM") in ("휴업일", "공휴일") for r in rows)


def holidays_among(office: str, code: str, dates) -> set:
    """주어진 날짜들 가운데 우리 학교 휴업일만 골라 돌려준다. 조회가 안 되면 예외를 그대로 올린다."""
    return {d for d in sorted(set(dates)) if d.weekday() < 5 and is_holiday(office, code, d)}
