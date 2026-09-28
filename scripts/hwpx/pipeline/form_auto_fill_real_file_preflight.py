"""SANDBOX_ONLY preflight for sanitized real-like HWPX samples.

HWPX-FORM-AUTO-FILL-WRITER-REAL-FILE-PREFLIGHT-09

This module is a safety gate before a real-like file enters the sandbox writer.
It accepts sanitized, non-user HWPX samples only and never writes to the source.
Reports intentionally avoid raw paths, raw filenames, and raw field values.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from hwpx.pipeline.approval_gate import ACTION_CONFIRM, ApprovalResult, ApprovedField
from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write
from hwpx.pipeline.form_writer_download_review import (
    ACTION_ACCEPT,
    apply_review_decision_from_dict,
    build_download_payload,
)
from hwpx.pipeline.form_writer_final_export_gate import build_final_export_payload
from hwpx.pipeline.form_writer_readback_hardening import verify_readback

SCHEMA_VERSION = "form_auto_fill_real_file_preflight_v1"
MODE = "SANDBOX_ONLY"
SOURCE_MUTATION_ALLOWED = False
TARGET_CONFIDENCE_MIN = 0.80

READY_FOR_SANDBOX_WRITE = "READY_FOR_SANDBOX_WRITE"
BLOCKED_PII_RISK = "BLOCKED_PII_RISK"
BLOCKED_RAW_PATH_RISK = "BLOCKED_RAW_PATH_RISK"
BLOCKED_RAW_FILENAME_RISK = "BLOCKED_RAW_FILENAME_RISK"
BLOCKED_INVALID_HWPX = "BLOCKED_INVALID_HWPX"
BLOCKED_MISSING_SECTION_XML = "BLOCKED_MISSING_SECTION_XML"
BLOCKED_NO_TARGET_MAP = "BLOCKED_NO_TARGET_MAP"
BLOCKED_AMBIGUOUS_TARGET = "BLOCKED_AMBIGUOUS_TARGET"
BLOCKED_LOW_TARGET_CONFIDENCE = "BLOCKED_LOW_TARGET_CONFIDENCE"
BLOCKED_NO_APPROVED_FIELDS = "BLOCKED_NO_APPROVED_FIELDS"
BLOCKED_SOURCE_MUTATION_RISK = "BLOCKED_SOURCE_MUTATION_RISK"
BLOCKED_READBACK_FAILED = "BLOCKED_READBACK_FAILED"
BLOCKED_UNEXPECTED_MUTATION = "BLOCKED_UNEXPECTED_MUTATION"

SAMPLE_POLICY = {
    "synthetic": "Allowed for negative and control tests.",
    "realLikeSanitized": (
        "Allowed only after removing or masking personal data, project names, "
        "addresses, phone numbers, business numbers, account numbers, and raw filenames."
    ),
    "realUserFileUsed": False,
    "recommendedLocation": "data/fixtures/hwpx/real_like_sanitized/",
    "commitPolicy": "Do not commit actual HWPX samples or generated output HWPX files.",
}

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
SECTION_RE = re.compile(r"Contents/section\d+\.xml", re.IGNORECASE)
ABS_PATH_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]:[\\/]|/(home|tmp|var|Users)/)")
RAW_FILENAME_RE = re.compile(r"\b[^\\/:\s]+\.hwpx\b", re.IGNORECASE)
PII_RE = re.compile(
    r"(\d{6}-\d{7}|\d{3}-\d{2}-\d{5}|\d{2,3}-\d{3,4}-\d{4}|"
    r"\d{2,6}-\d{2,6}-\d{2,6}|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})"
)


@dataclass
class TargetMapEntry:
    fieldKey: str
    label: str
    sectionName: str
    tableIndex: int
    row: int
    col: int
    confidence: float


@dataclass
class PreflightInput:
    sample_path: Path
    target_map: list[TargetMapEntry] | None
    approved_fields: list[ApprovedField]
    output_dir: Path
    sample_id: str = "real_like_hwpx_001"
    accept_output: bool = True


@dataclass
class RealFilePreflightResult:
    schemaVersion: str = SCHEMA_VERSION
    sampleId: str = ""
    mode: str = MODE
    preflightStatus: str = BLOCKED_INVALID_HWPX
    sourceMutationAllowed: bool = SOURCE_MUTATION_ALLOWED
    sourceHashBefore: str = ""
    sourceHashAfter: str = ""
    sourceMtimeChanged: bool = False
    structure: dict[str, Any] = field(default_factory=dict)
    targetMap: dict[str, Any] = field(default_factory=dict)
    sandboxResult: dict[str, Any] = field(default_factory=dict)
    security: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "sampleId": self.sampleId,
            "mode": self.mode,
            "preflightStatus": self.preflightStatus,
            "sourceMutationAllowed": self.sourceMutationAllowed,
            "sourceHashBefore": self.sourceHashBefore,
            "sourceHashAfter": self.sourceHashAfter,
            "sourceMtimeChanged": self.sourceMtimeChanged,
            "structure": self.structure,
            "targetMap": self.targetMap,
            "sandboxResult": self.sandboxResult,
            "security": self.security,
            "warnings": self.warnings,
        }


def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _sample_id_from_path(path: Path) -> str:
    return "sample_" + hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:12]


def _safe_security(
    pii: bool = False, raw_path: bool = False, raw_filename: bool = False
) -> dict[str, Any]:
    return {
        "piiLeak": pii,
        "rawPathLeak": raw_path,
        "rawFilenameLeak": raw_filename,
        "aiCalled": False,
        "ocrCalled": False,
        "hancomRequired": False,
    }


@dataclass
class BlockedResultDetails:
    source_hash_before: str = ""
    source_hash_after: str = ""
    mtime_changed: bool = False
    structure: dict[str, Any] | None = None
    target_map: dict[str, Any] | None = None
    security: dict[str, Any] | None = None
    warnings: list[str] | None = None


def _blocked_result(
    inp: PreflightInput, status: str, details: BlockedResultDetails | None = None
) -> RealFilePreflightResult:
    d = details or BlockedResultDetails()
    return RealFilePreflightResult(
        sampleId=inp.sample_id or _sample_id_from_path(inp.sample_path),
        preflightStatus=status,
        sourceHashBefore=d.source_hash_before,
        sourceHashAfter=d.source_hash_after or d.source_hash_before,
        sourceMtimeChanged=d.mtime_changed,
        structure=d.structure or _empty_structure(),
        targetMap=d.target_map or _empty_target_map(),
        sandboxResult=_empty_sandbox_result(),
        security=d.security or _safe_security(),
        warnings=d.warnings or ["WARN_SANDBOX_ONLY"],
    )


def _empty_structure() -> dict[str, Any]:
    return {
        "zipValid": False,
        "sectionXmlValid": False,
        "tableCount": 0,
        "cellCount": 0,
        "paragraphCount": 0,
    }


def _empty_target_map() -> dict[str, Any]:
    return {"resolvedTargets": 0, "ambiguousTargets": 0, "lowConfidenceTargets": 0}


def _empty_sandbox_result() -> dict[str, Any]:
    return {
        "writtenFields": 0,
        "readbackPass": 0,
        "readbackFail": 0,
        "unexpectedMutation": 0,
        "finalExportEnabled": False,
    }


def _read_zip_texts(path: Path) -> tuple[bool, list[str], list[str]]:
    if not path.exists() or not zipfile.is_zipfile(path):
        return False, [], []
    texts: list[str] = []
    names: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            for name in names:
                try:
                    data = archive.read(name)
                except KeyError:
                    continue
                if name.lower().endswith((".xml", ".txt", ".rels")):
                    texts.append(data.decode("utf-8", errors="ignore"))
    except zipfile.BadZipFile:
        return False, [], []
    return True, names, texts


def _scan_security(path: Path, texts: list[str]) -> tuple[dict[str, Any], str]:
    combined = "\n".join(texts)
    raw_bytes_text = ""
    if path.exists() and not texts:
        raw_bytes_text = path.read_bytes()[:4096].decode("utf-8", errors="ignore")
    scanned = combined + "\n" + raw_bytes_text
    security = _safe_security(
        pii=bool(PII_RE.search(scanned)),
        raw_path=bool(ABS_PATH_RE.search(scanned)),
        raw_filename=bool(RAW_FILENAME_RE.search(scanned)),
    )
    if security["piiLeak"]:
        return security, BLOCKED_PII_RISK
    if security["rawPathLeak"]:
        return security, BLOCKED_RAW_PATH_RISK
    if security["rawFilenameLeak"]:
        return security, BLOCKED_RAW_FILENAME_RISK
    return security, ""


def inspect_hwpx_structure(path: Path) -> dict[str, Any]:
    if not path.exists() or not zipfile.is_zipfile(path):
        return _empty_structure()

    section_xml_valid = True
    section_count = 0
    table_count = 0
    cell_count = 0
    paragraph_count = 0

    try:
        with zipfile.ZipFile(path) as archive:
            section_names = sorted(name for name in archive.namelist() if SECTION_RE.match(name))
            section_count = len(section_names)
            if not section_names:
                return {
                    "zipValid": True,
                    "sectionXmlValid": False,
                    "tableCount": 0,
                    "cellCount": 0,
                    "paragraphCount": 0,
                }
            for name in section_names:
                try:
                    root = ET.fromstring(archive.read(name).decode("utf-8"))
                except (ET.ParseError, UnicodeDecodeError, KeyError):
                    section_xml_valid = False
                    continue
                table_count += len(root.findall(f".//{{{NS_HP}}}tbl"))
                paragraph_count += len(root.findall(f".//{{{NS_HP}}}p"))
                for table in root.findall(f".//{{{NS_HP}}}tbl"):
                    for row in table.findall(f"{{{NS_HP}}}tr"):
                        cell_count += len(row.findall(f"{{{NS_HP}}}tc"))
    except zipfile.BadZipFile:
        return _empty_structure()

    return {
        "zipValid": True,
        "sectionXmlValid": section_xml_valid and section_count > 0,
        "tableCount": table_count,
        "cellCount": cell_count,
        "paragraphCount": paragraph_count,
    }


def _target_map_summary(target_map: list[TargetMapEntry] | None) -> tuple[dict[str, Any], str]:
    if target_map is None:
        return _empty_target_map(), BLOCKED_NO_TARGET_MAP
    if not target_map:
        return _empty_target_map(), BLOCKED_NO_TARGET_MAP

    field_locs: dict[str, set[tuple[Any, ...]]] = {}
    low_conf = 0
    for target in target_map:
        loc = (target.sectionName, target.tableIndex, target.row, target.col)
        field_locs.setdefault(target.fieldKey, set()).add(loc)
        if target.confidence < TARGET_CONFIDENCE_MIN:
            low_conf += 1

    ambiguous = sum(1 for locs in field_locs.values() if len(locs) > 1)
    summary = {
        "resolvedTargets": len(target_map),
        "ambiguousTargets": ambiguous,
        "lowConfidenceTargets": low_conf,
    }
    if ambiguous:
        return summary, BLOCKED_AMBIGUOUS_TARGET
    if low_conf:
        return summary, BLOCKED_LOW_TARGET_CONFIDENCE
    return summary, ""


def _approved_summary(approved_fields: list[ApprovedField]) -> str:
    eligible = [field for field in approved_fields if field.writerEligible and field.value]
    return "" if eligible else BLOCKED_NO_APPROVED_FIELDS


def _writer_ui_result(writer_dict: dict[str, Any]) -> dict[str, Any]:
    summary = writer_dict.get("summary", {})
    readback_fail = summary.get("readbackFail", 0)
    source_mutated = bool(writer_dict.get("sourceMutated"))
    output_hash = writer_dict.get("outputHash", "")
    writer_status = (
        "SUCCESS"
        if readback_fail == 0 and not source_mutated and output_hash
        else "FAILED_READBACK"
    )
    return {
        "schemaVersion": "form_writer_ui_result_v1",
        "writerStatus": writer_status,
        "summary": {
            "written": summary.get("written", 0),
            "blocked": summary.get("blocked", 0),
            "readbackPass": summary.get("readbackPass", 0),
            "readbackFail": readback_fail,
            "sourceMutated": source_mutated,
        },
        "output": {
            "outputFileId": "out_" + hashlib.sha256(output_hash.encode("utf-8")).hexdigest()[:12]
            if output_hash
            else "",
            "outputHash": output_hash[:16],
            "downloadEnabled": writer_status == "SUCCESS",
        },
        "fieldResults": [],
        "warnings": list(writer_dict.get("warnings", [])),
        "security": {
            "sourceMutationAllowed": False,
            "rawPathVisible": False,
            "rawFilenameVisible": False,
            "piiMasked": True,
        },
    }


def run_real_file_preflight(
    sample_path: Path,
    target_map: list[TargetMapEntry] | list[dict[str, Any]] | None,
    approved_fields: list[ApprovedField] | list[dict[str, Any]],
    output_dir: Path,
    sample_id: str = "real_like_hwpx_001",
    accept_output: bool = True,
) -> dict[str, Any]:
    """Run real-like sanitized HWPX preflight and optional sandbox writer."""
    normalized_targets = normalize_target_map(target_map)
    normalized_fields = normalize_approved_fields(approved_fields)
    inp = PreflightInput(
        sample_path=Path(sample_path),
        target_map=normalized_targets,
        approved_fields=normalized_fields,
        output_dir=Path(output_dir),
        sample_id=sample_id,
        accept_output=accept_output,
    )

    before_hash = _sha16(inp.sample_path) if inp.sample_path.exists() else ""
    before_mtime = inp.sample_path.stat().st_mtime_ns if inp.sample_path.exists() else 0

    zip_ok, _names, texts = _read_zip_texts(inp.sample_path)
    if not zip_ok:
        after_hash = _sha16(inp.sample_path) if inp.sample_path.exists() else ""
        after_mtime = inp.sample_path.stat().st_mtime_ns if inp.sample_path.exists() else 0
        return _blocked_result(
            inp,
            BLOCKED_INVALID_HWPX,
            BlockedResultDetails(
                source_hash_before=before_hash,
                source_hash_after=after_hash,
                mtime_changed=after_mtime != before_mtime,
                security=_safe_security(),
                warnings=["WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY", "WARN_SANDBOX_ONLY"],
            ),
        ).to_dict()

    structure = inspect_hwpx_structure(inp.sample_path)
    security, security_block = _scan_security(inp.sample_path, texts)
    target_summary, target_block = _target_map_summary(inp.target_map)
    approved_block = _approved_summary(inp.approved_fields)

    if not structure["sectionXmlValid"]:
        status = BLOCKED_MISSING_SECTION_XML
    elif security_block:
        status = security_block
    elif target_block:
        status = target_block
    elif approved_block:
        status = approved_block
    else:
        status = READY_FOR_SANDBOX_WRITE

    if status != READY_FOR_SANDBOX_WRITE:
        after_hash = _sha16(inp.sample_path)
        after_mtime = inp.sample_path.stat().st_mtime_ns
        return _blocked_result(
            inp,
            status,
            BlockedResultDetails(
                source_hash_before=before_hash,
                source_hash_after=after_hash,
                mtime_changed=after_mtime != before_mtime,
                structure=structure,
                target_map=target_summary,
                security=security,
                warnings=["WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY", "WARN_SANDBOX_ONLY"],
            ),
        ).to_dict()

    approval = ApprovalResult(
        formId=inp.sample_id,
        formName="sanitized real-like sample",
        approvedFields=inp.approved_fields,
        pendingFields=[],
        writerEnabled=False,
    )

    writer = run_sandbox_write(approval, inp.sample_path, inp.output_dir, dry_run=False)
    writer_dict = writer.to_dict()
    output_path = inp.output_dir / "output" / f"sandbox_{inp.sample_path.stem}.hwpx"
    readback = verify_readback(inp.sample_path, output_path, inp.approved_fields, writer_dict)

    after_hash = _sha16(inp.sample_path)
    after_mtime = inp.sample_path.stat().st_mtime_ns
    mtime_changed = after_mtime != before_mtime
    source_mutated = before_hash != after_hash or mtime_changed or writer.sourceMutated

    readback_summary = readback.summary
    final_export_enabled = False
    if (
        readback_summary["readbackFail"] == 0
        and readback_summary["unexpectedMutation"] == 0
        and not source_mutated
    ):
        ui_result = _writer_ui_result(writer_dict)
        download_payload = build_download_payload(
            ui_result,
            form_id=inp.sample_id,
            display_name="sanitized_review_copy",
            source_template_hash=before_hash,
        )
        if inp.accept_output:
            decision = apply_review_decision_from_dict(
                download_payload,
                {
                    "formId": inp.sample_id,
                    "outputFileId": download_payload["download"]["outputFileId"],
                    "action": ACTION_ACCEPT,
                    "decisionBy": "preflight",
                    "reason": "",
                },
            )
        else:
            decision = {
                "formId": inp.sample_id,
                "outputFileId": "",
                "action": "HOLD_REVIEW",
                "decisionResult": "REVIEW_ON_HOLD",
                "sourceMutated": False,
            }
        final_payload = build_final_export_payload(
            download_payload,
            decision,
            form_id=inp.sample_id,
            form_title="sanitized real-like sample",
            display_name="sanitized_final_candidate",
            source_template_hash=before_hash,
        )
        final_export_enabled = bool(final_payload.get("finalExportEnabled", False))

    if source_mutated:
        status = BLOCKED_SOURCE_MUTATION_RISK
    elif readback_summary["readbackFail"] > 0:
        status = BLOCKED_READBACK_FAILED
    elif readback_summary["unexpectedMutation"] > 0:
        status = BLOCKED_UNEXPECTED_MUTATION

    result = RealFilePreflightResult(
        sampleId=inp.sample_id,
        preflightStatus=status,
        sourceHashBefore=before_hash,
        sourceHashAfter=after_hash,
        sourceMtimeChanged=mtime_changed,
        structure=structure,
        targetMap=target_summary,
        sandboxResult={
            "writtenFields": writer.summary.get("written", 0),
            "readbackPass": readback_summary.get("readbackPass", 0),
            "readbackFail": readback_summary.get("readbackFail", 0),
            "unexpectedMutation": readback_summary.get("unexpectedMutation", 0),
            "finalExportEnabled": final_export_enabled,
        },
        security=security,
        warnings=["WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY", "WARN_SANDBOX_ONLY"],
    )
    return result.to_dict()


def normalize_target_map(
    target_map: list[TargetMapEntry] | list[dict[str, Any]] | None,
) -> list[TargetMapEntry] | None:
    if target_map is None:
        return None
    normalized: list[TargetMapEntry] = []
    for item in target_map:
        if isinstance(item, TargetMapEntry):
            normalized.append(item)
        else:
            normalized.append(
                TargetMapEntry(
                    fieldKey=str(item.get("fieldKey", "")),
                    label=str(item.get("label", "")),
                    sectionName=str(item.get("sectionName", "Contents/section0.xml")),
                    tableIndex=int(item.get("tableIndex", 0)),
                    row=int(item.get("row", 0)),
                    col=int(item.get("col", 1)),
                    confidence=float(item.get("confidence", 0.0)),
                )
            )
    return normalized


def normalize_approved_fields(
    approved_fields: list[ApprovedField] | list[dict[str, Any]],
) -> list[ApprovedField]:
    normalized: list[ApprovedField] = []
    for item in approved_fields:
        if isinstance(item, ApprovedField):
            normalized.append(item)
        else:
            normalized.append(
                ApprovedField(
                    fieldKey=str(item.get("fieldKey", "")),
                    label=str(item.get("label", "")),
                    value=str(item.get("value", "")),
                    originalValue=str(item.get("originalValue", "")),
                    action=str(item.get("action", ACTION_CONFIRM)),
                    sourceZone=str(item.get("sourceZone", "realLikeSanitized")),
                    confidence=float(item.get("confidence", 0.9)),
                    writerEligible=bool(item.get("writerEligible", True)),
                )
            )
    return normalized


def write_report(
    report: dict[str, Any], output_dir: Path, name: str = "real_file_preflight_summary.json"
) -> Path:
    """Write a PII-safe report. The caller controls the report directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if ABS_PATH_RE.search(payload) or RAW_FILENAME_RE.search(payload) or PII_RE.search(payload):
        raise ValueError("unsafe report payload")
    path = output_dir / name
    path.write_text(payload, encoding="utf-8")
    return path


