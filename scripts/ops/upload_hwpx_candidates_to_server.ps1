param(
    [string]$SourceDir = "data\local_corpus_candidates",
    [string]$ServerAlias = "haehan-app",
    [string]$ServerPath = "/home/ubuntu/apps/hwpx-web-office",
    [string]$RemoteCandidateDir = "data/local_corpus_candidates",
    [int]$MaxFiles = 0
)

$ErrorActionPreference = "Stop"

function Write-JsonAndExit {
    param(
        [hashtable]$Payload,
        [int]$Code = 0
    )
    $Payload | ConvertTo-Json -Depth 8
    exit $Code
}

$root = Resolve-Path "."
$sourcePath = Join-Path $root $SourceDir

if (-not (Test-Path -LiteralPath $sourcePath)) {
    Write-JsonAndExit @{
        schemaVersion = "web_office_hwpx_candidate_upload_v1"
        verdict = "NO_LOCAL_CANDIDATE_DIR"
        sourceDir = $SourceDir
        uploaded = 0
        promotionRequiresApproval = $true
    }
}

$files = Get-ChildItem -LiteralPath $sourcePath -Recurse -File -Filter "*.hwpx" |
    Sort-Object FullName

if ($MaxFiles -gt 0) {
    $files = $files | Select-Object -First $MaxFiles
}

if (-not $files -or $files.Count -eq 0) {
    Write-JsonAndExit @{
        schemaVersion = "web_office_hwpx_candidate_upload_v1"
        verdict = "NO_LOCAL_CANDIDATES"
        sourceDir = $SourceDir
        uploaded = 0
        promotionRequiresApproval = $true
    }
}

$remoteAbsDir = "$ServerPath/$RemoteCandidateDir"
ssh $ServerAlias "mkdir -p '$remoteAbsDir'"

$uploaded = @()
foreach ($file in $files) {
    $hash = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $remoteName = "$($hash.Substring(0, 24)).hwpx"
    $remotePath = "$remoteAbsDir/$remoteName"
    scp $file.FullName "${ServerAlias}:$remotePath"
    $uploaded += @{
        sourceHash = $hash
        sizeBytes = $file.Length
        remoteName = $remoteName
        originalFileNameStored = $false
        promotionStatus = "REVIEW_REQUIRED"
    }
}

Write-JsonAndExit @{
    schemaVersion = "web_office_hwpx_candidate_upload_v1"
    verdict = "PASS"
    serverAlias = $ServerAlias
    remoteCandidateDir = $RemoteCandidateDir
    uploaded = $uploaded.Count
    files = $uploaded
    promotionRequiresApproval = $true
}
