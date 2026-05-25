param(
    [string]$ServerAlias = "haehan-app",
    [string]$ServerPath = "/home/ubuntu/apps/hwpx-web-office",
    [int]$Port = 8767,
    [switch]$SkipLocalStatusCheck
)

$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$Step
    )

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $FilePath
    $escaped = @()
    foreach ($arg in $Arguments) {
        if ($arg -match '[\s"]') {
            $escaped += '"' + ($arg -replace '"', '\"') + '"'
        } else {
            $escaped += $arg
        }
    }
    $psi.Arguments = ($escaped -join " ")
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    [void]$proc.Start()
    $stdout = $proc.StandardOutput.ReadToEnd()
    $stderr = $proc.StandardError.ReadToEnd()
    $proc.WaitForExit()
    if ($proc.ExitCode -ne 0) {
        throw "$Step failed with exit code $($proc.ExitCode)`nSTDOUT:`n$stdout`nSTDERR:`n$stderr"
    }
    return @{
        stdout = $stdout
        stderr = $stderr
        exitCode = $proc.ExitCode
    }
}

$ScriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptPath "..\..")
$BundleDir = Join-Path $ProjectRoot "data\audit\deploy_bundle"
$ArchivePath = Join-Path $BundleDir "hwpx-web-office.tar"
$RemoteArchive = "/home/ubuntu/apps/hwpx-web-office.tar"

New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null

$head = (Invoke-Checked -FilePath "git" -Arguments @("rev-parse", "--short", "HEAD") -Step "git head").stdout.Trim()
$status = (Invoke-Checked -FilePath "git" -Arguments @("status", "--porcelain") -Step "git status").stdout
if (-not $SkipLocalStatusCheck -and $status.Trim()) {
    throw "working tree is not clean; commit or stash changes before server deploy"
}

Invoke-Checked -FilePath "git" -Arguments @("archive", "--format=tar", "-o", $ArchivePath, "HEAD") -Step "git archive" | Out-Null
Invoke-Checked -FilePath "scp" -Arguments @($ArchivePath, "${ServerAlias}:${RemoteArchive}") -Step "scp archive" | Out-Null

$serverScript = @"
set -e
mkdir -p "$ServerPath"
tar -xf "$RemoteArchive" -C "$ServerPath"
cd "$ServerPath"
python3 -m py_compile scripts/ops/verify_web_office_server_monitor.py scripts/ops/install_web_office_server_monitor_cron.py
python3 scripts/ops/verify_web_office_server_monitor.py --once --port $Port
pgrep -af 'python3 scripts/ops/verify_web_office_server_monitor.py --interval' | grep -v 'bash -lc' >/tmp/hwpx-web-office-monitor-process.txt
crontab -l | grep 'hwpx-web-office-monitor' >/tmp/hwpx-web-office-monitor-cron.txt
cat /tmp/hwpx-web-office-monitor-process.txt
cat /tmp/hwpx-web-office-monitor-cron.txt
grep -n 'RULE-13' docs/architecture/hwpx_work_execution_operating_rules_20260524.md
grep -n 'Operational Completion Rule' docs/architecture/web_office_backend_structure_standard_20260525.md
"@

$serverResult = Invoke-Checked -FilePath "ssh" -Arguments @($ServerAlias, "bash", "-lc", $serverScript) -Step "server deploy verify"
$serverOutput = $serverResult.stdout

$healthOk = $serverOutput -match '"verdict":\s*"(HEALTHY|RECOVERED)"'
$sandboxOk = $serverOutput -match '"sandboxMode":\s*true'
$mutationOk = $serverOutput -match '"sourceMutationBlocked":\s*true'
$monitorProcessOk = $serverOutput -match "python3 scripts/ops/verify_web_office_server_monitor.py --interval"
$monitorCronOk = $serverOutput -match "hwpx-web-office-monitor"
$ruleOk = $serverOutput -match "RULE-13"
$operationalRuleOk = $serverOutput -match "Operational Completion Rule"

if (-not ($healthOk -and $sandboxOk -and $mutationOk -and $monitorProcessOk -and $monitorCronOk -and $ruleOk -and $operationalRuleOk)) {
    throw "server validation output did not contain required pass signals`n$serverOutput"
}

$payload = [ordered]@{
    schemaVersion = "web_office_server_deploy_verify_v1"
    verdict = "PASS"
    serverAlias = $ServerAlias
    serverPath = $ServerPath
    port = $Port
    deployedHead = $head
    checks = [ordered]@{
        localWorkingTreeClean = -not $status.Trim()
        archiveCreated = Test-Path $ArchivePath
        serverHealthOk = $healthOk
        serverSandboxModeOk = $sandboxOk
        serverMutationBlockedOk = $mutationOk
        serverMonitorProcessOk = $monitorProcessOk
        serverMonitorCronOk = $monitorCronOk
        serverOperatingRulePresent = $ruleOk
        serverBackendStandardPresent = $operationalRuleOk
    }
}

$payload | ConvertTo-Json -Depth 8
