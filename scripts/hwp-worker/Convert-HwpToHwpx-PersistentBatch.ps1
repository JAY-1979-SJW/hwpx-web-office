param(
  [Parameter(Mandatory=$true)][string]$ManifestPath,
  [Parameter(Mandatory=$true)][string]$ResultPath,
  [string]$DiagDir = "tmp\hancom_hwp_to_hwpx_persistent_diag",
  [ValidateSet("direct", "haction")][string]$SaveStrategy = "direct"
)

$ErrorActionPreference = "Stop"
$provider = "hancom-com-powershell-persistent-batch"
$securityModuleName = "FilePathCheckerModuleExample"
$startedAt = Get-Date

function IsoNow() { (Get-Date).ToString("o") }

function Write-JsonLine($path, $obj) {
  $line = $obj | ConvertTo-Json -Compress -Depth 20
  Add-Content -Path $path -Value $line -Encoding UTF8
}

function Release-Com($obj) {
  try {
    if ($null -ne $obj) {
      [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($obj) | Out-Null
    }
  } catch {}
}

function Test-HwpxZip($path) {
  if (-not (Test-Path $path)) { return @{ ok = $false; error = "OUTPUT_NOT_FOUND"; entries = 0 } }
  try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction SilentlyContinue | Out-Null
    $zip = [System.IO.Compression.ZipFile]::OpenRead($path)
    try {
      $entries = @($zip.Entries | ForEach-Object { $_.FullName })
      $hasXml = ($entries | Where-Object { $_ -like "*.xml" }).Count -gt 0
      return @{ ok = $hasXml; error = $(if ($hasXml) { $null } else { "HWPX_XML_NOT_FOUND" }); entries = $entries.Count }
    } finally {
      $zip.Dispose()
    }
  } catch {
    return @{ ok = $false; error = "$_"; entries = 0 }
  }
}

function Save-HwpxDirect($hwpObject, $path) {
  return $hwpObject.SaveAs($path, "HWPX", "")
}

function Save-HwpxHAction($hwpObject, $path) {
  $hwpObject.HAction.GetDefault("FileSaveAs_S", $hwpObject.HParameterSet.HFileOpenSave.HSet) | Out-Null
  $hwpObject.HParameterSet.HFileOpenSave.filename = $path
  $hwpObject.HParameterSet.HFileOpenSave.Format = "HWPX"
  return $hwpObject.HAction.Execute("FileSaveAs_S", $hwpObject.HParameterSet.HFileOpenSave.HSet)
}

if ([System.Environment]::Is64BitProcess) {
  throw "POWERSHELL_BITNESS_UNSUPPORTED: run via SysWOW64\WindowsPowerShell\v1.0\powershell.exe"
}

New-Item -ItemType Directory -Path $DiagDir -Force | Out-Null
$diagLog = Join-Path $DiagDir ("persistent_batch_{0}.jsonl" -f ([Guid]::NewGuid().ToString("N").Substring(0, 8)))
$manifest = Get-Content -Path $ManifestPath -Encoding UTF8 | ConvertFrom-Json
$items = @($manifest.items)
$results = @()
$warnings = @()
$hwp = $null
$setMessageBoxMode = $null
$registerModule = $null

