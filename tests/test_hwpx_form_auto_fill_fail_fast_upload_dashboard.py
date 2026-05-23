"""Tests for fail-fast gate, module history, upload gate, and dashboard."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.build_hwpx_form_auto_fill_gate_dashboard as dashboard  # noqa: E402
import scripts.ops.gate_hwpx_form_auto_fill_fail_fast as fail_fast  # noqa: E402
import scripts.ops.gate_hwpx_form_auto_fill_upload as upload_gate  # noqa: E402
import scripts.ops.hwpx_form_auto_fill_module_audit_history as history  # noqa: E402


def test_01_scripts_importable() -> None:
    assert hasattr(fail_fast, "run_fail_fast_gate")
    assert hasattr(upload_gate, "evaluate_upload_request")
    assert hasattr(history, "write_history")
    assert hasattr(dashboard, "build_dashboard")


def test_02_upload_gate_accepts_sanitized_sandbox_metadata() -> None:
    result = upload_gate.evaluate_upload_request(
        {
            "mode": "SANDBOX_ONLY",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": False,
            "displayName": "sanitized_building_form",
            "packageKind": "SYNTHETIC_PACKAGE",
            "sourcePathHint": "source_a",
            "outputPathHint": "output_a",
        }
    )
    assert result["status"] == upload_gate.UPLOAD_ACCEPTED
    assert result["allowedForPreflight"] is True
    assert result["allowedForWriter"] is False


def test_03_upload_gate_blocks_real_user_file() -> None:
    result = upload_gate.evaluate_upload_request(
        {
            "mode": "SANDBOX_ONLY",
            "sourceMutationAllowed": False,
            "declaredSanitized": True,
            "realUserFile": True,
            "displayName": "sanitized_building_form",
            "packageKind": "HWPX_PACKAGE",
        }
    )
    assert result["status"] == "BLOCKED"
    assert result["blockedReason"] == upload_gate.BLOCKED_REAL_USER_FILE


def test_04_upload_gate_blocks_security_risks() -> None:
    cases = [
        ({"mode": "PRODUCTION"}, upload_gate.BLOCKED_NON_SANDBOX_MODE),
        ({"contentPreview": "phone 010-1234-5678"}, upload_gate.BLOCKED_PII_RISK),
        ({"displayName": "source.hwpx"}, upload_gate.BLOCKED_RAW_FILENAME_RISK),
        ({"sourcePathHint": "source_a", "outputPathHint": "source_a"}, upload_gate.BLOCKED_OUTPUT_EQUALS_SOURCE),
        ({"sourceMutationAllowed": True}, upload_gate.BLOCKED_SOURCE_MUTATION_ALLOWED),
    ]
    base = {
        "mode": "SANDBOX_ONLY",
        "sourceMutationAllowed": False,
        "declaredSanitized": True,
        "realUserFile": False,
        "displayName": "sanitized_building_form",
        "packageKind": "HWPX_PACKAGE",
        "sourcePathHint": "source_a",
        "outputPathHint": "output_a",
        "contentPreview": "masked",
    }
    for patch, expected in cases:
        payload = dict(base)
        payload.update(patch)
        result = upload_gate.evaluate_upload_request(payload)
        assert result["blockedReason"] == expected


def test_05_upload_gate_scenarios_write_safe_reports(tmp_path: Path) -> None:
    result = upload_gate.run_upload_gate_scenarios(report_dir=tmp_path)
    assert result["verdict"] == upload_gate.PASS_VERDICT
    assert (tmp_path / "upload_gate_summary.json").is_file()
    assert (tmp_path / "upload_gate_matrix.json").is_file()
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not upload_gate.ABS_PATH_RE.search(text)
        assert not upload_gate.RAW_FILENAME_RE.search(text)
        assert not upload_gate.PII_RE.search(text)


def test_06_module_history_writes_records(tmp_path: Path) -> None:
    payload = {
        "moduleResults": [
            {
                "id": "field_mapping",
                "status": "PASS",
                "staticStatus": "PASS",
                "pytest": {
                    "status": "PASS",
                    "durationSeconds": 0.1,
                    "attempts": 1,
                    "summary": "1 passed",
                },
                "missingFiles": [],
                "missingTokens": [],
                "forbiddenSourceHits": [],
                "security": {"piiLeak": 0, "rawPathLeak": 0, "rawFilenameLeak": 0},
            }
        ]
    }
    summary = history.write_history(payload, report_dir=tmp_path, run_id="run_test", append=False)
    assert summary["entriesWritten"] == 1
    assert summary["modulesPassed"] == 1
    assert (tmp_path / "module_audit_history.jsonl").is_file()


def test_07_dashboard_builds_safe_summary(tmp_path: Path) -> None:
    fail_fast_payload = {"verdict": fail_fast.PASS_VERDICT, "summary": {"failedChecks": 0}}
    upload_payload = {"verdict": upload_gate.PASS_VERDICT, "summary": {"accepted": 1, "blocked": 1}}
    history_summary = {"entriesWritten": 1, "modulesPassed": 1, "modulesFailed": 0}
    result = dashboard.build_dashboard(fail_fast_payload, upload_payload, history_summary, report_dir=tmp_path)
    assert result["verdict"] == dashboard.PASS_VERDICT
    assert (tmp_path / "gate_dashboard.json").is_file()
    assert (tmp_path / "gate_dashboard.md").is_file()


def test_08_fail_fast_smoke_runs_all_steps(tmp_path: Path) -> None:
    result = fail_fast.run_fail_fast_gate(report_dir=tmp_path, full_module_audit=False)
    assert result["verdict"] == fail_fast.PASS_VERDICT
    assert result["summary"]["stepsFailed"] == 0
    step_names = {step["name"] for step in result["steps"]}
    for expected in [
        "persistent_gate_installation",
        "module_audits",
        "module_audit_history",
        "zone_gates_from_module_audit",
        "upload_gate",
        "construction_design_audit",
        "repo_detailed_separation_plan",
        "gate_dashboard",
    ]:
        assert expected in step_names
    assert result["separationVerdict"] == fail_fast.separation_plan.PASS_VERDICT


def test_09_fail_fast_reports_have_no_leaks(tmp_path: Path) -> None:
    fail_fast.run_fail_fast_gate(report_dir=tmp_path, full_module_audit=False)
    for path in tmp_path.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not fail_fast.ABS_PATH_RE.search(text)
        assert not fail_fast.RAW_FILENAME_RE.search(text)
        assert not fail_fast.PII_RE.search(text)


def test_10_report_json_is_valid_after_smoke(tmp_path: Path) -> None:
    fail_fast.run_fail_fast_gate(report_dir=tmp_path, full_module_audit=False)
    json.loads((tmp_path / "fail_fast_gate_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "fail_fast_gate_steps.json").read_text(encoding="utf-8"))
