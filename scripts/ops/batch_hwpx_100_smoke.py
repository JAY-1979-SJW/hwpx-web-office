"""실 HWPX 100건 batch 시연.

corpus에서 100건 sampling → parser_engine으로 인식 → 마스터 회로 가동 →
배관으로 D동 적재 (in-memory). dry-run, env unset, R2 차단 게이트 적용.

원칙:
- read-only (원본 HWPX 수정 없음)
- writer 미호출
- output HWPX 미생성
- AI/OCR 미호출 (env unset → placeholder fallback)
- secret 미참조
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def parser_to_master_recognition(path: Path):
    """parser_engine 결과를 마스터 회로의 recognition_fn 시그니처에 맞춤."""
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2

    def _fn(source_ref: str) -> dict:
        result = parse_hwpx_v2(path)
        # parser_result → 운영동 recognitionResult 호환
        label_occs = []
        for slot in result.inputSlotCandidates:
            label = (getattr(slot, "labelText", None)
                          or getattr(slot, "anchorText", None)
                          or "")
            label_occs.append({
                "normalizedLabel": label.strip(),
                "cellKey": getattr(slot, "cellKey", None),
                "paragraphKey": getattr(slot, "paragraphKey", None),
                "neighborText": getattr(slot, "neighborText", None),
            })
        return {
            "documentId": source_ref,
            "documentType": getattr(result.document, "documentType", None)
                or "fillable_form",
            "subType": getattr(result.document, "subType", None),
            "sourceDocumentHash": result.inputFileName,
            "labelOccurrences": label_occs,
        }
    return _fn, None  # second is slot_detect (마스터가 slot은 별도 함수)


def parser_to_master_slot_detect(path: Path):
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2

    def _fn(rec: dict) -> list[dict]:
        result = parse_hwpx_v2(path)
        slots: list[dict] = []
        for s in result.inputSlotCandidates:
            slots.append({
                "label": getattr(s, "labelText", "") or "",
                "type": getattr(s, "slotType", "unknown"),
                "cellKey": getattr(s, "cellKey", None),
                "paragraphKey": getattr(s, "paragraphKey", None),
            })
        return slots
    return _fn


def run_batch(limit: int = 100) -> dict:
    from scripts.hwpx.master_orchestration import auto_fill_master as mo
    from scripts.hwpx.orchestration import fill_review_log_recorder as orc
    from scripts.hwpx.recognition_corpus import (
        corpus_schema as cs,
        audit_learning_log_contract as al,
    )

    # 1. corpus에서 100건 sampling
    corpus_path = PROJECT_ROOT / "data/recognition_corpus/corpus.sqlite3"
    if not corpus_path.is_file():
        return {"status": "FAIL", "reason": "corpus.sqlite3 not found"}
    conn_corpus = sqlite3.connect(str(corpus_path))
    rows = conn_corpus.execute(
        "SELECT document_id, source_path FROM hwpx_documents "
        "WHERE inventory_status='FOUND' "
        "ORDER BY first_seen_at LIMIT ?",
        (limit,)).fetchall()
    conn_corpus.close()

    # 2. D동 in-memory connection (R2 차단 유지)
    log_conn = orc.open_logging_connection(None)

    stats = {
        "total": len(rows),
        "parseSuccess": 0,
        "parseError": 0,
        "labelOccurrencesTotal": 0,
        "inputSlotsTotal": 0,
        "reviewItemsTotal": 0,
        "sessionsRecorded": 0,
        "sessionRecordError": 0,
        "elapsedSec": 0.0,
        "perFile": [],
    }
    errors: list[dict] = []

    start = time.time()
    for i, (doc_id, source_path) in enumerate(rows):
        file_path = PROJECT_ROOT / source_path
        if not file_path.is_file():
            stats["parseError"] += 1
            errors.append({"docId": doc_id, "stage": "file_missing",
                              "path": source_path})
            continue
        try:
            rec_fn, _ = parser_to_master_recognition(file_path)
            slot_fn = parser_to_master_slot_detect(file_path)
            master_res = mo.run_auto_fill_master(
                source_hwpx_ref=doc_id,
                recognition_fn=rec_fn,
                slot_detect_fn=slot_fn,
                request_id=f"batch-100-{i}",
            )
            stats["parseSuccess"] += 1
            stats["labelOccurrencesTotal"] += len(
                master_res["recognitionResult"]
                  .get("labelOccurrences") or [])
            stats["inputSlotsTotal"] += len(master_res.get("inputSlots") or [])
            stats["reviewItemsTotal"] += len(master_res.get("reviewItems") or [])

            try:
                rec_result = orc.record_pipeline_result(log_conn, master_res)
                stats["sessionsRecorded"] += 1
            except Exception as e:
                stats["sessionRecordError"] += 1
                errors.append({"docId": doc_id, "stage": "log_record",
                                  "error": str(e)[:200]})

            if i < 5 or i % 25 == 0:
                stats["perFile"].append({
                    "idx": i, "docId": doc_id[:40],
                    "labels": len(master_res["recognitionResult"]
                                       .get("labelOccurrences") or []),
                    "slots": len(master_res.get("inputSlots") or []),
                })
        except Exception as e:
            stats["parseError"] += 1
            errors.append({
                "docId": doc_id, "stage": "master_run",
                "error": str(e)[:200],
                "tb": traceback.format_exc()[-300:],
            })
    stats["elapsedSec"] = round(time.time() - start, 2)

    # 3. D동 view 통계
    view_stats = {}
    try:
        view_stats["totalSessions"] = log_conn.execute(
            "SELECT COUNT(*) FROM fill_review_sessions").fetchone()[0]
        view_stats["sessionsByStatus"] = dict(log_conn.execute(
            "SELECT session_status, COUNT(*) "
            "FROM fill_review_sessions GROUP BY session_status").fetchall())
        view_stats["totalDecisions"] = log_conn.execute(
            "SELECT COUNT(*) FROM fill_review_decision_logs").fetchone()[0]
    except Exception as e:
        view_stats["error"] = str(e)[:200]
    finally:
        log_conn.close()

    return {
        "status": "PASS" if stats["parseSuccess"] >= 1 else "FAIL",
        "limit": limit,
        "summary": stats,
        "dDongStats": view_stats,
        "errorCount": len(errors),
        "errorSamples": errors[:5],
    }


def main():
    limit = 100
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass
    report = run_batch(limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2,
                          default=str))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
