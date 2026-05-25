# Web Office Server Error Remediation Report

Date: 2026-05-25
Task: WEB-OFFICE-SERVER-ERROR-REMEDIATION-20260525
Baseline head: 15f987a
Final status: SERVER_VERIFIED_PASS

## 1. Scope

This report records the server-side error check and remediation performed after
the Web Office baseline had already passed its own health checks.

The Web Office repository code was not changed during the server remediation.
The work corrected server runtime state and an adjacent operational repository
that was failing under systemd.

## 2. Findings

### FINDING-01: Price reference API restart loop

Service: `mart-price-reference-api.service`

Observed error:

- PostgreSQL connection attempted against stale Docker network coordinates.
- The service was repeatedly restarting before the correction.

Root cause:

- `/home/ubuntu/.secrets/price-reference-api.env` still pointed to an obsolete
  database endpoint and credential set.
- The actual `price_db` was present in the current `gongmu-db` container.

Resolution:

- Backed up the existing environment file on the server.
- Updated the environment file to the current `gongmu-db` endpoint and
  credential set.
- Restarted `mart-price-reference-api.service`.

Verification:

- `systemctl is-active mart-price-reference-api.service` returned `active`.
- `curl -fsS http://127.0.0.1:8195/health` returned `{"status":"ok"}`.

### FINDING-02: Risk assessment queue oneshot services failed

Services:

- `risk-assessment-enqueue-incremental.service`
- `risk-assessment-enqueue-remap.service`
- `risk-assessment-enqueue-kosha-redownload.service`

Observed error:

- `build_collection_queue.py` raised `NameError` for missing SQL constants.

Root cause:

- A prior refactor in the adjacent `risk-assessment-generator` repository
  removed local SQL constant definitions while moving DB connection helpers.

Resolution:

- Restored the queue builder SQL constants.
- Verified dry-run mode for all three timer paths.
- Started the three oneshot services successfully.
- Committed and pushed the fix to GitHub:
  `7eb8d2a5 fix(ops): restore collection queue SQL constants`
- Reset the server checkout to `origin/master` so the server and GitHub
  baseline match.

Verification:

- `docker exec risk-assessment-api python3 /app/scripts/ops/build_collection_queue.py --dry-run --only incremental` passed.
- `docker exec risk-assessment-api python3 /app/scripts/ops/build_collection_queue.py --dry-run --only remap` passed.
- `docker exec risk-assessment-api python3 /app/scripts/ops/build_collection_queue.py --dry-run --only kosha_redownload` passed.

## 3. Web Office Verification

Commands:

```bash
systemctl --no-pager --failed
systemctl is-active mart-price-reference-api.service
curl -fsS http://127.0.0.1:8195/health
curl -fsS http://127.0.0.1:8767/api/web-office/health
```

Results:

- failed systemd units: `0 loaded units listed`
- price reference API: `active`
- price reference API health: `{"status":"ok"}`
- Web Office health: `SUCCESS`
- Web Office mode: `SANDBOX_ONLY`
- Web Office source mutation: `false`

## 4. Operational Rule Update

The operating baseline now treats server failed units as part of the Web Office
server verification gate.

For Web Office completion, local repository tests are not enough. The server
must also show:

- Web Office health success
- monitor and recovery path present
- security and structure checks available
- `systemctl --failed` with zero failed units
- adjacent operational services checked when they affect server readiness

## 5. Hold Items

- The price reference API environment file contains server secrets and remains
  server-only. It is intentionally not copied into this repository.
- The `risk-assessment-generator` fix is recorded in that repository, not this
  Web Office repository.

## 6. Final Decision

The server is clean at the time of this report.

The current server state can be used as an operationally verified baseline after
this report and the operating-rule update are committed.
