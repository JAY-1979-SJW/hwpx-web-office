"""Provider model and detection for Hancom HWP -> HWPX conversion routes."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
COM_BATCH_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hancom_hwp_to_hwpx_batch.py"
STANDALONE_CONVERTER_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hwp_to_hwpx_standalone.py"
HWPXJS_ADAPTER_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hwpxjs_hwp_to_hwpx.py"
HWPXJS_DEFAULT_REPO = REPO_ROOT / "tmp" / "external_hwpxjs_source"
LOCAL_GUI_SCRIPT = REPO_ROOT / "scripts" / "local-gui" / "hancom_hwp_to_hwpx_local_gui.py"
USER_PRESENT_SCRIPT = REPO_ROOT / "scripts" / "hwp-worker" / "Convert-HwpToHwpx-UserPresent.ps1"
PS32 = (
    Path(os.environ.get("WINDIR", r"C:\Windows"))
    / "SysWOW64"
    / "WindowsPowerShell"
    / "v1.0"
    / "powershell.exe"
)


PROVIDER_ORDER = [
    "standalone",
    "hwpxjs",
    "official_converter",
    "sdk",
    "com",
    "local_gui",
    "user_present",
]


@dataclass
class ProviderStatus:
    provider: str
    available: bool
    verified: bool
    status: str
    blocker: str
    evidence: str
    execution_allowed: bool
    next_action: str
    metadata: dict[str, Any] | None = None


@dataclass
class ConversionRequest:
    input_path: Path
    output_path: Path
    allow_execute: bool = False


@dataclass
class ConversionResult:
    provider: str
    status: str
    output_path: str
    warnings: list[str]
    errors: list[str]
    evidence: dict[str, Any]


class ConverterProvider:
    """Base provider contract.

    Detection is intentionally separate from execution. A provider can be
    available but still refuse execution until a one-file conversion has been
    verified and policy allows it.
    """

    provider_name: str

    def detect(self) -> ProviderStatus:
        raise NotImplementedError

    def execute_one(self, request: ConversionRequest) -> ConversionResult:
        status = self.detect()
        return ConversionResult(
            provider=status.provider,
            status="EXECUTION_REFUSED",
            output_path=str(request.output_path),
            warnings=[],
            errors=[status.blocker or "PROVIDER_NOT_EXECUTION_READY"],
            evidence={
                "available": status.available,
                "verified": status.verified,
                "execution_allowed": status.execution_allowed,
                "status": status.status,
                "next_action": status.next_action,
            },
        )


def status_to_dict(status: ProviderStatus) -> dict[str, Any]:
    return asdict(status)


def result_to_dict(result: ConversionResult) -> dict[str, Any]:
    return asdict(result)


def read_json(path: Path) -> object | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _as_list(value: object | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _row_text(row: Any) -> str:
    return json.dumps(row, ensure_ascii=False) if isinstance(row, dict) else str(row)


def _official_converter_contract(help_rows: list[Any], exe_hits: list[str]) -> dict[str, Any]:
    matching_rows = [
        row
        for row in help_rows
        if isinstance(row, dict)
        and Path(str(row.get("exe") or "")).name.lower() == "hwpconverter.exe"
    ]
    statuses = [str(row.get("status")) for row in matching_rows]
    has_stdout = any(str(row.get("stdout") or "").strip() for row in matching_rows)
    has_stderr = any(str(row.get("stderr") or "").strip() for row in matching_rows)
    if not exe_hits:
        contract = "NO_EXECUTABLE"
        reason = "No HwpConverter.exe candidate found"
    elif matching_rows and all(status == "TIMEOUT" for status in statuses):
        contract = "GUI_OR_BLOCKING_PROCESS"
        reason = "Help probes timed out without stdout/stderr"
    elif (
        matching_rows
        and any(status == "EXITED" for status in statuses)
        and (has_stdout or has_stderr)
    ):
        contract = "CLI_HELP_VISIBLE"
        reason = "Help probe exited and emitted text"
    elif matching_rows:
        contract = "UNKNOWN_HELP_BEHAVIOR"
        reason = "Help probe ran but did not expose a usable command contract"
    else:
        contract = "UNPROBED"
        reason = "No help probe rows found for HwpConverter.exe"
    return {
        "contract": contract,
        "reason": reason,
        "help_probe_count": len(matching_rows),
        "help_statuses": statuses,
        "help_has_stdout": has_stdout,
        "help_has_stderr": has_stderr,
    }


def official_converter_discovery_dirs() -> list[Path]:
    return [
        REPO_ROOT / "tmp" / "hancom_hwpx_converter_post_install",
        REPO_ROOT / "tmp" / "hancom_official_hwpx_converter_discovery",
    ]


class OfficialConverterProvider(ConverterProvider):
    provider_name = "official_converter"

    def _scan_discovery_dir(
        self,
        base: Path,
        shortcut_hits: list[str],
        uninstall_hits: list[str],
        exe_hits: list[str],
        help_rows_all: list[Any],
    ) -> None:
        shortcuts = read_json(base / "shortcut_candidates.json")
        for item in _as_list(shortcuts):
            text = _row_text(item)
            if any(token in text.lower() for token in ("hwpx", "converter")):
                shortcut_hits.append(text)

        for name in ("uninstall_hkcu.json", "uninstall_hklm.json"):
            rows = read_json(base / name)
            for item in _as_list(rows):
                text = _row_text(item)
                if any(token in text.lower() for token in ("hwpx", "converter")):
                    uninstall_hits.append(text)

        exes = read_json(base / "exe_candidates.json")
        for item in _as_list(exes):
            if isinstance(item, dict):
                full = str(item.get("FullName") or item.get("fullName") or "")
                name = Path(full).name.lower()
                if name == "hwpconverter.exe":
                    exe_hits.append(full)

        help_rows = read_json(base / "help_probe.json")
        help_rows_all.extend(_as_list(help_rows))

    def detect(self) -> ProviderStatus:
        shortcut_hits: list[str] = []
        uninstall_hits: list[str] = []
        exe_hits: list[str] = []
        help_rows_all: list[Any] = []

        for base in official_converter_discovery_dirs():
            self._scan_discovery_dir(base, shortcut_hits, uninstall_hits, exe_hits, help_rows_all)

        contract = _official_converter_contract(help_rows_all, exe_hits)
        metadata = {
            "shortcut_count": len(shortcut_hits),
            "uninstall_count": len(uninstall_hits),
            "hwpconverter_candidates": exe_hits,
            "contract": contract,
        }

        if shortcut_hits or uninstall_hits:
            return ProviderStatus(
                provider=self.provider_name,
                available=True,
                verified=False,
                status="FOUND_UNVERIFIED",
                blocker="CLI_OR_GUI_CONTRACT_UNKNOWN",
                evidence=f"shortcuts={len(shortcut_hits)} uninstall={len(uninstall_hits)}",
                execution_allowed=False,
                next_action="Inspect official converter target and help/GUI contract before one-file test",
                metadata=metadata,
            )

        if exe_hits:
            return ProviderStatus(
                provider=self.provider_name,
                available=False,
                verified=False,
                status="INTERNAL_CONVERTER_CANDIDATE_ONLY",
                blocker="OFFICIAL_ADDIN_NOT_INSTALLED",
                evidence=f"HwpConverter candidates={exe_hits}; contract={contract['contract']}",
                execution_allowed=False,
                next_action="Install official HWPX Converter Add-in, then re-run post-install discovery",
                metadata=metadata,
            )

        return ProviderStatus(
            provider=self.provider_name,
            available=False,
            verified=False,
            status="NOT_INSTALLED",
            blocker="OFFICIAL_ADDIN_NOT_INSTALLED",
            evidence="No HWPX converter shortcut/uninstall/verified executable found",
            execution_allowed=False,
            next_action="Install official HWPX Converter Add-in",
            metadata=metadata,
        )


class StandaloneProvider(ConverterProvider):
    provider_name = "standalone"

    def detect(self) -> ProviderStatus:
        exists = STANDALONE_CONVERTER_SCRIPT.exists()
        return ProviderStatus(
            provider=self.provider_name,
            available=exists,
            verified=exists,
            status="READY_TEXT_ONLY" if exists else "UNAVAILABLE",
            blocker="" if exists else "STANDALONE_CONVERTER_SCRIPT_NOT_FOUND",
            evidence=f"standalone_converter_script={exists}",
            execution_allowed=exists,
            next_action=(
                "Use independent text-only HWPX rebuild without Hancom Office"
                if exists
                else "Create scripts/hwpx/hwp_to_hwpx_standalone.py"
            ),
            metadata={
                "script": str(STANDALONE_CONVERTER_SCRIPT),
                "requires_hancom": False,
                "uses_com": False,
                "uses_gui": False,
                "limitations": [
                    "Text-first HWPX reconstruction",
                    "Original binary formatting/layout is not preserved",
                ],
            },
        )


class HwpxJsProvider(ConverterProvider):
    provider_name = "hwpxjs"

    def detect(self) -> ProviderStatus:
        adapter_exists = HWPXJS_ADAPTER_SCRIPT.exists()
        env_cli = os.environ.get("HWPXJS_CLI", "").strip()
        env_repo = (
            Path(os.environ.get("HWPXJS_REPO", "")).expanduser()
            if os.environ.get("HWPXJS_REPO")
            else None
        )
        repo = (env_repo or HWPXJS_DEFAULT_REPO).resolve()
        dist_cli = repo / "dist" / "cli.js"
        package_json = repo / "package.json"
        command_hits = [name for name in ("hwpxjs", "hwpx") if shutil.which(name)]
        metadata = {
            "adapter_script": str(HWPXJS_ADAPTER_SCRIPT),
            "adapter_exists": adapter_exists,
            "env_cli": env_cli,
            "repo": str(repo),
            "dist_cli": str(dist_cli),
            "dist_cli_exists": dist_cli.exists(),
            "source_exists": package_json.exists(),
            "command_hits": command_hits,
            "requires_hancom": False,
            "uses_com": False,
            "uses_gui": False,
            "upstream": "https://github.com/ssabro/hwpxjs",
            "limitations": [
                "External open-source CLI must already be installed or built",
                "Adapter does not download npm packages during conversion",
            ],
        }
        if not adapter_exists:
            return ProviderStatus(
                provider=self.provider_name,
                available=False,
                verified=False,
                status="UNAVAILABLE",
                blocker="HWPXJS_ADAPTER_SCRIPT_NOT_FOUND",
                evidence=f"adapter_script={HWPXJS_ADAPTER_SCRIPT}",
                execution_allowed=False,
                next_action="Create scripts/hwpx/hwpxjs_hwp_to_hwpx.py",
                metadata=metadata,
            )
        if env_cli and Path(env_cli).expanduser().exists():
            return ProviderStatus(
                provider=self.provider_name,
                available=True,
                verified=True,
                status="READY_EXTERNAL_CLI",
                blocker="",
                evidence=f"HWPXJS_CLI={Path(env_cli).expanduser().resolve()}",
                execution_allowed=True,
                next_action="Use --provider hwpxjs --mode convert --allow-execute for one-file conversion",
                metadata=metadata,
            )
        if dist_cli.exists() or command_hits:
            return ProviderStatus(
                provider=self.provider_name,
                available=True,
                verified=True,
                status="READY_OPEN_SOURCE_CLI",
                blocker="",
                evidence=f"dist_cli={dist_cli.exists()} command_hits={command_hits}",
                execution_allowed=True,
                next_action="Use --provider hwpxjs --mode convert --allow-execute for one-file conversion",
                metadata=metadata,
            )
        if package_json.exists():
            return ProviderStatus(
                provider=self.provider_name,
                available=False,
                verified=False,
                status="SOURCE_FOUND_NEEDS_BUILD",
                blocker="HWPXJS_CLI_NOT_BUILT",
                evidence=f"source={repo}; missing dist/cli.js and no hwpxjs command",
                execution_allowed=False,
                next_action="Run npm install && npm run build in the hwpxjs checkout, or set HWPXJS_CLI",
                metadata=metadata,
            )
        return ProviderStatus(
            provider=self.provider_name,
            available=False,
            verified=False,
            status="NOT_INSTALLED",
            blocker="HWPXJS_NOT_FOUND",
            evidence="No HWPXJS_CLI, built local dist/cli.js, or hwpxjs/hwpx command found",
            execution_allowed=False,
            next_action="Install @ssabrojs/hwpxjs or clone/build ssabro/hwpxjs",
            metadata=metadata,
        )


class SdkProvider(ConverterProvider):
    provider_name = "sdk"

    def detect(self) -> ProviderStatus:
        sdk_catalog = read_json(
            REPO_ROOT / "tmp" / "hancom_full_function_explorer" / "sdk_capability_catalog.json"
        )
        hwp_sdk = None
        if isinstance(sdk_catalog, list):
            hwp_sdk = next((row for row in sdk_catalog if row.get("tool_name") == "Hwp SDK"), None)
        return ProviderStatus(
            provider=self.provider_name,
            available=False,
            verified=False,
            status="LICENSE_REQUIRED",
            blocker="SDK_NOT_INSTALLED_OR_LICENSE_NOT_CONFIRMED",
            evidence=json.dumps(hwp_sdk, ensure_ascii=False)
            if hwp_sdk
            else "No installed SDK evidence",
            execution_allowed=False,
            next_action="Confirm Hwp SDK license, install path, and sample conversion API",
            metadata={"sdk_catalog_entry": hwp_sdk},
        )


class ComProvider(ConverterProvider):
    provider_name = "com"

    def detect(self) -> ProviderStatus:
        exists = COM_BATCH_SCRIPT.exists() and PS32.exists()
        return ProviderStatus(
            provider=self.provider_name,
            available=exists,
            verified=False,
            status="BLOCKED_SAVEAS_TIMEOUT" if exists else "UNAVAILABLE",
            blocker="COM_SAVEAS_HWPX_TIMEOUT",
            evidence=f"batch_script={COM_BATCH_SCRIPT.exists()} ps32={PS32.exists()} RegisterModule previously true; Open previously PASS",
            execution_allowed=False,
            next_action="Keep COM route for Open/preflight only until SaveAs timeout is resolved",
            metadata={"batch_script": str(COM_BATCH_SCRIPT), "ps32": str(PS32)},
        )


class LocalGuiProvider(ConverterProvider):
    provider_name = "local_gui"

    def detect(self) -> ProviderStatus:
        exists = LOCAL_GUI_SCRIPT.exists()
        return ProviderStatus(
            provider=self.provider_name,
            available=exists,
            verified=False,
            status="BLOCKED_SAVE_DIALOG_NOT_FOUND" if exists else "UNAVAILABLE",
            blocker="SAVE_DIALOG_NOT_FOUND",
            evidence=f"local_gui_script={exists}; GUI Open PASS and path quoting fixed in prior probes",
            execution_allowed=False,
            next_action="Resolve Save dialog detection before enabling HWPX save",
            metadata={"local_gui_script": str(LOCAL_GUI_SCRIPT)},
        )


class UserPresentProvider(ConverterProvider):
    provider_name = "user_present"

    def detect(self) -> ProviderStatus:
        exists = USER_PRESENT_SCRIPT.exists()
        return ProviderStatus(
            provider=self.provider_name,
            available=exists,
            verified=False,
            status="AVAILABLE_MANUAL_FALLBACK" if exists else "UNAVAILABLE",
            blocker="REQUIRES_USER_PRESENT_SAVEAS",
            evidence=f"user_present_script={exists}",
            execution_allowed=False,
            next_action="Use only as manual fallback after policy approval",
            metadata={"user_present_script": str(USER_PRESENT_SCRIPT)},
        )


def build_providers() -> list[ConverterProvider]:
    return [
        StandaloneProvider(),
        HwpxJsProvider(),
        OfficialConverterProvider(),
        SdkProvider(),
        ComProvider(),
        LocalGuiProvider(),
        UserPresentProvider(),
    ]


def detect_providers(providers: list[ConverterProvider] | None = None) -> list[ProviderStatus]:
    return [provider.detect() for provider in (providers or build_providers())]


def choose_provider(statuses: list[ProviderStatus]) -> ProviderStatus | None:
    by_name = {status.provider: status for status in statuses}
    for name in PROVIDER_ORDER:
        candidate = by_name.get(name)
        if candidate and candidate.available and candidate.verified and candidate.execution_allowed:
            return candidate
    return None
