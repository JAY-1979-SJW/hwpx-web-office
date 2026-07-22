#Requires -Version 5.1
<#
.SYNOPSIS
  User-present Hancom HWP to HWPX conversion worker.
  Opens the HWP through the same GUI path a user would use, then saves or
  verifies HWPX after the user confirms the document is open.
#>
param(
  [Parameter(Mandatory)][string]$InputPath,
  [Parameter(Mandatory)][string]$OutputPath,
  [int]$TimeoutSeconds = 180,
  [int]$WaitUserSeconds = 60,
  [string]$ResultPath = "tmp\hancom_user_present_outputs\user_present_result.json"
)

Set-StrictMode -Off
$ErrorActionPreference = "Stop"
Add-Type -Assembly System.IO.Compression.FileSystem -ErrorAction SilentlyContinue

$startedAt = Get-Date
$provider = "HANCOM_USER_PRESENT_GUI"
$events = [System.Collections.Generic.List[object]]::new()
$warnings = [System.Collections.Generic.List[string]]::new()

function Now-Iso { (Get-Date).ToString("o") }

function Add-Event($stage, $status = $null, $message = $null) {
  $events.Add([ordered]@{
    timestamp = Now-Iso
    stage = $stage
    status = $status
    message = $message
  })
}

function Get-HwpSnapshot {
  @(Get-Process Hwp -ErrorAction SilentlyContinue |
    Select-Object Id, ProcessName, StartTime, MainWindowTitle, Path, SessionId)
}

function To-PlainProcess($p) {
  [ordered]@{
    id = $p.Id
    process_name = $p.ProcessName
    start_time = if ($p.StartTime) { $p.StartTime.ToString("o") } else { $null }
    main_window_title = $p.MainWindowTitle
    path = $p.Path
    session_id = $p.SessionId
  }
}

function Resolve-HwpExe {
  $running = Get-HwpSnapshot | Where-Object { $_.Path } | Select-Object -First 1
  if ($running) { return $running.Path }

  $paths = @(
    "C:\Program Files (x86)\HNC\Office 2024\HOffice130\Bin\Hwp.exe",
    "C:\Program Files (x86)\Hnc\Office\HOffice130\Bin\Hwp.exe",
    "C:\Program Files (x86)\Hnc\Office\HOffice120\Bin\Hwp.exe",
    "C:\Program Files (x86)\Hnc\HOffice9\Bin\Hwp.exe",
    "C:\Program Files\Hnc\Office\HOffice130\Bin\Hwp.exe"
  )
  foreach ($path in $paths) {
    if (Test-Path $path) { return $path }
  }
  return $null
}

function Test-HwpxZip($path) {
  if (-not (Test-Path -LiteralPath $path)) {
    return @{ ok = $false; entries = 0; error = "OUTPUT_NOT_FOUND" }
  }
  $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $path).Path)
  if ($bytes.Length -lt 4 -or $bytes[0] -ne 0x50 -or $bytes[1] -ne 0x4B -or $bytes[2] -ne 0x03 -or $bytes[3] -ne 0x04) {
    return @{ ok = $false; entries = 0; error = "ZIP_HEADER_INVALID" }
  }
  try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $path).Path)
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
    $zip.Dispose()
    $hasXml = @($entries | Where-Object { $_.ToLowerInvariant().EndsWith(".xml") }).Count -gt 0
    return @{ ok = $hasXml; entries = $entries.Count; error = $(if ($hasXml) { $null } else { "HWPX_XML_NOT_FOUND" }) }
  } catch {
    return @{ ok = $false; entries = 0; error = "ZIP_READ_FAILED: $_" }
  }
}

