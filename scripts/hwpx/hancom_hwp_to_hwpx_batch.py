#!/usr/bin/env python3
"""
Convert local HWP samples to HWPX using Hancom Office only.

Policy:
- HWP conversion provider is fixed to Hancom COM via 32-bit PowerShell.
- LibreOffice, pyhwp, hwp5txt, and other fallback converters are intentionally
  not used.
- Input samples are read from a local folder. Outputs and reports are written
  under tmp/ by default and must not be committed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
HANCOM_CONVERTER_SCRIPT = REPO_ROOT / "scripts" / "hwp-worker" / "Convert-HwpToHwpx-v2.ps1"
HANCOM_USER_PRESENT_SCRIPT = REPO_ROOT / "scripts" / "hwp-worker" / "Convert-HwpToHwpx-UserPresent.ps1"
HANCOM_32BIT_POWERSHELL = Path(os.environ.get("WINDIR", r"C:\Windows")) / "SysWOW64" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
HWP_CONVERSION_PROVIDER = "HANCOM_COM_32BIT_ONLY"
HWP_USER_PRESENT_PROVIDER = "HANCOM_USER_PRESENT_GUI"
DISALLOWED_CONVERTERS = ("libreoffice", "soffice", "pyhwp", "hwp5txt", "hwp5odt")


def is_hwpx_zip(path: Path) -> bool:
    try:
        with ZipFile(path) as zf:
            names = set(zf.namelist())
        return any(name.endswith("section0.xml") for name in names) or "mimetype" in names
    except BadZipFile:
        return False


def inventory(input_dir: Path) -> dict[str, list[Path]]:
    files = [p for p in input_dir.rglob("*") if p.is_file()]
    return {
        "hwp": sorted(p for p in files if p.suffix.lower() == ".hwp"),
        "hwpx": sorted(p for p in files if p.suffix.lower() == ".hwpx"),
        "zip": sorted(p for p in files if p.suffix.lower() == ".zip"),
        "other": sorted(p for p in files if p.suffix.lower() not in {".hwp", ".hwpx", ".zip"}),
    }


def check_hancom_converter() -> dict[str, object]:
    return {
        "provider": HWP_CONVERSION_PROVIDER,
        "converter_script": str(HANCOM_CONVERTER_SCRIPT),
        "converter_script_exists": HANCOM_CONVERTER_SCRIPT.exists(),
        "user_present_script": str(HANCOM_USER_PRESENT_SCRIPT),
        "user_present_script_exists": HANCOM_USER_PRESENT_SCRIPT.exists(),
        "powershell_32bit": str(HANCOM_32BIT_POWERSHELL),
        "powershell_32bit_exists": HANCOM_32BIT_POWERSHELL.exists(),
        "disallowed_converters": list(DISALLOWED_CONVERTERS),
    }


def current_hwp_pids() -> set[int]:
    if os.name != "nt":
        return set()
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    pids: set[int] = set()
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if line.isdigit():
            pids.add(int(line))
    return pids


def stop_pids(pids: set[int]) -> list[int]:
    stopped: list[int] = []
    for pid in sorted(pids):
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode == 0:
            stopped.append(pid)
    return stopped


def read_last_diag_stage(diag_log: Path) -> dict[str, object] | None:
    if not diag_log.exists():
        return None
    last: dict[str, object] | None = None
    for line in diag_log.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            last = json.loads(line)
        except json.JSONDecodeError:
            continue
    return last


def timeout_error_code(last_stage: str | None) -> str:
    if last_stage == "OPEN_START":
        return "HANCOM_OPEN_TIMEOUT"
    if last_stage in {"SAVEAS_START", "SAVEAS_DIRECT_START", "SAVEAS_HACTION_START"}:
        return "HANCOM_SAVEAS_TIMEOUT"
    if last_stage == "COM_CREATE_START":
        return "COM_CREATE_TIMEOUT"
    if last_stage == "QUIT_START":
        return "QUIT_TIMEOUT"
    return "HANCOM_CONVERSION_TIMEOUT"


def parsed_error_code(parsed: dict[str, object] | None, ok: bool) -> str | None:
    if ok:
        return "HANCOM_CONVERSION_SUCCESS"
    if not parsed:
        return "HANCOM_UNKNOWN_ERROR"
    code = parsed.get("errorCode")
    if code:
        return str(code)
    if parsed.get("registerModule") is False:
        return "HANCOM_REGISTER_MODULE_FALSE"
    return "HANCOM_UNKNOWN_ERROR"


def convert_one(
    input_path: Path,
    output_dir: Path,
    timeout_sec: int,
    mode: str,
    diag_dir: Path,
    save_strategy: str,
) -> dict[str, object]:
    output_path = output_dir / f"{input_path.stem}.hwpx"
    if output_path.exists():
        output_path = output_dir / f"{input_path.stem}_{input_path.stat().st_size}.hwpx"
    job_id = uuid.uuid4().hex[:8]
    diag_dir.mkdir(parents=True, exist_ok=True)
    diag_log = diag_dir / f"hancom_hwp_to_hwpx_{job_id}.jsonl"
    stdout_log = diag_dir / f"hancom_hwp_to_hwpx_{job_id}.stdout.log"
    stderr_log = diag_dir / f"hancom_hwp_to_hwpx_{job_id}.stderr.log"

    cmd = [
        str(HANCOM_32BIT_POWERSHELL),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HANCOM_CONVERTER_SCRIPT),
        "-InputPath",
        str(input_path),
        "-OutputPath",
        str(output_path),
        "-TimeoutSec",
        str(timeout_sec),
        "-Mode",
        mode,
        "-SaveStrategy",
        save_strategy,
        "-DiagDir",
        str(diag_dir),
        "-JobId",
        job_id,
    ]
    before_pids = current_hwp_pids()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        after_pids = current_hwp_pids()
        owned_pids = after_pids - before_pids
        stopped_pids = stop_pids(owned_pids)
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout_log.write_text(stdout, encoding="utf-8", errors="replace")
        stderr_log.write_text(stderr, encoding="utf-8", errors="replace")
        last_diag = read_last_diag_stage(diag_log)
        last_stage = str(last_diag.get("stage")) if last_diag else None
        return {
            "input": str(input_path),
            "output": str(output_path),
            "provider": HWP_CONVERSION_PROVIDER,
            "mode": mode,
            "save_strategy": save_strategy,
            "job_id": job_id,
            "returncode": None,
            "ok": False,
            "converter_json": None,
            "error_code": timeout_error_code(last_stage),
            "error_message": f"Hancom conversion exceeded {timeout_sec}s subprocess timeout at {last_stage or 'UNKNOWN'}",
            "last_diag_stage": last_stage,
            "diag_log": str(diag_log),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "owned_hwp_pids": sorted(owned_pids),
            "stopped_hwp_pids": stopped_pids,
            "stdout_tail": stdout[-1000:],
            "stderr_tail": stderr[-1000:],
        }

    stdout_log.write_text(proc.stdout or "", encoding="utf-8", errors="replace")
    stderr_log.write_text(proc.stderr or "", encoding="utf-8", errors="replace")
    parsed = None
    stdout = (proc.stdout or "").strip()
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                parsed = None
            break
    ok = bool(parsed and parsed.get("ok") and (mode == "open-only" or (output_path.exists() and is_hwpx_zip(output_path))))

    return {
        "input": str(input_path),
        "output": str(output_path),
        "provider": HWP_CONVERSION_PROVIDER,
        "mode": mode,
        "save_strategy": save_strategy,
        "job_id": job_id,
        "returncode": proc.returncode,
        "ok": ok,
        "converter_json": parsed,
        "error_code": parsed_error_code(parsed, ok),
        "diag_log": str(diag_log),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def convert_one_with_strategy(
    input_path: Path,
    output_dir: Path,
    timeout_sec: int,
    mode: str,
    diag_dir: Path,
    save_strategy: str,
) -> dict[str, object]:
    if save_strategy != "auto" or mode == "open-only":
        return convert_one(input_path, output_dir, timeout_sec, mode, diag_dir, save_strategy)

    direct = convert_one(input_path, output_dir, timeout_sec, mode, diag_dir, "direct")
    if direct.get("ok"):
        direct["save_strategy"] = "auto"
        direct["strategy_attempts"] = [strategy_attempt_summary(direct)]
        return direct

    haction = convert_one(input_path, output_dir, timeout_sec, mode, diag_dir, "haction")
    haction["save_strategy"] = "auto"
    haction["strategy_attempts"] = [strategy_attempt_summary(direct), strategy_attempt_summary(haction)]
    return haction


def strategy_attempt_summary(result: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in result.items()
        if key not in {"strategy_attempts", "converter_json"}
    }


def convert_user_present_one(
    input_path: Path,
    output_dir: Path,
    timeout_sec: int,
    wait_user_sec: int,
    diag_dir: Path,
) -> dict[str, object]:
    output_path = output_dir / f"{input_path.stem}.hwpx"
    if output_path.exists():
        output_path = output_dir / f"{input_path.stem}_{input_path.stat().st_size}.hwpx"
    job_id = uuid.uuid4().hex[:8]
    diag_dir.mkdir(parents=True, exist_ok=True)
    result_path = diag_dir / f"hancom_user_present_{job_id}.json"
    stdout_log = diag_dir / f"hancom_user_present_{job_id}.stdout.log"
    stderr_log = diag_dir / f"hancom_user_present_{job_id}.stderr.log"

    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(HANCOM_USER_PRESENT_SCRIPT),
        "-InputPath",
        str(input_path),
        "-OutputPath",
        str(output_path),
        "-TimeoutSeconds",
        str(timeout_sec),
        "-WaitUserSeconds",
        str(wait_user_sec),
        "-ResultPath",
        str(result_path),
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            text=True,
            timeout=timeout_sec,
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
            "provider": HWP_USER_PRESENT_PROVIDER,
            "job_id": job_id,
            "returncode": None,
            "ok": False,
            "converter_json": None,
            "error_code": "USER_PRESENT_TIMEOUT",
            "error_message": f"User-present conversion exceeded {timeout_sec}s timeout",
            "result_path": str(result_path),
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "stdout_tail": stdout[-1000:],
            "stderr_tail": stderr[-1000:],
        }

    stdout_log.write_text("", encoding="utf-8", errors="replace")
    stderr_log.write_text("", encoding="utf-8", errors="replace")
    parsed = None
    if result_path.exists():
        try:
            parsed = json.loads(result_path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            parsed = None
    if parsed is None:
        stdout = (proc.stdout or "").strip()
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    parsed = None
                break
    ok = bool(parsed and parsed.get("ok") and output_path.exists() and is_hwpx_zip(output_path))
    return {
        "input": str(input_path),
        "output": str(output_path),
        "provider": HWP_USER_PRESENT_PROVIDER,
        "job_id": job_id,
        "returncode": proc.returncode,
        "ok": ok,
        "converter_json": parsed,
        "error_code": "USER_PRESENT_OUTPUT_VALID" if ok else (str(parsed.get("status")) if parsed else "USER_PRESENT_SAVEAS_FAILED"),
        "result_path": str(result_path),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
        "stderr_tail": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, help="Local folder containing downloaded G2B HWP/HWPX files")
    parser.add_argument("--output-dir", default="tmp/p3d_g2b_hancom_converted_hwpx_20260508")
    parser.add_argument("--report-json", default="tmp/p3d_g2b_hancom_conversion_report_20260508.json")
    parser.add_argument("--limit", type=int, default=3, help="Maximum HWP files to convert; 0 means all")
    parser.add_argument(
        "--skip-name-contains",
        action="append",
        default=[],
        help="Skip HWP files whose file name contains this text. Can be repeated.",
    )
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--wait-user-sec", type=int, default=60)
    parser.add_argument(
        "--save-strategy",
        choices=["direct", "haction", "auto"],
        default="direct",
        help="Hancom HWPX save strategy for COM conversion.",
    )
    parser.add_argument(
        "--provider",
        choices=[HWP_CONVERSION_PROVIDER, HWP_USER_PRESENT_PROVIDER],
        default=HWP_CONVERSION_PROVIDER,
    )
    parser.add_argument(
        "--mode",
        choices=["convert", "open-only", "saveas"],
        default="convert",
        help="Diagnostic mode passed to the Hancom worker.",
    )
    parser.add_argument("--diag-dir", default="tmp/hancom_hwp_to_hwpx_diag")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).resolve()
    output_dir = (REPO_ROOT / args.output_dir).resolve()
    report_json = (REPO_ROOT / args.report_json).resolve()
    diag_dir = (REPO_ROOT / args.diag_dir).resolve()

    if not input_dir.exists() or not input_dir.is_dir():
        raise SystemExit(f"INPUT_DIR_NOT_FOUND: {input_dir}")
    if args.provider == HWP_USER_PRESENT_PROVIDER and args.limit != 1:
        raise SystemExit("USER_PRESENT_LIMIT_GUARD: use --limit 1 until one conversion is verified")

    inv = inventory(input_dir)
    converter = check_hancom_converter()
    if not args.dry_run:
        if args.provider == HWP_CONVERSION_PROVIDER and not converter["converter_script_exists"]:
            raise SystemExit("HANCOM_CONVERTER_SCRIPT_NOT_FOUND")
        if args.provider == HWP_USER_PRESENT_PROVIDER and not converter["user_present_script_exists"]:
            raise SystemExit("HANCOM_USER_PRESENT_SCRIPT_NOT_FOUND")
        if args.provider == HWP_CONVERSION_PROVIDER and not converter["powershell_32bit_exists"]:
            raise SystemExit("POWERSHELL_32BIT_NOT_FOUND")
        output_dir.mkdir(parents=True, exist_ok=True)
        diag_dir.mkdir(parents=True, exist_ok=True)

    hwp_candidates = sorted(inv["hwp"], key=lambda p: (p.stat().st_size, p.name))
    if args.skip_name_contains:
        hwp_candidates = [
            p for p in hwp_candidates
            if not any(token in p.name for token in args.skip_name_contains)
        ]
    hwp_targets = hwp_candidates if args.limit == 0 else hwp_candidates[: args.limit]
    conversions = []
    if not args.dry_run:
        for hwp in hwp_targets:
            if args.provider == HWP_USER_PRESENT_PROVIDER:
                conversions.append(convert_user_present_one(hwp, output_dir, args.timeout_sec, args.wait_user_sec, diag_dir))
            else:
                conversions.append(convert_one_with_strategy(hwp, output_dir, args.timeout_sec, args.mode, diag_dir, args.save_strategy))

    valid_hwpx = []
    for path in inv["hwpx"]:
        valid_hwpx.append({
            "path": str(path),
            "size": path.stat().st_size,
            "is_hwpx_zip": is_hwpx_zip(path),
        })

    report = {
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "diag_dir": str(diag_dir),
        "policy": {
            "hwp_conversion_provider": args.provider,
            "com_direct_open": "BLOCKED" if args.provider == HWP_USER_PRESENT_PROVIDER else "ENABLED",
            "disallowed_converters": list(DISALLOWED_CONVERTERS),
            "server_upload": False,
            "git_stage_outputs": False,
        },
        "converter": converter,
        "counts": {k: len(v) for k, v in inv.items()},
        "dry_run": args.dry_run,
        "provider": args.provider,
        "mode": args.mode,
        "save_strategy": args.save_strategy,
        "hwp_targets": [str(p) for p in hwp_targets],
        "valid_hwpx_count": sum(1 for x in valid_hwpx if x["is_hwpx_zip"]),
        "hwpx_samples": valid_hwpx[:20],
        "conversions": conversions,
    }

    report_json.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": all(c.get("ok") for c in conversions) if conversions else True,
        "provider": args.provider,
        "input_dir": str(input_dir),
        "counts": report["counts"],
        "mode": args.mode,
        "hwp_target_count": len(hwp_targets),
        "converted_ok": sum(1 for c in conversions if c.get("ok")),
        "valid_hwpx_count": report["valid_hwpx_count"],
        "report_json": str(report_json),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
