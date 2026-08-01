"""라벨 기준서 — (라벨, docType) 단위로 판정을 굳혀 재추론을 없앤다.

설계서: docs/design/hwpx_label_reference_cache_standard.md
지시(2026-08-02, 대표님): "문서 파싱하고 기준서가 없어서 그런게 더
심한것 같은데 캐시를 미리 AI가 분석하면?"

왜 필요한가(실측)
------------------
문서별 해석(§4.5)은 문서 하나마다 처음 보는 것처럼 독립 판정한다.
같은 라벨 `소방공사감리원`이 문서 인스턴스에 따라 작성자/상대방으로
다르게 판정된 실사례를 발견했다. 전체 라벨 있는 칸 394,714개 중 고유
(라벨,docType) 조합은 142,090개뿐(64.0% 중복) — `접수번호`/신청신고 만
10,751번 등장한다.

1단계 — 새 AI 호출 없이 백필
-----------------------------
`ai_field_verification.verdicts`(2차 원문)와 `ai_field_interpretation.
interpretations`(1차 원문)가 이미 저장돼 있다. 이 둘을 다시 합의
계산(`ai_field_verification.agreement`)해 **일치한 칸만** 기준서에
채운다. 같은 (라벨,docType) 가 문서마다 다르게 나오면 `consistent=False`
로 남기고 자동 적용 대상에서 제외한다 — 애매한 걸 억지로 통일시키면
오류를 카탈로그 전체로 복제한다.

값은 저장하지 않는다(§4 개인정보 원칙 불변) — 저장하는 것은 라벨의
의미(isInput·filledBy·semantic·profileKey·question)뿐이다.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
TABLE = "label_reference_cache"

DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE}(
    cache_key TEXT PRIMARY KEY,
    label TEXT,
    doc_type TEXT,
    verdict TEXT,          -- self | other | none
    semantic TEXT,
    profile_key TEXT,
    question TEXT,
    sample_count INTEGER,
    conflict_count INTEGER,
    consistent INTEGER,    -- 1 = 자동 적용 가능, 0 = 매번 재판정
    source_form_ids TEXT   -- 최근 근거 form_id 몇 개(JSON, 감사용)
);
"""

_WS_RE = re.compile(r"\s+")


def normalize_label(label: str) -> str:
    """라벨 표기 흔들림(공백)만 지운다 — 의미까지 바꾸지 않는다."""
    return _WS_RE.sub("", (label or "").strip())


