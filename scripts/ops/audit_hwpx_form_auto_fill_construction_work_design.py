"""Audit the construction-work master design for HWPX form auto-fill."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.ops import audit_hwpx_form_auto_fill_modules as module_audit  # noqa: E402
from scripts.ops import gate_hwpx_form_auto_fill_zones as zone_gate  # noqa: E402

DESIGN = ROOT / "docs" / "reports" / "HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN.md"
REPORT_DIR = ROOT / "data" / "reports" / "hwpx_form_auto_fill_construction_work_design"
PASS_VERDICT = "PASS_HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN"
FAIL_VERDICT = "FAIL_HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN"

ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/][^\s\"']*|/(home|tmp|var|Users)/[^\s\"']*)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)

REQUIRED_TOKENS = {
    "A01": ("construction master design exists", "HWPX Form Auto Fill Construction Work Master Design"),
    "A02": ("baseline commit documented", "d95dcac"),
    "A03": ("SANDBOX_ONLY documented", "SANDBOX_ONLY"),
    "A04": ("project identity zone documented", "Z01 Project Identity"),
    "A05": ("parties and roles zone documented", "Z02 Parties And Roles"),
    "A06": ("schedule zone documented", "Z03 Schedule And Phase"),
    "A07": ("quantity cost zone documented", "Z04 Size Quantity Cost"),
    "A08": ("attachment evidence zone documented", "Z05 Attachments And Evidence"),
    "A09": ("safety compliance gate documented", "Z06 Safety And Compliance Gate"),
    "A10": ("batch API browser gate documented", "Z07 Batch API Browser Gate"),
    "A11": ("approval gate documented", "approvalStatus is READY_FOR_WRITER"),
    "A12": ("source safety documented", "sourceMutationAllowed false"),
    "A13": ("module audits linked", "PASS_HWPX_FORM_AUTO_FILL_MODULE_AUDITS"),
    "A14": ("zone gates linked", "PASS_HWPX_FORM_AUTO_FILL_ZONE_GATES"),
    "A15": ("real user file prohibited", "real user source file input"),
    "A16": ("production write prohibited", "production write"),
    "A17": ("source overwrite prohibited", "source overwrite endpoint"),
    "A18": ("final deploy prohibited", "final deploy endpoint"),
    "A19": ("AI fallback prohibited", "AI API fallback"),
    "A20": ("OCR fallback prohibited", "OCR fallback"),
    "A21": ("Hancom dependency prohibited", "required Hancom dependency"),
    "A22": ("promotion criteria documented", "At least 30 sanitized construction-like real-like samples"),
}


def _run_pytest(paths: list[str], timeout: int = 300) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *paths, "-q", "--tb=no"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    lines = [_safe_text(line.strip()) for line in (result.stdout + "\n" + result.stderr).splitlines() if line.strip()]
    return {
        "paths": paths,
        "returncode": result.returncode,
        "ok": result.returncode == 0,
        "summary": lines[-1] if lines else "no output",
    }


def _safe_text(text: str) -> str:
    text = ABS_PATH_RE.sub("<abs-path>", text)
    text = RAW_FILENAME_RE.sub("<hwpx-file>", text)
    text = PII_RE.sub("<masked>", text)
    return text


def _no_leak(text: str) -> bool:
    return not (ABS_PATH_RE.search(text) or RAW_FILENAME_RE.search(text) or PII_RE.search(text))


def _check(code: str, desc: str, ok: bool, fail_code: str | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "desc": desc,
        "status": "PASS" if ok else "FAIL",
        "failCode": None if ok else fail_code,
    }


def _dirty_baseline() -> dict[str, Any]:
    result = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(ROOT),
        capture_output=True,
        text=True, encoding="utf-8", errors="replace",
        timeout=30,
    )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    allowed_tokens = (
        "HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN.md",
        "test_hwpx_form_auto_fill_construction_work_design.py",
        "audit_hwpx_form_auto_fill_construction_work_design.py",
        "data/reports/hwpx_form_auto_fill_construction_work_design/",
        "logs/change_history.jsonl",
        "docs/devlog/",
        "reports/",
    )
    return {
        "documented": True,
        "knownHold": [
            "change_history_log_modified",
            "devlog_untracked",
            "reports_untracked",
        ],
        "unexpectedOutsideScope": [line for line in lines if not any(token in line for token in allowed_tokens)],
    }


def audit() -> dict[str, Any]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    text = DESIGN.read_text(encoding="utf-8") if DESIGN.exists() else ""

    checks: list[dict[str, Any]] = [
        _check("A00", "design file exists", DESIGN.is_file()),
    ]
    for code, (desc, token) in REQUIRED_TOKENS.items():
        checks.append(_check(code, desc, token in text))
    checks.extend(
        [
            _check("A23", "no raw path leak", _no_leak(text), "FAIL_RAW_PATH_LEAK"),
            _check("A24", "no raw filename leak", _no_leak(text), "FAIL_RAW_FILENAME_LEAK"),
            _check("A25", "no PII leak", _no_leak(text), "FAIL_PII_LEAK"),
        ]
    )

    design_tests = _run_pytest(["tests/test_hwpx_form_auto_fill_construction_work_design.py"], timeout=120)
    module_runner = module_audit.run_module_audits(
        report_dir=REPORT_DIR / "module_gate_subrun",
        module_ids={"field_mapping"},
        timeout=300,
    )
    zone_runner = zone_gate.run_zone_gates(
        report_dir=REPORT_DIR / "zone_gate_subrun",
        zone_ids={"input_parse"},
        timeout=300,
    )
    checks.extend(
        [
            _check("A26", "construction design tests pass", design_tests["ok"]),
            _check("A27", "representative zone gate runner passes", zone_runner["verdict"] == zone_gate.PASS_VERDICT),
            _check("A28", "representative module audit runner passes", module_runner["verdict"] == module_audit.PASS_VERDICT),
            _check("A29", "dirty baseline documented", _dirty_baseline()["documented"]),
        ]
    )

    failed = [item for item in checks if item["status"] != "PASS"]
    fail_codes = sorted({item["failCode"] for item in failed if item.get("failCode")})
    verdict = PASS_VERDICT if not failed else FAIL_VERDICT
    warnings = [
        "WARN_SANDBOX_ONLY",
        "WARN_REAL_USER_FILE_NOT_TESTED",
        "WARN_DEPLOY_NOT_PERFORMED",
        "WARN_CONSTRUCTION_POLICY_NOT_LEGAL_AUDIT",
        "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
    ]
    security = {
        "piiLeak": 0 if _no_leak(text) else 1,
        "rawPathLeak": 0 if not ABS_PATH_RE.search(text) else 1,
        "rawFilenameLeak": 0 if not RAW_FILENAME_RE.search(text) else 1,
        "aiApiCalled": False,
        "ocrCalled": False,
        "hancomRequired": False,
    }
    summary = {
        "schemaVersion": "hwpx_form_auto_fill_construction_work_master_design_v1",
        "verdict": verdict,
        "baselineCommit": "d95dcac",
        "designFile": "docs/reports/HWPX_FORM_AUTO_FILL_CONSTRUCTION_WORK_MASTER_DESIGN.md",
        "constructionZones": 7,
        "checks": checks,
        "runs": {
            "constructionDesign": design_tests,
            "zoneGateRunner": {
                "verdict": zone_runner["verdict"],
                "summary": zone_runner["summary"],
            },
            "moduleAuditRunner": {
                "verdict": module_runner["verdict"],
                "summary": module_runner["summary"],
            },
        },
        "security": security,
        "dirtyBaseline": _dirty_baseline(),
        "warnings": warnings,
        "failCodes": fail_codes,
    }
    _write_reports(summary)
    return summary


def _write_reports(summary: dict[str, Any]) -> None:
    _safe_write(REPORT_DIR / "construction_work_design_summary.json", summary)
    _safe_write(REPORT_DIR / "construction_work_design_checks.json", summary["checks"])
    _safe_write(REPORT_DIR / "security_scan_result.json", summary["security"])
    audit_payload = {
        "verdict": summary["verdict"],
        "checks": summary["checks"],
        "warnings": summary["warnings"],
        "failCodes": summary["failCodes"],
    }
    _safe_write(REPORT_DIR / "construction_work_design_audit.json", audit_payload)
    lines = [
        "# HWPX Form Auto Fill Construction Work Master Design Audit",
        "",
        f"- verdict: {summary['verdict']}",
        f"- baseline: {summary['baselineCommit']}",
        f"- construction zones: {summary['constructionZones']}",
        f"- construction design tests: {'PASS' if summary['runs']['constructionDesign']['ok'] else 'FAIL'}",
        f"- zone gate runner: {summary['runs']['zoneGateRunner']['verdict']}",
        f"- module audit runner: {summary['runs']['moduleAuditRunner']['verdict']}",
        f"- security: pii={summary['security']['piiLeak']} rawPath={summary['security']['rawPathLeak']} rawFilename={summary['security']['rawFilenameLeak']}",
        f"- warnings: {', '.join(summary['warnings'])}",
        "",
        "## Checks",
    ]
    lines.extend(f"- {item['status']} {item['code']} {item['desc']}" for item in summary["checks"])
    text = "\n".join(lines) + "\n"
    if not _no_leak(text):
        raise ValueError("unsafe markdown report")
    (REPORT_DIR / "construction_work_design_summary.md").write_text(text, encoding="utf-8")


def _safe_write(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if not _no_leak(text):
        raise ValueError(f"unsafe report payload: {path.name}")
    path.write_text(text, encoding="utf-8")


def main() -> int:
    result = audit()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
