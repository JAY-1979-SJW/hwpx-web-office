"""HWPX-AI-FILL-USAGE-METERING-GATE-01 감리검사.

무료 한도 하드캡 / 계량 로그 / 플랜별 통과를 검증한다.
외부 의존 없음 — temp 파일로 격리 실행.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))

import usage_metering_gate as gate


@pytest.fixture
def tmp_log(tmp_path: Path) -> Path:
    """격리된 계량 로그 파일 경로 — usage_metering_gate 가 append 로 채운다."""
    return tmp_path / "usage.log"


# 결정적 테스트를 위한 고정 시각(청구 기간 = 2026-07)
FIXED_NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=UTC)


def _fake_ai_fn(rec: dict, slots: list, extracted: list) -> list[dict]:
    """호출 1회당 proposal 2건 반환하는 가짜 AI 모델."""
    return [{"proposalId": "p1"}, {"proposalId": "p2"}]


def _count_events(log: Path, event_type: str) -> int:
    if not log.exists():
        return 0
    n = 0
    for line in log.read_text(encoding="utf-8").splitlines():
        if line.strip() and json.loads(line).get("type") == event_type:
            n += 1
    return n


def test_free_plan_hard_cap(tmp_log: Path) -> None:
    """free(한도 10) — 10회는 통과, 11회째 QuotaExceeded."""
    fn = gate.meter_ai_proposal_fn(
        _fake_ai_fn, account_id="u_free", plan="free", usage_log=tmp_log, now=FIXED_NOW
    )

    for i in range(10):
        out = fn({}, [], [])
        assert len(out) == 2, f"call {i} lost proposals"

    try:
        fn({}, [], [])
    except gate.QuotaExceeded as exc:
        assert exc.used == 10 and exc.quota == 10
    else:
        raise AssertionError("11th free call must be blocked")

    assert _count_events(tmp_log, gate.EVENT_CHARGED) == 10
    assert _count_events(tmp_log, gate.EVENT_BLOCKED) == 1
    print("PASS free_plan_hard_cap")


def test_pro_plan_passes_over_free_cap(tmp_log: Path) -> None:
    """pro(한도 100) — 무료 한도 10을 넘겨도 통과."""
    fn = gate.meter_ai_proposal_fn(
        _fake_ai_fn, account_id="u_pro", plan="pro", usage_log=tmp_log, now=FIXED_NOW
    )
    for _ in range(25):  # 무료 한도 초과 구간
        fn({}, [], [])
    assert gate.current_period_usage("u_pro", usage_log=tmp_log, now=FIXED_NOW) == 25
    print("PASS pro_plan_passes_over_free_cap")


def test_enterprise_unlimited_but_logged(tmp_log: Path) -> None:
    """enterprise(무제한) — 차단 없음, 계량 로그는 남음."""
    fn = gate.meter_ai_proposal_fn(
        _fake_ai_fn, account_id="u_ent", plan="enterprise", usage_log=tmp_log, now=FIXED_NOW
    )
    for _ in range(30):
        fn({}, [], [])
    assert _count_events(tmp_log, gate.EVENT_CHARGED) == 30
    assert _count_events(tmp_log, gate.EVENT_BLOCKED) == 0
    print("PASS enterprise_unlimited_but_logged")


def test_period_isolation(tmp_log: Path) -> None:
    """지난달 사용량은 이번달 한도에 영향 없음."""
    prev = datetime(2026, 6, 15, tzinfo=UTC)
    fn_prev = gate.meter_ai_proposal_fn(
        _fake_ai_fn, account_id="u_p", plan="free", usage_log=tmp_log, now=prev
    )
    for _ in range(10):  # 지난달 한도 소진
        fn_prev({}, [], [])

    # 이번달은 0에서 시작 — 통과해야 함
    fn_now = gate.meter_ai_proposal_fn(
        _fake_ai_fn, account_id="u_p", plan="free", usage_log=tmp_log, now=FIXED_NOW
    )
    fn_now({}, [], [])
    assert gate.current_period_usage("u_p", usage_log=tmp_log, now=FIXED_NOW) == 1
    print("PASS period_isolation")


def test_check_quota_readout(tmp_log: Path) -> None:
    """check_quota — 차단 없이 잔여 한도만 조회."""
    fn = gate.meter_ai_proposal_fn(
        _fake_ai_fn, account_id="u_c", plan="free", usage_log=tmp_log, now=FIXED_NOW
    )
    for _ in range(3):
        fn({}, [], [])
    status = gate.check_quota(account_id="u_c", plan="free", usage_log=tmp_log, now=FIXED_NOW)
    assert status["used"] == 3
    assert status["remaining"] == 7
    assert status["allowed"] is True
    print("PASS check_quota_readout")


def _run_all() -> int:
    import tempfile

    tests = [
        test_free_plan_hard_cap,
        test_pro_plan_passes_over_free_cap,
        test_enterprise_unlimited_but_logged,
        test_period_isolation,
        test_check_quota_readout,
    ]
    failed = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "usage.jsonl"
            try:
                t(log)
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
