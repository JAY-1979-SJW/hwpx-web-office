"""수집 서식 전량 입력 스키마 생성 — 파일별로 "무엇을 채워야 하는가"를 적재.

각 HWPX 를 파싱해 form_input_schema.build_input_schema 로
    서식종류 · 입력칸 목록(라벨·역할·의미·좌표) · 신청인/관공서/민감 칸 수
를 뽑아 catalog.sqlite 에 저장한다.

- 재개 가능: schema_status 가 채워진 행은 건너뛴다.
- 채움가능(fillable=1) 만 대상 — 기준표·삭제껍데기는 채울 게 없다.
- WAL 모드 — 생성 중에도 검색 가능.

정확도는 정답셋 3종으로 측정했다(tests/test_web_office_field_roles.py):
    ①튜닝 96.7% · ②검증 97.5% · ③최종(무오염) 94.2%
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
from scripts.hwpx.web_office.form_input_schema import build_input_schema  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"

COLUMNS = [
    ("form_kind", "TEXT"),          # 민원신청 / 발급증서 / 행정내부
    ("input_schema", "TEXT"),       # JSON 배열 — 입력칸 전체
    ("input_count", "INTEGER"),
    ("applicant_count", "INTEGER"),
    ("office_count", "INTEGER"),
    ("sensitive_count", "INTEGER"),
    ("schema_status", "TEXT"),      # OK / SKIP:<사유> / FAIL:<사유>
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
    con = sqlite3.connect(CATALOG, timeout=300)
    con.execute("PRAGMA journal_mode=WAL")
    ensure_schema(con)
    rows = con.execute(
        "SELECT form_id, source_path, name, field_count FROM forms "
        "WHERE status='OK' AND fillable=1 "
        "AND (schema_status IS NULL OR schema_status='') "
        "ORDER BY form_id").fetchall()
    if limit:
        rows = rows[:limit]
    _log(f"[start] 입력스키마 대상 {len(rows):,}종 (재개형 — 완료분 제외)")

    t0 = time.time()
    ok = fail = skip = 0
    agg_app = agg_off = agg_sec = 0
    kinds: dict[str, int] = {}
    cap = size_cap_mb * 1024 * 1024
    for i, (fid, rel, name, fc) in enumerate(rows, 1):
        if not rel or Path(rel).is_absolute() or rel.startswith(("/", "\\")):
            con.execute("UPDATE forms SET schema_status=? WHERE form_id=?",
                        ("SKIP_OUTSIDE_PROJECT", fid))
            skip += 1
            continue
        src = PROJECT_ROOT / rel
        try:
            if not src.is_file() or src.stat().st_size > cap:
                con.execute("UPDATE forms SET schema_status=? WHERE form_id=?",
                            ("SKIP_SIZE_OR_MISSING", fid))
                skip += 1
                continue
            res = load_hwpx_for_editor(
                {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
                project_root=PROJECT_ROOT)
            if res.get("verdict") != "PASS":
                con.execute("UPDATE forms SET schema_status=? WHERE form_id=?",
                            ("FAIL:PARSE", fid))
                fail += 1
                continue
            s = build_input_schema(res["documentModel"], res["renderPayload"],
                                   name=name, field_count=fc)
            con.execute(
                "UPDATE forms SET form_kind=?, input_schema=?, input_count=?,"
                " applicant_count=?, office_count=?, sensitive_count=?,"
                " schema_status='OK' WHERE form_id=?",
                (s["formKind"], json.dumps(s["inputs"], ensure_ascii=False),
                 s["inputCount"], s["applicantCount"], s["officeCount"],
                 s["sensitiveCount"], fid))
            ok += 1
            agg_app += s["applicantCount"]
            agg_off += s["officeCount"]
            agg_sec += s["sensitiveCount"]
            kinds[s["formKind"]] = kinds.get(s["formKind"], 0) + 1
        except Exception as e:  # noqa: BLE001
            con.execute("UPDATE forms SET schema_status=? WHERE form_id=?",
                        (f"FAIL:{type(e).__name__}", fid))
            fail += 1
        if i % 500 == 0:
            con.commit()
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(rows) - i) / rate / 60 if rate else 0
            _log(f"  … {i:,}/{len(rows):,} OK {ok:,} 실패 {fail} 스킵 {skip} "
                 f"[{el:.0f}s ~{rate:.1f}/s 남은 {eta:.0f}분] "
                 f"신청인칸 {agg_app:,} 관공서칸 {agg_off:,} 민감 {agg_sec:,}")
    con.commit()
    con.close()
    el = time.time() - t0
    _log(f"[done] OK {ok:,} · 실패 {fail} · 스킵 {skip} · {el/60:.1f}분")
    _log(f"[집계] 신청인칸 {agg_app:,} · 관공서칸 {agg_off:,} · 민감칸 {agg_sec:,}")
    _log("[서식종류] " + " · ".join(f"{k} {v:,}" for k, v in
                                    sorted(kinds.items(), key=lambda x: -x[1])))


def backfill_subject() -> dict:
    """저장된 스키마에 subject(본인/제3자)를 채워 넣는다.

    subject 는 라벨만으로 계산되므로 HWPX 를 다시 열 필요가 없다. 전량
    재파싱(약 2시간) 대신 수초에 끝난다. 이 필드가 없으면 '법정대리인성명'
    같은 제3자 칸에 신청인 프로필이 자동으로 들어간다.
    """
    from scripts.hwpx.web_office.form_field_roles import _subject_of
    con = sqlite3.connect(CATALOG, timeout=600)
    con.execute("PRAGMA journal_mode=WAL")
    rows = con.execute(
        "SELECT form_id, input_schema FROM forms WHERE schema_status='OK' "
        "AND input_schema IS NOT NULL").fetchall()
    updated = third = 0
    for fid, raw in rows:
        try:
            fields = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        changed = False
        for f in fields:
            want = (_subject_of(f.get("label", ""))
                    if f.get("role") == "applicant" else "self")
            if f.get("subject") != want:
                f["subject"] = want
                changed = True
            if want == "thirdParty":
                third += 1
        if changed:
            con.execute("UPDATE forms SET input_schema=? WHERE form_id=?",
                        (json.dumps(fields, ensure_ascii=False), fid))
            updated += 1
    con.commit()
    con.close()
    return {"formsUpdated": updated, "thirdPartyFields": third,
            "scanned": len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--size-cap-mb", type=float, default=1.5)
    ap.add_argument("--backfill-subject", action="store_true",
                    help="저장된 스키마에 subject 만 보정 (재파싱 없음)")
    args = ap.parse_args()
    if args.backfill_subject:
        r = backfill_subject()
        _log(f"[backfill] 스캔 {r['scanned']:,} · 갱신 {r['formsUpdated']:,} · "
             f"제3자칸 {r['thirdPartyFields']:,}")
        return
    run(args.limit, args.size_cap_mb)


if __name__ == "__main__":
    main()
