#!/usr/bin/env python3
"""Automatic delivery verification for generated HWPX files.

This verifier does not convert HWP with Hancom. It validates an already
generated HWPX package and can optionally open/render it through Hancom COM to
prove that Hancom accepts the package without a manual check.
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hwpx_package import HwpxValidator
from hwpx_package_audit import audit_hwpx_package
from hwpx_spine_repair import repair_hwpx_spine

REPO_ROOT = Path(__file__).resolve().parents[2]
DIAG_DIR = Path(__file__).resolve().parent / "diagnostics"
PS32 = Path(r"C:\Windows\SysWOW64\WindowsPowerShell\v1.0\powershell.exe")
RENDER_SCRIPT = REPO_ROOT / "scripts" / "hwpx" / "hancom_render_to_image.ps1"

if str(DIAG_DIR) not in sys.path:
    sys.path.insert(0, str(DIAG_DIR))
check_roundtrip_text = importlib.import_module("06_roundtrip_text_probe").check_roundtrip_text


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _check(name: str, passed: bool, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "PASS" if passed else "FAIL", **details}


def _warn(name: str, **details: Any) -> dict[str, Any]:
    return {"name": name, "status": "WARN", **details}


def _status_check(name: str, status: str, **details: Any) -> dict[str, Any]:
    normalized = status if status in {"PASS", "WARN", "FAIL", "SKIPPED"} else "FAIL"
    return {"name": name, "status": normalized, **details}


def repair_shadow_check(hwpx_path: Path, work_dir: Path, strict: bool) -> dict[str, Any]:
    repaired = work_dir / f"{hwpx_path.stem}.repaired.hwpx"
    repair = repair_hwpx_spine(hwpx_path, repaired)
    audit = (
        audit_hwpx_package(repaired, strict=strict)
        if repaired.exists()
        else {"status": "FAIL", "error": "REPAIRED_OUTPUT_NOT_FOUND"}
    )
    return {
        "status": "PASS"
        if repair.get("status") == "PASS" and audit.get("status") == "PASS"
        else "FAIL",
        "repaired": str(repaired),
        "repair": repair,
        "audit": audit,
    }


def hancom_render_check(
    hwpx_path: Path, work_dir: Path, page: int, resolution: int, timeout_sec: int
) -> dict[str, Any]:
    if not PS32.exists():
        return {"status": "SKIPPED", "reason": "POWERSHELL_32BIT_NOT_FOUND", "path": str(PS32)}
    if not RENDER_SCRIPT.exists():
        return {
            "status": "SKIPPED",
            "reason": "RENDER_SCRIPT_NOT_FOUND",
            "path": str(RENDER_SCRIPT),
        }
    output = work_dir / "hancom_render" / f"{hwpx_path.stem}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(PS32),
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RENDER_SCRIPT),
        "-InputPath",
        str(hwpx_path),
        "-OutputPath",
        str(output),
        "-Page",
        str(page),
        "-Resolution",
        str(resolution),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "FAIL",
            "reason": "HANCOM_RENDER_TIMEOUT",
            "timeout_sec": timeout_sec,
            "stdout": (exc.stdout or "")[-4000:],
            "stderr": (exc.stderr or "")[-4000:],
        }
    if completed.returncode != 0:
        return {
            "status": "FAIL",
            "reason": "HANCOM_RENDER_FAILED",
            "returncode": completed.returncode,
            "stdout": completed.stdout[-4000:],
            "stderr": completed.stderr[-4000:],
        }
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    payload: dict[str, Any] = {}
    if lines:
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError:
            payload = {"raw_stdout_tail": completed.stdout[-4000:]}
    rendered = Path(str(payload.get("output") or output))
    return {
        "status": "PASS"
        if payload.get("ok") is True and rendered.exists() and rendered.stat().st_size > 0
        else "FAIL",
        "mode": "hancom_open_print_to_image",
        "page": page,
        "resolution": resolution,
        "renderer": payload,
        "rendered": str(rendered),
        "rendered_exists": rendered.exists(),
        "rendered_size": rendered.stat().st_size if rendered.exists() else 0,
    }


def final_status(checks: list[dict[str, Any]], *, require_hancom: bool) -> str:
    if any(check.get("status") == "FAIL" for check in checks):
        return "FAIL"
    if require_hancom and not any(
        check.get("name") == "hancom_render" and check.get("status") == "PASS" for check in checks
    ):
        return "FAIL"
    if any(check.get("status") in {"WARN", "SKIPPED"} for check in checks):
        return "WARN"
    return "PASS"


def verify_hwpx_delivery(  # ruff: ignore[too-many-arguments] - hwpx_api.py 등 외부 호출부 존재, 시그니처 변경 보류
    hwpx_path: Path,
    *,
    source_hwp: Path | None = None,
    strict: bool = True,
    hancom: str = "auto",
    page: int = 1,
    resolution: int = 120,
    timeout_sec: int = 120,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    hwpx_path = Path(hwpx_path).expanduser().resolve()
    source_hwp = Path(source_hwp).expanduser().resolve() if source_hwp else None
    owned_temp = None
    if work_dir is None:
        owned_temp = tempfile.TemporaryDirectory(prefix="hwpx_delivery_verify_")
        work_dir = Path(owned_temp.name)
    else:
        work_dir = Path(work_dir).expanduser().resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        validation = HwpxValidator.validate_hwpx(hwpx_path)
        audit = audit_hwpx_package(hwpx_path, strict=strict)
        repair_shadow = (
            repair_shadow_check(hwpx_path, work_dir, strict=strict)
            if hwpx_path.exists()
            else {"status": "FAIL", "error": "HWPX_NOT_FOUND"}
        )
        roundtrip = (
            check_roundtrip_text(source_hwp, hwpx_path, 0.98)
            if source_hwp and source_hwp.exists()
            else {"status": "SKIPPED", "reason": "SOURCE_HWP_NOT_PROVIDED"}
        )

        checks = [
            _check("file_exists", hwpx_path.exists(), path=str(hwpx_path)),
            _check("zip_open", validation.get("zip_ok") is True, validation=validation),
            _check(
                "xml_parse",
                validation.get("xml_ok") is True,
                xml_errors=validation.get("xml_errors"),
            ),
            _check(
                "strict_package_audit",
                audit.get("status") == "PASS",
                audit_status=audit.get("status"),
            ),
            _check(
                "shadow_repair_audit",
                repair_shadow.get("status") == "PASS",
                repair_status=repair_shadow.get("status"),
            ),
        ]
        if source_hwp:
            checks.append(
                _status_check(
                    "source_text_roundtrip",
                    str(roundtrip.get("status") or "FAIL"),
                    roundtrip_status=roundtrip.get("status"),
                )
            )
        else:
            checks.append(_warn("source_text_roundtrip", reason="SOURCE_HWP_NOT_PROVIDED"))

        hancom_report = {"status": "SKIPPED", "reason": "HANCOM_CHECK_OFF"}
        if hancom in {"auto", "required"}:
            hancom_report = hancom_render_check(hwpx_path, work_dir, page, resolution, timeout_sec)
            if hancom_report.get("status") == "SKIPPED" and hancom == "auto":
                checks.append(_warn("hancom_render", reason=hancom_report.get("reason")))
            else:
                checks.append(
                    _check(
                        "hancom_render",
                        hancom_report.get("status") == "PASS",
                        hancom_status=hancom_report.get("status"),
                        reason=hancom_report.get("reason"),
                    )
                )
        elif hancom == "off":
            checks.append(_warn("hancom_render", reason="HANCOM_CHECK_OFF"))
        else:
            raise ValueError("hancom must be one of: auto, required, off")

        status = final_status(checks, require_hancom=hancom == "required")
        return {
            "status": status,
            "checked_at": iso_now(),
            "mode": "hwpx_delivery_auto_verify",
            "hwpx": str(hwpx_path),
            "source_hwp": str(source_hwp) if source_hwp else "",
            "strict": strict,
            "hancom_mode": hancom,
            "work_dir": str(work_dir),
            "checks": checks,
            "validation": validation,
            "audit": audit,
            "shadow_repair": repair_shadow,
            "roundtrip_text": roundtrip,
            "hancom_render": hancom_report,
        }
    finally:
        if owned_temp is not None:
            owned_temp.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwpx", required=True, type=Path)
    parser.add_argument("--source-hwp", type=Path)
    parser.add_argument("--hancom", choices=["auto", "required", "off"], default="auto")
    parser.add_argument("--no-strict", action="store_true")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--resolution", type=int, default=120)
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--report-json", type=Path)
    args = parser.parse_args()
    report = verify_hwpx_delivery(
        args.hwpx,
        source_hwp=args.source_hwp,
        strict=not args.no_strict,
        hancom=args.hancom,
        page=args.page,
        resolution=args.resolution,
        timeout_sec=args.timeout_sec,
        work_dir=args.work_dir,
    )
    if args.report_json:
        args.report_json.parent.mkdir(parents=True, exist_ok=True)
        args.report_json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
