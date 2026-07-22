"""WEB-OFFICE-HANCOM-PRECACHE — 서식 사전검증 배치(공장 공정 ②).

한컴이 설치된 공장 머신에서 지정 폴더의 HWPX 를 일괄 처리한다:
  1) 한컴 재저장 정규화 캐시 생성 (tmp/web_office_normalized/)
  2) 한컴 실렌더 페이지 이미지 캐시 생성 (tmp/web_office_truth/)
  3) 자체 추출 품질 채점(물림·겹침) + **한컴 실제 페이지수 대조**

산출 캐시는 한컴 없는 서비스 런타임에 그대로 배포된다(캐시 우선 서빙).
read-only — 원본 무수정. 보고는 stdout(JSON).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

from scripts.hwpx.web_office.coordinate_layout import (  # noqa: E402
    extract, layout_quality)
from scripts.hwpx.web_office.hancom_layout_refresh import (  # noqa: E402
    calibrate_row_scale, get_row_scale, hancom_available,
    normalize_for_layout, render_truth_pages)

PASS_VERDICT = "PASS_WEB_OFFICE_HANCOM_PRECACHE"
FAIL_VERDICT = "FAIL_WEB_OFFICE_HANCOM_PRECACHE"


def precache_one(path: Path, project_root: Path) -> dict:
    rel = (str(path.relative_to(project_root))
           if path.is_relative_to(project_root) else str(path))
    rec: dict = {"path": rel, "verdict": "OK", "warnings": []}
    t0 = time.time()
    try:
        norm = normalize_for_layout(path, project_root=project_root)
        rec["normalized"] = norm != path
        truth_dir = render_truth_pages(path, project_root=project_root)
        rec["truthCached"] = truth_dir is not None
        hancom_pages = None
        if truth_dir is not None:
            try:
                hancom_pages = int(
                    (truth_dir / "DONE").read_text(encoding="ascii").strip())
            except (OSError, ValueError):
                pass
        rec["hancomPages"] = hancom_pages
        # 캘리브레이션 — 쪽수 불일치 시 배율 탐색(공장 1회), 이후 적용 추출
        k = get_row_scale(path, project_root=project_root)
        if (hancom_pages is not None and abs(k - 1.0) < 1e-3
                and extract(str(norm)).get("pages") != hancom_pages):
            kk = calibrate_row_scale(path, project_root=project_root)
            if kk:
                k = kk
        rec["rowScale"] = round(k, 4)
        lay = extract(str(norm), row_scale=k)
        rec["ourPages"] = lay.get("pages")
        q = layout_quality(lay)
        rec["quality"] = q
        if not q["ok"]:
            rec["warnings"].append(
                f"QUALITY:{q['cellOverflow']}/{q['cellOverflowMaxPx']}px"
                f"/ovl{q['bodyOverlap']}")
        if hancom_pages is not None and rec["ourPages"] != hancom_pages:
            rec["warnings"].append(
                f"PAGE_MISMATCH:ours{rec['ourPages']}!=hancom{hancom_pages}")
        if not rec["truthCached"]:
            rec["warnings"].append("TRUTH_UNAVAILABLE")
    except Exception as e:  # noqa: BLE001
        rec["verdict"] = "ERROR"
        rec["error"] = f"{type(e).__name__}: {e}"[:160]
        return rec
    rec["seconds"] = round(time.time() - t0, 1)
    if rec["warnings"]:
        rec["verdict"] = "WARN"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", action="append", required=True,
                    help="HWPX 폴더(반복 지정 가능)")
    ap.add_argument("--limit", type=int, default=0, help="상한(0=전수)")
    ap.add_argument("--json", default=None, help="상세 결과 저장 경로")
    args = ap.parse_args()

    files: list[Path] = []
    for r in args.root:
        base = Path(r) if Path(r).is_absolute() else ROOT / r
        if base.is_file():
            files.append(base)
        elif base.is_dir():
            files.extend(sorted(base.glob("*.hwpx")))
    if args.limit:
        files = files[: args.limit]

    results = [precache_one(p, ROOT) for p in files]
    ok = sum(1 for r in results if r["verdict"] == "OK")
    warn = sum(1 for r in results if r["verdict"] == "WARN")
    err = sum(1 for r in results if r["verdict"] == "ERROR")
    page_match = sum(
        1 for r in results
        if r.get("hancomPages") is not None
        and r.get("ourPages") == r.get("hancomPages"))
    page_known = sum(1 for r in results if r.get("hancomPages") is not None)

    summary = {
        "schemaVersion": "web_office_hancom_precache_v1",
        "verdict": PASS_VERDICT if err == 0 else FAIL_VERDICT,
        "hancomAvailable": hancom_available(),
        "scanned": len(results),
        "ok": ok, "warn": warn, "error": err,
        "pageMatch": {"matched": page_match, "known": page_known},
        "worst": [
            {"path": r["path"], "verdict": r["verdict"],
             "warnings": r.get("warnings", [])[:3],
             "error": r.get("error")}
            for r in results if r["verdict"] != "OK"
        ][:15],
    }
    if args.json:
        Path(args.json).write_text(
            json.dumps({"summary": summary, "results": results},
                       ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
