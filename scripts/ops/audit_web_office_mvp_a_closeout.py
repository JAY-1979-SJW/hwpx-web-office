"""WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01 감사 스크립트.

closeout 문서 + RISK-LEDGER 별책이 시방서의 필수 섹션 / 토큰을 모두
포함하는지 정적으로 검사한다. 원본 HWPX 접근·writer 호출 0건.
"""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
CLOSEOUT_DOC = PR / "docs/architecture/web_office_mvp_a_closeout.md"
RISK_DOC = PR / "docs/architecture/web_office_risk_ledger.md"

MVP_A_COMMIT = "87b3428"

REQUIRED_CLOSEOUT_SECTIONS = [
    "MVP-A 준공 범위",
    "지원 기능",
    "비지원 기능",
    "안전 게이트",
    "현재 한계",
    "Phase 3 PARA-EDIT 착공 조건",
    "회귀 테스트 목록",
    "위험대장",
    "다음 공정",
    "금지사항",
]

# 지원 / 비지원 / 안전 게이트 핵심 토큰 — 시방서 검증 항목
REQUIRED_CLOSEOUT_TOKENS = [
    # 지원
    "SET_CELL_TEXT", "EditCommand v1", "forward", "inverse",
    "undo", "redo", "save dry-run", "sandbox output",
    "verify7 V1~V7", "원본 sha/mtime 무변경",
    # 비지원
    "문단 run 편집", "표 행/열 추가", "셀 병합",
    "이미지", "도장", "서명", "AI 자동 입력",
    "다중 사용자 협업", "픽셀 단위 한컴 호환",
    "브라우저", "HWPX XML 직접 파싱", "원본 직접 수정",
    "원본 HWPX",
    # 안전 게이트
    "sourceDocumentHash mismatch", "expectedBefore mismatch",
    "outputPath == sourcePath", "vacuous PASS",
    "partial-success", "verify7 PASS 전",
    # 착공 조건
    "Phase 3", "착공 조건", "대표님",
    # commit anchor
    MVP_A_COMMIT,
]

REQUIRED_RISK_TOKENS = [
    "R-MA-01", "R-MA-02", "R-MA-03", "R-MA-04", "R-MA-05",
    "R-MA-06", "R-MA-07", "R-MA-08",
    "R-MA-09", "R-MA-10",
    "Phase 3", "Phase 6",
    "MITIGATED", "OPEN", "ACCEPTED",
    "변경 절차",
]


def _read(p: Path) -> str:
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def _no_new_hwpx_outputs() -> list[dict]:
    findings = []
    # 본 공정이 만든 .hwpx 산출물 0건 검사. tests/fixtures/ 는
    # 사전 fixture 자산이므로 제외 (closeout 공정과 무관).
    scan = [
        PR / "docs/architecture",
        PR / "scripts/ops",
        PR / "frontend/web_office_viewer",
        PR / "scripts/hwpx/web_office",
    ]
    for p in scan:
        if not p.is_dir():
            continue
        for f in p.glob("**/*.hwpx"):
            findings.append({"code": "UNEXPECTED_HWPX_OUTPUT",
                                      "level": "FAIL",
                                      "detail": str(f.relative_to(PR))})
    return findings


def _commit_is_reachable(sha: str) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--verify", sha + "^{commit}"],
            capture_output=True, text=True, timeout=10, cwd=str(PR))
        return r.returncode == 0
    except Exception:
        return False


def audit() -> dict:
    findings: list[dict] = []
    co = _read(CLOSEOUT_DOC)
    rl = _read(RISK_DOC)

    if not co:
        findings.append({"code": "CLOSEOUT_DOC_MISSING",
                                  "level": "FAIL",
                                  "detail": str(CLOSEOUT_DOC.relative_to(PR))})
    if not rl:
        findings.append({"code": "RISK_LEDGER_MISSING",
                                  "level": "FAIL",
                                  "detail": str(RISK_DOC.relative_to(PR))})

    for sec in REQUIRED_CLOSEOUT_SECTIONS:
        if sec not in co:
            findings.append({"code": "CLOSEOUT_SECTION_MISSING",
                                      "level": "FAIL", "detail": sec})

    for tok in REQUIRED_CLOSEOUT_TOKENS:
        if tok not in co:
            findings.append({"code": "CLOSEOUT_TOKEN_MISSING",
                                      "level": "FAIL", "detail": tok})

    for tok in REQUIRED_RISK_TOKENS:
        if tok not in rl:
            findings.append({"code": "RISK_TOKEN_MISSING",
                                      "level": "FAIL", "detail": tok})

    # commit anchor 가 실제 reachable 인지 확인
    if not _commit_is_reachable(MVP_A_COMMIT):
        findings.append({"code": "MVP_A_COMMIT_UNREACHABLE",
                                  "level": "WARN",
                                  "detail": MVP_A_COMMIT})

    # 본 공정은 writer/원본 접근 / output HWPX 0건
    findings.extend(_no_new_hwpx_outputs())

    fail = sum(1 for f in findings if f["level"] == "FAIL")
    warn = sum(1 for f in findings if f["level"] == "WARN")
    verdict = ("PASS" if fail == 0 and warn == 0 else
                          ("WARN" if fail == 0 else "FAIL"))
    return {
        "task": "WEB-OFFICE-MVP-A-PARTIAL-CLOSEOUT-RISK-LEDGER-01",
        "closeoutDoc": str(CLOSEOUT_DOC.relative_to(PR)),
        "riskDoc": str(RISK_DOC.relative_to(PR)),
        "mvpACommit": MVP_A_COMMIT,
        "requiredSectionsCount": len(REQUIRED_CLOSEOUT_SECTIONS),
        "requiredTokensCount": (len(REQUIRED_CLOSEOUT_TOKENS)
                                                  + len(REQUIRED_RISK_TOKENS)),
        "failCount": fail, "warnCount": warn,
        "findings": findings,
        "verdict": verdict,
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
