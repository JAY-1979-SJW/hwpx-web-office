"""Read-only Web Office server security log baseline audit."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "web_office_security_log_audit_v1"
PASS_VERDICT = "PASS_WEB_OFFICE_SECURITY_LOG_AUDIT"
WARN_VERDICT = "WARN_WEB_OFFICE_SECURITY_LOG_AUDIT"
FAIL_VERDICT = "FAIL_WEB_OFFICE_SECURITY_LOG_AUDIT"

DEFAULT_LOG_CANDIDATES = [
    "/var/log/auth.log",
    "/var/log/secure",
    "/var/log/nginx/access.log",
    "/var/log/nginx/error.log",
    "/var/log/apache2/access.log",
    "/var/log/apache2/error.log",
    "data/audit/web_office_server_monitor/web_office_server_monitor.log",
    "data/audit/web_office_server_monitor/web_office_server_monitor.err.log",
]

SUSPICIOUS_PATTERNS = {
    "failed_password": re.compile(r"failed password", re.IGNORECASE),
    "invalid_user": re.compile(r"invalid user", re.IGNORECASE),
    "authentication_failure": re.compile(r"authentication failure", re.IGNORECASE),
    "permission_denied": re.compile(r"permission denied", re.IGNORECASE),
    "connection_refused": re.compile(r"connection refused|refused connect", re.IGNORECASE),
    "possible_breakin": re.compile(r"possible break-in|breakin", re.IGNORECASE),
    "http_4xx_5xx": re.compile(r'"\s(?:4\d\d|5\d\d)\s'),
    "structure_drift_detected": re.compile(r"STRUCTURE_DRIFT_DETECTED"),
    "monitor_down": re.compile(r'"verdict":\s*"(DOWN|BLOCKED_PORT_LISTENING|START_TIMEOUT)"'),
}


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _read_tail(path: Path, lines: int) -> tuple[str, str | None]:
    if not path.exists():
        return "", "MISSING"
    if not path.is_file():
        return "", "NOT_FILE"
    try:
        data = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except PermissionError:
        return "", "PERMISSION_DENIED"
    except OSError as exc:
        return "", f"READ_ERROR:{type(exc).__name__}"
    return "\n".join(data[-lines:]), None


def _journal_tail(unit: str | None, lines: int) -> dict[str, Any]:
    command = ["journalctl", "--no-pager", "-n", str(lines)]
    if unit:
        command.extend(["-u", unit])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True, encoding="utf-8", errors="replace",
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "reason": "JOURNALCTL_MISSING", "sample": ""}
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "JOURNALCTL_TIMEOUT", "sample": ""}
    if result.returncode != 0:
        return {
            "available": False,
            "reason": f"JOURNALCTL_EXIT_{result.returncode}",
            "stderr": result.stderr.strip()[:500],
            "sample": result.stdout[-2000:],
        }
    return {"available": True, "reason": None, "sample": result.stdout[-4000:]}


def _count_patterns(text: str) -> dict[str, int]:
    return {
        name: len(pattern.findall(text))
        for name, pattern in SUSPICIOUS_PATTERNS.items()
    }


def audit(
    *,
    project_root: Path = ROOT,
    tail_lines: int = 500,
    include_journal: bool = True,
) -> dict[str, Any]:
    project_root = project_root.resolve()
    log_results: list[dict[str, Any]] = []
    total_counts = {name: 0 for name in SUSPICIOUS_PATTERNS}
    warnings: list[dict[str, str]] = []

    for candidate in DEFAULT_LOG_CANDIDATES:
        raw_path = Path(candidate)
        is_system_log = candidate.startswith("/")
        path = raw_path if raw_path.is_absolute() else project_root / raw_path
        sample, warning = _read_tail(path, tail_lines)
        counts = _count_patterns(sample)
        for key, value in counts.items():
            total_counts[key] += value
        if warning:
            warnings.append({"code": warning, "log": candidate})
        safe_path = candidate if is_system_log else _safe_rel(path, project_root)
        log_results.append({
            "log": candidate,
            "safePath": safe_path,
            "available": warning is None,
            "warning": warning,
            "counts": counts,
        })

    journal_result: dict[str, Any] | None = None
    if include_journal:
        journal_result = _journal_tail(None, min(tail_lines, 300))
        if journal_result.get("available"):
            counts = _count_patterns(journal_result.get("sample", ""))
            for key, value in counts.items():
                total_counts[key] += value
            journal_result["counts"] = counts
        else:
            warnings.append({"code": journal_result.get("reason", "JOURNAL_UNAVAILABLE"), "log": "journalctl"})

    available_logs = sum(1 for item in log_results if item["available"])
    suspicious_total = sum(total_counts.values())
    verdict = PASS_VERDICT if suspicious_total == 0 else WARN_VERDICT
    return {
        "schemaVersion": SCHEMA_VERSION,
        "verdict": verdict,
        "checkedAt": datetime.now().isoformat(timespec="seconds"),
        "scope": "read_only_log_audit_no_firewall_change",
        "tailLines": tail_lines,
        "summary": {
            "logsChecked": len(log_results),
            "availableLogs": available_logs,
            "warnings": len(warnings),
            "suspiciousSignals": suspicious_total,
            "patternCounts": total_counts,
        },
        "logs": log_results,
        "journal": journal_result,
        "warnings": warnings,
        "holdItems": [
            "No firewall changes are made.",
            "No IP or port allowlist is changed.",
            "Suspicious signals are reported for review, not auto-blocked.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(ROOT))
    parser.add_argument("--tail-lines", type=int, default=500)
    parser.add_argument("--no-journal", dest="include_journal", action="store_false")
    parser.set_defaults(include_journal=True)
    args = parser.parse_args()
    payload = audit(
        project_root=Path(args.project_root),
        tail_lines=args.tail_lines,
        include_journal=args.include_journal,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["verdict"] in {PASS_VERDICT, WARN_VERDICT} else 1


if __name__ == "__main__":
    raise SystemExit(main())
