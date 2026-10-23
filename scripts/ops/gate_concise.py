"""게이트/진단 스크립트를 실행하고 verdict/핵심 수치만 출력한다.

전체 JSON 응답을 대화창에 그대로 찍는 습관을 기술적으로 막는다 —
원본 전체 출력은 로그 파일에 남기고, 화면에는 verdict와 실패
목록만 보여준다.

사용:
    python scripts/ops/gate_concise.py <대상 스크립트> [인자...]
    python scripts/ops/gate_concise.py -- python scripts/ops/gate_x.py --foo

종료 코드: 대상 스크립트의 종료 코드를 그대로 반환한다(CI/훅에서 체이닝 가능).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _find_verdicts(obj, path="", out=None):
    """중첩 dict에서 '*erdict' 로 끝나는 키를 전부 찾는다(최상위+하위 게이트 모두)."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k.lower().endswith("verdict"):
                out.append((path + k, v))
            elif isinstance(v, (dict, list)):
                _find_verdicts(v, path + k + ".", out)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _find_verdicts(item, f"{path}[{i}].", out)
    return out


def _find_failures(obj):
    if isinstance(obj, dict):
        f = obj.get("failures")
        if isinstance(f, list) and f:
            return f
    return []


def _parse_gate_output(stdout: str):
    """게이트들이 보통 JSON 하나를 stdout에 찍는다. 여러 JSON 블록이 섞여 있을 수 있으니
    실패하면 마지막 { ... } 블록만 다시 시도한다."""
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        start = stdout.rfind("{")
        if start >= 0:
            try:
                return json.loads(stdout[start:])
            except (json.JSONDecodeError, ValueError):
                return None
        return None


def main(argv: list[str]) -> int:
    if not argv:
        print("사용법: gate_concise.py <스크립트> [인자...]", file=sys.stderr)
        return 2
    if argv[0] == "--":
        argv = argv[1:]

    cmd = [sys.executable, *argv] if argv[0].endswith(".py") else argv

    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stdout = proc.stdout or ""

    log_dir = Path("data") / "reports" / "gate_concise_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{Path(argv[0]).stem}_full_output.log"
    log_path.write_text(stdout + (proc.stderr or ""), encoding="utf-8")

    parsed = _parse_gate_output(stdout)

    print(f"[gate_concise] 실행: {' '.join(argv)}")
    print(f"[gate_concise] 전체 출력 저장: {log_path} ({len(stdout)} bytes)")

    if parsed is None:
        print("[gate_concise] JSON 파싱 실패 - 마지막 5줄만 표시:")
        for line in stdout.strip().splitlines()[-5:]:
            print(f"  {line}")
        return proc.returncode

    verdicts = _find_verdicts(parsed)
    top_verdict = parsed.get("verdict", "?")
    fail_count = sum(1 for _, v in verdicts if v.startswith("FAIL"))
    pass_count = sum(1 for _, v in verdicts if v.startswith("PASS"))

    print(
        f"[gate_concise] verdict={top_verdict} (하위 게이트 PASS {pass_count} / FAIL {fail_count})"
    )

    failures = _find_failures(parsed)
    if failures:
        print(f"[gate_concise] failures: {failures}")

    if fail_count:
        print("[gate_concise] 실패한 하위 게이트:")
        for path, v in verdicts:
            if v.startswith("FAIL"):
                print(f"  - {path}: {v}")

    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
