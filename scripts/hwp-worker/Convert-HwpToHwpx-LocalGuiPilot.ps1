#Requires -Version 5.1
<#
.SYNOPSIS
  Local GUI pilot for opening HWP in Hancom and saving as HWPX through user-like UI input.
#>
param(
  [Parameter(Mandatory=$true)][string]$InputPath,
  [Parameter(Mandatory=$true)][string]$OutputPath,
  [int]$OpenWaitSeconds = 30,
  [int]$SaveWaitSeconds = 60,
  [string]$LogPath = "tmp\hancom_local_gui_outputs\gui_pilot_log.jsonl",
  [switch]$OpenOnly
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms

Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public class Win32WindowTools {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern int GetWindowThreadProcessId(IntPtr hWnd, out int processId);
}
"@

$script:StartTime = Get-Date
$script:LastStage = "START"
$script:HwpProcess = $null
$script:InputFullName = $InputPath
$script:OutputFullName = $OutputPath
$script:HwpExe = $null

function Get-ElapsedMs {
  [int64](((Get-Date) - $script:StartTime).TotalMilliseconds)
}

function ConvertTo-JsonLine($value) {
  $value | ConvertTo-Json -Compress -Depth 6
}

function Write-Stage {
  param(
    [Parameter(Mandatory=$true)][string]$Stage,
    [object]$ReturnValue = $null,
    [string]$ErrorMessage = $null
  )
  $script:LastStage = $Stage
  $dir = Split-Path -Parent $LogPath
  if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }
  $record = [ordered]@{
    timestamp = (Get-Date).ToString("o")
    stage = $Stage
    input_path = $script:InputFullName
    output_path = $script:OutputFullName
    elapsed_ms = Get-ElapsedMs
    return_value = $ReturnValue
    error_message = $ErrorMessage
  }
  Add-Content -LiteralPath $LogPath -Value (ConvertTo-JsonLine $record) -Encoding UTF8
}

function Finish {
  param(
    [bool]$Ok,
    [string]$Stage,
    [string]$Code,
    [string]$Message,
    [int]$ExitCode
  )
  $exists = Test-Path -LiteralPath $script:OutputFullName
  $size = 0
  if ($exists) {
    $size = (Get-Item -LiteralPath $script:OutputFullName).Length
  }
  $summary = [ordered]@{
    ok = $Ok
    stage = $Stage
    errorCode = $Code
    errorMessage = $Message
    inputPath = $script:InputFullName
    outputPath = $script:OutputFullName
    outputExists = $exists
    outputSize = $size
    hwpExe = $script:HwpExe
    hwpPid = $(if ($script:HwpProcess) { $script:HwpProcess.Id } else { $null })
    logPath = $LogPath
    elapsedMs = Get-ElapsedMs
  }
  $json = ConvertTo-JsonLine $summary
  Write-Output $json
  exit $ExitCode
}

function Fail {
  param([string]$Stage, [string]$Code, [string]$Message)
  Write-Stage "ERROR" $Code $Message
  Finish $false $Stage $Code $Message 1
}

function Get-VisibleWindows {
  return @(Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle } |
    ForEach-Object {
      [PSCustomObject]@{
        Handle = $_.MainWindowHandle
        ProcessId = $_.Id
        Title = $_.MainWindowTitle
      }
    })
}

function Wait-HwpWindow {
  param([int]$TargetProcessId, [int]$Seconds)
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    $wins = @(Get-VisibleWindows | Where-Object { $_.ProcessId -eq $TargetProcessId })
    $doc = @($wins | Where-Object { $_.Title -match "\.hwp|HWP|Hancom" } | Select-Object -First 1)
    if ($doc.Count -gt 0) { return $doc[0] }
    Start-Sleep -Milliseconds 500
  }
  return $null
}

function Wait-SaveDialog {
  param([int]$Seconds)
  $deadline = (Get-Date).AddSeconds($Seconds)
  $shell = New-Object -ComObject WScript.Shell
  $koreanSaveAs = [string]([char]0xB2E4) + [string]([char]0xB978) + " " + [string]([char]0xC774) + [string]([char]0xB984) + [string]([char]0xC73C) + [string]([char]0xB85C) + " " + [string]([char]0xC800) + [string]([char]0xC7A5)
  $koreanSave = [string]([char]0xC800) + [string]([char]0xC7A5)
  $patterns = @("Save As", "Save", $koreanSaveAs, $koreanSave)
  while ((Get-Date) -lt $deadline) {
    foreach ($p in $patterns) {
      try {
        if ($shell.AppActivate($p)) {
          return [PSCustomObject]@{
            Handle = $null
            ProcessId = $null
            Title = $p
          }
        }
      } catch {
        # Keep polling candidates.
      }
    }
    Start-Sleep -Milliseconds 500
  }
  return $null
}

function Quote-ProcessArgument {
  param([Parameter(Mandatory=$true)][string]$Value)
  return '"' + ($Value -replace '"', '\"') + '"'
}

