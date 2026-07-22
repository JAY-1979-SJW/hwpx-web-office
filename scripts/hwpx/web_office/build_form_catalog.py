"""서식 카탈로그 빌더 — 로컬 라이브러리 8,338종을 전부 파싱해 지식베이스(SQLite) 구축.

하이브리드 배포(로컬 처리)에 맞춰 로컬 SQLite 카탈로그를 만든다.
각 서식: 종류·필드 라벨·표 구조·구조지문을 추출해 저장.

용도: 사용자가 서식을 업로드하면 이 카탈로그와 대조해
      "이 서식이 무엇이고 어느 칸에 뭐가 들어가는지"를 즉시 안다.

- 거대 문서(>1.5MB, 0.5%)는 크기로 사전 제외(파싱 폭주 방지, 별도 플래그).
- 고유 서식 종류(정규화 파일명)당 대표 1개만 파싱.
- 진행 상황을 stdout에 실시간 출력.
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

LIB = PROJECT_ROOT / "data" / "drafts" / "form_library"
LIB_REL = "data/drafts/form_library"   # 브릿지는 project-relative sourcePath 요구
MANIFEST = LIB / "manifest.json"
CATALOG = LIB / "catalog.sqlite"
SIZE_CAP = 1.5 * 1024 * 1024   # 1.5MB 초과 = 거대 문서 사전 제외


def _log(m): print(m, flush=True)


def form_type(name: str) -> str:
    n = re.sub(r"\.hwpx?$", "", name, flags=re.I)
    n = re.sub(r"^[0-9a-f]{10}_", "", n)       # 수집 해시 접두
    n = re.sub(r"^\d{3,6}_\d{1,4}_", "", n)     # 데모 번호 접두
    n = re.sub(r"__(A|B|filled)$", "", n)       # 변형 접미
    n = re.sub(r"\(\d+\)", "", n)               # 번호 괄호
    return n.strip()


_BEONJI = re.compile(r"별지[\s_]*제?[\s_]*(\d+)호(?:의[\s_]*\d+)?[\s_]*서식")
_BEOLPYO = re.compile(r"별표[\s_]*(\d+)")
def statute_no(name: str) -> str:
    n = name.replace("_", " ")   # 언더스코어 → 공백 정규화
    m = _BEONJI.search(n)
    if m:
        return "별지 제" + m.group(0).split("제", 1)[-1].strip()
    m = _BEOLPYO.search(n)
    if m:
        return "별표 " + m.group(1)
    return ""


def cell_label(cells_by_rc: dict, cell: dict) -> str:
    r, c = cell["row"], cell["col"]
    for cc in range(c - 1, -1, -1):
        lc = cells_by_rc.get((r, cc))
        if lc and (lc.get("text") or "").strip():
            return lc["text"].strip()
    for rr in range(r - 1, -1, -1):
        uc = cells_by_rc.get((rr, c))
        if uc and (uc.get("text") or "").strip():
            return uc["text"].strip()
    return ""


def extract_fields(doc_model: dict, render_payload: dict) -> list[str]:
    """빈 입력칸의 라벨 목록(= 이 서식이 받는 필드)."""
    paras = doc_model.get("paragraphs", [])
    # cell scope 빈 문단 → (tableIndex,row,col)
    empty_cells = set()
    for p in paras:
        cs = p.get("containerScope") or {}
        if cs.get("kind") != "cell":
            continue
        txt = "".join(x.get("text", "") for x in p.get("runs", [])).strip()
        if not txt:
            empty_cells.add((cs.get("tableIndex"), cs.get("rowIndex"), cs.get("colIndex")))
    labels: list[str] = []
    seen = set()
    for ti, t in enumerate(render_payload.get("tables", [])):
        by_rc = {(c["row"], c["col"]): c for c in t.get("cells", [])}
        for c in t.get("cells", []):
            if c.get("isCoveredByMerge"):
                continue
            if (ti, c["row"], c["col"]) in empty_cells:
                lab = cell_label(by_rc, c)
                if lab and lab not in seen:
                    seen.add(lab)
                    labels.append(lab)
    return labels


def init_db(con):
    # WAL 모드 — 빌드 중에도 동시 읽기(검색) 허용
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS forms(
        form_id INTEGER PRIMARY KEY AUTOINCREMENT,
        form_type TEXT, statute_no TEXT, name TEXT, sha256 TEXT,
        size_bytes INTEGER, table_count INTEGER, cell_count INTEGER,
        field_count INTEGER, fingerprint TEXT, source_path TEXT, status TEXT);
    CREATE TABLE IF NOT EXISTS fields(
        form_id INTEGER, label TEXT);
    CREATE INDEX IF NOT EXISTS idx_forms_type ON forms(form_type);
    CREATE INDEX IF NOT EXISTS idx_forms_statute ON forms(statute_no);
    CREATE INDEX IF NOT EXISTS idx_fields_label ON fields(label);
    """)


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 0
    mani = json.loads(MANIFEST.read_text(encoding="utf-8"))
    # 고유 서식 종류당 대표 1개(HWPX만)
    reps: dict[str, dict] = {}
    for r in mani["records"]:
        if r["ext"] != "hwpx":
            continue
        t = form_type(r["name"])
        if t and t not in reps:
            reps[t] = r
    targets = list(reps.values())
    if limit:
        targets = targets[:limit]
    _log(f"[catalog] 고유 서식 종류 {len(targets)}개 파싱 시작 (거대 문서>1.5MB 제외)")

    CATALOG.unlink(missing_ok=True)
    con = sqlite3.connect(CATALOG)
    init_db(con)

    t0 = time.time()
    ok = skipped_big = failed = 0
    for i, r in enumerate(targets, 1):
        src = LIB / (r.get("collectedAs") or "")
        ft = form_type(r["name"])
        sn = statute_no(r["name"])
        if r["sizeBytes"] > SIZE_CAP or not src.exists():
            skipped_big += 1
            con.execute("INSERT INTO forms(form_type,statute_no,name,sha256,size_bytes,status,source_path)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (ft, sn, r["name"], r["sha256"], r["sizeBytes"], "SKIPPED_LARGE", r["sourcePath"]))
            continue
        try:
            rel_src = f"{LIB_REL}/{r['collectedAs']}"   # project-relative
            res = load_hwpx_for_editor({"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel_src},
                                       project_root=PROJECT_ROOT)
            if res.get("verdict") != "PASS":
                failed += 1
                con.execute("INSERT INTO forms(form_type,statute_no,name,sha256,size_bytes,status,source_path)"
                            " VALUES(?,?,?,?,?,?,?)",
                            (ft, sn, r["name"], r["sha256"], r["sizeBytes"], "PARSE_FAIL", r["sourcePath"]))
                continue
            dm = res.get("documentModel", {})
            rp = res.get("renderPayload", {})
            sm = res.get("summary", {})
            labels = extract_fields(dm, rp)
            cur = con.execute(
                "INSERT INTO forms(form_type,statute_no,name,sha256,size_bytes,table_count,cell_count,"
                "field_count,fingerprint,source_path,status) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (ft, sn, r["name"], r["sha256"], r["sizeBytes"], sm.get("tables", 0),
                 sm.get("cells", 0), len(labels), dm.get("sourceDocumentHash", ""),
                 r["sourcePath"], "OK"))
            fid = cur.lastrowid
            con.executemany("INSERT INTO fields(form_id,label) VALUES(?,?)",
                            [(fid, lab) for lab in labels])
            ok += 1
        except Exception as e:
            failed += 1
            con.execute("INSERT INTO forms(form_type,statute_no,name,sha256,size_bytes,status,source_path)"
                        " VALUES(?,?,?,?,?,?,?)",
                        (ft, sn, r["name"], r["sha256"], r["sizeBytes"], "ERROR:" + str(e)[:60], r["sourcePath"]))
        if i % 100 == 0:
            con.commit()
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(targets) - i) / rate / 60 if rate else 0
            _log(f"  … {i}/{len(targets)} (OK {ok}, 실패 {failed}, 대형 {skipped_big}) "
                 f"[{el:.0f}s, ~{rate:.1f}/s, 남은 {eta:.0f}분]")
    con.commit()
    con.close()
    el = time.time() - t0
    _log(f"[done] 총 {len(targets)}개 · OK {ok} · 실패 {failed} · 대형제외 {skipped_big} · {el/60:.1f}분")
    _log(f"[catalog] {CATALOG}")


if __name__ == "__main__":
    main()
