"""세션 점유 게이트 감리.

여러 세션이 같은 저장소를 쓸 때 서로의 파일을 커밋에 쓸어담는 사고를
막는 장치다. 막는 것보다 **잘못 막지 않는 것**이 더 중요해서, 통과해야
하는 경우를 더 촘촘히 고정한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.ops import gate_hwpx_session_claim as G  # ruff: ignore[module-import-not-at-top-of-file]


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """실제 저장소의 점유 파일을 건드리지 않는다."""
    monkeypatch.setattr(G, "CLAIM_FILE", tmp_path / "claims.json")
    monkeypatch.setattr(G, "LOG_FILE", tmp_path / "claims.jsonl")
    yield


# ── 막아야 하는 경우 ────────────────────────────────────────────


def test_other_session_claim_blocks(monkeypatch):
    G.claim("S_OTHER", ["scripts/a.py"], note="좌표 수리")
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    r = G.check("S_ME")
    assert r["verdict"] == G.FAIL
    assert r["conflicts"][0]["session"] == "S_OTHER"
    assert r["conflicts"][0]["paths"] == ["scripts/a.py"]


def test_partial_overlap_blocks(monkeypatch):
    """내 파일에 남의 파일이 하나만 섞여도 막는다 — 실제 사고 형태."""
    G.claim("S_OTHER", ["scripts/theirs.py"])
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/mine.py", "scripts/theirs.py"])
    r = G.check("S_ME")
    assert r["verdict"] == G.FAIL
    assert r["conflicts"][0]["paths"] == ["scripts/theirs.py"]


def test_path_separator_normalized(monkeypatch):
    """윈도우 역슬래시로 점유해도 git 의 슬래시 경로와 맞물려야 한다."""
    G.claim("S_OTHER", [r"scripts\ops\x.py"])
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/ops/x.py"])
    assert G.check("S_ME")["verdict"] == G.FAIL


def test_dotted_path_not_mangled(monkeypatch):
    """점으로 시작하는 경로가 깎이면 안 된다.

    lstrip("./") 은 선행 '.' 과 '/' 를 전부 깎아 `.githooks/pre-commit` 을
    `githooks/pre-commit` 으로 만든다 — 훅·설정 파일이 게이트에서 통째로
    빠진다(실제로 그렇게 새어 나갔다).
    """
    r = G.claim("S_OTHER", [".githooks/pre-commit", ".claude/settings.json"])
    assert ".githooks/pre-commit" in r["claimed"]
    monkeypatch.setattr(G, "_staged_files", lambda: [".githooks/pre-commit"])
    assert G.check("S_ME")["verdict"] == G.FAIL


def test_leading_dot_slash_stripped(monkeypatch):
    """`./scripts/a.py` 와 `scripts/a.py` 는 같은 파일이다."""
    G.claim("S_OTHER", ["./scripts/a.py"])
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.FAIL


# ── 통과해야 하는 경우 (오탐이 더 위험하다) ─────────────────────


def test_own_claim_does_not_block(monkeypatch):
    G.claim("S_ME", ["scripts/a.py"])
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.PASS


def test_unclaimed_files_pass(monkeypatch):
    G.claim("S_OTHER", ["scripts/a.py"])
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/b.py"])
    assert G.check("S_ME")["verdict"] == G.PASS


def test_no_claim_file_passes(monkeypatch):
    """점유 파일이 아예 없으면 통과 — 게이트 부재가 작업을 막지 않는다."""
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.PASS


def test_corrupt_claim_file_passes(monkeypatch):
    """깨진 점유 파일에도 통과 — 고장이 저장소를 잠그면 안 된다."""
    G.CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    G.CLAIM_FILE.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.PASS


def test_stale_claim_ignored(monkeypatch):
    """세션이 죽어도 저장소가 영구히 잠기지 않는다."""
    G.claim("S_DEAD", ["scripts/a.py"])
    data = json.loads(G.CLAIM_FILE.read_text(encoding="utf-8"))
    data["claims"][0]["heartbeatAt"] = G._now() - (G.STALE_AFTER_SEC + 60)
    G.CLAIM_FILE.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.PASS


def test_heartbeat_keeps_claim_alive(monkeypatch):
    G.claim("S_OTHER", ["scripts/a.py"])
    data = json.loads(G.CLAIM_FILE.read_text(encoding="utf-8"))
    data["claims"][0]["heartbeatAt"] = G._now() - (G.STALE_AFTER_SEC + 60)
    G.CLAIM_FILE.write_text(json.dumps(data), encoding="utf-8")
    G.heartbeat("S_OTHER")
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.FAIL, "heartbeat 후엔 다시 살아야 한다"


def test_nothing_staged_passes(monkeypatch):
    G.claim("S_OTHER", ["scripts/a.py"])
    monkeypatch.setattr(G, "_staged_files", list)
    assert G.check("S_ME")["verdict"] == G.PASS


def test_release_unblocks(monkeypatch):
    G.claim("S_OTHER", ["scripts/a.py"])
    monkeypatch.setattr(G, "_staged_files", lambda: ["scripts/a.py"])
    assert G.check("S_ME")["verdict"] == G.FAIL
    G.release("S_OTHER")
    assert G.check("S_ME")["verdict"] == G.PASS


# ── 점유 관리 ───────────────────────────────────────────────────


def test_reclaim_replaces_not_appends():
    G.claim("S_ME", ["a.py"])
    G.claim("S_ME", ["b.py"])
    live = G.live_claims()
    assert len(live) == 1
    assert live[0]["paths"] == ["b.py"]


def test_claim_reports_conflict_at_declaration():
    """선언 시점에 이미 남이 잡고 있으면 알려준다(막지는 않는다)."""
    G.claim("S_OTHER", ["a.py"])
    r = G.claim("S_ME", ["a.py", "b.py"])
    assert r["conflicts"] and r["conflicts"][0]["session"] == "S_OTHER"


def test_status_counts_live_and_stale():
    G.claim("S1", ["a.py"])
    G.claim("S2", ["b.py"])
    data = json.loads(G.CLAIM_FILE.read_text(encoding="utf-8"))
    data["claims"][0]["heartbeatAt"] = G._now() - (G.STALE_AFTER_SEC + 60)
    G.CLAIM_FILE.write_text(json.dumps(data), encoding="utf-8")
    s = G.status()
    assert len(s["live"]) == 1
    assert s["staleIgnored"] == 1


def test_append_only_log_records_events():
    G.claim("S1", ["a.py"], note="시공")
    G.release("S1")
    lines = [
        json.loads(x) for x in G.LOG_FILE.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    assert [x["event"] for x in lines] == ["claim", "release"]


# ── 훅 배선 ─────────────────────────────────────────────────────


def test_pre_commit_hook_invokes_guard():
    # 2026-09-13 commit-checklist-wrapper 도입 후 pre-commit 은 체크리스트만
    # 돌리고, 기존 가드 체인(session claim + repo guard)은 그 안에서 호출하는
    # pre-commit.orig 로 옮겨갔다 — 실제 배선은 두 파일을 합친 것이다.
    hook = PR / ".githooks" / "pre-commit"
    assert hook.is_file(), "pre-commit 훅이 없다"
    src = hook.read_text(encoding="utf-8")
    orig = PR / ".githooks" / "pre-commit.orig"
    if orig.is_file():
        src += "\n" + orig.read_text(encoding="utf-8")
    assert "gate_hwpx_session_claim.py --check" in src, "게이트가 배선되지 않았다"
    assert "run_hwpx_repo_commit_guard.py" in src, "기존 가드가 사라졌다"
    # 앞 가드가 실패해도 뒤가 실행돼 결과가 묻히지 않도록 || exit 1 로 끊는다
    assert src.count("|| exit 1") >= 2, "가드 실패가 무시될 수 있는 배선"
