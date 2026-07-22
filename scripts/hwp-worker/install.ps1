#Requires -Version 5.1
<#
.SYNOPSIS
  Haehan HwpWorker local installer POC.
  Hancom COM is 32-bit only. All COM/self-test operations are delegated to a 32-bit child process.
  install.ps1 itself may run in 64-bit PowerShell.
  Does NOT register Task Scheduler without explicit user approval.
.PARAMETER SelfTestHwpPath
  Path to a sample HWP file for self-test.
.PARAMETER InstallBase
  Installation root. Default: %LOCALAPPDATA%\Haehan\HwpWorker
.PARAMETER DryRun
  Skip all write operations (folder creation, config write).
#>
param(
  [string]$SelfTestHwpPath = "",
  [string]$InstallBase     = "$env:LOCALAPPDATA\Haehan\HwpWorker",
  [switch]$DryRun
)

Set-StrictMode -Off
$ErrorActionPreference = "SilentlyContinue"
Add-Type -Assembly System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

$Result = [ordered]@{
  ok                     = $false
  installMode            = "DISABLED_CLIENT"
  installBase            = $InstallBase
  dryRun                 = [bool]$DryRun
  errorCode              = $null
  errorMessage           = $null
  warnings               = [System.Collections.Generic.List[string]]::new()
  windowsVersion         = $null
  psVersion              = $null
  ps32BitPath            = $null
  installerBitness       = $null
  hancomArchitecture     = "x86"
  powershellBitness      = 32
  comPolicy              = "HANCOM_32BIT_ONLY"
  hancomInstallPath      = $null
  hancomExeVersion       = $null
  hancomComProgId        = $null
  viewerOnly             = $false
  setMessageBoxModeOk    = $false
  registerModuleOk       = $false
  selfTestHwpPath        = $null
  selfTestHwpxPath       = $null
  selfTestOutputSize     = 0
  selfTestZipEntries     = 0
  selfTestInputUnchanged = $false
  selfTestOwnedPidGone   = $false
  selfTestPassed         = $false
  versionSupportedByName = $null
  installDirCreated      = $false
  configWritten          = $false
  taskSchedulerCommand   = $null
  taskSchedulerStatus    = "NOT_REGISTERED"
  installResultPath      = $null
}

function Add-Warn($msg) { $Result.warnings.Add($msg) }

function Write-Result {
  $outJson = $Result | ConvertTo-Json -Depth 5 -Compress
  Write-Output $outJson
  if ($Result.installResultPath -and -not $DryRun) {
    try { $outJson | Out-File -FilePath $Result.installResultPath -Encoding utf8 -Force } catch {}
  }
}

function Fail($code, $msg) {
  $Result.errorCode    = $code
  $Result.errorMessage = $msg
  $Result.ok           = $false
  Write-Result
  exit 1
}

# --- 1. Environment info ---

$Result.windowsVersion   = [System.Environment]::OSVersion.VersionString
$Result.psVersion        = $PSVersionTable.PSVersion.ToString()
$Result.installerBitness = if ([System.Environment]::Is64BitProcess) { 64 } else { 32 }

if ($PSVersionTable.PSVersion.Major -lt 5) {
  Fail "POWERSHELL_BLOCKED" "PowerShell 5.1+ required. Current: $($Result.psVersion)"
}

# --- 2. Locate 32-bit PowerShell ---

$ps32 = "$env:WINDIR\SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $ps32)) {
  # Fallback: same-dir if already 32-bit
  if (-not [System.Environment]::Is64BitProcess) {
    $ps32 = (Get-Process -Id $PID).MainModule.FileName
  }
}
if (-not (Test-Path $ps32)) {
  Fail "POWERSHELL_32BIT_NOT_FOUND" "32-bit PowerShell not found at: $ps32"
}
$Result.ps32BitPath = $ps32

# Verify it is actually 32-bit
$bitnessCheck = & $ps32 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command {
  if ([System.Environment]::Is64BitProcess) { "64" } else { "32" }
}
if ($bitnessCheck -ne "32") {
  Fail "POWERSHELL_32BIT_NOT_FOUND" "Expected 32-bit PS at $ps32 but got: $bitnessCheck"
}

# --- 3. Hancom install detection (installer process, any bitness) ---

