"""Module ownership schema, routing, and gate checks for full-fidelity work."""

from __future__ import annotations

from typing import Any


ARCHITECTURE_SCHEMA_VERSION = 1

MODULE_ROUTES: list[dict[str, Any]] = [
    {
        "key": "architecture",
        "path": "scripts/hwpx/hwp_full_fidelity_architecture.py",
        "layer": "schema_gate_router",
        "owns": [
            "module ownership schema",
            "new-code routing",
            "architecture gate",
            "classification policy",
        ],
        "keywords": ["architecture", "module schema", "ownership", "router", "route", "gate", "classification", "분류", "구조"],
        "forbid_in_converter": True,
    },
    {
        "key": "security",
        "path": "scripts/hwpx/hwp_full_fidelity_security.py",
        "layer": "security_policy_gate",
        "owns": [
            "security policy",
            "forbidden capability checks",
            "security-sensitive change gate",
            "external dependency prohibition",
        ],
        "keywords": [
            "security",
            "secure",
            "forbidden",
            "network",
            "download",
            "subprocess",
            "shell",
            "hancom",
            "com automation",
            "gui automation",
            "credential",
            "token",
            "path traversal",
            "보안",
        ],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_api",
        "path": "scripts/hwpx/hwpx_api.py",
        "layer": "hwpx_editor_public_api",
        "owns": ["stable HWPX editor facade", "public direct-writer API", "builder API exports"],
        "keywords": ["hwpx api", "editor api", "direct writer api", "public facade", "document builder api"],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_schema",
        "path": "scripts/hwpx/hwpx_job_schema.py",
        "layer": "hwpx_editor_schema",
        "owns": ["compose job schema", "editor job validation", "declarative document input contract"],
        "keywords": ["job schema", "compose job schema", "compose schema", "editor schema", "schema validation", "declarative job"],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_composer",
        "path": "scripts/hwpx/hwpx_composer.py",
        "layer": "hwpx_editor_composition",
        "owns": ["declarative HWPX composition", "compose job execution order", "document composition orchestration"],
        "keywords": ["compose", "composer", "compose job", "compose document", "document composition"],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_adapter",
        "path": "scripts/hwpx/hwpx_writer_adapter.py",
        "layer": "hwpx_editor_compat_adapter",
        "owns": ["legacy HwpxEditor facade", "direct package editing adapter", "compatibility editor methods"],
        "keywords": ["hwpxeditor", "writer adapter", "editor adapter", "package editing", "direct edit"],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_package",
        "path": "scripts/hwpx/hwpx_package.py",
        "layer": "hwpx_editor_package_io",
        "owns": ["HWPX package IO", "ZIP/XML read-write helpers", "package validation primitives"],
        "keywords": ["hwpx package", "package io", "zip xml", "read xml", "write xml", "package helper"],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_text_ops",
        "path": "scripts/hwpx/hwpx_text_ops.py",
        "layer": "hwpx_editor_text_ops",
        "owns": ["placeholder replacement", "paragraph append", "text node editing"],
        "keywords": ["placeholder", "text op", "paragraph append", "replace text", "text node"],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_table_ops",
        "path": "scripts/hwpx/hwpx_table_ops.py",
        "layer": "hwpx_editor_table_ops",
        "owns": ["table render", "table row/cell updates", "table merge routing", "cell layout operation routing"],
        "keywords": ["table op", "table operation", "table merge", "merge cell", "cell layout", "append row", "delete row"],
        "accepted_paths": [
            "scripts/hwpx/hwpx_table_ops.py",
            "scripts/hwpx/hwpx_table_merge_ops.py",
            "scripts/hwpx/hwpx_table_cell_layout_ops.py",
            "scripts/hwpx/hwpx_table_cell_style.py",
            "scripts/hwpx/hwpx_table_dimension_style.py",
            "scripts/hwpx/hwpx_table_style_audit.py",
        ],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_image_ops",
        "path": "scripts/hwpx/hwpx_image_ops.py",
        "layer": "hwpx_editor_image_ops",
        "owns": ["BinData image insertion", "visible image operations", "picture clone/rebind", "image policy"],
        "keywords": ["image op", "picture", "bindata image", "visible image", "image policy", "chart png"],
        "accepted_paths": [
            "scripts/hwpx/hwpx_image_ops.py",
            "scripts/hwpx/hwpx_visible_image_ops.py",
            "scripts/hwpx/hwpx_picture_ops.py",
            "scripts/hwpx/hwpx_image_policy.py",
            "scripts/hwpx/hwpx_chart_png.py",
        ],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_page_section_ops",
        "path": "scripts/hwpx/hwpx_section_ops.py",
        "layer": "hwpx_editor_page_section_ops",
        "owns": ["section append/inspect", "page layout operations", "header/footer operations"],
        "keywords": ["section op", "page layout", "header footer", "page numbering", "append section"],
        "accepted_paths": [
            "scripts/hwpx/hwpx_section_ops.py",
            "scripts/hwpx/hwpx_page_layout_ops.py",
            "scripts/hwpx/hwpx_header_footer_ops.py",
        ],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_style_ops",
        "path": "scripts/hwpx/hwpx_style_ops.py",
        "layer": "hwpx_editor_style_ops",
        "owns": ["paragraph/table/image style normalization", "style resolver", "header/list/border style definitions"],
        "keywords": ["style op", "style resolver", "paragraph style", "table style", "list style", "border fill"],
        "accepted_paths": [
            "scripts/hwpx/hwpx_style_ops.py",
            "scripts/hwpx/hwpx_style_resolver.py",
            "scripts/hwpx/hwpx_header_style.py",
            "scripts/hwpx/hwpx_list_style_ops.py",
            "scripts/hwpx/hwpx_border_fill_style.py",
        ],
        "forbid_in_converter": True,
    },
    {
        "key": "hwpx_editor_gate_validation",
        "path": "scripts/hwpx/hwpx_write_gate.py",
        "layer": "hwpx_editor_gate_validation",
        "owns": ["write gate", "render validation", "capability coverage", "Java roundtrip gate", "editor regression"],
        "keywords": ["write gate", "render validation", "capability coverage", "java roundtrip", "editor regression", "full scenario"],
        "accepted_paths": [
            "scripts/hwpx/hwpx_write_gate.py",
            "scripts/hwpx/hwpx_validation.py",
            "scripts/hwpx/hwpx_capability_coverage.py",
            "scripts/hwpx/hwpx_java_roundtrip.py",
            "scripts/hwpx/hwpx_compose_regression.py",
            "scripts/hwpx/hwpx_full_scenario.py",
        ],
        "forbid_in_converter": True,
    },
    {
        "key": "converter",
        "path": "scripts/hwpx/hwp_full_fidelity_converter.py",
        "layer": "cli_orchestration",
        "owns": ["CLI argument parsing", "top-level conversion orchestration", "report writing", "legacy public aliases"],
        "keywords": ["cli", "argument", "command", "convert_full", "write_report", "entrypoint", "orchestration"],
        "forbid_in_converter": False,
    },
    {
        "key": "analyzer",
        "path": "scripts/hwpx/hwp_full_fidelity_analyzer.py",
        "layer": "analysis_pipeline",
        "owns": ["HWP OLE stream analysis", "record extraction", "analysis report assembly", "text extraction attachment"],
        "keywords": ["analyze", "ole", "stream", "record extraction", "docinfo records", "body records", "analysis"],
        "forbid_in_converter": True,
    },
    {
        "key": "decoders",
        "path": "scripts/hwpx/hwp_full_fidelity_decoders.py",
        "layer": "binary_decode",
        "owns": ["binary readers", "HWP record payload decoders", "tag-specific decoded dictionaries"],
        "keywords": ["decode", "decoder", "payload", "binary", "tag", "record", "u16", "u32"],
        "forbid_in_converter": True,
    },
    {
        "key": "coverage",
        "path": "scripts/hwpx/hwp_full_fidelity_coverage.py",
        "layer": "fidelity_gate",
        "owns": ["required record families", "coverage scoring", "blocker generation", "next decoder targets"],
        "keywords": ["coverage", "blocker", "fail-closed", "fidelity gate", "required family", "decoder target"],
        "forbid_in_converter": True,
    },
    {
        "key": "audit",
        "path": "scripts/hwpx/hwp_full_fidelity_audit.py",
        "layer": "audit_integrity",
        "owns": ["source manifest", "OLE metadata", "record audit", "embedded original integrity"],
        "keywords": ["audit", "manifest", "metadata", "integrity", "sha256", "original", "ole metadata"],
        "forbid_in_converter": True,
    },
    {
        "key": "header",
        "path": "scripts/hwpx/hwp_full_fidelity_header.py",
        "layer": "header_mapping",
        "owns": ["decoded DocInfo catalog", "Contents/header.xml generation", "list style mapping"],
        "keywords": ["header", "docinfo", "font", "border", "char shape", "para shape", "numbering", "bullet", "style"],
        "forbid_in_converter": True,
    },
    {
        "key": "layouts",
        "path": "scripts/hwpx/hwp_full_fidelity_layouts.py",
        "layer": "analysis_layout_catalog",
        "owns": ["body layout catalog", "page layout catalog", "table layout catalog from decoded HWP records"],
        "keywords": ["body layout", "page layout", "table layout", "paragraph catalog", "layout catalog"],
        "forbid_in_converter": True,
    },
    {
        "key": "section_updates",
        "path": "scripts/hwpx/hwp_full_fidelity_section_updates.py",
        "layer": "section_xml_bridge",
        "owns": ["HWPX section XML mutation", "paragraph style refs", "pagePr/margin", "table cell metrics"],
        "keywords": ["section xml", "body style", "pagepr", "margin", "cell metric", "celladdr", "cellspan", "lineSeg"],
        "forbid_in_converter": True,
    },
    {
        "key": "package",
        "path": "scripts/hwpx/hwp_full_fidelity_package.py",
        "layer": "package_injection",
        "owns": ["HWPX ZIP rewrite", "Preview JSON entries", "content.hpf header injection", "package analysis entries"],
        "keywords": ["zip", "package", "preview", "content.hpf", "inject", "entry", "rewrite"],
        "forbid_in_converter": True,
    },
]


