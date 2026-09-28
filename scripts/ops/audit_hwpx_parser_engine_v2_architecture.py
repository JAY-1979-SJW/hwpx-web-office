"""
Audit script: HWPX-PARSER-ENGINE-V2-ARCHITECTURE-01.

Parser V2 아키텍처 문서·계약 문서·설계 문서의 존재와
필수 계약 항목 포함 여부를 정적 감사한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS_ARCH = PROJECT_ROOT / "docs" / "architecture"
DOCS_CONTRACTS = PROJECT_ROOT / "docs" / "contracts"
DOCS_REPORTS = PROJECT_ROOT / "docs" / "reports"

ARCH_DOC = DOCS_ARCH / "hwpx_parser_engine_v2_architecture.md"
CONTRACT_DOC = DOCS_CONTRACTS / "hwpx_parser_engine_v2_contract.md"
MODULE_SPLIT_DOC = DOCS_ARCH / "hwpx_parser_v2_module_split_plan.md"
STRUCT_VS_SEMANTIC_DOC = DOCS_ARCH / "document_structure_vs_semantic_analysis.md"
SLOT_DETECTOR_DOC = DOCS_ARCH / "hwpx_input_slot_detector_design.md"
FIXTURE_EXPECT_DOC = DOCS_REPORTS / "hwpx_parser_v2_fixture_expectations_20260517.md"

EDIT_TOOL = PROJECT_ROOT / "scripts" / "hwpx" / "hwpx_edit_tool.py"
PROFILER = PROJECT_ROOT / "scripts" / "local" / "hwpx_corpus_profiler.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def audit() -> dict:
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. 아키텍처 문서 존재
    check("architecture doc present", ARCH_DOC.exists(), str(ARCH_DOC))

    # 2. 계약 문서 존재
    check("contract doc present", CONTRACT_DOC.exists(), str(CONTRACT_DOC))

    # 3. 모듈 분리 계획 문서 존재
    check("module split plan present", MODULE_SPLIT_DOC.exists(), str(MODULE_SPLIT_DOC))

    # 4. 구조 vs 의미 분석 문서 존재
    check("structure vs semantic doc present", STRUCT_VS_SEMANTIC_DOC.exists(), str(STRUCT_VS_SEMANTIC_DOC))

    # 5. input slot detector 설계 문서 존재
    check("input slot detector design present", SLOT_DETECTOR_DOC.exists(), str(SLOT_DETECTOR_DOC))

    # 6. fixture expectation 문서 존재
    check("fixture expectation doc present", FIXTURE_EXPECT_DOC.exists(), str(FIXTURE_EXPECT_DOC))

    # 7. schemaVersion v2 명시 (계약 문서)
    contract_src = _read(CONTRACT_DOC)
    check("contract: schemaVersion v2 present",
          '"schemaVersion": "v2"' in contract_src or "schemaVersion.*v2" in contract_src,
          str(CONTRACT_DOC))

    # 8. blocks[] 계약 존재
    check("contract: blocks[] defined", "blocks[]" in contract_src or "## blocks" in contract_src,
          str(CONTRACT_DOC))

    # 9. tables[] 계약 존재
    check("contract: tables[] defined", "tables[]" in contract_src or "## tables" in contract_src,
          str(CONTRACT_DOC))

    # 10. cells[] 계약 존재
    check("contract: cells[] defined", "cells[]" in contract_src or "## cells" in contract_src,
          str(CONTRACT_DOC))

    # 11. styles 계약 존재
    check("contract: styles defined", "## styles" in contract_src or "styles 필드" in contract_src,
          str(CONTRACT_DOC))

    # 12. inputSlotCandidates 계약 존재
    check("contract: inputSlotCandidates defined",
          "inputSlotCandidates" in contract_src, str(CONTRACT_DOC))

    # 13. 구조/의미 경계 문서에 "구조 분석" + "의미 분석" 모두 포함
    ss_src = _read(STRUCT_VS_SEMANTIC_DOC)
    check("struct-semantic: 구조 분석 defined", "구조 분석" in ss_src, str(STRUCT_VS_SEMANTIC_DOC))
    check("struct-semantic: 의미 분석 defined", "의미 분석" in ss_src, str(STRUCT_VS_SEMANTIC_DOC))
    check("struct-semantic: confidence policy present", "confidence" in ss_src.lower(), str(STRUCT_VS_SEMANTIC_DOC))

    # 14. writer/editor 수정 없음 — architecture doc에서 명시
    arch_src = _read(ARCH_DOC)
    check("architecture: read-only principle stated",
          "read-only" in arch_src or "읽기 전용" in arch_src, str(ARCH_DOC))

    # 15. apply_edit_plan 호출 없음 — architecture doc에서 금지 명시
    check("architecture: apply_edit_plan forbidden stated",
          "apply_edit_plan" in arch_src, str(ARCH_DOC))

    # 16. HWP 변환 금지 명시
    check("architecture: HWP conversion forbidden stated",
          "HWP 변환" in arch_src or "HWP→HWPX" in arch_src, str(ARCH_DOC))

    # 17. OCR 금지 명시
    check("architecture: OCR forbidden stated", "OCR" in arch_src, str(ARCH_DOC))

    # 18. input slot detector 탐지 규칙 정의
    slot_src = _read(SLOT_DETECTOR_DOC)
    for rule in ["label_right", "label_below", "schedule_bar_range", "ignore"]:
        check(f"slot detector: {rule} rule defined", rule in slot_src, str(SLOT_DETECTOR_DOC))

    # 19. fixture expectation: 4개 fixture 모두 포함
    fx_src = _read(FIXTURE_EXPECT_DOC)
    for fx in ["fx_many_tables_page_marker", "fx_metadata_form",
               "fx_stamp_approval_legal", "fx_nested_legal_complex"]:
        check(f"fixture expectation: {fx} present", fx in fx_src, str(FIXTURE_EXPECT_DOC))

    # 20. module split plan: 7개 모듈 후보 포함
    split_src = _read(MODULE_SPLIT_DOC)
    for mod in ["package_reader", "block_parser", "table_parser",
                "style_parser", "layout_classifier", "input_slot_detector", "parser_contract"]:
        check(f"module split: {mod} planned", mod in split_src, str(MODULE_SPLIT_DOC))

    failed = [c for c in checks if c["status"] != "PASS"]
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "pass_count": len(checks) - len(failed),
        "fail_count": len(failed),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = audit()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"[hwpx_parser_engine_v2_architecture audit] {report['status']} "
              f"pass={report['pass_count']} fail={report['fail_count']}")
        for c in report["checks"]:
            mark = "OK" if c["status"] == "PASS" else "FAIL"
            print(f"  [{mark}] {c['name']}")
            if c["status"] != "PASS" and c["detail"]:
                print(f"        detail: {c['detail']}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
