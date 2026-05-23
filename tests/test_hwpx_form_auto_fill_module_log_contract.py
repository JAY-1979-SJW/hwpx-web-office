"""Tests for module audit log contract gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import scripts.ops.gate_hwpx_form_auto_fill_module_log_contract as contract  # noqa: E402
import scripts.ops.hwpx_form_auto_fill_module_audit_history as history  # noqa: E402


def _module_payload() -> dict[str, object]:
    return {
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


def test_01_contract_importable() -> None:
    assert hasattr(contract, "run_module_log_contract_gate")
    assert hasattr(contract, "validate_module_log_contract")


def test_02_history_entries_include_contract_fields() -> None:
    entries = history.build_history_entries(_module_payload(), run_id="run_contract")
    entry = entries[0]
    for field in contract.REQUIRED_FIELDS:
        assert field in entry
    assert entry["moduleId"] == "field_mapping"
    assert entry["zone"] == "input_parse"
    assert entry["verdict"] == "PASS"
    assert entry["security"]["piiLeak"] == 0


def test_03_valid_entries_pass_contract(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.PASS_VERDICT
    assert result["summary"]["expectedModules"] == 1
    assert result["summary"]["loggedModules"] == 1
    assert result["summary"]["missingModuleLogs"] == 0


def test_04_reports_are_written(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert (tmp_path / "module_log_contract_summary.json").is_file()
    assert (tmp_path / "module_log_contract_matrix.json").is_file()
    assert (tmp_path / "module_log_contract_summary.md").is_file()


def test_05_missing_module_log_fails(tmp_path: Path) -> None:
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=_module_payload(), entries=[])
    assert result["verdict"] == contract.FAIL_VERDICT
    assert contract.FAIL_MISSING_MODULE_LOG in result["failures"]
    assert result["summary"]["missingModuleLogs"] == 1


def test_06_missing_required_field_fails(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    del entries[0]["checks"]
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.FAIL_VERDICT
    assert any(item.startswith(contract.FAIL_MISSING_REQUIRED_FIELD) for item in result["failures"])


def test_07_wrong_zone_fails(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    entries[0]["zone"] = "writer_readback"
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.FAIL_VERDICT
    assert contract.FAIL_INVALID_MODULE_ZONE in result["failures"]


def test_08_security_leak_counter_fails(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    entries[0]["security"]["piiLeak"] = 1
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.FAIL_VERDICT
    assert contract.FAIL_SECURITY_LEAK_IN_LOG in result["failures"]


def test_09_raw_path_pattern_fails(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    entries[0]["summary"] = "C:/Users/example/source"
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.FAIL_VERDICT
    assert contract.FAIL_SECURITY_LEAK_IN_LOG in result["failures"]


def test_10_raw_filename_pattern_fails(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    entries[0]["summary"] = "source.hwpx"
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.FAIL_VERDICT
    assert contract.FAIL_SECURITY_LEAK_IN_LOG in result["failures"]


def test_11_pii_pattern_fails(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    entries[0]["summary"] = "010-1234-5678"
    result = contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    assert result["verdict"] == contract.FAIL_VERDICT
    assert contract.FAIL_SECURITY_LEAK_IN_LOG in result["failures"]


def test_12_reports_have_no_leak_patterns(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    for path in tmp_path.iterdir():
        text = path.read_text(encoding="utf-8")
        assert not contract.ABS_PATH_RE.search(text)
        assert not contract.RAW_FILENAME_RE.search(text)
        assert not contract.PII_RE.search(text)


def test_13_json_reports_valid(tmp_path: Path) -> None:
    payload = _module_payload()
    entries = history.build_history_entries(payload, run_id="run_contract")
    contract.run_module_log_contract_gate(report_dir=tmp_path, module_payload=payload, entries=entries)
    json.loads((tmp_path / "module_log_contract_summary.json").read_text(encoding="utf-8"))
    json.loads((tmp_path / "module_log_contract_matrix.json").read_text(encoding="utf-8"))


def test_14_written_history_passes_contract(tmp_path: Path) -> None:
    payload = _module_payload()
    history.write_history(payload, report_dir=tmp_path / "history", run_id="run_contract", append=False)
    entries = [
        json.loads(line)
        for line in (tmp_path / "history" / "module_audit_history.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = contract.run_module_log_contract_gate(report_dir=tmp_path / "contract", module_payload=payload, entries=entries)
    assert result["verdict"] == contract.PASS_VERDICT
