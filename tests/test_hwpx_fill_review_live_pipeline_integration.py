"""HWPX-FILL-REVIEW-LIVE-PIPELINE-INTEGRATION-01 테스트.

문서 인지 → evidence → fill review → UI payload → decision → ApprovedEditPlan →
live sandbox writer → readback 종단 통합 시나리오.
"""
from __future__ import annotations

import hashlib
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"

METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"


@pytest.fixture(scope="module")
def pipe():
    from hwpx.fill_review import fill_review_live_pipeline as p
    return p


@pytest.fixture(scope="module")
def fr():
    from hwpx.fill_review import fill_review_contract as m
    return m


@pytest.fixture(scope="module")
def ui_mod():
    from hwpx.fill_review import fill_review_ui_adapter as m
    return m


@pytest.fixture(scope="module")
def ingest():
    from hwpx.fill_review import evidence_ingestion_contract as m
    return m


def _build_fixture_with_paragraphs(tmp_path: Path,
                                       paragraph_texts: list[str]) -> tuple[Path, str]:
    """METADATA_FORM 사본 + section0에 top-level <hp:p> append. 원본은 무수정."""
    ET.register_namespace("hp", NS_HP)
    dst = tmp_path / "fixture_with_paragraphs.hwpx"
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
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            zout.writestr(new_info, data)
    sha = hashlib.sha256(dst.read_bytes()).hexdigest()
    return dst, sha


def _read_paragraph_visible(zip_path: Path, section_idx: int, paragraph_idx: int) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        sec_paths = sorted(n for n in zf.namelist()
                              if "section" in n and n.endswith(".xml"))
        raw = zf.read(sec_paths[section_idx])
    root = ET.fromstring(raw)
    ps = [c for c in list(root) if c.tag == f"{{{NS_HP}}}p"]
    TAG_T = f"{{{NS_HP}}}t"
    TAG_TBL = f"{{{NS_HP}}}tbl"
    p = ps[paragraph_idx]
    parts: list[str] = []
    def walk(e):
        if e.tag == TAG_TBL:
            return
        if e.tag == TAG_T and e.text:
            parts.append(e.text)
        for c in list(e):
            walk(c)
    for c in list(p):
        walk(c)
    return "".join(parts)


def _read_cell_text(zip_path: Path, section_idx: int, table_idx: int,
                       row: int, col: int) -> str:
    with zipfile.ZipFile(zip_path) as zf:
        sec_paths = sorted(n for n in zf.namelist()
                              if "section" in n and n.endswith(".xml"))
        raw = zf.read(sec_paths[section_idx])
    root = ET.fromstring(raw)
    TAG_TBL = f"{{{NS_HP}}}tbl"
    TAG_TR = f"{{{NS_HP}}}tr"
    TAG_TC = f"{{{NS_HP}}}tc"
    TAG_T = f"{{{NS_HP}}}t"
    tbl_count = 0
    for tbl in root.iter(TAG_TBL):
        if tbl_count != table_idx:
            tbl_count += 1
            continue
        for r_idx, tr in enumerate([c for c in tbl if c.tag == TAG_TR]):
            if r_idx != row:
                continue
            for c_idx, tc in enumerate([c for c in tr if c.tag == TAG_TC]):
                if c_idx != col:
                    continue
                parts = [t.text for t in tc.iter(TAG_T) if t.text]
                return "".join(parts)
    return ""


# ── 시나리오 헬퍼 ────────────────────────────────────────────────────────────

