"""카탈로그 서식명 복구 — 모지바케(latin-1 오독) 파일명을 원본 한글로 되돌린다.

원인: http.client 가 HTTP 헤더를 latin-1 로 디코드한다. 서버가 UTF-8 파일명을
퍼센트인코딩 없이 Content-Disposition 에 실어 보내면 수집 당시 모지바케가 되고,
파일명 정제(_safe)에서 한글이 아닌 문자가 '_' 로 치환되며 이름이 뭉개졌다.

데이터 손실은 없다 — 각 기관 인덱스(*_forms_index.jsonl)의 `name` 필드에
모지바케 원문이 그대로 남아 있어 `encode('latin-1').decode('utf-8')` 로 복구된다.

동작: 인덱스의 (file → name) 을 복구해 카탈로그 forms.name 을 갱신.
      HWPX 산출물명은 `{원본stem}.hwpx` 또는 `{stem}_{크기}.hwpx` 형태이므로
      원본 파일 stem 으로 매칭한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
CATALOG = LIB / "catalog.sqlite"
KO = re.compile(r"[가-힣]")


def demojibake(s: str, rounds: int = 3) -> str:
    """latin-1 오독 되돌리기. 이중/삼중 인코딩도 있어 한글이 나올 때까지 반복."""
    cur = s or ""
    for _ in range(rounds):
        if not cur or KO.search(cur):
            return cur
        try:
            nxt = cur.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return cur
        if nxt == cur:
            return cur
        cur = nxt
    return cur


def index_name_map(inst_code: str) -> dict[str, str]:
    """{저장파일 stem: 복구된 원본명} — 인덱스에서 추출."""
    idx = LIB / f"{inst_code}_forms_index.jsonl"
    out: dict[str, str] = {}
    if not idx.exists():
        return out
    for line in idx.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        fname, name = r.get("file"), r.get("name")
        if not fname or not name:
            continue
        fixed = demojibake(name)
        if not KO.search(fixed):
            continue
        out[Path(fname).stem] = Path(fixed).stem
    return out


def kgs_name_map() -> dict[str, str]:
    """가스안전공사 특례: 수집 시 Content-Disposition 이 없어 이름이 'kgs_N' 으로
    저장됐다. 정적 경로(/asset/file/{한글명}.hwp)에 원본명이 있으므로 목록
    페이지에서 순서대로 되살린다(수집기와 동일한 추출 순서)."""
    import urllib.error
    import urllib.parse
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://www.kgs.or.kr/kgs/aceb/tab.do", headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            txt = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}
    seen, names = set(), []
    for path in re.findall(r"/asset/file/\S+?\.hwpx?", txt):
        if path in seen:
            continue
        seen.add(path)
        names.append(urllib.parse.unquote(Path(path).name))
    # 수집기는 1부터 순번을 붙였다: {i}_kgs_{i}
    return {f"{i}_kgs_{i}": Path(n).stem for i, n in enumerate(names, 1)}


def hug_name_map(max_pages: int = 10) -> dict[str, str]:
    """주택도시보증공사 특례: 저장 파일명이 서버 경로명(35045_attachfile2_1)이라
    한글이 없다. 서식자료실 목록의 downLoad.jsp 링크에 표시명(onm)이 있으므로
    snm(base64 경로)의 파일명과 짝지어 되살린다.
    주의: 페이지는 EUC-KR, onm 은 CP949 퍼센트인코딩이다."""
    import base64
    import binascii
    import urllib.error
    import urllib.parse
    import urllib.request

    base = "https://www.khug.or.kr/hug/web/cs/cl/cscl000003.jsp"
    out: dict[str, str] = {}
    for pg in range(1, max_pages + 1):
        try:
            req = urllib.request.Request(
                f"{base}?gotoPage={pg}", headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                txt = r.read().decode("euc-kr", "replace")
        except (urllib.error.URLError, TimeoutError, OSError):
            break
        links = re.findall(r"downLoad\.jsp\?[^\"'>]*", txt)
        if not links:
            break
        before = len(out)
        for l in links:
            q = urllib.parse.parse_qs(urllib.parse.urlparse("?" + l.split("?", 1)[1]).query)
            onm, snm = q.get("onm", [""])[0], q.get("snm", [""])[0]
            if not onm or not snm:
                continue
            try:
                path = urllib.parse.unquote(base64.b64decode(snm).decode("utf-8", "replace"))
                name = urllib.parse.unquote(onm, encoding="cp949", errors="strict")
            except (binascii.Error, UnicodeDecodeError, UnicodeEncodeError, ValueError):
                continue
            key = Path(path).stem  # 예: 35045_attachfile2_1
            if key and KO.search(name):
                out[key] = Path(name).stem
        if len(out) == before:
            break
    return out


def _repair_one_row(r, nmap: dict, con: sqlite3.Connection, dry_run: bool) -> bool:
    cur = r["name"] or ""
    if KO.search(cur):
        return False  # 이미 정상
    stem = re.sub(r"\.hwpx?$", "", cur, flags=re.I)
    # 전체 stem 우선 조회. 없을 때만 변환기 중복 접미(_크기)를 떼고 재시도
    # (먼저 떼면 '10_kgs_10' 같은 정상 stem 이 '10_kgs' 로 망가진다)
    # 조회 후보: 전체 stem → 순번접두 제거 → 변환기 중복접미 제거
    # (먼저 접미를 떼면 '10_kgs_10' 같은 정상 stem 이 망가진다)
    cands = [
        stem,
        re.sub(r"^\d+_", "", stem),
        re.sub(r"_\d+$", "", stem),
        re.sub(r"_\d+$", "", re.sub(r"^\d+_", "", stem)),
    ]
    new = next((nmap[c] for c in cands if c in nmap), None)
    if not new:
        return False
    if not dry_run:
        con.execute("UPDATE forms SET name=? WHERE form_id=?", (new + ".hwpx", r["form_id"]))
    return True


def repair(inst_codes: list[str], *, dry_run: bool = False) -> dict:
    con = sqlite3.connect(CATALOG)
    con.row_factory = sqlite3.Row
    total_fixed = 0
    per_inst: dict[str, int] = {}
    for code in inst_codes:
        nmap = index_name_map(code)
        if code == "kgs":
            nmap = {**nmap, **kgs_name_map()}
        if code == "hug":
            nmap = {**nmap, **hug_name_map()}
        if not nmap:
            continue
        rows = con.execute(
            "SELECT form_id, name, source_path FROM forms WHERE source_path LIKE ?",
            (f"%/{code}_hwpx/%",),
        ).fetchall()
        fixed = sum(1 for r in rows if _repair_one_row(r, nmap, con, dry_run))
        if fixed:
            per_inst[code] = fixed
            total_fixed += fixed
    if not dry_run:
        con.commit()
    con.close()
    return {"totalFixed": total_fixed, "perInstitution": per_inst, "dryRun": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--institutions",
        default="nhis,nps,comwel,lh,kogas,kodit,"
        "kosaf,hira,kibo,cak,cu,kgs,kalis,koelsa,keco,kotsa,kinfa,"
        "hug,hf,kamco,ccrs,ksure,kepco",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    codes = [c.strip() for c in args.institutions.split(",") if c.strip()]
    res = repair(codes, dry_run=args.dry_run)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