$hwpExe = $null
$hwpSearchPatterns = @(
  "$env:ProgramFiles\HNC\Hwp*\Hwp.exe",
  "${env:ProgramFiles(x86)}\HNC\Hwp*\Hwp.exe",
  "$env:ProgramFiles\Hancom\Hwp*\Hwp.exe",
  "${env:ProgramFiles(x86)}\Hancom\Hwp*\Hwp.exe",
  "$env:ProgramFiles\HNC\Office*\HOffice*\Bin\Hwp.exe",
  "${env:ProgramFiles(x86)}\HNC\Office*\HOffice*\Bin\Hwp.exe"
)
foreach ($pat in $hwpSearchPatterns) {
  $found = Get-Item $pat -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($found) { $hwpExe = $found.FullName; break }
}
if (-not $hwpExe) {
  foreach ($rp in @("HKLM:\SOFTWARE\HNC\HwpFrame","HKLM:\SOFTWARE\WOW6432Node\HNC\HwpFrame","HKCU:\SOFTWARE\HNC\HwpFrame")) {
    $val = (Get-ItemProperty $rp -ErrorAction SilentlyContinue).InstallPath
    if ($val -and (Test-Path (Join-Path $val "Hwp.exe"))) {
      $hwpExe = Join-Path $val "Hwp.exe"; break
    }
  }
}
if (-not $hwpExe) {
  Fail "HANCOM_NOT_INSTALLED" "Hwp.exe not found. Install Hancom Office first."
}

$Result.hancomInstallPath = Split-Path $hwpExe -Parent
try { $Result.hancomExeVersion = (Get-Item $hwpExe).VersionInfo.FileVersion } catch { $Result.hancomExeVersion = "unknown" }
if ($Result.hancomExeVersion -match "^(\d+)") {
  $Result.versionSupportedByName = "reference-only(major=$($Matches[1])): judgment is self-test result only"
}

# --- 4. COM check via 32-bit child process ---

$comCheckScript = {
  $ErrorActionPreference = "Stop"
  $progId = $null
  $hwp    = $null
  foreach ($id in @("HwpFrame.HwpObject.2","HwpFrame.HwpObject")) {
    try { $hwp = New-Object -ComObject $id -ErrorAction Stop; $progId = $id; break } catch {}
  }
  if (-not $hwp) {
    Write-Output "FAIL:HANCOM_COM_UNAVAILABLE"
    exit 1
  }
  $msgBoxOk = $false
  try { $hwp.SetMessageBoxMode(65535) | Out-Null; $msgBoxOk = $true } catch {}
  $regModOk = $false
  try { $hwp.RegisterModule("FilePathCheckDLL","SecurityModule") | Out-Null; $regModOk = $true } catch {}
  try { $hwp.Quit() } catch {}
  try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
  [System.GC]::Collect()
  [System.GC]::WaitForPendingFinalizers()
  [System.GC]::Collect()
  Write-Output "OK:${progId}:${msgBoxOk}:${regModOk}"
}

$comCheckRaw = & $ps32 -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command $comCheckScript

if ($comCheckRaw -match "^FAIL:(.+)") {
  Fail "HANCOM_COM_UNAVAILABLE" "32-bit COM check failed: $($Matches[1]). Viewer-only or COM not registered."
}
if ($comCheckRaw -match "^OK:([^:]+):([^:]+):(.+)") {
  $Result.hancomComProgId     = $Matches[1]
  $Result.setMessageBoxModeOk = ($Matches[2] -eq "True")
  $Result.registerModuleOk    = ($Matches[3] -eq "True")
} else {
  Fail "HANCOM_COM_UNAVAILABLE" "Unexpected COM check output: $comCheckRaw"
}

if (-not $Result.registerModuleOk) {
  Add-Warn "RegisterModule failed in COM check — will retry in self-test"
}

# --- 5. Self-test HWP selection ---

$selfTestHwp = $SelfTestHwpPath
if (-not $selfTestHwp -or -not (Test-Path $selfTestHwp)) {
  $scriptDir  = Split-Path $MyInvocation.MyCommand.Path -Parent
  $candidates = @(
    (Join-Path $scriptDir "selftest\test.hwp"),
    (Join-Path $scriptDir "test.hwp"),
    "C:\Users\skyjw\AppData\Local\Temp\hancom_hwpx_poc\sample_input.hwp"
  )
  foreach ($c in $candidates) { if (Test-Path $c) { $selfTestHwp = $c; break } }
}
if (-not $selfTestHwp -or -not (Test-Path $selfTestHwp)) {
  Fail "SELF_TEST_SAMPLE_MISSING" "No self-test HWP found. Provide -SelfTestHwpPath or place test.hwp in selftest\ folder."
}

$Result.selfTestHwpPath  = $selfTestHwp
$tmpName                 = "haehan_selftest_$([System.Guid]::NewGuid().ToString('N').Substring(0,8)).hwpx"
$selfTestHwpxPath        = Join-Path ([System.IO.Path]::GetTempPath()) $tmpName
$Result.selfTestHwpxPath = $selfTestHwpxPath
$originalLwt             = (Get-Item $selfTestHwp).LastWriteTime

