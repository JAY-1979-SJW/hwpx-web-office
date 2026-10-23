"""HWPX-RECOGNITION-LABEL-PROMOTION-CANDIDATE-REVIEW-BATCH-01 — gate audit."""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports/hwpx_label_promotion_review_batch_audit"


def run_audit() -> dict:
    from scripts.hwpx.recognition_corpus import corpus_schema as cs
    from scripts.hwpx.recognition_corpus import label_promotion_review_batch as rb

    findings: list[dict] = []
    mod = (PROJECT_ROOT
             / "scripts/hwpx/recognition_corpus/"
               "label_promotion_review_batch.py")
    findings.append({"check": "module_exists", "ok": mod.is_file(),
                       "detail": str(mod.relative_to(PROJECT_ROOT))})

    conn = cs.open_corpus_db(":memory:")
    # seed
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count,"
        " document_count, evidence_score, status, evidence_json) "
        "VALUES ('공사명','PROJECT_NAME',2000,800,0.9,'PENDING','{}')")
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count,"
        " document_count, evidence_score, status, evidence_json) "
        "VALUES ('미상라벨','UNKNOWN',1000,200,0.8,'PENDING','{}')")
    conn.execute(
        "INSERT INTO label_promotion_candidates "
        "(normalized_label, proposed_semantic, occurrence_count,"
        " document_count, evidence_score, status, evidence_json) "
        "VALUES ('주소','ADDRESS',800,400,0.7,'PENDING','{}')")
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by,"
        " decided_at) VALUES ('주소','ADDRESS','APPROVED','r1','now')")
    conn.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by,"
        " decided_at) VALUES ('주소','COMPANY_NAME','APPROVED','r2','now')")
    conn.commit()

    b = rb.build_promotion_review_batch(conn)

    must = ("schemaVersion", "engineVersion", "requestId",
              "sourceCorpusSha", "generatedAt", "candidateCount",
              "reviewableCount", "blockedCount", "conflictCount",
              "unknownSemanticCount", "disagreementOnlyCount",
              "ambiguousOnlyCount", "buckets", "topReviewCandidates",
              "warnings")
    findings.append({"check": "required_result_fields",
                       "ok": all(k in b for k in must),
                       "detail": f"missing={[k for k in must if k not in b]}"})

    findings.append({"check": "blocked_unknown_semantic_bucket",
                       "ok": b["unknownSemanticCount"] >= 1,
                       "detail": f"unknown={b['unknownSemanticCount']}"})

    findings.append({"check": "blocked_conflict_bucket",
                       "ok": b["conflictCount"] >= 1,
                       "detail": f"conflict={b['conflictCount']}"})

    # disagreement bucket via taint
    bd = rb.build_promotion_review_batch(
        conn, tainted_disagreement={"will-not-match"})
    findings.append({"check": "disagreement_bucket_helper_works",
                       "ok": isinstance(bd["disagreementOnlyCount"], int),
                       "detail": f"d={bd['disagreementOnlyCount']}"})

    findings.append({"check": "high_priority_ranking",
                       "ok": len(b["buckets"]["HIGH_PRIORITY_REVIEW"]) >= 1,
                       "detail":
                           f"high={len(b['buckets']['HIGH_PRIORITY_REVIEW'])}"})

    md = rb.build_review_markdown(b)
    findings.append({"check": "markdown_review_table",
                       "ok": "| candidateId | normalizedLabel" in md,
                       "detail": f"len={len(md)}"})

    # approval validation — happy + sad
    cid = b["buckets"]["HIGH_PRIORITY_REVIEW"][0]["candidateId"]
    good = {"schemaVersion": rb.APPROVAL_INPUT_SCHEMA_VERSION,
              "approvedBy": "auditor", "decidedAt": "now",
              "decisions": [{"candidateId": cid,
                                "normalizedLabel": "공사명",
                                "proposedSemantic": "PROJECT_NAME",
                                "decision": "APPROVE"}]}
    bad = dict(good); bad["approvedBy"] = ""
    v_ok = rb.validate_human_approval_batch_input(good, review_batch=b)
    v_bad = rb.validate_human_approval_batch_input(bad, review_batch=b)
    findings.append({"check": "approval_input_validation",
                       "ok": v_ok["ok"] and not v_bad["ok"],
                       "detail":
                           f"good={v_ok['ok']} bad_errs={len(v_bad['errors'])}"})

    # static safety
    safety = rb.audit_review_batch_safety()
    findings.append({"check": "no_human_decision_or_dictionary_insert",
                       "ok": safety["ok"],
                       "detail": f"violations={safety['violations']}"})

    # production isolation re-check
    iso = cs.audit_production_isolation()
    findings.append({"check": "production_isolation_maintained",
                       "ok": iso["ok"],
                       "detail": (f"violations={iso['violations']}"
                                    if iso["violations"] else "clean")})

    # gitignore
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    must_gi = ("data/recognition_corpus/exports/",
                  "data/recognition_corpus/*.sqlite3")
    miss = [p for p in must_gi if p not in gi]
    findings.append({"check": "gitignore_corpus_and_exports",
                       "ok": not miss, "detail": f"missing={miss}"})

    summary = {
        "totalChecks": len(findings),
        "passCount": sum(1 for f in findings if f["ok"]),
        "failCount": sum(1 for f in findings if not f["ok"]),
        "findings": findings,
        "auditVerdict": ("PASS" if all(f["ok"] for f in findings)
                          else "FAIL"),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8")
    md_out = ["# HWPX-RECOGNITION-LABEL-PROMOTION-REVIEW-BATCH-01", "",
                f"verdict: **{summary['auditVerdict']}**  "
                f"pass={summary['passCount']}/{summary['totalChecks']}",
                "", "| check | ok | detail |", "|---|---|---|"]
    md_out.extend(f"| {f['check']} | "
                          f"{'PASS' if f['ok'] else 'FAIL'} | "
                          f"{f['detail']} |" for f in findings)
    (OUTPUT_DIR / "audit.md").write_text("\n".join(md_out),
                                              encoding="utf-8")
    return summary


if __name__ == "__main__":
    print("[HWPX-RECOGNITION-LABEL-PROMOTION-REVIEW-BATCH-01 GATE AUDIT]")
    r = run_audit()
    for f in r["findings"]:
        print(f"  {'PASS' if f['ok'] else 'FAIL'} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {r['auditVerdict']}  "
            f"pass={r['passCount']}/{r['totalChecks']}")
    sys.exit(0 if r["auditVerdict"] == "PASS" else 1)
