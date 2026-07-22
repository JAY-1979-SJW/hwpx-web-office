"""서식 전량 해부 배치 — 카탈로그의 모든 서식에서 행정 요건을 추출·저장.

각 서식 HWPX 를 파싱해 form_requirements.extract_requirements 로
  첨부서류 · 처리기간 · 수수료 · 근거법령 · 제출처 · 입력칸
을 뽑아 catalog.sqlite 의 forms 테이블에 적재한다.

- 재개 가능: req_status 가 채워진 행은 건너뛴다.
- WAL 모드 — 해부 중에도 검색 가능.
- 진행 상황 stdout.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402
from scripts.hwpx.web_office.form_requirements import extract_requirements  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"

COLUMNS = [
    ("attachments", "TEXT"),          # JSON 배열
    ("attachment_count", "INTEGER"),
    ("processing_time", "TEXT"),
    ("fee", "TEXT"),
    ("legal_basis", "TEXT"),          # JSON 배열
    ("submit_to", "TEXT"),
    ("req_status", "TEXT"),           # OK / FAIL:<사유>
]


def _log(m: str) -> None:
    print(m, flush=True)


def ensure_schema(con: sqlite3.Connection) -> None:
    have = {r[1] for r in con.execute("PRAGMA table_info(forms)")}
    for name, typ in COLUMNS:
        if name not in have:
            con.execute(f"ALTER TABLE forms ADD COLUMN {name} {typ}")
    con.commit()


def run(limit: int = 0, size_cap_mb: float = 1.5) -> None:
    con = sqlite3.connect(CATALOG)
    con.execute("PRAGMA journal_mode=WAL")
    ensure_schema(con)
    rows = con.execute(
        "SELECT form_id, source_path FROM forms "
        "WHERE status='OK' AND (req_status IS NULL OR req_status='') "
        "ORDER BY form_id"
    ).fetchall()
    if limit:
        rows = rows[:limit]
    _log(f"[start] 해부 대상 {len(rows):,}종 (재개형 — 완료분 제외)")

    t0 = time.time()
    ok = fail = skip = 0
    agg_attach = agg_fee = agg_time = agg_law = agg_to = 0
    cap = size_cap_mb * 1024 * 1024
    for i, (fid, rel) in enumerate(rows, 1):
        # 프로젝트 밖 절대경로(구 로컬 수집분)는 로더가 §4 정책으로 거부한다 → 스킵
        if not rel or Path(rel).is_absolute() or rel.startswith(("/", "\\")):
            con.execute("UPDATE forms SET req_status=? WHERE form_id=?",
                        ("SKIP_OUTSIDE_PROJECT", fid))
            skip += 1
            continue
        src = PROJECT_ROOT / rel
        try:
            if not src.is_file() or src.stat().st_size > cap:
                con.execute("UPDATE forms SET req_status=? WHERE form_id=?",
                            ("SKIP_SIZE_OR_MISSING", fid))
                skip += 1
                continue
            res = load_hwpx_for_editor(
                {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
                project_root=PROJECT_ROOT)
            if res.get("verdict") != "PASS":
                con.execute("UPDATE forms SET req_status=? WHERE form_id=?",
                            ("FAIL:PARSE", fid))
                fail += 1
                continue
            r = extract_requirements(res["documentModel"], res["renderPayload"])
            con.execute(
                "UPDATE forms SET attachments=?, attachment_count=?, processing_time=?,"
                " fee=?, legal_basis=?, submit_to=?, req_status='OK' WHERE form_id=?",
                (json.dumps(r["attachments"], ensure_ascii=False),
                 r["attachmentCount"], r["processingTime"], r["fee"],
                 json.dumps(r["legalBasis"], ensure_ascii=False),
                 r["submitTo"], fid))
            ok += 1
            agg_attach += 1 if r["attachments"] else 0
            agg_fee += 1 if r["fee"] else 0
            agg_time += 1 if r["processingTime"] else 0
            agg_law += 1 if r["legalBasis"] else 0
            agg_to += 1 if r["submitTo"] else 0
        except Exception as e:  # noqa: BLE001
            con.execute("UPDATE forms SET req_status=? WHERE form_id=?",
                        (f"FAIL:{type(e).__name__}", fid))
            fail += 1
        if i % 500 == 0:
            con.commit()
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(rows) - i) / rate / 60 if rate else 0
            _log(f"  … {i:,}/{len(rows):,} OK {ok:,} 실패 {fail} 스킵 {skip} "
                 f"[{el:.0f}s ~{rate:.1f}/s 남은 {eta:.0f}분] "
                 f"첨부 {agg_attach:,} 수수료 {agg_fee:,} 기간 {agg_time:,}")
    con.commit()
    con.close()
    el = time.time() - t0
    _log(f"[done] OK {ok:,} · 실패 {fail} · 스킵 {skip} · {el/60:.1f}분")
    _log(f"[추출] 첨부서류 {agg_attach:,} · 수수료 {agg_fee:,} · 처리기간 {agg_time:,} · "
         f"근거법령 {agg_law:,} · 제출처 {agg_to:,}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--size-cap-mb", type=float, default=1.5)
    args = ap.parse_args()
    run(args.limit, args.size_cap_mb)


if __name__ == "__main__":
    main()
