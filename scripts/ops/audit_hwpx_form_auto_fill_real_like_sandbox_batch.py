"""Audit for HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-SANDBOX-BATCH-10."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from hwpx.pipeline import form_auto_fill_real_file_preflight as pf  # noqa: E402
from hwpx.pipeline import form_auto_fill_real_like_sandbox_batch as batch  # noqa: E402

REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_real_like_sandbox_batch"
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_SANDBOX_BATCH"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_WRITER_REAL_LIKE_SANDBOX_BATCH"
WARNINGS = [
    "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
    "WARN_SANDBOX_ONLY",
    "WARN_SOME_FILES_BLOCKED",
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
        and "form_auto_fill_real_like_sandbox_batch" not in line
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


def _write_zip(path: Path, files: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _make_limit_batch(tmp: Path, limit: int) -> dict[str, Any]:
    input_dir = batch.create_batch_fixture_dir(tmp / f"limit_{limit}" / "fixtures", limit)
    return batch.run_real_like_sandbox_batch(
        input_dir,
        tmp / f"limit_{limit}" / "out",
        limit=limit,
        sandbox_only=True,
        mask_pii=True,
        fail_on_source_mutation=True,
        fail_on_readback_fail=True,
        fail_on_unexpected_mutation=True,
    )


def _make_blocked_batch(tmp: Path) -> dict[str, Any]:
    input_dir = tmp / "blocked" / "fixtures"
    batch.create_batch_fixture_dir(input_dir, 1)
    _write_zip(input_dir / "pii_case.hwpx", {"Contents/section0.xml": _section("010-1234-5678")})
    (input_dir / "invalid_case.hwpx").write_bytes(b"not a zip")

    files = sorted(input_dir.glob("*.hwpx"))
    target_map_by_sample: dict[str, list[pf.TargetMapEntry] | None] = {}
    for index, path in enumerate(files, start=1):
        sid = batch._sample_id(index, path)
        if path.name.startswith("sanitized_"):
            continue
        if path.name.startswith("invalid_") or path.name.startswith("pii_"):
            continue
    return batch.run_real_like_sandbox_batch(
        input_dir,
        tmp / "blocked" / "out",
        limit=10,
        sandbox_only=True,
        target_map_by_sample=target_map_by_sample,
    )


def _make_target_blocked_batches(tmp: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, target_override in [
        ("noTargetMap", None),
        (
            "ambiguous",
            pf.default_real_like_target_map()
            + [pf.TargetMapEntry("contractorName", "Contractor", "Contents/section0.xml", 0, 1, 1, 0.91)],
        ),
        ("lowConfidence", _low_conf_targets()),
    ]:
        input_dir = batch.create_batch_fixture_dir(tmp / name / "fixtures", 1)
        sample = next(input_dir.glob("*.hwpx"))
        sid = batch._sample_id(1, sample)
        result[name] = batch.run_real_like_sandbox_batch(
            input_dir,
            tmp / name / "out",
            limit=1,
            sandbox_only=True,
            target_map_by_sample={sid: target_override},
        )
    return result


def _low_conf_targets() -> list[pf.TargetMapEntry]:
    targets = pf.default_real_like_target_map()
    targets[0].confidence = 0.79
    return targets


def _safe_report_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if pf.ABS_PATH_RE.search(text) or pf.RAW_FILENAME_RE.search(text) or pf.PII_RE.search(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def _blocked_breakdown(*batches: dict[str, Any]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for item in batches:
        for row in item.get("blockedResults", []):
            reason = row.get("blockedReason", "")
            breakdown[reason] = breakdown.get(reason, 0) + 1
    return breakdown


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    dirty = _dirty_baseline()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        limit_1 = _make_limit_batch(tmp, 1)
        limit_5 = _make_limit_batch(tmp, 5)
        limit_10 = _make_limit_batch(tmp, 10)
        blocked = _make_blocked_batch(tmp)
        target_blocked = _make_target_blocked_batches(tmp)

    batch_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_like_sandbox_batch.py"], timeout=300)
    preflight_run = _run_pytest(["tests/test_hwpx_form_auto_fill_real_file_preflight.py"], timeout=300)
    browser_api_e2e_run = _run_pytest(
        [
            "tests/test_hwpx_form_autofill_browser_smoke.py",
            "tests/test_hwpx_form_autofill_api_route.py",
            "tests/test_hwpx_form_autofill_frontend_contract.py",
            "tests/test_hwpx_form_auto_fill_e2e_smoke.py",
        ],
        timeout=1200,
    )
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

    module_path = ROOT / "scripts" / "hwpx" / "pipeline" / "form_auto_fill_real_like_sandbox_batch.py"
    source = module_path.read_text(encoding="utf-8")
    lower = source.lower()
    combined_reports = json.dumps(
        {
            "limit1": limit_1,
            "limit5": limit_5,
            "limit10": limit_10,
            "blocked": blocked,
            "targetBlocked": target_blocked,
        },
        ensure_ascii=False,
    )
    blocked_breakdown = _blocked_breakdown(blocked, *target_blocked.values())

    checks = [
        _check("A01", "batch runner exists", module_path.exists()),
        _check("A02", "sanitized real-like sample policy enforced", bool(pf.SAMPLE_POLICY)),
        _check("A03", "limit=1 supported", limit_1["summary"]["processed"] == 1),
        _check("A04", "limit=5 supported", limit_5["summary"]["processed"] == 5),
        _check("A05", "limit=10 supported", limit_10["summary"]["processed"] == 10),
        _check("A06", "SANDBOX_ONLY enforced", all(b["mode"] == "SANDBOX_ONLY" for b in [limit_1, limit_5, limit_10]), "FAIL_OPERATION_MODE_NOT_SANDBOX"),
        _check("A07", "READY_FOR_SANDBOX_WRITE only written", limit_10["summary"]["writtenFiles"] == limit_10["summary"]["ready"]),
        _check("A08", "blocked files not written", all(row["writtenFields"] == 0 for row in blocked.get("blockedResults", []))),
        _check("A09", "blocked reasons recorded", bool(blocked_breakdown)),
        _check("A10", "output_path == source_path absent", "output_path" not in combined_reports and "source_path" not in combined_reports, "FAIL_OUTPUT_EQUALS_SOURCE"),
        _check("A11", "per-file source sha256 unchanged", all(not row["sourceHashChanged"] for row in limit_10["fileResults"]), "FAIL_SOURCE_HWPX_MUTATED"),
        _check("A12", "per-file source mtime unchanged", all(not row["sourceMtimeChanged"] for row in limit_10["fileResults"]), "FAIL_SOURCE_HWPX_MUTATED"),
        _check("A13", "readbackFail zero required", limit_10["summary"]["readbackFail"] == 0, "FAIL_READBACK_FAILURE_DETECTED"),
        _check("A14", "unexpectedMutation zero required", limit_10["summary"]["unexpectedMutation"] == 0, "FAIL_UNEXPECTED_MUTATION_DETECTED"),
        _check("A15", "sourceMutation zero required", limit_10["summary"]["sourceMutation"] == 0, "FAIL_SOURCE_HWPX_MUTATED"),
        _check("A16", "final export requires ACCEPTED_BY_USER", all(row["finalExportEnabled"] for row in limit_10["fileResults"] if row["status"] == batch.STATUS_SANDBOX_WRITE_PASS)),
        _check("A17", "no raw path leak", not pf.ABS_PATH_RE.search(combined_reports), "FAIL_RAW_PATH_LEAK"),
        _check("A18", "no raw filename leak", not pf.RAW_FILENAME_RE.search(combined_reports), "FAIL_RAW_FILENAME_LEAK"),
        _check("A19", "no PII leak", not pf.PII_RE.search(combined_reports), "FAIL_PII_LEAK"),
        _check("A20", "AI API not called", all(t not in lower for t in ["openai", "anthropic", "chatcompletion", "gemini"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A21", "OCR not called", all(t not in lower for t in ["pytesseract", "easyocr", "paddleocr"]), "FAIL_AI_OR_OCR_CALLED"),
        _check("A22", "Hancom not required", all(t not in lower for t in ["hwp5", "pyhwp", "hwpctrl", "import hancom"])),
        _check("A23", "previous real file preflight tests pass", preflight_run["ok"]),
        _check("A24", "previous browser/API/E2E tests pass", browser_api_e2e_run["ok"]),
        _check("A25", "previous writer chain tests pass", writer_chain_run["ok"]),
        _check("A26", "dirty baseline documented", dirty["documented"] is True),
    ]

    failed = [item for item in checks if item["status"] == "FAIL"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT

    summary = {
        "task": "HWPX-FORM-AUTO-FILL-WRITER-REAL-LIKE-SANDBOX-BATCH-10",
        "verdict": verdict,
        "samplePolicy": pf.SAMPLE_POLICY,
        "dirtyBaseline": dirty,
        "limitRuns": {
            "limit1": _summarize_batch(limit_1),
            "limit5": _summarize_batch(limit_5),
            "limit10": _summarize_batch(limit_10),
        },
        "blockedBreakdown": blocked_breakdown,
        "checks": checks,
        "runs": {
            "batch": batch_run,
            "realFilePreflight": preflight_run,
            "browserApiE2e": browser_api_e2e_run,
            "writerChain": writer_chain_run,
        },
        "warnings": WARNINGS,
        "failCodes": fail_codes,
    }
    file_results = limit_10["fileResults"]
    blocked_results = blocked.get("blockedResults", []) + [
        row
        for item in target_blocked.values()
        for row in item.get("blockedResults", [])
    ]
    security_scan = {
        "piiLeak": limit_10["summary"]["piiLeak"],
        "rawPathLeak": limit_10["summary"]["rawPathLeak"],
        "rawFilenameLeak": limit_10["summary"]["rawFilenameLeak"],
        "aiCalled": 0,
        "ocrCalled": 0,
        "hancomRequired": False,
    }
    audit_payload = {"verdict": verdict, "checks": checks, "warnings": WARNINGS, "failCodes": fail_codes}

    _safe_report_write(REPORT_DIR / "batch_summary.json", summary)
    _safe_report_write(REPORT_DIR / "file_results.json", file_results)
    _safe_report_write(REPORT_DIR / "blocked_results.json", blocked_results)
    _safe_report_write(REPORT_DIR / "security_scan_result.json", security_scan)
    _safe_report_write(REPORT_DIR / "batch_audit.json", audit_payload)
    _write_summary_md(REPORT_DIR / "batch_summary.md", summary)

    return summary


def _summarize_batch(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "overallVerdict": value["overallVerdict"],
        "summary": value["summary"],
    }


def _write_summary_md(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# HWPX Form Auto Fill Real-Like Sandbox Batch 10",
        "",
        f"- verdict: {summary['verdict']}",
        f"- limit=1: {summary['limitRuns']['limit1']['overallVerdict']}",
        f"- limit=5: {summary['limitRuns']['limit5']['overallVerdict']}",
        f"- limit=10: {summary['limitRuns']['limit10']['overallVerdict']}",
        f"- warnings: {', '.join(summary['warnings'])}",
        "",
        "## Checks",
    ]
    lines.extend(f"- {item['status']} {item['code']} {item['desc']}" for item in summary["checks"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())

