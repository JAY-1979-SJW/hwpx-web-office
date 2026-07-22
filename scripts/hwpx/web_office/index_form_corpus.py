"""변환된 HWPX 코퍼스를 카탈로그에 색인 — 필드 추출 + 기관 도메인 태깅.

대상:
  law_hwpx/       법제처 법정서식 → institution = 소관부처(law_forms_index.jsonl)
  kepco_hwpx/     한국전력공사
  nhis_hwpx/      국민건강보험공단
  nps_hwpx/       국민연금공단
  comwel_hwpx/    근로복지공단
  lh_hwpx/        한국토지주택공사(LH)
  kogas_hwpx/     한국가스공사

각 HWPX를 파서로 로드 → 표/셀/빈칸 라벨(필드) 추출 → catalog.sqlite forms/fields 에 삽입.
- 재개 가능: source_path 이미 색인된 것 스킵.
- WAL 모드(색인 중 검색 허용). 진행 로그 stdout.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402
from scripts.hwpx.web_office.build_form_catalog import (  # noqa: E402
    form_type, statute_no, extract_fields,
)

LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
LIB_REL = "data/drafts/form_library"
CATALOG = LIB / "catalog.sqlite"
SIZE_CAP = 1.5 * 1024 * 1024

CORPORA = [
    # 공공기관 먼저(소규모·고가치 → 즉시 검색 가능), 법제처 대량은 마지막
    {"dir": "kodit_hwpx", "institution": "신용보증기금"},
    {"dir": "kosaf_hwpx", "institution": "한국장학재단"},
    {"dir": "kibo_hwpx", "institution": "기술보증기금"},
    {"dir": "hira_hwpx", "institution": "건강보험심사평가원"},
    {"dir": "cak_hwpx", "institution": "대한건설협회"},
    {"dir": "cu_hwpx", "institution": "신협중앙회"},
    {"dir": "kgs_hwpx", "institution": "한국가스안전공사"},
    {"dir": "kalis_hwpx", "institution": "국토안전관리원"},
    {"dir": "koelsa_hwpx", "institution": "한국승강기안전공단"},
    {"dir": "keco_hwpx", "institution": "한국환경공단"},
    {"dir": "kotsa_hwpx", "institution": "한국교통안전공단"},
    {"dir": "kinfa_hwpx", "institution": "서민금융진흥원"},
    {"dir": "hug_hwpx", "institution": "주택도시보증공사(HUG)"},
    {"dir": "hf_hwpx", "institution": "한국주택금융공사"},
    {"dir": "kamco_hwpx", "institution": "한국자산관리공사(캠코)"},
    {"dir": "ccrs_hwpx", "institution": "신용회복위원회"},
    {"dir": "ksure_hwpx", "institution": "한국무역보험공사"},
    {"dir": "kepco_hwpx", "institution": "한국전력공사"},
    {"dir": "nhis_hwpx", "institution": "국민건강보험공단"},
    {"dir": "nps_hwpx", "institution": "국민연금공단"},
    {"dir": "comwel_hwpx", "institution": "근로복지공단"},
    {"dir": "lh_hwpx", "institution": "한국토지주택공사(LH)"},
    {"dir": "kogas_hwpx", "institution": "한국가스공사"},
    {"dir": "law_hwpx", "index": "law_forms_index.jsonl", "inst_from_index": True},
]


def _log(m): print(m, flush=True)


def _ministry_map(index_path: Path) -> dict[str, str]:
    """법제처: seq → 소관부처명."""
    mp: dict[str, str] = {}
    if not index_path.exists():
        return mp
    for line in index_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        seq = str(r.get("seq") or "")
        if seq:
            mp[seq] = (r.get("ministry") or "").strip() or "기타부처"
    return mp


_SEQ = re.compile(r"^(\d+)_")


def index_corpus(con: sqlite3.Connection, cfg: dict) -> tuple[int, int, int]:
    src_dir = LIB / cfg["dir"]
    if not src_dir.is_dir():
        return 0, 0, 0
    files = sorted(src_dir.glob("*.hwpx"))
    mmap = _ministry_map(LIB / cfg["index"]) if cfg.get("inst_from_index") else {}
    fixed_inst = cfg.get("institution", "")

    done = {r[0] for r in con.execute(
        "SELECT source_path FROM forms WHERE source_path LIKE ?",
        (f"{LIB_REL}/{cfg['dir']}/%",))}

    ok = fail = skip = 0
    t0 = time.time()
    for i, f in enumerate(files, 1):
        rel = f"{LIB_REL}/{cfg['dir']}/{f.name}"
        if rel in done:
            skip += 1
            continue
        inst = fixed_inst
        if cfg.get("inst_from_index"):
            m = _SEQ.match(f.name)
            inst = mmap.get(m.group(1), "기타부처") if m else "기타부처"
        ft = form_type(f.name)
        sn = statute_no(f.name)
        try:
            if f.stat().st_size > SIZE_CAP:
                con.execute(
                    "INSERT INTO forms(form_type,statute_no,name,size_bytes,status,source_path,institution)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (ft, sn, f.name, f.stat().st_size, "SKIPPED_LARGE", rel, inst))
                skip += 1
                continue
            res = load_hwpx_for_editor(
                {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel}, project_root=PROJECT_ROOT)
            if res.get("verdict") != "PASS":
                con.execute(
                    "INSERT INTO forms(form_type,statute_no,name,size_bytes,status,source_path,institution)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (ft, sn, f.name, f.stat().st_size, "PARSE_FAIL", rel, inst))
                fail += 1
                continue
            dm = res.get("documentModel", {})
            rp = res.get("renderPayload", {})
            sm = res.get("summary", {})
            labels = extract_fields(dm, rp)
            cur = con.execute(
                "INSERT INTO forms(form_type,statute_no,name,size_bytes,table_count,cell_count,"
                "field_count,fingerprint,source_path,status,institution) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ft, sn, f.name, f.stat().st_size, sm.get("tables", 0), sm.get("cells", 0),
                 len(labels), dm.get("sourceDocumentHash", ""), rel, "OK", inst))
            fid = cur.lastrowid
            con.executemany("INSERT INTO fields(form_id,label) VALUES(?,?)",
                            [(fid, lab) for lab in labels])
            ok += 1
        except Exception as e:  # noqa: BLE001
            con.execute(
                "INSERT INTO forms(form_type,statute_no,name,size_bytes,status,source_path,institution)"
                " VALUES(?,?,?,?,?,?,?)",
                (ft, sn, f.name, f.stat().st_size, "ERROR:" + str(e)[:50], rel, inst))
            fail += 1
        if i % 200 == 0:
            con.commit()
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(files) - i) / rate / 60 if rate else 0
            _log(f"  [{cfg['dir']}] {i}/{len(files)} OK {ok} 실패 {fail} 스킵 {skip} "
                 f"[{el:.0f}s ~{rate:.1f}/s 남은 {eta:.0f}분]")
    con.commit()
    return ok, fail, skip


def main() -> None:
    con = sqlite3.connect(CATALOG)
    con.execute("PRAGMA journal_mode=WAL")
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    t0 = time.time()
    tot_ok = tot_fail = tot_skip = 0
    for cfg in CORPORA:
        if only and cfg["dir"] != only:
            continue
        _log(f"[corpus] {cfg['dir']} 색인 시작 …")
        ok, fail, skip = index_corpus(con, cfg)
        tot_ok += ok; tot_fail += fail; tot_skip += skip
        _log(f"[corpus] {cfg['dir']} 완료 — OK {ok} · 실패 {fail} · 스킵 {skip}")
    con.close()
    _log(f"[done] 전체 색인 OK {tot_ok} · 실패 {tot_fail} · 스킵 {tot_skip} · {(time.time()-t0)/60:.1f}분")


if __name__ == "__main__":
    main()
