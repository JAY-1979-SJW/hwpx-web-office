"""문서별 순차 처리 + 목차(즉석 재계산판) 감리.

build_pipeline_index(SQL 조인)와 다른 도구다 — 이쪽은 파일을 매번
다시 열어 ①②③을 순서대로 돌린다(소량 표본·시연용). 외부 I/O(HWPX 로드·
AI 호출)는 전부 monkeypatch 로 끊고, process_one 의 단계 전이·목차
작성기만 고정한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

import scripts.hwpx.web_office.build_document_index as D  # noqa: E402


def _stub_no_inputs(monkeypatch):
    monkeypatch.setattr(D, "load_hwpx_for_editor", lambda req, project_root:
                        {"verdict": "PASS", "documentModel": {}, "renderPayload": {}})
    monkeypatch.setattr(D, "build_input_schema", lambda dm, rp, name, field_count:
                        {"inputs": [], "docType": "기타", "formKind": "행정내부",
                         "inputCount": 0, "applicantCount": 0, "officeCount": 0,
                         "cleanName": name})


def test_process_one_load_failure_short_circuits(monkeypatch):
    monkeypatch.setattr(D, "load_hwpx_for_editor", lambda req, project_root:
                        {"verdict": "REJECTED", "reason": "SOURCE_PATH_MISSING"})
    row = D.process_one(1, "no.hwpx", "이름")
    assert row["stage"] == "SCHEMA" and row["status"] == "LOAD_FAILED"


def test_process_one_stops_at_schema_when_no_inputs(monkeypatch):
    _stub_no_inputs(monkeypatch)
    row = D.process_one(2, "x.hwpx", "빈서식")
    assert row["stage"] == "SCHEMA" and row["status"] == "NO_INPUTS"
    assert "elapsedSec" in row


def test_process_one_reports_interpret_failure(monkeypatch):
    monkeypatch.setattr(D, "load_hwpx_for_editor", lambda req, project_root:
                        {"verdict": "PASS", "documentModel": {}, "renderPayload": {}})
    monkeypatch.setattr(D, "build_input_schema", lambda dm, rp, name, field_count:
                        {"inputs": [{"paragraphId": "p1", "role": "applicant",
                                    "label": "성명"}],
                         "docType": "신청신고", "formKind": "민원신청",
                         "inputCount": 1, "applicantCount": 1, "officeCount": 0,
                         "cleanName": name})
    monkeypatch.setattr(D, "interpret_one", lambda sp, sj, cn:
                        {"status": "AI_FAILED", "error": "AI_TIMEOUT"})
    row = D.process_one(3, "x.hwpx", "서식")
    assert row["stage"] == "INTERPRET" and row["status"] == "AI_FAILED"


def test_process_one_full_pipeline_computes_revival(monkeypatch):
    monkeypatch.setattr(D, "load_hwpx_for_editor", lambda req, project_root:
                        {"verdict": "PASS", "documentModel": {}, "renderPayload": {}})
    monkeypatch.setattr(D, "build_input_schema", lambda dm, rp, name, field_count:
                        {"inputs": [{"paragraphId": "p1", "role": "office",
                                    "label": "검측부위"}],
                         "docType": "기타", "formKind": "행정내부",
                         "inputCount": 1, "applicantCount": 0, "officeCount": 1,
                         "cleanName": name})
    interp = [{"key": "p1", "label": "검측부위", "isInput": True,
              "filledBy": "작성자", "confidence": 0.9, "ruleRole": "office"}]
    monkeypatch.setattr(D, "interpret_one", lambda sp, sj, cn:
                        {"status": "OK",
                         "interpretations": json.dumps(interp, ensure_ascii=False),
                         "author_count": 1, "not_input_count": 0,
                         "semantic_count": 0})
    monkeypatch.setattr(D, "build_context_fields", lambda inputs, dm, title, roles: [])
    monkeypatch.setattr(D, "verify_fields", lambda fields, interp: {
        "ok": True, "agreement": {"agreementRate": 1.0, "disagreedCount": 0,
                                  "disagreed": [], "authorAgreed": ["p1"]}})
    row = D.process_one(4, "x.hwpx", "죽은서식")
    assert row["stage"] == "DONE" and row["status"] == "OK"
    assert row["wasDead"] is True
    assert row["revivedCount"] == 1
    assert row["revivedLabels"] == ["검측부위"]


def test_build_index_writes_jsonl_and_markdown_incrementally(tmp_path, monkeypatch):
    _stub_no_inputs(monkeypatch)
    targets = [(1, "a.hwpx", "서식A"), (2, "b.hwpx", "서식B")]
    out = tmp_path / "idx"
    path = D.build_index(targets, out_dir=out)
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert {json.loads(l)["formId"] for l in lines} == {1, 2}
    md = (out / "document_index.md").read_text(encoding="utf-8")
    assert "#1" in md and "#2" in md and "합계" in md


def test_build_index_resumes_and_skips_done(tmp_path, monkeypatch):
    _stub_no_inputs(monkeypatch)
    out = tmp_path / "idx"
    D.build_index([(1, "a.hwpx", "서식A")], out_dir=out)
    calls = []
    orig = D.process_one

    def spy(*a, **kw):
        calls.append(a[0])
        return orig(*a, **kw)
    monkeypatch.setattr(D, "process_one", spy)
    D.build_index([(1, "a.hwpx", "서식A"), (2, "b.hwpx", "서식B")], out_dir=out)
    assert calls == [2]        # 1번은 재개 스킵, 2번만 새로 처리
    lines = (out / "document_index.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
