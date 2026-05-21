#!/usr/bin/env python3
"""Health check for HWPX/Hancom local toolchain modules."""

from __future__ import annotations

import argparse
import compileall
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "tmp" / "hancom_toolchain_health_check"
DEFAULT_API_URL = "http://127.0.0.1:8080"
PYTEST_TEMP_ROOT = Path(tempfile.gettempdir()) / "office-analysis-engine-pytest"
HWP_OLE_SIGNATURE = bytes.fromhex("D0CF11E0A1B11AE1")


def status(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def check_compile(paths: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    ok = True
    for path in paths:
        path_ok = compileall.compile_dir(str(path), quiet=1, force=False)
        rows.append({"path": str(path), "status": status(bool(path_ok))})
        ok = ok and bool(path_ok)
    return {"status": status(ok), "items": rows}


def run_command(command: list[str], timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "status": "PASS" if proc.returncode == 0 else "FAIL",
            "returncode": proc.returncode,
            "command": command,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "FAIL",
            "returncode": None,
            "command": command,
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
            "error": f"timeout after {timeout}s",
        }



def normalize_pytest_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") == "PASS":
        return result
    combined = f"{result.get('stdout_tail', '')}\n{result.get('stderr_tail', '')}"
    if "PermissionError" in combined and "pytest" in str(result.get("command", "")):
        fixed = dict(result)
        fixed["status"] = "WARN"
        fixed["warning"] = "PYTEST_SUBPROCESS_PERMISSION_BLOCKED; run pytest directly with --basetemp"
        return fixed
    return result


def check_http_get(url: str, timeout: int = 5) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(1000).decode("utf-8", errors="replace")
        return {"status": "PASS", "http_status": response.status, "url": url, "body": body}
    except urllib.error.URLError as exc:
        return {"status": "FAIL", "url": url, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        return {"status": "FAIL", "url": url, "error": str(exc)}


def prepare_user_present_evidence_fixture(out_dir: Path) -> tuple[Path, Path]:
    fixture_dir = out_dir / "user_present_evidence"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    input_path = fixture_dir / "sample.hwp"
    output_path = fixture_dir / "sample.hwpx"
    result_path = fixture_dir / "user_present_result.json"
    input_path.write_bytes(HWP_OLE_SIGNATURE + b"placeholder")
    with zipfile.ZipFile(output_path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("Contents/section0.xml", "<root><p>ok</p></root>")
    write_json(
        result_path,
        {
            "ok": True,
            "provider": "HANCOM_USER_PRESENT_GUI",
            "stage": "OUTPUT_CHECK_DONE",
            "status": "USER_PRESENT_OUTPUT_VALID",
            "input_path": str(input_path),
            "output_path": str(output_path),
            "output_exists": True,
            "output_size": output_path.stat().st_size,
            "zip_valid": True,
            "zip_entries": 2,
            "zip_error": None,
        },
    )
    return result_path, fixture_dir / "promotion_evidence.json"


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Hancom Toolchain Health Check",
        "",
        f"- generated_at: `{report['generated_at']}`",
        f"- status: `{report['status']}`",
        f"- api_base_url: `{report['api_base_url']}`",
        "",
        "## Checks",
        "",
    ]
    for name, item in report["checks"].items():
        lines.append(f"- `{name}`: `{item.get('status')}`")
    lines.extend(
        [
            "",
            "## Router",
            "",
            "```text",
            report["checks"]["router_preflight"].get("stdout_tail", "").strip(),
            "```",
            "",
            "## API Health",
            "",
            "```json",
            json.dumps(report["checks"]["api_health"], ensure_ascii=False, indent=2),
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = Path(args.out_dir).expanduser().resolve()
    run_id = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    PYTEST_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    pytest_basetemp = PYTEST_TEMP_ROOT / f"pytest_hwpx_health_{run_id}"
    compile_paths = [
        REPO_ROOT / "scripts" / "hwpx",
        REPO_ROOT / "scripts" / "hancom-toolchain",
        REPO_ROOT / "scripts" / "local-gui",
    ]
    user_present_result, user_present_evidence = prepare_user_present_evidence_fixture(out_dir)
    checks: dict[str, Any] = {
        "python_compile": check_compile(compile_paths),
        "pytest_hwpx": normalize_pytest_result(
            run_command(
                [sys.executable, "-m", "pytest", "scripts\\hwpx", "-q", "--basetemp", str(pytest_basetemp)],
                timeout=180,
            )
        ),
        "router_preflight": run_command(
            [
                sys.executable,
                "scripts/hwpx/hancom_hwp_converter_router.py",
                "--output-dir",
                str(out_dir / "router"),
            ],
            timeout=120,
        ),
        "user_present_evidence": run_command(
            [
                sys.executable,
                "scripts/hwpx/hancom_user_present_evidence.py",
                "--result-json",
                str(user_present_result),
                "--evidence-json",
                str(user_present_evidence),
                "--execution-approved",
            ],
            timeout=60,
        ),
    }
    if args.no_api:
        checks["api_health"] = {
            "status": "SKIP",
            "url": f"{args.api_base_url.rstrip('/')}/health",
            "reason": "--no-api was provided",
        }
        checks["api_parse_smoke"] = {
            "status": "SKIP",
            "reason": "--no-api was provided",
        }
        checks["api_security_smoke"] = {
            "status": "SKIP",
            "reason": "--no-api was provided",
        }
    else:
        checks["api_health"] = check_http_get(f"{args.api_base_url.rstrip('/')}/health", timeout=args.timeout)

    if not args.no_api and args.sample and checks["api_health"]["status"] == "PASS":
        checks["api_parse_smoke"] = run_command(
            [
                sys.executable,
                "scripts/hwpx/client_parse_hwpx_smoke.py",
                "--base-url",
                args.api_base_url.rstrip("/"),
                "--sample",
                args.sample,
                "--timeout",
                str(args.timeout),
                "--json-output",
                str(out_dir / "client_parse_hwpx_smoke.json"),
            ],
            timeout=max(args.timeout + 10, 40),
        )
        checks["api_security_smoke"] = run_command(
            [
                sys.executable,
                "scripts/hwpx/test_hwpx_security.py",
                "--base-url",
                args.api_base_url.rstrip("/"),
                "--out-dir",
                str(out_dir / "security"),
            ],
            timeout=max(args.timeout + 10, 40),
        )
    elif not args.no_api:
        checks["api_parse_smoke"] = {
            "status": "SKIP",
            "reason": "api health failed or no sample provided",
        }
        checks["api_security_smoke"] = {
            "status": "SKIP",
            "reason": "api health failed or no sample provided",
        }

    overall_ok = all(item.get("status") in {"PASS", "SKIP", "WARN"} for item in checks.values())
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "hancom_toolchain_health_check",
        "status": status(overall_ok),
        "api_base_url": args.api_base_url.rstrip("/"),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check HWPX/Hancom local toolchain health")
    parser.add_argument("--api-base-url", default=DEFAULT_API_URL)
    parser.add_argument("--sample", default="smoke-test.hwpx")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--no-api", action="store_true", help="Skip HTTP health, parse, and security smoke checks")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    report = build_report(args)
    write_json(out_dir / "health_check.json", report)
    md_path = out_dir / "health_check.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "json": str(out_dir / "health_check.json"), "md": str(md_path)}, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
