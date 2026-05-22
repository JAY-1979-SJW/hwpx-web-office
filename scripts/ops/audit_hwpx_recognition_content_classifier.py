"""HWPX-RECOGNITION-CONTENT-CLASSIFIER-CONTRACT-01 — gate audit."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports/hwpx_recognition_content_classifier_audit"


class _Cell:
    def __init__(self, r, c, t, tid="t"):
        self.tableId = tid; self.row = r; self.col = c
        self.normalizedText = t


class _Para:
    def __init__(self, t): self.normalizedText = t


class _Table:
    def __init__(self, cells, tid="t"):
        self.tableId = tid; self.cells = cells


class _Res:
    def __init__(self, tables, paras=()):
        self.tables = tables; self.paragraphs = list(paras)


def _fillable_fixture():
    cells = []
    for i, lbl in enumerate(["신청인", "대표자", "주소", "전화번호",
                                "상호", "성명", "접수번호", "접수일자"]):
        cells.append(_Cell(i, 0, lbl))
        cells.append(_Cell(i, 1, ""))
    return _Res([_Table(cells)], [_Para("신청서 작성")])


def _reference_fixture():
    cells = [_Cell(r, c, f"기준값{r}-{c}")
                 for r in range(20) for c in range(5)]
    return _Res([_Table(cells)],
                  [_Para("작성기준 단위량 산출기준 별표"), _Para("보유기준")])


def _empty_fixture():
    return _Res([], [])


def run_audit() -> dict:
    from scripts.hwpx.recognition_corpus import content_classifier as cc
    from scripts.hwpx.recognition_corpus import corpus_schema as cs

    findings: list[dict] = []
    mod_path = (PROJECT_ROOT
                  / "scripts/hwpx/recognition_corpus/content_classifier.py")

    findings.append({"check": "module_exists",
                       "ok": mod_path.is_file(),
                       "detail": str(mod_path.relative_to(PROJECT_ROOT))})

    findings.append({"check": "classifier_version",
                       "ok": cc.CLASSIFIER_VERSION == "content_classifier_v1",
                       "detail": cc.CLASSIFIER_VERSION})

    # fillable
    f = cc.extract_content_features(_fillable_fixture(),
                                          "samples/[별지 1] 신청서.hwpx")
    r1 = cc.classify_document_content(f, document_id="fillX")
    findings.append({"check": "fillable_fixture_classified",
                       "ok": r1["contentType"] == "fillable_form",
                       "detail": f"type={r1['contentType']} "
                                   f"sub={r1['subType']} "
                                   f"conf={r1['confidence']}"})

    # reference
    f = cc.extract_content_features(_reference_fixture(),
                                          "samples/[별표 1] 기준.hwpx")
    r2 = cc.classify_document_content(f, document_id="refX")
    findings.append({"check": "reference_fixture_classified",
                       "ok": r2["contentType"] == "reference_table",
                       "detail": f"type={r2['contentType']} "
                                   f"conf={r2['confidence']}"})

    # empty
    f = cc.extract_content_features(_empty_fixture(),
                                          "tests/fixtures/hwpx/gantt/x.hwpx")
    r3 = cc.classify_document_content(f, document_id="emptyX")
    findings.append({"check": "empty_fixture_classified",
                       "ok": r3["contentType"] == "empty_template",
                       "detail": f"type={r3['contentType']} "
                                   f"sub={r3['subType']}"})

    # required fields
    must = ("schemaVersion", "engineVersion", "classifierVersion",
              "documentId", "filenamePatternType", "contentType",
              "subType", "confidence", "evidence", "featureSummary",
              "disagreement", "ambiguous", "warnings")
    findings.append({"check": "required_result_fields",
                       "ok": all(k in r1 for k in must),
                       "detail": f"missing="
                                   f"{[k for k in must if k not in r1]}"})

    # disagreement
    f = cc.extract_content_features(_reference_fixture(), "x.hwpx")
    rd = cc.classify_document_content(f, filename_type="fillable_form",
                                          document_id="dX")
    findings.append({"check": "filename_content_disagreement_detected",
                       "ok": rd["disagreement"] is True
                              and "NEEDS_HUMAN_REVIEW" in rd["warnings"],
                       "detail": f"disagreement={rd['disagreement']} "
                                   f"warnings={rd['warnings']}"})

    # DB compatibility
    try:
        conn = cs.open_corpus_db(":memory:")
        conn.execute(
            "INSERT INTO hwpx_documents "
            "(document_id, source_path, source_kind, file_size, mtime,"
            " detected_type, inventory_status, sha256, first_seen_at) "
            "VALUES ('d','/x','collected',1,1.0,'hwpx','FOUND',?,'now')",
            ("0" * 64,),
        )
        rec = cc.build_document_classification_record(r1, classified_at="now")
        rec["document_id"] = "d"
        conn.execute(
            "INSERT INTO document_classifications "
            "(document_id, classifier_version, document_type, confidence,"
            " evidence_json, classified_at) VALUES (?,?,?,?,?,?)",
            (rec["document_id"], rec["classifier_version"],
                rec["document_type"], rec["confidence"],
                rec["evidence_json"], rec["classified_at"]),
        )
        conn.commit()
        n = conn.execute(
            "SELECT COUNT(*) FROM document_classifications"
        ).fetchone()[0]
        conn.close()
        findings.append({"check": "db_record_compatible",
                           "ok": n == 1,
                           "detail": f"rows={n}"})
    except Exception as e:
        findings.append({"check": "db_record_compatible",
                           "ok": False, "detail": str(e)})

    # production isolation
    iso = cs.audit_production_isolation()
    findings.append({"check": "production_isolation_maintained",
                       "ok": iso["ok"],
                       "detail": (f"violations={iso['violations']}"
                                    if iso["violations"] else "clean")})

    # no writer/output/AI/OCR static check on module source
    src = mod_path.read_text(encoding="utf-8")
    bad = [n for n in ("execute_writer_call_plan_live_sandbox",
                            "import anthropic", "import openai",
                            "pytesseract", "ZipFile(",
                            "corpus.sqlite3", "open_corpus_db")
              if n in src]
    findings.append({"check": "no_writer_no_output_no_ai_no_ocr_no_db_write",
                       "ok": not bad, "detail": f"bad={bad}"})

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
        encoding="utf-8",
    )
    md = ["# HWPX-RECOGNITION-CONTENT-CLASSIFIER-CONTRACT-01", "",
            f"verdict: **{summary['auditVerdict']}**  "
            f"pass={summary['passCount']}/{summary['totalChecks']}",
            "", "| check | ok | detail |", "|---|---|---|"]
    for f in findings:
        md.append(f"| {f['check']} | {'PASS' if f['ok'] else 'FAIL'} "
                     f"| {f['detail']} |")
    (OUTPUT_DIR / "audit.md").write_text("\n".join(md), encoding="utf-8")
    return summary


if __name__ == "__main__":
    print("[HWPX-RECOGNITION-CONTENT-CLASSIFIER-CONTRACT-01 GATE AUDIT]")
    r = run_audit()
    for f in r["findings"]:
        print(f"  {'PASS' if f['ok'] else 'FAIL'} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {r['auditVerdict']}  "
            f"pass={r['passCount']}/{r['totalChecks']}")
    sys.exit(0 if r["auditVerdict"] == "PASS" else 1)
