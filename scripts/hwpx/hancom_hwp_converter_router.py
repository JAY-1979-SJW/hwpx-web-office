#!/usr/bin/env python3
"""Hancom HWP converter router.

This tool does not invent a converter. It classifies the local machine's
available Hancom conversion routes and returns a one-file-safe execution plan.
Actual HWP conversion remains blocked unless a verified provider is available
and execution is explicitly requested.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from hancom_hwp_converter_providers import (
    PROVIDER_ORDER,
    ProviderStatus,
    choose_provider,
    detect_providers,
    status_to_dict,
)
from hancom_hwp_to_hwpx_batch import (
    HWP_CONVERSION_PROVIDER,
    HWP_USER_PRESENT_PROVIDER,
    convert_one_with_strategy,
    convert_user_present_one,
)
from hancom_provider_promotion_gate import read_promotion_evidence, validate_promotion_evidence
from hwp_to_hwpx_standalone import (
    configure_logging,
    convert_batch,
    convert_hwp_to_hwpx,
    default_log_path,
    log_result,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
TMP_DEFAULT = REPO_ROOT / "tmp" / "hancom_hwp_converter_router"
USER_PRESENT_SCRIPT = REPO_ROOT / "scripts" / "hwp-worker" / "Convert-HwpToHwpx-UserPresent.ps1"
USER_PRESENT_EVIDENCE_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hancom_user_present_evidence.py"
LOCAL_GUI_SCRIPT = REPO_ROOT / "scripts" / "local-gui" / "hancom_hwp_to_hwpx_local_gui.py"
HWPXJS_ADAPTER_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hwpxjs_hwp_to_hwpx.py"
HWP_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


PROVIDER_TO_EXECUTOR = {
    "hwpxjs": "HWPXJS_OPEN_SOURCE",
    "standalone": "STANDALONE_TEXT_ONLY",
    "com": HWP_CONVERSION_PROVIDER,
    "local_gui": "HANCOM_LOCAL_GUI",
    "user_present": HWP_USER_PRESENT_PROVIDER,
}
EXECUTABLE_BOOTSTRAP_PROVIDERS = ["standalone", "hwpxjs", "com", "local_gui", "user_present"]
PROMOTION_EVIDENCE_REQUIRED_PROVIDERS = {
    "official_converter",
    "sdk",
    "com",
    "local_gui",
    "user_present",
}


def is_hwpx_zip(path: Path) -> bool:
    try:
        with ZipFile(path) as zf:
            names = zf.namelist()
        return bool(names) and (
            any(name.lower().endswith(".xml") for name in names) or "mimetype" in names
        )
    except (BadZipFile, OSError):
        return False


def has_hwp_binary_signature(path: Path) -> bool:
    try:
        return path.read_bytes()[: len(HWP_OLE_SIGNATURE)] == HWP_OLE_SIGNATURE
    except OSError:
        return False


def safe_path(path: str | None) -> str | None:
    if not path:
        return None
    return str(Path(path).expanduser().resolve())


def _provider_by_name(providers: list[object], name: str) -> object | None:
    for provider in providers:
        if getattr(provider, "provider", None) == name:
            return provider
    return None


def promote_providers_with_evidence(
    providers: list[ProviderStatus],
    promotion_gate: dict[str, object],
) -> list[ProviderStatus]:
    """Mark one detected provider executable after explicit one-file evidence."""
    if promotion_gate.get("promotable") is not True:
        return providers
    provider_name = str(promotion_gate.get("provider") or "")
    promoted: list[ProviderStatus] = []
    for provider in providers:
        if provider.provider != provider_name:
            promoted.append(provider)
            continue
        promoted.append(
            replace(
                provider,
                available=True,
                verified=True,
                status="PROMOTED_BY_ONE_FILE_EVIDENCE",
                blocker="",
                evidence=f"{provider.evidence}; promotion_evidence={promotion_gate.get('path')}",
                execution_allowed=True,
                next_action="Ready for explicit one-file conversion with --allow-execute",
            )
        )
    return promoted


def _provider_status_dict_for_plan(
    provider: ProviderStatus, status: str, blocker: str
) -> dict[str, object]:
    planned = replace(provider, status=status, blocker=blocker)
    return status_to_dict(planned)


def choose_bootstrap_provider(
    providers: list[ProviderStatus], requested_provider: str
) -> ProviderStatus | None:
    by_name = {provider.provider: provider for provider in providers}
    candidates = (
        [requested_provider] if requested_provider != "auto" else EXECUTABLE_BOOTSTRAP_PROVIDERS
    )
    for name in candidates:
        provider = by_name.get(name)
        if provider and provider.available and name in PROVIDER_TO_EXECUTOR:
            return provider
    return None


def provider_requires_promotion_evidence(plan: dict[str, object]) -> bool:
    selected = plan.get("selected_provider")
    if not isinstance(selected, dict):
        return True
    return str(selected.get("provider") or "") in PROMOTION_EVIDENCE_REQUIRED_PROVIDERS


def build_user_present_manual_plan(
    input_path: Path | None, output_path: Path, output_dir: Path
) -> dict[str, object]:
    result_json = output_dir / "user_present_result.json"
    evidence_json = output_dir / "user_present_promotion_evidence_template.json"
    if not input_path:
        return {
            "available": USER_PRESENT_SCRIPT.exists(),
            "script": str(USER_PRESENT_SCRIPT),
            "status": "INPUT_REQUIRED",
            "reason": "Manual fallback requires --input",
            "command": None,
            "result_json": str(result_json),
            "promotion_evidence_template": str(evidence_json),
        }
    if not input_path.exists():
        return {
            "available": USER_PRESENT_SCRIPT.exists(),
            "script": str(USER_PRESENT_SCRIPT),
            "status": "INPUT_NOT_FOUND",
            "reason": "Manual fallback requires an existing .hwp input",
            "command": None,
            "result_json": str(result_json),
            "promotion_evidence_template": str(evidence_json),
        }
    if input_path.suffix.lower() != ".hwp":
        return {
            "available": USER_PRESENT_SCRIPT.exists(),
            "script": str(USER_PRESENT_SCRIPT),
            "status": "INPUT_NOT_HWP",
            "reason": "Manual fallback only supports .hwp input",
            "command": None,
            "result_json": str(result_json),
            "promotion_evidence_template": str(evidence_json),
        }
    if not has_hwp_binary_signature(input_path):
        return {
            "available": USER_PRESENT_SCRIPT.exists(),
            "script": str(USER_PRESENT_SCRIPT),
            "status": "INPUT_NOT_HWP_BINARY",
            "reason": "Manual fallback requires a real binary .hwp file",
            "command": None,
            "result_json": str(result_json),
            "promotion_evidence_template": str(evidence_json),
        }
    command = (
        "powershell -ExecutionPolicy Bypass -File "
        f'"{USER_PRESENT_SCRIPT}" '
        f'-InputPath "{input_path}" '
        f'-OutputPath "{output_path}" '
        f'-ResultPath "{result_json}"'
    )
    evidence_command = (
        "python "
        f'"{USER_PRESENT_EVIDENCE_SCRIPT}" '
        f'--result-json "{result_json}" '
        f'--evidence-json "{evidence_json}" '
        "--execution-approved"
    )
    return {
        "available": USER_PRESENT_SCRIPT.exists(),
        "script": str(USER_PRESENT_SCRIPT),
        "evidence_builder": str(USER_PRESENT_EVIDENCE_SCRIPT),
        "status": "READY_FOR_USER_PRESENT_MANUAL_RUN"
        if USER_PRESENT_SCRIPT.exists()
        else "SCRIPT_NOT_FOUND",
        "reason": "Requires a visible Hancom window and user confirmation; not eligible for unattended execution",
        "command": command,
        "result_json": str(result_json),
        "promotion_evidence_template": str(evidence_json),
        "promotion_evidence_command": evidence_command,
    }


def build_promotion_evidence_template(
    provider: str, input_path: Path | None, output_path: Path
) -> dict[str, object]:
    return {
        "provider": provider,
        "input_path": str(input_path) if input_path else "",
        "output_path": str(output_path),
        "one_file_success": False,
        "execution_approved": False,
        "verified_at": "",
        "output_validation": {
            "status": "FAIL",
            "zip_ok": False,
            "xml_ok": False,
            "source": "Fill after one-file conversion succeeds",
        },
        "notes": "Set one_file_success and execution_approved to true only after a real one-file HWP to HWPX conversion succeeds and output validation passes.",
    }


def _provider_meets_execution_bar(provider: object | None) -> bool:
    return bool(
        provider
        and getattr(provider, "available", False)
        and getattr(provider, "verified", False)
        and getattr(provider, "execution_allowed", False)
    )


def _select_provider_for_request(
    requested_provider: str, input_is_batch_dir: bool, promoted_providers: list[object]
) -> object | None:
    if requested_provider == "auto" and input_is_batch_dir:
        standalone = _provider_by_name(promoted_providers, "standalone")
        return (
            standalone
            if _provider_meets_execution_bar(standalone)
            else choose_provider(promoted_providers)
        )
    if requested_provider == "auto":
        return choose_provider(promoted_providers)
    requested_selected = _provider_by_name(promoted_providers, requested_provider)
    return requested_selected if _provider_meets_execution_bar(requested_selected) else None


def _resolve_bootstrap_provider(
    selected: object | None,
    providers: list[object],
    requested_provider: str,
    args: argparse.Namespace,
) -> tuple[object | None, str | None]:
    if not (
        selected is None
        and getattr(args, "mode", "preflight") == "convert"
        and getattr(args, "allow_execute", False)
    ):
        return None, None
    bootstrap_provider = choose_bootstrap_provider(providers, requested_provider)
    reason = (
        "Explicit one-file bootstrap execution; provider is available but not promoted by evidence yet"
        if bootstrap_provider
        else None
    )
    return bootstrap_provider, reason


def _validate_plan_input_path(
    input_path: Path | None, effective_provider: object | None
) -> str | None:
    if not input_path:
        return None
    if not input_path.exists():
        return "INPUT_NOT_FOUND"
    if input_path.is_dir() and not (
        effective_provider and effective_provider.provider == "standalone"
    ):
        return "INPUT_DIRECTORY_REQUIRES_STANDALONE_PROVIDER"
    if not input_path.is_dir() and input_path.suffix.lower() != ".hwp":
        return "INPUT_NOT_HWP"
    if not input_path.is_dir() and not has_hwp_binary_signature(input_path):
        return "INPUT_NOT_HWP_BINARY"
    return None


def _determine_plan_status(
    selected: object | None, bootstrap_provider: object | None, input_error: str | None
) -> tuple[str, str]:
    if selected is None and bootstrap_provider is None:
        return "NO_EXECUTABLE_PROVIDER", "No provider is both verified and execution_allowed"
    if input_error:
        return "INPUT_INVALID", input_error
    if bootstrap_provider is not None:
        return "READY_FOR_BOOTSTRAP_ONE_FILE_EXECUTION", ""
    return "READY_FOR_ONE_FILE_EXECUTION", ""


def build_plan(args: argparse.Namespace, providers: list[object]) -> dict[str, object]:
    input_path = Path(args.input).expanduser().resolve() if args.input else None
    output_dir = Path(args.output_dir).expanduser().resolve()
    input_is_batch_dir = bool(input_path and input_path.is_dir())
    output_name = (
        input_path.with_suffix(".hwpx").name
        if input_path and not input_is_batch_dir
        else "output.hwpx"
    )
    output_path = output_dir if input_is_batch_dir else output_dir / output_name
    raw_promotion_evidence = read_promotion_evidence(getattr(args, "promotion_evidence_json", None))
    promotion_gate_for_selection = validate_promotion_evidence(raw_promotion_evidence)
    promoted_providers = promote_providers_with_evidence(providers, promotion_gate_for_selection)
    requested_provider = str(getattr(args, "provider", "auto") or "auto")
    selected = _select_provider_for_request(
        requested_provider, input_is_batch_dir, promoted_providers
    )
    bootstrap_provider, bootstrap_reason = _resolve_bootstrap_provider(
        selected, providers, requested_provider, args
    )
    user_present_status = _provider_by_name(providers, "user_present")
    selected_provider_name = selected.provider if selected else None
    promotion_gate = validate_promotion_evidence(raw_promotion_evidence, selected_provider_name)
    effective_provider = selected or bootstrap_provider
    input_error = _validate_plan_input_path(input_path, effective_provider)

    status, blocker = _determine_plan_status(selected, bootstrap_provider, input_error)

    manual_fallback = None
    if getattr(args, "manual_fallback", False):
        manual_fallback = build_user_present_manual_plan(input_path, output_path, output_dir)

    return {
        "mode": args.mode,
        "input": str(input_path) if input_path else None,
        "output_dir": str(output_dir),
        "planned_output": str(output_path),
        "input_validation": {
            "provided": input_path is not None,
            "exists": input_path.exists() if input_path else None,
            "is_dir": input_path.is_dir() if input_path else None,
            "suffix": input_path.suffix.lower() if input_path else None,
            "error": input_error,
        },
        "status": status,
        "blocker": blocker,
        "requested_provider": requested_provider,
        "selected_provider": (
            status_to_dict(selected)
            if selected
            else (
                _provider_status_dict_for_plan(
                    bootstrap_provider,
                    "BOOTSTRAP_EXECUTION_CANDIDATE",
                    "UNPROMOTED_ONE_FILE_BOOTSTRAP",
                )
                if bootstrap_provider
                else None
            )
        ),
        "execution_bootstrap": {
            "enabled": bootstrap_provider is not None,
            "provider": bootstrap_provider.provider if bootstrap_provider else None,
            "reason": bootstrap_reason,
            "writes_promotion_evidence": True,
        },
        "manual_fallback": manual_fallback,
        "fallback_provider": status_to_dict(user_present_status) if user_present_status else None,
        "promotion_gate": promotion_gate,
        "provider_order": PROVIDER_ORDER,
        "execution_policy": {
            "default_mode": "preflight",
            "batch_allowed": bool(
                effective_provider and effective_provider.provider == "standalone"
            ),
            "one_file_only": not bool(
                input_is_batch_dir
                and effective_provider
                and effective_provider.provider == "standalone"
            ),
            "requires_allow_execute": True,
        },
    }


def build_conversion_promotion_evidence(
    provider: str,
    input_path: Path,
    output_path: Path,
    conversion: dict[str, object],
    execution_approved: bool,
) -> dict[str, object]:
    zip_ok = output_path.exists() and is_hwpx_zip(output_path)
    xml_ok = zip_ok
    one_file_success = (
        bool(conversion.get("ok")) and has_hwp_binary_signature(input_path) and zip_ok and xml_ok
    )
    return {
        "provider": provider,
        "input_path": str(input_path),
        "output_path": str(output_path),
        "one_file_success": one_file_success,
        "execution_approved": execution_approved,
        "verified_at": datetime.now(UTC).isoformat(),
        "output_validation": {
            "status": "PASS" if zip_ok and xml_ok else "FAIL",
            "zip_ok": zip_ok,
            "xml_ok": xml_ok,
            "source": "hancom_hwp_converter_router.is_hwpx_zip",
        },
        "input_validation": {
            "status": "PASS" if has_hwp_binary_signature(input_path) else "FAIL",
            "hwp_binary_signature_ok": has_hwp_binary_signature(input_path),
        },
        "source_conversion": conversion,
        "notes": "Generated after explicit --allow-execute one-file conversion.",
    }


def write_promotion_evidence_if_requested(
    args: argparse.Namespace,
    plan: dict[str, object],
    conversion: dict[str, object],
) -> str | None:
    if conversion.get("mode") == "batch_text_only_rebuild":
        return None
    output_path_text = (
        conversion.get("output") or plan.get("actual_output") or plan.get("planned_output")
    )
    if not output_path_text:
        return None
    evidence_arg = getattr(args, "promotion_evidence_out", None)
    output_dir = Path(str(plan["output_dir"]))
    evidence_path = (
        Path(evidence_arg).expanduser().resolve()
        if evidence_arg
        else output_dir / "promotion_evidence.json"
    )
    selected = plan.get("selected_provider")
    provider = str(selected.get("provider") if isinstance(selected, dict) else "")
    evidence = build_conversion_promotion_evidence(
        provider,
        Path(str(plan["input"])).expanduser().resolve(),
        Path(str(output_path_text)).expanduser().resolve(),
        conversion,
        bool(getattr(args, "allow_execute", False)),
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(evidence_path)


def execute_one_file_conversion(
    args: argparse.Namespace, plan: dict[str, object]
) -> dict[str, object]:
    selected = plan.get("selected_provider")
    if not isinstance(selected, dict):
        return {
            "ok": False,
            "status": "NO_SELECTED_PROVIDER",
            "errors": ["No selected provider is ready for execution"],
        }
    provider = str(selected.get("provider") or "")
    input_path = Path(str(plan["input"])).expanduser().resolve()
    output_dir = Path(str(plan["output_dir"])).expanduser().resolve()
    diag_dir = Path(getattr(args, "diag_dir", None) or (output_dir / "diag")).expanduser().resolve()
    timeout_sec = int(getattr(args, "timeout_sec", 90))

    if provider == "com":
        return convert_one_with_strategy(
            input_path,
            output_dir,
            timeout_sec,
            "convert",
            diag_dir,
            str(getattr(args, "save_strategy", "auto")),
        )
    if provider == "standalone":
        return execute_standalone_one(input_path, output_dir, args)
    if provider == "hwpxjs":
        return execute_hwpxjs_one(input_path, output_dir, args)
    if provider == "local_gui":
        return execute_local_gui_one(
            input_path,
            output_dir,
            timeout_sec,
            diag_dir,
        )
    if provider == "user_present":
        return convert_user_present_one(
            input_path,
            output_dir,
            timeout_sec,
            int(getattr(args, "wait_user_sec", 60)),
            diag_dir,
        )
    return {
        "ok": False,
        "status": "PROVIDER_EXECUTION_NOT_IMPLEMENTED",
        "provider": provider,
        "errors": [f"Provider {provider} has no router executor"],
    }


def execute_standalone_one(
    input_path: Path, output_dir: Path, args: argparse.Namespace
) -> dict[str, object]:
    expected_texts = list(getattr(args, "expected_text", []) or [])
    strict_quality = bool(getattr(args, "strict_quality", False))
    existing_policy = str(getattr(args, "existing_policy", "fail") or "fail")
    fidelity_policy = str(getattr(args, "fidelity_policy", "text") or "text")
    log_file = getattr(args, "log_file", None)
    configure_logging(
        Path(log_file) if log_file else default_log_path(input_path, output_dir),
        level=str(getattr(args, "log_level", "INFO") or "INFO"),
    )
    if input_path.is_dir():
        report = convert_batch(
            input_path,
            output_dir,
            expected_texts=expected_texts,
            strict_quality=strict_quality,
            pattern=str(getattr(args, "pattern", "*.hwp") or "*.hwp"),
            existing_policy=existing_policy,
            fidelity_policy=fidelity_policy,
            fail_fast=bool(getattr(args, "fail_fast", False)),
            workers=int(getattr(args, "workers", 1) or 1),
            job_id=str(getattr(args, "job_id", "") or "") or None,
        )
        return {
            "input": str(input_path),
            "output": str(output_dir),
            "provider": "STANDALONE_TEXT_ONLY",
            "mode": "batch_text_only_rebuild",
            "ok": bool(report.get("status") == "PASS"),
            "error_code": "STANDALONE_BATCH_OUTPUT_VALID"
            if report.get("status") == "PASS"
            else "STANDALONE_BATCH_CONVERSION_FAILED",
            "converter_json": report,
        }
    output_path = output_dir / f"{input_path.stem}.hwpx"
    if output_path.exists():
        output_path = output_dir / f"{input_path.stem}_{input_path.stat().st_size}.hwpx"
    report = convert_hwp_to_hwpx(
        input_path,
        output_path,
        expected_texts=expected_texts,
        strict_quality=strict_quality,
        existing_policy=existing_policy,
        fidelity_policy=fidelity_policy,
        embed_original=bool(getattr(args, "embed_original", False)),
        decoded_style_bridge=bool(getattr(args, "decoded_style_bridge", False)),
    )
    log_result("router_file_complete", report)
    report_output = Path(str(report.get("output") or output_path)).expanduser().resolve()
    ok = bool(
        report.get("status") == "PASS" and report_output.exists() and is_hwpx_zip(report_output)
    )
    return {
        "input": str(input_path),
        "output": str(report_output),
        "provider": "STANDALONE_TEXT_ONLY",
        "ok": ok,
        "error_code": "STANDALONE_OUTPUT_VALID"
        if ok
        else str(report.get("error") or "STANDALONE_CONVERSION_FAILED"),
        "converter_json": report,
    }


def execute_hwpxjs_one(
    input_path: Path, output_dir: Path, args: argparse.Namespace
) -> dict[str, object]:
    output_path = output_dir / f"{input_path.stem}.hwpx"
    if output_path.exists():
        output_path = output_dir / f"{input_path.stem}_{input_path.stat().st_size}.hwpx"
    diag_dir = Path(getattr(args, "diag_dir", None) or (output_dir / "diag")).expanduser().resolve()
    diag_dir.mkdir(parents=True, exist_ok=True)
    result_json = diag_dir / f"hwpxjs_{uuid.uuid4().hex[:8]}.json"
    timeout_sec = int(getattr(args, "timeout_sec", 120) or 120)
    cmd = [
        "python",
        str(HWPXJS_ADAPTER_SCRIPT),
        str(input_path),
        str(output_path),
        "--timeout-sec",
        str(timeout_sec),
        "--report-json",
        str(result_json),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec + 15,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "input": str(input_path),
            "output": str(output_path),
            "provider": "HWPXJS_OPEN_SOURCE",
            "ok": False,
            "returncode": None,
            "error_code": "HWPXJS_ADAPTER_TIMEOUT",
            "result_json": str(result_json),
            "stdout_tail": str(exc.stdout or "")[-1000:],
            "stderr_tail": str(exc.stderr or "")[-1000:],
        }

    parsed = None
    if result_json.exists():
        try:
            parsed = json.loads(result_json.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            parsed = None
    ok = bool(
        parsed
        and parsed.get("status") == "PASS"
        and output_path.exists()
        and is_hwpx_zip(output_path)
    )
    return {
        "input": str(input_path),
        "output": str(output_path),
        "provider": "HWPXJS_OPEN_SOURCE",
        "ok": ok,
        "returncode": proc.returncode,
        "converter_json": parsed,
        "error_code": "HWPXJS_OUTPUT_VALID"
        if ok
        else str((parsed or {}).get("error") or "HWPXJS_FAILED"),
        "result_json": str(result_json),
        "stdout_tail": (proc.stdout or "")[-1000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def execute_local_gui_one(
    input_path: Path,
    output_dir: Path,
    timeout_sec: int,
    diag_dir: Path,
) -> dict[str, object]:
    output_path = output_dir / f"{input_path.stem}.hwpx"
    if output_path.exists():
        output_path = output_dir / f"{input_path.stem}_{input_path.stat().st_size}.hwpx"
    job_id = uuid.uuid4().hex[:8]
    diag_dir.mkdir(parents=True, exist_ok=True)
    result_json = diag_dir / f"hancom_local_gui_{job_id}.json"
    stdout_log = diag_dir / f"hancom_local_gui_{job_id}.stdout.log"
    stderr_log = diag_dir / f"hancom_local_gui_{job_id}.stderr.log"
    cmd = [
        "python",
        str(LOCAL_GUI_SCRIPT),
        "--input",
        str(input_path),
        "--output",
        str(output_path),
        "--timeout-sec",
        str(timeout_sec),
        "--mode",
        "save",
        "--result-json",
        str(result_json),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec + 15,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout_log.write_text(stdout, encoding="utf-8", errors="replace")
        stderr_log.write_text(stderr, encoding="utf-8", errors="replace")
        return {
            "input": str(input_path),
            "output": str(output_path),
            "provider": "HANCOM_LOCAL_GUI",
            "job_id": job_id,
            "returncode": None,
            "ok": False,
            "error_code": "LOCAL_GUI_TIMEOUT",
            "error_message": f"Local GUI conversion exceeded {timeout_sec + 15}s timeout",
            "result_json": str(result_json),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
        }

    stdout_log.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    stderr_log.write_text(proc.stderr or "", encoding="utf-8", errors="replace")
    parsed = None
    if result_json.exists():
        try:
            parsed = json.loads(result_json.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            parsed = None
    ok = bool(
        parsed
        and parsed.get("status") == "OUTPUT_VALID"
        and output_path.exists()
        and is_hwpx_zip(output_path)
    )
    return {
        "input": str(input_path),
        "output": str(output_path),
        "provider": "HANCOM_LOCAL_GUI",
        "job_id": job_id,
        "returncode": proc.returncode,
        "ok": ok,
        "converter_json": parsed,
        "error_code": "LOCAL_GUI_OUTPUT_VALID"
        if ok
        else str((parsed or {}).get("status") or "LOCAL_GUI_FAILED"),
        "result_json": str(result_json),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    normalized_rows = [{
            key: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            if isinstance(value, (dict, list))
            else value
            for key, value in row.items()
        } for row in rows]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(normalized_rows[0]))
        writer.writeheader()
        writer.writerows(normalized_rows)


def run(args: argparse.Namespace) -> dict[str, object]:
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    providers = detect_providers()
    plan = build_plan(args, providers)
    result: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "tool": "hancom_hwp_converter_router",
        "schema_version": 2,
        "providers": [status_to_dict(provider) for provider in providers],
        "plan": plan,
    }

    if args.mode == "convert" and not args.allow_execute:
        plan["status"] = "EXECUTION_REFUSED"
        plan["blocker"] = "convert mode requires --allow-execute and a verified provider"
    elif args.mode == "convert":
        promotion_gate = plan.get("promotion_gate")
        if plan.get("status") not in {
            "READY_FOR_ONE_FILE_EXECUTION",
            "READY_FOR_BOOTSTRAP_ONE_FILE_EXECUTION",
        }:
            plan["status"] = "EXECUTION_REFUSED"
            plan["blocker"] = plan.get("blocker") or "provider or input is not execution-ready"
        elif (
            plan.get("status") == "READY_FOR_ONE_FILE_EXECUTION"
            and provider_requires_promotion_evidence(plan)
            and (
                not isinstance(promotion_gate, dict) or promotion_gate.get("promotable") is not True
            )
        ):
            plan["status"] = "EXECUTION_REFUSED_PROMOTION_GATE"
            plan["blocker"] = "convert mode requires promotable one-file provider evidence"
        else:
            conversion = execute_one_file_conversion(args, plan)
            result["conversion"] = conversion
            if conversion.get("ok"):
                plan["status"] = "CONVERSION_SUCCEEDED"
                plan["blocker"] = ""
                plan["actual_output"] = conversion.get("output")
                evidence_path = write_promotion_evidence_if_requested(args, plan, conversion)
                if evidence_path:
                    plan["promotion_evidence_out"] = evidence_path
            else:
                plan["status"] = "CONVERSION_FAILED"
                plan["blocker"] = str(
                    conversion.get("error_code") or conversion.get("status") or "CONVERSION_FAILED"
                )

    report_json = (
        Path(args.report_json).expanduser().resolve()
        if args.report_json
        else output_dir / "router_report.json"
    )
    report_csv = output_dir / "provider_status.csv"
    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(report_csv, [status_to_dict(provider) for provider in providers])
    manual_fallback = plan.get("manual_fallback")
    if isinstance(manual_fallback, dict) and manual_fallback.get("promotion_evidence_template"):
        evidence_template = build_promotion_evidence_template(
            "user_present",
            Path(args.input).expanduser().resolve() if args.input else None,
            Path(str(plan["planned_output"])),
        )
        evidence_path = Path(str(manual_fallback["promotion_evidence_template"]))
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence_template, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    result["report_json"] = str(report_json)
    result["provider_csv"] = str(report_csv)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Hancom HWP converter router")
    parser.add_argument("--input", help="One HWP file path. Optional for provider preflight.")
    parser.add_argument(
        "--output-dir", default=str(TMP_DEFAULT), help="tmp output/report directory"
    )
    parser.add_argument("--report-json", help="Router report JSON path")
    parser.add_argument(
        "--promotion-evidence-json", help="Future provider promotion evidence JSON path"
    )
    parser.add_argument(
        "--promotion-evidence-out",
        help="Path to write promotion evidence after a successful conversion",
    )
    parser.add_argument(
        "--manual-fallback",
        action="store_true",
        help="Include user-present manual fallback command and evidence template",
    )
    parser.add_argument("--mode", choices=["preflight", "convert"], default="preflight")
    parser.add_argument(
        "--provider",
        choices=["auto", "hwpxjs", "standalone", "com", "local_gui", "user_present"],
        default="auto",
    )
    parser.add_argument(
        "--allow-execute",
        action="store_true",
        help="Required for future one-file conversion execution",
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=90, help="One-file conversion timeout in seconds"
    )
    parser.add_argument(
        "--wait-user-sec", type=int, default=60, help="User-present confirmation wait in seconds"
    )
    parser.add_argument("--save-strategy", choices=["direct", "haction", "auto"], default="auto")
    parser.add_argument("--diag-dir", help="Directory for converter diagnostic logs")
    parser.add_argument(
        "--expected-text", action="append", help="Text that must appear in standalone output"
    )
    parser.add_argument(
        "--strict-quality",
        action="store_true",
        help="Fail standalone conversion on quality warnings",
    )
    parser.add_argument(
        "--embed-original", action="store_true", help="Embed the original HWP in standalone output"
    )
    parser.add_argument(
        "--decoded-style-bridge",
        action="store_true",
        help="Apply decoded style bridge in standalone output",
    )
    parser.add_argument(
        "--fidelity-policy",
        choices=["text", "audit", "strict"],
        default="text",
        help="Standalone fidelity handling for unsupported HWP records",
    )
    parser.add_argument(
        "--pattern", default="*.hwp", help="Standalone batch file pattern. Default: *.hwp"
    )
    parser.add_argument(
        "--existing-policy",
        choices=["fail", "skip", "rename", "overwrite"],
        default="fail",
        help="Standalone output collision policy. Default: fail.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Standalone batch stops after the first failed file",
    )
    parser.add_argument(
        "--workers", type=int, default=1, help="Standalone batch parallel workers. Default: 1"
    )
    parser.add_argument("--log-file", help="Standalone converter log file path")
    parser.add_argument(
        "--log-level", default="INFO", help="Standalone converter log level. Default: INFO"
    )
    parser.add_argument("--job-id", help="Standalone converter job id")
    args = parser.parse_args()
    result = run(args)
    plan = result["plan"]
    print(
        json.dumps(
            {
                "status": plan["status"],
                "blocker": plan["blocker"],
                "report_json": result["report_json"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
