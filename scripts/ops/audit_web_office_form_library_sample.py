"""WEB-OFFICE-FORM-LIBRARY-SAMPLE-AUDIT — form_library 무작위 표본 전수 감리.

data/drafts/form_library (실제 서로 다른 정부 서식 5.4만건) 에서 재현 가능한
무작위 표본을 뽑아 audit_web_office_input_cell_corpus.audit_one 로 계통 감사.
5.4만건 전수는 시간이 과다해(문서당 수 초) 우선 표본으로 결함 유형·비율을
잡고, 필요 시 전수로 확장한다. read-only — 원본 무수정.
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/hwpx"))

from scripts.ops.audit_web_office_input_cell_corpus import audit_one  # noqa: E402

SEED = 20260723
SAMPLE_N = 500
LIB = ROOT / "data/drafts/form_library"


def main() -> int:
    files = sorted(LIB.glob("*.hwpx"))
    print(f"form_library 전체 {len(files)}건", file=sys.stderr)
    random.seed(SEED)
    sample = random.sample(files, min(SAMPLE_N, len(files)))

    results = []
    t0 = time.time()
    for i, p in enumerate(sample):
        try:
            r = audit_one(p, ROOT)
        except Exception as e:  # noqa: BLE001
            r = {"path": str(p.relative_to(ROOT)), "verdict": "ERROR",
                 "error": f"{type(e).__name__}: {e}"[:160]}
        results.append(r)
        if (i + 1) % 25 == 0:
            print(f"  진행 {i+1}/{len(sample)} "
                  f"({time.time()-t0:.0f}s)", file=sys.stderr)

    ok = sum(1 for r in results if r["verdict"] == "OK")
    warn = sum(1 for r in results if r["verdict"] == "WARN")
    err = sum(1 for r in results if r["verdict"] == "ERROR")
    kinds: dict[str, int] = {}
    for r in results:
        for w in r.get("warnings", []):
            k = w.split(":", 1)[0]
            kinds[k] = kinds.get(k, 0) + 1
    err_kinds: dict[str, int] = {}
    for r in results:
        if r["verdict"] == "ERROR":
            k = (r.get("error") or "?").split(":", 1)[0]
            err_kinds[k] = err_kinds.get(k, 0) + 1

    summary = {
        "schemaVersion": "web_office_form_library_sample_audit_v1",
        "libraryTotal": len(files),
        "sampleSize": len(sample),
        "seed": SEED,
        "ok": ok, "warn": warn, "error": err,
        "warningKinds": kinds,
        "errorKinds": err_kinds,
        "elapsedSec": round(time.time() - t0, 1),
        "worstErrors": [
            {"path": r["path"], "error": r.get("error")}
            for r in results if r["verdict"] == "ERROR"
        ][:15],
        "worstWarnSamples": [
            {"path": r["path"], "warnings": r.get("warnings", [])[:4]}
            for r in results if r["verdict"] == "WARN"
        ][:15],
    }
    Path(ROOT / "tmp/form_library_sample_report.json").write_text(
        json.dumps({"summary": summary, "results": results},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
