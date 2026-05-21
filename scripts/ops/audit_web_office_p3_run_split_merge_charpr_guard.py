#!/usr/bin/env python3
"""WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01 준공감사.

charPrIDRef split/merge guard 구현 완결성 검사.
"""
from __future__ import annotations
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
BASELINE_COMMIT = "e04d325"

_CMD_MJS   = PR / "frontend/web_office_viewer/para_edit_command.mjs"
_STATE_MJS = PR / "frontend/web_office_viewer/para_edit_state.mjs"
_SMOKE_MJS = PR / "frontend/web_office_viewer/para_edit_structure_smoke.mjs"
_MODEL_PY  = PR / "scripts/hwpx/web_office/para_edit_model.py"
_TEST_PY   = PR / "tests/test_web_office_p3_run_split_merge_charpr_guard.py"
_AUDIT_PY  = Path(__file__)

issues: list[dict] = []


def _ok(code: str, detail: str = "") -> None:
    print(f"  [OK]  {code}" + (f" — {detail}" if detail else ""))


def _fail(code: str, detail: str = "", block: bool = True) -> None:
    lvl = "FAIL" if block else "WARN"
    print(f"  [{lvl}] {code}" + (f" — {detail}" if detail else ""))
    issues.append({"code": code, "detail": detail, "block": block})


# ── 1. Python 상수 ───────────────────────────────────────────────
print("\n[1] Python model 상수")
src_py = _MODEL_PY.read_text(encoding="utf-8")
for const in ("REASON_CHARPR_MISSING_ON_RUN",
              "REASON_CHARPR_SPLIT_SOURCE_MISSING",
              "validate_run_charpr_integrity"):
    if const in src_py:
        _ok(f"py_{const}")
    else:
        _fail(f"py_{const}_missing", f"{const} 없음")

# ── 2. JS 상수 / 함수 ───────────────────────────────────────────
print("\n[2] JS 상수·함수")
src_cmd = _CMD_MJS.read_text(encoding="utf-8")
for sym in ("REASON_CHARPR_MISSING_ON_RUN",
            "REASON_CHARPR_SPLIT_SOURCE_MISSING",
            "validateRunCharPrIntegrity",
            "CHARPR_SPLIT_SOURCE_MISSING"):
    if sym in src_cmd:
        _ok(f"js_cmd_{sym}")
    else:
        _fail(f"js_cmd_{sym}_missing", f"{sym} 없음")

# ── 3. JS state machine guard 사용 확인 ─────────────────────────
print("\n[3] JS state machine guard")
src_state = _STATE_MJS.read_text(encoding="utf-8")
for sym in ("validateRunCharPrIntegrity",
            "REASON_CHARPR_MISSING_ON_RUN",
            "_charPrGuard"):
    if sym in src_state:
        _ok(f"js_state_{sym}")
    else:
        _fail(f"js_state_{sym}_missing", f"{sym} 없음")

# ── 4. 금지 패턴 부재 확인 ──────────────────────────────────────
print("\n[4] 금지 패턴")
for path, label, forbidden in [
    (_CMD_MJS,   "cmd.mjs",   r"writeFile.*header\.xml|header\.xml.*write"),
    (_STATE_MJS, "state.mjs", r"writeFile.*header\.xml|header\.xml.*write"),
    (_MODEL_PY,  "model.py",  r"charPrIDRef\s*=\s*\{\}"),  # 신규 charPr 빈 객체 생성
]:
    import re
    text = path.read_text(encoding="utf-8")
    if re.search(forbidden, text):
        _fail(f"forbidden_{label}", f"금지 패턴 발견: {forbidden}")
    else:
        _ok(f"no_forbidden_{label}")

