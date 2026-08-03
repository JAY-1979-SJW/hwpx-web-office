"""새 진단/스크립트 파일에서 '장황한 통째 출력' 패턴을 감지한다.

토큰 절감 원칙(CLAUDE.md §3-A) 기술 집행 — pre-commit 필수 게이트는
아니고(기존 게이트 체인에 얽히면 위험도가 크다), 필요할 때 수동으로
돌려서 새로 짠 스크립트를 점검하는 보조 도구다.

탐지 패턴:
  - print(json.dumps(x, indent=...))  x 크기 제한/필터링 없이 통째 출력
  - print(json.dumps(x, ensure_ascii=False, indent=...))  동일 패턴
  - pprint.pprint(대상)  전체 구조 그대로 찍기

사용:
    python scripts/ops/audit_verbose_output_lint.py <파일...>
    python scripts/ops/audit_verbose_output_lint.py $(git diff --cached --name-only -- '*.py')
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# json.dumps(... indent= ...) 를 print()/직접 출력하는 패턴.
# 앞에 슬라이스([:N]) 나 필터링(예: {k: v for ...}) 흔적이 없으면 의심.
_JSON_DUMP_PRINT_RE = re.compile(
    r'print\(\s*json\.dumps\([^)]*indent\s*=', re.MULTILINE)
_PPRINT_RE = re.compile(r'\bpprint\.pprint\(')
_SLICE_HINT_RE = re.compile(r'\[:\d+\]|\[:N\]|head\(|\.head\b')


def scan_file(path: Path) -> list[tuple[int, str]]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    lines = text.splitlines()
    for i, line in enumerate(lines, 1):
        if _JSON_DUMP_PRINT_RE.search(line):
            # 같은 줄이나 바로 위 몇 줄에 슬라이스/제한 흔적이 있으면 통과
            context = "\n".join(lines[max(0, i - 3):i])
            if not _SLICE_HINT_RE.search(context):
                findings.append((i, "json.dumps(..., indent=..) 통째 출력 의심 - 필드 선별/슬라이스 권장"))
        if _PPRINT_RE.search(line):
            findings.append((i, "pprint.pprint() 전체 구조 출력 - 필요한 키만 뽑아 출력 권장"))
    return findings


def main(argv: list[str]) -> int:
    if not argv:
        print("사용법: audit_verbose_output_lint.py <파일...>")
        return 0

    total = 0
    for arg in argv:
        path = Path(arg)
        if not path.is_file() or path.suffix != ".py":
            continue
        findings = scan_file(path)
        if findings:
            print(f"\n{path}:")
            for line_no, msg in findings:
                print(f"  L{line_no}: {msg}")
            total += len(findings)

    if total:
        print(f"\n[audit_verbose_output_lint] {total}건 발견 (참고용 - 커밋을 막지 않음)")
    else:
        print("[audit_verbose_output_lint] 발견 없음")
    return 0  # 정보성 - 항상 0 반환(빌드를 막지 않음)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