function Try-ComSaveAs($inputPath, $outputPath) {
  $attempts = [System.Collections.Generic.List[object]]::new()
  foreach ($mode in @("active", "new")) {
    $hwp = $null
    try {
      if ($mode -eq "active") {
        $hwp = [System.Runtime.InteropServices.Marshal]::GetActiveObject("HwpFrame.HwpObject.2")
      } else {
        $hwp = New-Object -ComObject HwpFrame.HwpObject.2
        try { $hwp.XHwpWindows.Item(0).Visible = $true } catch {}
        try { $hwp.SetMessageBoxMode(65535) | Out-Null } catch {}
        try { $hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModuleExample") | Out-Null } catch {}
        $openRet = $hwp.Open($inputPath, "", "forceopen:true;versionwarning:false;lock:false;")
        $attempts.Add([ordered]@{ mode = $mode; stage = "open"; ok = $true; message = "Open returned $openRet" })
      }
      if ($null -eq $hwp) {
        throw "COM object is null"
      }
      try { $hwp.SetMessageBoxMode(65535) | Out-Null } catch {}
      $ret = $hwp.SaveAs($outputPath, "HWPX", "")
      $attempts.Add([ordered]@{ mode = $mode; stage = "saveas"; ok = $true; message = "SaveAs returned $ret" })
      return @{ ok = $true; mode = $mode; message = "SaveAs returned $ret"; attempts = @($attempts) }
    } catch {
      $attempts.Add([ordered]@{ mode = $mode; stage = "saveas"; ok = $false; message = "$_" })
    }
  }
  return @{ ok = $false; mode = $null; message = "All COM SaveAs attempts failed"; attempts = @($attempts) }
}

function Write-Result($ok, $stage, $code, $message, $exitCode) {
  $zipCheck = Test-HwpxZip $OutputPath
  $outputExists = Test-Path -LiteralPath $OutputPath
  $outputSize = 0
  if ($outputExists) {
    $outputSize = (Get-Item -LiteralPath $OutputPath).Length
  }
  $result = [ordered]@{
    ok = $ok
    provider = $provider
    stage = $stage
    status = $code
    message = $message
    input_path = $InputPath
    output_path = $OutputPath
    output_exists = $outputExists
    output_size = $outputSize
    zip_valid = $zipCheck.ok
    zip_entries = $zipCheck.entries
    zip_error = $zipCheck.error
    started_at = $startedAt.ToString("o")
    finished_at = Now-Iso
    wait_user_seconds = $WaitUserSeconds
    timeout_seconds = $TimeoutSeconds
    warnings = @($warnings)
    events = @($events)
    hwp_processes = @(Get-HwpSnapshot | ForEach-Object { To-PlainProcess $_ })
  }
  $dir = Split-Path $ResultPath -Parent
  if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
  }
  $json = $result | ConvertTo-Json -Depth 8
  Set-Content -Path $ResultPath -Value $json -Encoding UTF8
  Write-Output $json
  exit $exitCode
}

