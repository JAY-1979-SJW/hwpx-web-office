"""WEB-OFFICE PARA-EDIT E2E pipeline — 기존 자재 orchestration.

ro_view_importer → para_edit_model(EditCommand v2) →
paragraph_edit_plan → paragraph_writer_adapter (paragraph_save_pipeline 경유)
→ paragraph_save_verify7 → readback 동선을 하나의 함수로 묶는다.

본 모듈은 신규 기능을 추가하지 않는다. 기존 자재만 호출하며,
writer / output / 원본 HWPX 의 mutation API 는 일절 호출하지 않는다
(save_paragraph_edits 가 내부에서 활성화하는 writer 경로만 사용).
"""
from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))

from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view,
)
from scripts.hwpx.web_office.para_edit_model import (  # noqa: E402
    Paragraph, ParaTextRun, ParagraphTarget,
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command, make_apply_format_command,
    CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
    CT_APPLY_FORMAT,
)
from scripts.hwpx.web_office.paragraph_save_pipeline import (  # noqa: E402
    save_paragraph_edits,
    VERDICT_PASS, VERDICT_PARTIAL, VERDICT_FAIL,
    VERDICT_REJECTED, VERDICT_NOOP,
)


SCENARIO_TYPE = "TYPE_TEXT"
SCENARIO_REPLACE = "REPLACE_TEXT_RANGE"
SCENARIO_DELETE = "DELETE_TEXT_RANGE"
SCENARIO_APPLY_FORMAT = "APPLY_FORMAT"

E2E_SCENARIOS = {SCENARIO_TYPE, SCENARIO_REPLACE, SCENARIO_DELETE,
                  SCENARIO_APPLY_FORMAT}

# WEB-OFFICE-PARA-READBACK-PARSER-01 — readback gate 결과 코드.
READBACK_PASS = "PASS"
READBACK_FAIL = "FAIL"
READBACK_DEFERRED = "DEFERRED"
READBACK_SKIP = "SKIP"

# WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 — TYPE_TEXT expectedBefore 계약을
# 빈 range slice 기준으로 정렬해 readback gate 활성화.
_READBACK_SCENARIOS = {SCENARIO_REPLACE, SCENARIO_DELETE, SCENARIO_TYPE,
                                              SCENARIO_APPLY_FORMAT}


def _expected_after_paragraph_text(
    before: str, applied: list[dict],
) -> str:
    """applied[] 의 (rangeStart, rangeEnd, afterText) 를 before 에 순차 적용.

    본 공정 범위는 1 paragraph · 1 edit 시나리오. 다중 편집 ordering 은 별도
    공정 (multi-edit writer 활성화) 에서 다룬다. 안전을 위해 offset 큰 순으로
    적용해 인덱스 안정성을 확보한다.
    """
    text = before
    for it in sorted(
        applied,
        key=lambda x: int(x.get("rangeStart", 0)),
        reverse=True,
    ):
        s = int(it.get("rangeStart", 0))
        e = int(it.get("rangeEnd", 0))
        after = it.get("afterText", "") or ""
        text = text[:s] + after + text[e:]
    return text


def _match_output_paragraph(
    out_doc: Any, paragraph_id: str, container_scope: dict | None,
) -> Any:
    """output RO-VIEW 에서 편집 대상 paragraph 를 재매칭.

    matching 우선순위 — text-only fallback 은 금지 (READBACK_PARSER-01).
      1. paragraphId 동일.
      2. paragraphId 가 어긋난 경우 containerScope 4 키 (kind/tableIndex/
         rowIndex/colIndex/paragraphIndex) 완전 일치 — cell scope 한정.
    block scope 또는 둘 다 실패 시 None.
    """
    for p in out_doc.paragraphs:
        if p.paragraphId == paragraph_id:
            return p
    if not container_scope or container_scope.get("kind") != "cell":
        return None
    keys = ("kind", "tableIndex", "rowIndex", "colIndex",
            "paragraphIndex")
    target = {k: container_scope.get(k) for k in keys}
    for p in out_doc.paragraphs:
        ps = p.containerScope or {}
        if all(ps.get(k) == target[k] for k in keys):
            return p
    return None


