"""Security policy and gate checks for full-fidelity conversion work."""

from __future__ import annotations

from typing import Any


SECURITY_SCHEMA_VERSION = 1

FORBIDDEN_CAPABILITIES = [
    {
        "key": "hancom_runtime",
        "keywords": ["hancom", "hwp.exe", "hwpctrl", "com automation", "gui automation", "official converter"],
        "reason": "The independent full-fidelity converter must not depend on Hancom runtime, COM, GUI automation, or official converter binaries.",
    },
    {
        "key": "network_dependency",
        "keywords": ["download", "http", "https", "network", "remote", "api upload", "cloud"],
        "reason": "Conversion must not require network access or upload source documents.",
    },
    {
        "key": "shell_execution",
        "keywords": ["subprocess", "shell", "powershell", "cmd.exe", "exec", "spawn process"],
        "reason": "Document conversion logic must not shell out unless a dedicated security-reviewed adapter owns it.",
    },
]

SENSITIVE_DOMAINS = [
    {
        "key": "archive_path_safety",
        "keywords": ["zip", "entry", "extract", "rewrite", "path traversal", "../", "absolute path"],
        "owner": "scripts/hwpx/hwp_full_fidelity_package.py",
    },
    {
        "key": "original_integrity",
        "keywords": ["original", "sha256", "hash", "integrity", "manifest", "byte exact"],
        "owner": "scripts/hwpx/hwp_full_fidelity_audit.py",
    },
    {
        "key": "untrusted_binary_parse",
        "keywords": ["payload", "binary", "ole", "stream", "record", "decompress"],
        "owner": "scripts/hwpx/hwp_full_fidelity_analyzer.py",
    },
    {
        "key": "secret_material",
        "keywords": ["token", "credential", "password", "secret", "api key"],
        "owner": "scripts/hwpx/hwp_full_fidelity_security.py",
    },
]


def security_catalog() -> dict[str, Any]:
    return {
        "schema_version": SECURITY_SCHEMA_VERSION,
        "forbidden_capabilities": FORBIDDEN_CAPABILITIES,
        "sensitive_domains": SENSITIVE_DOMAINS,
        "rules": [
            "Independent full-fidelity conversion must not require Hancom runtime, COM, GUI automation, official converter binaries, or network upload.",
            "Archive writes must normalize ZIP entry names and must not extract entries to arbitrary filesystem paths.",
            "The original HWP must remain byte-exact when embedded and must be verified by size and SHA-256.",
            "Security-sensitive changes must be reviewed through this gate before implementation.",
        ],
    }


def security_gate(summary: str, planned_paths: list[str] | None = None) -> dict[str, Any]:
    text = summary.lower()
    normalized_paths = [path.replace("\\", "/") for path in planned_paths or []]
    forbidden_hits = []
    for capability in FORBIDDEN_CAPABILITIES:
        matches = [keyword for keyword in capability["keywords"] if keyword.lower() in text]
        if matches:
            forbidden_hits.append(
                {
                    "key": capability["key"],
                    "matched_keywords": matches,
                    "reason": capability["reason"],
                }
            )

    sensitive_hits = []
    for domain in SENSITIVE_DOMAINS:
        matches = [keyword for keyword in domain["keywords"] if keyword.lower() in text]
        if matches:
            owner = domain["owner"].replace("\\", "/")
            sensitive_hits.append(
                {
                    "key": domain["key"],
                    "matched_keywords": matches,
                    "owner": owner,
                    "owner_in_planned_paths": owner in normalized_paths,
                }
            )

    if forbidden_hits:
        status = "FAIL"
        reason = "Forbidden security capability requested."
    elif any(not hit["owner_in_planned_paths"] for hit in sensitive_hits):
        status = "WARN"
        reason = "Security-sensitive change should include the owning module path."
    else:
        status = "PASS"
        reason = "No forbidden capability detected."

    return {
        "status": status,
        "schema_version": SECURITY_SCHEMA_VERSION,
        "forbidden_hits": forbidden_hits,
        "sensitive_hits": sensitive_hits,
        "planned_paths": normalized_paths,
        "reason": reason,
    }
