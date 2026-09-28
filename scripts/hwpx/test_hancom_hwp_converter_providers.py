import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hancom_hwp_converter_providers as providers
from hancom_hwp_converter_providers import (
    ComProvider,
    ConversionRequest,
    HwpxJsProvider,
    OfficialConverterProvider,
    ProviderStatus,
    StandaloneProvider,
    _official_converter_contract,
    choose_provider,
    detect_providers,
    read_json,
    result_to_dict,
    status_to_dict,
)


def test_read_json_returns_none_for_missing_or_invalid_json(tmp_path: Path) -> None:
    assert read_json(tmp_path / "missing.json") is None

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")

    assert read_json(invalid) is None


def test_detect_providers_uses_injected_provider_instances() -> None:
    class FakeProvider:
        def detect(self) -> ProviderStatus:
            return ProviderStatus(
                provider="fake",
                available=True,
                verified=False,
                status="FOUND",
                blocker="NOT_VERIFIED",
                evidence="unit",
                execution_allowed=False,
                next_action="verify",
            )

    statuses = detect_providers([FakeProvider()])

    assert len(statuses) == 1
    assert statuses[0].provider == "fake"
    assert statuses[0].status == "FOUND"


def test_choose_provider_respects_router_priority_order() -> None:
    standalone = ProviderStatus(
        provider="standalone",
        available=True,
        verified=True,
        status="READY",
        blocker="",
        evidence="unit",
        execution_allowed=True,
        next_action="execute",
    )
    local_gui = ProviderStatus(
        provider="local_gui",
        available=True,
        verified=True,
        status="READY",
        blocker="",
        evidence="unit",
        execution_allowed=True,
        next_action="execute",
    )
    official = ProviderStatus(
        provider="official_converter",
        available=True,
        verified=True,
        status="READY",
        blocker="",
        evidence="unit",
        execution_allowed=True,
        next_action="execute",
    )

    assert choose_provider([local_gui, official]) == official
    assert choose_provider([local_gui, official, standalone]) == standalone


def test_standalone_provider_detects_ready_when_script_exists(monkeypatch, tmp_path: Path) -> None:
    script = tmp_path / "hwp_to_hwpx_standalone.py"
    script.write_text("# unit\n", encoding="utf-8")
    monkeypatch.setattr(providers, "STANDALONE_CONVERTER_SCRIPT", script)

    status = StandaloneProvider().detect()

    assert status.provider == "standalone"
    assert status.available is True
    assert status.verified is True
    assert status.execution_allowed is True
    assert status.status == "READY_TEXT_ONLY"
    assert status.metadata["requires_hancom"] is False


def test_hwpxjs_provider_detects_source_checkout_needing_build(monkeypatch, tmp_path: Path) -> None:
    adapter = tmp_path / "hwpxjs_hwp_to_hwpx.py"
    adapter.write_text("# unit\n", encoding="utf-8")
    repo = tmp_path / "hwpxjs"
    repo.mkdir()
    (repo / "package.json").write_text('{"name":"@ssabrojs/hwpxjs"}', encoding="utf-8")
    monkeypatch.setattr(providers, "HWPXJS_ADAPTER_SCRIPT", adapter)
    monkeypatch.setattr(providers, "HWPXJS_DEFAULT_REPO", repo)
    monkeypatch.setattr(providers.shutil, "which", lambda _name: None)
    monkeypatch.delenv("HWPXJS_CLI", raising=False)
    monkeypatch.delenv("HWPXJS_REPO", raising=False)

    status = HwpxJsProvider().detect()

    assert status.provider == "hwpxjs"
    assert status.available is False
    assert status.status == "SOURCE_FOUND_NEEDS_BUILD"
    assert status.blocker == "HWPXJS_CLI_NOT_BUILT"
    assert status.metadata["source_exists"] is True


