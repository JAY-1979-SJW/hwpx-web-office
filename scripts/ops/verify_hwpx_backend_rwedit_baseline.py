"""Integrated backend HWPX read/write/edit verification baseline runner."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))

from scripts.ops.verify_hwpx_backend_paragraph_edit import (  # noqa: E402
    verify as verify_paragraph,
)
from scripts.ops.verify_hwpx_backend_cell_edit import (  # noqa: E402
    verify as verify_cell,
)

TASK_NAME = "HWPX-BACKEND-RWEDIT-BASELINE-SCRIPT-41"


def verify() -> dict:
    paragraph = verify_paragraph()
    cell = verify_cell()

    findings: list[dict] = []
    if paragraph.get("verdict") != "PASS":
        findings.append({
            "code": "PARAGRAPH_BASELINE_NOT_PASS",
            "detail": paragraph,
        })
    if cell.get("verdict") != "PASS":
        findings.append({
            "code": "CELL_BASELINE_NOT_PASS",
            "detail": cell,
        })

    verdict = "PASS" if not findings else "FAIL"
    return {
        "task": TASK_NAME,
        "paragraph": {
            "verdict": paragraph.get("verdict"),
            "targetParagraph": paragraph.get("targetParagraph"),
            "fixture": paragraph.get("fixture"),
        },
        "cell": {
            "verdict": cell.get("verdict"),
            "targetCell": cell.get("targetCell"),
            "fixture": cell.get("fixture"),
        },
        "findings": findings,
        "verdict": verdict,
    }


def main() -> int:
    payload = verify()
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
