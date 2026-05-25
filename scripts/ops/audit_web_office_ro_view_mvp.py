"""WEB-OFFICE-RO-VIEW-MVP-01 감사 스크립트.

샘플 HWPX 최소 3건을 RO-VIEW 로 변환하고 다음을 검증한다:
- schemaVersion / engineVersion 고정값 일치
- stable id (cellId/paragraphId/blockId/objectId) 중복 없음
- 표가 있는 문서는 table/cell payload 생성
- 원본 sha256 변경 없음
- editable=False 고정
- writer/output/edit-command 미발생 (정적 — 본 스크립트는 writer 미호출)
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office import SCHEMA_VERSION, ENGINE_VERSION
from scripts.hwpx.web_office.ro_view_importer import (
    import_hwpx_as_ro_view,
)
from scripts.hwpx.web_office.render_payload import build_render_payload


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _resolve_fixtures(limit: int = 3) -> list[Path]:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return _resolve_checked_in_fixtures(limit)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute("""
            SELECT d.source_path FROM hwpx_documents d
            JOIN document_classifications c ON c.document_id=d.document_id
            WHERE d.inventory_status='FOUND'
              AND c.document_type='fillable_form'
              AND d.file_size BETWEEN 30000 AND 120000
            ORDER BY d.first_seen_at LIMIT ?
        """, (limit,)).fetchall()
    finally:
        conn.close()
    fixtures = [PR / r[0] for r in rows if (PR / r[0]).is_file()]
    if len(fixtures) >= limit:
        return fixtures[:limit]
    fallback = _resolve_checked_in_fixtures(limit)
    merged = list(dict.fromkeys(fixtures + fallback))
    return merged[:limit]


def _resolve_checked_in_fixtures(limit: int) -> list[Path]:
    fixture_dir = PR / "tests/fixtures/hwpx/corpus"
    if not fixture_dir.is_dir():
        return []
    fixtures = sorted(
        p for p in fixture_dir.glob("*.hwpx")
        if 30000 <= p.stat().st_size <= 120000
    )
    return fixtures[:limit]


def audit_one(path: Path) -> dict:
    sha_before = _sha(path)
    mtime_before = path.stat().st_mtime_ns

    doc = import_hwpx_as_ro_view(path)
    payload = build_render_payload(doc)

    # stable id 중복 검증
    cell_ids = [c.cellId for c in doc.cells]
    par_ids = [p.paragraphId for p in doc.paragraphs]
    block_ids = [b.blockId for b in doc.blocks]
    obj_ids = [o.objectId for o in doc.objects]

    findings: list[dict] = []
    for label, ids in [("cellId", cell_ids), ("paragraphId", par_ids),
                                   ("blockId", block_ids), ("objectId", obj_ids)]:
        if len(ids) != len(set(ids)):
            dup = [x for x in set(ids) if ids.count(x) > 1][:3]
            findings.append({"code": f"{label}_DUPLICATE",
                                      "level": "FAIL", "detail": dup})

    if doc.schemaVersion != SCHEMA_VERSION:
        findings.append({"code": "SCHEMA_VERSION_MISMATCH",
                                  "level": "FAIL",
                                  "detail": doc.schemaVersion})
    if doc.engineVersion != ENGINE_VERSION:
        findings.append({"code": "ENGINE_VERSION_MISMATCH",
                                  "level": "FAIL",
                                  "detail": doc.engineVersion})

    # editable=False 고정 확인
    if payload.get("editable") is not False:
        findings.append({"code": "PAYLOAD_EDITABLE_NOT_FALSE",
                                  "level": "FAIL", "detail": "root"})
    for tbl in payload.get("tables", []):
        if tbl.get("editable") is not False:
            findings.append({"code": "TABLE_EDITABLE_NOT_FALSE",
                                      "level": "FAIL",
                                      "detail": tbl.get("tableId")})

    # 표 있는 문서면 cell payload 비어있지 않아야 함
    if doc.tables and not doc.cells:
        findings.append({"code": "CELLS_EMPTY_WITH_TABLES",
                                  "level": "FAIL", "detail": None})

    sha_after = _sha(path)
    mtime_after = path.stat().st_mtime_ns
    if sha_after != sha_before:
        findings.append({"code": "SOURCE_SHA_CHANGED", "level": "FAIL",
                                  "detail": path.name})
    if mtime_after != mtime_before:
        findings.append({"code": "SOURCE_MTIME_CHANGED",
                                  "level": "FAIL", "detail": path.name})

    return {
        "path": str(path.relative_to(PR)),
        "schemaVersion": doc.schemaVersion,
        "engineVersion": doc.engineVersion,
        "documentId": doc.documentId,
        "counts": {
            "sections": len(doc.sections),
            "blocks": len(doc.blocks),
            "paragraphs": len(doc.paragraphs),
            "tables": len(doc.tables),
            "cells": len(doc.cells),
            "objects": len(doc.objects),
            "warnings": len(doc.warnings),
        },
        "stableIdUnique": {
            "cellId": len(cell_ids) == len(set(cell_ids)),
            "paragraphId": len(par_ids) == len(set(par_ids)),
            "blockId": len(block_ids) == len(set(block_ids)),
            "objectId": len(obj_ids) == len(set(obj_ids)),
        },
        "srcUnchanged": sha_after == sha_before
                                and mtime_after == mtime_before,
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def audit() -> dict:
    fixtures = _resolve_fixtures(3)
    if len(fixtures) < 3:
        return {"task": "WEB-OFFICE-RO-VIEW-MVP-01",
                    "verdict": "FAIL",
                    "reason": f"need ≥3 fixtures, got {len(fixtures)}"}

    per_file = [audit_one(p) for p in fixtures]
    fails = sum(1 for r in per_file if r["verdict"] != "PASS")
    return {
        "task": "WEB-OFFICE-RO-VIEW-MVP-01",
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "sampleCount": len(per_file),
        "results": per_file,
        "verdict": "PASS" if fails == 0 else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
