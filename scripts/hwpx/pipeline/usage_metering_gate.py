"""HWPX-AI-FILL-USAGE-METERING-GATE-01.

AI fill 과금 게이트 — AI 후보 생성(ai_proposal_fn) 호출 1건을 계량하고,
플랜별 무료 한도를 초과하면 차단한다.

수익 구조의 생명선:
- 뷰어/편집은 무료 개방(미끼)이지만 AI fill은 외부 모델 API 원가가
  발생한다. 무료 사용자가 무제한 호출하면 API 청구서가 폭증한다.
- 본 게이트가 계정별·월별 사용량을 append-only 로그로 기록하고,
  플랜별 무료 한도를 **하드캡**으로 강제한다.

배관 위치:
- master orchestration이 `ai_proposal_fn`을 주입하기 **직전**,
  `meter_ai_proposal_fn(fn, account=...)`로 감싼다.
- `run_auto_fill_master` 회로 자체는 수정하지 않는다(무침습).

방화구획:
- production 운영동(fill_review)에서 본 모듈 import 금지.
- raw 개인정보 미참조 — 로그에는 계정 식별자 + 건수만 적재.
- secret/token 미참조.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

CONTRACT_NAME = "HWPX-AI-FILL-USAGE-METERING-GATE-01"
CONTRACT_VERSION = "v1"

# ── 플랜별 월 무료/포함 한도 (AI fill 호출 건수) ──────────────────────
# None = 무제한. 값은 요금제 설계와 1:1로 연동된다.
PLAN_QUOTAS: dict[str, int | None] = {
    "free": 10,
    "pro": 100,
    "team": 500,
    "enterprise": None,
}
DEFAULT_PLAN = "free"

# ── 사용량 창고 (CLAUDE.md §5 — data/audit append-only) ──────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_USAGE_LOG = PROJECT_ROOT / "data" / "audit" / "ai_fill_usage.jsonl"

# 이벤트 종류
EVENT_CHARGED = "ai_fill_charged"   # 정상 계량된 호출
EVENT_BLOCKED = "ai_fill_blocked"   # 한도 초과로 차단된 호출


class QuotaExceeded(RuntimeError):
    """무료/포함 한도 초과 — AI fill 호출 차단 시그널.

    호출자(배관/서버 진입점)가 잡아서 402/업그레이드 안내로 변환한다.
    """

    def __init__(self, *, account_id: str, plan: str,
                 used: int, quota: int, period: str) -> None:
        self.account_id = account_id
        self.plan = plan
        self.used = used
        self.quota = quota
        self.period = period
        super().__init__(
            f"AI fill quota exceeded — account={account_id} plan={plan} "
            f"used={used}/{quota} period={period}"
        )


# ── billing period / quota 헬퍼 ──────────────────────────────────────

def billing_period(now: datetime | None = None) -> str:
    """청구 기간 키(YYYY-MM). now 미지정 시 UTC 현재월."""
    ref = now or datetime.now(timezone.utc)
    return ref.strftime("%Y-%m")


def quota_for_plan(plan: str) -> int | None:
    """플랜의 월 한도. 미등록 플랜은 free로 강등(안전측)."""
    return PLAN_QUOTAS.get(plan, PLAN_QUOTAS[DEFAULT_PLAN])


# ── 사용량 집계 (append-only 로그 스캔) ──────────────────────────────
#
# MVP 구현: JSONL 파일을 순차 스캔한다. 규모가 커지면(수만 계정)
# 이 함수만 DB 카운터 쿼리로 교체하면 되고, 게이트 인터페이스는 불변이다.

def current_period_usage(
    account_id: str,
    *,
    period: str | None = None,
    usage_log: str | Path | None = None,
    now: datetime | None = None,
) -> int:
    """해당 계정이 이번 청구 기간에 정상 계량한 AI fill 건수."""
    period = period or billing_period(now)
    log_path = Path(usage_log) if usage_log else _DEFAULT_USAGE_LOG
    if not log_path.exists():
        return 0
    count = 0
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # 손상 라인은 건너뛴다 (append-only 무결성 보존)
            if (event.get("type") == EVENT_CHARGED
                    and event.get("accountId") == account_id
                    and event.get("period") == period):
                count += int(event.get("units", 1))
    return count


def _append_event(log_path: Path, event: dict[str, Any]) -> None:
    """append-only 이벤트 적재. 부모 디렉터리 자동 생성."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── 사전 점검 (한도 체크) ────────────────────────────────────────────

