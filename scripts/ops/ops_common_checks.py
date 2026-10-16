"""audit_*/gate_* 스크립트가 각자 복사해 쓰던 작은 검사 함수의 공용 구현.

- 이 파일은 감사/게이트가 아니라 그들이 가져다 쓰는 라이브러리다. 이름을 `audit_`/`gate_` 로
  시작하지 않게 둔 것은 의도다 — 감사 스크립트 수집 패턴에 섞이지 않게 하려는 것(시험이 고정한다).
- 검사 강도는 호출하는 쪽이 정한다: 정규식·예외 메시지·기준 커밋은 전부 인자로 받고, 여기서
  기본값을 만들지 않는다(파일마다 정규식 리터럴이 달라서, 합치면 검사가 약해지거나 새 실패가 난다).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

# 유출 탐지 정규식의 정본. 감사/게이트가 파일마다 같은 리터럴을 복사해 쓰던 것을 한 곳에 둔다.
# RAW_FILENAME_RE 는 ".hwpx" 뒤에 하이픈·글자·점이 이어지는 이름(`a.hwpx-bak` 류)까지 잡는 쪽이다.
# 저장소 목록을 만드는 classify_hwpx_repo_inventory 만은 좁은 `(?![-\w.])` 변형을 따로 쓴다 —
# 저장소에 `Dockerfile.hwpx-ro-view` 가 실제로 있어, 넓은 쪽으로 합치면 그 보고서 쓰기가 막힌다(실측).
ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def redact_text(text: str, abs_re: re.Pattern[str], raw_re: re.Pattern[str], pii_re: re.Pattern[str]) -> str:
    """경로·hwpx 파일명·개인정보 패턴을 각각 `<abs-path>`·`<hwpx-file>`·`<masked>` 로 바꾼 문자열.

    정규식은 기본값 없는 필수 인자다 — 마스킹 강도는 호출하는 감사가 정하고, 여기서 정하지 않는다.
    """
    text = abs_re.sub("<abs-path>", text)
    text = raw_re.sub("<hwpx-file>", text)
    return pii_re.sub("<masked>", text)


def no_leak(text: str, *patterns: re.Pattern[str]) -> bool:
    """어느 패턴에도 걸리지 않으면 True. 패턴이 하나도 없으면 ValueError.

    패턴 없이 호출하면 아무것도 검사하지 않고 통과해 유출 검사가 조용히 꺼지므로, 호출 실수를
    통과가 아니라 실패로 드러낸다.
    """
    if not patterns:
        raise ValueError("no_leak: at least one pattern is required")
    return not any(p.search(text) for p in patterns)


def safe_write_json(path: Path, payload: Any, leak_free: Callable[[str], bool], error_prefix: str) -> None:
    """payload 를 JSON 으로 직렬화해 `leak_free(text)` 가 참일 때만 쓴다.

    `leak_free` 는 문자열을 받아 bool 을 돌려주는 함수다(각 감사의 `_no_leak`). 거짓이면
    파일을 쓰지 않고 `ValueError(f"{error_prefix}: {path.name}")` — 값은 메시지에 넣지 않는다.
    `leak_free` 가 None 이거나 호출할 수 없으면 검사가 꺼진 채 쓰이지 않도록 쓰기 전에 TypeError.
    """
    if not callable(leak_free):
        raise TypeError("safe_write_json: leak_free must be callable")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not leak_free(text):
        raise ValueError(f"{error_prefix}: {path.name}")
    path.write_text(text, encoding="utf-8")


def check_audit_no_writer_calls(source_file: str | Path, symbols: Iterable[str]) -> list[dict]:
    """감사 모듈 자신(`source_file`)의 소스에 금지된 writer 심볼(정규식)이 있으면 FAIL 항목으로 돌려준다.

    `source_file` 과 `symbols` 는 기본값 없는 필수 인자다 — 감사마다 금지 심볼 목록이 달라(두 그룹의 값이
    서로 다르다) 여기서 합치거나 기본값을 두지 않는다. 호출하는 감사가 `__file__` 과 자기 상수를 넘긴다.
    파일을 읽지 못하면 OSError 가 그대로 올라온다.
    """
    me = Path(source_file).read_text(encoding="utf-8")
    return [
        {"code": "AUDIT_FORBIDDEN_WRITER_CALL", "level": "FAIL", "detail": sym}
        for sym in symbols
        if re.search(sym, me)
    ]


def check_locked_files(
    locked_files: Iterable[str],
    baseline_commit: str,
    cwd: Path,
    timeout: int = 20,
    *,
    rc_failure_code: str = "GIT_DIFF_RC",
) -> list[dict]:
    """잠금 파일이 기준 커밋에서 바뀌었는지 `git diff` 로 확인한다(읽기 전용).

    반환 항목 코드: GIT_DIFF_FAILED(WARN) / rc_failure_code(WARN, 기본 GIT_DIFF_RC) /
    LOCKED_FILE_CHANGED(FAIL). rc≠0 일 때의 코드 문자열은 감사 보고서에 그대로 찍히므로,
    그 코드로 `GIT_DIFF_FAILED` 를 쓰던 감사는 `rc_failure_code="GIT_DIFF_FAILED"` 로 보존한다.
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
                "code": rc_failure_code,
                "level": "WARN",
                "detail": f"{rel}: rc={r.returncode}",
            })
            continue
        if r.stdout.strip():
            findings.append({"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": rel})
    return findings


def check_result(code: str, desc: str, ok: bool, fail_code: str | None = None) -> dict[str, Any]:
    """감사 점검 한 건의 결과 dict. `ok` 가 참이면 PASS, 아니면 FAIL 이고 그때만 `failCode` 가 채워진다.

    `ok` 는 불리언 변환 규칙 그대로 참/거짓을 가른다(복사본의 `"PASS" if ok` 와 같다).
    """
    return {"code": code, "desc": desc, "status": "PASS" if ok else "FAIL", "failCode": fail_code if not ok else None}


def load_json_file(path: str | None) -> Any:
    """`path` 가 비어 있지 않으면 UTF-8 JSON 파일을 읽어 돌려주고, None/빈 문자열이면 None.

    파일이 없거나 JSON 이 깨졌으면 OSError/JSONDecodeError 가 그대로 올라온다.
    """
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def missing_phrase_findings(src: str, phrases: list[str], code: str) -> list[dict]:
    """`src` 에 들어 있지 않은 문구마다 FAIL 항목(`code`, 문구는 detail)을 `phrases` 순서대로 돌려준다."""
    return [{"code": code, "level": "FAIL", "detail": phrase} for phrase in phrases if phrase not in src]


def node_available() -> bool:
    """`node --version` 이 성공(종료코드 0)하면 True. node 가 없거나 10초 안에 안 끝나면 False."""
    try:
        r = subprocess.run(
            ["node", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            check=False,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def pick_cell_paragraph(doc: Any) -> Any:
    """표 셀 안의 첫 문단 중 문단/글자 속성 참조와 2자 이상 텍스트가 있는 것을 돌려준다. 없으면 None."""
    for p in doc.paragraphs:
        cs = p.containerScope or {}
        if cs.get("kind") == "cell" and p.parPrIDRef and p.runs and p.runs[0].charPrIDRef and (len(p.text or "") >= 2):
            return p
    return None


def sha256_file(path: Path) -> str:
    """파일 내용의 sha256 16진수 문자열."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
