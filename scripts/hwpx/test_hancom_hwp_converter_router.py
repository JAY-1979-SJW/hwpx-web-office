from argparse import Namespace
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hancom_hwp_converter_router as router
from hancom_hwp_converter_providers import ProviderStatus
from hancom_hwp_converter_router import build_plan, run


HWP_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def write_hwp_signature_fixture(path: Path) -> None:
    path.write_bytes(HWP_OLE_SIGNATURE + b"placeholder")


def args(tmp_path: Path, **overrides: object) -> Namespace:
    values = {
        "input": None,
        "output_dir": str(tmp_path),
        "mode": "preflight",
        "allow_execute": False,
        "report_json": None,
        "promotion_evidence_json": None,
        "promotion_evidence_out": None,
        "manual_fallback": False,
        "provider": "auto",
        "timeout_sec": 90,
        "wait_user_sec": 60,
        "save_strategy": "auto",
        "diag_dir": None,
        "expected_text": [],
        "strict_quality": False,
        "fidelity_policy": "text",
        "pattern": "*.hwp",
        "existing_policy": "fail",
        "fail_fast": False,
        "workers": 1,
        "log_file": None,
        "log_level": "INFO",
        "job_id": None,
    }
    values.update(overrides)
    return Namespace(**values)


def blocked_provider(name: str = "com") -> ProviderStatus:
    return ProviderStatus(
        provider=name,
        available=True,
        verified=False,
        status="BLOCKED",
        blocker="NOT_VERIFIED",
        evidence="test",
        execution_allowed=False,
        next_action="verify first",
    )


def executable_provider(name: str = "com") -> ProviderStatus:
    return ProviderStatus(
        provider=name,
        available=True,
        verified=True,
        status="READY",
        blocker="",
        evidence="test",
        execution_allowed=True,
        next_action="execute one",
    )


def test_build_plan_refuses_when_no_executable_provider(tmp_path: Path) -> None:
    plan = build_plan(args(tmp_path), [blocked_provider()])

    assert plan["status"] == "NO_EXECUTABLE_PROVIDER"
    assert plan["selected_provider"] is None
    assert plan["execution_policy"]["one_file_only"] is True


