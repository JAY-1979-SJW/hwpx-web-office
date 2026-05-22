"""End-to-End batch — 인지 → AI 판단 → 정확 입력 → 검증.

대표님 정책:
- 인지: parser_engine (기존)
- AI 판단: tests/fixtures (Claude-as-LLM)
- 입력: hwpx_edit_tool.apply_edit_plan (기존 자재)
- 신규 도구 작성 금지 (CLAUDE.md §10)

각 문서별 결과 개별 보고 (jsonl).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts/hwpx"))


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_set_cells_plan(parser_result, ai_proposal_callable) -> dict:
    """parser 결과를 AI 판단을 거쳐 set_cells plan으로 변환."""
    from scripts.hwpx.ai_proposal import target_resolver as tr

    # M4: parser tableId → enum 정수 index 매핑.
    # apply_edit_plan은 enum idx를 받고, 끝 번호만 추출하면 다른 section의
    # 같은 끝 번호 table과 충돌(예: t_s0_000 == t_s1_000).
    tid_to_idx = {tbl.tableId: i for i, tbl in enumerate(parser_result.tables)}

    # parser → recognitionResult
    label_occs = []
    slot_by_key: dict[str, dict] = {}
    for slot in parser_result.inputSlotCandidates:
        label = (getattr(slot, "labelText", None)
                      or getattr(slot, "anchorText", None) or "")
        norm = tr.normalize_label(label)
        if not norm:
            continue
        tbl = getattr(slot, "tableId", "") or ""
        row = getattr(slot, "row", 0)
        col = getattr(slot, "col", 0)
        if not tbl or tbl not in tid_to_idx:
            continue
        t_idx = tid_to_idx[tbl]
        cell_key = f"t{t_idx}:r{row}:c{col}"
        label_occs.append({
            "normalizedLabel": norm,
            "cellKey": cell_key,
            "neighborText": label,
        })
        slot_by_key[cell_key] = {
            "tableIdx": t_idx, "row": row, "col": col,
            "label": norm,
        }
    rec = {
        "documentId": "poc",
        "documentType": "fillable_form",
        "labelOccurrences": label_occs,
    }

    # AI 판단
    proposals = ai_proposal_callable(rec, [], [])

    # AI proposal → set_cells (target_resolver로 cellKey 결정)
    set_cells = []
    seen_keys: set[str] = set()
    duplicates_blocked = 0
    for p in proposals:
        resolution = tr.resolve_target(p, rec)
        if resolution["status"] != "RESOLVED":
            continue
        target = resolution["target"]
        cell_key = target.get("cellKey")
        if not cell_key or cell_key in seen_keys:
            duplicates_blocked += int(cell_key in seen_keys)
            continue
        seen_keys.add(cell_key)
        slot_info = slot_by_key.get(cell_key)
        if not slot_info:
            continue
        # M4: parser tableId enum idx를 그대로 set_cells.table로 사용.
        table_idx = slot_info["tableIdx"]
        set_cells.append({
            "table": table_idx, "row": slot_info["row"],
            "col": slot_info["col"], "value": p["value"],
            "_label": p["label"], "_semantic": p.get("semanticType"),
        })
    return {
        "set_cells": set_cells,
        "_meta": {
            "labelOccurrences": len(label_occs),
            "aiProposals": len(proposals),
            "setCellsBuilt": len(set_cells),
            "duplicatesBlocked": duplicates_blocked,
        },
    }


def _process_one(file_path: Path, sandbox_dir: Path,
                      ai_fn) -> dict:
    """1 문서 end-to-end. 결과 dict 반환."""
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    from scripts.hwpx import hwpx_edit_tool as edit_tool

    rec_start = time.time()
    parser_result = parse_hwpx_v2(file_path)
    rec_time = time.time() - rec_start

    plan = _build_set_cells_plan(parser_result, ai_fn)
    meta = plan.pop("_meta")

    if not plan["set_cells"]:
        return {
            "status": "SKIP_NO_FILLS",
            "recognitionMs": int(rec_time * 1000),
            **meta,
            "outputCreated": False,
            "originalUnmodified": True,
        }

    # writer 호출 (sandbox path)
    sandbox_path = sandbox_dir / f"{file_path.stem}__filled.hwpx"
    src_sha_before = _file_sha256(file_path)

    write_start = time.time()
    try:
        apply_result = edit_tool.apply_edit_plan(
            file_path, sandbox_path,
            {"set_cells": [{k: v for k, v in c.items()
                              if not k.startswith("_")}
                              for c in plan["set_cells"]]},
            dry_run=False,
        )
    except Exception as e:
        return {
            "status": "ERROR_WRITER",
            "error": str(e)[:200],
            "recognitionMs": int(rec_time * 1000),
            **meta,
            "outputCreated": False,
            "originalUnmodified": _file_sha256(file_path) == src_sha_before,
        }
    write_time = time.time() - write_start

    output_exists = sandbox_path.exists() and sandbox_path.stat().st_size > 0
    src_sha_after = _file_sha256(file_path)
    original_unmodified = (src_sha_after == src_sha_before)

    # 입력 정확도 검증: 결과 HWPX의 section XML에 우리 value가 byte-level로
    # 들어갔는지 확인 (가장 신뢰 가능한 방법).
    verification = {"verifiedCells": 0, "mismatchedCells": 0, "checkErrors": []}
    if output_exists:
        try:
            import zipfile
            xml_blobs: list[str] = []
            with zipfile.ZipFile(str(sandbox_path)) as z:
                for name in z.namelist():
                    if name.endswith(".xml"):
                        try:
                            xml_blobs.append(
                                z.read(name).decode("utf-8", "ignore"))
                        except Exception:
                            pass
            blob = "\n".join(xml_blobs)
            for sc in plan["set_cells"]:
                if sc["value"] in blob:
                    verification["verifiedCells"] += 1
                else:
                    verification["mismatchedCells"] += 1
        except Exception as e:
            verification["checkErrors"].append(str(e)[:120])

    # expected set_cells 적재 (사후 검증용)
    expected_set_cells = [{
        "table": c["table"], "row": c["row"], "col": c["col"],
        "value": c["value"],
        "label": c.get("_label"), "semantic": c.get("_semantic"),
    } for c in plan["set_cells"]]

    return {
        "status": (
            "OK" if (output_exists and original_unmodified
                        and verification["mismatchedCells"] == 0
                        and not verification["checkErrors"])
            else "WARN"
        ),
        "recognitionMs": int(rec_time * 1000),
        "writeMs": int(write_time * 1000),
        **meta,
        "outputCreated": output_exists,
        "originalUnmodified": original_unmodified,
        "outputBytes": sandbox_path.stat().st_size if output_exists else 0,
        "verification": verification,
        "applyResultStatus": apply_result.get("status"),
        "expectedSetCells": expected_set_cells,
        "sandboxPath": str(sandbox_path).replace("\\", "/"),
    }


def run_batch(limit: int, sandbox_dir: Path, report_jsonl: Path) -> dict:
    from tests.fixtures.ai_proposal_client_fixture import (
        make_ai_proposal_callable,
    )

    sandbox_dir.mkdir(parents=True, exist_ok=True)
    report_jsonl.parent.mkdir(parents=True, exist_ok=True)

    corpus_path = PROJECT_ROOT / "data/recognition_corpus/corpus.sqlite3"
    conn = sqlite3.connect(str(corpus_path))
    only_form = "--form" in sys.argv
    if only_form:
        rows = conn.execute(
            "SELECT d.document_id, d.source_path "
            "FROM hwpx_documents d "
            "JOIN document_classifications c "
            "  ON c.document_id = d.document_id "
            "WHERE d.inventory_status='FOUND' "
            "  AND c.document_type='fillable_form' "
            "ORDER BY d.first_seen_at LIMIT ?", (limit,)).fetchall()
    else:
        rows = conn.execute(
            "SELECT document_id, source_path FROM hwpx_documents "
            "WHERE inventory_status='FOUND' "
            "ORDER BY first_seen_at LIMIT ?", (limit,)).fetchall()
    conn.close()

    ai_fn = make_ai_proposal_callable()

    stats = {"total": len(rows), "OK": 0, "WARN": 0, "SKIP_NO_FILLS": 0,
              "ERROR_WRITER": 0, "verifiedCellsTotal": 0,
              "mismatchedCellsTotal": 0, "outputsCreated": 0,
              "elapsedSec": 0.0}

    start = time.time()
    with report_jsonl.open("w", encoding="utf-8") as f:
        for i, (doc_id, source_path) in enumerate(rows):
            file_path = PROJECT_ROOT / source_path
            if not file_path.is_file():
                rec = {"idx": i, "docId": doc_id, "status": "FILE_MISSING"}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                continue
            try:
                res = _process_one(file_path, sandbox_dir, ai_fn)
            except Exception as e:
                res = {"status": "ERROR_OUTER", "error": str(e)[:200]}
            rec = {"idx": i, "docId": doc_id, "src": source_path, **res}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()

            status = res.get("status", "ERROR")
            stats[status] = stats.get(status, 0) + 1
            v = res.get("verification") or {}
            stats["verifiedCellsTotal"] += v.get("verifiedCells", 0)
            stats["mismatchedCellsTotal"] += v.get("mismatchedCells", 0)
            if res.get("outputCreated"):
                stats["outputsCreated"] += 1
    stats["elapsedSec"] = round(time.time() - start, 2)
    return {
        "status": "PASS" if stats.get("ERROR_WRITER", 0) == 0 else "WARN",
        "summary": stats,
        "reportPath": str(report_jsonl),
        "sandboxDir": str(sandbox_dir),
    }


def main():
    limit = 1
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass
    suffix = "_form" if "--form" in sys.argv else ""
    sandbox = PROJECT_ROOT / f"data/drafts/hwpx_e2e_demo_sandbox{suffix}"
    report = PROJECT_ROOT / f"data/drafts/hwpx_e2e_demo_report{suffix}.jsonl"
    out = run_batch(limit, sandbox, report)
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
