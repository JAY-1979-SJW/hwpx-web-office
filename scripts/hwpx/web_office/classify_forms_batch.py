"""수집 서식 전량 분류 적재 — docType · fillable · cleanName 을 카탈로그에 기록.

form_taxonomy.classify_document 로 38,165건을 분류해 forms 테이블에 채운다.
이름만 보는 순수 계산이라 HWPX 파싱이 없어 전량이 수초에 끝난다.

컬럼:
    doc_type     신청신고 / 증명발급 / 보고통지 / 대장기록 / 계약동의 /
                 계획내역 / 기준별표 / 기타
    fillable     1=채울 칸이 있는 서식, 0=기준표·삭제껍데기·빈문서
    clean_name   해시접두·서식번호를 뗀 사람이 읽는 이름
    doc_reason   판정 근거 (NAME_SUFFIX / NAME_KEYWORD / ANNEX_TABLE /
                 DELETED_STUB / UNMATCHED)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.hwpx.web_office.form_taxonomy import classify_document  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"

COLUMNS = [("doc_type", "TEXT"), ("fillable", "INTEGER"),
           ("clean_name", "TEXT"), ("doc_reason", "TEXT")]


def ensure_schema(con: sqlite3.Connection) -> None:
    have = {r[1] for r in con.execute("PRAGMA table_info(forms)")}
    for name, typ in COLUMNS:
        if name not in have:
            con.execute(f"ALTER TABLE forms ADD COLUMN {name} {typ}")
    con.commit()


STASH = PROJECT_ROOT / "data" / "drafts" / "form_library" / "doc_classification.jsonl"


def compute() -> tuple[list[tuple], dict]:
    """분류만 계산해서 반환 — DB 쓰기 잠금과 무관하게 언제든 돌릴 수 있다.

    해부 배치가 장시간 쓰기 잠금을 쥐고 있으면 ALTER TABLE 이 막힌다.
    계산과 적재를 분리해 두면 잠금이 풀릴 때 적재만 다시 하면 된다."""
    con = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True, timeout=60)
    rows = con.execute("SELECT form_id, name, field_count FROM forms").fetchall()
    con.close()
    stats: dict[str, int] = {}
    fillable = 0
    updates: list[tuple] = []
    for fid, name, fc in rows:
        r = classify_document(name, fc)
        stats[r["docType"]] = stats.get(r["docType"], 0) + 1
        fillable += bool(r["fillable"])
        updates.append((r["docType"], 1 if r["fillable"] else 0,
                        r["cleanName"], r["reason"], fid))
    return updates, {"total": len(rows), "fillable": fillable,
                     "byDocType": dict(sorted(stats.items(), key=lambda x: -x[1]))}


def stash() -> dict:
    """계산 결과를 파일에 쌓아둔다 (잠금 해제 후 --apply 로 적재)."""
    import json
    updates, summary = compute()
    STASH.parent.mkdir(parents=True, exist_ok=True)
    with STASH.open("w", encoding="utf-8") as f:
        for u in updates:
            f.write(json.dumps(u, ensure_ascii=False) + "\n")
    summary["stashPath"] = str(STASH)
    return summary


def apply_stash() -> dict:
    """쌓아둔 분류를 카탈로그에 적재."""
    import json
    if not STASH.exists():
        raise SystemExit(f"stash 없음: {STASH} — 먼저 --stash 로 계산하세요")
    updates = [tuple(json.loads(l)) for l in
               STASH.read_text(encoding="utf-8").splitlines() if l.strip()]
    con = sqlite3.connect(CATALOG, timeout=300)
    con.execute("PRAGMA journal_mode=WAL")
    ensure_schema(con)
    con.executemany(
        "UPDATE forms SET doc_type=?, fillable=?, clean_name=?, doc_reason=? "
        "WHERE form_id=?", updates)
    con.commit()
    con.close()
    return {"applied": len(updates)}


def run(dry_run: bool = False) -> dict:
    con = sqlite3.connect(CATALOG, timeout=300)
    con.execute("PRAGMA journal_mode=WAL")
    ensure_schema(con)
    rows = con.execute("SELECT form_id, name, field_count FROM forms").fetchall()
    t0 = time.time()
    stats: dict[str, int] = {}
    fillable = 0
    updates = []
    for fid, name, fc in rows:
        r = classify_document(name, fc)
        stats[r["docType"]] = stats.get(r["docType"], 0) + 1
        fillable += bool(r["fillable"])
        updates.append((r["docType"], 1 if r["fillable"] else 0,
                        r["cleanName"], r["reason"], fid))
    if not dry_run:
        con.executemany(
            "UPDATE forms SET doc_type=?, fillable=?, clean_name=?, doc_reason=? "
            "WHERE form_id=?", updates)
        con.commit()
    con.close()
    return {"total": len(rows), "fillable": fillable,
            "byDocType": dict(sorted(stats.items(), key=lambda x: -x[1])),
            "elapsedSec": round(time.time() - t0, 1), "dryRun": dry_run}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stash", action="store_true",
                    help="계산만 해서 파일에 쌓아둔다(쓰기 잠금 회피)")
    ap.add_argument("--apply", action="store_true",
                    help="쌓아둔 분류를 카탈로그에 적재")
    args = ap.parse_args()
    if args.apply:
        print(f"[applied] {apply_stash()['applied']:,}건 적재")
        return
    if args.stash:
        res = stash()
        print(f"[stash] {res['total']:,}건 계산 · 채움가능 {res['fillable']:,} "
              f"({res['fillable']/res['total']*100:.1f}%)")
        for k, v in res["byDocType"].items():
            print(f"   {k:<10}{v:>8,}")
        print(f"[out] {res['stashPath']}")
        return
    res = run(args.dry_run)
    print(f"[done] {res['total']:,}건 분류 · 채움가능 {res['fillable']:,} "
          f"({res['fillable']/res['total']*100:.1f}%) · {res['elapsedSec']}초")
    for k, v in res["byDocType"].items():
        print(f"   {k:<10}{v:>8,}")


if __name__ == "__main__":
    main()
