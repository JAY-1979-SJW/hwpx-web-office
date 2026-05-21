#!/usr/bin/env python3
"""Read-only API/upload/download/output gate audit."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_PARTS = {".git", ".gradle", "build", "deliverables", "reports", "logs", "__pycache__", "node_modules"}
TEXT_SUFFIXES = {".java", ".py", ".md", ".json", ".yml", ".yaml", ".kt", ".kts"}

CREATE_CONTEXT_RE = re.compile(r'createContext\("([^"]+)"\s*,\s*wrap\(new\s+([A-Za-z0-9_]+)')
UPLOAD_RE = re.compile(r"(?i)(multipart|upload|filename|requestBody|Content-Type|\\.xlsx|\\.hwpx|\\.hwp)")
DOWNLOAD_RE = re.compile(r"(?i)(download|Content-Disposition|sendResponseHeaders|outputFileName|artifact|localPath)")
SIZE_RE = re.compile(r"(?i)(MAX_.*BYTES|fileBytes\.length|data\.length|size\(|too large|Content-Length)")
EXT_RE = re.compile(r"(?i)(\\.hwpx|\\.hwp|\\.xlsx|\\.xlsm|\\.csv|endsWith|extension|allowlist|contentType)")
PATH_TRAVERSAL_RE = re.compile(r"(?i)(\.\.|normalize\(|startsWith\(|resolve\(|sanitize|safeOutputName|filename\.contains)")
HWPX_PACKAGE_RE = re.compile(r"(?i)(ZipFile|ZipInputStream|zipfile|mimetype|manifest|section|xml|package validation|validate)")
EXCEL_VALIDATION_RE = re.compile(r"(?i)(WorkbookFactory|RawWorkbookParser|XSSFWorkbook|sheet|workbook|formula|macro|external)")
HWP_RE = re.compile(r"(?i)(\\.hwp|HwpToHwpx|Hancom|hwp-to-hwpx|convert-hwp)")
LOCAL_GATE_RE = re.compile(r"(?i)(WORKER_TOKEN_REQUIRED|isWorkerTokenAccepted|X-Conversion-Gate|LOCAL_WORKER_REQUIRED|local worker|user_present|X-Converter-Provider)")
META_RE = re.compile(r"(?s)(schemaVersion).{0,500}(engineVersion).{0,500}(requestId)|requestId.{0,500}schemaVersion.{0,500}engineVersion")
RAW_PATH_RESPONSE_RE = re.compile(r"(?i)(outputFilePath|getAbsolutePath|X-Hwpx-Editor-Saved-Path|localPath)")
ENGINE_DETAIL_RE = re.compile(r"(?i)(RawWorkbookParser|SemanticLayerBuilder|ContractBillNormalizer|ProgressBillBuilder|PythonScriptBridge|HwpToHwpx|hwpx_edit|plan-json)")
RESPONSE_RE = re.compile(r"(?i)(send\(|toJson|response|Map<String, Object>|sendResponseHeaders)")


@dataclass
class Finding:
    severity: str
    rule: str
    path: str
    detail: str


def repo_files() -> list[Path]:
    out = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT)
    files: list[Path] = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        rel = Path(raw.decode("utf-8", errors="replace"))
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            continue
        if rel.suffix.lower() in TEXT_SUFFIXES:
            files.append(rel)
    return files


def read(path: Path) -> str:
    try:
        return (ROOT / path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def is_handler(path: Path) -> bool:
    s = path.as_posix()
    return s.startswith("src/main/java/com/haehan/engine/http/") and s.endswith("Handler.java")


def line_count(path: Path) -> int:
    text = read(path)
    return text.count("\n") + (1 if text else 0)


def discover_endpoints(files: list[Path]) -> list[dict]:
    server = Path("src/main/java/com/haehan/engine/http/EngineHttpServer.java")
    text = read(server)
    endpoints: list[dict] = []
    for match in CREATE_CONTEXT_RE.finditer(text):
        endpoints.append({
            "path": match.group(1),
            "handler": match.group(2),
            "source": server.as_posix(),
        })
    return endpoints


def audit() -> dict:
    files = repo_files()
    findings: list[Finding] = []
    endpoints = discover_endpoints(files)
    upload_handlers: list[str] = []
    download_handlers: list[str] = []
    generate_handlers: list[str] = []
    convert_handlers: list[str] = []
    local_worker_candidates: list[str] = []
    large_handlers: list[dict] = []
    meta_missing_candidates: list[str] = []

    for path in files:
        s = path.as_posix()
        text = read(path)
        head = text[:20000]
        if not is_handler(path):
            continue

        lines = line_count(path)
        if lines >= 500:
            large_handlers.append({"path": s, "lines": lines})
            findings.append(Finding("WARN", "large_handler_candidate", s, f"handler has {lines} lines; split plan required"))

        is_upload = bool(UPLOAD_RE.search(head))
        is_download = bool(DOWNLOAD_RE.search(head))
        if is_upload:
            upload_handlers.append(s)
            if not EXT_RE.search(head):
                findings.append(Finding("WARN", "upload_extension_gate_unclear", s, "upload handler lacks visible extension/file type gate signal"))
            if not SIZE_RE.search(head):
                findings.append(Finding("WARN", "upload_size_limit_unclear", s, "upload handler lacks visible file size limit signal"))
            if not PATH_TRAVERSAL_RE.search(head):
                findings.append(Finding("WARN", "upload_path_traversal_gate_unclear", s, "upload handler lacks visible filename/path traversal defense signal"))

        if is_download:
            download_handlers.append(s)
            if RAW_PATH_RESPONSE_RE.search(head):
                findings.append(Finding("WARN", "raw_path_response_candidate", s, "handler may expose raw filesystem path/header; prefer artifact id or sanitized metadata"))
            if not PATH_TRAVERSAL_RE.search(head) and re.search(r"(?i)(filename|download|Content-Disposition)", head):
                findings.append(Finding("WARN", "download_filename_sanitize_unclear", s, "download/output filename sanitize signal is unclear"))

        if re.search(r"(?i)(generate|render|build|standardize|editor)", s + "\n" + head):
            generate_handlers.append(s)
        if re.search(r"(?i)(convert|HwpToHwpx|hwp-to-hwpx)", s + "\n" + head):
            convert_handlers.append(s)
        if HWP_RE.search(s + "\n" + head):
            local_worker_candidates.append(s)
            if "ConvertHwpToHwpxHandler.java" in s and LOCAL_GATE_RE.search(head):
                findings.append(Finding("WARN", "hwp_route_requires_stronger_local_worker_boundary", s, ".hwp conversion route has worker token/gate signals but should be isolated behind explicit LocalWorkerAdapter in P6"))
            elif "HwpxUploadHandler.java" in s:
                findings.append(Finding("WARN", "hwp_upload_ui_local_worker_boundary_unclear", s, "HWP upload UI references conversion flow; P6 should route it through explicit LocalWorkerAdapter/API gate"))
            elif not LOCAL_GATE_RE.search(head):
                findings.append(Finding("FAIL", "hwp_hancom_without_local_worker_gate", s, "HWP/Hancom route lacks visible local worker/user-present gate signal"))

        if "Hwpx" in s or "hwpx" in head.lower():
            if is_upload and not HWPX_PACKAGE_RE.search(head):
                findings.append(Finding("WARN", "hwpx_package_validation_unclear", s, "HWPX upload path lacks visible package validation signal"))
        if re.search(r"(?i)(Workbook|xlsx|xlsm)", s + "\n" + head):
            if is_upload and not EXCEL_VALIDATION_RE.search(head):
                findings.append(Finding("WARN", "excel_validation_unclear", s, "Excel upload path lacks visible workbook validation signal"))

        if RESPONSE_RE.search(head) and not META_RE.search(head):
            meta_missing_candidates.append(s)
            findings.append(Finding("WARN", "api_meta_contract_missing_candidate", s, "handler response may not include schemaVersion/engineVersion/requestId meta contract"))

        if ENGINE_DETAIL_RE.search(head) and lines >= 80:
            findings.append(Finding("WARN", "handler_contains_engine_detail", s, "handler contains engine/usecase detail signals; P6 split should keep handler thin"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")
    return {
        "audit": "api_upload_download_gates",
        "status": status,
        "files_scanned": len(files),
        "endpoint_count": len(endpoints),
        "upload_handler_count": len(upload_handlers),
        "download_handler_count": len(download_handlers),
        "generate_handler_count": len(generate_handlers),
        "convert_handler_count": len(convert_handlers),
        "local_worker_candidate_count": len(local_worker_candidates),
        "large_handler_count": len(large_handlers),
        "meta_missing_candidate_count": len(meta_missing_candidates),
        "finding_count": len(findings),
        "endpoints": endpoints,
        "upload_handlers": upload_handlers[:80],
        "download_handlers": download_handlers[:80],
        "generate_handlers": generate_handlers[:80],
        "convert_handlers": convert_handlers[:80],
        "local_worker_candidates": local_worker_candidates[:80],
        "large_handlers": large_handlers,
        "meta_missing_candidates": meta_missing_candidates[:80],
        "findings": [asdict(f) for f in findings[:250]],
        "policy": {
            "hwp": "LOCAL_WORKER_REQUIRED",
            "hwpx": "SERVER_ALLOWED_AFTER_PACKAGE_VALIDATION",
            "xlsx": "SERVER_ALLOWED_AFTER_EXCEL_VALIDATION",
            "download": "ARTIFACT_ID_AND_OUTPUT_GATE_REQUIRED",
            "meta": ["schemaVersion", "engineVersion", "requestId"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"api_upload_download_gate_status={result['status']}")
    print(f"files_scanned={result['files_scanned']}")
    print(f"endpoint_count={result['endpoint_count']}")
    print(f"upload_handler_count={result['upload_handler_count']}")
    print(f"download_handler_count={result['download_handler_count']}")
    print(f"large_handler_count={result['large_handler_count']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"{item['severity']} {item['rule']} {item['path']}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
