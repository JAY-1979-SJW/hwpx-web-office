import json
import subprocess
import sys


def test_hwpx_upload_handler_split_readiness_audit_runs(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    proc = subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["audit"] == "hwpx_upload_handler_split_readiness"
    assert data["phase"] == "P9C"
    assert data["status"] in {"PASS", "WARN", "FAIL"}
    assert data["handler"]["path"].endswith("HwpxUploadHandler.java")
    assert data["handler"]["commit_body_in_p8d"] is False
    assert data["handler"]["commit_body_allowed_in_p8f"] in {True, False}
    assert data["baseline"]["decision"] in {"BASELINE_SAFE", "BASELINE_WARN", "BASELINE_UNSAFE"}
    assert "risk_counts" in data
    assert data["policy"]["no_handler_body_commit"] is True
    assert all(data["gate_presence"].values())
    assert data["pattern_counts"]["file_type_gate_ref"] >= 1
    assert data["pattern_counts"]["upload_security_gate_ref"] >= 1
    assert data["split_plan"]["recommended_next_hunks"]
    assert "actual_value" not in proc.stdout.lower()


def test_hwpx_upload_handler_gate_candidates_are_reported(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    hunk_names = {item["name"] for item in data["split_plan"]["recommended_next_hunks"]}
    assert "file_type_upload_gate" in hunk_names
    assert "hwp_conversion_execution_gate" in hunk_names
    assert "download_output_artifact_gate" in hunk_names
    assert data["pattern_counts"]["convert_api"] >= 1
    assert data["pattern_counts"]["download"] >= 1


def test_hwpx_upload_handler_baseline_has_no_fail_level_runtime_risks(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["baseline"]["decision"] in {"BASELINE_SAFE", "BASELINE_WARN"}
    assert data["contract_checks"]["handler_endpoint_contract_unchanged"] is True
    assert data["contract_checks"]["api_error_key_preserved"] is True
    assert data["risk_counts"]["secret_literal"] == 0
    assert data["risk_counts"]["direct_process_execution"] == 0
    assert data["risk_counts"]["external_browser_execution"] == 0
    assert data["risk_counts"]["db_write"] == 0


def test_hwpx_upload_handler_filetype_upload_gates_are_connected(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["pattern_counts"]["file_type_gate_ref"] >= 1
    assert data["pattern_counts"]["upload_security_gate_ref"] >= 1
    assert data["risk_counts"]["direct_process_execution"] == 0


def test_hwpx_upload_handler_execution_location_gate_p8h_connected(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    p8h = data["p8h_gate_connection"]
    assert p8h["execution_location_gate_connected"] is True
    assert p8h["local_worker_required_present"] is True
    assert p8h["hwp_conversion_flow_has_gate"] is True
    assert p8h["no_direct_server_execution"] is True
    assert p8h["no_external_browser"] is True
    assert data["pattern_counts"]["execution_location_gate_ref"] >= 1


def test_hwpx_upload_handler_output_artifact_gate_p8i_connected(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    p8i = data["p8i_gate_connection"]
    assert p8i["output_artifact_gate_connected"] is True
    assert p8i["raw_path_guard_present"] is True
    assert p8i["sanitize_download_name_present"] is True
    assert data["pattern_counts"]["output_artifact_gate_ref"] >= 1
    no_unguarded = not any(
        f["rule"] == "raw_path_candidate_unguarded"
        for f in data["findings"]
    )
    assert no_unguarded, "raw_path_candidate_unguarded should not fire when OutputArtifactGate is connected"


def test_hwpx_upload_handler_p9a_view_split_completed(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    p9a = data["p9a_split"]
    assert p9a["view_file_exists"] is True
    assert p9a["handler_slim"] is True
    assert p9a["view_has_gate_refs"] is True  # checked against combined helper text
    assert p9a["handler_lines_after_split"] < 100
    # gate refs must still be visible (via combined text)
    assert data["pattern_counts"]["file_type_gate_ref"] >= 1
    assert data["pattern_counts"]["upload_security_gate_ref"] >= 1
    assert data["pattern_counts"]["execution_location_gate_ref"] >= 1
    assert data["pattern_counts"]["output_artifact_gate_ref"] >= 1


def test_hwpx_upload_handler_p9b_view_helpers_split_completed(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    p9b = data["p9b_split"]
    assert p9b["gate_policy_exists"] is True
    assert p9b["styles_exists"] is True
    assert p9b["scripts_exists"] is True
    assert p9b["view_slim"] is True
    assert p9b["gate_policy_has_all_gate_refs"] is True


def test_hwpx_upload_parse_usecase_p9c_skeleton_exists(tmp_path):
    output = tmp_path / "hwpx_upload_handler_split_readiness.json"
    subprocess.run(
        [sys.executable, "scripts/audit_hwpx_upload_handler_split_readiness.py", "--json", str(output)],
        text=True,
        capture_output=True,
        check=True,
    )
    data = json.loads(output.read_text(encoding="utf-8"))
    p9c = data["p9c_usecase"]
    assert p9c["usecase_exists"] is True
    assert p9c["result_exists"] is True
    assert p9c["no_http_import"] is True, "usecase must not import from http package"
    assert p9c["uses_file_type_gate"] is True
    assert p9c["uses_upload_security_gate"] is True
    # handler_wired_p9d_deferred is True in P9C, False after P9D wiring
    assert p9c["handler_wired_p9d_deferred"] in {True, False}, "handler_wired field must be present"
