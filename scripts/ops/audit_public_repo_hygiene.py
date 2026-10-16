#!/usr/bin/env python3
"""공개 저장소 위생 감사 — 추적 파일에 개인 경로·비밀값이 들어갔는지 검사한다.

검사 대상은 `git ls-files` 의 추적 파일이다. 출력은 파일 경로·줄 번호·패턴 이름뿐이며
매칭된 값은 절대 출력하지 않는다. 허용 목록(ALLOWED_FILES)에 없는 위반이 있으면 exit 1.
커밋 작성자 이메일이 noreply 가 아닌 경우는 개수만 경고한다(실패 아님, 이력은 재작성하지 않는다).

사용: python scripts/ops/audit_public_repo_hygiene.py [--root <저장소 경로>]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

# 접두어는 이어 붙여 만든다 — 이 파일 자신이 비밀값 패턴에 걸리지 않게 한다.
_GH = "gh" + "p_"
_SK = "s" + "k-"

# 이름 -> 정규식. 더미 사용자명(Public·test·example·<USER>)은 개인 경로로 보지 않는다.
PATTERNS: dict[str, re.Pattern[str]] = {
    "ABSOLUTE_USER_PATH": re.compile(
        r"[A-Za-z]:[\\/]+Users[\\/]+(?!(?:Public|test|example|User|USER|username)\b|<)[^\\/\s\"'<>]+"
    ),
    "ONEDRIVE_BUSINESS_FOLDER": re.compile(r"OneDrive[\\/]+[^\\/\s\"'<>]*[가-힣]"),
    "AWS_ACCESS_KEY": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GITHUB_TOKEN": re.compile(re.escape(_GH) + r"[A-Za-z0-9]{36}"),
    # 앞이 영숫자면 단어 중간(예: risk-...)이므로 비밀값으로 보지 않는다.
    "API_SECRET_KEY": re.compile(r"(?<![A-Za-z0-9])" + re.escape(_SK) + r"[A-Za-z0-9_-]{20,}"),
    "PRIVATE_KEY_BLOCK": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "SECRET_ASSIGNMENT": re.compile(
        r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][^'\"\s]{12,}['\"]"
    ),
}

# 허용 목록: (경로, 패턴 이름) -> (사유, 허용 최대 건수). 건수를 넘기면 위반이다 —
# 같은 파일에 새 위반이 더 들어와도 통과하지 못하게 한다. 파일 통째 제외는 금지이며,
# 새 항목은 경로·패턴·사유·건수를 모두 적고 코드리뷰를 받는다.
_DUMMY_PATH_REASON = "원시 경로 누출 감지 시험용 더미 문자열(실제 계정명 아님)"
ALLOWED_FILES: dict[tuple[str, str], tuple[str, int]] = {
    ("scripts/ops/audit_hwpx_form_auto_fill_real_file_preflight.py", "ABSOLUTE_USER_PATH"): (
        _DUMMY_PATH_REASON,
        1,
    ),
    ("tests/test_hwpx_form_auto_fill_real_file_preflight.py", "ABSOLUTE_USER_PATH"): (
        _DUMMY_PATH_REASON,
        1,
    ),
}

BINARY_ZIP_SUFFIXES = (".hwpx",)
ZIP_MEMBERS = ("Contents/content.hpf",)
MAX_TEXT_BYTES = 2_000_000


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    pattern: str


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=root, text=True, encoding="utf-8", errors="replace"
    )


def tracked_files(root: Path) -> list[str]:
    out = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def _lines_of(root: Path, rel: str) -> list[str]:
    path = root / rel
    if not path.is_file():
        return []
    if rel.lower().endswith(BINARY_ZIP_SUFFIXES):
        try:
            with zipfile.ZipFile(path) as zf:
                names = [n for n in ZIP_MEMBERS if n in zf.namelist()]
                return [
                    line
                    for n in names
                    for line in zf.read(n).decode("utf-8", errors="replace").splitlines()
                ]
        except (zipfile.BadZipFile, OSError):
            return []
    if path.stat().st_size > MAX_TEXT_BYTES:
        return []
    data = path.read_bytes()
    if b"\0" in data:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def scan(root: Path, files: list[str] | None = None) -> list[Finding]:
    """허용 목록 적용 전의 모든 위반(값은 담지 않는다)."""
    found: list[Finding] = []
    for rel in files if files is not None else tracked_files(root):
        for no, line in enumerate(_lines_of(root, rel), start=1):
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    found.append(Finding(rel.replace("\\", "/"), no, name))
    return found


def violations(findings: list[Finding]) -> list[Finding]:
    """허용 목록에 없거나, 허용 건수를 넘긴 위반만 돌려준다."""
    used: dict[tuple[str, str], int] = {}
    bad: list[Finding] = []
    for f in findings:
        key = (f.path, f.pattern)
        allowed = ALLOWED_FILES.get(key)
        used[key] = used.get(key, 0) + 1
        if allowed is None or used[key] > allowed[1]:
            bad.append(f)
    return bad


def non_noreply_author_count(root: Path, limit: int = 200) -> int:
    try:
        emails = _git(root, "log", f"-n{limit}", "--format=%ae").split()
    except subprocess.CalledProcessError:
        return 0
    return sum(1 for e in emails if not e.lower().endswith("noreply.github.com"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".", help="검사할 git 저장소 경로")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()

    findings = scan(root)
    bad = violations(findings)
    allowed = len(findings) - len(bad)
    for f in bad:
        print(f"VIOLATION {f.path}:{f.line} {f.pattern}")
    warn = non_noreply_author_count(root)
    if warn:
        print(f"WARN 최근 커밋 중 noreply 가 아닌 작성자 이메일 {warn}건 (값은 출력하지 않음)")
    print(f"hygiene: violations={len(bad)} allowed={allowed} files_scanned={len(tracked_files(root))}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
