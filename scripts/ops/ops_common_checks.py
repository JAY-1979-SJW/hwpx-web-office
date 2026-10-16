"""audit_*/gate_* 스크립트가 각자 복사해 쓰던 작은 검사 함수의 공용 구현.

- 이 파일은 감사/게이트가 아니라 그들이 가져다 쓰는 라이브러리다. 이름을 `audit_`/`gate_` 로
  시작하지 않게 둔 것은 의도다 — 감사 스크립트 수집 패턴에 섞이지 않게 하려는 것(시험이 고정한다).
- 검사 강도는 호출하는 쪽이 정한다: 정규식·예외 메시지·기준 커밋은 전부 인자로 받고, 여기서
  기본값을 만들지 않는다(파일마다 정규식 리터럴이 달라서, 합치면 검사가 약해지거나 새 실패가 난다).
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any


def no_leak(text: str, *patterns: re.Pattern[str]) -> bool:
    """어느 패턴에도 걸리지 않으면 True. 패턴이 없으면 검사할 것이 없으므로 True."""
    return not any(p.search(text) for p in patterns)


def safe_write_json(path: Path, payload: Any, leak_free: Callable[[str], bool], error_prefix: str) -> None:
    """payload 를 JSON 으로 직렬화해 `leak_free(text)` 가 참일 때만 쓴다.

    `leak_free` 는 문자열을 받아 bool 을 돌려주는 함수다(각 감사의 `_no_leak`). 거짓이면
    파일을 쓰지 않고 `ValueError(f"{error_prefix}: {path.name}")` — 값은 메시지에 넣지 않는다.
    """
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not leak_free(text):
        raise ValueError(f"{error_prefix}: {path.name}")
    path.write_text(text, encoding="utf-8")


def check_locked_files(
    locked_files: Iterable[str],
    baseline_commit: str,
    cwd: Path,
    timeout: int = 20,
) -> list[dict]:
    """잠금 파일이 기준 커밋에서 바뀌었는지 `git diff` 로 확인한다(읽기 전용).

    반환 항목 코드: GIT_DIFF_FAILED(WARN) / GIT_DIFF_RC(WARN) / LOCKED_FILE_CHANGED(FAIL).
    """
    findings: list[dict] = []
    for rel in locked_files:
        try:
            r = subprocess.run(
                ["git", "diff", baseline_commit, "--", rel],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(cwd),
                timeout=timeout,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({"code": "GIT_DIFF_FAILED", "level": "WARN", "detail": f"{rel}: {e}"})
            continue
        if r.returncode != 0:
            findings.append({
                "code": "GIT_DIFF_RC",
                "level": "WARN",
                "detail": f"{rel}: rc={r.returncode}",
            })
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": rel})
    return findings