def create_real_like_sanitized_hwpx(path: Path) -> Path:
    """Create a sanitized real-like fixture for tests and audits.

    The generated file is intended for temporary test directories, not commits.
    """
    rows = [
        ["Contractor", ""],
        ["Project Code", ""],
        ["Reviewer", ""],
        ["Attachment", "masked-ready"],
    ]
    cells_xml = lambda cells: "".join(
        f"<hp:tc><hp:p><hp:run><hp:t>{cell}</hp:t></hp:run></hp:p></hp:tc>" for cell in cells
    )
    rows_xml = "".join(f"<hp:tr>{cells_xml(row)}</hp:tr>" for row in rows)
    section_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<hp:sec xmlns:hp="{NS_HP}">'
        f"<hp:tbl>{rows_xml}</hp:tbl>"
        "</hp:sec>"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Contents/section0.xml", section_xml.encode("utf-8"))
        archive.writestr("Contents/metadata.xml", b"<meta><sanitized>true</sanitized></meta>")
    return path


def default_real_like_target_map() -> list[TargetMapEntry]:
    return [
        TargetMapEntry("contractorName", "Contractor", "Contents/section0.xml", 0, 0, 1, 0.95),
        TargetMapEntry("projectCode", "Project Code", "Contents/section0.xml", 0, 1, 1, 0.92),
        TargetMapEntry("reviewerName", "Reviewer", "Contents/section0.xml", 0, 2, 1, 0.90),
    ]


