#Requires -Version 5.1
<#
.SYNOPSIS
  HWP to HWPX converter v2 with staged diagnostics.
  Outputs one JSON line to stdout and writes JSONL diagnostics under tmp/.
#>
param(
  [Parameter(Mandatory)][string]$InputPath,
  [Parameter(Mandatory)][string]$OutputPath,
  [int]$TimeoutSec = 90,
  [ValidateSet("convert", "open-only", "saveas")][string]$Mode = "convert",
  [ValidateSet("direct", "haction")][string]$SaveStrategy = "direct",
  [string]$DiagDir = "tmp\hancom_hwp_to_hwpx_diag",
  [string]$JobId = ([System.Guid]::NewGuid().ToString("N").Substring(0,8))
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"
Add-Type -Assembly System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

$provider = "hancom-com-powershell-v2"
$startTime = Get-Date
$repoRoot = (Get-Location).Path
if (-not [System.IO.Path]::IsPathRooted($DiagDir)) {
  $DiagDir = Join-Path $repoRoot $DiagDir
}
New-Item -ItemType Directory -Path $DiagDir -Force | Out-Null
$diagLog = Join-Path $DiagDir ("hancom_hwp_to_hwpx_{0}.jsonl" -f $JobId)
$diagSummary = Join-Path $DiagDir ("hancom_hwp_to_hwpx_{0}.json" -f $JobId)

$warnings = [System.Collections.Generic.List[string]]::new()
$hwp = $null
$beforePids = @()
$ownedPids = @()
$lastStage = "START"
$registerModule = $null
$setMessageBoxMode = $null
$securityModuleName = "FilePathCheckerModuleExample"

function Now-Iso { (Get-Date).ToString("o") }

function Get-HwpPids {
  @(Get-Process -Name Hwp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id)
}

function Elapsed-Ms {
  [int64](((Get-Date) - $startTime).TotalMilliseconds)
}

function Json-Compress($hash) {
  $hash | ConvertTo-Json -Compress -Depth 6
}

function Write-Stage($stage, $returnValue = $null, $errorMessage = $null) {
  $script:lastStage = $stage
  $after = Get-HwpPids
  $record = [ordered]@{
    timestamp       = Now-Iso
    job_id          = $JobId
    mode            = $Mode
    save_strategy   = $SaveStrategy
    stage           = $stage
    input_path      = $InputPath
    output_path     = $OutputPath
    elapsed_ms      = Elapsed-Ms
    return_value    = $returnValue
    error_message   = $errorMessage
    hwp_pids_before = @($script:beforePids)
    hwp_pids_after  = @($after)
  }
  Add-Content -Path $diagLog -Value (Json-Compress $record) -Encoding UTF8
}

function Release-Com($obj) {
  if ($null -eq $obj) { return }
  try { [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($obj) | Out-Null } catch {}
  [System.GC]::Collect()
  [System.GC]::WaitForPendingFinalizers()
  [System.GC]::Collect()
}

function Test-HwpxZip($path) {
  if (-not (Test-Path $path)) { return @{ ok = $false; entries = 0; error = "OUTPUT_NOT_FOUND" } }
  $stream = $null
  try {
    $bytes = [System.IO.File]::ReadAllBytes($path)
    if ($bytes.Length -lt 4 -or $bytes[0] -ne 0x50 -or $bytes[1] -ne 0x4B) {
      return @{ ok = $false; entries = 0; error = "ZIP_HEADER_INVALID" }
    }
    $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
    $zip.Dispose()
    $hasXml = @($entries | Where-Object { $_ -like "*.xml" }).Count -gt 0
    return @{ ok = $hasXml; entries = $entries.Count; error = $(if ($hasXml) { $null } else { "HWPX_XML_NOT_FOUND" }) }
  } catch {
    return @{ ok = $false; entries = 0; error = "ZIP_READ_FAILED: $_" }
  } finally {
    if ($null -ne $stream) { $stream.Dispose() }
  }
}

function Finish($ok, $stage, $code, $msg, $exitCode) {
  $finalPids = Get-HwpPids
  $residualPids = @($script:ownedPids | Where-Object { $_ -in $finalPids })
  $outputExists = Test-Path $OutputPath
  $outputSize = 0
  if ($outputExists) { $outputSize = (Get-Item $OutputPath).Length }
  $zipCheck = Test-HwpxZip $OutputPath
  $summary = [ordered]@{
    ok                 = $ok
    jobId              = $JobId
    mode               = $Mode
    saveStrategy       = $SaveStrategy
    inputPath          = $InputPath
    outputPath         = $OutputPath
    outputExists       = $outputExists
    outputSize         = $outputSize
    zipValid           = $zipCheck.ok
    zipEntries         = $zipCheck.entries
    stage              = $stage
    provider           = $provider
    warningCount       = $warnings.Count
    warnings           = @($warnings)
    errorCode          = $code
    errorMessage       = $msg
    setMessageBoxMode  = $script:setMessageBoxMode
    registerModuleName = $script:securityModuleName
    registerModule     = $script:registerModule
    ownedPidsStart     = @($script:ownedPids)
    ownedPidsEnd       = @($residualPids)
    ownedGoneClean     = ($residualPids.Count -eq 0)
    diagLog            = $diagLog
    diagSummary        = $diagSummary
    elapsedMs          = Elapsed-Ms
  }
  $json = Json-Compress $summary
  Set-Content -Path $diagSummary -Value $json -Encoding UTF8
  Write-Output $json
  exit $exitCode
}

function Fail($stage, $code, $msg) {
  Write-Stage "ERROR" $code $msg
  Finish $false $stage $code $msg 1
}

function Save-HwpxDirect($hwpObject, $path) {
  Write-Stage "SAVEAS_DIRECT_START"
  $ret = $hwpObject.SaveAs($path, "HWPX", "")
  Write-Stage "SAVEAS_DIRECT_DONE" $ret
  return $ret
}

function Save-HwpxHAction($hwpObject, $path) {
  Write-Stage "SAVEAS_HACTION_START"
  $hwpObject.HAction.GetDefault("FileSaveAs_S", $hwpObject.HParameterSet.HFileOpenSave.HSet) | Out-Null
  $hwpObject.HParameterSet.HFileOpenSave.filename = $path
  $hwpObject.HParameterSet.HFileOpenSave.Format = "HWPX"
  $ret = $hwpObject.HAction.Execute("FileSaveAs_S", $hwpObject.HParameterSet.HFileOpenSave.HSet)
  Write-Stage "SAVEAS_HACTION_DONE" $ret
  return $ret
}

Write-Stage "START"

if ([System.Environment]::Is64BitProcess) {
  Fail "COM_CREATE_START" "POWERSHELL_BITNESS_UNSUPPORTED" "Run via SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
}

try {
  Write-Stage "INPUT_CHECK_START"
  if (-not (Test-Path $InputPath)) { Fail "INPUT_CHECK_START" "INPUT_NOT_FOUND" "Not found: $InputPath" }
  $outDir = Split-Path $OutputPath -Parent
  if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
  Write-Stage "INPUT_CHECK_DONE" $true

  $beforePids = Get-HwpPids

  Write-Stage "COM_CREATE_START"
  $hwp = New-Object -ComObject HwpFrame.HwpObject.2
  Start-Sleep -Milliseconds 500
  $afterComPids = Get-HwpPids
  $ownedPids = @($afterComPids | Where-Object { $_ -notin $beforePids })
  Write-Stage "COM_CREATE_DONE" $true

  try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}

  Write-Stage "SET_MESSAGE_BOX_MODE_START"
  try {
    $setMessageBoxMode = $hwp.SetMessageBoxMode(65535)
    Write-Stage "SET_MESSAGE_BOX_MODE_DONE" $setMessageBoxMode
  } catch {
    $warnings.Add("SetMessageBoxMode failed: $_")
    Write-Stage "SET_MESSAGE_BOX_MODE_DONE" $false "$_"
  }

  Write-Stage "REGISTER_MODULE_START"
  try {
    Write-Stage "REGISTER_MODULE_NAME" $securityModuleName
    $registerModule = $hwp.RegisterModule("FilePathCheckDLL", $securityModuleName)
    Write-Stage "REGISTER_MODULE_DONE" $registerModule
    if ($registerModule -ne $true) { $warnings.Add("RegisterModule($securityModuleName) returned $registerModule") }
  } catch {
    $registerModule = $false
    $warnings.Add("RegisterModule($securityModuleName) failed: $_")
    Write-Stage "REGISTER_MODULE_DONE" $false "$_"
  }

  Write-Stage "OPEN_START"
  $openRet = $hwp.Open($InputPath, "", "forceopen:true;versionwarning:false;lock:false;")
  Write-Stage "OPEN_DONE" $openRet

  if ($Mode -eq "open-only") {
    Write-Stage "QUIT_START"
    try { $hwp.Clear(1) } catch { $warnings.Add("Clear: $_") }
    try { $hwp.Quit() } catch { $warnings.Add("Quit: $_") }
    Release-Com $hwp
    $hwp = $null
    Start-Sleep -Milliseconds 500
    Write-Stage "QUIT_DONE" $true
    Write-Stage "END" $true
    Finish $true "END" $null $null 0
  }

  Write-Stage "SAVEAS_START" $SaveStrategy
  if ($SaveStrategy -eq "haction") {
    $saveRet = Save-HwpxHAction $hwp $OutputPath
  } else {
    $saveRet = Save-HwpxDirect $hwp $OutputPath
  }
  Write-Stage "SAVEAS_DONE" $saveRet

  Write-Stage "OUTPUT_CHECK_START"
  $zipCheck = Test-HwpxZip $OutputPath
  if (-not $zipCheck.ok) {
    Write-Stage "OUTPUT_CHECK_DONE" $false $zipCheck.error
    Fail "OUTPUT_CHECK_DONE" "HANCOM_OUTPUT_INVALID" $zipCheck.error
  }
  Write-Stage "OUTPUT_CHECK_DONE" "SAVEAS_OUTPUT_VALID"

  Write-Stage "QUIT_START"
  try { $hwp.Clear(1) } catch { $warnings.Add("Clear: $_") }
  try { $hwp.Quit() } catch { $warnings.Add("Quit: $_") }
  Release-Com $hwp
  $hwp = $null
  Start-Sleep -Milliseconds 500
  Write-Stage "QUIT_DONE" $true
  Write-Stage "END" $true
  Finish $true "END" $null $null 0
} catch {
  $err = "$_"
  try {
    if ($null -ne $hwp) {
      Write-Stage "QUIT_START" $null "cleanup after error"
      try { $hwp.Clear(1) } catch {}
      try { $hwp.Quit() } catch {}
      Release-Com $hwp
      $hwp = $null
      Write-Stage "QUIT_DONE" $true
    }
  } catch {}
  Fail $lastStage "HANCOM_UNKNOWN_ERROR" $err
}