def _readback_verify_paragraph(
    *,
    output_path: Path,
    paragraph_id: str,
    container_scope: dict | None,
    applied_items: list[dict],
    text_before: str,
    scenario: str,
    source_char_pr_set: set | None = None,
) -> dict[str, Any]:
    """output HWPX 를 import_hwpx_as_ro_view 로 재측량 → V1/V7 결과.

    - V1_RANGE_POSITION_OK: applied[].rangeStart 위치에 afterText 가 정확
      매칭. DELETE 는 빈 afterText → length 0 슬라이스도 PASS 판정.
    - V7_READBACK_MATCH: output paragraph.text 가 expectedAfter 와 동일.

    cross-match 차단: paragraphId 또는 containerScope 4 키 매칭만 허용
    (동일 텍스트가 다른 paragraph 에 있어도 cross-match 금지).
    """
    out_meta: dict[str, Any] = {
        "V1_RANGE_POSITION_OK": READBACK_SKIP,
        "V4_CHARPR_PRESERVED": READBACK_SKIP,
        "V7_READBACK_MATCH": READBACK_SKIP,
        "matchedParagraphId": None,
        "matchedBy": None,
        "outputParagraphText": None,
        "expectedAfterText": None,
        "outputParPrIDRef": None,
        "outputRunCharPrIDRefs": None,
        "appliedCharPrSet": None,
        "outputCharPrSet": None,
        "notes": [],
    }
    if scenario not in _READBACK_SCENARIOS:
        out_meta["V1_RANGE_POSITION_OK"] = READBACK_DEFERRED
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_DEFERRED
        out_meta["V7_READBACK_MATCH"] = READBACK_DEFERRED
        out_meta["notes"].append(
            f"scenario {scenario} outside readback scope")
        return out_meta
    if not applied_items:
        # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 정책 §5:
        # applied=∅ 인 시나리오 (TYPE_TEXT 의 expectedBefore reject 등)
        # 에서는 V4 도 DEFERRED 로 명시한다.
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_DEFERRED
        out_meta["notes"].append("applied=∅")
        return out_meta
    if not output_path.is_file():
        out_meta["V1_RANGE_POSITION_OK"] = READBACK_FAIL
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_FAIL
        out_meta["V7_READBACK_MATCH"] = READBACK_FAIL
        out_meta["notes"].append("output HWPX not found")
        return out_meta

    try:
        out_doc = import_hwpx_as_ro_view(output_path)
    except Exception as e:  # noqa: BLE001
        out_meta["V1_RANGE_POSITION_OK"] = READBACK_FAIL
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_FAIL
        out_meta["V7_READBACK_MATCH"] = READBACK_FAIL
        out_meta["notes"].append(f"readback import failed: {e}")
        return out_meta

    out_p = _match_output_paragraph(
        out_doc, paragraph_id, container_scope)
    if out_p is None:
        out_meta["V1_RANGE_POSITION_OK"] = READBACK_FAIL
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_FAIL
        out_meta["V7_READBACK_MATCH"] = READBACK_FAIL
        out_meta["notes"].append(
            "output paragraph not located by paragraphId/containerScope")
        return out_meta

    out_meta["matchedParagraphId"] = out_p.paragraphId
    out_meta["matchedBy"] = (
        "paragraphId" if out_p.paragraphId == paragraph_id
        else "containerScope")
    out_meta["outputParagraphText"] = out_p.text
    out_meta["outputParPrIDRef"] = out_p.parPrIDRef
    out_meta["outputRunCharPrIDRefs"] = [
        r.charPrIDRef for r in out_p.runs]

    expected_after = _expected_after_paragraph_text(
        text_before, applied_items)
    out_meta["expectedAfterText"] = expected_after

    # V1 — applied[].afterText 가 정확한 offset 에 위치
    v1_ok = True
    for it in applied_items:
        start = int(it.get("rangeStart", 0))
        after = it.get("afterText", "") or ""
        end = start + len(after)
        if out_p.text[start:end] != after:
            v1_ok = False
            out_meta["notes"].append(
                f"V1 mismatch at offset {start}: "
                f"expected {after!r}, "
                f"got {out_p.text[start:end]!r}")
            break
    out_meta["V1_RANGE_POSITION_OK"] = (
        READBACK_PASS if v1_ok else READBACK_FAIL)

    # V7 — paragraph 전체 텍스트 일치
    if out_p.text == expected_after:
        out_meta["V7_READBACK_MATCH"] = READBACK_PASS
    else:
        out_meta["V7_READBACK_MATCH"] = READBACK_FAIL
        out_meta["notes"].append(
            f"V7 mismatch: expected {expected_after!r}, "
            f"got {out_p.text!r}")

    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 — V4 cross-check.
    # applied[].applyCharPrIDRef 가 모두 원본 char_pr_set 의 부분집합이고,
    # output run 의 charPrIDRef 도 원본 집합 밖으로 나가지 않아야 한다.
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: APPLY_FORMAT
    # 명령은 paragraph 의 원본 charPr set 에 없던 (header 에는 있는) id
    # 로의 교체를 허용한다 — 해당 명령의 targetCharPrIDRef 는 V4 source
    # 집합에 ad hoc 으로 포함시켜 신규 charPr 도입(=header 미존재) 만
    # 검사하도록 한다.
    src_set = set(source_char_pr_set) if source_char_pr_set else set()
    for it in applied_items:
        if it.get("commandType") == "APPLY_FORMAT":
            tgt = it.get("targetCharPrIDRef") or it.get("applyCharPrIDRef")
            if tgt is not None:
                src_set.add(tgt)
    applied_set = {it.get("applyCharPrIDRef") for it in applied_items}
    out_set = {r.charPrIDRef for r in out_p.runs}
    out_meta["appliedCharPrSet"] = sorted(
        str(x) for x in applied_set)
    out_meta["outputCharPrSet"] = sorted(
        str(x) for x in out_set)
    new_from_apply = applied_set - src_set
    new_from_out = out_set - src_set
    if not src_set:
        # source 집합이 비어있으면 신호 부족 — DEFERRED 처리
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_DEFERRED
        out_meta["notes"].append(
            "source_char_pr_set empty — V4 deferred")
    elif new_from_apply or new_from_out:
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_FAIL
        out_meta["notes"].append(
            f"V4 charPr expanded: applied_new="
            f"{sorted(str(x) for x in new_from_apply)} "
            f"output_new="
            f"{sorted(str(x) for x in new_from_out)}")
    else:
        out_meta["V4_CHARPR_PRESERVED"] = READBACK_PASS
    return out_meta


