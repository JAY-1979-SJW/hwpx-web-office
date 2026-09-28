"""WEB-OFFICE-CELL-SAVE-HWPX-VERIFY7-01 감사 스크립트.

0018 fixture 로 정상 SET_CELL_TEXT 1건 save pipeline 을 실행하여
verify7 V1~V7 PASS, 원본 sha/mtime 무변경, output sandbox 격리,
audit log append 모두 검증한다.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.hwpx_sample_source import (  # noqa: E402
    resolve_sample as _catalog_sample)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)
from scripts.hwpx.web_office.edit_command_model import (  # noqa: E402
    make_set_cell_text_command)
from scripts.hwpx.web_office.cell_save_pipeline import (  # noqa: E402
    save_cell_edits, VERDICT_PASS)
from scripts.hwpx.web_office.cell_save_audit import (  # noqa: E402
    append_save_audit_record)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _resolve_fixture() -> Path | None:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        # 레거시 corpus DB 부재 — 카탈로그 표본으로 대체한다.
        # 이게 없으면 감리가 조용히 SKIP 되어 안 돈 채 통과처럼 보인다.
        return _catalog_sample()
    conn = sqlite3.connect(db)
    row = conn.execute("""
        SELECT d.source_path FROM hwpx_documents d
        JOIN document_classifications c ON c.document_id=d.document_id
        WHERE d.inventory_status='FOUND'
          AND c.document_type='fillable_form'
          AND d.file_size BETWEEN 30000 AND 80000
        ORDER BY d.first_seen_at LIMIT 1
    """).fetchone()
    conn.close()
    return (PR / row[0]) if row and (PR / row[0]).is_file() else None


def audit() -> dict:
    fixture = _resolve_fixture()
    if fixture is None:
        return {"task": "WEB-OFFICE-CELL-SAVE-HWPX-VERIFY7-01",
                    "verdict": "SKIP",
                    "reason": "fixture missing"}

    sha_before = _sha(fixture)
    mtime_before = fixture.stat().st_mtime_ns

    doc = import_hwpx_as_ro_view(fixture)
    # 변경 대상: r3c0 (table 0) — "전화번호" 라벨 셀
    target = next((c for c in doc.cells
                              if c.row == 3 and c.col == 0
                              and c.tableId == "t_s0_000"), None)
    if target is None:
        return {"task": "WEB-OFFICE-CELL-SAVE-HWPX-VERIFY7-01",
                    "verdict": "FAIL", "reason": "target cell missing"}
    after_value = "SAVE_AUDIT_777"
    cmd = make_set_cell_text_command(
        cell_id=target.cellId, table_index=0,
        before=target.text, after=after_value,
        source_document_hash=doc.sourceDocumentHash)

    findings: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="cell_save_audit_") as td:
        out = Path(td) / "audit_out.hwpx"
        res = save_cell_edits(source_path=fixture, output_path=out,
                                              command_log=[cmd])

        if res["verdict"] != VERDICT_PASS:
            findings.append({"code": "PIPELINE_NOT_PASS", "level": "FAIL",
                                      "detail": res})
        v7 = (res.get("verify7") or {}).get("results", {})
        for k in ("V1_POSITION_OK", "V2_NO_CROSS_LEAK",
                          "V3_UNTOUCHED_PRESERVED", "V4_SOURCE_HASH_OK",
                          "V5_EXPECTED_BEFORE_OK", "V6_OUTPUT_ISOLATED",
                          "V7_READBACK_MATCH"):
            if v7.get(k) != "PASS":
                findings.append({"code": f"{k}_FAIL", "level": "FAIL",
                                          "detail": v7.get(k)})

        if not res.get("outputCreated"):
            findings.append({"code": "OUTPUT_NOT_CREATED",
                                      "level": "FAIL"})

        # readback 검증
        if out.is_file():
            out_doc = import_hwpx_as_ro_view(out)
            out_cell = next((c for c in out_doc.cells
                                          if c.cellId == target.cellId), None)
            if out_cell is None or out_cell.text != after_value:
                findings.append({"code": "READBACK_MISMATCH",
                                          "level": "FAIL",
                                          "detail": {
                                              "expected": after_value,
                                              "got": (out_cell.text
                                                            if out_cell else None)}})

        # audit log append 시도 (임시 jsonl 사용 — 운영 audit dir 오염 방지)
        audit_jsonl = Path(td) / "audit.jsonl"
        append_save_audit_record(
            save_result=res, command_log=[cmd],
            source_path=fixture, output_path=out,
            jsonl_path=audit_jsonl)
        if not audit_jsonl.is_file() or audit_jsonl.stat().st_size == 0:
            findings.append({"code": "AUDIT_LOG_NOT_APPENDED",
                                      "level": "FAIL"})

    # 원본 무변경 게이트
    if _sha(fixture) != sha_before:
        findings.append({"code": "SOURCE_SHA_CHANGED", "level": "FAIL"})
    if fixture.stat().st_mtime_ns != mtime_before:
        findings.append({"code": "SOURCE_MTIME_CHANGED",
                                  "level": "FAIL"})

    return {
        "task": "WEB-OFFICE-CELL-SAVE-HWPX-VERIFY7-01",
        "fixture": str(fixture.relative_to(PR)),
        "targetCell": target.cellId,
        "afterValue": after_value,
        "pipelineVerdict": res.get("verdict"),
        "verify7": (res.get("verify7") or {}).get("results"),
        "sourceUnchanged": res.get("sourceUnchanged"),
        "outputCreated": res.get("outputCreated"),
        "outputHash": (res.get("outputHash") or "")[:32],
        "findings": findings,
        "verdict": "PASS" if not findings else "FAIL",
    }


def main() -> int:
    out = audit()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
