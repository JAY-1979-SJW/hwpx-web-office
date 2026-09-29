"""파생 산출물 통합 재생성 — HWPX 한 번만 열어 셋을 함께 채운다.

왜 필요한가
-----------
`3f94c2a` 이전의 `table_parser._cell_raw_text` 는 `elem.text` 만 읽어
`<hp:fwSpace/>` 같은 인라인 자식 **뒤에 오는 글자(child.tail)를 버렸다.**

    <hp:t>(서명<hp:fwSpace/>또는<hp:fwSpace/></hp:t>  →  '(서명'

    '(서명 또는 인)'                        → '(서명인)'
    '[]천장재[]단열재[]지붕재…'              → '[][][]'
    '건축법 시행령」제15조'                   → '건축법제15조'

또 중첩 표 내용이 바깥 셀에 중복으로 딸려 들어왔다. 실측(표본 300건·셀
51,404개): 텍스트가 바뀐 셀 440개(0.9%)지만 **영향 파일은 150/300(절반)**,
그중 내용이 있는데 빈칸으로 오인된 칸 15개, `isLikelyInputSlot` 판정이
뒤집힌 칸 76개, `isLikelyLabel` 53개.

이 텍스트를 먹고 만들어진 파생 산출물이 전부 낡았다:
  ① 입력 스키마(라벨·역할·의미·subject)
  ② 행정 요건(첨부서류·처리기간·수수료·근거법령·제출처)
  ③ 라벨 색인(fields) + field_count → 이것을 먹는 doc_type/fillable 까지

셋 다 같은 HWPX 를 다시 연다. 따로 돌리면 파싱을 3번 한다 — 여기서는
**한 번 열어 셋을 함께** 만든다.

안전 설계
---------
- 기존 `forms` / `fields` 를 **건드리지 않는다.** 스테이징 테이블
  `derivations_rebuild` 에만 쌓는다. 도중에 끊겨도 현재 카탈로그는 온전하다.
- 재개 가능 — 이미 쌓인 form_id 는 건너뛴다.
- **100건마다 커밋** (기존 배치는 500건 주기라, 남은 482건을 돌릴 때
  3.5시간 작업이 통째로 미커밋 상태로 떠 있었다. 같은 실수를 반복하지 않는다.)
- 반영은 별도 단계: `--promote` 를 줘야 `forms`/`fields` 에 옮긴다.
  옮기기 전에 커버리지를 검사하고, 미달이면 거부한다.

사용
----
    python scripts/hwpx/web_office/rebuild_form_derivations_batch.py
    python scripts/hwpx/web_office/rebuild_form_derivations_batch.py --status
    python scripts/hwpx/web_office/rebuild_form_derivations_batch.py --promote
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

from scripts.hwpx.web_office.build_form_catalog import extract_fields  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.form_field_roles import _subject_of  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.form_input_schema import build_input_schema  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.form_requirements import extract_requirements  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.form_taxonomy import classify_document  # ruff: ignore[module-import-not-at-top-of-file]

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"

STAGING = "derivations_rebuild"
COMMIT_EVERY = 100

DDL = f"""
CREATE TABLE IF NOT EXISTS {STAGING}(
    form_id INTEGER PRIMARY KEY,
    rebuild_status TEXT,
    field_count INTEGER,
    labels TEXT,
    doc_type TEXT,
    fillable INTEGER,
    clean_name TEXT,
    doc_reason TEXT,
    form_kind TEXT,
    input_schema TEXT,
    input_count INTEGER,
    applicant_count INTEGER,
    office_count INTEGER,
    sensitive_count INTEGER,
    schema_status TEXT,
    attachments TEXT,
    attachment_count INTEGER,
    processing_time TEXT,
    fee TEXT,
    legal_basis TEXT,
    submit_to TEXT,
    req_status TEXT
);
"""


def _log(m: str) -> None:
    print(m, flush=True)


STAGING_COLS = [
    "form_id",
    "rebuild_status",
    "field_count",
    "labels",
    "doc_type",
    "fillable",
    "clean_name",
    "doc_reason",
    "form_kind",
    "input_schema",
    "input_count",
    "applicant_count",
    "office_count",
    "sensitive_count",
    "schema_status",
    "attachments",
    "attachment_count",
    "processing_time",
    "fee",
    "legal_basis",
    "submit_to",
    "req_status",
]


def _connect() -> sqlite3.Connection:
    # isolation_level=None → 자동 트랜잭션 없음. 쓰기 잠금을 잡는 시점을
    # 우리가 직접 정한다(_flush 참조). 기본값이면 첫 INSERT 에서 트랜잭션이
    # 열려 커밋까지 유지되는데, 그 사이에 파싱이 끼면 워커 하나가 쓰기
    # 잠금을 수 분씩 붙든다 — 샤드 병렬 실행이 전부 'database is locked'
    # 로 죽은 실제 원인이었다.
    con = sqlite3.connect(CATALOG, timeout=120, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=120000")
    return con


def _flush(con: sqlite3.Connection, pending: list[dict], retries: int = 10) -> None:
    """모아둔 행을 짧은 트랜잭션 하나로 쓴다.

    잠금을 잡는 구간이 밀리초 단위라 샤드가 여럿이어도 서로 거의 안 기다린다.
    그래도 겹치면 물러났다 다시 시도한다.
    """
    if not pending:
        return
    sql = (
        f"INSERT OR REPLACE INTO {STAGING}"
        f"({', '.join(STAGING_COLS)}) "
        f"VALUES({', '.join('?' * len(STAGING_COLS))})"
    )
    payload = [tuple(r.get(c) for c in STAGING_COLS) for r in pending]
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
    raise sqlite3.OperationalError(f"스테이징 쓰기 실패 — {retries}회 재시도 후에도 잠김")


def _apply_subject(fields: list[dict]) -> int:
    """subject(본인/제3자)를 라벨로 계산해 넣는다.

    별도 backfill 패스를 돌 필요가 없도록 여기서 끝낸다. 이 값이 없으면
    '법정대리인성명' 같은 제3자 칸에 신청인 프로필이 자동으로 들어간다.
    """
    third = 0
    for f in fields:
        want = _subject_of(f.get("label", "")) if f.get("role") == "applicant" else "self"
        f["subject"] = want
        if want == "thirdParty":
            third += 1
    return third


def _build_pending_query(shard: int, shards: int) -> str:
    shard_sql = ""
    if shards > 1:
        shard_sql = f" AND (f.form_id % {int(shards)}) = {int(shard)}"
    return (
        f"SELECT f.form_id, f.source_path, f.name FROM forms f "
        f"LEFT JOIN {STAGING} s ON s.form_id = f.form_id "
        f"WHERE f.status='OK' AND s.form_id IS NULL{shard_sql} "
        f"ORDER BY f.form_id"
    )


def _fill_requirements_fields(row: dict, dm, rp) -> None:
    r = extract_requirements(dm, rp)
    row["attachments"] = json.dumps(r["attachments"], ensure_ascii=False)
    row["attachment_count"] = r["attachmentCount"]
    row["processing_time"] = r["processingTime"]
    row["fee"] = r["fee"]
    row["legal_basis"] = json.dumps(r["legalBasis"], ensure_ascii=False)
    row["submit_to"] = r["submitTo"]
    row["req_status"] = "OK"


def _fill_input_schema_fields(
    row: dict, dm, rp, name: str, fc: int, kinds: dict[str, int]
) -> dict[str, int]:
    s = build_input_schema(dm, rp, name=name, field_count=fc)
    inputs = s["inputs"]
    third = _apply_subject(inputs)
    row["form_kind"] = s["formKind"]
    row["input_schema"] = json.dumps(inputs, ensure_ascii=False)
    row["input_count"] = s["inputCount"]
    row["applicant_count"] = s["applicantCount"]
    row["office_count"] = s["officeCount"]
    row["sensitive_count"] = s["sensitiveCount"]
    row["schema_status"] = "OK"
    kinds[s["formKind"]] = kinds.get(s["formKind"], 0) + 1
    return {
        "third": third,
        "app": s["applicantCount"],
        "off": s["officeCount"],
        "sec": s["sensitiveCount"],
    }


def _load_and_classify_form(row: dict, rel: str, name: str) -> tuple[dict | None, dict | None]:
    """(dm_rp, cls) 반환. 실패 시 dm_rp=None (row에 이미 상태 기록됨)."""
    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel}, project_root=PROJECT_ROOT
    )
    if res.get("verdict") != "PASS":
        row["rebuild_status"] = "FAIL:PARSE"
        return None, None
    dm, rp = res["documentModel"], res["renderPayload"]

    # ③ 라벨 색인 + field_count — 먼저 나와야 한다. 분류(fillable)가 이 값을 먹기 때문이다.
    labels = extract_fields(dm, rp)
    fc = len(labels)
    row["field_count"] = fc
    row["labels"] = json.dumps(labels, ensure_ascii=False)

    cls = classify_document(name, fc)
    row["doc_type"] = cls["docType"]
    row["fillable"] = 1 if cls["fillable"] else 0
    row["clean_name"] = cls["cleanName"]
    row["doc_reason"] = cls["reason"]
    return {"dm": dm, "rp": rp, "fc": fc}, cls


def _process_one_form(fid: int, rel: str, name: str, cap: float, kinds: dict[str, int]) -> dict:
    """반환: row dict + status(ok/fail/skip) + agg_third/app/off/sec 델타."""
    row: dict = {"form_id": fid, "rebuild_status": "OK"}
    agg = {"third": 0, "app": 0, "off": 0, "sec": 0}
    status = "ok"
    try:
        if not rel or Path(rel).is_absolute() or rel.startswith(("/", "\\")):
            row["rebuild_status"] = "SKIP_OUTSIDE_PROJECT"
            status = "skip"
        else:
            src = PROJECT_ROOT / rel
            if not src.is_file() or src.stat().st_size > cap:
                row["rebuild_status"] = "SKIP_SIZE_OR_MISSING"
                status = "skip"
            else:
                loaded, cls = _load_and_classify_form(row, rel, name)
                if loaded is None:
                    status = "fail"
                else:
                    _fill_requirements_fields(row, loaded["dm"], loaded["rp"])
                    # ① 입력 스키마 — 새 fillable 기준
                    if cls["fillable"]:
                        agg = _fill_input_schema_fields(
                            row, loaded["dm"], loaded["rp"], name, loaded["fc"], kinds
                        )
                    else:
                        row["schema_status"] = "SKIP_NOT_FILLABLE"
                    status = "ok"
    except Exception as e:  # ruff: ignore[blind-except]
        row["rebuild_status"] = f"FAIL:{type(e).__name__}"
        status = "fail"
    return {"row": row, "status": status, "agg": agg}


def run(limit: int = 0, size_cap_mb: float = 3.0, shard: int = 0, shards: int = 1) -> None:
    """shards>1 이면 form_id % shards == shard 인 것만 처리한다.

    파싱이 CPU 바운드 단일 프로세스라 16코어 기계에서 1코어만 쓴다.
    샤드를 나눠 여러 프로세스로 돌리면 그만큼 줄어든다.

    쓰기는 파싱이 끝난 뒤 `_flush` 로 모아서 짧게 한다. 파싱 도중에 쓰기
    트랜잭션을 물고 있으면 워커 하나가 잠금을 수 분씩 붙들어 나머지가 전부
    'database is locked' 로 죽는다 — 첫 시도에서 실제로 그렇게 됐다.
    """
    con = _connect()
    con.executescript(DDL)

    rows = con.execute(_build_pending_query(shard, shards)).fetchall()
    if limit:
        rows = rows[:limit]
    done_already = con.execute(f"SELECT COUNT(*) FROM {STAGING}").fetchone()[0]
    tag = f"[shard {shard}/{shards}] " if shards > 1 else ""
    _log(f"{tag}[start] 재생성 대상 {len(rows):,}종 (이미 쌓인 {done_already:,}건 제외 — 재개형)")

    t0 = time.time()
    ok = fail = skip = 0
    agg_third = agg_app = agg_off = agg_sec = 0
    kinds: dict[str, int] = {}
    cap = size_cap_mb * 1024 * 1024
    pending: list[dict] = []

    for i, (fid, rel, name) in enumerate(rows, 1):
        outcome = _process_one_form(fid, rel, name, cap, kinds)
        row = outcome["row"]
        if outcome["status"] == "ok":
            ok += 1
        elif outcome["status"] == "fail":
            fail += 1
        else:
            skip += 1
        agg_third += outcome["agg"]["third"]
        agg_app += outcome["agg"]["app"]
        agg_off += outcome["agg"]["off"]
        agg_sec += outcome["agg"]["sec"]

        pending.append(row)
        if len(pending) >= COMMIT_EVERY:
            _flush(con, pending)
        if i % 500 == 0:
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(rows) - i) / rate / 60 if rate else 0
            _log(
                f"{tag}  … {i:,}/{len(rows):,} OK {ok:,} 실패 {fail} "
                f"스킵 {skip} [{el:.0f}s ~{rate:.1f}/s 남은 {eta:.0f}분] "
                f"신청인칸 {agg_app:,} 제3자칸 {agg_third:,}"
            )

    _flush(con, pending)
    con.close()
    el = time.time() - t0
    _log(f"{tag}[done] OK {ok:,} · 실패 {fail} · 스킵 {skip} · {el / 60:.1f}분")
    _log(
        f"[집계] 신청인칸 {agg_app:,} · 관공서칸 {agg_off:,} · "
        f"민감칸 {agg_sec:,} · 제3자칸 {agg_third:,}"
    )
    if kinds:
        _log(
            "[서식종류] "
            + " · ".join(f"{k} {v:,}" for k, v in sorted(kinds.items(), key=lambda x: -x[1]))
        )
    _log("[다음] --status 로 확인 후 --promote 로 반영")


def status() -> dict:
    con = _connect()
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if STAGING not in have:
        con.close()
        return {"staged": 0, "target": 0, "note": "스테이징 테이블 없음"}
    target = con.execute("SELECT COUNT(*) FROM forms WHERE status='OK'").fetchone()[0]
    staged = con.execute(f"SELECT COUNT(*) FROM {STAGING}").fetchone()[0]
    by = dict(
        con.execute(
            f"SELECT rebuild_status, COUNT(*) FROM {STAGING} GROUP BY 1 ORDER BY 2 DESC"
        ).fetchall()
    )
    schema_ok = con.execute(f"SELECT COUNT(*) FROM {STAGING} WHERE schema_status='OK'").fetchone()[
        0
    ]
    con.close()
    return {
        "target": target,
        "staged": staged,
        "byStatus": by,
        "schemaOk": schema_ok,
        "remaining": target - staged,
    }


def promote(force: bool = False) -> dict:
    """스테이징을 forms/fields 에 반영. 커버리지 미달이면 거부."""
    st = status()
    if st["remaining"] > 0 and not force:
        return {
            "promoted": False,
            "reason": f"미완 {st['remaining']:,}건 — 배치를 마저 돌리거나 --force 를 준다",
            **st,
        }
    con = _connect()
    con.execute("BEGIN")
    try:
        con.execute(f"""
            UPDATE forms SET
                field_count      = (SELECT s.field_count      FROM {STAGING} s WHERE s.form_id=forms.form_id),
                doc_type         = (SELECT s.doc_type         FROM {STAGING} s WHERE s.form_id=forms.form_id),
                fillable         = (SELECT s.fillable         FROM {STAGING} s WHERE s.form_id=forms.form_id),
                clean_name       = (SELECT s.clean_name       FROM {STAGING} s WHERE s.form_id=forms.form_id),
                doc_reason       = (SELECT s.doc_reason       FROM {STAGING} s WHERE s.form_id=forms.form_id),
                form_kind        = (SELECT s.form_kind        FROM {STAGING} s WHERE s.form_id=forms.form_id),
                input_schema     = (SELECT s.input_schema     FROM {STAGING} s WHERE s.form_id=forms.form_id),
                input_count      = (SELECT s.input_count      FROM {STAGING} s WHERE s.form_id=forms.form_id),
                applicant_count  = (SELECT s.applicant_count  FROM {STAGING} s WHERE s.form_id=forms.form_id),
                office_count     = (SELECT s.office_count     FROM {STAGING} s WHERE s.form_id=forms.form_id),
                sensitive_count  = (SELECT s.sensitive_count  FROM {STAGING} s WHERE s.form_id=forms.form_id),
                schema_status    = (SELECT s.schema_status    FROM {STAGING} s WHERE s.form_id=forms.form_id),
                attachments      = (SELECT s.attachments      FROM {STAGING} s WHERE s.form_id=forms.form_id),
                attachment_count = (SELECT s.attachment_count FROM {STAGING} s WHERE s.form_id=forms.form_id),
                processing_time  = (SELECT s.processing_time  FROM {STAGING} s WHERE s.form_id=forms.form_id),
                fee              = (SELECT s.fee              FROM {STAGING} s WHERE s.form_id=forms.form_id),
                legal_basis      = (SELECT s.legal_basis      FROM {STAGING} s WHERE s.form_id=forms.form_id),
                submit_to        = (SELECT s.submit_to        FROM {STAGING} s WHERE s.form_id=forms.form_id),
                req_status       = (SELECT s.req_status       FROM {STAGING} s WHERE s.form_id=forms.form_id)
            WHERE EXISTS (SELECT 1 FROM {STAGING} s WHERE s.form_id=forms.form_id)
        """)
        # 라벨 색인 재구축 — 재생성분이 있는 서식만 갈아끼운다
        con.execute(
            f"DELETE FROM fields WHERE form_id IN "
            f"(SELECT form_id FROM {STAGING} WHERE labels IS NOT NULL)"
        )
        for fid, raw in con.execute(
            f"SELECT form_id, labels FROM {STAGING} WHERE labels IS NOT NULL"
        ).fetchall():
            try:
                labels = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            con.executemany(
                "INSERT INTO fields(form_id,label) VALUES(?,?)", [(fid, lab) for lab in labels]
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        con.close()
        raise
    con.close()
    return {"promoted": True, **st}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--size-cap-mb", type=float, default=3.0)
    ap.add_argument("--status", action="store_true", help="진행 상황만 출력")
    ap.add_argument("--promote", action="store_true", help="스테이징을 forms/fields 에 반영")
    ap.add_argument("--force", action="store_true", help="--promote 시 미완이어도 강행")
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--shards", type=int, default=1, help="여러 프로세스로 나눠 돌릴 때 총 개수")
    args = ap.parse_args()
    if args.status:
        _log(json.dumps(status(), ensure_ascii=False, indent=2))
        return
    if args.promote:
        _log(json.dumps(promote(args.force), ensure_ascii=False, indent=2))
        return
    run(args.limit, args.size_cap_mb, args.shard, args.shards)


if __name__ == "__main__":
    main()
