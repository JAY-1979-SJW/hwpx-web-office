"""공용 검사 함수(ops_common_checks) 계약 시험 — 임시 폴더·임시 git 저장소만 사용한다."""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import classify_hwpx_repo_inventory as inventory
from scripts.ops import ops_common_checks as occ

MODULE_REL = "scripts/ops/ops_common_checks.py"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def _repo_with(tmp_path: Path, files: dict[str, str]) -> str:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        (tmp_path / rel).write_text(text, encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- no_leak -----------------------------------------------------------------


def test_01_no_leak_true_without_match() -> None:
    assert occ.no_leak("hello", re.compile("zzz"), re.compile("qqq")) is True


def test_02_no_leak_false_when_any_pattern_matches() -> None:
    assert occ.no_leak("hello zzz", re.compile("qqq"), re.compile("zzz")) is False


def test_03_no_leak_without_patterns_raises() -> None:
    # 패턴 없이 부르면 통과(True)가 아니라 실패 - 정규식을 빠뜨린 교체가 검사를 조용히 끄지 못한다.
    with pytest.raises(ValueError):
        occ.no_leak("anything")


# --- safe_write_json ----------------------------------------------------------


def test_04_safe_write_json_writes_when_clean(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    occ.safe_write_json(out, {"a": "한글"}, lambda t: True, "unsafe")
    assert out.read_text(encoding="utf-8") == '{\n  "a": "한글"\n}'


def test_05_safe_write_json_refuses_leak_and_does_not_echo_value(tmp_path: Path) -> None:
    out = tmp_path / "r.json"
    secret_like = "zz-marker-value"
    with pytest.raises(ValueError) as exc:
        occ.safe_write_json(out, {"k": secret_like}, lambda t: secret_like not in t, "FAIL_UNSAFE_REPORT")
    assert str(exc.value) == "FAIL_UNSAFE_REPORT: r.json"
    assert secret_like not in str(exc.value)
    assert not out.exists()


@pytest.mark.parametrize("bad", [None, "not-callable", 0])
def test_05b_safe_write_json_requires_callable_leak_check(tmp_path: Path, bad: object) -> None:
    out = tmp_path / "r.json"
    with pytest.raises(TypeError):
        occ.safe_write_json(out, {"a": 1}, bad, "unsafe")  # type: ignore[arg-type]
    assert not out.exists()


# --- check_locked_files -------------------------------------------------------


def test_06_locked_file_unchanged_has_no_findings(tmp_path: Path) -> None:
    base = _repo_with(tmp_path, {"a.txt": "one\n"})
    assert occ.check_locked_files(["a.txt"], base, tmp_path) == []


def test_07_locked_file_changed_is_fail(tmp_path: Path) -> None:
    base = _repo_with(tmp_path, {"a.txt": "one\n"})
    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")
    assert occ.check_locked_files(["a.txt"], base, tmp_path) == [
        {"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": "a.txt"}
    ]


def test_08_bad_baseline_is_warn_rc(tmp_path: Path) -> None:
    _repo_with(tmp_path, {"a.txt": "one\n"})
    found = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path)
    assert [f["code"] for f in found] == ["GIT_DIFF_RC"]
    assert found[0]["level"] == "WARN"


@pytest.mark.parametrize(
    "exc",
    [FileNotFoundError("git"), subprocess.TimeoutExpired(cmd="git", timeout=1)],
)
def test_09_git_unavailable_or_timeout_is_warn_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise exc

    monkeypatch.setattr(occ.subprocess, "run", boom)
    found = occ.check_locked_files(["a.txt"], "HEAD", tmp_path)
    assert [f["code"] for f in found] == ["GIT_DIFF_FAILED"]
    assert found[0]["level"] == "WARN"


def test_09b_rc_failure_code_default_keeps_git_diff_rc(tmp_path: Path) -> None:
    _repo_with(tmp_path, {"a.txt": "one\n"})
    explicit = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path, rc_failure_code="GIT_DIFF_RC")
    assert explicit == occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path)