def _paragraph_scenario_input(fr, tmp_path, *,
                                   placeholder_text="__PROJECT_NAME__",
                                   evidence_value="ABC프로젝트",
                                   include_decision=True,
                                   decision="APPROVE",
                                   edited=None,
                                   sha_override=None):
    """fixture-with-paragraphs + recognition + evidence + decision payload 구성.

    return input_dict ready for run_fill_review_live_pipeline_sandbox.
    """
    src, sha = _build_fixture_with_paragraphs(tmp_path, [placeholder_text])
    # 첫 placeholder는 paragraphIndex=1 (기존 p[0] + 추가 1개)
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha, sourcePath=str(src),
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": placeholder_text}],
    )
    evidence_inputs = []
    if evidence_value is not None:
        evidence_inputs.append({
            "inputId": "in1", "sourceName": "contract.xlsx",
            "sourceHash": "sha:ev", "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": evidence_value},
        })
    decision_payload = None
    if include_decision:
        # decision은 reviewItem 1건에 대해 만들어 줘야 한다
        decision_payload = {
            "documentId": "d", "sourceDocumentHash": sha_override or sha,
            "decisions": [],   # 채워서 보낼 예정 — orchestrator 호출 전 reviewItem id를 알아야 한다
        }
    return {
        "sourcePath": src, "sha": sha,
        "rec": rec, "evidence_inputs": evidence_inputs,
        "decision_payload": decision_payload,
        "decision": decision, "edited": edited,
        "include_decision": include_decision,
    }


