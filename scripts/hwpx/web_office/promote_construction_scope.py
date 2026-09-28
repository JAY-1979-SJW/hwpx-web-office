#!/usr/bin/env python3
"""
build_ai_interpretation_cache.promote()의 안전 로직(should_demote/
should_promote_to_user, 2차 검증 일치 반영)을 그대로 재사용하되,
건축·건설 범위 form_id로만 제한한다.

이유: 기존 promote()는 성공률 게이트를 스테이징 "전체"로 계산해서
(현재 전체 44%) 건축·건설(98%)만 좋아도 통째로 거부된다. 반영 로직
자체는 건드리지 않고, 대상 집합만 좁힌다.

API 호출 없음(순수 DB 병합) - 이미 스테이징된 해석 결과를 옮길 뿐이다.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.web_office.ai_field_interpretation import should_demote, should_promote_to_user  # ruff: ignore[module-import-not-at-top-of-file]

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
STAGING = "ai_field_interpretation"
VERIFY_TABLE = "ai_field_verification"
PROMOTE_MIN_OK_RATIO = 0.90

CONSTRUCTION_DOC_RE = re.compile(
    r"(검측|시공|감리|공사|착공|준공|기성|공정|안전관리|품질관리"
    r"|자재승인|하도급|설계변경|현장대리인|건설기술|시방)"
)


def _log(m):
    print(m, flush=True)


def _scope_form_ids(con) -> set:
    """건축·건설 범위 form_id 목록 (문서명 키워드 기준 - 기존 --scope construction과 동일 규칙)."""
    all_forms = con.execute(
        "SELECT form_id, COALESCE(clean_name,''), COALESCE(name,'') FROM forms"
    ).fetchall()
    return {fid for fid, cn, n in all_forms if CONSTRUCTION_DOC_RE.search(f"{cn} {n}")}


def _staging_ok_ratio(con, scope_ids: set) -> tuple[int, int, float]:
    rows = con.execute(
        f"SELECT status, COUNT(*) FROM {STAGING} WHERE form_id IN"
        f" ({','.join('?' * len(scope_ids))}) GROUP BY status",
        tuple(scope_ids),
    ).fetchall()
    staged = sum(n for _, n in rows)
    ok = dict(rows).get("OK", 0)
    ratio = (ok / staged) if staged else 0.0
    return staged, ok, ratio


def _verified_by_form(con, scope_ids: set) -> dict:
    verified_by_form = {}
    for fid, agreed in con.execute(
        f"SELECT form_id, author_agreed FROM {VERIFY_TABLE}"
        f" WHERE status='OK' AND author_agreed IS NOT NULL"
    ):
        if fid not in scope_ids:
            continue
        try:
            verified_by_form[fid] = set(json.loads(agreed))
        except (json.JSONDecodeError, TypeError):
            pass
    return verified_by_form


def _apply_ai_judgment(
    f: dict, it: dict, doc_type: str, form_kind: str, app_before: int, agreed
) -> tuple[bool, bool, bool]:
    """AI 해석(it)을 스키마 필드(f)에 반영한다(제자리 수정).

    반환: (demoted, revived, tagged) 각각 이번 필드에서 일어났는지 여부.
    """
    judged = {
        **it,
        "label": it.get("label") or f.get("label") or "",
        "ruleRole": it.get("ruleRole") or f.get("role") or "",
    }
    demoted = revived = tagged = False
    if f.get("role") == "applicant" and should_demote(judged):
        f["role"] = "noise"
        demoted = True
    elif f.get("role") == "office" and should_promote_to_user(
        judged,
        doc_type=doc_type,
        form_kind=form_kind,
        form_applicant_count=app_before,
        verified=(it.get("key") in agreed if agreed is not None else None),
    ):
        f["role"] = "applicant"
        revived = True
    if not (f.get("semantic") or "").strip() and it["semantic"]:
        f["semantic"] = it["semantic"]
        tagged = True
    if it.get("meaning"):
        f["aiMeaning"] = it["meaning"]
    if it.get("question"):
        f["aiQuestion"] = it["question"]
    if it.get("profileKey"):
        f["aiProfileKey"] = it["profileKey"]
    return demoted, revived, tagged


def _process_one_form(con, form_id, interp_json: str, verified_by_form: dict):
    """단일 서식에 AI 해석을 반영한다.

    반환: (pending_update_row, (demoted, revived, tagged)) — schema 가 없으면
    (None, None).
    """
    row = con.execute(
        "SELECT input_schema, doc_type, form_kind, applicant_count FROM forms WHERE form_id=?",
        (form_id,),
    ).fetchone()
    if not row or not row[0]:
        return None, None
    schema = json.loads(row[0])
    doc_type, form_kind, app_before = row[1] or "", row[2] or "", row[3] or 0
    by_key = {i["key"]: i for i in json.loads(interp_json)}
    agreed = verified_by_form.get(form_id)

    demoted = revived = tagged = 0
    for f in schema:
        it = by_key.get(f.get("paragraphId"))
        if not it:
            continue
        d, r, t = _apply_ai_judgment(f, it, doc_type, form_kind, app_before, agreed)
        demoted += d
        revived += r
        tagged += t

    inputs = [f for f in schema if f.get("role") != "noise"]
    app = sum(1 for f in inputs if f.get("role") == "applicant")
    pending_row = (
        json.dumps(schema, ensure_ascii=False),
        len(inputs),
        app,
        len(inputs) - app,
        form_id,
    )
    return pending_row, (demoted, revived, tagged)


def _write_pending_updates(con, pending: list) -> None:
    for i in range(0, len(pending), 200):
        chunk = pending[i : i + 200]
        con.execute("BEGIN IMMEDIATE")
        con.executemany(
            "UPDATE forms SET input_schema=?, input_count=?,"
            " applicant_count=?, office_count=? WHERE form_id=?",
            chunk,
        )
        con.execute("COMMIT")


def promote_scoped():
    con = sqlite3.connect(CATALOG, timeout=120, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=120000")

    scope_ids = _scope_form_ids(con)
    staged, ok, ratio = _staging_ok_ratio(con, scope_ids)
    if not staged:
        _log("REJECTED: 건축·건설 범위 스테이징이 비었다")
        return
    _log(f"건축·건설 범위: 스테이징 {staged}건, OK {ok}건, 비율 {ratio:.1%}")
    if ratio < PROMOTE_MIN_OK_RATIO:
        _log(f"REJECTED: 성공률 {ratio:.1%} < 게이트 {PROMOTE_MIN_OK_RATIO:.0%}")
        return

    verified_by_form = _verified_by_form(con, scope_ids)
    if verified_by_form:
        _log(f"2차 검증 반영 대상: {len(verified_by_form)}건")

    updated = demoted = tagged = revived = revived_forms = 0
    pending = []
    for form_id, interp_json in con.execute(
        f"SELECT form_id, interpretations FROM {STAGING}"
        f" WHERE status='OK' AND interpretations IS NOT NULL"
        f" AND form_id IN ({','.join('?' * len(scope_ids))})",
        tuple(scope_ids),
    ):
        pending_row, stats = _process_one_form(con, form_id, interp_json, verified_by_form)
        if pending_row is None:
            continue
        pending.append(pending_row)
        form_demoted, revived_here, form_tagged = stats
        demoted += form_demoted
        tagged += form_tagged
        updated += 1
        revived += revived_here
        if revived_here:
            revived_forms += 1

    _write_pending_updates(con, pending)

    _log(
        f"PROMOTED(건축건설 범위): 서식 {updated} · 오염제거(noise 강등) {demoted}"
        f" · semantic 신규부여 {tagged}"
        f" · 역할교정(죽은 서식 되살림) {revived}칸/{revived_forms}서식"
    )
    con.close()


if __name__ == "__main__":
    promote_scoped()
