"""WEB-OFFICE-CATALOG-FILL-SAMPLE-AUDIT — 카탈로그 매칭 실측(1단계 판정용).

기준서: docs/architecture 없음(신규 조사) — 계획 파일 참고.

upload_document_parser.parse_hwpx() → form_field_catalog(jsonl) 매칭 →
form_field_mapper.map_fields() → review_panel.build_review_panel() 를
실제 hwpx 파일로 처음 실행해본다. 이 파이프라인을 지금까지 실행하던 유일한
곳(tests/test_hwpx_form_auto_fill_e2e_smoke.py)이 전부 합성(가짜) 데이터만
써서, formName 완전일치 매칭이 실제 파일명으로 통하는지 한 번도 확인된 적이
없었다(2026-09-29 조사 확인).

이 스크립트는 아무것도 연결하지 않는다 — 매칭이 실전에서 되는지만 재는
순수 측정 스크립트. 원본 hwpx 무수정(parse_hwpx/map_fields/build_review_panel
전부 read-only).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from hwpx.pipeline.review_panel import build_panel_from_paths  # ruff: ignore[module-import-not-at-top-of-file]
from hwpx.recognition_corpus.form_type_classifier import classify_form_type  # ruff: ignore[module-import-not-at-top-of-file]

CATALOG_JSONL = ROOT / "data" / "reports" / "hwpx_form_field_catalog" / "form_field_catalog.jsonl"

# generate_wired_forms.py 의 DOCS 와 같은, 이미 검증된 실제 서식 3건.
# 참조 서식과 대상 서식을 같은 파일로 둔다 — "매칭 로직 자체가 실제
# 파일명으로 통하는가"부터 확인하는 최소 시험이라, 서로 다른 두 사본을
# 아직 못 구한 지금 단계에서는 자기 자신 매칭이 가장 정직한 첫 시험이다.
SAMPLES: list[str] = [
    "data/drafts/form_library/0393790f0e_16b6afa1e14849fc_02910_045_"
    "[별지_제22호의3서식]_공사_감리자_지정_신청서.hwpx",
    "data/drafts/form_library/022e3f35e6_6ff3fe63f13a8199_01076_035_"
    "[별지_제17호서식]_소방시설공사_완공검사신청서__A.hwpx",
    "data/drafts/form_library/035e67fa92_7e0e56c15d7fecd8_01315_072_"
    "[별지_제41호서식]_특정ㆍ준특정옥외탱크저장소의_구조안전점검시기_"
    "연장신청서(위험물의_저장관리_등의_상황).hwpx",
]


def run_sample() -> dict:
    reports = []
    for rel in SAMPLES:
        path = ROOT / rel
        form_name = classify_form_type(path).formName
        panel = build_panel_from_paths(path, CATALOG_JSONL)
        summary = panel.summary
        reports.append({
            "path": rel,
            "classifiedFormName": form_name,
            "catalogMatched": summary.autoFillCount
            + summary.reviewCount
            + summary.missingRequiredCount
            > 0,
            "autoFillCount": summary.autoFillCount,
            "reviewCount": summary.reviewCount,
            "missingRequiredCount": summary.missingRequiredCount,
            "missingOptionalCount": summary.missingOptionalCount,
        })

    matched = [r for r in reports if r["catalogMatched"]]
    return {
        "schemaVersion": "web_office_catalog_fill_sample_v1",
        "sampleCount": len(SAMPLES),
        "matchedCount": len(matched),
        "matchRatio": round(len(matched) / len(SAMPLES), 3),
        "reports": reports,
    }


def main() -> int:
    result = run_sample()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
