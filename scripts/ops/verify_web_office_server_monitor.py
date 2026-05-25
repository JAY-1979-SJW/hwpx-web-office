"""Monitor and recover the local Web Office backend server.

Default behavior is intentionally conservative:
- check the Web Office health endpoint;
- if healthy, report HEALTHY;
- if down and the configured port is free, start uvicorn;
- if the port is occupied but health is bad, do not kill the process.

Use this for the local sandbox server, not production deployment.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8767
SCHEMA_VERSION = "web_office_server_monitor_v1"
PASS_HEALTHY = "HEALTHY"
PASS_RECOVERED = "RECOVERED"
FAIL_DOWN = "DOWN"
FAIL_BLOCKED = "BLOCKED_PORT_LISTENING"
FAIL_START_TIMEOUT = "START_TIMEOUT"


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/api/web-office/health"


def _request_json(url: str, *, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _check_health(host: str, port: int, timeout: float) -> dict[str, Any]:
    url = _health_url(host, port)
    try:
        payload = _request_json(url, timeout=timeout)
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "url": url,
            "error": f"{type(exc).__name__}: {exc}",
            "payload": None,
        }
    data = payload.get("data") or {}
    checks = {
        "statusSuccess": payload.get("status") == "SUCCESS",
        "sandboxMode": payload.get("mode") == "SANDBOX_ONLY",
        "sourceMutationBlocked": payload.get("sourceMutationAllowed") is False,
        "pipelineReady": data.get("pipelineReady") is True,
    }
    return {
        "ok": all(checks.values()),
        "url": url,
        "checks": checks,
        "payload": payload,
    }


def _port_listening(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _monitor_dir(project_root: Path) -> Path:
    return project_root / "data" / "audit" / "web_office_server_monitor"


def _output_dir(project_root: Path) -> Path:
    return project_root / "data" / "audit" / "web_office_server_outputs"


def _start_server(
    *,
    project_root: Path,
    host: str,
    port: int,
) -> dict[str, Any]:
    mon_dir = _monitor_dir(project_root)
    mon_dir.mkdir(parents=True, exist_ok=True)
    out_dir = _output_dir(project_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = mon_dir / f"web_office_server_{port}_{stamp}.log"
    pid_path = mon_dir / f"web_office_server_{port}.pid"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)
    env["HWPX_WEB_OFFICE_API_OUTPUT_DIR"] = str(out_dir)
    log_handle = log_path.open("a", encoding="utf-8")
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "scripts.hwpx.web_office.editor_api_route:app",
            "--host",
            host,
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(project_root),
        env=env,
        stdout=log_handle,
        stderr=log_handle,
        creationflags=creationflags,
    )
    log_handle.close()
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    return {
        "pid": proc.pid,
        "pidFile": str(pid_path.relative_to(project_root)),
        "logFile": str(log_path.relative_to(project_root)),
        "outputDir": str(out_dir.relative_to(project_root)),
    }


def check_and_recover(args: argparse.Namespace) -> dict[str, Any]:
    project_root = Path(args.project_root).resolve()
    health = _check_health(args.host, args.port, args.timeout)
    if health["ok"]:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "verdict": PASS_HEALTHY,
            "host": args.host,
            "port": args.port,
            "health": health,
            "recovery": None,
        }

    listening = _port_listening(args.host, args.port)
    if not args.recover:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "verdict": FAIL_DOWN,
            "host": args.host,
            "port": args.port,
            "health": health,
            "portListening": listening,
            "recovery": {"attempted": False},
        }

    if listening:
        return {
            "schemaVersion": SCHEMA_VERSION,
            "verdict": FAIL_BLOCKED,
            "host": args.host,
            "port": args.port,
            "health": health,
            "portListening": True,
            "recovery": {
                "attempted": False,
                "reason": "port is occupied but health check failed",
            },
        }

    recovery = _start_server(
        project_root=project_root,
        host=args.host,
        port=args.port,
    )
    deadline = time.monotonic() + args.start_timeout
    recovered_health: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        time.sleep(args.poll_delay)
        recovered_health = _check_health(args.host, args.port, args.timeout)
        if recovered_health["ok"]:
            return {
                "schemaVersion": SCHEMA_VERSION,
                "verdict": PASS_RECOVERED,
                "host": args.host,
                "port": args.port,
                "health": recovered_health,
                "recovery": {"attempted": True, **recovery},
            }

    return {
        "schemaVersion": SCHEMA_VERSION,
        "verdict": FAIL_START_TIMEOUT,
        "host": args.host,
        "port": args.port,
        "health": recovered_health or health,
        "recovery": {"attempted": True, **recovery},
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Monitor and recover the local Web Office backend server.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--poll-delay", type=float, default=0.5)
    parser.add_argument("--start-timeout", type=float, default=30.0)
    parser.add_argument("--max-checks", type=int, default=0,
                        help="0 means run until interrupted.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-recover", dest="recover", action="store_false")
    parser.set_defaults(recover=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    checks = 0
    while True:
        checks += 1
        payload = check_and_recover(args)
        payload["checkNumber"] = checks
        payload["checkedAt"] = datetime.now().isoformat(timespec="seconds")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(payload["verdict"], flush=True)
        if args.once or (args.max_checks and checks >= args.max_checks):
            return 0 if payload["verdict"] in {PASS_HEALTHY, PASS_RECOVERED} else 1
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