function Test-HwpxZip {
  param([string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    return @{ ok = $false; error = "NO_FILE"; entries = 0; xml = $false }
  }
  try {
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 4 -or $bytes[0] -ne 0x50 -or $bytes[1] -ne 0x4B -or $bytes[2] -ne 0x03 -or $bytes[3] -ne 0x04) {
      return @{ ok = $false; error = "ZIP_HEADER_FALSE"; entries = 0; xml = $false }
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($Path)
    $entries = @($zip.Entries | ForEach-Object { $_.FullName })
    $zip.Dispose()
    $hasXml = @($entries | Where-Object { $_.ToLowerInvariant().EndsWith(".xml") }).Count -gt 0
    return @{ ok = $hasXml; error = $(if ($hasXml) { $null } else { "XML_FALSE" }); entries = $entries.Count; xml = $hasXml }
  } catch {
    return @{ ok = $false; error = "ZIP_READ_FAILED: $_"; entries = 0; xml = $false }
  }
}

function Find-HwpExe {
  $candidates = @(
    "C:\Program Files (x86)\HNC\Office 2024\HOffice130\Bin\Hwp.exe",
    "C:\Program Files (x86)\Hnc\Office\HOffice130\Bin\Hwp.exe",
    "C:\Program Files (x86)\Hnc\Office\HOffice120\Bin\Hwp.exe",
    "C:\Program Files (x86)\Hnc\HOffice9\Bin\Hwp.exe",
    "C:\Program Files\Hnc\Office\HOffice130\Bin\Hwp.exe"
  )
  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) { return $candidate }
  }
  $found = Get-ChildItem "C:\Program Files", "C:\Program Files (x86)" -Recurse -Filter Hwp.exe -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($found) { return $found.FullName }
  return $null
}

Write-Stage "START"

try {
  Write-Stage "INPUT_RAW" $InputPath
  $script:InputFullName = (Resolve-Path -LiteralPath $InputPath).Path
  $inputItem = Get-Item -LiteralPath $script:InputFullName -ErrorAction Stop
  $outputParent = Split-Path -Parent $OutputPath
  if (-not $outputParent) { $outputParent = "." }
  New-Item -ItemType Directory -Force -Path $outputParent | Out-Null
  $script:OutputFullName = [System.IO.Path]::GetFullPath((Join-Path (Resolve-Path -LiteralPath $outputParent).Path (Split-Path -Leaf $OutputPath)))
  Write-Stage "INPUT_RESOLVED" $script:InputFullName
  Write-Stage "INPUT_EXISTS" $true
  Write-Stage "INPUT_SIZE" $inputItem.Length
  Write-Stage "OUTPUT_RESOLVED" $script:OutputFullName

  $script:HwpExe = Find-HwpExe
  if (-not $script:HwpExe) {
    Fail "HWP_START_PROCESS" "HWP_EXE_NOT_FOUND" "Hwp.exe was not found."
  }

  Write-Stage "HWP_START_PROCESS" $script:HwpExe
  $hwpArgument = Quote-ProcessArgument $script:InputFullName
  Write-Stage "HWP_ARGUMENT_USED" $hwpArgument
  $processInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $processInfo.FileName = $script:HwpExe
  $processInfo.Arguments = $hwpArgument
  $processInfo.WorkingDirectory = Split-Path -Parent $script:HwpExe
  $processInfo.UseShellExecute = $false
  $script:HwpProcess = [System.Diagnostics.Process]::Start($processInfo)

  $hwpWindow = Wait-HwpWindow -TargetProcessId $script:HwpProcess.Id -Seconds $OpenWaitSeconds
  if (-not $hwpWindow) {
    Fail "HWP_WINDOW_DETECTED" "HWP_WINDOW_NOT_FOUND" "Hancom document window was not detected."
  }
  Write-Stage "HWP_WINDOW_DETECTED" $hwpWindow.Title

  if ($OpenOnly) {
    Write-Stage "END" "OPEN_ONLY"
    Finish $true "END" $null $null 0
  }

  $shell = New-Object -ComObject WScript.Shell
  [void]$shell.AppActivate($script:HwpProcess.Id)
  Start-Sleep -Milliseconds 500

  Write-Stage "SAVE_DIALOG_START" "F12"
  [System.Windows.Forms.SendKeys]::SendWait("{F12}")
  Start-Sleep -Seconds 2

  $saveDialog = Wait-SaveDialog -Seconds 8
  if (-not $saveDialog) {
    Write-Stage "SAVE_DIALOG_START" "CTRL_SHIFT_S"
    [void]$shell.AppActivate($script:HwpProcess.Id)
    Start-Sleep -Milliseconds 300
    [System.Windows.Forms.SendKeys]::SendWait("^+s")
    Start-Sleep -Seconds 2
    $saveDialog = Wait-SaveDialog -Seconds 8
  }

  if (-not $saveDialog) {
    Fail "SAVE_DIALOG_START" "SAVE_DIALOG_NOT_FOUND" "Save dialog was not detected after F12 or Ctrl+Shift+S."
  }
  Write-Stage "SAVE_DIALOG_DETECTED" $saveDialog.Title

  [void]$shell.AppActivate($saveDialog.Title)
  Start-Sleep -Milliseconds 500
  [System.Windows.Forms.SendKeys]::SendWait("^a")
  Start-Sleep -Milliseconds 200
  [System.Windows.Forms.SendKeys]::SendWait($script:OutputFullName)
  Write-Stage "SAVE_DIALOG_FILLED" $script:OutputFullName
  Start-Sleep -Milliseconds 300
  [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
  Write-Stage "SAVE_DIALOG_CONFIRMED"

  $deadline = (Get-Date).AddSeconds($SaveWaitSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $script:OutputFullName) { break }
    Start-Sleep -Milliseconds 500
  }

  $zip = Test-HwpxZip $script:OutputFullName
  Write-Stage "OUTPUT_CHECK" $zip
  if (-not $zip.ok) {
    Fail "OUTPUT_CHECK" "OUTPUT_INVALID" $zip.error
  }

  Write-Stage "END" $true
  Finish $true "END" $null $null 0
} catch {
  Fail $script:LastStage "LOCAL_GUI_PILOT_ERROR" "$_"
}
