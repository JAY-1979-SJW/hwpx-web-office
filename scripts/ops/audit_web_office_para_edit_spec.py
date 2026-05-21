"""WEB-OFFICE-PARA-EDIT-SPEC-01 감사 스크립트.

PARA-EDIT 시방서 + R-P3 별책이 시방서 검증 항목을 모두 포함하는지
정적으로 검사. 코드/writer/원본 접근 0건.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
SPEC_DOC = PR / "docs/architecture/web_office_para_edit_spec.md"
RISK_DOC = PR / "docs/architecture/web_office_para_edit_risk_ledger_update.md"

# 시방서 본권 필수 섹션 20개
REQUIRED_SPEC_SECTIONS = [
    "Phase 3 PARA-EDIT 목표",
    "비목표",
    "MVP-A 와의 경계",
    "문단 / Run 모델",
    "ParagraphTarget 모델",
    "TextRange 모델",
    "commandType 설계",
    "TYPE_TEXT 정책",
    "REPLACE_TEXT_RANGE 정책",
    "DELETE_TEXT_RANGE 정책",
    "run split / merge 정책",
    "charPrIDRef 보존 정책",
    "parPrIDRef 보존 정책",
    "expectedBefore / stale session 정책",
    "undo / redo 정책",
    "save / verify 정책",
    "readback 검증 기준",
    "위험대장 R-P3 항목",
    "Phase 3 구현 순서",
    "착공 승인 조건",
]

REQUIRED_SPEC_TOKENS = [
    # commandType
    "TYPE_TEXT", "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE",
    "SET_PARAGRAPH_TEXT_SAFE", "SPLIT_TEXT_RUN", "MERGE_TEXT_RUNS",
    "SET_CELL_TEXT",
    # 스타일 보존
    "charPrIDRef 보존", "parPrIDRef 보존",
    "ANCHOR_CHARPR", "FOCUS_CHARPR", "REQUIRES_REVIEW",
    "MERGE_CHARPR_MISMATCH",
    # expectedBefore / stale
    "expectedBefore", "STALE_SESSION",
    "EXPECTED_BEFORE_MISMATCH_PARAGRAPH",
    "compositionstart", "compositionend",
    # verify7 paragraph 확장
    "V1_RANGE_POSITION_OK", "V2_NO_CROSS_PARAGRAPH_LEAK",
    "V3_UNTOUCHED_RUNS_PRESERVED", "V4_CHARPR_PRESERVED",
    "V5_PARPR_PRESERVED", "V6_OUTPUT_ISOLATED",
    "V7_READBACK_MATCH",
    # applied=∅ + vacuous
    "applied=∅", "vacuous PASS", "DRY_RUN_NO_APPLIED",
    # MVP-A 보호
    "MVP-A", "SET_CELL_TEXT", "회귀", "89/89",
    "CELL-EDIT 코드 변경 금지",
    # 금지
    "원본 직접 수정" if False else "원본 HWPX 접근",
    "writer 호출", "output HWPX 생성",
    "브라우저에서 HWPX XML 직접 파싱",
    # 착공
    "착공 조건", "대표님 명시 승인",
]

REQUIRED_RISK_TOKENS = [
    "R-P3-01", "R-P3-02", "R-P3-03", "R-P3-04",
    "R-P3-05", "R-P3-06", "R-P3-07",
    "PLANNED", "활성화 트리거",
    "MERGE_CHARPR_MISMATCH",
    "V4_CHARPR_PRESERVED", "V5_PARPR_PRESERVED",
    "V2_NO_CROSS_PARAGRAPH_LEAK",
    "composition", "Enter",
    "COMMAND_TYPE_CONFLICT_IN_GROUP",
]


def _read(p: Path) -> str:
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def _no_code_or_hwpx_outputs() -> list[dict]:
    findings: list[dict] = []
    # 본 공정 산출물 디렉토리 .hwpx 0건
    for sub in ("docs/architecture", "scripts/ops",
                            "frontend/web_office_viewer",
                            "scripts/hwpx/web_office"):
        d = PR / sub
        if not d.is_dir():
            continue
        for f in d.glob("**/*.hwpx"):
            findings.append({"code": "UNEXPECTED_HWPX_OUTPUT",
                                      "level": "FAIL",
                                      "detail": str(f.relative_to(PR))})
    return findings


def _no_para_edit_impl_code_present() -> list[dict]:
    """SAVE-VERIFY7 / paragraph_edit_plan 등 후속 공정 파일이 있으면 FAIL.

    Note: para_edit_model.py / para_edit_normalizer.py /
    para_edit_command.mjs 등 모델 자재는 MODEL-01 공정의 정식 산출물로
    본 잠금 대상에서 제외한다 (MODEL-01 도입 후 본 SPEC 공정 잠금은
    SAVE-VERIFY7 단계 사전 진입을 막는 용도로 좁혔다).
    """
    # SAVE-VERIFY7-01 부분 준공 공정 진입 후 paragraph_edit_plan.py /
    # paragraph_save_pipeline.py 는 정식 산출물이므로 잠금 대상에서 제외.
    # 잔여 잠금 대상은 본 공정에서도 생성하지 않는 후속 자재.
    findings: list[dict] = []
    forbidden_impl = [
        PR / "scripts/hwpx/web_office/cell_para_save_pipeline.py",
        PR / "frontend/web_office_viewer/para_edit_save_runtime.mjs",
    ]
    for p in forbidden_impl:
        if p.is_file():
            findings.append({"code": "PARA_EDIT_IMPL_PRESENT",
                                      "level": "FAIL",
                                      "detail": str(p.relative_to(PR))})
    return findings


def audit() -> dict:
    findings: list[dict] = []
    spec = _read(SPEC_DOC)
    risk = _read(RISK_DOC)

    if not spec:
        findings.append({"code": "SPEC_DOC_MISSING", "level": "FAIL",
                                  "detail": str(SPEC_DOC.relative_to(PR))})
    if not risk:
        findings.append({"code": "RISK_DOC_MISSING", "level": "FAIL",
                                  "detail": str(RISK_DOC.relative_to(PR))})

    for sec in REQUIRED_SPEC_SECTIONS:
        if sec not in spec:
            findings.append({"code": "SPEC_SECTION_MISSING",
                                      "level": "FAIL", "detail": sec})

    for tok in REQUIRED_SPEC_TOKENS:
        if tok not in spec:
            findings.append({"code": "SPEC_TOKEN_MISSING",
                                      "level": "FAIL", "detail": tok})

    for tok in REQUIRED_RISK_TOKENS:
        if tok not in risk:
            findings.append({"code": "RISK_TOKEN_MISSING",
                                      "level": "FAIL", "detail": tok})

    findings.extend(_no_code_or_hwpx_outputs())
    findings.extend(_no_para_edit_impl_code_present())

    fail = sum(1 for f in findings if f["level"] == "FAIL")
    return {
        "task": "WEB-OFFICE-PARA-EDIT-SPEC-01",
        "specDoc": str(SPEC_DOC.relative_to(PR)),
        "riskDoc": str(RISK_DOC.relative_to(PR)),
        "requiredSectionsCount": len(REQUIRED_SPEC_SECTIONS),
        "requiredTokensCount": (len(REQUIRED_SPEC_TOKENS)
                                                  + len(REQUIRED_RISK_TOKENS)),
        "failCount": fail,
        "findings": findings,
        "verdict": "PASS" if fail == 0 else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
