"""WEB-OFFICE-VISUAL-REGRESSION — M0 검증 하네스 CLI (지시문 8·9장).

한컴 실렌더(truth 캐시)를 기준 이미지로, 좌표 렌더러 뷰어 스크린샷과의
페이지별 픽셀 diff%를 계산한다. 완료 기준(9장 M7): 전 페이지 diff < 1%.

사전조건: uvicorn 서버(HWPX_WEB_OFFICE_HANCOM_REFRESH 무관, 캐시만 필요)와
headless Chrome(--remote-debugging-port)이 떠 있어야 한다.
read-only — 원본 무수정. 보고는 stdout(JSON).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

from scripts.hwpx.web_office.visual_diff import run_diff  # noqa: E402

PASS_VERDICT = "PASS_WEB_OFFICE_VISUAL_REGRESSION"
FAIL_VERDICT = "FAIL_WEB_OFFICE_VISUAL_REGRESSION"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", required=True,
                    help="프로젝트-상대 .hwpx 경로(반복 지정 가능)")
    ap.add_argument("--cdp-port", type=int, default=9223)
    ap.add_argument("--http-base", default="http://127.0.0.1:8773")
    ap.add_argument("--out", default="tmp/visual_diff")
    args = ap.parse_args()

    out_root = ROOT / args.out
    results = []
    for rel in args.source:
        cand = ROOT / rel
        if not cand.is_file():
            results.append({"path": rel, "ok": False, "error": "NOT_FOUND"})
            continue
        dig = hashlib.sha256(cand.read_bytes()).hexdigest()[:16]
        truth_dir = ROOT / "tmp/web_office_truth" / dig
        out_dir = out_root / dig
        r = run_diff(args.cdp_port, args.http_base, rel, truth_dir, out_dir)
        results.append(r)

    ok = sum(1 for r in results if r.get("ok"))
    summary = {
        "schemaVersion": "web_office_visual_regression_v1",
        "verdict": PASS_VERDICT if ok == len(results) and results
        else FAIL_VERDICT,
        "scanned": len(results),
        "ok": ok,
        "worst": [
            {"path": r["path"],
             "perPage": [p for p in r.get("perPage", [])
                        if p.get("diffPct", 0) > 1.0][:3],
             "error": r.get("error")}
            for r in results if not r.get("ok")
        ],
    }
    (out_root).mkdir(parents=True, exist_ok=True)
    (out_root / "report.json").write_text(
        json.dumps({"summary": summary, "results": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