def cache_key(label: str, doc_type: str) -> str:
    return f"{normalize_label(label)}|||{doc_type or ''}"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(CATALOG, timeout=120, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=120000")
    return con


def backfill_from_verified(*, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """검증 통과 기록에서 새 AI 호출 없이 라벨 기준서를 채운다."""
    from scripts.hwpx.web_office.ai_field_verification import agreement
    from scripts.hwpx.web_office.build_ai_interpretation_cache import (
        STAGING, VERIFY_TABLE)

    con = _connect()
    con.execute(DDL)
    rows = con.execute(
        f"SELECT v.form_id, v.verdicts, s.interpretations,"
        f" COALESCE(f.doc_type,'') FROM {VERIFY_TABLE} v"
        f" JOIN {STAGING} s ON s.form_id=v.form_id"
        f" JOIN forms f ON f.form_id=v.form_id"
        f" WHERE v.status='OK' AND v.verdicts IS NOT NULL").fetchall()

    # (key) -> {verdict별 등장수, semantic/profileKey/question 표본, form_ids}
    acc: dict[str, dict[str, Any]] = {}
    forms_seen = 0
    for form_id, verdicts_json, interp_json, doc_type in rows:
        forms_seen += 1
        verdicts = json.loads(verdicts_json)
        interp = json.loads(interp_json)
        ag = agreement(interp, verdicts)
        agreed_keys = (set(ag["authorAgreed"]) | set(ag["notInputAgreed"])
                      | set(ag["otherAgreed"]))
        by_key = {i["key"]: i for i in interp}
        for key in agreed_keys:
            i = by_key.get(key)
            if not i:
                continue
            label = i.get("label") or ""
            if not label:
                continue
            v = verdicts.get(key)  # self|other|none — 2차(독립) 판정
            ck = cache_key(label, doc_type)
            slot = acc.setdefault(ck, {
                "label": label, "doc_type": doc_type,
                "verdict_counts": {}, "semantic": {}, "profile_key": {},
                "question": {}, "form_ids": [],
            })
            slot["verdict_counts"][v] = slot["verdict_counts"].get(v, 0) + 1
            if i.get("semantic"):
                slot["semantic"][i["semantic"]] = \
                    slot["semantic"].get(i["semantic"], 0) + 1
            if i.get("profileKey"):
                slot["profile_key"][i["profileKey"]] = \
                    slot["profile_key"].get(i["profileKey"], 0) + 1
            if i.get("question"):
                slot["question"][i["question"]] = \
                    slot["question"].get(i["question"], 0) + 1
            if len(slot["form_ids"]) < 5:
                slot["form_ids"].append(form_id)

    def _majority(counter: dict) -> str:
        return max(counter.items(), key=lambda kv: kv[1])[0] if counter else ""

    payload = []
    consistent_n = inconsistent_n = 0
    for ck, slot in acc.items():
        vc = slot["verdict_counts"]
        total = sum(vc.values())
        top_v, top_n = max(vc.items(), key=lambda kv: kv[1])
        conflict = total - top_n
        consistent = 1 if conflict == 0 else 0
        if consistent:
            consistent_n += 1
        else:
            inconsistent_n += 1
        payload.append((
            ck, slot["label"], slot["doc_type"], top_v,
            _majority(slot["semantic"]), _majority(slot["profile_key"]),
            _majority(slot["question"]), total, conflict, consistent,
            json.dumps(slot["form_ids"], ensure_ascii=False),
        ))

    con.execute(f"DELETE FROM {TABLE}")   # 백필은 전량 재계산(재현 가능)
    con.executemany(
        f"INSERT INTO {TABLE}(cache_key,label,doc_type,verdict,semantic,"
        f"profile_key,question,sample_count,conflict_count,consistent,"
        f"source_form_ids) VALUES(?,?,?,?,?,?,?,?,?,?,?)", payload)
    con.commit()
    con.close()

    return {
        "formsScanned": forms_seen,
        "entriesTotal": len(payload),
        "consistent": consistent_n,
        "inconsistent": inconsistent_n,
        "fieldOccurrencesCovered": sum(p[7] for p in payload),
    }


def lookup(con: sqlite3.Connection, label: str,
          doc_type: str) -> dict[str, Any] | None:
    """신뢰 가능한(consistent) 기준서 항목만 돌려준다. 없으면 None."""
    row = con.execute(
        f"SELECT verdict, semantic, profile_key, question, sample_count"
        f" FROM {TABLE} WHERE cache_key=? AND consistent=1",
        (cache_key(label, doc_type),)).fetchone()
    if not row:
        return None
    return {"verdict": row[0], "semantic": row[1], "profileKey": row[2],
            "question": row[3], "sampleCount": row[4]}


def status() -> dict[str, Any]:
    con = _connect()
    con.execute(DDL)
    total = con.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    consistent = con.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE consistent=1").fetchone()[0]
    covered = con.execute(
        f"SELECT SUM(sample_count) FROM {TABLE}").fetchone()[0] or 0
    con.close()
    return {"entries": total, "consistent": consistent,
            "inconsistent": total - consistent, "fieldOccurrencesCovered": covered}


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.backfill:
        print(json.dumps(backfill_from_verified(), ensure_ascii=False, indent=2))
    elif a.status:
        print(json.dumps(status(), ensure_ascii=False, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
