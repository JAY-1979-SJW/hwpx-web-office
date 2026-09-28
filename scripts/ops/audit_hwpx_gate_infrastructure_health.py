"""감사 도구 자체 건강 확인 게이트 — "게이트가 살아있는가"를 감사한다.

왜 필요한가 (2026-09-28 완성도 감사에서 실측)
------------------------------------------
이 저장소는 기능별 감사 스크립트(`audit_*.py` 122개)·게이트(`gate_*.py`
16개)·verify7 체크리스트·RISK-LEDGER 를 갖추고 있어서 설계 자체는
촘촘하다. 그런데 "그 장치들이 지금도 실제로 작동하는가"를 확인하는
상위 루프가 없었다:

  · 형제 저장소(33)에서 `.git/hooks/pre-commit` 이 존재하지 않는
    스크립트를 참조하는 죽은 파일로 방치돼 있었다
    (`docs/specs/2026-09-24_hwpx_33to02_HANDOFF.md` 결함 #6).
  · 이 저장소(02)는 `pytest` 조차 오래 안 돌려봐서 `olefile`/
    `fastapi`/`pymupdf` 누락으로 26개 테스트 파일이 수집조차
    안 되는 상태였다 — 아무 게이트도 이걸 잡지 못했다.

이 스크립트는 "게이트 인프라 자체"를 빠르게(기본 수 초 이내) 점검한다.
전체 pytest 스위트(3497개, ~17분)를 매번 돌리는 건 커밋 훅으로 쓰기엔
너무 느려서 기본값에서는 뺀다 — 세션 시작 시 또는 주기적으로 사람이
직접 돌리거나, `--deep` 로 필요할 때만 무겁게 돌린다.

설계 원칙 (scripts/ops/gate_hwpx_session_claim.py 계승)
--------------------------------------------------------
- 이 스크립트 자신도 "감사 대상"이다 — 존재만으로 안심하면 안 되고
  주기적으로 사람이 실행 결과를 확인해야 한다(§3 현재창 보고).
- 실패 원인은 항상 "무엇이 없고 어떻게 고치는지"까지 출력한다.

사용
----
    python scripts/ops/audit_hwpx_gate_infrastructure_health.py
    python scripts/ops/audit_hwpx_gate_infrastructure_health.py --deep   # pytest 수집까지 확인 (~3분)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    # Windows 콘솔 기본 코드페이지(cp949)에서 한글 출력이 깨지는 것 방지.
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[2]
PASS = "PASS"
FAIL = "FAIL"

# requirements.txt 로 관리되는 서드파티 의존성 중, 과거 실제로 빠져서
# 테스트 수집을 깨뜨렸던 것 위주 + 웹 서비스 구동에 직결되는 것.
CRITICAL_IMPORTS = {
    "fastapi": "web_office 백엔드 API (scripts/hwpx/web_office/service.py 등)",
    "olefile": "HWP(바이너리) 파싱 (scripts/extract_hwp_body_fields.py)",
    "fitz": "PDF 파싱 — pip 패키지명은 pymupdf (scripts/kpi_parse.py 등)",
    "pytest": "회귀 스위트 실행 자체",
}


def check_git_hooks_path() -> dict:
    proc = subprocess.run(
        ["git", "config", "--get", "core.hooksPath"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    configured = proc.stdout.strip()
    if configured != ".githooks":
        return {
            "verdict": FAIL,
            "detail": f"core.hooksPath={configured!r} (기대값: '.githooks') — "
                      f"고치기: git config core.hooksPath .githooks",
        }
    return {"verdict": PASS, "detail": "core.hooksPath=.githooks"}


def check_pre_commit_chain() -> dict:
    hook = REPO_ROOT / ".githooks" / "pre-commit"
    if not hook.is_file():
        return {"verdict": FAIL, "detail": f"{hook} 없음 — 훅 자체가 미설치"}

    text = hook.read_text(encoding="utf-8", errors="replace")
    # pre-commit 훅이 참조하는 하위 체커 경로를 실제로 찾을 수 있는지 확인.
    # (형제 저장소 33에서 이 연결이 끊겨 있던 게 결함 #6 이었다.)
    referenced = [
        line.strip().split("=", 1)[1].strip().strip('"')
        for line in text.splitlines()
        if line.strip().startswith("CHK=") or line.strip().startswith('[ -f "$CHK" ] || CHK=')
    ]
    resolved = []
    missing = []
    for raw in referenced:
        candidate = raw.replace('$TOP', str(REPO_ROOT)).replace('"', "")
        p = Path(candidate)
        (resolved if p.is_file() else missing).append(candidate)

    if not resolved:
        return {
            "verdict": FAIL,
            "detail": f"{hook} 가 참조하는 체커 스크립트 중 실존하는 게 0건 "
                      f"— 커밋할 때마다 '검사기 없음' 으로 차단되거나 조용히 무력화됐을 수 있음. "
                      f"후보: {referenced}",
        }
    return {"verdict": PASS, "detail": f"체커 연결 확인됨: {resolved[0]}"}


def check_post_commit_hook() -> dict:
    hook = REPO_ROOT / ".githooks" / "post-commit"
    if not hook.is_file():
        return {"verdict": FAIL, "detail": f"{hook} 없음"}
    return {"verdict": PASS, "detail": str(hook)}


def check_critical_imports() -> dict:
    missing = []
    for module, why in CRITICAL_IMPORTS.items():
        proc = subprocess.run(
            [sys.executable, "-c", f"import {module}"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            missing.append({"module": module, "why": why})
    if missing:
        pip_names = " ".join(
            "pymupdf" if m["module"] == "fitz" else m["module"] for m in missing
        )
        return {
            "verdict": FAIL,
            "detail": f"누락: {[m['module'] for m in missing]} — "
                      f"고치기: {sys.executable} -m pip install {pip_names} "
                      f"(또는 requirements.txt 참조)",
            "missing": missing,
        }
    return {"verdict": PASS, "detail": "핵심 서드파티 패키지 전부 임포트 가능"}


def check_requirements_file() -> dict:
    req = REPO_ROOT / "requirements.txt"
    if not req.is_file():
        return {
            "verdict": FAIL,
            "detail": "저장소 루트에 requirements.txt 없음 — 새 환경에서 "
                      "무엇을 설치해야 하는지 알 방법이 없음",
        }
    return {"verdict": PASS, "detail": str(req)}


def check_pytest_collect_deep() -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    if "error" in tail.lower() and not tail.strip().endswith("0 errors"):
        return {"verdict": FAIL, "detail": tail}
    return {"verdict": PASS, "detail": tail}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deep", action="store_true",
        help="pytest --collect-only 까지 실행 (~3분, 전체 3497개 테스트 수집 가능 여부 확인)",
    )
    args = parser.parse_args()

    checks = {
        "gitHooksPath": check_git_hooks_path(),
        "preCommitChain": check_pre_commit_chain(),
        "postCommitHook": check_post_commit_hook(),
        "criticalDependencies": check_critical_imports(),
        "requirementsFile": check_requirements_file(),
    }
    if args.deep:
        checks["pytestCollect"] = check_pytest_collect_deep()

    failures = [name for name, result in checks.items() if result["verdict"] == FAIL]
    payload = {
        "verdict": FAIL if failures else PASS,
        "checks": checks,
        "failures": failures,
    }

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
