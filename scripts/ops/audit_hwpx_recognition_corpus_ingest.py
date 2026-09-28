"""HWPX-RECOGNITION-CORPUS-INGEST-AUDIT-01

inventory.json + 실제 HWPX 파싱 → corpus.sqlite3 ingest:
  1. hwpx_documents (inventory baseline)
  2. document_classifications (filename_pattern_v1)
  3. label_occurrences (라벨 후보 corpus)
  4. label_promotion_candidates (PENDING — production dict 미매칭 고빈도 라벨)

원본 sha256/mtime 무변경 / writer 미호출 / output HWPX 미생성 /
secret 출력 없음 / production module DB import 없음.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.recognition_corpus import corpus_schema as cs   # noqa: E402

INVENTORY_PATH = PROJECT_ROOT / "reports/collected_hwpx_inventory_audit/inventory.json"
DB_PATH = PROJECT_ROOT / "data/recognition_corpus/corpus.sqlite3"
OUTPUT_DIR = PROJECT_ROOT / "reports/hwpx_recognition_corpus_ingest_audit"

CLASSIFIER_VERSION = "filename_pattern_v1"
INGEST_AUDIT_LABEL = "v1_ingest"

# 최소 occurrence/document_count로 promotion candidate 후보 채택
PROMOTION_MIN_OCCURRENCE = 5
PROMOTION_MIN_DOCUMENTS = 3


def _classify_doc_type_by_filename(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/")
    if rel.startswith("tests/fixtures/hwpx/gantt/"):
        return "empty_template"
    if rel.startswith("tests/fixtures/hwpx/corpus/"):
        return "fillable_form"
    name = rel.rsplit("/", 1)[-1]
    if "[별지" in name or "별지_제" in name or "별지 제" in name:
        return "fillable_form"
    if "[별표" in name or "별표_" in name or "별표 " in name:
        return "reference_table"
    return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _production_label_dictionary() -> dict:
    """현재 production fill_review_contract의 _LABEL_TO_SEMANTIC을 읽어 비교 기준으로 사용.

    DB 모듈은 production을 import해도 단방향(읽기만)이므로 isolation gate 위반 아님.
    (production module이 corpus DB를 import하는 것만 금지)
    """
    from scripts.hwpx.fill_review.fill_review_contract import _LABEL_TO_SEMANTIC
    return dict(_LABEL_TO_SEMANTIC)


def _extract_label_candidates(parser_result):
    """파일별 (cellId, label_text, normalized_label, neighbor empty, table_id, row, col).

    조건: 셀 텍스트 ≤ 25자, 우측 셀(같은 row, col+1)이 빈 셀.
    """
    out: list[dict] = []
    for t in parser_result.tables:
        cmap = {(c.row, c.col): c for c in t.cells}
        for c in t.cells:
            text = (c.normalizedText or "").strip()
            if not text or len(text) > 25:
                continue
            v = cmap.get((c.row, c.col + 1))
            if v is None:
                continue
            right_empty = (v.normalizedText or "").strip() == ""
            if not right_empty:
                continue
            from scripts.hwpx.fill_review.fill_review_contract import (
                _normalize_label,
            )
            norm = _normalize_label(text)
            if not norm:
                continue
            out.append({
                "label_text": text,
                "normalized_label": norm,
                "table_id": t.tableId,
                "row_index": c.row,
                "cell_index": c.col,
                "cell_key": c.cellId,
                "right_neighbor_empty": 1,
                "neighbor_text": "",
            })
    return out


def _ingest_one(conn: sqlite3.Connection, item: dict, parser_engine,
                  now_iso: str) -> dict:
    """단일 파일을 DB에 ingest. return summary dict."""
    rel = item["sourcePath"]
    path = PROJECT_ROOT / rel
    res = {"sourcePath": rel, "document_id": item["sha256"],
            "ingest_status": "OK", "label_occurrence_count": 0,
            "documentType": "unknown",
            "sha256Before": item["sha256"], "sha256After": "",
            "mtimeBefore": item["mtime"], "mtimeAfter": -1,
            "errors": []}

    # source mutation check (재해시)
    try:
        sha_after = _file_sha256(path)
        mt_after = path.stat().st_mtime
    except Exception as exc:  # noqa: BLE001 -- 이 단계만 기록 후 계속
        res["ingest_status"] = "FAIL_SOURCE_READ"
        res["errors"].append(str(exc))
        return res
    res["sha256After"] = sha_after
    res["mtimeAfter"] = mt_after
    if sha_after != item["sha256"] or mt_after != item["mtime"]:
        res["ingest_status"] = "FAIL_UNSAFE_MUTATION"
        res["errors"].append("sha256/mtime mismatch with inventory baseline")
        return res

    # 1) hwpx_documents UPSERT
    conn.execute(
        "INSERT OR REPLACE INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime, "
        " detected_type, inventory_status, sha256, first_seen_at, "
        " last_audited_at, notes) "
        "VALUES (?, ?, ?, ?, ?, 'hwpx', 'FOUND', ?, ?, ?, ?)",
        (item["sha256"], rel, item["sourceKind"], item["fileSize"],
          item["mtime"], item["sha256"], now_iso, now_iso, ""),
    )

    # 2) parse
    try:
        r = parser_engine.parse_hwpx_v2(path)
    except Exception as exc:  # noqa: BLE001 -- 이 단계만 기록 후 계속
        res["ingest_status"] = "FAIL_PARSE"
        res["errors"].append(str(exc)[:200])
        return res

    # 3) filename classifier
    doc_type = _classify_doc_type_by_filename(rel)
    res["documentType"] = doc_type
    conn.execute(
        "INSERT OR REPLACE INTO document_classifications "
        "(document_id, classifier_version, document_type, confidence, "
        " evidence_json, classified_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (item["sha256"], CLASSIFIER_VERSION, doc_type,
          0.7 if doc_type != "unknown" else 0.3,
          json.dumps({"basis": "filename_pattern"}),
          now_iso),
    )

    # 4) label occurrences (기존 label_occurrences는 ingest 단위로 추가; 동일 doc_id
    #    재진입 시 DELETE 후 재삽입 — idempotent)
    conn.execute(
        "DELETE FROM label_occurrences WHERE document_id=?",
        (item["sha256"],),
    )
    cands = _extract_label_candidates(r)
    if cands:
        conn.executemany(
            "INSERT INTO label_occurrences "
            "(document_id, table_id, cell_key, label_text, normalized_label, "
            " neighbor_text, right_neighbor_empty, row_index, cell_index, "
            " audited_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(item["sha256"], c["table_id"], c["cell_key"], c["label_text"],
                c["normalized_label"], c["neighbor_text"],
                c["right_neighbor_empty"], c["row_index"], c["cell_index"],
                now_iso) for c in cands],
        )
        res["label_occurrence_count"] = len(cands)

    return res


def _rebuild_promotion_candidates(conn: sqlite3.Connection,
                                       production_dict: dict,
                                       now_iso: str) -> int:
    """production 사전에 없는 고빈도 라벨을 PENDING promotion candidate로 등록.

    proposed_semantic은 UNKNOWN으로 둔다 (사람 검수 필요 — Gate 3 잠금).
    """
    # 기존 PENDING은 모두 비우고 재계산 (idempotent)
    conn.execute("DELETE FROM label_promotion_candidates WHERE status='PENDING'")
    rows = conn.execute(
        "SELECT normalized_label, COUNT(*) AS occ, "
        "       COUNT(DISTINCT document_id) AS docs "
        "  FROM label_occurrences "
        " GROUP BY normalized_label "
        "HAVING occ >= ? AND docs >= ? "
        " ORDER BY occ DESC",
        (PROMOTION_MIN_OCCURRENCE, PROMOTION_MIN_DOCUMENTS),
    ).fetchall()
    inserted = 0
    for label, occ, docs in rows:
        if label in production_dict:
            continue
        # evidence_score: 발생빈도/문서수 정규화 (0~1)
        # 임시 점수: log-scale (단순)
        import math
        score = min(1.0, math.log10(occ + 1) / 4.0
                    + math.log10(docs + 1) / 4.0)
        score = round(score, 4)
        conn.execute(
            "INSERT INTO label_promotion_candidates "
            "(normalized_label, proposed_semantic, occurrence_count, "
            " document_count, evidence_score, status, conflict_count, "
            " evidence_json) "
            "VALUES (?, ?, ?, ?, ?, 'PENDING', 0, ?)",
            (label, "UNKNOWN", occ, docs, score,
              json.dumps({"basis": "frequency"})),
        )
        inserted += 1
    return inserted


def run_ingest(limit: int | None = None) -> dict:
    """전체 inventory를 corpus DB로 ingest. limit 지정 시 첫 N개."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not INVENTORY_PATH.exists():
        return {"overallVerdict": "FAIL_INVENTORY_MISSING",
                  "detail": str(INVENTORY_PATH)}

    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    items = inv["items"]
    # parseCandidate=True + unique sha256
    seen: set[str] = set()
    targets: list[dict] = []
    for it in items:
        if not it.get("parseCandidate"):
            continue
        sha = it.get("sha256", "")
        if not sha or sha in seen:
            continue
        seen.add(sha)
        targets.append(it)
    if limit is not None and limit > 0:
        targets = targets[:limit]

    print(f"[ingest] target unique parseable: {len(targets)}", flush=True)

    # parser_engine 1회 import
    from scripts.hwpx.parser import parser_engine
    production_dict = _production_label_dictionary()

    conn = cs.open_corpus_db(DB_PATH)
    try:
        now_iso = _now_iso()
        started = time.time()
        ingested: list[dict] = []
        failed: list[dict] = []
        mutation_violations: list[dict] = []
        batch_count = 0
        for i, item in enumerate(targets, 1):
            try:
                res = _ingest_one(conn, item, parser_engine, now_iso)
            except Exception as exc:  # noqa: BLE001 -- 이 단계만 기록 후 계속
                res = {"sourcePath": item["sourcePath"],
                         "document_id": item["sha256"],
                         "ingest_status": "FAIL_INGEST",
                         "errors": [str(exc)[:200]],
                         "label_occurrence_count": 0,
                         "documentType": "unknown",
                         "sha256Before": item["sha256"],
                         "sha256After": item["sha256"],
                         "mtimeBefore": item["mtime"],
                         "mtimeAfter": item["mtime"]}
            if res["ingest_status"] == "OK":
                ingested.append(res)
            elif res["ingest_status"] == "FAIL_UNSAFE_MUTATION":
                mutation_violations.append(res)
                failed.append(res)
            else:
                failed.append(res)
            batch_count += 1
            if batch_count >= 100:
                conn.commit()
                batch_count = 0
            if i % 500 == 0:
                print(f"  ... {i}/{len(targets)} "
                       f"({time.time()-started:.0f}s)", flush=True)
        conn.commit()
        elapsed_ingest = time.time() - started

        # promotion candidate 재구성
        promo_count = _rebuild_promotion_candidates(conn, production_dict, now_iso)
        conn.commit()

        # 통계
        doctype_counts: dict[str, int] = {}
        for r in ingested:
            doctype_counts[r["documentType"]] = \
                doctype_counts.get(r["documentType"], 0) + 1
        label_total = conn.execute(
            "SELECT COUNT(*) FROM label_occurrences"
        ).fetchone()[0]
        unique_norm = conn.execute(
            "SELECT COUNT(DISTINCT normalized_label) FROM label_occurrences"
        ).fetchone()[0]
        top_labels = conn.execute(
            "SELECT normalized_label, occurrence_count, document_count "
            "  FROM labels_by_frequency LIMIT 50"
        ).fetchall()

        summary = {
            "targetCount": len(targets),
            "ingestedCount": len(ingested),
            "failedCount": len(failed),
            "unsafeMutationCount": len(mutation_violations),
            "elapsedSeconds": round(elapsed_ingest, 1),
            "labelOccurrenceTotal": label_total,
            "uniqueNormalizedLabelCount": unique_norm,
            "promotionCandidatePending": promo_count,
            "documentTypeBreakdown": doctype_counts,
            "topLabels": [{"label": r[0], "occurrence": r[1],
                              "documents": r[2]} for r in top_labels],
            "overallVerdict": ("FAIL_UNSAFE_MUTATION"
                                  if mutation_violations
                                  else ("WARN_PARTIAL_INGEST"
                                          if failed
                                          else "PASS_CORPUS_INGEST")),
            "auditedAt": now_iso,
        }

        (OUTPUT_DIR / "ingest_audit.json").write_text(
            json.dumps({"summary": summary,
                          "ingested": ingested[:200],   # 샘플만 저장
                          "failed": failed[:200],
                          "mutationViolations": mutation_violations},
                         ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        md = [
            "# HWPX-RECOGNITION-CORPUS-INGEST-AUDIT-01",
            "",
            "## Summary",
            f"- targets: {summary['targetCount']}",
            f"- ingested: {summary['ingestedCount']}",
            f"- failed: {summary['failedCount']}",
            f"- unsafeMutation: {summary['unsafeMutationCount']}",
            f"- elapsed: {summary['elapsedSeconds']}s",
            f"- label occurrences total: {summary['labelOccurrenceTotal']}",
            f"- unique normalized labels: "
            f"{summary['uniqueNormalizedLabelCount']}",
            f"- promotion candidates (PENDING): "
            f"{summary['promotionCandidatePending']}",
            f"- overallVerdict: **{summary['overallVerdict']}**",
            "",
            "## Document type breakdown (filename_pattern_v1)",
            "",
            "| docType | count |",
            "|---|---|",
        ]
        for dt, n in sorted(doctype_counts.items(), key=lambda x: -x[1]):
            md.append(f"| {dt} | {n} |")
        md.append("")
        md.append("## Top 50 labels by frequency")
        md.append("")
        md.append("| # | normalized_label | occurrence | documents |")
        md.append("|---|---|---|---|")
        for i, t in enumerate(summary["topLabels"], 1):
            md.append(f"| {i} | {t['label']} | {t['occurrence']} "
                         f"| {t['documents']} |")
        (OUTPUT_DIR / "ingest_audit.md").write_text(
            "\n".join(md), encoding="utf-8",
        )

        return summary
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    print("[HWPX-RECOGNITION-CORPUS-INGEST-AUDIT-01]")
    s = run_ingest(limit=args.limit)
    print(json.dumps(s, ensure_ascii=False, indent=2))
    if s.get("overallVerdict", "").startswith("FAIL"):
        sys.exit(1)
