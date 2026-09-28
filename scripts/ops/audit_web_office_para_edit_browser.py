"""WEB-OFFICE-PARA-EDIT-BROWSER-01 감사 스크립트.

JS 브라우저 상태기계 + runtime + React 컴포넌트의 정적 잠금 +
14 시나리오 자체 검증. writer / save / output 호출 0건 정적 잠금.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
VIEWER_DIR = PR / "frontend/web_office_viewer"
SELF_TEST = VIEWER_DIR / "para_edit_browser_self_test.mjs"

JS_FILES = [
    VIEWER_DIR / "para_edit_state.mjs",
    VIEWER_DIR / "para_edit_runtime.mjs",
    VIEWER_DIR / "para_edit_browser_self_test.mjs",
    VIEWER_DIR / "components/WebOfficeParagraphEditor.tsx",
]

# 본 공정 산출물에 등장하면 안 되는 토큰 (writer / save 본 실행 금지)
FORBIDDEN_JS = [
    "apply" + "_edit_plan", "hwpx" + "_edit_tool",
    "saveButton",
    "fetch('/save", "fetch(\"/save",
    "DOMParser", "XMLHttpRequest", ".hwpx",
    'contenteditable="true"', "contentEditable={true",
]


def _check_static() -> list[dict]:
    findings: list[dict] = []
    for p in JS_FILES:
        if not p.is_file():
            findings.append({"code": "JS_FILE_MISSING", "level": "FAIL",
                                      "detail": str(p.relative_to(PR))})
            continue
        src = p.read_text(encoding="utf-8")
        for tok in FORBIDDEN_JS:
            if tok in src:
                findings.append({"code": "FORBIDDEN_JS_TOKEN",
                                          "level": "FAIL",
                                          "detail": f"{p.name}: {tok}"})
    return findings


def _run_js() -> dict:
    r = subprocess.run(["node", str(SELF_TEST)],
                                      capture_output=True, text=True,
                                      timeout=30, encoding="utf-8")
    if r.returncode != 0:
        return {"ok": False, "stderr": r.stderr[:500],
                    "stdout": r.stdout[:500]}
    try:
        last = r.stdout.strip().splitlines()[-1]
        out = json.loads(last)
    except Exception as e:
        return {"ok": False, "stderr": f"parse: {e}"}
    return {"ok": out.get("verdict") == "PASS",
                "checks": out.get("checks", {})}


def audit() -> dict:
    findings: list[dict] = []
    findings.extend(_check_static())

    js = _run_js()
    if not js["ok"]:
        findings.append({"code": "JS_SELF_TEST_FAIL", "level": "FAIL",
                                  "detail": js})

    # 본 공정 디렉토리 .hwpx 0건
    for d in [VIEWER_DIR, PR / "scripts/hwpx/web_office"]:
        if d.is_dir():
            for f in d.glob("*.hwpx"):
                findings.append({"code": "UNEXPECTED_HWPX",
                                          "level": "FAIL",
                                          "detail": str(f.relative_to(PR))})

    return {
        "task": "WEB-OFFICE-PARA-EDIT-BROWSER-01",
        "jsChecks": js.get("checks", {}),
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