def architecture_catalog() -> dict[str, Any]:
    return {
        "schema_version": ARCHITECTURE_SCHEMA_VERSION,
        "routes": MODULE_ROUTES,
        "rules": [
            "New feature code must route to the owning module before editing.",
            "hwp_full_fidelity_converter.py stays limited to CLI, convert orchestration, report writing, and compatibility aliases.",
            "Fail-closed policy, schema, gate, and router logic must be explicit modules, not inline converter code.",
            "Security policy, forbidden capability checks, and sensitive-operation gates must be explicit modules, not inline converter code.",
            "A new module must be added to this catalog before it becomes an accepted destination.",
        ],
    }


def route_new_code(summary: str) -> dict[str, Any]:
    text = summary.lower()
    scored: list[tuple[int, dict[str, Any], list[str]]] = []
    for route in MODULE_ROUTES:
        matches = [keyword for keyword in route["keywords"] if keyword.lower() in text]
        if matches:
            scored.append((len(matches), route, matches))
    if not scored:
        route = next(item for item in MODULE_ROUTES if item["key"] == "converter")
        return {
            "status": "REVIEW",
            "schema_version": ARCHITECTURE_SCHEMA_VERSION,
            "recommended_module": route["key"],
            "recommended_path": route["path"],
            "confidence": "low",
            "matched_keywords": [],
            "reason": "No ownership keywords matched; treat as orchestration only if it cannot be assigned to a focused module.",
        }
    scored.sort(key=lambda item: (-item[0], item[1]["key"]))
    _, route, matches = scored[0]
    return {
        "status": "PASS",
        "schema_version": ARCHITECTURE_SCHEMA_VERSION,
        "recommended_module": route["key"],
        "recommended_path": route["path"],
        "confidence": "high" if len(matches) >= 2 else "medium",
        "matched_keywords": matches,
        "reason": f"Change belongs to {route['layer']} ownership.",
    }


