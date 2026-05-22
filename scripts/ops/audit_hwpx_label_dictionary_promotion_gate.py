"""HWPX-RECOGNITION-LABEL-DICTIONARY-PROMOTION-GATE-01 — gate audit."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports/hwpx_label_dictionary_promotion_gate_audit"


def run_audit() -> dict:
    from scripts.hwpx.recognition_corpus import corpus_schema as cs
    from scripts.hwpx.recognition_corpus import label_promotion_gate as pg

    findings: list[dict] = []
    mod = PROJECT_ROOT / "scripts/hwpx/recognition_corpus/label_promotion_gate.py"
    findings.append({"check": "module_exists", "ok": mod.is_file(),
                       "detail": str(mod.relative_to(PROJECT_ROOT))})

    conn = cs.open_corpus_db(":memory:")

    def cand(label="공사명", semantic="PROJECT_NAME",
               occ=10, docs=5, score=0.9):
        return {"normalized_label": label, "proposed_semantic": semantic,
                  "occurrence_count": occ, "document_count": docs,
                  "evidence_score": score}

    def add_human(label, semantic, status, by="reviewer1"):
        conn.execute(
            "INSERT INTO human_label_decisions "
            "(normalized_label, semantic_type, decision_status, decided_by,"
            " decided_at) VALUES (?,?,?,?,'now')",
            (label, semantic, status, by))
        conn.commit()

    # 1) no human approval blocks
    r = pg.evaluate_promotion_candidate(conn, cand("a1"))
    findings.append({"check": "no_human_approval_blocks",
                       "ok": r["status"] == "BLOCKED_NO_HUMAN_APPROVAL",
                       "detail": r["status"]})

    # 2) human approval allows
    add_human("공사명", "PROJECT_NAME", "APPROVED")
    r = pg.evaluate_promotion_candidate(conn, cand())
    findings.append({"check": "human_approval_allows",
                       "ok": r["allowed"] and r["status"] == "PROMOTION_ALLOWED",
                       "detail": r["status"]})

    # 3) UNKNOWN semantic blocked
    r = pg.evaluate_promotion_candidate(conn, cand("u1", "UNKNOWN"))
    findings.append({"check": "unknown_semantic_blocked",
                       "ok": r["status"] == "BLOCKED_UNKNOWN_SEMANTIC",
                       "detail": r["status"]})

    # 4) semantic conflict
    add_human("공사명", "COMPANY_NAME", "APPROVED", by="r2")
    r = pg.evaluate_promotion_candidate(conn, cand())
    findings.append({"check": "semantic_conflict_blocked",
                       "ok": r["status"] == "BLOCKED_CONFLICT",
                       "detail": r["status"]})

    # 5) disagreement-only blocks
    add_human("상호", "COMPANY_NAME", "APPROVED")
    conn.execute(
        "INSERT INTO hwpx_documents "
        "(document_id, source_path, source_kind, file_size, mtime,"
        " detected_type, inventory_status, sha256, first_seen_at) "
        "VALUES ('d1','/x','collected',1,1.0,'hwpx','FOUND',?,'now')",
        ("0" * 64,))
    conn.execute(
        "INSERT INTO label_occurrences "
        "(document_id, label_text, normalized_label, right_neighbor_empty,"
        " audited_at) VALUES ('d1','상호','상호',1,'now')")
    conn.commit()
    r = pg.evaluate_promotion_candidate(
        conn, cand(label="상호", semantic="COMPANY_NAME"),
        tainted_document_ids={"d1"})
    findings.append({"check": "disagreement_only_blocks",
                       "ok": r["status"] == "BLOCKED_DISAGREEMENT_ONLY",
                       "detail": r["status"]})

    # 6) dictionary version build
    fresh = cs.open_corpus_db(":memory:")
    fresh.execute(
        "INSERT INTO human_label_decisions "
        "(normalized_label, semantic_type, decision_status, decided_by,"
        " decided_at) VALUES ('공사명','PROJECT_NAME','APPROVED','r','now')")
    fresh.commit()
    rs = [pg.evaluate_promotion_candidate(fresh, cand())]
    info = pg.build_dictionary_version(
        fresh, "v_audit", rs, approved_by="auditor",
        source_corpus_sha="sha:audit")
    findings.append({"check": "dictionary_version_built",
                       "ok": info["entryCount"] == 1,
                       "detail": f"entries={info['entryCount']}"})

    # 7) snapshot export+validate (tmp)
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "snap.json"
        snap = pg.export_dictionary_snapshot(fresh, "v_audit", out,
                                                    results=rs)
        v = pg.validate_dictionary_snapshot(snap)
        findings.append({"check": "snapshot_export_and_validate",
                           "ok": v["ok"] and out.exists(),
                           "detail": f"validate={v['ok']}"})

    # 8) production isolation
    iso = pg.audit_production_snapshot_isolation()
    findings.append({"check": "production_db_import_isolation",
                       "ok": iso["ok"],
                       "detail": (f"violations={iso['violations']}"
                                    if iso["violations"] else "clean")})

    # 9) static guards
    src = mod.read_text(encoding="utf-8")
    bad = [n for n in ("execute_writer_call_plan_live_sandbox",
                            "import anthropic", "import openai",
                            "pytesseract", "ZipFile(")
              if n in src]
    findings.append({"check": "no_writer_no_output_no_ai_no_ocr",
                       "ok": not bad, "detail": f"bad={bad}"})

    # 10) gitignore
    gi = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    must = ("data/recognition_corpus/*.sqlite3",
              "data/recognition_corpus/exports/")
    miss = [p for p in must if p not in gi]
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
    md = ["# HWPX-RECOGNITION-LABEL-DICTIONARY-PROMOTION-GATE-01", "",
            f"verdict: **{summary['auditVerdict']}**  "
            f"pass={summary['passCount']}/{summary['totalChecks']}",
            "", "| check | ok | detail |", "|---|---|---|"]
    for f in findings:
        md.append(f"| {f['check']} | "
                     f"{'PASS' if f['ok'] else 'FAIL'} | {f['detail']} |")
    (OUTPUT_DIR / "audit.md").write_text("\n".join(md), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print("[HWPX-RECOGNITION-LABEL-DICTIONARY-PROMOTION-GATE-01 GATE AUDIT]")
    r = run_audit()
    for f in r["findings"]:
        print(f"  {'PASS' if f['ok'] else 'FAIL'} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {r['auditVerdict']}  "
            f"pass={r['passCount']}/{r['totalChecks']}")
    sys.exit(0 if r["auditVerdict"] == "PASS" else 1)