def test_09c_rc_failure_code_changes_only_the_code(tmp_path: Path) -> None:
    _repo_with(tmp_path, {"a.txt": "one\n"})
    default = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path)
    custom = occ.check_locked_files(["a.txt"], "no-such-rev", tmp_path, rc_failure_code="GIT_DIFF_FAILED")
    assert [f["code"] for f in custom] == ["GIT_DIFF_FAILED"]
    assert [{k: v for k, v in f.items() if k != "code"} for f in custom] == [
        {k: v for k, v in f.items() if k != "code"} for f in default
    ]


def test_09d_rc_failure_code_is_keyword_only(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        occ.check_locked_files(["a.txt"], "HEAD", tmp_path, 20, "GIT_DIFF_FAILED")  # type: ignore[misc]


def test_09e_rc_failure_code_does_not_affect_changed_or_clean(tmp_path: Path) -> None:
    base = _repo_with(tmp_path, {"a.txt": "one\n", "b.txt": "one\n"})
    (tmp_path / "a.txt").write_text("two\n", encoding="utf-8")
    assert occ.check_locked_files(["b.txt", "a.txt"], base, tmp_path, rc_failure_code="GIT_DIFF_FAILED") == [
        {"code": "LOCKED_FILE_CHANGED", "level": "FAIL", "detail": "a.txt"}
    ]


# rc≠0 코드로 GIT_DIFF_FAILED 를 쓰던 감사 3개 - 보고서에 찍히는 이 문자열이 바뀌지 않게 고정한다.
_B_AUDITS = [
    "audit_web_office_para_adapter_applycharpr",
    "audit_web_office_para_edit_e2e_integration",
    "audit_web_office_para_readback_parser",
]


@pytest.mark.parametrize("name", _B_AUDITS)
def test_09f_b_group_audits_report_git_diff_failed_on_rc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    import importlib

    mod = importlib.import_module("scripts.ops." + name)
    _repo_with(tmp_path, {"a.txt": "one\n"})
    monkeypatch.setattr(mod, "PR", tmp_path)
    monkeypatch.setattr(mod, "BASELINE_COMMIT", "no-such-rev")
    monkeypatch.setattr(mod, "LOCKED_FILES", ["a.txt"])
    assert mod._check_locked_files() == [
        {"code": "GIT_DIFF_FAILED", "level": "WARN", "detail": "a.txt: rc=128"}
    ]


# --- 이름이 감사 수집 패턴에 섞이지 않는다 ---------------------------------------


def test_10_module_name_is_not_collected_as_audit_or_gate() -> None:
    name = Path(MODULE_REL).name
    # 감사 스크립트를 세거나 모으는 파일 이름 패턴(audit_*.py / gate_*.py)에 걸리지 않는다.
    assert not fnmatch.fnmatch(name, "audit_*.py")
    assert not fnmatch.fnmatch(name, "gate_*.py")
    # 분류기의 이름 토큰(audit_/gate_ 등)에도 걸리지 않는다 - 분류는 아래 정확한 경로 규칙이 정한다.
    lowered = MODULE_REL.lower()
    assert not any(tok in lowered for tok in ("audit_", "gate_", "verify_", "build_", "classify_"))


def test_11_module_has_no_audit_entrypoint() -> None:
    # 라이브러리라서 main/audit 진입점이 없다 — 있으면 감사로 오인된다.
    assert not hasattr(occ, "main")
    assert not hasattr(occ, "audit")


def test_12_classification_is_pinned_to_exact_path_and_name_only() -> None:
    # 새 공용 모듈은 정확한 경로 규칙으로 감사 지원 모듈(AUDIT_GATE/closeout_security)이 된다.
    assert inventory.classify_path(MODULE_REL) == ("AUDIT_GATE", "closeout_security", "keep_gate_audit")
    assert inventory.classify_path("tests/test_ops_common_checks.py")[1] == "closeout_security"
    # 넓은 접두사로 번지지 않는다 - 다른 ops_common_* 파일은 자동 편입되지 않는다.
    other = inventory.classify_path("scripts/ops/ops_common_other.py")
    assert other[0] != "AUDIT_GATE" and other[1] == "unassigned"