def module_architecture_gate(summary: str, planned_paths: list[str]) -> dict[str, Any]:
    route = route_new_code(summary)
    recommended_path = route["recommended_path"].replace("\\", "/")
    normalized_paths = [path.replace("\\", "/") for path in planned_paths]
    converter_path = "scripts/hwpx/hwp_full_fidelity_converter.py"
    writes_converter = converter_path in normalized_paths
    recommended_route = next(item for item in MODULE_ROUTES if item["key"] == route["recommended_module"])
    accepted_paths = [recommended_path] + [path.replace("\\", "/") for path in recommended_route.get("accepted_paths", [])]
    writes_recommended = any(path in normalized_paths for path in accepted_paths)
    if recommended_route.get("forbid_in_converter") and writes_converter and not writes_recommended:
        status = "FAIL"
        reason = "Planned change writes converter for code owned by a focused module."
    elif route["status"] == "REVIEW":
        status = "REVIEW"
        reason = route["reason"]
    elif writes_recommended:
        status = "PASS"
        reason = "Planned path matches the routed module."
    else:
        status = "WARN"
        reason = "Recommended module is not in planned paths; review before writing code."
    return {
        "status": status,
        "schema_version": ARCHITECTURE_SCHEMA_VERSION,
        "route": route,
        "planned_paths": normalized_paths,
        "reason": reason,
    }
