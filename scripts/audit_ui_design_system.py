#!/usr/bin/env python3
"""Read-only P12B audit: UI design system standard lock check."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH_DIR = ROOT / "docs/architecture"
HTTP_DIR = ROOT / "src/main/java/com/haehan/engine/http"

REQUIRED_UI_DOCS = [
    "ui_design_system_20260515.md",
    "ui_design_system_20260515.json",
    "hwpx_editor_ui_layout_20260515.md",
    "hwpx_editor_ui_layout_20260515.json",
    "ui_component_rules_20260515.md",
    "ui_component_rules_20260515.json",
    "hwpx_editor_ui_state_policy_20260515.md",
    "hwpx_editor_ui_state_policy_20260515.json",
]

REQUIRED_BRAND_COLORS = [
    "#F97316",  # primary
    "#EA580C",  # primary hover
    "#FFF7ED",  # primary soft
    "#0F172A",  # navy
    "#1E293B",  # navy secondary
    "#F1F5F9",  # navy soft
    "#F5F7FA",  # bg
    "#111827",  # text primary
    "#4B5563",  # text secondary
    "#6B7280",  # text muted
    "#E5E7EB",  # border
]

REQUIRED_COMPONENTS = [
    "TopAccentLine",
    "HeaderBar",
    "StatusBadge",
    "UploadCard",
    "GateStatusPanel",
    "EditorToolbar",
    "DocumentTree",
    "ValidationPanel",
    "CommandResultPanel",
    "DownloadPanel",
    "ArtifactInfoPanel",
    "ErrorBoundaryPanel",
]

REQUIRED_STATUSES = [
    "PASS", "WARN", "FAIL",
    "DRY_RUN", "LOCAL_WORKER_REQUIRED", "USER_PRESENT_REQUIRED",
    "SAVED", "ERROR",
]

REQUIRED_PHASES = [
    "IDLE", "UPLOADING", "UPLOADED", "PARSING",
    "READY", "EDITING", "VALIDATING", "DRY_RUN",
    "SAVING", "EXPORTED", "ERROR",
]


@dataclass
class Finding:
    severity: str
    rule: str
    file: str
    detail: str


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def audit() -> dict:
    findings: list[Finding] = []

    # 1. Required docs present
    doc_status: dict[str, bool] = {}
    for doc in REQUIRED_UI_DOCS:
        exists = (ARCH_DIR / doc).exists()
        doc_status[doc] = exists
        if not exists:
            findings.append(Finding("FAIL", "ui_doc_missing", doc, f"Required UI doc not found: {doc}"))

    # 2. Brand colors in design system doc
    design_text = read(ARCH_DIR / "ui_design_system_20260515.md")
    design_json_text = read(ARCH_DIR / "ui_design_system_20260515.json")
    color_status: dict[str, bool] = {}
    for color in REQUIRED_BRAND_COLORS:
        found = color.upper() in design_text.upper() or color.upper() in design_json_text.upper()
        color_status[color] = found
        if not found:
            findings.append(Finding("FAIL", "brand_color_missing",
                                    "ui_design_system_20260515.md/json",
                                    f"Brand color {color} not found in design system docs"))

    # 3. Top Accent Line rule
    top_accent_in_design = "4px" in design_text and "#F97316" in design_text and "top" in design_text.lower()
    top_accent_in_layout = "4px" in read(ARCH_DIR / "hwpx_editor_ui_layout_20260515.md") and "F97316" in read(ARCH_DIR / "hwpx_editor_ui_layout_20260515.md")
    if not top_accent_in_design or not top_accent_in_layout:
        findings.append(Finding("FAIL", "top_accent_line_rule_missing",
                                "ui_design_system_20260515.md",
                                "Top Accent Line (4px #F97316 fixed-top) rule not documented"))

    # 4. Component rules present
    component_text = read(ARCH_DIR / "ui_component_rules_20260515.md")
    component_json_text = read(ARCH_DIR / "ui_component_rules_20260515.json")
    component_status: dict[str, bool] = {}
    for comp in REQUIRED_COMPONENTS:
        found = comp in component_text or comp in component_json_text
        component_status[comp] = found
        if not found:
            findings.append(Finding("WARN", "component_rule_missing",
                                    "ui_component_rules_20260515.md",
                                    f"Component rule not found: {comp}"))

    # 5. Status badge coverage
    badge_text = read(ARCH_DIR / "ui_design_system_20260515.md")
    status_status: dict[str, bool] = {}
    for status in REQUIRED_STATUSES:
        found = status in badge_text
        status_status[status] = found
        if not found:
            findings.append(Finding("WARN", "status_badge_missing",
                                    "ui_design_system_20260515.md",
                                    f"StatusBadge state not documented: {status}"))

    # 6. UI state phases coverage
    state_text = read(ARCH_DIR / "hwpx_editor_ui_state_policy_20260515.md")
    state_json_text = read(ARCH_DIR / "hwpx_editor_ui_state_policy_20260515.json")
    phase_status: dict[str, bool] = {}
    for phase in REQUIRED_PHASES:
        found = phase in state_text or phase in state_json_text
        phase_status[phase] = found
        if not found:
            findings.append(Finding("WARN", "ui_phase_missing",
                                    "hwpx_editor_ui_state_policy_20260515.md",
                                    f"UI phase not documented: {phase}"))

    # 7. Policy checks in docs
    layout_text = read(ARCH_DIR / "hwpx_editor_ui_layout_20260515.md")
    combined = design_text + layout_text + component_text + state_text

    artifact_id_policy = "artifactId" in combined
    raw_path_forbidden = "raw path" in combined.lower() or "raw_path" in combined
    xml_zip_forbidden = "XML/ZIP" in combined or "xml_zip" in combined.lower() or "HWPX XML" in combined
    command_only_browser = "command" in combined and "브라우저" in combined
    download_panel_forbidden = "DownloadPanel" in component_text and "raw_filesystem_path" in (component_json_text + layout_text)
    gate_status_panel = "GateStatusPanel" in component_text

    if not artifact_id_policy:
        findings.append(Finding("FAIL", "artifact_id_policy_missing", "ui docs",
                                "artifactId display policy not documented"))
    if not raw_path_forbidden:
        findings.append(Finding("FAIL", "raw_path_not_forbidden", "ui docs",
                                "raw path display forbidden policy not documented"))
    if not xml_zip_forbidden:
        findings.append(Finding("FAIL", "xml_zip_not_forbidden", "ui docs",
                                "XML/ZIP direct access forbidden policy not documented"))
    if not command_only_browser:
        findings.append(Finding("FAIL", "command_only_browser_missing", "ui docs",
                                "browser command-only principle not documented"))
    if not download_panel_forbidden:
        findings.append(Finding("WARN", "download_panel_raw_path_rule_incomplete",
                                "ui_component_rules_20260515",
                                "DownloadPanel raw path forbidden rule may be incomplete"))
    if not gate_status_panel:
        findings.append(Finding("WARN", "gate_status_panel_rule_missing",
                                "ui_component_rules_20260515.md",
                                "GateStatusPanel rule not found"))

    # 8. Check existing UI Java files for orange accent color
    styles_file = HTTP_DIR / "HwpxUploadPageStyles.java"
    styles_text = read(styles_file)
    orange_in_styles = "#F97316" in styles_text or "f97316" in styles_text.lower()
    navy_in_styles = "#0F172A" in styles_text or "#1E293B" in styles_text
    if not orange_in_styles:
        findings.append(Finding("WARN", "orange_accent_not_in_existing_styles",
                                "HwpxUploadPageStyles.java",
                                "Primary orange #F97316 not found in existing styles — may need alignment in P13"))
    if not navy_in_styles:
        findings.append(Finding("WARN", "navy_not_in_existing_styles",
                                "HwpxUploadPageStyles.java",
                                "Navy color not found in existing styles — may need alignment in P13"))

    # 9. Check no raw filesystem path in existing UI HTML
    view_file = HTTP_DIR / "HwpxUploadPageView.java"
    view_text = read(view_file)
    raw_path_in_view = any(p in view_text for p in ["/home/", "C:\\\\", "/var/", "/tmp/"])
    if raw_path_in_view:
        findings.append(Finding("FAIL", "raw_path_in_existing_view",
                                "HwpxUploadPageView.java",
                                "Raw filesystem path found in UI view — must be removed"))

    severities = {f.severity for f in findings}
    status = "FAIL" if "FAIL" in severities else ("WARN" if "WARN" in severities else "PASS")

    return {
        "audit": "ui_design_system",
        "phase": "P12B",
        "status": status,
        "ui_docs": doc_status,
        "brand_colors": color_status,
        "top_accent_line": top_accent_in_design and top_accent_in_layout,
        "components": component_status,
        "status_badges": status_status,
        "ui_phases": phase_status,
        "policies": {
            "artifact_id_policy": artifact_id_policy,
            "raw_path_forbidden": raw_path_forbidden,
            "xml_zip_forbidden": xml_zip_forbidden,
            "command_only_browser": command_only_browser,
            "download_panel_raw_path_rule": download_panel_forbidden,
            "gate_status_panel_rule": gate_status_panel,
        },
        "existing_ui": {
            "orange_accent_in_styles": orange_in_styles,
            "navy_in_styles": navy_in_styles,
            "no_raw_path_in_view": not raw_path_in_view,
        },
        "finding_count": len(findings),
        "findings": [asdict(f) for f in findings],
        "policy": {
            "no_endpoint_path_change": True,
            "no_api_response_key_change": True,
            "no_browser_hwpx_direct_access": True,
            "no_hancom_auto_run": True,
            "push_forbidden": True,
            "db_write_forbidden": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", dest="json_path")
    args = parser.parse_args()
    result = audit()
    print(f"ui_design_system_status={result['status']}")
    print(f"finding_count={result['finding_count']}")
    for item in result["findings"][:20]:
        print(f"  {item['severity']} [{item['file']}] {item['rule']}: {item['detail'][:80]}")
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
