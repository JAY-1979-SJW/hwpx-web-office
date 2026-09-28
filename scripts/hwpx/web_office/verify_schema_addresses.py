"""파싱 검증 — 스키마의 paragraphId 가 실파일에서 실제로 풀리는가.

지시(2026-08-02, 대표님): "파싱하고 검증하고 단계별로 해야 하고"

역할 분담(단계 분리):
    rebuild_form_derivations_batch  파싱 → derivations_rebuild → forms.input_schema
    이 모듈                          검증 → schema_address_verification (읽기전용, forms 무수정)
    build_ai_interpretation_cache   AI 1차 해석 → ai_field_interpretation
    (같은 모듈) --verify             AI 2차 검증 → ai_field_verification

이 단계는 AI 가 아니라 **기계 대조**다. form_direct_fill 이 실제 기입 때
쓰는 것과 **같은 함수**로 좌표를 풀어본다(재구현 금지 — 2026-08-01 전수
조사도 이 원칙으로 370,505칸을 검증했다). 여기서 안 풀리면 그 스키마는
기입 단계에서도 반려되므로, AI 해석에 넘기기 전에 걸러내는 게 싸다.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts/hwpx"))

from hwpx_package import HwpxPackage  # ruff: ignore[module-import-not-at-top-of-file]
from hwpx_paragraph_ops import find_paragraph_in_cell, paragraph_runs  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.form_direct_fill import (  # ruff: ignore[module-import-not-at-top-of-file]
    _direct,
    _section_entry_by_number,
    _tables_in_root,
    parse_paragraph_id,
)

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
TABLE = "schema_address_verification"
FLUSH_EVERY = 200

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE}(
    form_id INTEGER PRIMARY KEY,
    status TEXT,
    total_cells INTEGER,
    ok_cells INTEGER,
    fail_cells INTEGER,
    fail_reasons TEXT,
    verdict TEXT,
    elapsed_sec REAL
);
"""
COLS = [
    "form_id",
    "status",
    "total_cells",
    "ok_cells",
    "fail_cells",
    "fail_reasons",
    "verdict",
    "elapsed_sec",
]

PASS_MIN_RATIO = 0.98  # 이 아래면 그 서식은 FAIL(전수 조사 실측 기준선)


