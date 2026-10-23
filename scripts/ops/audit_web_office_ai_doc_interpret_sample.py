"""WEB-OFFICE-AI-DOC-INTERPRET-SAMPLE-AUDIT — 실제 서식 표본으로 run_dry_run 실측.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md §6 (수치 게이트)

editor_api_route.call_ai_fill_with_context(질문 패널이 실제로 타는 경로)를
그대로 통해 실제 Claude CLI(Haiku)로 실제 hwpx 서식 표본을 돌려 §6 게이트
(비창조 위반 0건 · 제3자 칸 제안 0건 · 주소 해석 실패 통과 0건)와 매핑률
(참고 지표)을 있는 그대로 측정한다. mock/가짜 runner 를 쓰지 않는다 —
실사용 가능 여부 판정은 실측이어야 한다(대표님 지시: "성공 기준과 품질
지수를 평가해서 최고 평가를 받아야 사용").

read-only — 원본 hwpx 는 절대 수정하지 않는다(run_dry_run 자체가 무기입).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.hwpx.web_office.editor_api_route import call_ai_fill_with_context  # ruff: ignore[module-import-not-at-top-of-file]

# generate_wired_forms.py 의 DOCS 와 같은, 이미 검증된 실제 서식 3건.
# 소스 데이터는 실제 개인정보가 아닌 시험용 예시값(이 프로젝트 테스트 관례와
# 동일한 "가나다전기"/"홍길동" 류)이다 — 매핑 정확도만 재는 것이 목적이라
# 실존 인물·업체 정보를 쓸 이유가 없다.
SAMPLES: list[dict] = [
    {
        "sourcePath": (
            "data/drafts/form_library/0393790f0e_16b6afa1e14849fc_02910_045_"
            "[별지_제22호의3서식]_공사_감리자_지정_신청서.hwpx"
        ),
        "sourceData": {
            "공사명": "가나다 신축공사",
            "현장명": "가나다 신축현장",
            "성명": "홍길동",
            "생년월일": "1980-01-01",
            "전화번호": "010-1234-5678",
            "주소": "서울특별시 강남구 테헤란로 1",
            "자격증번호": "12345",
            "착수일": "2026-01-01",
            "종료일": "2026-12-31",
        },
    },
    {
        "sourcePath": (
            "data/drafts/form_library/022e3f35e6_6ff3fe63f13a8199_01076_035_"
            "[별지_제17호서식]_소방시설공사_완공검사신청서__A.hwpx"
        ),
        "sourceData": {
            "공사명": "가나다 소방시설공사",
            "대표자": "홍길동",
            "전화번호": "010-1234-5678",
            "소재지": "서울특별시 강남구 테헤란로 1",
            "착공일": "2026-01-01",
            "완공일": "2026-06-30",
        },
    },
    {
        "sourcePath": (
            "data/drafts/form_library/035e67fa92_7e0e56c15d7fecd8_01315_072_"
            "[별지_제41호서식]_특정ㆍ준특정옥외탱크저장소의_구조안전점검시기_"
            "연장신청서(위험물의_저장관리_등의_상황).hwpx"
        ),
        "sourceData": {
            "상호": "가나다탱크",
            "대표자": "홍길동",
            "전화번호": "010-1234-5678",
            "소재지": "서울특별시 강남구 테헤란로 1",
            "탱크용량": "1000",
            "저장물질": "경유",
        },
    },
]


def run_sample() -> dict:
    reports = []
    for s in SAMPLES:
        envelope = call_ai_fill_with_context(
            {"sourcePath": s["sourcePath"], "sourceData": s["sourceData"]},
            project_root=ROOT,
        )
        report = envelope.get("data") or {}
        reports.append({"sourcePath": s["sourcePath"], **report})

    non_source_violations = sum(
        1
        for r in reports
        for p in (r.get("rejected") or [])
        if p.get("reason") == "NON_SOURCE_VALUE"
    )
    third_party_leaks = sum(
        1
        for r in reports
        for p in (r.get("proposals") or [])
        if p.get("key") in {h.get("key") for h in (r.get("heldForThirdParty") or [])}
    )
    address_failures_passed = sum(
        1 for r in reports for p in (r.get("proposals") or []) if p.get("addressFailure")
    )
    total_fields = sum(r.get("fieldCount", 0) for r in reports)
    total_accepted = sum(len(r.get("proposals") or []) for r in reports)
    coverage = round(total_accepted / total_fields, 3) if total_fields else 0.0

    gates_pass = (
        non_source_violations == 0 and third_party_leaks == 0 and address_failures_passed == 0
    )
    return {
        "schemaVersion": "web_office_ai_doc_interpret_sample_v1",
        "verdict": "PASS" if gates_pass else "FAIL",
        "sampleCount": len(SAMPLES),
        "totalFields": total_fields,
        "totalAccepted": total_accepted,
        "coverage": coverage,
        "baselineCoverage": 0.307,
        "gates": {
            "nonSourceViolations": non_source_violations,
            "thirdPartyLeaks": third_party_leaks,
            "addressFailuresPassed": address_failures_passed,
        },
        "reports": reports,
    }


def main() -> int:
    result = run_sample()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