def _align_verify7_with_readback(result: dict[str, Any]) -> None:
    """E2E 결과에서 verify7 summary를 actual readback 결과와 정렬한다.

    paragraph_save_verify7 는 하위 legacy gate라서 V1/V7 에 대해 아직
    readback unsupported FAIL 을 유지할 수 있다. run_para_edit_e2e 는
    실제 output reread 결과를 별도로 확보하므로, E2E summary 에서는 그
    truth source 를 우선 반영한다.
    """
    verify7 = result.get("verify7")
    readback = result.get("readback")
    if not isinstance(verify7, dict) or not isinstance(readback, dict):
        return

    results = verify7.get("results")
    findings = verify7.get("findings")
    if not isinstance(results, dict):
        return
    if not isinstance(findings, list):
        findings = []
        verify7["findings"] = findings

    overrides = {
        "V1_RANGE_POSITION_OK": readback.get("V1_RANGE_POSITION_OK"),
        "V4_CHARPR_PRESERVED": readback.get("V4_CHARPR_PRESERVED"),
        "V7_READBACK_MATCH": readback.get("V7_READBACK_MATCH"),
    }
    aligned_keys: list[str] = []
    for gate, value in overrides.items():
        if isinstance(value, str) and value in {
            READBACK_PASS, READBACK_FAIL, READBACK_DEFERRED, READBACK_SKIP,
        }:
            results[gate] = value
            aligned_keys.append(gate)

    if "V1_RANGE_POSITION_OK" in aligned_keys:
        findings = [
            f for f in findings
            if not (
                isinstance(f, dict)
                and f.get("code") == "V1_READBACK_UNSUPPORTED"
            )
        ]
        verify7["findings"] = findings

    if aligned_keys:
        notes = result.get("notes")
        if not isinstance(notes, list):
            notes = []
            result["notes"] = notes
        notes.append(
            "verify7 aligned to readback for: " + ", ".join(aligned_keys)
        )

    verdict = "PASS" if all(v == "PASS" for v in results.values()) else "FAIL"
    verify7["verdict"] = verdict


