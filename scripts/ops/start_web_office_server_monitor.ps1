param(
    [int]$Port = 8767,
    [int]$IntervalSeconds = 30,
    [string]$HostName = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$MonitorDir = Join-Path $ProjectRoot "data\audit\web_office_server_monitor"
$PidFile = Join-Path $MonitorDir "web_office_server_monitor.pid"
$LogFile = Join-Path $MonitorDir "web_office_server_monitor.log"
$ErrFile = Join-Path $MonitorDir "web_office_server_monitor.err.log"
$MonitorScript = Join-Path $ProjectRoot "scripts\ops\verify_web_office_server_monitor.py"

New-Item -ItemType Directory -Force -Path $MonitorDir | Out-Null

if (Test-Path $PidFile) {
    $ExistingPidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $ExistingPid = 0
    if ([int]::TryParse($ExistingPidText, [ref]$ExistingPid)) {
        $ExistingProcess = Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue
        if ($ExistingProcess) {
            $payload = [ordered]@{
                schemaVersion = "web_office_server_monitor_launcher_v1"
                verdict = "ALREADY_RUNNING"
                pid = $ExistingPid
                pidFile = "data/audit/web_office_server_monitor/web_office_server_monitor.pid"
                logFile = "data/audit/web_office_server_monitor/web_office_server_monitor.log"
            }
            $payload | ConvertTo-Json -Depth 8
            exit 0
        }
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$ArgsList = @(
    "scripts\ops\verify_web_office_server_monitor.py",
    "--host", $HostName,
    "--port", "$Port",
    "--interval", "$IntervalSeconds",
    "--project-root", "`"$ProjectRoot`""
)

$Process = Start-Process -FilePath "python" `
    -ArgumentList $ArgsList `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrFile `
    -PassThru

Set-Content -LiteralPath $PidFile -Value $Process.Id -Encoding UTF8

$payload = [ordered]@{
    schemaVersion = "web_office_server_monitor_launcher_v1"
    verdict = "STARTED"
    pid = $Process.Id
    port = $Port
    intervalSeconds = $IntervalSeconds
    pidFile = "data/audit/web_office_server_monitor/web_office_server_monitor.pid"
    logFile = "data/audit/web_office_server_monitor/web_office_server_monitor.log"
    errorLogFile = "data/audit/web_office_server_monitor/web_office_server_monitor.err.log"
}
$payload | ConvertTo-Json -Depth 8
