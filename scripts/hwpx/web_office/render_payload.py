"""Browser Render Payload v1 — read-only.

DocumentModel → 브라우저가 직접 받아 렌더할 수 있는 JSON 형태.
editable=False 고정. 셀 navigation id는 생성하지만 편집 동작은 비활성.
"""
from __future__ import annotations
from typing import Any

from . import SCHEMA_VERSION, ENGINE_VERSION
from .document_model import WebOfficeDocumentModel


PAYLOAD_VERSION = "render-payload-1.0"


def build_render_payload(
    doc: WebOfficeDocumentModel,
    *,
    char_pr_defs: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """RO-VIEW용 render payload 생성. edit/save 관련 필드는 포함하지 않는다.

    WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01:
    char_pr_defs 가 주어지면 payload.styles.charPrDefs 로 additive 노출
    (read-only). header.xml 의 charPr 정의 속성 (fontName/fontSizePt/
    textColor/bold/italic/underline 등) 을 브라우저 toolbar preview 에서
    참조하기 위함. 기본 None → 기존 schema 와 동일.
    """
    def paragraph_payload(p) -> dict[str, Any]:
        return {
            "paragraphId": p.paragraphId,
            "text": p.text,
            "parPrIDRef": p.parPrIDRef,
            "runs": [{"runId": r.runId, "text": r.text,
                       "charPrIDRef": r.charPrIDRef} for r in p.runs],
            "containerScope": p.containerScope,
            "editable": False,
        }

    cells_by_table: dict[str, list[dict[str, Any]]] = {}
    for c in doc.cells:
        cells_by_table.setdefault(c.tableId, []).append({
            "cellId": c.cellId,
            "navigationId": c.cellId,        # navigation 용 식별자만
            "row": c.row, "col": c.col,
            "rowSpan": c.rowSpan, "colSpan": c.colSpan,
            "isCoveredByMerge": c.isCoveredByMerge,
            "isMergedOrigin": c.isMergedOrigin,
            "text": c.text,
            "cellMargin": c.cellMargin,
            "paragraphs": [paragraph_payload(p) for p in c.paragraphs],
            "editable": False,
        })

    paragraph_index = {p.paragraphId: paragraph_payload(p)
                       for p in doc.paragraphs}

    tables = []
    for t in doc.tables:
        tables.append({
            "tableId": t.tableId,
            "blockId": t.blockId,
            "sectionIndex": t.sectionIndex,
            "rowCount": t.rowCount,
            "colCount": t.colCount,
            "visualColCount": t.visualColCount,
            "hasMergedCells": t.hasMergedCells,
            "inMargin": t.inMargin,
            "outMargin": t.outMargin,
            "cells": cells_by_table.get(t.tableId, []),
            "editable": False,
        })

    blocks = []
    for b in doc.blocks:
        entry = {
            "blockId": b.blockId, "type": b.type,
            "sectionIndex": b.sectionIndex,
            "blockIndex": b.blockIndex,
            "ref": b.ref,
            "editable": False,
        }
        if b.type == "paragraph" and b.ref and b.ref in paragraph_index:
            entry["paragraph"] = paragraph_index[b.ref]
        blocks.append(entry)

    pages = [
        {"sectionIndex": s.sectionIndex,
            "sourceXmlPath": s.sourceXmlPath,
            "editable": False}
        for s in doc.sections
    ]

    payload: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "engineVersion": ENGINE_VERSION,
        "payloadVersion": PAYLOAD_VERSION,
        "documentId": doc.documentId,
        "sourceRef": {
            "sha256": doc.sourceDocumentHash,
            "path": doc.sourceDocumentPath,
        },
        "editable": False,
        "pages": pages,
        "blocks": blocks,
        "tables": tables,
        "objects": [
            {"objectId": o.objectId, "kind": o.kind,
                "sectionIndex": o.sectionIndex,
                "placeholder": o.placeholder,
                "editable": False}
            for o in doc.objects
        ],
        "warnings": doc.warnings,
    }
    styles_payload: dict[str, Any] = {}
    if doc.styles.paraPrDefs:
        styles_payload["paraPrDefs"] = doc.styles.paraPrDefs
    if doc.styles.fontFaceDefs:
        styles_payload["fontFaceDefs"] = doc.styles.fontFaceDefs
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01:
    # styles.charPrDefs 를 read-only additive 로 노출 (toolbar preview 용).
    if char_pr_defs is None and doc.styles.charPrDefs:
        char_pr_defs = doc.styles.charPrDefs
    if char_pr_defs is not None:
        styles_payload["charPrDefs"] = {
            str(cid): {
                "charPrId": str(cid),
                "fontName": d.get("fontName"),
                "fontFace": d.get("fontFace"),
                "fontRef": d.get("fontRef") or {},
                "fontSizePt": d.get("fontSizePt"),
                "height": d.get("height"),
                "textColor": d.get("textColor") or None,
                "ratio": d.get("ratio") or {},
                "spacing": d.get("spacing") or {},
                "relSz": d.get("relSz") or {},
                "offset": d.get("offset") or {},
                "bold": bool(d.get("bold")),
                "italic": bool(d.get("italic")),
                "underline": bool(d.get("underline")),
                "underlineDef": d.get("underlineDef") or {},
                "strikeout": bool(d.get("strikeout")),
                "strikeoutDef": d.get("strikeoutDef") or {},
                "shadow": d.get("shadow") or {},
            }
            for cid, d in char_pr_defs.items()
        }
    if styles_payload:
        payload["styles"] = styles_payload
    return payload