def test_hwpxjs_provider_detects_built_local_cli(monkeypatch, tmp_path: Path) -> None:
    adapter = tmp_path / "hwpxjs_hwp_to_hwpx.py"
    adapter.write_text("# unit\n", encoding="utf-8")
    repo = tmp_path / "hwpxjs"
    dist = repo / "dist"
    dist.mkdir(parents=True)
    (repo / "package.json").write_text('{"name":"@ssabrojs/hwpxjs"}', encoding="utf-8")
    (dist / "cli.js").write_text("#!/usr/bin/env node\n", encoding="utf-8")
    monkeypatch.setattr(providers, "HWPXJS_ADAPTER_SCRIPT", adapter)
    monkeypatch.setattr(providers, "HWPXJS_DEFAULT_REPO", repo)
    monkeypatch.setattr(providers.shutil, "which", lambda _name: None)
    monkeypatch.delenv("HWPXJS_CLI", raising=False)
    monkeypatch.delenv("HWPXJS_REPO", raising=False)

    status = HwpxJsProvider().detect()

    assert status.available is True
    assert status.verified is True
    assert status.execution_allowed is True
    assert status.status == "READY_OPEN_SOURCE_CLI"
    assert status.metadata["dist_cli_exists"] is True


def test_base_execute_one_refuses_until_provider_is_verified(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(providers, "COM_BATCH_SCRIPT", tmp_path / "missing.py")
    monkeypatch.setattr(providers, "PS32", tmp_path / "missing-powershell.exe")

    request = ConversionRequest(
        input_path=tmp_path / "sample.hwp",
        output_path=tmp_path / "sample.hwpx",
        allow_execute=True,
    )

    result = ComProvider().execute_one(request)

    assert result.status == "EXECUTION_REFUSED"
    assert result.provider == "com"
    assert result.errors == ["COM_SAVEAS_HWPX_TIMEOUT"]
    assert result_to_dict(result)["evidence"]["verified"] is False


def test_com_provider_detects_unavailable_when_required_paths_are_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(providers, "COM_BATCH_SCRIPT", tmp_path / "missing.py")
    monkeypatch.setattr(providers, "PS32", tmp_path / "missing-powershell.exe")

    status = ComProvider().detect()

    assert status.provider == "com"
    assert status.available is False
    assert status.verified is False
    assert status.status == "UNAVAILABLE"
    assert status.execution_allowed is False


def test_official_converter_detects_unverified_install_evidence(monkeypatch, tmp_path: Path) -> None:
    discovery = tmp_path / "discovery"
    discovery.mkdir()
    monkeypatch.setattr(providers, "official_converter_discovery_dirs", lambda: [discovery])

    status = OfficialConverterProvider().detect()

    assert status.provider == "official_converter"
    assert status.available is False
    assert status.status == "NOT_INSTALLED"

    (discovery / "shortcut_candidates.json").write_text(
        '[{"Name": "HWPX Converter", "Target": "C:/Hancom/HwpConverter.exe"}]',
        encoding="utf-8",
    )

    status = OfficialConverterProvider().detect()

    assert status.available is True
    assert status.verified is False
    assert status.status == "FOUND_UNVERIFIED"
    assert status_to_dict(status)["blocker"] == "CLI_OR_GUI_CONTRACT_UNKNOWN"
    assert status.metadata["shortcut_count"] == 1
    assert status.metadata["contract"]["contract"] == "NO_EXECUTABLE"


def test_official_converter_contract_classifies_blocking_help_probe() -> None:
    contract = _official_converter_contract(
        [
            {
                "exe": "C:/Hancom/HwpConverter.exe",
                "args": ["/?"],
                "status": "TIMEOUT",
                "stdout": "",
                "stderr": "",
            }
        ],
        ["C:/Hancom/HwpConverter.exe"],
    )

    assert contract["contract"] == "GUI_OR_BLOCKING_PROCESS"
    assert contract["help_probe_count"] == 1
    assert contract["help_statuses"] == ["TIMEOUT"]


def test_official_converter_contract_detects_visible_cli_help() -> None:
    contract = _official_converter_contract(
        [
            {
                "exe": "C:/Hancom/HwpConverter.exe",
                "args": ["--help"],
                "status": "EXITED",
                "stdout": "usage: converter input output",
                "stderr": "",
            }
        ],
        ["C:/Hancom/HwpConverter.exe"],
    )

    assert contract["contract"] == "CLI_HELP_VISIBLE"
    assert contract["help_has_stdout"] is True