def _run_paragraph_scenario(pipe, ui_mod, tmp_path, scenario, output_name="out.hwpx",
                                sha_override_for_input=None):
    src = scenario["sourcePath"]
    sha = scenario["sha"]
    output = tmp_path / output_name

    # 미리 한 번 review-only 모드로 돌려서 reviewItem id 얻기
    review_only = {
        "sourcePath": src, "outputPath": output,
        "sourceDocumentHash": sha,
        "recognitionResult": scenario["rec"],
        "evidenceInputs": scenario["evidence_inputs"],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    review_items = [it for sec in r0["uiPayload"]["reviewSections"]
                       for it in sec["items"]]
    decision_payload = scenario["decision_payload"]
    if decision_payload is not None and review_items:
        d = {"reviewItemId": review_items[0]["reviewItemId"],
              "decision": scenario["decision"],
              "userComment": "", "decidedBy": "u", "decidedAt": "now"}
        if scenario["edited"] is not None:
            d["editedValue"] = scenario["edited"]
        decision_payload["decisions"] = [d]
        if sha_override_for_input is not None:
            decision_payload["sourceDocumentHash"] = sha_override_for_input
    input_dict = {
        "sourcePath": src, "outputPath": output,
        "sourceDocumentHash": sha,
        "recognitionResult": scenario["rec"],
        "evidenceInputs": scenario["evidence_inputs"],
        "decisionPayload": decision_payload,
    }
    return input_dict, pipe.run_fill_review_live_pipeline_sandbox(input_dict)


# ── T01: blocking missing material → BLOCKED_BY_MISSING_MATERIAL ────────────

def test_blocking_missing_material_blocks_writer(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    # 사업자등록번호 라벨 → BUSINESS_LICENSE 자료 필요. evidence 비움.
    cells = [
        {"cellKey": "t_s0_000:r3:c0", "normalizedText": "사업자등록번호",
          "rowIndex": 3, "cellIndex": 0},
        {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
          "rowIndex": 3, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha, sourcePath=str(src), cells=cells,
    )
    # decision으로 APPROVE 시도해도 blocking material 때문에 차단
    review_only = {
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha,
        "recognitionResult": rec,
        "evidenceInputs": [],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    # 가짜로 APPROVE 시도
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "BLOCKED_BY_MISSING_MATERIAL"
    assert res["writerResult"] is None
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before
    assert not (tmp_path / "out.hwpx").exists()


# ── T02: evidence 있음 → FillMatch + ReviewItem READY_FOR_REVIEW ────────────

def test_evidence_produces_ready_for_review_match(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in1", "sourceName": "contract.xlsx",
            "sourceHash": "sha:e", "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    assert res["pipelineStatus"] == "READY_FOR_REVIEW"
    assert len(res["fillReview"]["matches"]) == 1


# ── T03: decision 없음 → READY_FOR_REVIEW, writer 미호출 ───────────────────

def test_no_decision_returns_ready_for_review_without_writer(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    assert res["pipelineStatus"] == "READY_FOR_REVIEW"
    assert res["writerResult"] is None
    assert not (tmp_path / "out.hwpx").exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T04~T05: APPROVE / EDIT_VALUE → operation 생성 ─────────────────────────

def test_approve_paragraph_produces_writer_apply(pipe, fr, ui_mod, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          placeholder_text="__PROJECT_NAME__",
                                          evidence_value="ABC프로젝트",
                                          decision="APPROVE")
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "WRITER_APPLIED"
    assert res["writerResult"] is not None
    assert res["outputCreated"] is True
    assert res["originalUnmodified"] is True
    # 원본 sha256 무변경
    assert hashlib.sha256(sc["sourcePath"].read_bytes()).hexdigest() == sc["sha"]


def test_edit_value_paragraph_uses_user_value(pipe, fr, ui_mod, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          placeholder_text="__PROJECT_NAME__",
                                          evidence_value="EVIDENCE_VAL",
                                          decision="EDIT_VALUE",
                                          edited="USER_EDITED_VAL")
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "WRITER_APPLIED"
    output = inp["outputPath"]
    assert _read_paragraph_visible(output, 0, 1) == "USER_EDITED_VAL"


# ── T06~T08: REJECT / HOLD / REQUEST_MATERIAL → operation 미생성 ───────────

def _make_decision_only_review(pipe, fr, tmp_path, decision):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          evidence_value="V", decision=decision)
    inp, res = _run_paragraph_scenario(pipe, ui_mod_module := __import__(
        "hwpx.fill_review.fill_review_ui_adapter", fromlist=["x"]),
                                            tmp_path, sc)
    return inp, res


def test_reject_produces_no_operation(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path, decision="REJECT")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "BLOCKED_BY_EMPTY_APPROVALS"
    assert res["writerResult"] is None
    assert not Path(inp["outputPath"]).exists()


def test_hold_produces_no_operation(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path, decision="HOLD")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "BLOCKED_BY_EMPTY_APPROVALS"


# ── T08: REQUEST_MATERIAL ──────────────────────────────────────────────────

def test_request_material_alone_no_writer(pipe, fr, tmp_path):
    """REQUEST_MATERIAL은 missing request 시나리오에서만 의미가 있다."""
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    cells = [
        {"cellKey": "t_s0_000:r3:c0", "normalizedText": "직인",
          "rowIndex": 3, "cellIndex": 0},
        {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
          "rowIndex": 3, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha, cells=cells,
    )
    review_only = {
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "REQUEST_MATERIAL",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    # REQUEST_MATERIAL이면 blocking missing material 때문에 차단
    assert res["pipelineStatus"] in (
        "BLOCKED_BY_MISSING_MATERIAL", "BLOCKED_BY_EMPTY_APPROVALS",
    )
    assert res["writerResult"] is None


# ── T09~T11: decision validation failure → BLOCKED_BY_DECISION_VALIDATION ─

def test_source_hash_mismatch_blocked(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          decision="APPROVE",
                                          sha_override="sha:WRONG")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc,
                                            sha_override_for_input="sha:WRONG")
    assert res["pipelineStatus"] == "BLOCKED_BY_DECISION_VALIDATION"
    assert res["writerResult"] is None
    assert not Path(inp["outputPath"]).exists()


def test_duplicate_decision_blocked(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    review_only = {
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "A"},
        }],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    rid = items[0]["reviewItemId"]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [
            {"reviewItemId": rid, "decision": "APPROVE",
              "userComment": "", "decidedBy": "u", "decidedAt": "now"},
            {"reviewItemId": rid, "decision": "REJECT",
              "userComment": "", "decidedBy": "u", "decidedAt": "now"},
        ],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "BLOCKED_BY_DECISION_VALIDATION"
    assert res["writerResult"] is None


def test_unknown_review_item_blocked(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    review_only = {
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "A"},
        }],
    }
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": "rev_NOT_EXISTS",
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "BLOCKED_BY_DECISION_VALIDATION"


# ── T12~T13: APPROVE + setParagraphText / setCellText ──────────────────────

def test_approve_cell_text_writes_output(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    # METADATA_FORM의 r3:c1은 실제로 빈 셀 (raw)
    cells = [
        {"cellKey": "t_s0_000:r3:c0", "normalizedText": "공사명",
          "rowIndex": 3, "cellIndex": 0},
        {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
          "rowIndex": 3, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha, cells=cells,
    )
    output = tmp_path / "out_cell.hwpx"
    review_only = {
        "sourcePath": src, "outputPath": output,
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC공사"},
        }],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "WRITER_APPLIED", res
    assert output.exists()
    assert "ABC공사" in _read_cell_text(output, 0, 0, 3, 1)


# ── T14: EDIT_VALUE + setCellText reflected in output ─────────────────────

def test_edit_value_cell_text_reflected(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    cells = [
        {"cellKey": "t_s0_000:r3:c0", "normalizedText": "공사명",
          "rowIndex": 3, "cellIndex": 0},
        {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
          "rowIndex": 3, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha, cells=cells,
    )
    output = tmp_path / "out_edit_cell.hwpx"
    review_only = {
        "sourcePath": src, "outputPath": output,
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "AUTO"},
        }],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "EDIT_VALUE", "editedValue": "USER",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "WRITER_APPLIED"
    assert "USER" in _read_cell_text(output, 0, 0, 3, 1)


# ── T16: replaceTextRun smoke via OP_TO_WRITER_METHOD ──────────────────────

def test_replace_text_run_mapped_in_pipeline(pipe):
    assert "replaceTextRun" in pipe.OP_TO_WRITER_METHOD
    assert pipe.OP_TO_WRITER_METHOD["replaceTextRun"] == "writer.replace_text_run"
    assert "setParagraphText" in pipe.OP_TO_WRITER_METHOD
    assert "setCellText" in pipe.OP_TO_WRITER_METHOD


# ── T17: expectedBefore mismatch → writer blocked (paragraph op 경로) ──────

def test_expected_before_mismatch_blocks_writer(pipe, fr, tmp_path):
    # 실제 paragraph text는 "ACTUAL_TEXT"인데 recognition은 placeholder "__PROJECT_NAME__"라고
    # 주장 → fill_review가 expectedBefore="__PROJECT_NAME__"인 operation을 만들고
    # → live writer가 실제 paragraph text와 비교 → mismatch → BLOCKED
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["ACTUAL_TEXT"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001",
                       "text": "__PROJECT_NAME__"}],   # 실제와 다른 텍스트 주장
    )
    output = tmp_path / "out_mis.hwpx"
    review_only = {
        "sourcePath": src, "outputPath": output,
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "NEW"},
        }],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "WRITER_BLOCKED"
    assert res["outputCreated"] is False
    assert not output.exists()
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T18: sourceDocumentHash 누락 → BLOCKED_BY_SOURCE_HASH ──────────────────

