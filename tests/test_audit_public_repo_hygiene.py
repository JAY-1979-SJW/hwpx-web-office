"""공개 저장소 위생 감사(audit_public_repo_hygiene) 계약 시험 — 임시 git 저장소만 사용한다."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_public_repo_hygiene as hyg

BS = chr(92)
# 매칭 값이 출력에 새지 않는지 보려고 쓰는 표식 — 실제 비밀·계정이 아닌 가짜 값이다.
FAKE_USER = "zzfakeperson"
USER_PATH = "C:" + BS + "Users" + BS + FAKE_USER + BS + "doc"
FAKE_AWS = "AKIA" + "ABCDEFGHIJKLMNOP"


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


def test_01_clean_repo_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {"a.txt": "hello\n", "b/c.py": "x = 1\n"})
    assert hyg.main(["--root", str(root)]) == 0
    assert "violations=0" in capsys.readouterr().out


def test_02_user_path_outside_allowlist_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {"docs/note.md": f"path {USER_PATH}\n"})
    assert hyg.main(["--root", str(root)]) == 1
    out = capsys.readouterr().out
    assert "VIOLATION docs/note.md:1 ABSOLUTE_USER_PATH" in out


def test_03_output_never_contains_matched_value(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, {"x.txt": f"{USER_PATH}\nkey {FAKE_AWS}\n"})
    assert hyg.main(["--root", str(root)]) == 1
    captured = capsys.readouterr()
    text = captured.out + captured.err
    assert FAKE_USER not in text
    assert FAKE_AWS not in text
    assert "AWS_ACCESS_KEY" in text


@pytest.mark.parametrize(
    "line",
    [
        "C:" + BS + "Users" + BS + "Public" + BS + "x",
        "C:" + BS + "Users" + BS + "<USER>" + BS + "x",
        "Cost of risk-" + "a" * 30,
    ],
)
def test_04_dummy_and_word_internal_values_are_not_flagged(tmp_path: Path, line: str) -> None:
    root = _repo(tmp_path, {"ok.txt": line + "\n"})
    assert hyg.violations(hyg.scan(root)) == []


def test_05_real_looking_secret_assignment_is_flagged(tmp_path: Path) -> None:
    secret_line = 'api_key = "' + "q" * 20 + '"\n'
    root = _repo(tmp_path, {"cfg.py": secret_line})
    names = {f.pattern for f in hyg.scan(root)}
    assert "SECRET_ASSIGNMENT" in names


def test_06_allowlist_permits_listed_path_but_not_other_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, {"allowed/t.py": USER_PATH + "\n", "other/u.py": USER_PATH + "\n"})
    monkeypatch.setattr(
        hyg, "ALLOWED_FILES", {("allowed/t.py", "ABSOLUTE_USER_PATH"): ("시험용 더미", 1)}
    )
    bad = hyg.violations(hyg.scan(root))
    assert [(f.path, f.pattern) for f in bad] == [("other/u.py", "ABSOLUTE_USER_PATH")]


def test_07_allowlist_count_cap_blocks_extra_violation_in_same_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _repo(tmp_path, {"allowed/t.py": USER_PATH + "\n" + USER_PATH + "\n"})
    monkeypatch.setattr(
        hyg, "ALLOWED_FILES", {("allowed/t.py", "ABSOLUTE_USER_PATH"): ("시험용 더미", 1)}
    )
    bad = hyg.violations(hyg.scan(root))
    assert [(f.path, f.line) for f in bad] == [("allowed/t.py", 2)]


def test_08_allowlist_is_per_pattern(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path, {"allowed/t.py": USER_PATH + "\n" + FAKE_AWS + "\n"})
    monkeypatch.setattr(
        hyg, "ALLOWED_FILES", {("allowed/t.py", "ABSOLUTE_USER_PATH"): ("시험용 더미", 1)}
    )
    assert [f.pattern for f in hyg.violations(hyg.scan(root))] == ["AWS_ACCESS_KEY"]


def test_09_hwpx_manifest_is_scanned_but_other_members_are_not(tmp_path: Path) -> None:
    sub = tmp_path / "docs"
    sub.mkdir()
    z = sub / "f.hwpx"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Contents/content.hpf", USER_PATH)
        zf.writestr("Contents/section0.xml", FAKE_AWS)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    names = {(f.path, f.pattern) for f in hyg.scan(tmp_path)}
    assert names == {("docs/f.hwpx", "ABSOLUTE_USER_PATH")}


def test_10_binary_and_oversized_files_are_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _repo(tmp_path, {"t.txt": USER_PATH + "\n"})
    (root / "bin.dat").write_bytes(b"\0" + USER_PATH.encode())
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert {f.path for f in hyg.scan(root)} == {"t.txt"}
    monkeypatch.setattr(hyg, "MAX_TEXT_BYTES", 5)
    assert hyg.scan(root) == []


def test_11_real_repo_head_has_no_violations() -> None:
    """이 저장소의 추적 파일 자체가 감사를 통과해야 한다(허용 목록 밖 위반 0)."""
    assert hyg.violations(hyg.scan(ROOT)) == []


def test_12_korean_warning_does_not_crash_on_cp1252_console(tmp_path: Path) -> None:
    """CI 윈도우 콘솔(cp1252)에서 한글 경고 출력이 인코딩 오류로 죽던 결함의 회귀 시험."""
    root = _repo(tmp_path, {"a.txt": "hello\n"})
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "-m", "x"],
        cwd=root,
        check=True,
    )
    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ops" / "audit_public_repo_hygiene.py"), "--root", str(root)],
        capture_output=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert b"Traceback" not in proc.stderr