# --- 6. Self-test via 32-bit child (inline Convert-HwpToHwpx-v2 logic) ---

$converterScript = Join-Path (Split-Path $MyInvocation.MyCommand.Path -Parent) "Convert-HwpToHwpx-v2.ps1"

if (Test-Path $converterScript) {
  # Delegate to Convert-HwpToHwpx-v2.ps1 via 32-bit PS
  $selfTestRaw = & $ps32 -NoProfile -NonInteractive -ExecutionPolicy Bypass `
    -File $converterScript `
    -InputPath $selfTestHwp `
    -OutputPath $selfTestHwpxPath `
    -TimeoutSec 90 `
    -JobId "selftest-install"
  try {
    $stj = $selfTestRaw | ConvertFrom-Json
    if (-not $stj.ok) {
      Fail "SELF_TEST_FAILED" "Self-test conversion failed: $($stj.errorCode) — $($stj.errorMessage)"
    }
    $Result.selfTestOutputSize   = $stj.outputSize
    $Result.selfTestZipEntries   = $stj.zipEntries
    $Result.selfTestOwnedPidGone = $stj.ownedGoneClean
    if ($stj.warningCount -gt 0) {
      foreach ($w in $stj.warnings) { Add-Warn "self-test: $w" }
    }
  } catch {
    Fail "SELF_TEST_FAILED" "Self-test output parse error: $_ / raw: $selfTestRaw"
  }
} else {
  # Inline fallback (no converter script present yet)
  Add-Warn "Convert-HwpToHwpx-v2.ps1 not found alongside installer — running inline self-test"

  $inlineScript = [scriptblock]::Create(@'
param($hwpIn, $hwpxOut)
$ErrorActionPreference = "SilentlyContinue"
Add-Type -Assembly System.IO.Compression.FileSystem -ErrorAction SilentlyContinue
$beforePids = @(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$hwp = $null
try { $hwp = New-Object -ComObject HwpFrame.HwpObject.2 -ErrorAction Stop } catch {
  try { $hwp = New-Object -ComObject HwpFrame.HwpObject -ErrorAction Stop } catch {
    Write-Output "FAIL:SELF_TEST_OPEN_FAILED:COM_CREATE"
    exit 1
  }
}
Start-Sleep -Milliseconds 500
$afterPids = @(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
$ownedPids = @($afterPids | Where-Object { $_ -notin $beforePids })
try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
try { $hwp.SetMessageBoxMode(65535) | Out-Null } catch {}
try { $hwp.RegisterModule("FilePathCheckDLL","SecurityModule") | Out-Null } catch {}
try {
  $hwp.Open($hwpIn, "", "forceopen:true;versionwarning:false;lock:false;") | Out-Null
} catch {
  try { $hwp.Quit() } catch {}
  try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
  [System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers(); [System.GC]::Collect()
  Write-Output "FAIL:SELF_TEST_OPEN_FAILED:$_"
  exit 1
}
try {
  $hwp.SaveAs($hwpxOut, "HWPX", "") | Out-Null
} catch {
  try { $hwp.Clear(1); $hwp.Quit() } catch {}
  try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
  [System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers(); [System.GC]::Collect()
  Write-Output "FAIL:SELF_TEST_SAVEAS_FAILED:$_"
  exit 1
}
try { $hwp.Clear(1) } catch {}
try { $hwp.Quit() } catch {}
try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($hwp) | Out-Null } catch {}
[System.GC]::Collect(); [System.GC]::WaitForPendingFinalizers(); [System.GC]::Collect()
$deadline = (Get-Date).AddSeconds(5)
$gone = $false
while ((Get-Date) -lt $deadline) {
  if (@(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Where-Object { $_.Id -in $ownedPids }).Count -eq 0) { $gone = $true; break }
  Start-Sleep -Milliseconds 300
}
if (-not (Test-Path $hwpxOut)) { Write-Output "FAIL:HWPX_VERIFY_FAILED:not_created"; exit 1 }
$sz = (Get-Item $hwpxOut).Length
$entries = 0
try { $z = [System.IO.Compression.ZipFile]::OpenRead($hwpxOut); $entries = $z.Entries.Count; $z.Dispose() } catch {}
Write-Output "OK:${sz}:${entries}:${gone}"
'@)

  $selfTestRaw = & $ps32 -NoProfile -NonInteractive -ExecutionPolicy Bypass `
    -Command $inlineScript -hwpIn $selfTestHwp -hwpxOut $selfTestHwpxPath

  if ($selfTestRaw -match "^FAIL:([^:]+):(.*)") {
    Fail "SELF_TEST_FAILED" "Inline self-test: $($Matches[1]) — $($Matches[2])"
  }
  if ($selfTestRaw -match "^OK:(\d+):(\d+):(\w+)") {
    $Result.selfTestOutputSize   = [int]$Matches[1]
    $Result.selfTestZipEntries   = [int]$Matches[2]
    $Result.selfTestOwnedPidGone = ($Matches[3] -eq "True")
  } else {
    Fail "SELF_TEST_FAILED" "Inline self-test unexpected output: $selfTestRaw"
  }
}

