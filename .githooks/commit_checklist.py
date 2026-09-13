#!/usr/bin/env python
# -*- coding: utf-8 -*-
# module_category: audit
# primary_trade: common
"""커밋 전 체크리스트 — 모든 저장소 공통 pre-commit 검사기(표준 라이브러리만).

기준서: C:/work/03. cad-program/docs/specs/2026-09-13_커밋전_체크리스트_전저장소_훅강제_spec.md
원본: 03. cad-program/scripts/ops/commit_checklist/commit_checklist.py — 각 저장소 .githooks/ 에 사본 배포.

스테이징된 파일을 검사하고 결과를 .git/commit_checklist_last.md 로 생성한다. 차단 항목이 하나라도
있으면 종료코드 1. 우회: 환경변수 SKIP_COMMIT_CHECKLIST=<사유>(사유 필수, 리포트에 기록).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import re
import subprocess
import sys
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

MAX_BYTES = 50 * 1024 * 1024
SCAN_TEXT_MAX = 2 * 1024 * 1024

SECRET_NAME_PATTERNS = [
    re.compile(r"(^|/)\.env(\.[^/]*)?$", re.I),
    re.compile(r"\.(pem|key|pfx|p12)$", re.I),
    re.compile(r"(^|/)id_(rsa|dsa|ecdsa|ed25519)$", re.I),
    re.compile(r"(^|/)credentials[^/]*\.json$", re.I),
]
SECRET_NAME_ALLOW = [re.compile(r"(^|/)\.env\.(example|sample|template)$", re.I)]
SECRET_CONTENT_PATTERNS = [
    ("Anthropic API 키", re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API 키", re.compile(r"sk-(proj-)?[A-Za-z0-9]{32,}")),
    ("AWS 액세스 키", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub 토큰", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("개인키", re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA |)PRIVATE KEY-----")),
]
CONFLICT_RE = re.compile(r"^(<{7} |>{7} )", re.M)


def _git(args: List[str], cwd: Optional[str] = None, binary: bool = False):
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if out.returncode != 0:
        raise RuntimeError(out.stderr.decode("utf-8", "replace").strip())
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def staged_files(cwd: Optional[str] = None) -> List[str]:
    raw = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd, binary=True)
    return [p.decode("utf-8", "replace") for p in raw.split(b"\0") if p]


def staged_blob(path: str, cwd: Optional[str] = None) -> bytes:
    return _git(["show", f":{path}"], cwd, binary=True)


def check_secret_name(path: str) -> Optional[str]:
    p = path.replace("\\", "/")
    if any(a.search(p) for a in SECRET_NAME_ALLOW):
        return None
    for pat in SECRET_NAME_PATTERNS:
        if pat.search(p):
            return f"비밀정보 파일명 의심: {path}"
    return None


def check_content(path: str, data: bytes) -> List[str]:
    issues: List[str] = []
    if len(data) > MAX_BYTES:
        issues.append(f"대용량 파일 {len(data) / 1024 / 1024:.1f}MB > 50MB: {path}")
        return issues
    if b"\0" in data[:8000] or len(data) > SCAN_TEXT_MAX:
        return issues
    text = data.decode("utf-8", "replace")
    for label, pat in SECRET_CONTENT_PATTERNS:
        if pat.search(text):
            issues.append(f"{label} 의심 문자열: {path}")
    if CONFLICT_RE.search(text):
        issues.append(f"병합 충돌 마커: {path}")
    suffix = PurePosixPath(path.replace("\\", "/")).suffix.lower()
    if suffix == ".py":
        try:
            compile(text, path, "exec")
        except SyntaxError as e:
            issues.append(f"파이썬 문법 오류 {path}:{e.lineno} {e.msg}")
    elif suffix == ".json":
        try:
            json.loads(text.lstrip("\ufeff"))
        except ValueError as e:
            issues.append(f"JSON 문법 오류 {path}: {e}")
    return issues


def run_checklist(cwd: Optional[str] = None) -> Tuple[bool, Dict[str, List[str]], List[str]]:
    files = staged_files(cwd)
    results: Dict[str, List[str]] = {
        # 빈 커밋·메시지만 수정(--amend)은 정상 작업이라 차단하지 않는다(실측: 3개 저장소 과잉차단).
        "1. 스테이징 파일 검사 대상": [],
        "2. 비밀정보(파일명·내용)": [],
        "3. 병합 충돌 마커": [],
        "4. 대용량 파일(>50MB)": [],
        "5. 파이썬 문법": [],
        "6. JSON 문법": [],
    }
    for f in files:
        n = check_secret_name(f)
        if n:
            results["2. 비밀정보(파일명·내용)"].append(n)
        try:
            data = staged_blob(f, cwd)
        except RuntimeError:
            continue
        for issue in check_content(f, data):
            if "의심 문자열" in issue:
                results["2. 비밀정보(파일명·내용)"].append(issue)
            elif "충돌" in issue:
                results["3. 병합 충돌 마커"].append(issue)
            elif "대용량" in issue:
                results["4. 대용량 파일(>50MB)"].append(issue)
            elif "파이썬" in issue:
                results["5. 파이썬 문법"].append(issue)
            elif "JSON" in issue:
                results["6. JSON 문법"].append(issue)
    ok = all(not v for v in results.values())
    return ok, results, files


def write_report(git_dir: str, ok: bool, results: Dict[str, List[str]], files: List[str], skip_reason: str) -> str:
    lines = [f"# 커밋 전 체크리스트 — {_dt.datetime.now().isoformat(timespec='seconds')}",
             f"판정: {'PASS' if ok else ('BYPASS(' + skip_reason + ')' if skip_reason else 'FAIL')}",
             f"스테이징 파일 {len(files)}개", ""]
    for k, v in results.items():
        lines.append(f"- [{'x' if not v else ' '}] {k}" + ("" if not v else f" — {len(v)}건"))
        lines += [f"    - {i}" for i in v[:50]]
    lines.append("\n저장소 고유 게이트(기준서·lane·테스트 등)는 기존 훅(pre-commit.orig·commit-msg)이 이어서 검사한다.")
    path = os.path.join(git_dir, "commit_checklist_last.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def main() -> int:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    git_dir = _git(["rev-parse", "--git-dir"]).strip()
    ok, results, files = run_checklist()
    skip = os.environ.get("SKIP_COMMIT_CHECKLIST", "").strip()
    report = write_report(git_dir, ok, results, files, skip if not ok else "")
    print("=" * 60)
    print("[커밋 전 체크리스트] " + ("PASS" if ok else "FAIL"))
    for k, v in results.items():
        print(f"  {'✓' if not v else '✗'} {k}" + ("" if not v else f" ({len(v)}건)"))
        for i in v[:10]:
            print(f"      - {i}")
    print(f"  리포트: {report}")
    if ok:
        return 0
    if skip:
        print(f"[우회] SKIP_COMMIT_CHECKLIST={skip} — 리포트에 기록됨")
        return 0
    print("커밋 차단 — 위 항목을 고친 뒤 다시 커밋하세요(우회: SKIP_COMMIT_CHECKLIST=<사유>).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
