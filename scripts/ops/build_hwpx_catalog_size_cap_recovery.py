"""SKIPPED_LARGE 서식 구제 — 크기 상한(1.5MB) 재조정(3MB) 후 재분류.

배경: build_form_catalog.py 는 1.5MB 초과 문서를 파싱 자체를 건너뛰고
status='SKIPPED_LARGE' 로 저장한다(파싱 앞에서 규칙이 후보를 잘라내는
패턴 — §4.6 위반 소지). 실측 결과 이 임계값을 넘겨 스킵된 116건 중
49건(42%)은 3MB 미만으로, 정상 임계값 상향만으로 회복 가능하다.

이 스크립트는 build_form_catalog.py 를 다시 돌리지 않는다 — 그 스크립트는
catalog.sqlite 를 통째로 삭제하고 새로 만들어(이미 쌓인 derivations_rebuild·
ai_field_interpretation 등 수개월치 파생 작업이 전부 날아간다). 대신 기존
DB에 UPDATE 만으로 SKIPPED_LARGE → OK 전환한다(forms/fields 외 테이블 무영향).

이후 절차(이 스크립트가 하지 않음, 별도 실행 필요):
  python scripts/hwpx/web_office/rebuild_form_derivations_batch.py --size-cap-mb 3
  python scripts/hwpx/web_office/rebuild_form_derivations_batch.py --promote

사용: python scripts/ops/build_hwpx_catalog_size_cap_recovery.py [--size-cap-mb 3]
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts.hwpx.web_office.build_form_catalog import extract_fields  # noqa: E402
from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402

CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"


def _log(m: str) -> None:
    print(m, flush=True)


def run(size_cap_mb: float = 3.0) -> dict:
    if not CATALOG.is_file():
        raise SystemExit(f"카탈로그 DB 없음: {CATALOG}")
    cap = size_cap_mb * 1024 * 1024
    con = sqlite3.connect(CATALOG)
    con.execute("PRAGMA journal_mode=WAL")

    targets = con.execute(
        "SELECT form_id, source_path, name, size_bytes FROM forms "
        "WHERE status='SKIPPED_LARGE' AND size_bytes<=? ORDER BY form_id",
        (cap,)).fetchall()
    _log(f"[recover] 대상 {len(targets)}건 (임계값 {size_cap_mb}MB 이하 SKIPPED_LARGE)")

    ok = fail = 0
    t0 = time.time()
    for fid, rel, name, size_bytes in targets:
        try:
            if not rel or Path(rel).is_absolute():
                fail += 1
                continue
            src = PROJECT_ROOT / rel
            if not src.is_file():
                fail += 1
                continue
            res = load_hwpx_for_editor(
                {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
                project_root=PROJECT_ROOT)
            if res.get("verdict") != "PASS":
                con.execute("UPDATE forms SET status=? WHERE form_id=?",
                            (f"PARSE_FAIL:{res.get('reason', '')[:40]}", fid))
                fail += 1
                continue
            dm, rp = res["documentModel"], res["renderPayload"]
            sm = res.get("summary", {})
            labels = extract_fields(dm, rp)
            con.execute(
                "UPDATE forms SET status='OK', table_count=?, cell_count=?, "
                "field_count=?, fingerprint=? WHERE form_id=?",
                (sm.get("tables", 0), sm.get("cells", 0), len(labels),
                 dm.get("sourceDocumentHash", ""), fid))
            con.execute("DELETE FROM fields WHERE form_id=?", (fid,))
            con.executemany("INSERT INTO fields(form_id,label) VALUES(?,?)",
                            [(fid, lab) for lab in labels])
            ok += 1
        except Exception as e:  # noqa: BLE001 - 개별 실패는 건너뛰고 계속 진행
            con.execute("UPDATE forms SET status=? WHERE form_id=?",
                        (f"ERROR:{str(e)[:40]}", fid))
            fail += 1
        con.commit()

    remaining_large = con.execute(
        "SELECT COUNT(*) FROM forms WHERE status='SKIPPED_LARGE'").fetchone()[0]
    con.close()
    el = time.time() - t0
    result = {"targets": len(targets), "ok": ok, "fail": fail,
              "remaining_skipped_large": remaining_large, "elapsedSec": round(el, 1)}
    _log(f"[done] 대상 {len(targets)} · OK {ok} · 실패 {fail} · "
         f"잔존 SKIPPED_LARGE {remaining_large} · {el:.1f}초")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size-cap-mb", type=float, default=3.0)
    args = ap.parse_args()
    run(args.size_cap_mb)