def test_missing_source_doc_hash_blocks(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash="",
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    dp = {
        "documentId": "d", "sourceDocumentHash": "",
        "decisions": [{"reviewItemId": "rev_001",
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": "",
        "recognitionResult": rec, "evidenceInputs": [],
        "decisionPayload": dp,
    })
    # decision validation 단계에서 source hash mismatch → BLOCKED_BY_DECISION_VALIDATION
    # 혹은 build_approved_edit_plan에서 BLOCKED_INVALID_PLAN → BLOCKED_BY_EMPTY_APPROVALS
    assert res["pipelineStatus"] in (
        "BLOCKED_BY_SOURCE_HASH", "BLOCKED_BY_DECISION_VALIDATION",
        "BLOCKED_BY_EMPTY_APPROVALS", "BLOCKED_BY_MISSING_MATERIAL",
    )
    assert res["writerResult"] is None
    assert not (tmp_path / "out.hwpx").exists()


# ── T19: outputPath == sourcePath → 차단 ──────────────────────────────────

def test_output_equals_source_blocked(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    review_only = {
        "sourcePath": src, "outputPath": src,
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "X"},
        }],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "WRITER_BLOCKED"
    assert any(e.get("code") == "OUTPUT_OVERWRITES_SOURCE" for e in res["errors"])
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before


# ── T20: readback mismatch monkeypatch ────────────────────────────────────

def test_readback_failed_via_monkeypatch(pipe, fr, tmp_path, monkeypatch):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    output = tmp_path / "out_rb.hwpx"

    class FakeWriterResult:
        verdict = "FAIL_READBACK_MISMATCH"
        originalUnmodified = True
        outputCreated = False
        readback = None

        def to_dict(self):
            return {"verdict": self.verdict,
                      "originalUnmodified": self.originalUnmodified,
                      "outputCreated": self.outputCreated,
                      "readback": {"divergences": ["forced"]}}

    def fake_live(wcp, src_p, out_p):
        return FakeWriterResult()

    review_only = {
        "sourcePath": src, "outputPath": output,
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    }, live_writer=fake_live)
    assert res["pipelineStatus"] == "READBACK_FAILED"