try {
  Add-Event "INPUT_CHECK_START"
  $input = (Resolve-Path -LiteralPath $InputPath).Path
  $outDir = Split-Path $OutputPath -Parent
  if ($outDir -and -not (Test-Path $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
  }
  $output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
  $InputPath = $input
  $OutputPath = $output
  Add-Event "INPUT_CHECK_DONE" "OK"

  Add-Event "GUI_OPEN_START"
  $before = Get-HwpSnapshot
  $beforeIds = @($before | ForEach-Object { $_.Id })
  $hwpExe = Resolve-HwpExe
  if (-not $hwpExe) {
    Write-Result $false "GUI_OPEN_START" "HWP_EXE_NOT_FOUND" "Hwp.exe not found" 1
  }
  Start-Process -FilePath $hwpExe -ArgumentList ('"{0}"' -f $InputPath) | Out-Null
  Add-Event "GUI_OPEN_LAUNCHED" "OK" $hwpExe

  $deadline = (Get-Date).AddSeconds($WaitUserSeconds)
  $openedTitle = $null
  while ((Get-Date) -lt $deadline) {
    $title = @(Get-HwpSnapshot | Where-Object { $_.MainWindowTitle -like "*$(Split-Path $InputPath -Leaf)*" } | Select-Object -First 1 -ExpandProperty MainWindowTitle)
    if ($title.Count -gt 0) {
      $openedTitle = $title[0]
      break
    }
    Start-Sleep -Seconds 1
  }
  if ($openedTitle) {
    Add-Event "GUI_OPEN_DETECTED" "OPEN_CONFIRMED_BY_WINDOW_TITLE" $openedTitle
  } else {
    Add-Event "GUI_OPEN_WAIT_USER" "WAITING_FOR_USER"
  }

  Write-Host ""
  Write-Host "한컴에서 문서가 정상적으로 열렸으면 Enter를 누르세요."
  Write-Host "보안/확인/복구 팝업이 있으면 직접 처리한 뒤 Enter를 누르세요."
  Write-Host "실패했으면 N 입력 후 Enter를 누르세요."
  $userInput = Read-Host
  if ($userInput -eq "N" -or $userInput -eq "n") {
    Add-Event "USER_CONFIRM_OPEN" "USER_PRESENT_OPEN_FAILED"
    Write-Result $false "USER_CONFIRM_OPEN" "USER_PRESENT_OPEN_FAILED" "User reported that the HWP did not open" 1
  }
  Add-Event "USER_CONFIRM_OPEN" "USER_PRESENT_OPEN_CONFIRMED"

  Add-Event "SAVEAS_ACTIVE_COM_START"
  $saveStatus = "USER_PRESENT_SAVEAS_FAILED"
  $saveMessage = $null
  $saveResult = Try-ComSaveAs $InputPath $OutputPath
  foreach ($attempt in @($saveResult.attempts)) {
    Add-Event "SAVEAS_COM_ATTEMPT" $(if ($attempt.ok) { "OK" } else { "FAIL" }) "$($attempt.mode):$($attempt.stage):$($attempt.message)"
  }
  if ($saveResult.ok) {
    $saveStatus = "USER_PRESENT_SAVEAS_SUCCESS"
    $saveMessage = "$($saveResult.mode): $($saveResult.message)"
    Add-Event "SAVEAS_ACTIVE_COM_DONE" $saveStatus $saveMessage
  } else {
    $saveMessage = "$($saveResult.message)"
    $warnings.Add("Active COM SaveAs failed: $saveMessage")
    Add-Event "SAVEAS_ACTIVE_COM_DONE" $saveStatus $saveMessage
  }

  $zipCheck = Test-HwpxZip $OutputPath
  if (-not $zipCheck.ok) {
    Write-Host ""
    Write-Host "자동 SaveAs 검증에 실패했습니다: $($zipCheck.error)"
    Write-Host "한컴에서 직접 '다른 이름으로 저장'으로 아래 경로에 HWPX 저장 후 Enter를 누르세요."
    Write-Host $OutputPath
    Write-Host "직접 저장도 실패했으면 N 입력 후 Enter를 누르세요."
    $manualInput = Read-Host
    if ($manualInput -eq "N" -or $manualInput -eq "n") {
      Add-Event "MANUAL_SAVEAS" "USER_PRESENT_SAVEAS_FAILED"
      Write-Result $false "MANUAL_SAVEAS" "USER_PRESENT_SAVEAS_FAILED" "User reported manual SaveAs failure" 1
    }
    Add-Event "MANUAL_SAVEAS" "USER_PRESENT_SAVEAS_RECHECK"
    $zipCheck = Test-HwpxZip $OutputPath
  }

  if ($zipCheck.ok) {
    Add-Event "OUTPUT_CHECK_DONE" "USER_PRESENT_OUTPUT_VALID"
    Write-Result $true "OUTPUT_CHECK_DONE" "USER_PRESENT_OUTPUT_VALID" "HWPX output is valid" 0
  }
  Add-Event "OUTPUT_CHECK_DONE" "USER_PRESENT_OUTPUT_INVALID" $zipCheck.error
  Write-Result $false "OUTPUT_CHECK_DONE" "USER_PRESENT_OUTPUT_INVALID" $zipCheck.error 1
} catch {
  Add-Event "ERROR" "USER_PRESENT_UNKNOWN_ERROR" "$_"
  Write-Result $false "ERROR" "USER_PRESENT_UNKNOWN_ERROR" "$_" 1
}
