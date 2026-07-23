"""WEB-OFFICE-VISUAL-BASELINE-PROMOTE — 구조 diff 개선 시 기준선 재고정 절차.

목적(대표님 지시): 렌더링 개선(예: 테두리 중복 제거)이 pinned 시각회귀
게이트(test_web_office_visual_regression.py)를 깨뜨리는 문제는 결함이
아니라 "정당한 개선 시 기준 이미지를 갱신하는 절차"가 없다는 프로세스
공백이었다. 이 스크립트가 그 절차를 대신한다:

    1) 대상 fixture 전체에 M0 구조 diff(이진화+팽창, visual_diff.py) 실행
    2) 저장된 승인 기준선(BASELINE_FILE)과 비교
       - 모든 페이지가 기준선 이하(개선 또는 동일)면 "승인 가능"
       - 단 하나라도 기준선을 초과(악화)하면 즉시 거부 — 회귀 유입 차단
    3) --approve 없이는 diff 이미지 경로만 보여주고 종료(육안 승인 대기)
    4) --approve 지정 시에만 새 기준선을 파일에 기록(재고정)

이 파일(BASELINE_FILE)은 git 추적 대상이다 — 기준선 자체가 코드 리뷰
가능한 이력을 가져야 "몰래 통과 기준을 낮추는" 것을 방지한다.
read-only 렌더 측정만 수행 — 원본 HWPX 무수정.
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

BASELINE_FILE = ROOT / "data/reports/web_office_visual_baseline.json"
# 신규 진입 시 임의로 관대한 값을 못 박지 않도록, 최초 등재는 반드시
# --approve 와 함께 실측값 그대로 기록한다(수기 입력 금지).
REGRESSION_MARGIN_PCT = 0.05   # 부동소수 잡음 흡수용 허용오차(퍼센트포인트)

PASS_VERDICT = "PASS_WEB_OFFICE_VISUAL_BASELINE_PROMOTE"
FAIL_VERDICT = "FAIL_WEB_OFFICE_VISUAL_BASELINE_PROMOTE"


def _load_baseline() -> dict:
    if BASELINE_FILE.is_file():
        return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
    return {"schemaVersion": "web_office_visual_baseline_v1", "fixtures": {}}


def _fixture_key(source_rel: str) -> str:
    return source_rel.replace("\\", "/")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", action="append", required=True,
                    help="프로젝트-상대 .hwpx 경로(반복 지정 가능)")
    ap.add_argument("--cdp-port", type=int, default=9223)
    ap.add_argument("--http-base", default="http://127.0.0.1:8773")
    ap.add_argument("--out", default="tmp/visual_diff_promote")
    ap.add_argument("--approve", action="store_true",
                    help="육안 승인 완료 — 기준선 파일에 실제로 기록한다. "
                         "생략하면 diff 이미지 경로만 보여주고 기록 안 함.")
    args = ap.parse_args()

    baseline = _load_baseline()
    out_root = ROOT / args.out
    results = []
    any_regression = False

    for rel in args.source:
        cand = ROOT / rel
        if not cand.is_file():
            results.append({"path": rel, "verdict": "NOT_FOUND"})
            continue
        dig = hashlib.sha256(cand.read_bytes()).hexdigest()[:16]
        truth_dir = ROOT / "tmp/web_office_truth" / dig
        out_dir = out_root / dig
        r = run_diff(args.cdp_port, args.http_base, rel, truth_dir, out_dir)

        key = _fixture_key(rel)
        prior = baseline["fixtures"].get(key)
        page_reports = []
        fixture_regressed = False
        for p in r.get("perPage", []):
            cur = p.get("structDiffPct")
            if cur is None:
                continue
            prior_pct = (prior or {}).get(str(p["page"]))
            regressed = (prior_pct is not None
                         and cur > prior_pct + REGRESSION_MARGIN_PCT)
            if regressed:
                fixture_regressed = True
                any_regression = True
            page_reports.append({
                "page": p["page"], "structDiffPct": cur,
                "priorBaseline": prior_pct,
                "delta": (round(cur - prior_pct, 3)
                          if prior_pct is not None else None),
                "regressed": regressed,
                "diffImage": p.get("diffImage")})
        results.append({
            "path": rel, "verdict": "REGRESSED" if fixture_regressed
            else "OK", "pages": page_reports})

    ok = not any_regression
    summary = {
        "schemaVersion": "web_office_visual_baseline_promote_v1",
        "verdict": PASS_VERDICT if ok else FAIL_VERDICT,
        "approved": bool(args.approve) and ok,
        "anyRegression": any_regression,
        "results": results,
    }

    if args.approve and ok:
        for rel in args.source:
            match = next((r for r in results if r["path"] == rel), None)
            if not match or match["verdict"] != "OK":
                continue
            key = _fixture_key(rel)
            baseline["fixtures"][key] = {
                str(p["page"]): p["structDiffPct"] for p in match["pages"]}
        BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_FILE.write_text(
            json.dumps(baseline, ensure_ascii=False, indent=1),
            encoding="utf-8")
        summary["baselineFile"] = str(BASELINE_FILE.relative_to(ROOT))
    elif args.approve and not ok:
        summary["note"] = ("회귀 발견 — 승인해도 기준선을 기록하지 않았다. "
                            "regressed=true 인 페이지의 diffImage 를 먼저 확인.")
    else:
        summary["note"] = ("--approve 미지정 — diff 이미지 경로만 보여줌. "
                            "육안 확인 후 --approve 재실행시 기준선 기록.")

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0 if summary["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