def test_build_plan_rejects_non_hwp_input_before_execution(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwpx"
    sample.write_text("not a real hwpx", encoding="utf-8")

    plan = build_plan(args(tmp_path, input=str(sample)), [executable_provider()])

    assert plan["status"] == "INPUT_INVALID"
    assert plan["blocker"] == "INPUT_NOT_HWP"
    assert plan["input_validation"]["suffix"] == ".hwpx"


def test_build_plan_selects_verified_provider_for_one_file(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)

    plan = build_plan(args(tmp_path, input=str(sample)), [executable_provider()])

    assert plan["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert plan["selected_provider"]["provider"] == "com"
    assert plan["planned_output"].endswith("sample.hwpx")


def test_build_plan_selects_standalone_provider_by_default(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)

    plan = build_plan(
        args(tmp_path, input=str(sample)),
        [executable_provider("com"), executable_provider("standalone")],
    )

    assert plan["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert plan["selected_provider"]["provider"] == "standalone"


def test_build_plan_keeps_standalone_before_hwpxjs_for_default_one_file(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)

    plan = build_plan(
        args(tmp_path, input=str(sample)),
        [executable_provider("standalone"), executable_provider("hwpxjs")],
    )

    assert plan["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert plan["selected_provider"]["provider"] == "standalone"


def test_build_plan_selects_hwpxjs_when_explicitly_requested(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)

    plan = build_plan(
        args(tmp_path, input=str(sample), provider="hwpxjs"),
        [executable_provider("standalone"), executable_provider("hwpxjs")],
    )

    assert plan["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert plan["selected_provider"]["provider"] == "hwpxjs"


def test_build_plan_keeps_standalone_for_batch_even_if_hwpxjs_exists(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "sample.hwp").write_bytes(HWP_OLE_SIGNATURE + b"placeholder")

    plan = build_plan(
        args(tmp_path, input=str(input_dir)),
        [executable_provider("hwpxjs"), executable_provider("standalone")],
    )

    assert plan["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert plan["selected_provider"]["provider"] == "standalone"
    assert plan["execution_policy"]["batch_allowed"] is True


def test_run_wires_provider_detection_into_json_and_csv_reports(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    report_json = tmp_path / "reports" / "router_report.json"

    monkeypatch.setattr(router, "detect_providers", lambda: [executable_provider("official_converter")])

    result = run(
        args(
            tmp_path,
            input=str(sample),
            report_json=str(report_json),
        )
    )

    report = json.loads(report_json.read_text(encoding="utf-8"))
    provider_csv = Path(result["provider_csv"])

    assert result["report_json"] == str(report_json.resolve())
    assert provider_csv.exists()
    assert report["schema_version"] == 2
    assert report["providers"][0]["provider"] == "official_converter"
    assert report["plan"]["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert report["plan"]["selected_provider"]["provider"] == "official_converter"
    assert "official_converter" in provider_csv.read_text(encoding="utf-8-sig")
    assert report["plan"]["promotion_gate"]["status"] == "NOT_PROVIDED"


def test_convert_mode_remains_refused_without_allow_execute(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [executable_provider("official_converter")])

    result = run(args(tmp_path, input=str(sample), mode="convert", allow_execute=False))

    assert result["plan"]["status"] == "EXECUTION_REFUSED"
    assert result["plan"]["blocker"] == "convert mode requires --allow-execute and a verified provider"


def test_convert_mode_requires_promotable_evidence_even_with_verified_provider(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [executable_provider("official_converter")])

    result = run(args(tmp_path, input=str(sample), mode="convert", allow_execute=True))

    assert result["plan"]["status"] == "EXECUTION_REFUSED_PROMOTION_GATE"
    assert "promotable one-file provider evidence" in result["plan"]["blocker"]


def test_convert_mode_executes_standalone_without_promotion_evidence(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [executable_provider("standalone")])

    called = {}

    def fake_standalone(input_path, output_path, expected_texts=None, strict_quality=False, existing_policy="fail", fidelity_policy="text", embed_original=False, decoded_style_bridge=False):
        called.update(
            {
                "input_path": input_path,
                "output_path": output_path,
                "expected_texts": expected_texts,
                "strict_quality": strict_quality,
                "existing_policy": existing_policy,
                "fidelity_policy": fidelity_policy,
            }
        )
        from zipfile import ZipFile

        with ZipFile(output_path, "w") as zf:
            zf.writestr("mimetype", "application/vnd.hancom.hwpml")
            zf.writestr("Contents/section0.xml", "<root/>")
        return {"status": "PASS", "output": str(output_path)}

    monkeypatch.setattr(router, "convert_hwp_to_hwpx", fake_standalone)

    result = run(
        args(
            tmp_path,
            input=str(sample),
            mode="convert",
            allow_execute=True,
            expected_text=["건축법"],
            strict_quality=True,
        )
    )

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["selected_provider"]["provider"] == "standalone"
    assert result["conversion"]["provider"] == "STANDALONE_TEXT_ONLY"
    assert called["input_path"] == sample.resolve()
    assert called["expected_texts"] == ["건축법"]
    assert called["strict_quality"] is True
    assert called["existing_policy"] == "fail"
    assert called["fidelity_policy"] == "text"


def test_convert_mode_executes_hwpxjs_without_promotion_evidence(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [executable_provider("hwpxjs")])

    called = {}

    def fake_hwpxjs(input_path, output_dir, args_obj):
        called.update({"input_path": input_path, "output_dir": output_dir, "timeout_sec": args_obj.timeout_sec})
        return {
            "input": str(input_path),
            "output": str(output_dir / "sample.hwpx"),
            "provider": "HWPXJS_OPEN_SOURCE",
            "ok": True,
            "error_code": "HWPXJS_OUTPUT_VALID",
        }

    monkeypatch.setattr(router, "execute_hwpxjs_one", fake_hwpxjs)

    result = run(args(tmp_path, input=str(sample), mode="convert", allow_execute=True, timeout_sec=7))

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["selected_provider"]["provider"] == "hwpxjs"
    assert result["conversion"]["provider"] == "HWPXJS_OPEN_SOURCE"
    assert called["input_path"] == sample.resolve()
    assert called["timeout_sec"] == 7


def test_convert_mode_executes_standalone_batch_directory(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "a.hwp").write_bytes(HWP_OLE_SIGNATURE + b"a")
    monkeypatch.setattr(router, "detect_providers", lambda: [executable_provider("standalone")])

    called = {}

    def fake_batch(
        input_path,
        output_dir,
        expected_texts=None,
        strict_quality=False,
        pattern="*.hwp",
        existing_policy="fail",
        fidelity_policy="text",
        fail_fast=False,
        workers=1,
        job_id=None,
    ):
        called.update(
            {
                "input_path": input_path,
                "output_dir": output_dir,
                "expected_texts": expected_texts,
                "strict_quality": strict_quality,
                "pattern": pattern,
                "existing_policy": existing_policy,
                "fidelity_policy": fidelity_policy,
                "fail_fast": fail_fast,
                "workers": workers,
                "job_id": job_id,
            }
        )
        return {
            "status": "PASS",
            "mode": "batch_text_only_rebuild",
            "input_dir": str(input_path),
            "output_dir": str(output_dir),
            "target_count": 1,
            "ok_count": 1,
            "fail_count": 0,
            "results": [{"status": "PASS", "output": str(output_dir / "a.hwpx")}],
        }

    monkeypatch.setattr(router, "convert_batch", fake_batch)

    result = run(
        args(
            tmp_path / "output",
            input=str(input_dir),
            mode="convert",
            allow_execute=True,
            expected_text=["건축법"],
            strict_quality=True,
            pattern="**/*.hwp",
            existing_policy="skip",
            fidelity_policy="strict",
            fail_fast=True,
            workers=3,
            job_id="router-job",
        )
    )

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["execution_policy"]["batch_allowed"] is True
    assert result["plan"]["execution_policy"]["one_file_only"] is False
    assert result["conversion"]["mode"] == "batch_text_only_rebuild"
    assert called["input_path"] == input_dir.resolve()
    assert called["expected_texts"] == ["건축법"]
    assert called["strict_quality"] is True
    assert called["pattern"] == "**/*.hwp"
    assert called["existing_policy"] == "skip"
    assert called["fidelity_policy"] == "strict"
    assert called["fail_fast"] is True
    assert called["workers"] == 3
    assert called["job_id"] == "router-job"


def test_build_plan_includes_promotion_gate_result_for_missing_evidence(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    missing_evidence = tmp_path / "missing.json"

    plan = build_plan(
        args(tmp_path, input=str(sample), promotion_evidence_json=str(missing_evidence)),
        [executable_provider("official_converter")],
    )

    assert plan["status"] == "READY_FOR_ONE_FILE_EXECUTION"
    assert plan["promotion_gate"]["status"] == "FAIL"
    assert "PROMOTION_EVIDENCE_NOT_FOUND" in plan["promotion_gate"]["errors"]


def test_build_plan_can_include_user_present_manual_fallback_without_input(tmp_path: Path) -> None:
    plan = build_plan(args(tmp_path, manual_fallback=True), [blocked_provider("user_present")])

    fallback = plan["manual_fallback"]
    assert fallback["status"] == "INPUT_REQUIRED"
    assert fallback["command"] is None
    assert fallback["promotion_evidence_template"].endswith("user_present_promotion_evidence_template.json")


def test_build_plan_blocks_user_present_manual_fallback_for_non_hwp_input(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwpx"
    sample.write_text("not a real hwp", encoding="utf-8")

    plan = build_plan(args(tmp_path, input=str(sample), manual_fallback=True), [blocked_provider("user_present")])

    fallback = plan["manual_fallback"]
    assert plan["input_validation"]["error"] == "INPUT_NOT_HWP"
    assert fallback["status"] == "INPUT_NOT_HWP"
    assert fallback["command"] is None


def test_build_plan_blocks_user_present_manual_fallback_for_fake_hwp_input(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    sample.write_bytes(b"placeholder")

    plan = build_plan(args(tmp_path, input=str(sample), manual_fallback=True), [blocked_provider("user_present")])

    fallback = plan["manual_fallback"]
    assert plan["input_validation"]["error"] == "INPUT_NOT_HWP_BINARY"
    assert fallback["status"] == "INPUT_NOT_HWP_BINARY"
    assert fallback["command"] is None


def test_build_plan_includes_user_present_manual_command_for_one_file(tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)

    plan = build_plan(args(tmp_path, input=str(sample), manual_fallback=True), [blocked_provider("user_present")])

    fallback = plan["manual_fallback"]
    assert fallback["status"] in {"READY_FOR_USER_PRESENT_MANUAL_RUN", "SCRIPT_NOT_FOUND"}
    assert "-InputPath" in fallback["command"]
    assert str(sample.resolve()) in fallback["command"]
    assert fallback["evidence_builder"].endswith("hancom_user_present_evidence.py")
    assert "--result-json" in fallback["promotion_evidence_command"]
    assert "--execution-approved" in fallback["promotion_evidence_command"]
    assert plan["fallback_provider"]["provider"] == "user_present"


def test_run_writes_user_present_promotion_evidence_template(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [blocked_provider("user_present")])

    result = run(args(tmp_path, input=str(sample), manual_fallback=True))
    template_path = Path(result["plan"]["manual_fallback"]["promotion_evidence_template"])
    template = json.loads(template_path.read_text(encoding="utf-8"))

    assert template_path.exists()
    assert template["provider"] == "user_present"
    assert template["one_file_success"] is False
    assert template["execution_approved"] is False


def test_convert_mode_executes_promoted_com_provider(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    output = tmp_path / "sample.hwpx"
    evidence = tmp_path / "promotion.json"
    write_hwp_signature_fixture(sample)
    output.write_bytes(b"placeholder")
    evidence.write_text(
        json.dumps(
            {
                "provider": "com",
                "input_path": str(sample),
                "output_path": str(output),
                "one_file_success": True,
                "execution_approved": True,
                "verified_at": "2026-05-10T00:00:00Z",
                "output_validation": {"status": "PASS", "zip_ok": True, "xml_ok": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(router, "detect_providers", lambda: [blocked_provider("com")])

    called = {}

    def fake_convert(input_path, output_dir, timeout_sec, mode, diag_dir, save_strategy):
        called.update(
            {
                "input_path": input_path,
                "output_dir": output_dir,
                "timeout_sec": timeout_sec,
                "mode": mode,
                "diag_dir": diag_dir,
                "save_strategy": save_strategy,
            }
        )
        return {"ok": True, "output": str(output_dir / "sample.hwpx"), "error_code": None}

    monkeypatch.setattr(router, "convert_one_with_strategy", fake_convert)

    result = run(
        args(
            tmp_path,
            input=str(sample),
            mode="convert",
            allow_execute=True,
            promotion_evidence_json=str(evidence),
            timeout_sec=12,
            save_strategy="haction",
            diag_dir=str(tmp_path / "diag"),
        )
    )

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["selected_provider"]["status"] == "PROMOTED_BY_ONE_FILE_EVIDENCE"
    assert result["conversion"]["ok"] is True
    assert called["input_path"] == sample.resolve()
    assert called["timeout_sec"] == 12
    assert called["mode"] == "convert"
    assert called["save_strategy"] == "haction"


def test_convert_mode_bootstraps_available_com_provider_and_writes_evidence(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    output = tmp_path / "sample.hwpx"
    evidence_out = tmp_path / "evidence" / "promotion.json"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [blocked_provider("com")])

    def fake_convert(input_path, output_dir, timeout_sec, mode, diag_dir, save_strategy):
        output.write_bytes(b"PK\x03\x04placeholder")
        from zipfile import ZipFile

        with ZipFile(output, "w") as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("Contents/section0.xml", "<root/>")
        return {"ok": True, "output": str(output), "error_code": None}

    monkeypatch.setattr(router, "convert_one_with_strategy", fake_convert)

    result = run(
        args(
            tmp_path,
            input=str(sample),
            mode="convert",
            allow_execute=True,
            provider="com",
            promotion_evidence_out=str(evidence_out),
        )
    )
    evidence = json.loads(evidence_out.read_text(encoding="utf-8"))

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["execution_bootstrap"]["enabled"] is True
    assert result["plan"]["selected_provider"]["status"] == "BOOTSTRAP_EXECUTION_CANDIDATE"
    assert result["plan"]["promotion_evidence_out"] == str(evidence_out.resolve())
    assert evidence["provider"] == "com"
    assert evidence["one_file_success"] is True
    assert evidence["output_validation"]["zip_ok"] is True


def test_convert_mode_can_bootstrap_requested_local_gui_provider(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    output = tmp_path / "sample.hwpx"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(router, "detect_providers", lambda: [blocked_provider("com"), blocked_provider("local_gui")])

    called = {}

    def fake_local_gui(input_path, output_dir, timeout_sec, diag_dir):
        called.update(
            {
                "input_path": input_path,
                "output_dir": output_dir,
                "timeout_sec": timeout_sec,
                "diag_dir": diag_dir,
            }
        )
        from zipfile import ZipFile

        with ZipFile(output, "w") as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("Contents/section0.xml", "<root/>")
        return {"ok": True, "output": str(output), "error_code": None}

    monkeypatch.setattr(router, "execute_local_gui_one", fake_local_gui)

    result = run(
        args(
            tmp_path,
            input=str(sample),
            mode="convert",
            allow_execute=True,
            provider="local_gui",
            timeout_sec=21,
        )
    )

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["selected_provider"]["provider"] == "local_gui"
    assert result["plan"]["execution_bootstrap"]["provider"] == "local_gui"
    assert called["input_path"] == sample.resolve()
    assert called["timeout_sec"] == 21


def test_requested_local_gui_overrides_ready_standalone_for_bootstrap(monkeypatch, tmp_path: Path) -> None:
    sample = tmp_path / "sample.hwp"
    output = tmp_path / "sample.hwpx"
    write_hwp_signature_fixture(sample)
    monkeypatch.setattr(
        router,
        "detect_providers",
        lambda: [executable_provider("standalone"), blocked_provider("local_gui")],
    )

    def fake_local_gui(_input_path, _output_dir, _timeout_sec, _diag_dir):
        from zipfile import ZipFile

        with ZipFile(output, "w") as zf:
            zf.writestr("mimetype", "application/hwp+zip")
            zf.writestr("Contents/section0.xml", "<root/>")
        return {"ok": True, "output": str(output), "error_code": None}

    monkeypatch.setattr(router, "execute_local_gui_one", fake_local_gui)

    result = run(
        args(
            tmp_path,
            input=str(sample),
            mode="convert",
            allow_execute=True,
            provider="local_gui",
        )
    )

    assert result["plan"]["status"] == "CONVERSION_SUCCEEDED"
    assert result["plan"]["selected_provider"]["provider"] == "local_gui"
    assert result["plan"]["execution_bootstrap"]["enabled"] is True
    assert result["conversion"]["output"] == str(output)
