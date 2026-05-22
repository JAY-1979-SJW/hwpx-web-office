# HWPX API Connection Check

## Scope

Checked local HTTP API connectivity for the office-analysis-engine HWPX parser path.

## Initial State

Direct probes before server startup:

- `http://127.0.0.1:8080/health`: connection failed
- `http://127.0.0.1:8081/api/v1/health`: connection failed
- `http://127.0.0.1:8000/health`: connection failed

Port/process inspection using `Get-NetTCPConnection` was blocked by local permissions.

## Server Startup

The first Gradle startup attempt failed because the Gradle wrapper could not access the user-home Gradle lock file:

- path: `C:\Users\skyjw\.gradle\wrapper\dists\gradle-8.7-bin\...\gradle-8.7-bin.zip.lck`
- error: access denied

The server was then started with external execution approval.

A second startup attempt failed because `serve 8080` was not quoted correctly and Gradle interpreted `8080` as a task.

Final startup command shape:

```powershell
Start-Process -FilePath '.\gradlew.bat' -ArgumentList 'run "--args=serve 8080"'
```

## Fix Applied

To remove fragile Gradle argument quoting, a dedicated Gradle task was added:

```powershell
.\gradlew.bat serve -Pport=8080
```

Implementation:

- `build.gradle.kts`: added `tasks.register<JavaExec>("serve")`
- `README.md`: added `serve` and API smoke usage

The task calls `com.haehan.engine.Application` with arguments:

```text
serve <port>
```

where `<port>` defaults to `8080` and can be overridden with `-Pport=<port>`.

## Health Result

Endpoint:

```text
GET http://127.0.0.1:8080/health
```

Result:

```json
{
  "status": 200,
  "body": "{\"status\":\"ok\",\"engine\":\"office-analysis-engine\",\"version\":\"0.1.0\"}"
}
```

## Parse Smoke Result

Command:

```powershell
python scripts\hwpx\client_parse_hwpx_smoke.py --base-url http://127.0.0.1:8080 --sample smoke-test.hwpx --timeout 30 --json-output tmp\api_connection_check\client_parse_hwpx_smoke.json
```

Result:

- health: PASS
- parse: PASS
- schemaVersion: `1.0`
- engineVersion: `1.0.0`
- fullText: `smoke`
- paragraphs: `1`
- blocks: `1`
- tables: `0`
- warningCount: `0`
- errorCount: `0`
- ok: `true`

Output:

- `tmp/api_connection_check/client_parse_hwpx_smoke.json`

## Price Classifier Probe

Endpoint:

```text
GET http://127.0.0.1:8081/api/v1/health
```

Result:

- connection failed

This only means the local price-classifier service was not running during this check.

## Conclusion

The local HWPX parser API connection is working:

- server startup: PASS after corrected Gradle args
- `/health`: PASS
- `/parse-hwpx`: PASS

The price-classifier API was not running locally at `127.0.0.1:8081`.

## Fix Verification

Verification command:

```powershell
.\gradlew.bat serve -Pport=18080
python scripts\hwpx\client_parse_hwpx_smoke.py --base-url http://127.0.0.1:18080 --sample smoke-test.hwpx --timeout 30 --json-output tmp\api_connection_check\client_parse_hwpx_smoke_18080.json
```

Result:

- `GET /health`: PASS
- `POST /parse-hwpx`: PASS
- `ok`: `true`
- `fullText`: `smoke`
- `errorCount`: `0`

Additional verification:

- `.\gradlew.bat compileJava`: pass
