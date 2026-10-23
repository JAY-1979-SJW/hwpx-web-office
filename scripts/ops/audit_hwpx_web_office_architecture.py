"""HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01 감사 스크립트.

설계서 / 오픈소스 리뷰가 시방서의 필수 항목을 충족하는지 정적으로
검사한다. writer 호출·원본 HWPX 접근은 일절 하지 않는다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ARCH_DOC = PROJECT_ROOT / "docs/architecture/hwpx_web_office_editor_deep_architecture.md"
OSR_DOC = PROJECT_ROOT / "docs/architecture/hwpx_web_office_open_source_review.md"

REQUIRED_SECTIONS = [
    "목표와 비목표",
    "기존 HWPX 엔진 자산",
    "Web Office 전체 계층도",
    "DocumentModel schema",
    "Layout/Renderer 전략",
    "Selection/Cursor 전략",
    "Table/Cell editing 전략",
    "Paragraph editing 전략",
    "Image/Stamp/Signature 전략",
    "EditCommand",
    "Save",
    "PDF",
    "AI field mapping",
    "자재DB",
    "보안",
    "오픈소스 라이선스",
    "Phase",
    "MVP 부분 준공",
]

REQUIRED_REPO_LINKS = [
    "scripts/hwpx/parser/parser_engine.py",
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/ai_proposal/ai_proposal_contract.py",
    "scripts/hwpx/fill_review/fill_review_contract.py",
    "scripts/ops/verify_e2e_input_precision.py",
    "scripts/hwpx/master_orchestration/auto_fill_master.py",
]

OSR_REQUIRED_COLUMNS = ["라이선스", "결정"]
OSR_REQUIRED_VERDICTS = ["채택", "보류", "배제"]


def _read(p: Path) -> str:
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def _missing_findings(
    items: tuple[str, ...] | list[str], text: str, code: str, level: str
) -> list[dict]:
    return [{"code": code, "level": level, "detail": item} for item in items if item not in text]


def audit() -> dict:
    findings: list[dict] = []
    arch = _read(ARCH_DOC)
    osr = _read(OSR_DOC)

    if not arch:
        findings.append({"code": "ARCH_DOC_MISSING", "level": "FAIL", "detail": str(ARCH_DOC)})
    if not osr:
        findings.append({"code": "OSR_DOC_MISSING", "level": "FAIL", "detail": str(OSR_DOC)})

    findings.extend(_missing_findings(REQUIRED_SECTIONS, arch, "SECTION_MISSING", "FAIL"))
    findings.extend(_missing_findings(REQUIRED_REPO_LINKS, arch, "REPO_LINK_MISSING", "WARN"))
    findings.extend(_missing_findings(OSR_REQUIRED_COLUMNS, osr, "OSR_COLUMN_MISSING", "FAIL"))
    findings.extend(_missing_findings(OSR_REQUIRED_VERDICTS, osr, "OSR_VERDICT_MISSING", "FAIL"))
    # MVP / Phase / 부분 준공 토큰 (시방서 검증 항목)
    findings.extend(
        _missing_findings(
            ("MVP-A", "Phase 0", "부분 준공"), arch, "MVP_PHASE_TOKEN_MISSING", "FAIL"
        )
    )

    # writer 실행 금지 명시 (§11-1 ②, 시방서 금지 조항)
    if "writer 실행" not in arch or "금지" not in arch:
        findings.append({
            "code": "WRITER_FORBIDDEN_NOTE_MISSING",
            "level": "FAIL",
            "detail": "writer 실행 금지 문구 누락",
        })

    # 한컴 완전 호환을 1차 기준으로 잡지 말 것
    if not re.search(r"한컴.*완전 호환.*1차.*아니|한컴.*1차 목표.*아니", arch):
        findings.append({
            "code": "HANCOM_FULL_NOT_PRIMARY_MISSING",
            "level": "WARN",
            "detail": "한컴 완전 호환 비목표 명시 부족",
        })

    fail = sum(1 for f in findings if f["level"] == "FAIL")
    warn = sum(1 for f in findings if f["level"] == "WARN")
    verdict = "PASS" if fail == 0 and warn == 0 else ("WARN" if fail == 0 else "FAIL")
    return {
        "task": "HWPX-WEB-OFFICE-EDITOR-DEEP-ARCHITECTURE-01",
        "arch_doc": str(ARCH_DOC.relative_to(PROJECT_ROOT)),
        "osr_doc": str(OSR_DOC.relative_to(PROJECT_ROOT)),
        "required_sections": len(REQUIRED_SECTIONS),
        "fail_count": fail,
        "warn_count": warn,
        "findings": findings,
        "verdict": verdict,
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