def check_quota(
    *,
    account_id: str,
    plan: str = DEFAULT_PLAN,
    period: str | None = None,
    usage_log: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """호출 전 한도 상태 조회. 차단하지 않고 dict만 반환(서버가 판단)."""
    period = period or billing_period(now)
    quota = quota_for_plan(plan)
    used = current_period_usage(
        account_id, period=period, usage_log=usage_log, now=now)
    allowed = quota is None or used < quota
    remaining = None if quota is None else max(0, quota - used)
    return {
        "accountId": account_id,
        "plan": plan,
        "period": period,
        "used": used,
        "quota": quota,
        "remaining": remaining,
        "allowed": allowed,
    }


# ── 계량 래퍼 (핵심 밸브) ────────────────────────────────────────────

def meter_ai_proposal_fn(
    ai_proposal_fn: Callable[[dict, list[dict], list[dict]], list[dict]],
    *,
    account_id: str,
    plan: str = DEFAULT_PLAN,
    request_id: str | None = None,
    usage_log: str | Path | None = None,
    now: datetime | None = None,
) -> Callable[[dict, list[dict], list[dict]], list[dict]]:
    """`ai_proposal_fn`을 과금 게이트로 감싼 새 callable을 반환한다.

    반환된 callable은 master orchestration이 그대로 주입할 수 있는
    동일 시그니처(recognition, slots, extracted)를 유지한다.

    동작:
      ① 청구 기간 사용량을 조회 → 한도 초과면 BLOCKED 로그 + QuotaExceeded raise
      ② 원본 fn 호출
      ③ 성공 시 CHARGED 로그 1건 적재(units=1, 건당 과금)

    Enterprise(무제한)도 계량 로그는 남긴다 — 정산·분석용.
    """
    log_path = Path(usage_log) if usage_log else _DEFAULT_USAGE_LOG

    def _gated(recognition: dict, slots: list[dict],
               extracted: list[dict]) -> list[dict]:
        period = billing_period(now)
        quota = quota_for_plan(plan)
        used = current_period_usage(
            account_id, period=period, usage_log=log_path, now=now)

        if quota is not None and used >= quota:
            _append_event(log_path, {
                "type": EVENT_BLOCKED,
                "accountId": account_id,
                "plan": plan,
                "period": period,
                "requestId": request_id,
                "used": used,
                "quota": quota,
                "ts": (now or datetime.now(timezone.utc)).isoformat(),
            })
            raise QuotaExceeded(
                account_id=account_id, plan=plan,
                used=used, quota=quota, period=period)

        proposals = ai_proposal_fn(recognition, slots, extracted) or []

        _append_event(log_path, {
            "type": EVENT_CHARGED,
            "accountId": account_id,
            "plan": plan,
            "period": period,
            "requestId": request_id,
            "units": 1,
            "proposalCount": len(proposals),
            "ts": (now or datetime.now(timezone.utc)).isoformat(),
        })
        return proposals

    return _gated


# ── snapshot ─────────────────────────────────────────────────────────

def dump_contract_snapshot() -> dict[str, Any]:
    return {
        "contractName": CONTRACT_NAME,
        "contractVersion": CONTRACT_VERSION,
        "planQuotas": dict(PLAN_QUOTAS),
        "defaultPlan": DEFAULT_PLAN,
        "usageLog": str(_DEFAULT_USAGE_LOG.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "events": [EVENT_CHARGED, EVENT_BLOCKED],
    }
