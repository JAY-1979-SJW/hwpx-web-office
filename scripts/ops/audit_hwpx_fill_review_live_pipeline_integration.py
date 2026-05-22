"""HWPX-FILL-REVIEW-LIVE-PIPELINE-INTEGRATION-01 게이트 감사."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_fill_review_live_pipeline_audit"
METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


def _build_fixture_with_paragraphs(tmp_path: Path,
                                       paragraph_texts: list[str]):
    ET.register_namespace("hp", NS_HP)
    dst = tmp_path / "fixture.hwpx"
    with zipfile.ZipFile(METADATA_FORM) as zin, \
         zipfile.ZipFile(dst, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = ET.fromstring(data)
                for text in paragraph_texts:
                    p = ET.SubElement(root, f"{{{NS_HP}}}p")
                    run = ET.SubElement(p, f"{{{NS_HP}}}run")
                    t = ET.SubElement(run, f"{{{NS_HP}}}t")
                    t.text = text
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            ni = zipfile.ZipInfo(info.filename, info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            zout.writestr(ni, data)
    return dst, hashlib.sha256(dst.read_bytes()).hexdigest()


def run_audit() -> dict:
    from scripts.hwpx.fill_review import fill_review_live_pipeline as pipe
    from scripts.hwpx.fill_review import fill_review_contract as fr

    findings: list[dict] = []
    tmp = Path(tempfile.mkdtemp(prefix="audit_fill_pipeline_"))

    # 1) READY_FOR_REVIEW (decision 없음 → writer 미호출, output 미생성)
    src, sha = _build_fixture_with_paragraphs(tmp, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    out0 = tmp / "out0.hwpx"
    res_ready = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": out0,
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    findings.append({
        "check": "pipeline_output_required_fields",
        "ok": all(k in res_ready for k in (
            "schemaVersion", "engineVersion", "requestId", "documentId",
            "sourceDocumentHash", "pipelineStatus", "evidenceIngestion",
            "fillReview", "uiPayload", "decisionValidation",
            "approvedEditPlan", "writerResult", "readback",
            "originalUnmodified", "outputCreated", "warnings", "errors",
        )),
        "detail": f"keys={sorted(res_ready.keys())}",
    })
    findings.append({
        "check": "ready_for_review_no_writer_no_output",
        "ok": (res_ready["pipelineStatus"] == "READY_FOR_REVIEW"
                and res_ready["writerResult"] is None
                and not out0.exists()),
        "detail": f"status={res_ready['pipelineStatus']}",
    })

    # 2) blocking missing material → writer 미호출
    src2, sha2 = _build_fixture_with_paragraphs(tmp, ["dummy"])
    rec2 = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha2,
        cells=[
            {"cellKey": "t_s0_000:r3:c0", "normalizedText": "사업자등록번호",
              "rowIndex": 3, "cellIndex": 0},
            {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
              "rowIndex": 3, "cellIndex": 1},
        ],
    )
    out2 = tmp / "out2.hwpx"
    r2_review = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src2, "outputPath": out2,
        "sourceDocumentHash": sha2, "recognitionResult": rec2,
        "evidenceInputs": [],
    })
    items2 = [it for sec in r2_review["uiPayload"]["reviewSections"]
                 for it in sec["items"]]
    dp2 = {
        "documentId": "d", "sourceDocumentHash": sha2,
        "decisions": [{"reviewItemId": items2[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    r2 = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src2, "outputPath": out2,
        "sourceDocumentHash": sha2, "recognitionResult": rec2,
        "evidenceInputs": [], "decisionPayload": dp2,
    })
    findings.append({
        "check": "blocking_missing_material_blocks_writer",
        "ok": (r2["pipelineStatus"] == "BLOCKED_BY_MISSING_MATERIAL"
                and r2["writerResult"] is None and not out2.exists()),
        "detail": f"status={r2['pipelineStatus']}",
    })

    # 3) sourceDocumentHash mismatch → BLOCKED_BY_DECISION_VALIDATION
    src3, sha3 = _build_fixture_with_paragraphs(tmp, ["__PROJECT_NAME__"])
    rec3 = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha3,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    out3 = tmp / "out3.hwpx"
    r3_review = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src3, "outputPath": out3,
        "sourceDocumentHash": sha3, "recognitionResult": rec3,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    items3 = [it for sec in r3_review["uiPayload"]["reviewSections"]
                 for it in sec["items"]]
    dp3 = {
        "documentId": "d", "sourceDocumentHash": "sha:WRONG",
        "decisions": [{"reviewItemId": items3[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    r3 = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src3, "outputPath": out3,
        "sourceDocumentHash": sha3, "recognitionResult": rec3,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
        "decisionPayload": dp3,
    })
    findings.append({
        "check": "source_hash_mismatch_blocks_writer",
        "ok": (r3["pipelineStatus"] == "BLOCKED_BY_DECISION_VALIDATION"
                and not out3.exists()),
        "detail": f"status={r3['pipelineStatus']}",
    })

    # 4) outputPath == sourcePath 차단
    out_eq = tmp / "out_eq.hwpx"
    src4, sha4 = _build_fixture_with_paragraphs(tmp, ["__PROJECT_NAME__"])
    rec4 = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha4,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    r4_review = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src4, "outputPath": src4,
        "sourceDocumentHash": sha4, "recognitionResult": rec4,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    items4 = [it for sec in r4_review["uiPayload"]["reviewSections"]
                 for it in sec["items"]]
    dp4 = {
        "documentId": "d", "sourceDocumentHash": sha4,
        "decisions": [{"reviewItemId": items4[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    sha_pre = hashlib.sha256(src4.read_bytes()).hexdigest()
    r4 = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src4, "outputPath": src4,
        "sourceDocumentHash": sha4, "recognitionResult": rec4,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
        "decisionPayload": dp4,
    })
    findings.append({
        "check": "output_equals_source_blocked",
        "ok": (r4["pipelineStatus"] == "WRITER_BLOCKED"
                and any(e.get("code") == "OUTPUT_OVERWRITES_SOURCE"
                          for e in r4["errors"])
                and hashlib.sha256(src4.read_bytes()).hexdigest() == sha_pre),
        "detail": f"status={r4['pipelineStatus']}",
    })

    # 5) APPROVE / paragraph → WRITER_APPLIED + output 생성
    src5, sha5 = _build_fixture_with_paragraphs(tmp, ["__PROJECT_NAME__"])
    rec5 = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha5,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    out5 = tmp / "out5.hwpx"
    r5_review = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src5, "outputPath": out5,
        "sourceDocumentHash": sha5, "recognitionResult": rec5,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    items5 = [it for sec in r5_review["uiPayload"]["reviewSections"]
                 for it in sec["items"]]
    dp5 = {
        "documentId": "d", "sourceDocumentHash": sha5,
        "decisions": [{"reviewItemId": items5[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    sha_pre5 = hashlib.sha256(src5.read_bytes()).hexdigest()
    r5 = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src5, "outputPath": out5,
        "sourceDocumentHash": sha5, "recognitionResult": rec5,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
        "decisionPayload": dp5,
    })
    findings.append({
        "check": "approve_paragraph_writes_output",
        "ok": (r5["pipelineStatus"] == "WRITER_APPLIED"
                and out5.exists()
                and hashlib.sha256(src5.read_bytes()).hexdigest() == sha_pre5),
        "detail": f"status={r5['pipelineStatus']}",
    })

    # 6) naming locks
    findings.append({
        "check": "set_paragraph_text_official_name_locked",
        "ok": (pipe.OP_TO_WRITER_METHOD["setParagraphText"]
                == "writer.set_paragraph_text"
                and "setParagraphText" in pipe.PIPELINE_ALLOWED_OPERATIONS),
        "detail": f"map={pipe.OP_TO_WRITER_METHOD}",
    })
    findings.append({
        "check": "set_cell_paragraph_text_forbidden",
        "ok": ("setCellParagraphText" not in pipe.PIPELINE_ALLOWED_OPERATIONS
                and "setCellParagraphText" not in pipe.OP_TO_WRITER_METHOD),
        "detail": "forbidden name not in pipeline whitelist",
    })

    # 7) ApprovedEditPlan operations ⊆ PIPELINE_ALLOWED
    ops5 = (r5["approvedEditPlan"] or {}).get("operations", [])
    findings.append({
        "check": "approved_operations_within_pipeline_whitelist",
        "ok": all(op["operationType"] in pipe.PIPELINE_ALLOWED_OPERATIONS
                     for op in ops5),
        "detail": f"types={[o['operationType'] for o in ops5]}",
    })

    # 8) readback divergences == [] for successful case
    rb = (r5.get("readback") or {})
    findings.append({
        "check": "readback_has_no_divergences_on_success",
        "ok": (rb.get("divergences") == []
                or rb.get("divergences") is None),
        "detail": f"divergences={rb.get('divergences')}",
    })

    summary = {
        "totalChecks": len(findings),
        "passCount": sum(1 for f in findings if f["ok"]),
        "failCount": sum(1 for f in findings if not f["ok"]),
        "findings": findings,
        "auditVerdict": "PASS" if all(f["ok"] for f in findings) else "FAIL",
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "audit.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    print("[HWPX-FILL-REVIEW-LIVE-PIPELINE-INTEGRATION-01 GATE AUDIT]")
    result = run_audit()
    for f in result["findings"]:
        flag = "PASS" if f["ok"] else "FAIL"
        print(f"  {flag} {f['check']}: {f['detail']}")
    print("=" * 60)
    print(f"verdict: {result['auditVerdict']}  "
          f"pass={result['passCount']}/{result['totalChecks']}")
    sys.exit(0 if result["auditVerdict"] == "PASS" else 1)
