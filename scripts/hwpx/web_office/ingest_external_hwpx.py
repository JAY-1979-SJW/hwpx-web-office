"""프로젝트 밖(원드라이브 등) HWPX 를 프로젝트 안으로 들여온다.

배경:
    카탈로그에 원본 저장소(33. office-analysis-engine) 시절 경로가 8,260건
    남아 있다. 파일은 로컬에 실재하지만 프로젝트 밖 절대경로라 로더의
    §4 경계검증에 막혀 해부·입력스키마 대상에서 통째로 빠졌다.

방침:
    경계검증을 느슨하게 하지 않는다. 대신 파일을 프로젝트 안으로 복사하고
    카탈로그의 source_path 를 새 상대경로로 바꾼다. 보안 경계는 그대로 두고
    데이터만 안으로 들인다.

중복:
    이름(clean_name) 기준으로 이미 보유한 서식은 들이지 않는다. 바이트
    해시로는 0건 중복이지만, 같은 서식도 한컴 변환 설정이 다르면 바이트가
    달라져 해시 중복 판정이 무의미하다(실측: 8,260건 전부 해시 신규,
    그러나 이름 기준으로는 2,256건이 이미 보유분).

DB 쓰기는 분리한다 — 해부/스키마 배치가 장시간 쓰기 잠금을 쥐고 있으면
UPDATE 가 막히므로, 복사 결과를 매니페스트로 남기고 --apply 로 반영한다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.hwpx.web_office.form_taxonomy import clean_name  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"
DEST_DIR = PROJECT_ROOT / "data" / "drafts" / "form_library" / "legacy_hwpx"
MANIFEST = PROJECT_ROOT / "data" / "drafts" / "form_library" / "legacy_ingest.jsonl"


def _log(m: str) -> None:
    print(m, flush=True)


def _safe(name: str, n: int = 90) -> str:
    s = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", name or "").strip("_")
    return s[:n] or "form"


def copy_in(limit: int = 0) -> dict:
    con = sqlite3.connect(f"file:{CATALOG}?mode=ro", uri=True, timeout=120)
    held = {clean_name(n) for (n,) in con.execute(
        "SELECT name FROM forms WHERE source_path LIKE 'data/%'")}
    rows = con.execute(
        "SELECT form_id, name, source_path FROM forms "
        "WHERE status='OK' AND source_path NOT LIKE 'data/%' "
        "ORDER BY form_id").fetchall()
    con.close()

    DEST_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    copied = skipped_dup = missing = failed = 0
    used: set[str] = {p.name for p in DEST_DIR.glob("*.hwpx")}
    records: list[dict] = []
    for i, (fid, name, sp) in enumerate(rows, 1):
        if limit and copied >= limit:
            break
        if clean_name(name) in held:
            skipped_dup += 1
            records.append({"formId": fid, "status": "SKIP_ALREADY_HELD"})
            continue
        src = Path(sp)
        if not src.is_file():
            missing += 1
            records.append({"formId": fid, "status": "SKIP_MISSING"})
            continue
        stem = _safe(Path(name or src.name).stem)
        fname = f"{fid}_{stem}.hwpx"
        if fname in used:
            fname = f"{fid}_{stem}_{len(used)}.hwpx"
        try:
            shutil.copy2(src, DEST_DIR / fname)
        except OSError:
            failed += 1
            records.append({"formId": fid, "status": "FAIL_COPY"})
            continue
        used.add(fname)
        copied += 1
        records.append({
            "formId": fid, "status": "COPIED",
            "newPath": f"data/drafts/form_library/legacy_hwpx/{fname}",
        })
        if copied % 500 == 0:
            el = time.time() - t0
            _log(f"  … 복사 {copied:,} (중복스킵 {skipped_dup:,}) "
                 f"[{el:.0f}s ~{copied/el:.0f}/s]")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return {"copied": copied, "skippedDuplicate": skipped_dup,
            "missing": missing, "failed": failed,
            "manifest": str(MANIFEST), "elapsedSec": round(time.time() - t0, 1)}


def apply_manifest() -> dict:
    """복사 결과를 카탈로그에 반영 — source_path 교체 + 재분석 대상으로 표시."""
    if not MANIFEST.is_file():
        raise SystemExit(f"매니페스트 없음: {MANIFEST} — 먼저 복사하세요")
    recs = [json.loads(l) for l in
            MANIFEST.read_text(encoding="utf-8").splitlines() if l.strip()]
    con = sqlite3.connect(CATALOG, timeout=600)
    con.execute("PRAGMA journal_mode=WAL")
    moved = marked = 0
    for r in recs:
        if r["status"] == "COPIED":
            # 경로 교체 후 해부·스키마를 다시 돌리도록 상태를 비운다
            con.execute(
                "UPDATE forms SET source_path=?, req_status=NULL, "
                "schema_status=NULL WHERE form_id=?",
                (r["newPath"], r["formId"]))
            moved += 1
        elif r["status"] == "SKIP_ALREADY_HELD":
            con.execute(
                "UPDATE forms SET schema_status='SKIP_DUPLICATE_OF_HELD' "
                "WHERE form_id=?", (r["formId"],))
            marked += 1
    con.commit()
    con.close()
    return {"pathUpdated": moved, "markedDuplicate": marked}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--apply", action="store_true",
                    help="복사 매니페스트를 카탈로그에 반영")
    args = ap.parse_args()
    if args.apply:
        r = apply_manifest()
        _log(f"[applied] 경로교체 {r['pathUpdated']:,} · "
             f"중복표시 {r['markedDuplicate']:,}")
        return
    r = copy_in(args.limit)
    _log(f"[done] 복사 {r['copied']:,} · 중복스킵 {r['skippedDuplicate']:,} · "
         f"없음 {r['missing']} · 실패 {r['failed']} · {r['elapsedSec']}초")
    _log(f"[out] {DEST_DIR}")
    _log(f"[manifest] {r['manifest']}")


if __name__ == "__main__":
    main()
