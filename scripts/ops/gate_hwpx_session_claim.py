"""세션 점유 게이트 — 같은 저장소에서 여러 세션이 서로 침범하지 못하게.

왜 필요한가 (2026-07-23~24 실제 사고)
------------------------------------
`feat/hwpx-coord-fidelity` 브랜치에 여러 세션이 동시에 작업하면서:

  · 내가 `git add` 로 내 파일만 지정했는데 staged 목록에 다른 세션이 올려둔
    `coordinate_layout.py` 가 섞여 있었다 — **인덱스는 공유된다.**
  · 경로 지정 커밋을 준비하는 사이 다른 세션이 커밋하면서 **내 작업 파일
    10개를 자기 커밋(f6d36c4)에 통째로 쓸어갔다.** 내용은 반영됐지만
    커밋 메시지는 무관한 내용으로 남았다.
  · 잠금 기준(BASELINE_COMMIT)을 양쪽이 번갈아 옮겨 서로의 감리를 깨뜨렸다
    (334d665 → b9782a5 → 3f94c2a → 2f7db75 → e9517fc → 517849c).
  · 파서 파일이 계속 바뀌어 파싱 캐시 버전이 흔들렸다.

이 모듈은 **파일 단위 점유**를 선언하고, 커밋 시점에 남의 점유 파일이
섞였는지 막는다. `.githooks` 는 같은 `.git` 을 쓰므로 훅 한 번 설치로
양쪽 세션 모두에 적용된다.

설계 원칙
---------
- **안전한 쪽으로 실패한다**: 점유 파일이 없거나 깨졌으면 통과시킨다.
  게이트 고장이 작업을 막으면 안 된다.
- **오래된 점유는 무시한다**: heartbeat 가 TTL 을 넘으면 죽은 세션으로
  보고 통과시킨다. 세션이 죽어도 저장소가 잠기지 않는다.
- **막을 때는 푸는 법을 알려준다**: 차단 메시지에 해제 명령을 그대로 싣는다.
- 자기 점유는 막지 않는다. **다른 세션 점유와 겹칠 때만** 막는다.

사용
----
    gate_hwpx_session_claim.py --session S1 --claim scripts/a.py tests/b.py
    gate_hwpx_session_claim.py --session S1 --note "좌표 수리" --claim ...
    gate_hwpx_session_claim.py --status
    gate_hwpx_session_claim.py --check        # pre-commit 훅이 부른다
    gate_hwpx_session_claim.py --session S1 --release
    gate_hwpx_session_claim.py --session S1 --heartbeat
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CLAIM_FILE = ROOT / "data" / "audit" / "session_claims.json"
LOG_FILE = ROOT / "data" / "audit" / "session_claims.jsonl"

# heartbeat 가 이 시간을 넘으면 죽은 세션으로 보고 점유를 무시한다.
STALE_AFTER_SEC = 6 * 3600

PASS = "PASS_SESSION_CLAIM_GUARD"
FAIL = "FAIL_SESSION_CLAIM_GUARD"


def _now() -> float:
    return time.time()


def _read() -> dict[str, Any]:
    """점유 상태를 읽는다. 없거나 깨졌으면 빈 상태 — 절대 예외를 내지 않는다."""
    try:
        if not CLAIM_FILE.is_file():
            return {"claims": []}
        data = json.loads(CLAIM_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("claims"), list):
            return {"claims": []}
        return data
    except (OSError, json.JSONDecodeError):
        return {"claims": []}


def _write(data: dict[str, Any]) -> None:
    CLAIM_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CLAIM_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CLAIM_FILE)


def _append_log(event: dict[str, Any]) -> None:
    """append-only 기록 (CLAUDE.md §5 공용창고 규칙)."""
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _norm(p: str) -> str:
    """경로 표기 정규화.

    `lstrip("./")` 을 쓰면 안 된다 — 그건 선행 문자 중 '.' 과 '/' 를 **전부**
    깎아서 `.githooks/pre-commit` 이 `githooks/pre-commit` 으로 뭉개진다.
    점으로 시작하는 경로(.githooks, .claude 등)가 매칭에서 통째로 빠진다.
    """
    s = p.replace("\\", "/").strip()
    while s.startswith("./"):
        s = s[2:]
    return s


def _rel_or_abs(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def live_claims(data: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """죽지 않은 점유만 반환."""
    data = data if data is not None else _read()
    now = _now()
    out = []
    for c in data.get("claims", []):
        if not isinstance(c, dict):
            continue
        hb = c.get("heartbeatAt") or c.get("claimedAt") or 0
        try:
            hb = float(hb)
        except (TypeError, ValueError):
            hb = 0
        if now - hb <= STALE_AFTER_SEC:
            out.append(c)
    return out


def claim(session: str, paths: list[str], note: str = "") -> dict[str, Any]:
    data = _read()
    claims = [c for c in data.get("claims", []) if c.get("session") != session]
    mine = {
        "session": session,
        "paths": sorted({_norm(p) for p in paths if p.strip()}),
        "note": note,
        "pid": os.getpid(),
        "claimedAt": _now(),
        "heartbeatAt": _now(),
    }
    claims.append(mine)
    _write({"claims": claims})
    _append_log({"event": "claim", **mine})
    # 이미 남이 점유한 것과 겹치면 알려준다(막지는 않는다 — 선언 단계)
    conflicts = _conflicts(mine["paths"], session)
    return {"claimed": mine["paths"], "conflicts": conflicts}


def release(session: str) -> dict[str, Any]:
    data = _read()
    before = len(data.get("claims", []))
    claims = [c for c in data.get("claims", []) if c.get("session") != session]
    _write({"claims": claims})
    _append_log({"event": "release", "session": session, "at": _now()})
    return {"released": before - len(claims)}


def heartbeat(session: str) -> dict[str, Any]:
    data = _read()
    hit = 0
    for c in data.get("claims", []):
        if c.get("session") == session:
            c["heartbeatAt"] = _now()
            hit += 1
    _write(data)
    return {"refreshed": hit}


def _conflicts(paths: list[str], session: str) -> list[dict[str, Any]]:
    """다른 살아있는 세션이 점유한 경로와의 충돌."""
    want = {_norm(p) for p in paths}
    out = []
    for c in live_claims():
        if c.get("session") == session:
            continue
        overlap = sorted(want & {_norm(p) for p in c.get("paths", [])})
        if overlap:
            out.append({
                "session": c.get("session"),
                "note": c.get("note", ""),
                "paths": overlap,
                "heartbeatAt": c.get("heartbeatAt"),
            })
    return out


def _staged_files() -> list[str]:
    try:
        r = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=20,
        )
        if r.returncode != 0:
            return []
        return [_norm(x) for x in r.stdout.splitlines() if x.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def current_session() -> str:
    """이 세션의 식별자. 환경변수로 주지 않으면 빈 값(= 소유 없음)."""
    return (os.environ.get("HWPX_SESSION_ID") or os.environ.get("CLAUDE_SESSION_ID") or "").strip()


def check(session: str | None = None) -> dict[str, Any]:
    """staged 파일이 다른 세션 점유와 겹치는지. pre-commit 훅용."""
    session = session if session is not None else current_session()
    staged = _staged_files()
    if not staged:
        return {"verdict": PASS, "staged": 0, "conflicts": []}
    conflicts = _conflicts(staged, session or "__unknown__")
    return {
        "verdict": FAIL if conflicts else PASS,
        "session": session or "(미설정)",
        "staged": len(staged),
        "conflicts": conflicts,
    }


def status() -> dict[str, Any]:
    all_c = _read().get("claims", [])
    live = live_claims()
    stale = len(all_c) - len(live)
    return {
        "live": [
            {
                "session": c.get("session"),
                "note": c.get("note", ""),
                "paths": len(c.get("paths", [])),
                "ageMin": round((_now() - float(c.get("heartbeatAt") or 0)) / 60, 1),
            }
            for c in live
        ],
        "staleIgnored": stale,
        # 저장소 밖 경로여도 죽지 않는다 — 상태 조회가 실패하면
        # 게이트가 왜 막는지 확인할 방법이 사라진다.
        "claimFile": _rel_or_abs(CLAIM_FILE),
        "staleAfterHours": STALE_AFTER_SEC / 3600,
    }


def _print(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _handle_check(sess: str | None) -> int:
    r = check(sess)
    if r["verdict"] == PASS:
        return 0
    sys.stderr.write(
        "\n[STOP] 다른 세션이 점유한 파일이 staged 에 섞였습니다.\n"
        "        같은 저장소를 여러 세션이 쓰고 있어, 그대로 커밋하면\n"
        "        남의 작업을 자기 커밋에 쓸어담게 됩니다.\n\n"
    )
    for c in r["conflicts"]:
        sys.stderr.write(f"  세션 {c['session']}  ({c['note']})\n")
        for p in c["paths"]:
            sys.stderr.write(f"      {p}\n")
    sys.stderr.write(
        "\n  조치:\n"
        "    git restore --staged <위 경로>      ← 인덱스에서만 내림"
        " (내용은 그대로)\n"
        "    python scripts/ops/gate_hwpx_session_claim.py --status\n"
        "    (그 세션이 끝났다면)  --session <그세션> --release\n"
        f"    점유는 {STALE_AFTER_SEC // 3600}시간 heartbeat 없으면"
        " 자동 만료됩니다.\n\n"
    )
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", default=None)
    ap.add_argument("--note", default="")
    ap.add_argument("--claim", nargs="*", default=None, metavar="PATH")
    ap.add_argument("--release", action="store_true")
    ap.add_argument("--heartbeat", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    sess = args.session or current_session()

    if args.status:
        _print(status())
        return 0
    if args.check:
        return _handle_check(sess)
    if args.release:
        if not sess:
            _print({"error": "SESSION_REQUIRED"})
            return 2
        _print(release(sess))
        return 0
    if args.heartbeat:
        if not sess:
            _print({"error": "SESSION_REQUIRED"})
            return 2
        _print(heartbeat(sess))
        return 0
    if args.claim is not None:
        if not sess:
            _print({"error": "SESSION_REQUIRED"})
            return 2
        _print(claim(sess, args.claim, args.note))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