# ── 5. locked files diff ─────────────────────────────────────────
print("\n[5] Baseline 이후 변경 확인")
locked = [
    "frontend/web_office_viewer/para_edit_command.mjs",
    "frontend/web_office_viewer/para_edit_state.mjs",
    "scripts/hwpx/web_office/para_edit_model.py",
    "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
]
for f in locked:
    r = subprocess.run(
        ["git", "diff", BASELINE_COMMIT, "--", f],
        capture_output=True, text=True, cwd=str(PR),
    )
    if r.stdout.strip():
        _ok(f"changed_{Path(f).name}")
    else:
        _fail(f"unchanged_{Path(f).name}", "baseline 이후 변경 없음")

# ── 6. staged zero ───────────────────────────────────────────────
print("\n[6] staged 파일 0개")
r = subprocess.run(
    ["git", "diff", "--cached", "--name-only"],
    capture_output=True, text=True, cwd=str(PR),
)
staged = [l for l in r.stdout.strip().splitlines() if l]
if not staged:
    _ok("staged_zero")
else:
    _fail("staged_not_zero", f"staged: {staged}", block=False)

# ── 7. JS smoke ─────────────────────────────────────────────────
print("\n[7] JS smoke")
import shutil
node = shutil.which("node")
if not node:
    _fail("js_smoke", "node 없음 — WARN_ENV_DEPENDENT", block=False)
else:
    r = subprocess.run(
        [node, str(_SMOKE_MJS)],
        capture_output=True, text=True, timeout=30,
    )
    if r.returncode == 0:
        data = json.loads(r.stdout)
        if data.get("verdict") == "PASS":
            checks = data.get("checks", {})
            _ok("js_smoke", f"{len(checks)}개 체크 PASS")
            for k in ("charPrIntegrityValidNormal", "charPrMissingRunReject",
                      "splitRunPreservesCharPr", "splitNullCharPrThrows",
                      "paraDeleteMergeKeepsDifferentCharPrSeparate"):
                if checks.get(k, {}).get("ok"):
                    _ok(f"smoke_{k}")
                else:
                    _fail(f"smoke_{k}_fail", f"check {k} FAIL")
        else:
            failed = [k for k, v in data.get("checks", {}).items()
                      if not v.get("ok")]
            _fail("js_smoke_verdict", f"FAIL at {failed}")
    else:
        _fail("js_smoke_error", r.stderr[:200])

# ── 8. Python tests ──────────────────────────────────────────────
print("\n[8] Python tests")
r = subprocess.run(
    [sys.executable, "-m", "pytest",
     str(_TEST_PY), "-q", "--tb=short"],
    capture_output=True, text=True, timeout=120,
    cwd=str(PR),
)
lines = r.stdout.strip().splitlines()
summary = next((l for l in reversed(lines) if "passed" in l or "failed" in l
                or "error" in l), "")
if r.returncode == 0:
    _ok("python_tests", summary)
else:
    failed_lines = [l for l in lines if "FAILED" in l]
    _fail("python_tests", summary + " | " + "; ".join(failed_lines[:5]))

# ── 최종 판정 ───────────────────────────────────────────────────
print("\n" + "=" * 60)
blocking = [i for i in issues if i["block"]]
warns    = [i for i in issues if not i["block"]]
if not blocking:
    verdict = "PASS" if not warns else "WARN"
else:
    verdict = "FAIL"
print(f"최종 판정: {verdict}")
if blocking:
    for i in blocking:
        print(f"  FAIL: {i['code']} — {i['detail']}")
if warns:
    for i in warns:
        print(f"  WARN: {i['code']} — {i['detail']}")

out = {
    "공정": "WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01",
    "baseline": BASELINE_COMMIT,
    "verdict": verdict,
    "issues": issues,
    "ts": datetime.now(timezone.utc).isoformat(),
}
audit_dir = PR / "data/audit"
audit_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
out_path = audit_dir / f"audit_p3_charpr_guard_{ts}.jsonl"
out_path.write_text(json.dumps(out, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"감사 기록: {out_path}")
sys.exit(0 if verdict != "FAIL" else 1)
