"""post_commit 훅: devlog 생성(외부 claude CLI 호출)은 HWPX_DEVLOG_GENERATE=1 일 때만."""

import importlib.util
import subprocess
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "hooks" / "post_commit.py"


def _load():
    spec = importlib.util.spec_from_file_location("post_commit_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=dev", "-c", "user.email=dev@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    # post_commit.main() 이 `git config user.name` 을 읽는다 — 전역 설정이 없는 CI 에서도 읽히게 저장소 로컬로 둔다.
    _git(repo, "config", "user.name", "dev")
    (repo / "a.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-q", "-m", "feat: sample")
    return repo


def test_enabled_only_when_env_is_exactly_one():
    module = _load()
    assert module.devlog_generation_enabled({}) is False
    assert module.devlog_generation_enabled({"HWPX_DEVLOG_GENERATE": "0"}) is False
    assert module.devlog_generation_enabled({"HWPX_DEVLOG_GENERATE": "true"}) is False
    assert module.devlog_generation_enabled({"HWPX_DEVLOG_GENERATE": "1"}) is True


def test_main_skips_devlog_and_external_call_by_default(tmp_path, monkeypatch):
    module = _load()
    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.delenv("HWPX_DEVLOG_GENERATE", raising=False)
    calls = []
    monkeypatch.setattr(module, "claude_available", lambda: calls.append("available") or True)
    monkeypatch.setattr(module, "generate_devlog_claude", lambda *a, **k: calls.append("claude"))

    module.main()

    assert calls == []
    assert not (repo / "docs" / "devlog").exists()
    assert (repo / "logs" / "change_history.jsonl").exists()


def test_main_writes_devlog_when_opted_in(tmp_path, monkeypatch):
    module = _load()
    repo = _make_repo(tmp_path)
    monkeypatch.chdir(repo)
    monkeypatch.setenv("HWPX_DEVLOG_GENERATE", "1")
    monkeypatch.delenv("ALLOW_POST_COMMIT_AUTO_COMMIT", raising=False)
    monkeypatch.setattr(module, "claude_available", lambda: False)

    module.main()

    devlogs = list((repo / "docs" / "devlog").glob("*.md"))
    assert len(devlogs) == 1
