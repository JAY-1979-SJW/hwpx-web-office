"""실 HWPX 100건 batch — AI fixture inject (테스트 환경 시뮬레이션).

원칙 (CLAUDE.md §10 + 대표님 지시):
- AI는 판단 주체 (fixture가 그 역할)
- 신규 도구 작성 금지 — 기존 자재만 호출
- 입력 후 AI가 결과 자가 검증
- writer dry-run, 운영 corpus DB 미접근 (R2 차단 유지)
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def _parser_callables(file_path: Path):
    from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
    from scripts.hwpx.ai_proposal import target_resolver as tr

    def recognition_fn(source_ref: str) -> dict:
        result = parse_hwpx_v2(file_path)
        label_occs = []
        for slot in result.inputSlotCandidates:
            label = (getattr(slot, "labelText", None)
                          or getattr(slot, "anchorText", None) or "")
            # 기존 자재 호출 — target_resolver.normalize_label
            normalized = tr.normalize_label(label)
            if not normalized:
                continue
            table_id = getattr(slot, "tableId", "") or ""
            row = getattr(slot, "row", 0)
            col = getattr(slot, "col", 0)
            cell_key = f"{table_id}:r{row}:c{col}" if table_id else None
            label_occs.append({
                "normalizedLabel": normalized,
                "cellKey": cell_key,
                "paragraphKey": None,
                "neighborText": label,
            })
        return {
            "documentId": source_ref,
            "documentType": getattr(result.document,
                                          "documentType", None) or "fillable_form",
            "subType": getattr(result.document, "subType", None),
            "sourceDocumentHash": result.inputFileName,
            "labelOccurrences": label_occs,
        }

    def slot_detect_fn(rec: dict) -> list[dict]:
        result = parse_hwpx_v2(file_path)
        return [{
            "label": getattr(s, "labelText", "") or "",
            "type": getattr(s, "slotType", "unknown"),
            "cellKey": getattr(s, "cellKey", None),
            "paragraphKey": getattr(s, "paragraphKey", None),
        } for s in result.inputSlotCandidates]

    return recognition_fn, slot_detect_fn


def run_batch_with_ai(limit: int = 100) -> dict:
    from scripts.hwpx.master_orchestration import auto_fill_master as mo
    from scripts.hwpx.orchestration import fill_review_log_recorder as orc
    from tests.fixtures.ai_proposal_client_fixture import (
        make_ai_proposal_callable, self_verify_review_items,
    )

    # corpus에서 100건 sampling
    corpus_path = PROJECT_ROOT / "data/recognition_corpus/corpus.sqlite3"
    conn_corpus = sqlite3.connect(str(corpus_path))
    rows = conn_corpus.execute(
        "SELECT document_id, source_path FROM hwpx_documents "
        "WHERE inventory_status='FOUND' "
        "ORDER BY first_seen_at LIMIT ?", (limit,)).fetchall()
    conn_corpus.close()

    # 학습 로그 in-memory (R2 차단 유지)
    log_conn = orc.open_logging_connection(None)

    # AI fixture callable
    ai_fn = make_ai_proposal_callable()

    stats = {
        "total": len(rows),
        "parseSuccess": 0,
        "labelOccurrencesTotal": 0,
        "inputSlotsTotal": 0,
        "aiProposalsTotal": 0,
        "reviewItemsTotal": 0,
        "holdsTotal": 0,
        "rejectedTotal": 0,
        "sessionsRecorded": 0,
        "selfVerifyCounts": {},
        "selfVerifyIssues": 0,
        "warningsTotal": 0,
        "errorsTotal": 0,
        "elapsedSec": 0.0,
    }
    sample_results: list[dict] = []
    all_review_items: list[dict] = []

    start = time.time()
    for i, (doc_id, source_path) in enumerate(rows):
        file_path = PROJECT_ROOT / source_path
        if not file_path.is_file():
            stats["errorsTotal"] += 1
            continue
        try:
            rec_fn, slot_fn = _parser_callables(file_path)
            master_res = mo.run_auto_fill_master(
                source_hwpx_ref=doc_id,
                recognition_fn=rec_fn,
                slot_detect_fn=slot_fn,
                ai_proposal_fn=ai_fn,                # AI fixture inject
                request_id=f"ai-batch-100-{i}",
            )
            stats["parseSuccess"] += 1
            stats["labelOccurrencesTotal"] += len(
                master_res["recognitionResult"].get("labelOccurrences") or [])
            stats["inputSlotsTotal"] += len(master_res.get("inputSlots") or [])
            stats["aiProposalsTotal"] += master_res.get(
                "aiProposalSummary", {}).get("totalSubmitted", 0)
            ri = master_res.get("reviewItems") or []
            stats["reviewItemsTotal"] += len(ri)
            stats["holdsTotal"] += len(master_res.get("holdProposals") or [])
            stats["rejectedTotal"] += len(
                master_res.get("rejectedProposals") or [])
            stats["warningsTotal"] += len(master_res.get("warnings") or [])
            stats["errorsTotal"] += len(master_res.get("errors") or [])
            all_review_items.extend(ri)

            orc.record_pipeline_result(log_conn, master_res)
            stats["sessionsRecorded"] += 1

            if i < 3 or i in (25, 50, 75):
                sample_results.append({
                    "idx": i,
                    "docId": doc_id[:32],
                    "labels": len(master_res["recognitionResult"]
                                       .get("labelOccurrences") or []),
                    "proposals": master_res.get("aiProposalSummary", {})
                                       .get("totalSubmitted", 0),
                    "reviewItems": len(ri),
                })
        except Exception as e:
            stats["errorsTotal"] += 1
            sample_results.append({
                "idx": i, "docId": doc_id[:32],
                "error": str(e)[:200],
            })
    stats["elapsedSec"] = round(time.time() - start, 2)

    # ── AI 자가 검증 ──────────────────────────────────────────────────
    self_verify = self_verify_review_items(all_review_items)
    stats["selfVerifyCounts"] = self_verify["counts"]
    stats["selfVerifyIssues"] = len(self_verify["issues"])

    # D동 통계
    d_dong = {}
    try:
        d_dong["totalSessions"] = log_conn.execute(
            "SELECT COUNT(*) FROM fill_review_sessions").fetchone()[0]
        d_dong["sessionsByStatus"] = dict(log_conn.execute(
            "SELECT session_status, COUNT(*) FROM fill_review_sessions "
            "GROUP BY session_status").fetchall())
    finally:
        log_conn.close()

    return {
        "status": "PASS" if stats["errorsTotal"] == 0 else "WARN",
        "limit": limit,
        "summary": stats,
        "dDongStats": d_dong,
        "selfVerifyIssuesSample": self_verify["issues"][:5],
        "sampleResults": sample_results,
    }


def main():
    limit = 100
    if len(sys.argv) > 1:
        try:
            limit = int(sys.argv[1])
        except ValueError:
            pass
    report = run_batch_with_ai(limit=limit)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
