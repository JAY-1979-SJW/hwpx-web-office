"""Install the Web Office server monitor as an @reboot cron job.

This installer is intended for the Linux app server. It only edits the current
user's crontab and does not require root.
"""
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MARKER = "hwpx-web-office-monitor"


def _current_crontab() -> list[str]:
    result = subprocess.run(
        ["crontab", "-l"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def _install(lines: list[str]) -> None:
    payload = "\n".join(lines).rstrip() + "\n"
    subprocess.run(
        ["crontab", "-"],
        input=payload,
        text=True,
        check=True,
    )


def build_reboot_line(project_root: Path, port: int, interval: int) -> str:
    monitor_log = "data/audit/web_office_server_monitor/web_office_server_monitor.log"
    monitor_err = "data/audit/web_office_server_monitor/web_office_server_monitor.err.log"
    return (
        "@reboot /usr/bin/flock -n /tmp/hwpx_web_office_monitor.lock "
        "bash -lc "
        f"'cd {project_root} && "
        "mkdir -p data/audit/web_office_server_monitor && "
        "python3 scripts/ops/verify_web_office_server_monitor.py "
        f"--interval {interval} --port {port} "
        f">> {monitor_log} 2>> {monitor_err}' "
        f"# {MARKER}"
    )


def install(project_root: Path, port: int, interval: int) -> dict:
    project_root = project_root.resolve()
    line = build_reboot_line(project_root, port, interval)
    existing = [
        item for item in _current_crontab()
        if MARKER not in item
    ]
    existing.append(line)
    _install(existing)
    return {
        "schemaVersion": "web_office_server_monitor_cron_installer_v1",
        "verdict": "INSTALLED",
        "marker": MARKER,
        "projectRoot": str(project_root),
        "port": port,
        "interval": interval,
        "line": line,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    import json
    payload = install(Path(args.project_root), args.port, args.interval)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