# ── T21-T22: 원본 sha256/mtime + output 격리 ───────────────────────────────

def test_source_unchanged_and_output_isolated(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          placeholder_text="__PROJECT_NAME__",
                                          evidence_value="ABC")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    src = sc["sourcePath"]
    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    mtime_before = src.stat().st_mtime
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "WRITER_APPLIED"
    assert hashlib.sha256(src.read_bytes()).hexdigest() == sha_before
    assert src.stat().st_mtime == mtime_before
    assert Path(inp["outputPath"]).exists()
    assert Path(inp["outputPath"]) != src


def test_blocked_case_no_output(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path, decision="REJECT")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "BLOCKED_BY_EMPTY_APPROVALS"
    assert not Path(inp["outputPath"]).exists()


# ── T24: confidence=0.99 + decision 없음 → writer 미호출 ──────────────────

def test_high_confidence_without_decision_no_writer(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "x.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    assert res["pipelineStatus"] == "READY_FOR_REVIEW"
    assert res["writerResult"] is None
    assert not (tmp_path / "x.hwpx").exists()


# ── T25: blocking missing material + APPROVE → writer 미호출 ──────────────

def test_blocking_missing_material_blocks_even_with_approve(pipe, fr, tmp_path):
    """T01과 동일 시나리오 — 명시적 회귀."""
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    cells = [
        {"cellKey": "t_s0_000:r3:c0", "normalizedText": "사업자등록번호",
          "rowIndex": 3, "cellIndex": 0},
        {"cellKey": "t_s0_000:r3:c1", "normalizedText": "",
          "rowIndex": 3, "cellIndex": 1},
    ]
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha, cells=cells,
    )
    review_only = {
        "sourcePath": src, "outputPath": tmp_path / "out.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [],
    }
    r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
    items = [it for sec in r0["uiPayload"]["reviewSections"]
                for it in sec["items"]]
    dp = {
        "documentId": "d", "sourceDocumentHash": sha,
        "decisions": [{"reviewItemId": items[0]["reviewItemId"],
                          "decision": "APPROVE",
                          "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
    }
    res = pipe.run_fill_review_live_pipeline_sandbox({
        **review_only, "decisionPayload": dp,
    })
    assert res["pipelineStatus"] == "BLOCKED_BY_MISSING_MATERIAL"
    assert res["writerResult"] is None


# ── T27-T28: naming locks ─────────────────────────────────────────────────

def test_set_paragraph_text_name_locked(pipe):
    assert "setParagraphText" in pipe.PIPELINE_ALLOWED_OPERATIONS
    assert pipe.OP_TO_WRITER_METHOD["setParagraphText"] == "writer.set_paragraph_text"


def test_set_cell_paragraph_text_not_in_pipeline(pipe):
    assert "setCellParagraphText" not in pipe.PIPELINE_ALLOWED_OPERATIONS
    assert "setCellParagraphText" not in pipe.OP_TO_WRITER_METHOD


# ── T29: UI payload summary 정합성 ────────────────────────────────────────

def test_ui_payload_counts_consistent(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["__PROJECT_NAME__"])
    rec = fr.make_document_recognition_result(
        documentId="d", sourceDocumentHash=sha,
        paragraphs=[{"paragraphKey": "p_s0_0001", "text": "__PROJECT_NAME__"}],
    )
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "x.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
            "sourceTypeHint": "CONTRACT_XLSX",
            "extractedFields": {"projectName": "ABC"},
        }],
    })
    summary = res["uiPayload"]["summary"]
    item_count = len(res["fillReview"]["reviewItems"])
    assert summary["totalReviewItems"] == item_count


