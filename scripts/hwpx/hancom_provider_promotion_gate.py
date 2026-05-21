"""Promotion evidence validation for HWP conversion providers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = [
    "provider",
    "input_path",
    "output_path",
    "one_file_success",
    "execution_approved",
    "verified_at",
    "output_validation",
]


def read_promotion_evidence(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    evidence_path = Path(path).expanduser().resolve()
    if not evidence_path.exists():
        return {
            "status": "FAIL",
            "path": str(evidence_path),
            "errors": ["PROMOTION_EVIDENCE_NOT_FOUND"],
            "warnings": [],
        }
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "FAIL",
            "path": str(evidence_path),
            "errors": [f"PROMOTION_EVIDENCE_INVALID_JSON:{type(exc).__name__}"],
            "warnings": [],
        }
    if not isinstance(data, dict):
        return {
            "status": "FAIL",
            "path": str(evidence_path),
            "errors": ["PROMOTION_EVIDENCE_NOT_OBJECT"],
            "warnings": [],
        }
    data["_path"] = str(evidence_path)
    return data


def validate_promotion_evidence(evidence: dict[str, Any] | None, provider_name: str | None = None) -> dict[str, Any]:
    if evidence is None:
        return {
            "status": "NOT_PROVIDED",
            "provider": provider_name,
            "promotable": False,
            "errors": [],
            "warnings": ["Promotion evidence JSON was not provided"],
        }
    if evidence.get("status") == "FAIL" and "errors" in evidence:
        return {
            "status": "FAIL",
            "provider": provider_name,
            "promotable": False,
            "errors": list(evidence.get("errors", [])),
            "warnings": list(evidence.get("warnings", [])),
            "path": evidence.get("path"),
        }

    errors: list[str] = []
    warnings: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in evidence:
            errors.append(f"MISSING_FIELD:{field}")

    evidence_provider = str(evidence.get("provider") or "")
    if provider_name and evidence_provider and evidence_provider != provider_name:
        errors.append(f"PROVIDER_MISMATCH:{evidence_provider}!={provider_name}")

    if evidence.get("one_file_success") is not True:
        errors.append("ONE_FILE_SUCCESS_NOT_TRUE")
    if evidence.get("execution_approved") is not True:
        errors.append("EXECUTION_APPROVED_NOT_TRUE")

    output_path = Path(str(evidence.get("output_path") or "")).expanduser()
    if not output_path.exists():
        errors.append("OUTPUT_PATH_NOT_FOUND")

    validation = evidence.get("output_validation")
    if not isinstance(validation, dict):
        errors.append("OUTPUT_VALIDATION_NOT_OBJECT")
    else:
        validation_status = validation.get("status")
        zip_ok = validation.get("zip_ok")
        xml_ok = validation.get("xml_ok")
        if validation_status not in {"PASS", "WARN"}:
            errors.append("OUTPUT_VALIDATION_STATUS_NOT_PASS_OR_WARN")
        if zip_ok is not True:
            errors.append("OUTPUT_VALIDATION_ZIP_NOT_TRUE")
        if xml_ok is not True:
            errors.append("OUTPUT_VALIDATION_XML_NOT_TRUE")
        if validation_status == "WARN":
            warnings.append("OUTPUT_VALIDATION_WARN")

    return {
        "status": "PASS" if not errors else "FAIL",
        "provider": evidence_provider or provider_name,
        "promotable": not errors,
        "errors": errors,
        "warnings": warnings,
        "path": evidence.get("_path"),
    }
