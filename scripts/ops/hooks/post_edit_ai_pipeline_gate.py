"""PostToolUse 훅 — AI 해석 공정 파일을 고치면 §4.5/§4.6 게이트를 즉시 돌린다.

지시(2026-08-01, 대표님): "위 방식을 운영규칙 훅 및 게이트 설치해"

왜 훅인가
---------
운영규칙(CLAUDE.md §4.6)과 게이트 스크립트만 있으면 '돌리는 것을 잊는'
구멍이 남는다. 파이프라인 파일을 고치는 순간 자동으로 게이트가 돌아야
규칙이 실효를 갖는다. 실제로 이 저장소에서 규칙 위반(규칙이 AI 앞에서
칸을 잘라 검측요청서가 통째로 죽은 것)이 오래 발견되지 않았다.

동작
----
- 대상 파일이 아니면 조용히 통과(exit 0).
- 대상이면 게이트 실행 → PASS 면 조용히 통과.
- FAIL 이면 PostToolUse `decision: block` 으로 위반 코드를 되돌려준다.
  편집을 되돌리지는 않는다 — 무엇이 깨졌는지 즉시 알리는 것이 목적이다.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GATE = ROOT / "scripts" / "ops" / "gate_hwpx_ai_interpretation_pipeline.py"

# AI 해석 공정 파일 — 이것들을 고치면 게이트를 돌린다
TARGET_RE = re.compile(
    r"web_office[\\/](?:ai_[a-z_]+|build_ai_interpretation_cache)\.py$",
    re.IGNORECASE)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:       # noqa: BLE001 — 훅이 세션을 막으면 안 된다
        return 0

    tool_input = data.get("tool_input") or {}
    tool_response = data.get("tool_response") or {}
    path = (tool_input.get("file_path")
            or (tool_response.get("filePath") if isinstance(tool_response, dict)
                else None)
            or "")
    if not path or not TARGET_RE.search(str(path)):
        return 0
    if not GATE.is_file():
        return 0

    try:
        proc = subprocess.run(
            [sys.executable, str(GATE)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120, check=False, cwd=str(ROOT))
    except Exception as exc:      # noqa: BLE001
        _emit({"systemMessage":
               f"[§4.6 게이트] 실행 실패 — {type(exc).__name__}"})
        return 0

    if proc.returncode == 0:
        return 0

    try:
        result = json.loads(proc.stdout)
        failed = [f"{c['code']}({c['desc']})"
                  for c in result.get("checks", [])
                  if c.get("status") != "PASS"]
    except Exception:              # noqa: BLE001
        failed = []
    detail = " · ".join(failed) if failed else (proc.stdout or "")[:300]
    reason = (f"CLAUDE.md §4.5/§4.6 게이트 FAIL — {detail}\n"
              f"파싱 우선·두 신호 합의 원칙을 깬 편집입니다. "
              f"`python scripts/ops/gate_hwpx_ai_interpretation_pipeline.py` "
              f"로 상세를 확인하고 수리하세요.")
    _emit({
        "systemMessage": f"[§4.6 게이트 FAIL] {detail[:160]}",
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": reason,
        },
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