def default_real_like_approved_fields() -> list[ApprovedField]:
    return [
        ApprovedField(
            "contractorName",
            "Contractor",
            "MASKED_CO",
            "",
            ACTION_CONFIRM,
            "realLikeSanitized",
            0.95,
        ),
        ApprovedField(
            "projectCode",
            "Project Code",
            "PRJ_MASKED",
            "",
            ACTION_CONFIRM,
            "realLikeSanitized",
            0.92,
        ),
        ApprovedField(
            "reviewerName", "Reviewer", "MASKED_USER", "", ACTION_CONFIRM, "realLikeSanitized", 0.90
        ),
    ]


def _cli() -> int:
    import argparse
    import tempfile

    parser = argparse.ArgumentParser(description="Run sanitized real-like HWPX preflight")
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        sample = create_real_like_sanitized_hwpx(tmp / "sanitized_sample.hwpx")
        report = run_real_file_preflight(
            sample,
            default_real_like_target_map(),
            default_real_like_approved_fields(),
            Path(args.output_dir) if args.output_dir else tmp / "out",
            sample_id="real_like_hwpx_001",
            accept_output=True,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["preflightStatus"] == READY_FOR_SANDBOX_WRITE else 1


if __name__ == "__main__":
    raise SystemExit(_cli())