def _ro_paragraph_to_model(ro_p: Any) -> Paragraph:
    """RO-VIEW WebOfficeParagraph → para_edit_model.Paragraph.

    runs / charPrIDRef / parPrIDRef 를 그대로 보존한다.
    신규 정규화·검증·매핑 로직은 일절 추가하지 않는다 (§11-6).
    """
    runs = [
        ParaTextRun(runId=r.runId, text=r.text,
                    charPrIDRef=r.charPrIDRef)
        for r in ro_p.runs
    ]
    return Paragraph(paragraphId=ro_p.paragraphId,
                     parPrIDRef=ro_p.parPrIDRef, runs=runs)


def _build_target(ro_p: Any, source_sha: str) -> ParagraphTarget:
    """RO-VIEW paragraph 의 containerScope → ParagraphTarget.

    cell scope 면 cellCoord 와 containerId 를 발급하고,
    block scope 면 paragraphId 를 containerId 로 사용한다.
    """
    scope = ro_p.containerScope or {}
    kind = scope.get("kind", "block")
    if kind == "cell":
        cell_coord = {
            "table": scope["tableIndex"],
            "row": scope["rowIndex"],
            "col": scope["colIndex"],
        }
        container_id = (
            f"cell_t{scope['tableIndex']}"
            f"_r{scope['rowIndex']}"
            f"_c{scope['colIndex']}"
        )
    else:
        cell_coord = None
        container_id = ro_p.paragraphId
    return ParagraphTarget(
        paragraphId=ro_p.paragraphId,
        containerKind=kind,
        containerId=container_id,
        sourceSha256=source_sha,
        cellCoord=cell_coord,
        containerScope=dict(scope) if scope else None,
    )


