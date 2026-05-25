# Web Office Baseline Lock Precheck Report

Date: 2026-05-25
Task: WEB-OFFICE-BASELINE-LOCK-PRECHECK-20260525
Baseline candidate: `a3209b2`
Final status: SERVER_VERIFIED_PASS

## 1. Purpose

This report records the final server-side audit before locking the current Web
Office operational baseline.

No application code, firewall policy, IP allowlist, port exposure, or production
write behavior was changed during this audit.

## 2. Server Audit Results

Server: `haehan-app`
Server path: `/home/ubuntu/apps/hwpx-web-office`
Health endpoint: `http://127.0.0.1:8767/api/web-office/health`

| Check | Result |
| --- | --- |
| Web Office health | PASS (`SUCCESS`) |
| Runtime mode | PASS (`SANDBOX_ONLY`) |
| Source mutation block | PASS (`sourceMutationAllowed=false`) |
| Pipeline readiness | PASS |
| Monitor one-shot | PASS (`HEALTHY`) |
| App structure drift | PASS (`PASS_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT`) |
| Monitor process | PASS |
| Monitor `@reboot` cron | PASS |
| Security log audit | PASS (`PASS_WEB_OFFICE_SECURITY_LOG_AUDIT`) |
| Suspicious security signals | PASS (`0`) |
| Failed systemd units | PASS (`0 loaded units listed`) |
| Local repository status | PASS (`master...origin/master`) |

## 3. Commands Executed

```bash
cd /home/ubuntu/apps/hwpx-web-office
python3 scripts/ops/verify_web_office_server_monitor.py --once --port 8767 --include-structure-drift
```

Result: `HEALTHY`

```bash
pgrep -af 'verify_web_office_server_monitor.py.*--interval'
crontab -l | grep hwpx-web-office-monitor
```

Result: monitor process and `@reboot` registration present.

```bash
cd /home/ubuntu/apps/hwpx-web-office
python3 scripts/ops/audit_web_office_security_logs.py --tail-lines 5000
```

Result: `PASS_WEB_OFFICE_SECURITY_LOG_AUDIT`, suspicious signals `0`.

```bash
cd /home/ubuntu/apps/hwpx-web-office
python3 scripts/ops/audit_web_office_app_structure_drift.py
```

Result: `PASS_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT`.

```bash
systemctl --no-pager --failed
```

Result: `0 loaded units listed`.

```bash
curl -fsS http://127.0.0.1:8767/api/web-office/health
```

Result: `SUCCESS`, `SANDBOX_ONLY`, `sourceMutationAllowed=false`.

## 4. Warnings

The security log audit reported missing log warnings for:

- `/var/log/secure`
- `/var/log/apache2/access.log`
- `/var/log/apache2/error.log`

These are accepted warnings for the current Ubuntu/nginx server profile. The
available auth, nginx, monitor, and journal sources were checked and suspicious
signal count was `0`.

## 5. Hold Items

- Do not enable production write.
- Do not expose new public ports.
- Do not change firewall rules or IP allowlists without a separate approved
  task.
- Do not copy server secret files into this repository.

## 6. Lock Decision

The baseline candidate `a3209b2` is ready for baseline locking from the server
audit perspective.

Recommended next step:

1. Create a baseline lock commit if this report is not yet committed.
2. Create a baseline tag after the report commit is pushed.
3. Verify the tag and server state once more.
