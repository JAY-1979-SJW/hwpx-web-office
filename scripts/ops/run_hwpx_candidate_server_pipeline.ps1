param(
    [string]$SourceDir = "data\local_corpus_candidates",
    [string]$ServerAlias = "haehan-app",
    [string]$ServerPath = "/home/ubuntu/apps/hwpx-web-office",
    [string]$RemoteCandidateDir = "data/local_corpus_candidates",
    [string]$RemoteReportDir = "data/reports/web_office_hwpx_corpus_candidates",
    [int]$MaxFiles = 0,
    [int]$WaitSeconds = 2
)

$ErrorActionPreference = "Stop"

function ConvertFrom-JsonOutput {
    param([string[]]$Lines)
    $text = ($Lines -join "`n").Trim()
    if (-not $text) {
        throw "Empty JSON output"
    }
    return $text | ConvertFrom-Json
}

function Write-PipelineJson {
    param([hashtable]$Payload)
    $Payload | ConvertTo-Json -Depth 12
}

$uploadArgs = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "scripts\ops\upload_hwpx_candidates_to_server.ps1",
    "-SourceDir", $SourceDir,
    "-ServerAlias", $ServerAlias,
    "-ServerPath", $ServerPath,
    "-RemoteCandidateDir", $RemoteCandidateDir,
    "-MaxFiles", "$MaxFiles"
)

$uploadOutput = & powershell @uploadArgs
$upload = ConvertFrom-JsonOutput $uploadOutput

$remoteCommand = @"
cd '$ServerPath' &&
mkdir -p '$RemoteCandidateDir' '$RemoteReportDir' &&
python3 scripts/ops/run_web_office_hwpx_corpus_candidate_scan.py --candidate-root '$RemoteCandidateDir' --report-dir '$RemoteReportDir' --background &&
sleep $WaitSeconds &&
echo PIPELINE_SCAN_SUMMARY_JSON &&
python3 - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('$RemoteReportDir/candidate_scan_report.json').read_text())
manifest = json.loads(Path('$RemoteReportDir/candidate_manifest_draft.json').read_text())
print(json.dumps({
  'reportVerdict': report.get('verdict'),
  'finalStatus': report.get('finalStatus'),
  'scanned': report.get('scanCounters', {}).get('scanned'),
  'candidateCount': len(manifest.get('candidates', [])),
  'promotionRequiresApproval': report.get('promotionRequiresApproval'),
  'claimBoundary': report.get('claimBoundary')
}, ensure_ascii=False))
PY
"@

$serverOutput = ssh $ServerAlias $remoteCommand
$jsonLines = @()
$collect = $false
foreach ($line in $serverOutput) {
    if ($line.Trim() -eq "PIPELINE_SCAN_SUMMARY_JSON") {
        $collect = $true
        continue
    }
    if ($collect) {
        $jsonLines += $line
    }
}
$serverScan = ConvertFrom-JsonOutput $jsonLines

$verdict = "PASS"
if ($serverScan.reportVerdict -ne "PASS" -or $serverScan.promotionRequiresApproval -ne $true) {
    $verdict = "FAIL"
}

Write-PipelineJson @{
    schemaVersion = "web_office_hwpx_candidate_server_pipeline_v1"
    verdict = $verdict
    uploadVerdict = $upload.verdict
    uploaded = $upload.uploaded
    serverScan = $serverScan
    serverAlias = $ServerAlias
    remoteCandidateDir = $RemoteCandidateDir
    remoteReportDir = $RemoteReportDir
    automaticPromotionAllowed = $false
    promotionRequiresApproval = $true
}
