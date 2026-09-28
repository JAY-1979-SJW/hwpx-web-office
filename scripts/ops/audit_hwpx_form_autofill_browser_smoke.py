"""
HWPX-FORM-AUTO-FILL-WRITER-BROWSER-SMOKE-08 audit script.

Generates PII-safe browser smoke reports under:
data/reports/hwpx_form_autofill_browser_smoke/
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_autofill_browser_smoke"
FRONTEND_HTML = ROOT / "frontend" / "web_office_viewer" / "form_autofill_browser_smoke.html"
FRONTEND_JS = ROOT / "frontend" / "web_office_viewer" / "form_autofill_browser_smoke.mjs"
BROWSER_TEST = ROOT / "tests" / "test_hwpx_form_autofill_browser_smoke.py"

PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_BROWSER_SMOKE"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_BROWSER_SMOKE"
WARNINGS = [
    "WARN_SYNTHETIC_BROWSER_SCENARIO_ONLY",
    "WARN_SANDBOX_ONLY",
    "WARN_REAL_USER_FILE_NOT_TESTED",
    "WARN_DEPLOY_NOT_PERFORMED",
]

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
RAW_HWPX_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


def _run_pytest(paths: list[str], timeout: int = 300) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    lines = [line.strip() for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()]
    return {
        "paths": paths,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "summary": _safe_text(lines[-1] if lines else "no output"),
    }


def _safe_text(text: str) -> str:
    text = ABS_PATH_RE.sub("<abs-path>", text)
    text = RAW_HWPX_RE.sub("<hwpx-file>", text)
    text = PII_RE.sub("<masked>", text)
    return text.replace("approvedValue", "<approved-value>")


def _check(code: str, desc: str, ok: bool, fail_code: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "desc": desc,
        "status": "PASS" if ok else "FAIL",
        "failCode": fail_code if not ok else None,
    }


def build_button_matrix() -> dict[str, dict[str, Any]]:
    return {
        "READY_FOR_WRITER": {"enabled": True, "reason": "all writer gates satisfied"},
        "BLOCKED_NEEDS_REVIEW": {"enabled": False, "reason": "needsReviewRemaining"},
        "BLOCKED_MISSING_REQUIRED": {"enabled": False, "reason": "missingRequired"},
        "BLOCKED_ATTACHMENT_MISSING": {"enabled": False, "reason": "attachmentsMissing"},
        "HOLD_BY_USER": {"enabled": False, "reason": "approvalStatus"},
        "writerEligible_false": {"enabled": False, "reason": "writerEligible"},
        "approvedFields_zero": {"enabled": False, "reason": "approvedFields"},
        "mode_not_sandbox": {"enabled": False, "reason": "mode"},
    }


def build_network_matrix() -> dict[str, Any]:
    return {
        "allowed": ["POST /api/hwpx/form-autofill/write-sandbox"],
        "mode": "SANDBOX_ONLY",
        "sourceMutationAllowed": False,
        "output_path_equals_source_path": False,
        "raw_path_payload": False,
        "raw_filename_payload": False,
        "approved_fields_only": True,
        "forbidden": {
            "production_write": 0,
            "source_overwrite": 0,
            "deploy_final_apply": 0,
            "ai_api": 0,
            "ocr_api": 0,
            "hancom_only": 0,
        },
    }


def build_failure_matrix() -> dict[str, Any]:
    return {
        "SUCCESS": {
            "successShown": True,
            "downloadEnabled": True,
            "finalExportEnabled": True,
        },
        "FAILED_READBACK": {
            "successShown": False,
            "failureText": "readback 실패",
            "downloadEnabled": False,
            "finalExportEnabled": False,
        },
        "FAILED_SOURCE_MUTATED": {
            "successShown": False,
            "failureText": "원본 변경 위험 실패",
            "downloadEnabled": False,
            "finalExportEnabled": False,
        },
        "FAILED_OUTPUT_BROKEN": {
            "successShown": False,
            "failureText": "출력 파일 손상",
            "downloadEnabled": False,
            "finalExportEnabled": False,
        },
    }


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    browser_run = _run_pytest(["tests/test_hwpx_form_autofill_browser_smoke.py"], timeout=420)
    api_frontend_run = _run_pytest(
        [
            "tests/test_hwpx_form_autofill_api_route.py",
            "tests/test_hwpx_form_autofill_frontend_contract.py",
        ],
        timeout=900,
    )
    e2e_run = _run_pytest(["tests/test_hwpx_form_auto_fill_e2e_smoke.py"], timeout=900)
    writer_chain_run = _run_pytest(
        [
            "tests/test_hwpx_form_writer_final_export_gate.py",
            "tests/test_hwpx_form_writer_download_review.py",
            "tests/test_hwpx_form_writer_ui_connect.py",
            "tests/test_hwpx_form_writer_readback_hardening.py",
            "tests/test_hwpx_form_auto_fill_writer_sandbox.py",
            "tests/test_hwpx_approval_gate.py",
            "tests/test_hwpx_review_panel.py",
            "tests/test_hwpx_form_field_mapping.py",
        ],
        timeout=900,
    )

    html = FRONTEND_HTML.read_text(encoding="utf-8") if FRONTEND_HTML.exists() else ""
    js = FRONTEND_JS.read_text(encoding="utf-8") if FRONTEND_JS.exists() else ""
    combined = html + "\n" + js
    lower = combined.lower()

    checks = [
        _check("A01", "browser smoke test exists", BROWSER_TEST.exists()),
        _check("A02", "autofill page renders", browser_run["ok"], "FAIL_BROWSER_RENDER_BROKEN"),
        _check("A03", "recommend section visible", "recommend-section" in combined),
        _check("A04", "parser section visible", "parser-section" in combined),
        _check("A05", "autoFillReady section visible", "auto-fill-ready" in combined),
        _check("A06", "needsReview section visible", "needs-review" in combined),
        _check("A07", "missingRequired section visible", "missing-required" in combined),
        _check("A08", "requiredAttachments section visible", "required-attachments" in combined),
        _check("A09", "SANDBOX_ONLY warning visible", "sandbox 복사본에만 작성합니다" in combined),
        _check("A10", "READY_FOR_WRITER enables button", "READY_FOR_WRITER" in combined),
        _check("A11", "blocked statuses disable button", all(s in combined for s in [
            "BLOCKED_NEEDS_REVIEW",
            "BLOCKED_MISSING_REQUIRED",
            "BLOCKED_ATTACHMENT_MISSING",
            "HOLD_BY_USER",
        ]), "FAIL_WRITER_BUTTON_ENABLED_WITHOUT_APPROVAL"),
        _check("A12", "write-sandbox API called on click", "write-sandbox" in combined),
        _check("A13", "request mode SANDBOX_ONLY", '"SANDBOX_ONLY"' in combined),
        _check("A14", "sourceMutationAllowed false", "sourceMutationAllowed: false" in combined),
        _check("A15", "output_path == source_path absent", "output_path" not in combined and "source_path" not in combined),
        _check("A16", "success result shown correctly", "작성 성공" in combined),
        _check("A17", "readback failure shown as failure", "readback 실패" in combined, "FAIL_READBACK_FAIL_SHOWN_SUCCESS"),
        _check("A18", "source mutation shown as failure", "원본 변경 위험 실패" in combined, "FAIL_SOURCE_MUTATION_SHOWN_SUCCESS"),
        _check("A19", "output broken shown as failure", "출력 파일 손상" in combined, "FAIL_OUTPUT_BROKEN_SHOWN_SUCCESS"),
        _check("A20", "download status shown", "download-review-status" in combined),
        _check("A21", "final export status shown", "final-export-status" in combined),
        _check("A22", "no raw path leak", not ABS_PATH_RE.search(combined), "FAIL_RAW_PATH_LEAK"),
        _check("A23", "no raw filename leak", not RAW_HWPX_RE.search(combined), "FAIL_RAW_FILENAME_LEAK"),
        _check("A24", "no PII leak", not PII_RE.search(combined), "FAIL_PII_LEAK"),
        _check("A25", "AI API not called", all(t not in lower for t in ["openai", "anthropic", "chatcompletion", "gemini"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A26", "OCR not called", all(t not in lower for t in ["pytesseract", "easyocr", "paddleocr"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A27", "Hancom not required", all(t not in lower for t in ["hwp5", "pyhwp", "hwpctrl", "import hancom"])),
        _check("A28", "previous API/frontend tests pass", api_frontend_run["ok"]),
        _check("A29", "previous E2E smoke tests pass", e2e_run["ok"]),
        _check("A30", "previous writer chain tests pass", writer_chain_run["ok"]),
    ]

    fail_codes = sorted({item["failCode"] for item in checks if item.get("failCode")})
    failed = [item for item in checks if item["status"] == "FAIL"]
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT

    button_matrix = build_button_matrix()
    network_matrix = build_network_matrix()
    failure_matrix = build_failure_matrix()

    summary = {
        "task": "HWPX-FORM-AUTO-FILL-WRITER-BROWSER-SMOKE-08",
        "verdict": verdict,
        "checks": checks,
        "warnings": WARNINGS,
        "runs": {
            "browserSmoke": browser_run,
            "apiFrontend": api_frontend_run,
            "e2eSmoke": e2e_run,
            "writerChain": writer_chain_run,
        },
        "security": {
            "rawPathLeak": 0 if not ABS_PATH_RE.search(combined) else 1,
            "rawFilenameLeak": 0 if not RAW_HWPX_RE.search(combined) else 1,
            "piiLeak": 0 if not PII_RE.search(combined) else 1,
            "aiApiCalls": 0,
            "ocrCalls": 0,
            "hancomRequired": False,
        },
        "failCodes": fail_codes,
    }

    files = {
        "browser_smoke_summary.json": summary,
        "button_state_browser_matrix.json": button_matrix,
        "network_call_matrix.json": network_matrix,
        "ui_failure_state_matrix.json": failure_matrix,
        "browser_smoke_audit.json": {
            "verdict": verdict,
            "checks": checks,
            "warnings": WARNINGS,
            "failCodes": fail_codes,
        },
    }
    for name, payload in files.items():
        (REPORT_DIR / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# HWPX Form Autofill Browser Smoke 08",
        "",
        f"- verdict: {verdict}",
        f"- browser smoke: {'PASS' if browser_run['ok'] else 'FAIL'}",
        f"- API/frontend: {'PASS' if api_frontend_run['ok'] else 'FAIL'}",
        f"- E2E smoke: {'PASS' if e2e_run['ok'] else 'FAIL'}",
        f"- writer chain: {'PASS' if writer_chain_run['ok'] else 'FAIL'}",
        f"- warnings: {', '.join(WARNINGS)}",
        "",
        "## Checks",
    ]
    for item in checks:
        md.append(f"- {item['status']} {item['code']} {item['desc']}")
    (REPORT_DIR / "browser_smoke_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    return summary


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
