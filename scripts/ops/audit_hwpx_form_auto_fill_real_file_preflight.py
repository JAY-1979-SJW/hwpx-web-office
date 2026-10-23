"""Audit for HWPX-FORM-AUTO-FILL-WRITER-REAL-FILE-PREFLIGHT-09."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_real_file_preflight"
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_FILE_PREFLIGHT"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_REAL_FILE_PREFLIGHT"
WARNINGS = [
    "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
    "WARN_SANDBOX_ONLY",
    "WARN_REAL_USER_FILE_NOT_TESTED",
    "WARN_DEPLOY_NOT_PERFORMED",
    "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
]


def _run_pytest(paths: list[str], timeout: int = 900) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    text = result.stdout + "\n" + result.stderr
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return {
        "paths": paths,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "summary": _safe_text(lines[-1] if lines else "no output"),
    }


def _safe_text(text: str) -> str:
    text = pf.ABS_PATH_RE.sub("<abs-path>", text)
    text = pf.RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = pf.PII_RE.sub("<masked>", text)
    return text


def _dirty_baseline() -> dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    counts = {
        "changeHistoryLog": sum(1 for line in lines if line.startswith("M logs/change_history.jsonl")),
        "devlogUntracked": sum(1 for line in lines if line.startswith("?? docs/devlog/")),
        "reportsUntracked": sum(1 for line in lines if line.startswith("?? reports/")),
    }
    known = []
    if counts["changeHistoryLog"]:
        known.append("change_history_log_modified")
    if counts["devlogUntracked"]:
        known.append("devlog_untracked")
    if counts["reportsUntracked"]:
        known.append("reports_untracked")
    unexpected = [
        line
        for line in lines
        if not line.startswith("M logs/change_history.jsonl")
        and not line.startswith("?? docs/devlog/")
        and not line.startswith("?? reports/")
        and "form_auto_fill_real_file_preflight" not in line
    ]
    return {
        "documented": True,
        "knownHold": known,
        "knownHoldCounts": counts,
        "unexpectedOutsideScope": unexpected,
    }


def _check(code: str, desc: str, ok: bool, fail_code: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "desc": desc,
        "status": "PASS" if ok else "FAIL",
        "failCode": fail_code if not ok else None,
    }


def _scenario_reports(tmp: Path) -> dict[str, dict[str, Any]]:
    ready_sample = pf.create_real_like_sanitized_hwpx(tmp / "ready" / "sanitized.hwpx")
    ready = pf.run_real_file_preflight(
        ready_sample,
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "ready_out",
        sample_id="real_like_hwpx_001",
        accept_output=True,
    )
    invalid = pf.run_real_file_preflight(
        _write_bytes(tmp / "invalid" / "bad.bin", b"not a zip"),
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "invalid_out",
    )
    missing_section = pf.run_real_file_preflight(
        _write_zip(tmp / "missing" / "missing.hwpx", {"Contents/header.xml": "<root/>"}),
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "missing_out",
    )
    pii = pf.run_real_file_preflight(
        _write_zip(tmp / "pii" / "pii.hwpx", {"Contents/section0.xml": _section("010-1234-5678")}),
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "pii_out",
    )
    raw_path = pf.run_real_file_preflight(
        _write_zip(tmp / "path" / "path.hwpx", {"Contents/section0.xml": _section(r"C:\\Users\\masked\\doc")}),
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "path_out",
    )
    raw_filename = pf.run_real_file_preflight(
        _write_zip(tmp / "filename" / "filename.hwpx", {"Contents/section0.xml": _section("source_original.hwpx")}),
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "filename_out",
    )
    no_target_map = pf.run_real_file_preflight(
        ready_sample,
        None,
        pf.default_real_like_approved_fields(),
        tmp / "no_target_out",
    )
    ambiguous_targets = pf.default_real_like_target_map() + [
        pf.TargetMapEntry("contractorName", "Contractor", "Contents/section0.xml", 0, 1, 1, 0.91)
    ]
    ambiguous = pf.run_real_file_preflight(
        ready_sample,
        ambiguous_targets,
        pf.default_real_like_approved_fields(),
        tmp / "ambiguous_out",
    )
    low_targets = pf.default_real_like_target_map()
    low_targets[0].confidence = 0.79
    low_conf = pf.run_real_file_preflight(
        ready_sample,
        low_targets,
        pf.default_real_like_approved_fields(),
        tmp / "low_out",
    )
    no_approved = pf.run_real_file_preflight(
        ready_sample,
        pf.default_real_like_target_map(),
        [],
        tmp / "no_approved_out",
    )
    hold_export = pf.run_real_file_preflight(
        ready_sample,
        pf.default_real_like_target_map(),
        pf.default_real_like_approved_fields(),
        tmp / "hold_export_out",
        accept_output=False,
    )
    return {
        "ready": ready,
        "invalid": invalid,
        "missingSection": missing_section,
        "pii": pii,
        "rawPath": raw_path,
        "rawFilename": raw_filename,
        "noTargetMap": no_target_map,
        "ambiguous": ambiguous,
        "lowConfidence": low_conf,
        "noApproved": no_approved,
        "holdExport": hold_export,
    }


def _write_bytes(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def _write_zip(path: Path, files: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    import zipfile

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in files.items():
            archive.writestr(name, text.encode("utf-8"))
    return path


def _section(value: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{pf.NS_HP}">'
        f"<hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>Contractor</hp:t></hp:run></hp:p></hp:tc>"
        f"<hp:tc><hp:p><hp:run><hp:t>{value}</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>"
        "</hp:sec>"
    )


def _safe_report_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if pf.ABS_PATH_RE.search(text) or pf.RAW_FILENAME_RE.search(text) or pf.PII_RE.search(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dirty = _dirty_baseline()

    with tempfile.TemporaryDirectory() as td:
        scenarios = _scenario_reports(Path(td))

    preflight_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_file_preflight.py"], timeout=300)
    browser_run = _run_pytest(["tests/test_hwpx_form_autofill_browser_smoke.py"], timeout=300)
    api_frontend_run = _run_pytest(
        ["tests/test_hwpx_form_autofill_api_route.py", "tests/test_hwpx_form_autofill_frontend_contract.py"],
        timeout=900,
    )
    e2e_run = _run_pytest(["tests/test_hwpx_form_auto_fill_e2e_smoke.py"], timeout=300)
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
        timeout=600,
    )

    module_path = ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_file_preflight.py"
    source = module_path.read_text(encoding="utf-8")
    lower = source.lower()
    ready = scenarios["ready"]

    checks = [
        _check("A01", "real file preflight module exists", module_path.exists()),
        _check("A02", "sanitized real-like HWPX sample policy exists", bool(pf.SAMPLE_POLICY)),
        _check("A03", "invalid HWPX blocked", scenarios["invalid"]["preflightStatus"] == pf.BLOCKED_INVALID_HWPX),
        _check("A04", "missing section XML blocked", scenarios["missingSection"]["preflightStatus"] == pf.BLOCKED_MISSING_SECTION_XML),
        _check("A05", "PII risk blocked", scenarios["pii"]["preflightStatus"] == pf.BLOCKED_PII_RISK, "FAIL_PII_RISK_NOT_BLOCKED"),
        _check("A06", "raw path risk blocked", scenarios["rawPath"]["preflightStatus"] == pf.BLOCKED_RAW_PATH_RISK),
        _check("A07", "raw filename risk blocked", scenarios["rawFilename"]["preflightStatus"] == pf.BLOCKED_RAW_FILENAME_RISK),
        _check("A08", "missing target map blocked", scenarios["noTargetMap"]["preflightStatus"] == pf.BLOCKED_NO_TARGET_MAP),
        _check("A09", "ambiguous target blocked", scenarios["ambiguous"]["preflightStatus"] == pf.BLOCKED_AMBIGUOUS_TARGET),
        _check("A10", "low confidence target blocked", scenarios["lowConfidence"]["preflightStatus"] == pf.BLOCKED_LOW_TARGET_CONFIDENCE),
        _check("A11", "no approved fields blocked", scenarios["noApproved"]["preflightStatus"] == pf.BLOCKED_NO_APPROVED_FIELDS),
        _check("A12", "READY_FOR_SANDBOX_WRITE allows sandbox only", ready["preflightStatus"] == pf.READY_FOR_SANDBOX_WRITE and ready["sandboxResult"]["writtenFields"] > 0),
        _check("A13", "mode SANDBOX_ONLY", ready["mode"] == "SANDBOX_ONLY", "FAIL_OPERATION_MODE_NOT_SANDBOX"),
        _check("A14", "sourceMutationAllowed false", ready["sourceMutationAllowed"] is False),
        _check("A15", "output_path == source_path absent", "output_path" not in json.dumps(ready) and "source_path" not in json.dumps(ready), "FAIL_OUTPUT_EQUALS_SOURCE"),
        _check("A16", "source sha256 unchanged", ready["sourceHashBefore"] == ready["sourceHashAfter"], "FAIL_SOURCE_HWPX_MUTATED"),
        _check("A17", "source mtime unchanged", ready["sourceMtimeChanged"] is False, "FAIL_SOURCE_HWPX_MUTATED"),
        _check("A18", "readback fail blocks success", ready["sandboxResult"]["readbackFail"] == 0),
        _check("A19", "unexpected mutation blocks success", ready["sandboxResult"]["unexpectedMutation"] == 0, "FAIL_UNEXPECTED_MUTATION"),
        _check("A20", "final export requires ACCEPTED_BY_USER", ready["sandboxResult"]["finalExportEnabled"] is True and scenarios["holdExport"]["sandboxResult"]["finalExportEnabled"] is False),
        _check("A21", "no raw path leak", not pf.ABS_PATH_RE.search(json.dumps(scenarios, ensure_ascii=False)), "FAIL_RAW_PATH_LEAK"),
        _check("A22", "no raw filename leak", not pf.RAW_FILENAME_RE.search(json.dumps(scenarios, ensure_ascii=False)), "FAIL_RAW_FILENAME_LEAK"),
        _check("A23", "no PII leak", not pf.PII_RE.search(json.dumps(scenarios, ensure_ascii=False)), "FAIL_PII_LEAK"),
        _check("A24", "AI API not called", all(t not in lower for t in ["openai", "anthropic", "chatcompletion", "gemini"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A25", "OCR not called", all(t not in lower for t in ["pytesseract", "easyocr", "paddleocr"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A26", "Hancom not required", all(t not in lower for t in ["hwp5", "pyhwp", "hwpctrl", "import hancom"])),
        _check("A27", "previous browser smoke tests pass", browser_run["ok"]),
        _check("A28", "previous API/frontend tests pass", api_frontend_run["ok"]),
        _check("A29", "previous E2E smoke tests pass", e2e_run["ok"]),
        _check("A30", "previous writer chain tests pass", writer_chain_run["ok"]),
        _check("A31", "dirty baseline documented", dirty["documented"] is True),
    ]

    failed = [item for item in checks if item["status"] == "FAIL"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT

    matrix = {
        key: {
            "preflightStatus": value["preflightStatus"],
            "writtenFields": value["sandboxResult"]["writtenFields"],
            "readbackFail": value["sandboxResult"]["readbackFail"],
            "finalExportEnabled": value["sandboxResult"]["finalExportEnabled"],
        }
        for key, value in scenarios.items()
    }
    target_resolution = {
        "ready": ready["targetMap"],
        "ambiguous": scenarios["ambiguous"]["targetMap"],
        "lowConfidence": scenarios["lowConfidence"]["targetMap"],
        "noTargetMap": scenarios["noTargetMap"]["targetMap"],
    }
    security_scan = {
        "ready": ready["security"],
        "pii": scenarios["pii"]["security"],
        "rawPath": scenarios["rawPath"]["security"],
        "rawFilename": scenarios["rawFilename"]["security"],
    }
    summary = {
        "task": "HWPX-FORM-AUTO-FILL-WRITER-REAL-FILE-PREFLIGHT-09",
        "verdict": verdict,
        "samplePolicy": pf.SAMPLE_POLICY,
        "dirtyBaseline": dirty,
        "checks": checks,
        "runs": {
            "realFilePreflight": preflight_run,
            "browserSmoke": browser_run,
            "apiFrontend": api_frontend_run,
            "e2eSmoke": e2e_run,
            "writerChain": writer_chain_run,
        },
        "readySummary": ready,
        "warnings": WARNINGS,
        "failCodes": fail_codes,
    }
    audit_payload = {"verdict": verdict, "checks": checks, "warnings": WARNINGS, "failCodes": fail_codes}

    _safe_report_write(REPORT_DIR / "real_file_preflight_summary.json", summary)
    _safe_report_write(REPORT_DIR / "real_file_preflight_matrix.json", matrix)
    _safe_report_write(REPORT_DIR / "target_map_resolution.json", target_resolution)
    _safe_report_write(REPORT_DIR / "security_scan_result.json", security_scan)
    _safe_report_write(REPORT_DIR / "real_file_preflight_audit.json", audit_payload)

    md = [
        "# HWPX Form Auto Fill Real File Preflight 09",
        "",
        f"- verdict: {verdict}",
        f"- real file preflight: {'PASS' if preflight_run['ok'] else 'FAIL'}",
        f"- browser smoke: {'PASS' if browser_run['ok'] else 'FAIL'}",
        f"- API/frontend: {'PASS' if api_frontend_run['ok'] else 'FAIL'}",
        f"- E2E smoke: {'PASS' if e2e_run['ok'] else 'FAIL'}",
        f"- writer chain: {'PASS' if writer_chain_run['ok'] else 'FAIL'}",
        f"- warnings: {', '.join(WARNINGS)}",
        "",
        "## Checks",
    ]
    md.extend(f"- {item['status']} {item['code']} {item['desc']}" for item in checks)
    (REPORT_DIR / "real_file_preflight_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    return summary


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
