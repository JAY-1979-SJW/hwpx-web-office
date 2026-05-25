"""Audit Web Office HWPX read remediation coverage.

This audit implements the remediation plan in
docs/architecture/web_office_hwpx_reading_scope_standard_20260525.md.

It does not certify full HWPX compatibility. It verifies that the current
fixture corpus is inventoried, that unsupported XML/package surface is reported
deterministically, and that the Web Office read model still loads without
mutating source files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "scripts" / "hwpx") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "hwpx"))

from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view  # noqa: E402
from scripts.hwpx.web_office.render_payload import build_render_payload  # noqa: E402


SCHEMA_VERSION = "web_office_hwpx_read_remediation_audit_v1"
PASS_VERDICT = "PASS_WEB_OFFICE_HWPX_READ_REMEDIATION_CURRENT_SCOPE"
FAIL_VERDICT = "FAIL_WEB_OFFICE_HWPX_READ_REMEDIATION"
STATUS_VALUE = "BASIC_READ_VERIFIED_FULL_READ_NOT_CLAIMED"

DEFAULT_CORPUS_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
DEFAULT_REPORT_DIR = (
    PROJECT_ROOT / "data" / "reports" / "web_office_hwpx_read_remediation"
)

SUPPORTED_CURRENT_XML_LOCALS = {
    "HCFVersion",
    "package",
    "metadata",
    "manifest",
    "item",
    "spine",
    "itemref",
    "head",
    "fontfaces",
    "fontface",
    "font",
    "styles",
    "charPr",
    "paraPr",
    "borderFills",
    "borderFill",
    "fillBrush",
    "winBrush",
    "sec",
    "p",
    "run",
    "t",
    "tbl",
    "tr",
    "tc",
    "cellAddr",
    "cellSpan",
    "cellSz",
    "subList",
    "linesegarray",
    "lineseg",
}

IGNORED_BY_POLICY_XML_LOCALS = {
    "container",
    "rootfiles",
    "rootfile",
    "masterPage",
    "mappingTable",
    "docOption",
    "trackchangelist",
    "forbiddenStringList",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_rel(path: Path) -> str:
    return str(path.resolve().relative_to(PROJECT_ROOT.resolve())).replace("\\", "/")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _load_manifest(corpus_dir: Path) -> dict[str, Any]:
    manifest_path = corpus_dir / "fixture_manifest.json"
    if not manifest_path.is_file():
        return {"fixtures": [], "manifestFound": False}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["manifestFound"] = True
    return payload


def _classify_xml_local(local: str) -> str:
    if local in SUPPORTED_CURRENT_XML_LOCALS:
        return "parsed_for_current_model"
    if local in IGNORED_BY_POLICY_XML_LOCALS:
        return "ignored_by_policy"
    return "unsupported_with_warning"


def _inspect_package(path: Path) -> dict[str, Any]:
    entry_count = 0
    xml_entries: list[str] = []
    non_xml_entries: list[str] = []
    element_counter: Counter[str] = Counter()
    package_findings: list[dict[str, Any]] = []

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        entry_count = len(names)
        for name in names:
            if name.endswith((".xml", ".hpf")):
                xml_entries.append(name)
                try:
                    root = ET.fromstring(zf.read(name))
                except Exception as exc:  # pragma: no cover - covered by payload
                    package_findings.append({
                        "code": "XML_PARSE_FAILED",
                        "entry": name,
                        "message": str(exc),
                    })
                    continue
                for elem in root.iter():
                    element_counter[_local_name(elem.tag)] += 1
            else:
                non_xml_entries.append(name)

    classifications: dict[str, dict[str, Any]] = {}
    for local, count in sorted(element_counter.items()):
        classifications[local] = {
            "count": count,
            "classification": _classify_xml_local(local),
        }

    unsupported = {
        local: item
        for local, item in classifications.items()
        if item["classification"] == "unsupported_with_warning"
    }
    ignored = {
        local: item
        for local, item in classifications.items()
        if item["classification"] == "ignored_by_policy"
    }
    parsed = {
        local: item
        for local, item in classifications.items()
        if item["classification"] == "parsed_for_current_model"
    }

    return {
        "entryCount": entry_count,
        "xmlEntryCount": len(xml_entries),
        "nonXmlEntryCount": len(non_xml_entries),
        "xmlEntries": xml_entries,
        "elementClassifications": classifications,
        "classificationSummary": {
            "parsedForCurrentModel": len(parsed),
            "ignoredByPolicy": len(ignored),
            "unsupportedWithWarning": len(unsupported),
        },
        "unsupportedElementLocals": sorted(unsupported),
        "ignoredElementLocals": sorted(ignored),
        "findings": package_findings,
    }


def _audit_fixture(path: Path, manifest_by_name: dict[str, dict[str, Any]]) -> dict[str, Any]:
    sha_before = _sha256(path)
    mtime_before = path.stat().st_mtime_ns
    findings: list[dict[str, Any]] = []

    try:
        package = _inspect_package(path)
    except Exception as exc:
        package = {}
        findings.append({"code": "PACKAGE_INSPECTION_FAILED", "message": str(exc)})

    try:
        doc = import_hwpx_as_ro_view(path)
        payload = build_render_payload(doc)
        model_counts = {
            "sections": len(doc.sections),
            "blocks": len(doc.blocks),
            "paragraphs": len(doc.paragraphs),
            "tables": len(doc.tables),
            "cells": len(doc.cells),
            "objects": len(doc.objects),
            "warnings": len(doc.warnings),
        }
        if doc.tables and not doc.cells:
            findings.append({"code": "TABLES_WITHOUT_CELLS"})
        if payload.get("editable") is not False:
            findings.append({"code": "PAYLOAD_EDITABLE_NOT_FALSE"})
    except Exception as exc:
        model_counts = {}
        findings.append({"code": "WEB_OFFICE_IMPORT_FAILED", "message": str(exc)})

    sha_after = _sha256(path)
    mtime_after = path.stat().st_mtime_ns
    if sha_after != sha_before or mtime_after != mtime_before:
        findings.append({"code": "SOURCE_MUTATED_DURING_READ"})

    manifest_entry = manifest_by_name.get(path.name)
    if manifest_entry is None:
        findings.append({"code": "MISSING_FIXTURE_MANIFEST_ENTRY"})

    return {
        "path": _safe_rel(path),
        "fileName": path.name,
        "fixtureId": (manifest_entry or {}).get("fixtureId"),
        "category": (manifest_entry or {}).get("category"),
        "sha256": sha_before,
        "sizeBytes": path.stat().st_size,
        "packageInventory": package,
        "webOfficeModelCounts": model_counts,
        "sourceUnchanged": sha_after == sha_before and mtime_after == mtime_before,
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def run_audit(
    *,
    corpus_dir: Path = DEFAULT_CORPUS_DIR,
    report_dir: Path = DEFAULT_REPORT_DIR,
    write_reports: bool = True,
) -> dict[str, Any]:
    corpus_dir = corpus_dir.resolve()
    report_dir = report_dir.resolve()
    manifest = _load_manifest(corpus_dir)
    manifest_entries = manifest.get("fixtures") or []
    manifest_by_name = {
        str(item.get("fileName")): item
        for item in manifest_entries
        if item.get("fileName")
    }
    files = sorted(p for p in corpus_dir.glob("*.hwpx") if p.is_file())

    fixture_results = [_audit_fixture(path, manifest_by_name) for path in files]
    unsupported_locals: set[str] = set()
    ignored_locals: set[str] = set()
    parsed_locals: set[str] = set()
    for result in fixture_results:
        inventory = result.get("packageInventory") or {}
        unsupported_locals.update(inventory.get("unsupportedElementLocals") or [])
        ignored_locals.update(inventory.get("ignoredElementLocals") or [])
        classifications = inventory.get("elementClassifications") or {}
        parsed_locals.update(
            local
            for local, item in classifications.items()
            if item.get("classification") == "parsed_for_current_model"
        )

    missing_manifest_files = sorted(
        name for name in manifest_by_name
        if not (corpus_dir / name).is_file()
    )
    failures = [
        {
            "path": result["path"],
            "findings": result["findings"],
        }
        for result in fixture_results
        if result["findings"]
    ]
    if not files:
        failures.append({"path": _safe_rel(corpus_dir), "findings": [{"code": "NO_HWPX_FIXTURES"}]})
    if missing_manifest_files:
        failures.append({
            "path": _safe_rel(corpus_dir / "fixture_manifest.json"),
            "findings": [{
                "code": "MANIFEST_REFERENCES_MISSING_FILES",
                "files": missing_manifest_files,
            }],
        })

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "task": "WEB-OFFICE-HWPX-READ-REMEDIATION-AUDIT-20260525",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "statusValue": STATUS_VALUE,
        "fullCompatibilityClaimed": False,
        "serverFinalReferenceRequired": True,
        "corpus": {
            "path": _safe_rel(corpus_dir),
            "manifestFound": bool(manifest.get("manifestFound")),
            "manifestFixtureCount": len(manifest_entries),
            "hwpxFileCount": len(files),
            "missingManifestFiles": missing_manifest_files,
        },
        "coverageSummary": {
            "parsedElementFamilies": sorted(parsed_locals),
            "ignoredByPolicyElementFamilies": sorted(ignored_locals),
            "unsupportedWithWarningElementFamilies": sorted(unsupported_locals),
            "unsupportedWithWarningCount": len(unsupported_locals),
        },
        "fixtures": fixture_results,
        "failures": failures,
        "requiredWording": (
            "Basic HWPX read is verified; full compatibility and UI fidelity remain open."
        ),
        "verdict": PASS_VERDICT if not failures else FAIL_VERDICT,
    }

    if write_reports:
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / "reading_remediation_report.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        (report_dir / "reading_remediation_summary.md").write_text(
            _format_markdown(payload),
            encoding="utf-8",
        )

    return payload


def _format_markdown(payload: dict[str, Any]) -> str:
    coverage = payload["coverageSummary"]
    corpus = payload["corpus"]
    lines = [
        "# Web Office HWPX Read Remediation Audit",
        "",
        f"- Verdict: `{payload['verdict']}`",
        f"- Status: `{payload['statusValue']}`",
        f"- Full compatibility claimed: `{payload['fullCompatibilityClaimed']}`",
        f"- Corpus files: `{corpus['hwpxFileCount']}`",
        f"- Manifest fixtures: `{corpus['manifestFixtureCount']}`",
        f"- Unsupported element families reported: `{coverage['unsupportedWithWarningCount']}`",
        "",
        "## Required Wording",
        "",
        payload["requiredWording"],
        "",
        "## Unsupported Element Families",
        "",
    ]
    unsupported = coverage["unsupportedWithWarningElementFamilies"]
    if unsupported:
        lines.extend(f"- `{item}`" for item in unsupported)
    else:
        lines.append("- none")
    lines.extend(["", "## Failures", ""])
    if payload["failures"]:
        lines.extend(f"- `{item['path']}`: `{item['findings']}`" for item in payload["failures"])
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, default=DEFAULT_CORPUS_DIR)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--no-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = run_audit(
        corpus_dir=args.corpus_dir,
        report_dir=args.report_dir,
        write_reports=not args.no_write,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(payload["verdict"])
    return 0 if payload["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