try {
  Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "COM_CREATE_START"; count = $items.Count }
  $hwp = New-Object -ComObject HwpFrame.HwpObject.2
  Start-Sleep -Milliseconds 500
  try { $hwp.XHwpWindows.Item(0).Visible = $false } catch {}
  Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "COM_CREATE_DONE"; count = $items.Count }

  try {
    $setMessageBoxMode = $hwp.SetMessageBoxMode(65535)
  } catch {
    $warnings += "SetMessageBoxMode failed: $_"
  }
  try {
    $registerModule = $hwp.RegisterModule("FilePathCheckDLL", $securityModuleName)
    if ($registerModule -ne $true) { $warnings += "RegisterModule returned $registerModule" }
  } catch {
    $registerModule = $false
    $warnings += "RegisterModule failed: $_"
  }

  $index = 0
  foreach ($item in $items) {
    $index += 1
    $itemStarted = Get-Date
    $inputPath = [string]$item.inputPath
    $outputPath = [string]$item.outputPath
    $itemId = [string]$item.itemId
    $ok = $false
    $errorCode = $null
    $errorMessage = $null
    $openRet = $null
    $saveRet = $null
    $zipCheck = @{ ok = $false; error = "NOT_RUN"; entries = 0 }
    try {
      $outDir = Split-Path $outputPath -Parent
      if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
      Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "ITEM_OPEN_START"; index = $index; itemId = $itemId; inputPath = $inputPath; outputPath = $outputPath }
      $openRet = $hwp.Open($inputPath, "", "forceopen:true;versionwarning:false;lock:false;")
      Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "ITEM_OPEN_DONE"; index = $index; itemId = $itemId; returnValue = $openRet }
      Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "ITEM_SAVE_START"; index = $index; itemId = $itemId; saveStrategy = $SaveStrategy }
      if ($SaveStrategy -eq "haction") {
        $saveRet = Save-HwpxHAction $hwp $outputPath
      } else {
        $saveRet = Save-HwpxDirect $hwp $outputPath
      }
      Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "ITEM_SAVE_DONE"; index = $index; itemId = $itemId; returnValue = $saveRet }
      $zipCheck = Test-HwpxZip $outputPath
      if ($zipCheck.ok -eq $true) {
        $ok = $true
        $errorCode = "HANCOM_CONVERSION_SUCCESS"
      } else {
        $errorCode = "HANCOM_OUTPUT_INVALID"
        $errorMessage = [string]$zipCheck.error
      }
    } catch {
      $errorCode = "HANCOM_ITEM_ERROR"
      $errorMessage = "$_"
      Write-JsonLine $diagLog @{ timestamp = IsoNow; stage = "ITEM_ERROR"; index = $index; itemId = $itemId; error = $errorMessage }
    } finally {
      try { $hwp.Clear(1) } catch {}
    }
    $elapsedMs = [int]((Get-Date) - $itemStarted).TotalMilliseconds
    $outItem = Get-Item -Path $outputPath -ErrorAction SilentlyContinue
    $results += [pscustomobject][ordered]@{
      itemId = $itemId
      index = $index
      ok = $ok
      inputPath = $inputPath
      outputPath = $outputPath
      outputExists = ($null -ne $outItem)
      outputSize = $(if ($null -ne $outItem) { $outItem.Length } else { 0 })
      openReturn = $openRet
      saveReturn = $saveRet
      zipValid = $zipCheck.ok
      zipEntries = $zipCheck.entries
      errorCode = $errorCode
      errorMessage = $errorMessage
      elapsedMs = $elapsedMs
    }
  }

  try { $hwp.Quit() } catch {}
  Release-Com $hwp
  $hwp = $null
} catch {
  $warnings += "batch failed: $_"
  try {
    if ($null -ne $hwp) {
      try { $hwp.Quit() } catch {}
      Release-Com $hwp
      $hwp = $null
    }
  } catch {}
} finally {
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}

$okCount = @($results | Where-Object { $_.ok -eq $true }).Count
$failCount = $items.Count - $okCount
$summary = [ordered]@{
  ok = ($failCount -eq 0)
  provider = $provider
  startedAt = $startedAt.ToString("o")
  finishedAt = (Get-Date).ToString("o")
  count = $items.Count
  okCount = $okCount
  failCount = $failCount
  saveStrategy = $SaveStrategy
  setMessageBoxMode = $setMessageBoxMode
  registerModuleName = $securityModuleName
  registerModule = $registerModule
  warningCount = @($warnings).Count
  warnings = @($warnings)
  diagLog = $diagLog
  results = @($results)
}
$json = $summary | ConvertTo-Json -Depth 30
Set-Content -Path $ResultPath -Value $json -Encoding UTF8
Write-Output ($summary | ConvertTo-Json -Compress -Depth 8)
if ($failCount -eq 0) { exit 0 } else { exit 1 }