# --- 7. HWPX verify (installer side) ---

if (-not (Test-Path $selfTestHwpxPath)) {
  Fail "HWPX_VERIFY_FAILED" "Self-test HWPX not found at: $selfTestHwpxPath"
}
if ($Result.selfTestOutputSize -lt 1000) {
  Fail "HWPX_VERIFY_FAILED" "HWPX too small: $($Result.selfTestOutputSize) bytes"
}
if ($Result.selfTestZipEntries -lt 3) {
  Add-Warn "HWPX ZIP entries low: $($Result.selfTestZipEntries)"
}

$currentLwt = (Get-Item $selfTestHwp).LastWriteTime
$Result.selfTestInputUnchanged = ($currentLwt -eq $originalLwt)
if (-not $Result.selfTestInputUnchanged) {
  Add-Warn "Source HWP LastWriteTime changed: before=$originalLwt after=$currentLwt"
}

$Result.selfTestPassed = $true

# --- 8. Create install directories ---

if (-not $DryRun) {
  $allDirs = @($InstallBase) + (@("bin","scripts","config","logs","temp","selftest","updates") | ForEach-Object { Join-Path $InstallBase $_ })
  foreach ($d in $allDirs) {
    try { New-Item -ItemType Directory -Path $d -Force -ErrorAction Stop | Out-Null } catch {
      Fail "INSTALL_DIR_NOT_WRITABLE" "Cannot create: $d -- $_"
    }
  }
  $Result.installDirCreated = $true
} else {
  Add-Warn "[DryRun] Skipping dir creation: $InstallBase"
}

# --- 9. Write worker-config.json ---

$configPath = Join-Path $InstallBase "config\worker-config.json"
$configObj  = [ordered]@{
  workerId                = [System.Guid]::NewGuid().ToString()
  providerVersion         = "hancom-com-powershell-v2"
  installDir              = $InstallBase
  hancomArchitecture      = "x86"
  powershellBitness       = 32
  comPolicy               = "HANCOM_32BIT_ONLY"
  ps32BitPath             = $Result.ps32BitPath
  hancomComProgId         = $Result.hancomComProgId
  hancomExeVersion        = $Result.hancomExeVersion
  selfTestStatus          = "pass"
  selfTestAt              = (Get-Date -Format "o")
  localApiPort            = 17823
  localApiOriginAllowlist = @()
  convertTimeoutSec       = 90
  logRetentionDays        = 7
  serverBaseUrl           = ""
  lastErrorCode           = $null
}

if (-not $DryRun) {
  try {
    $configObj | ConvertTo-Json -Depth 3 | Out-File -FilePath $configPath -Encoding utf8 -Force
    $Result.configWritten = $true
  } catch { Add-Warn "Config write failed: $_" }
} else {
  Add-Warn "[DryRun] Skipping config write: $configPath"
}

# --- 10. Task Scheduler command (32-bit PS, display only) ---

$workerScript = Join-Path $InstallBase "bin\HwpWorkerHost.ps1"
$taskCmd = (
  '"' + $ps32 + '" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $workerScript + '"'
)
$registerCmd = (
  'Register-ScheduledTask ' +
  '-TaskName "HaehanHwpWorker" ' +
  '-Action (New-ScheduledTaskAction -Execute "' + $ps32 + '" ' +
  '  -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File \"' + $workerScript + '\"") ' +
  '-Trigger (New-ScheduledTaskTrigger -AtLogOn -User "' + $env:USERNAME + '") ' +
  '-RunLevel Limited ' +
  '-Description "Haehan HWP Worker - 32-bit COM, user session logon" ' +
  '-Force'
)
$Result.taskSchedulerCommand = $registerCmd
$Result.taskSchedulerStatus  = "REGISTRATION_PENDING_APPROVAL"

$Result.installResultPath = Join-Path $InstallBase "config\install-result.json"

# --- 11. Final judgment ---

$Result.installMode  = "USER_LOCAL_WORKER"
$Result.ok           = $true
$Result.errorCode    = $null
$Result.errorMessage = $null

Write-Result
exit 0
