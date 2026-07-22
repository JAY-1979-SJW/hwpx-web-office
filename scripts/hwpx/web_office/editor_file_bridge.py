"""Real HWPX load/save bridge for the browser editor.

The load side returns a render payload plus the editor document model needed by
cell_edit_state.mjs. The save side reuses save_apply_bridge.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .render_payload import build_render_payload
from .ro_view_importer import import_hwpx_as_ro_view
from .save_apply_bridge import apply_cell_save_request


_PR = Path(__file__).resolve().parents[3]


def _resolve_project_hwpx(project_root: Path, source_path: Any) -> tuple[Path, str]:
    if not isinstance(source_path, str) or not source_path:
        raise ValueError("sourcePath is required")
    requested = Path(source_path)
    if requested.is_absolute():
        raise ValueError("sourcePath must be project-relative")
    candidate = (project_root / requested).resolve()
    root = project_root.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("sourcePath escapes project root")
    if candidate.suffix.lower() != ".hwpx":
        raise ValueError("sourcePath must point to .hwpx")
    if not candidate.is_file():
        raise ValueError("sourcePath does not exist")
    rel = candidate.relative_to(root).as_posix()
    return candidate, rel


def _sanitize_document_model(doc_dict: dict[str, Any], source_rel: str) -> dict[str, Any]:
    clean = deepcopy(doc_dict)
    clean["sourceDocumentPath"] = source_rel
    return clean


def _sanitize_render_payload(payload: dict[str, Any], source_rel: str) -> dict[str, Any]:
    clean = deepcopy(payload)
    clean.setdefault("sourceRef", {})
    clean["sourceRef"]["path"] = source_rel
    return clean


def _recognize_input_fields(
    source_path: Path, document_model: dict[str, Any],
) -> list[dict[str, Any]] | None:
    """AI 필드 인식(hwpx_header_field_detector)을 로드에 연결.

    AI 창에 HWPX 를 주면 문서를 해부해 입력 지점을 찾듯, 로드 시 같은
    로직으로 라벨·빈칸 짝을 인식한다. 표 타깃은 cellAddr(절대좌표)를
    등장순 cellId 로 번역해 해당 셀을 입력칸으로 해제 + 라벨 부여.
    실패해도 로드는 계속(None 반환 — 뷰어는 파서 분류만 사용).
    """
    try:
        import re as _re
        import sys as _sys
        import zipfile
        import xml.etree.ElementTree as _ET
        _hx = str(Path(__file__).resolve().parents[1])   # scripts/hwpx
        if _hx not in _sys.path:
            _sys.path.insert(0, _hx)
        from hwpx_package import HwpxPackage
        from hwpx_header_field_detector import detect_input_fields

        pkg = (HwpxPackage.open(source_path)
               if hasattr(HwpxPackage, "open") else HwpxPackage(source_path))
        rep = detect_input_fields(pkg)
        fields = rep.get("fields") or []
        if not fields:
            return []

        # 표 전역 등장순 → tableId, 표별 cellAddr → 등장순 (r,c) 매핑
        def _ln(t):
            return t.rsplit("}", 1)[-1] if "}" in t else t
        z = zipfile.ZipFile(source_path)
        secs = sorted(
            [n for n in z.namelist()
             if _re.search(r"section\d+\.xml$", n.lower())],
            key=lambda n: int(_re.search(r"section(\d+)", n.lower()).group(1)))
        table_ids: list[str] = []
        addr_maps: list[dict[tuple[int, int], tuple[int, int]]] = []
        for sec in secs:
            si = int(_re.search(r"section(\d+)", sec.lower()).group(1))
            root = _ET.fromstring(z.read(sec))
            for ti, tbl in enumerate(
                    e for e in root.iter() if _ln(e.tag) == "tbl"):
                table_ids.append(f"t_s{si}_{ti:03d}")
                amap: dict[tuple[int, int], tuple[int, int]] = {}
                trs = [e for e in tbl if _ln(e.tag) == "tr"]
                for r, tr in enumerate(trs):
                    tcs = [e for e in tr if _ln(e.tag) == "tc"]
                    for c, tc in enumerate(tcs):
                        addr = next((x for x in tc.iter()
                                     if _ln(x.tag) == "cellAddr"), None)
                        if addr is not None:
                            amap[(int(addr.attrib.get("rowAddr", 0)),
                                  int(addr.attrib.get("colAddr", 0)))] = (r, c)
                addr_maps.append(amap)

        cells_by_id = {c.get("cellId"): c
                       for c in (document_model.get("cells") or [])}
        out: list[dict[str, Any]] = []
        for f in fields:
            entry: dict[str, Any] = {
                "label": f.get("label"), "key": f.get("key"),
                "fieldType": f.get("type"),
                "expectedFormat": f.get("expected_format"),
                "prompt": f.get("prompt"), "reason": f.get("reason"),
                "confidence": f.get("confidence"),
            }
            t = f.get("target") or {}
            ti = f.get("table")
            if ti is not None and 0 <= int(ti) < len(table_ids):
                occ = addr_maps[int(ti)].get(
                    (int(t.get("row", -1)), int(t.get("col", -1))))
                if occ is not None:
                    cid = f"cell_{table_ids[int(ti)]}_r{occ[0]}_c{occ[1]}"
                    entry["cellId"] = cid
                    cell = cells_by_id.get(cid)
                    # 인식 타깃 셀 잠금 해제 + 라벨 부여(기존 라벨 우선)
                    if cell is not None and not cell.get("isCoveredByMerge"):
                        cell["isInputCell"] = True
                        if not cell.get("inputLabel"):
                            cell["inputLabel"] = f.get("label")
            elif t.get("kind") == "paragraph":
                entry["paragraph"] = {
                    "section": t.get("section"),
                    "order": t.get("paragraph_order"),
                    "text": t.get("current_text"),
                }
            out.append(entry)
        return out
    except Exception:
        return None


def load_hwpx_for_editor(
    request: dict[str, Any],
    *,
    project_root: Path = _PR,
) -> dict[str, Any]:
    """Load a project-relative HWPX into browser editor contract payloads."""
    if not isinstance(request, dict):
        return {"verdict": "REJECTED", "reason": "REQUEST_NOT_OBJECT"}
    if request.get("operation") != "HWPX_EDITOR_LOAD":
        return {"verdict": "REJECTED", "reason": "UNSUPPORTED_OPERATION"}
    try:
        source_path, source_rel = _resolve_project_hwpx(
            project_root, request.get("sourcePath"))
    except ValueError as exc:
        return {"verdict": "REJECTED", "reason": "INVALID_REQUEST",
                "detail": str(exc)}

    doc = import_hwpx_as_ro_view(source_path)
    document_model = _sanitize_document_model(doc.to_dict(), source_rel)
    # AI 필드 인식 — 라벨·빈칸 짝을 해부해 입력 지점을 열고 라벨을 단다
    # (AI 자동입력의 대상 목록이기도 하다). 실패 시 None → 파서 분류만.
    recognized = _recognize_input_fields(source_path, document_model)
    if recognized is not None:
        document_model["recognizedFields"] = recognized
    render_payload = _sanitize_render_payload(build_render_payload(doc), source_rel)
    cells = document_model.get("cells") or []
    header_cells = [c for c in cells if c.get("headerCell") is True]
    return {
        "operation": "HWPX_EDITOR_LOAD",
        "verdict": "PASS",
        "sourcePath": source_rel,
        "documentId": document_model["documentId"],
        "sourceDocumentHash": document_model["sourceDocumentHash"],
        "documentModel": document_model,
        "renderPayload": render_payload,
        "summary": {
            "sections": len(document_model.get("sections") or []),
            "blocks": len(document_model.get("blocks") or []),
            "tables": len(document_model.get("tables") or []),
            "cells": len(cells),
            "headerCells": len(header_cells),
            "warnings": len(document_model.get("warnings") or []),
        },
    }


def load_and_apply_cell_save(
    load_request: dict[str, Any],
    save_request: dict[str, Any],
    *,
    project_root: Path = _PR,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Testable vertical slice: load a real file, then apply browser commands."""
    load_response = load_hwpx_for_editor(load_request, project_root=project_root)
    if load_response.get("verdict") != "PASS":
        return {"verdict": "REJECTED", "load": load_response, "save": None}
    save_response = apply_cell_save_request(
        save_request, project_root=project_root, output_dir=output_dir)
    return {
        "operation": "HWPX_EDITOR_LOAD_SAVE",
        "verdict": "PASS" if save_response.get("verdict") == "PASS" else "FAIL",
        "load": load_response,
        "save": save_response,
    }