def _log(m: str) -> None:
    print(m, flush=True)


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(CATALOG, timeout=120, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=120000")
    return con


def _flush(con: sqlite3.Connection, pending: list[dict], retries: int = 10) -> None:
    if not pending:
        return
    sql = f"INSERT OR REPLACE INTO {TABLE}({', '.join(COLS)}) VALUES({', '.join('?' * len(COLS))})"
    payload = [tuple(r.get(c) for c in COLS) for r in pending]
    for attempt in range(retries):
        try:
            con.execute("BEGIN IMMEDIATE")
            con.executemany(sql, payload)
            con.execute("COMMIT")
            pending.clear()
            return
        except sqlite3.OperationalError as e:
            try:
                con.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            if "locked" not in str(e).lower() and "busy" not in str(e).lower():
                raise
            time.sleep(0.4 * (attempt + 1))
    raise sqlite3.OperationalError("검증 스테이징 쓰기 실패 — 잠김")


def _resolve_one_field(
    f: dict, pkg, entry_by_sec: dict, tables_by_sec: dict[int, list | None], reasons: dict[str, int]
) -> bool:
    """스키마 1개 필드의 좌표를 해석. 실패 시 reasons 카운터를 올리고 False."""

    def _fail(reason: str) -> bool:
        reasons[reason] = reasons.get(reason, 0) + 1
        return False

    pid = f.get("paragraphId") or ""
    coord = parse_paragraph_id(pid)
    if coord is None:
        return _fail("PID_UNPARSEABLE")
    sec, tbl_i, row, col, p_i = coord
    if sec not in tables_by_sec:
        entry = entry_by_sec.get(sec)
        tables_by_sec[sec] = _tables_in_root(pkg.read_xml(entry)) if entry else None
    tbls = tables_by_sec[sec]
    if tbls is None or not 0 <= tbl_i < len(tbls):
        return _fail("TABLE_NOT_FOUND")
    rows = _direct(tbls[tbl_i], "tr")
    if not 0 <= row < len(rows):
        return _fail("ROW_NOT_FOUND")
    cols = _direct(rows[row], "tc")
    if not 0 <= col < len(cols):
        return _fail("CELL_NOT_FOUND")
    para = find_paragraph_in_cell(cols[col], p_i)
    if para is None:
        return _fail("PARAGRAPH_NOT_FOUND")
    if not paragraph_runs(para):
        return _fail("NO_RUN")
    return True


def verify_one(source_rel: str, schema: list[dict], *, project_root: Path = PROJECT_ROOT) -> dict:
    """스키마 1건의 좌표 해석 결과. 원본은 읽기만 한다."""
    src = project_root / source_rel
    if not src.is_file():
        return {
            "status": "SOURCE_MISSING",
            "total_cells": len(schema),
            "ok_cells": 0,
            "fail_cells": len(schema),
            "fail_reasons": "{}",
        }
    pkg = HwpxPackage(src)
    entry_by_sec = _section_entry_by_number(pkg)
    tables_by_sec: dict[int, list | None] = {}
    reasons: dict[str, int] = {}
    ok = sum(1 for f in schema if _resolve_one_field(f, pkg, entry_by_sec, tables_by_sec, reasons))
    total = len(schema)
    fail = total - ok
    ratio = ok / total if total else 1.0
    return {
        "status": "OK",
        "total_cells": total,
        "ok_cells": ok,
        "fail_cells": fail,
        "fail_reasons": json.dumps(reasons),
        "verdict": "PASS" if ratio >= PASS_MIN_RATIO else "FAIL",
    }


def run(limit: int = 0, shard: int = 0, shards: int = 1, scope: str | None = None) -> None:
    con = _connect()
    con.execute(DDL)
    done = {r[0] for r in con.execute(f"SELECT form_id FROM {TABLE}")}
    q = (
        "SELECT form_id, source_path, input_schema FROM forms"
        " WHERE input_schema IS NOT NULL AND input_schema != ''"
    )
    if scope:
        q += f" AND source_path LIKE '%{scope}%'"
    rows = con.execute(q + " ORDER BY form_id").fetchall()
    targets = [r for r in rows if r[0] not in done and (shards <= 1 or r[0] % shards == shard)]
    if limit:
        targets = targets[:limit]
    _log(f"검증 대상 {len(targets)}건 (shard {shard}/{shards})")

    pending: list[dict] = []
    t0 = time.time()
    for n, (form_id, source_path, schema_json) in enumerate(targets, 1):
        t1 = time.time()
        try:
            schema = json.loads(schema_json)
            r = verify_one(source_path, schema)
        except Exception as exc:  # ruff: ignore[blind-except]
            r = {"status": "ERROR", "fail_reasons": f"{type(exc).__name__}: {exc}"[:200]}
        r["form_id"] = form_id
        r["elapsed_sec"] = round(time.time() - t1, 2)
        pending.append(r)
        if len(pending) >= FLUSH_EVERY:
            _flush(con, pending)
            rate = (time.time() - t0) / n
            _log(f"[{n}/{len(targets)}] {rate * 1000:.0f}ms/건")
    _flush(con, pending)
    _log(f"완료 {len(targets)}건 / {time.time() - t0:.1f}s")
    con.close()


def status() -> None:
    con = _connect()
    con.execute(DDL)
    total = con.execute(
        "SELECT COUNT(*) FROM forms WHERE input_schema IS NOT NULL AND input_schema != ''"
    ).fetchone()[0]
    staged = con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    _log(f"파싱 완료 {total} · 검증 완료 {staged} ({staged / max(1, total) * 100:.1f}%)")
    for v, n in con.execute(
        f"SELECT COALESCE(verdict,status), COUNT(*) FROM {TABLE} GROUP BY COALESCE(verdict,status)"
    ):
        _log(f"  {v}: {n}")
    agg = con.execute(
        f"SELECT SUM(total_cells), SUM(ok_cells), SUM(fail_cells) FROM {TABLE} WHERE status='OK'"
    ).fetchone()
    if agg and agg[0]:
        tot, ok, fail = agg
        _log(f"  칸 {tot} · 해석성공 {ok} ({ok / tot * 100:.2f}%) · 실패 {fail}")
    con.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1)
    ap.add_argument("--scope", default=None, help="source_path 부분 일치 필터")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        status()
    else:
        run(limit=a.limit, shard=a.shard, shards=a.shards, scope=a.scope)


if __name__ == "__main__":
    main()
