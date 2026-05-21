#!/usr/bin/env python3
"""Adapter for ssabro/hwpxjs HWP -> HWPX conversion.

The adapter is intentionally thin: it does not download npm packages or build
TypeScript. It discovers an already installed `hwpxjs`/`hwpx` command or a
locally built `dist/cli.js`, executes `convert:hwp`, and validates that the
result is a HWPX-like ZIP package.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = REPO_ROOT / "tmp" / "external_hwpxjs_source"
HWP_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


@dataclass(frozen=True)
class HwpxJsCandidate:
    kind: str
    command: list[str]
    cwd: str | None
    evidence: str


def is_hwp_binary(path: Path) -> bool:
    try:
        return path.read_bytes()[: len(HWP_OLE_SIGNATURE)] == HWP_OLE_SIGNATURE
    except OSError:
        return False


def is_hwpx_zip(path: Path) -> bool:
    try:
        with ZipFile(path) as zf:
            names = zf.namelist()
        return bool(names) and ("mimetype" in names or any(name.lower().endswith(".xml") for name in names))
    except (BadZipFile, OSError):
        return False


def _command_candidate(executable: str) -> HwpxJsCandidate | None:
    found = shutil.which(executable)
    if not found:
        return None
    return HwpxJsCandidate(
        kind="command",
        command=[found],
        cwd=None,
        evidence=f"{executable}={found}",
    )


def discover_hwpxjs(repo: Path | None = None) -> dict[str, object]:
    """Return executable discovery details without mutating the machine."""
    env_cli = os.environ.get("HWPXJS_CLI", "").strip()
    if env_cli:
        cli_path = Path(env_cli).expanduser()
        if cli_path.exists():
            return {
                "status": "READY",
                "candidate": asdict(
                    HwpxJsCandidate(
                        kind="env_cli",
                        command=["node", str(cli_path.resolve())] if cli_path.suffix.lower() == ".js" else [str(cli_path.resolve())],
                        cwd=str(cli_path.parent.resolve()),
                        evidence=f"HWPXJS_CLI={cli_path.resolve()}",
                    )
                ),
            }
        return {"status": "ENV_CLI_NOT_FOUND", "candidate": None, "evidence": f"HWPXJS_CLI={env_cli}"}

    repo_root = Path(os.environ.get("HWPXJS_REPO", "") or repo or DEFAULT_REPO).expanduser().resolve()
    dist_cli = repo_root / "dist" / "cli.js"
    package_json = repo_root / "package.json"
    if dist_cli.exists():
        return {
            "status": "READY",
            "candidate": asdict(
                HwpxJsCandidate(
                    kind="local_dist",
                    command=["node", str(dist_cli)],
                    cwd=str(repo_root),
                    evidence=f"dist_cli={dist_cli}",
                )
            ),
        }

    for executable in ("hwpxjs", "hwpx"):
        candidate = _command_candidate(executable)
        if candidate:
            return {"status": "READY", "candidate": asdict(candidate)}

    if package_json.exists():
        return {
            "status": "SOURCE_FOUND_NEEDS_BUILD",
            "candidate": None,
            "evidence": f"source={repo_root}; missing dist/cli.js",
            "next_action": "Run npm install && npm run build in the hwpxjs checkout, or set HWPXJS_CLI to a built CLI.",
        }

    return {
        "status": "NOT_FOUND",
        "candidate": None,
        "evidence": "No HWPXJS_CLI, built local dist/cli.js, or hwpxjs/hwpx command found",
        "searched_repo": str(repo_root),
    }


def _candidate_from_discovery(discovery: dict[str, object]) -> HwpxJsCandidate | None:
    raw = discovery.get("candidate")
    if not isinstance(raw, dict):
        return None
    command = raw.get("command")
    if not isinstance(command, list) or not command:
        return None
    return HwpxJsCandidate(
        kind=str(raw.get("kind") or ""),
        command=[str(part) for part in command],
        cwd=str(raw.get("cwd")) if raw.get("cwd") else None,
        evidence=str(raw.get("evidence") or ""),
    )


def promote_temp_output(temp_output: Path, output_path: Path) -> dict[str, object]:
    """Move a validated temp file into place, tolerating OneDrive locks."""
    unlink_error = ""
    if output_path.exists():
        try:
            output_path.unlink()
        except PermissionError as exc:
            unlink_error = str(exc)
    try:
        temp_output.replace(output_path)
        return {"method": "replace", "temp_cleanup": "removed", "preexisting_unlink_error": unlink_error}
    except PermissionError:
        shutil.copy2(temp_output, output_path)
        cleanup = "removed"
        cleanup_error = ""
        try:
            temp_output.unlink()
        except OSError as exc:
            cleanup = "left_in_place"
            cleanup_error = str(exc)
        return {
            "method": "copy_unlink",
            "temp_cleanup": cleanup,
            "temp_cleanup_error": cleanup_error,
            "preexisting_unlink_error": unlink_error,
        }


def convert_with_hwpxjs(input_path: Path, output_path: Path, *, timeout_sec: int = 120) -> dict[str, object]:
    input_path = input_path.expanduser().resolve()
    output_path = output_path.expanduser().resolve()
    discovery = discover_hwpxjs()
    candidate = _candidate_from_discovery(discovery)
    started_at = datetime.now(timezone.utc).isoformat()
    if not input_path.exists():
        return {"status": "FAIL", "error": "INPUT_NOT_FOUND", "input": str(input_path), "discovery": discovery}
    if input_path.suffix.lower() != ".hwp" or not is_hwp_binary(input_path):
        return {"status": "FAIL", "error": "INPUT_NOT_HWP_BINARY", "input": str(input_path), "discovery": discovery}
    if candidate is None:
        return {"status": "FAIL", "error": "HWPXJS_NOT_EXECUTABLE", "input": str(input_path), "discovery": discovery}

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_name(f".hwpxjs_tmp.{uuid4().hex}{output_path.suffix}")
    if temp_output.exists():
        temp_output.unlink()

    command = [*candidate.command, "convert:hwp", str(input_path), str(temp_output)]
    try:
        proc = subprocess.run(
            command,
            cwd=candidate.cwd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "FAIL",
            "error": "HWPXJS_TIMEOUT",
            "input": str(input_path),
            "output": str(output_path),
            "timeout_sec": timeout_sec,
            "stdout_tail": str(exc.stdout or "")[-2000:],
            "stderr_tail": str(exc.stderr or "")[-2000:],
            "discovery": discovery,
            "started_at": started_at,
        }

    zip_ok = temp_output.exists() and is_hwpx_zip(temp_output)
    if proc.returncode == 0 and zip_ok:
        promotion = promote_temp_output(temp_output, output_path)
        return {
            "status": "PASS",
            "error": None,
            "input": str(input_path),
            "output": str(output_path),
            "provider": "HWPXJS",
            "returncode": proc.returncode,
            "zip_ok": True,
            "promotion": promotion,
            "command_kind": candidate.kind,
            "discovery": discovery,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "stdout_tail": (proc.stdout or "")[-2000:],
            "stderr_tail": (proc.stderr or "")[-2000:],
        }

    if temp_output.exists():
        temp_output.unlink()
    return {
        "status": "FAIL",
        "error": "HWPXJS_CONVERSION_FAILED" if proc.returncode != 0 else "HWPXJS_OUTPUT_INVALID",
        "input": str(input_path),
        "output": str(output_path),
        "provider": "HWPXJS",
        "returncode": proc.returncode,
        "zip_ok": zip_ok,
        "command_kind": candidate.kind,
        "discovery": discovery,
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert HWP to HWPX through an installed hwpxjs CLI")
    parser.add_argument("input", nargs="?", help="Input .hwp path")
    parser.add_argument("output", nargs="?", help="Output .hwpx path")
    parser.add_argument("--discover", action="store_true", help="Only report hwpxjs discovery status")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--report-json", help="Write JSON report")
    args = parser.parse_args()

    if args.discover:
        report = discover_hwpxjs()
    else:
        if not args.input or not args.output:
            parser.error("input and output are required unless --discover is used")
        report = convert_with_hwpxjs(Path(args.input), Path(args.output), timeout_sec=int(args.timeout_sec))

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report_json:
        path = Path(args.report_json).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report.get("status") in {"READY", "PASS", "SOURCE_FOUND_NEEDS_BUILD"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