def run_para_edit_e2e(
    *,
    source_path: Path,
    output_path: Path,
    scenario: str,
    paragraph_id: str,
    range_anchor: int = 0,
    range_focus: int | None = None,
    insert_text: str = "",
    replace_after: str = "",
    target_char_pr_id: str | None = None,
    allow_writer: bool = True,
) -> dict[str, Any]:
    """ro_view → command → plan → writer → verify7 → readback E2E.

    Parameters
    ----------
    scenario:
        SCENARIO_TYPE / SCENARIO_REPLACE / SCENARIO_DELETE 중 하나.
    paragraph_id:
        RO-VIEW import 결과의 paragraphId.
    range_anchor / range_focus:
        REPLACE / DELETE 의 paragraph offset 범위.
        TYPE_TEXT 는 range_anchor 를 caret_offset 으로 사용.
    insert_text:
        SCENARIO_TYPE 에서 삽입할 텍스트.
    replace_after:
        SCENARIO_REPLACE 에서 치환 후 텍스트.
    allow_writer:
        save_paragraph_edits 의 writer 본 실행 활성화 여부 (기본 True).

    Returns
    -------
    save_paragraph_edits 의 반환 dict 에 e2eScenario / targetParagraph
    필드를 덧붙인 dict.
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    doc = import_hwpx_as_ro_view(source_path)
    ro_p = next(
        (p for p in doc.paragraphs
         if p.paragraphId == paragraph_id),
        None,
    )
    if ro_p is None:
        return {
            "verdict": VERDICT_REJECTED,
            "rejected": [{
                "reason": "TARGET_PARAGRAPH_NOT_FOUND",
                "paragraphId": paragraph_id,
            }],
            "e2eScenario": scenario,
            "sourceDocumentHash": doc.sourceDocumentHash,
        }

    model_p = _ro_paragraph_to_model(ro_p)
    target = _build_target(ro_p, doc.sourceDocumentHash)
    container_scope = target.containerScope

    if scenario == SCENARIO_TYPE:
        cmd = make_type_text_command(
            target=target, paragraph=model_p,
            caret_offset=range_anchor,
            insert_text=insert_text,
            source_document_hash=doc.sourceDocumentHash,
            container_scope=container_scope)
    elif scenario == SCENARIO_REPLACE:
        focus = (range_focus if range_focus is not None
                 else range_anchor)
        cmd = make_replace_text_range_command(
            target=target, paragraph=model_p,
            range_anchor=range_anchor, range_focus=focus,
            after_text=replace_after,
            source_document_hash=doc.sourceDocumentHash,
            container_scope=container_scope)
    elif scenario == SCENARIO_DELETE:
        focus = (range_focus if range_focus is not None
                 else range_anchor)
        cmd = make_delete_text_range_command(
            target=target, paragraph=model_p,
            range_anchor=range_anchor, range_focus=focus,
            source_document_hash=doc.sourceDocumentHash,
            container_scope=container_scope)
    elif scenario == SCENARIO_APPLY_FORMAT:
        focus = (range_focus if range_focus is not None
                 else range_anchor)
        cmd = make_apply_format_command(
            target=target, paragraph=model_p,
            range_anchor=range_anchor, range_focus=focus,
            target_char_pr_id=target_char_pr_id or "",
            source_document_hash=doc.sourceDocumentHash,
            container_scope=container_scope)
    else:
        return {
            "verdict": VERDICT_REJECTED,
            "rejected": [{
                "reason": "UNSUPPORTED_E2E_SCENARIO",
                "scenario": scenario,
            }],
            "e2eScenario": scenario,
            "sourceDocumentHash": doc.sourceDocumentHash,
        }

    if cmd is None:
        return {
            "verdict": VERDICT_NOOP,
            "rejected": [],
            "accepted": [],
            "e2eScenario": scenario,
            "sourceDocumentHash": doc.sourceDocumentHash,
            "notes": ["command factory NOOP"],
        }

    paragraphs_by_id = {model_p.paragraphId: model_p}
    result = save_paragraph_edits(
        source_path=source_path,
        output_path=output_path,
        command_log=[cmd],
        paragraphs_by_id=paragraphs_by_id,
        source_document_hash=doc.sourceDocumentHash,
        allow_writer=allow_writer)
    result["e2eScenario"] = scenario
    result["targetParagraph"] = {
        "paragraphId": ro_p.paragraphId,
        "containerScope": container_scope,
        "runCount": len(ro_p.runs),
        "parPrIDRef": ro_p.parPrIDRef,
        "charPrIDRef": (ro_p.runs[0].charPrIDRef
                        if ro_p.runs else None),
        "textBefore": ro_p.text,
    }

    # WEB-OFFICE-PARA-READBACK-PARSER-01 — V1/V7 readback gate.
    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 — V4 cross-check.
    applied = result.get("appliedPlanEdits") or []
    source_char_pr_set = {r.charPrIDRef for r in ro_p.runs}
    result["readback"] = _readback_verify_paragraph(
        output_path=output_path,
        paragraph_id=ro_p.paragraphId,
        container_scope=container_scope,
        applied_items=applied,
        text_before=ro_p.text,
        scenario=scenario,
        source_char_pr_set=source_char_pr_set,
    )
    _align_verify7_with_readback(result)
    return result