# ── T30: evidence rejected/warnings 보존 ─────────────────────────────────

def test_evidence_rejected_reflected_in_pipeline_warnings(pipe, fr, tmp_path):
    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    rec = fr.make_document_recognition_result(documentId="d",
                                                    sourceDocumentHash=sha)
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "x.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [{
            "inputId": "bad", "sourceName": "x", "sourceHash": "",  # 누락
            "extractedFields": {"projectName": "Y"},
        }],
    })
    assert res["evidenceIngestion"]["rejectedCount"] == 1
    assert any(w.get("code") == "EVIDENCE_INPUTS_REJECTED"
                for w in res["warnings"])


# ── T31: ApprovedEditPlan.operations whitelist ───────────────────────────

def test_approved_operations_are_subset_of_pipeline_allowed(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          placeholder_text="__PROJECT_NAME__",
                                          evidence_value="ABC")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    ops = (res["approvedEditPlan"] or {}).get("operations", []) or []
    for op in ops:
        assert op["operationType"] in pipe.PIPELINE_ALLOWED_OPERATIONS


# ── T32: writerResult/readback in pipeline output ────────────────────────

def test_writer_and_readback_in_pipeline_output(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          placeholder_text="__PROJECT_NAME__",
                                          evidence_value="ABC")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["writerResult"] is not None
    assert "readback" in res
    assert res["pipelineStatus"] == "WRITER_APPLIED"


# ── T33: writer not invoked on blocked path ──────────────────────────────

def test_writer_not_invoked_on_blocked_path(pipe, fr, tmp_path):
    call_log: list = []

    def fake_live(*a, **k):
        call_log.append("live")
        raise AssertionError("writer should not be called")

    src, sha = _build_fixture_with_paragraphs(tmp_path, ["dummy"])
    rec = fr.make_document_recognition_result(documentId="d",
                                                    sourceDocumentHash=sha)
    # decision payload 없음 → READY_FOR_REVIEW
    res = pipe.run_fill_review_live_pipeline_sandbox({
        "sourcePath": src, "outputPath": tmp_path / "x.hwpx",
        "sourceDocumentHash": sha, "recognitionResult": rec,
        "evidenceInputs": [],
    }, live_writer=fake_live)
    assert res["pipelineStatus"] == "READY_FOR_REVIEW"
    assert call_log == []


# ── T34: writer 호출 케이스 verify (실제 live sandbox) ──────────────────

def test_writer_invoked_on_approve_path(pipe, fr, tmp_path):
    sc = _paragraph_scenario_input(fr, tmp_path,
                                          placeholder_text="__PROJECT_NAME__",
                                          evidence_value="VAL")
    from hwpx.fill_review import fill_review_ui_adapter as ui_mod
    inp, res = _run_paragraph_scenario(pipe, ui_mod, tmp_path, sc)
    assert res["pipelineStatus"] == "WRITER_APPLIED"
    assert res["outputCreated"] is True


# ── T42: audit script PASS ────────────────────────────────────────────────

def test_audit_script_passes():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "audit_hwpx_fill_review_live_pipeline_integration",
        PROJECT_ROOT
        / "scripts/ops/audit_hwpx_fill_review_live_pipeline_integration.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    result = mod.run_audit()
    assert result["auditVerdict"] == "PASS", result
