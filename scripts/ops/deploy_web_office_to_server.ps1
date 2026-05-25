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
$FixtureCorpusDir = Join-Path $ProjectRoot "tests\fixtures\hwpx\corpus"
$RemoteFixtureCorpusDir = "$ServerPath/tests/fixtures/hwpx/corpus"

New-Item -ItemType Directory -Force -Path $BundleDir | Out-Null

$head = (Invoke-Checked -FilePath "git" -Arguments @("rev-parse", "--short", "HEAD") -Step "git head").stdout.Trim()
$status = (Invoke-Checked -FilePath "git" -Arguments @("status", "--porcelain") -Step "git status").stdout
if (-not $SkipLocalStatusCheck -and $status.Trim()) {
    throw "working tree is not clean; commit or stash changes before server deploy"
}

$fixtureFiles = @(Get-ChildItem -Path $FixtureCorpusDir -Filter "*.hwpx" -File | Sort-Object Name)
if ($fixtureFiles.Count -lt 1) {
    throw "fixture corpus has no .hwpx files: $FixtureCorpusDir"
}

Invoke-Checked -FilePath "git" -Arguments @("archive", "--format=tar", "-o", $ArchivePath, "HEAD") -Step "git archive" | Out-Null
Invoke-Checked -FilePath "scp" -Arguments @($ArchivePath, "${ServerAlias}:${RemoteArchive}") -Step "scp archive" | Out-Null
Invoke-Checked -FilePath "ssh" -Arguments @($ServerAlias, "mkdir", "-p", $RemoteFixtureCorpusDir) -Step "server fixture dir" | Out-Null
$fixtureScpArgs = @()
foreach ($fixture in $fixtureFiles) {
    $fixtureScpArgs += $fixture.FullName
}
$fixtureScpArgs += "${ServerAlias}:${RemoteFixtureCorpusDir}/"
Invoke-Checked -FilePath "scp" -Arguments $fixtureScpArgs -Step "scp fixture corpus" | Out-Null

$serverScript = @"
set -e
mkdir -p "$ServerPath"
tar -xf "$RemoteArchive" -C "$ServerPath"
cd "$ServerPath"
python3 -m py_compile scripts/ops/verify_web_office_server_monitor.py scripts/ops/install_web_office_server_monitor_cron.py scripts/ops/audit_web_office_app_structure_drift.py scripts/ops/audit_web_office_hwpx_read_remediation.py scripts/ops/verify_web_office_editor_backend_runtime_smoke.py
python3 scripts/ops/install_web_office_server_monitor_cron.py --port $Port --interval 30
python3 scripts/ops/verify_web_office_server_monitor.py --once --port $Port --include-structure-drift
python3 scripts/ops/audit_web_office_app_structure_drift.py
python3 scripts/ops/audit_web_office_hwpx_read_remediation.py --no-write
python3 scripts/ops/verify_web_office_editor_backend_runtime_smoke.py
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
$structureDriftOk = $serverOutput -match '"verdict":\s*"PASS_WEB_OFFICE_APP_STRUCTURE_DRIFT_AUDIT"'
$monitorIncludesStructureDriftOk = $serverOutput -match "--include-structure-drift"
$monitorProcessOk = $serverOutput -match "python3 scripts/ops/verify_web_office_server_monitor.py --interval"
$monitorCronOk = $serverOutput -match "hwpx-web-office-monitor"
$ruleOk = $serverOutput -match "RULE-13"
$operationalRuleOk = $serverOutput -match "Operational Completion Rule"
$remediationAuditOk = $serverOutput -match "PASS_WEB_OFFICE_HWPX_READ_REMEDIATION_CURRENT_SCOPE"
$runtimeSmokeOk = $serverOutput -match "PASS_HWPX_EDITOR_BACKEND_RUNTIME_SMOKE"
$fixtureCorpusOk = $serverOutput -match '"hwpxFileCount":\s*5'
$unsupportedCategoryOk = $serverOutput -match '"unsupportedCategorySummary"'

if (-not ($healthOk -and $sandboxOk -and $mutationOk -and $structureDriftOk -and $monitorIncludesStructureDriftOk -and $monitorProcessOk -and $monitorCronOk -and $ruleOk -and $operationalRuleOk -and $remediationAuditOk -and $runtimeSmokeOk -and $fixtureCorpusOk -and $unsupportedCategoryOk)) {
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
        fixtureCorpusFilesSynced = $fixtureFiles.Count
        serverHealthOk = $healthOk
        serverSandboxModeOk = $sandboxOk
        serverMutationBlockedOk = $mutationOk
        serverStructureDriftOk = $structureDriftOk
        serverHwpxReadRemediationAuditOk = $remediationAuditOk
        serverBackendRuntimeSmokeOk = $runtimeSmokeOk
        serverFixtureCorpusOk = $fixtureCorpusOk
        serverUnsupportedCategorySummaryOk = $unsupportedCategoryOk
        serverMonitorIncludesStructureDriftOk = $monitorIncludesStructureDriftOk
        serverMonitorProcessOk = $monitorProcessOk
        serverMonitorCronOk = $monitorCronOk
        serverOperatingRulePresent = $ruleOk
        serverBackendStandardPresent = $operationalRuleOk
    }
}

$payload | ConvertTo-Json -Depth 8
