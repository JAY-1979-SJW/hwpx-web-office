param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$MonitorDir = Join-Path $ProjectRoot "data\audit\web_office_server_monitor"
$PidFile = Join-Path $MonitorDir "web_office_server_monitor.pid"

if (-not (Test-Path $PidFile)) {
    $payload = [ordered]@{
        schemaVersion = "web_office_server_monitor_launcher_v1"
        verdict = "NOT_RUNNING"
        reason = "pid file missing"
    }
    $payload | ConvertTo-Json -Depth 8
    exit 0
}

$PidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
$MonitorPid = 0
if (-not [int]::TryParse($PidText, [ref]$MonitorPid)) {
    Remove-Item -LiteralPath $PidFile -Force
    $payload = [ordered]@{
        schemaVersion = "web_office_server_monitor_launcher_v1"
        verdict = "STALE_PID_FILE_REMOVED"
        reason = "pid file did not contain an integer"
    }
    $payload | ConvertTo-Json -Depth 8
    exit 0
}

$Process = Get-Process -Id $MonitorPid -ErrorAction SilentlyContinue
if (-not $Process) {
    Remove-Item -LiteralPath $PidFile -Force
    $payload = [ordered]@{
        schemaVersion = "web_office_server_monitor_launcher_v1"
        verdict = "STALE_PID_FILE_REMOVED"
        pid = $MonitorPid
    }
    $payload | ConvertTo-Json -Depth 8
    exit 0
}

if ($Process.ProcessName -notmatch "python") {
    $payload = [ordered]@{
        schemaVersion = "web_office_server_monitor_launcher_v1"
        verdict = "REFUSED"
        reason = "pid is not a python process"
        pid = $MonitorPid
        processName = $Process.ProcessName
    }
    $payload | ConvertTo-Json -Depth 8
    exit 1
}

Stop-Process -Id $MonitorPid -Force:$Force
Remove-Item -LiteralPath $PidFile -Force

$payload = [ordered]@{
    schemaVersion = "web_office_server_monitor_launcher_v1"
    verdict = "STOPPED"
    pid = $MonitorPid
}
$payload | ConvertTo-Json -Depth 8
