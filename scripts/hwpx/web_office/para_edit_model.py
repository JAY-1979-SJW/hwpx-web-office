"""EditCommand v2 모델 — Phase 3 PARA-EDIT MODEL.

문단 run 단위 편집 명령의 데이터 모델 + 정합성 검증.
writer 호출, output HWPX 생성, 원본 HWPX 접근은 일절 없다.
"""
from __future__ import annotations
import datetime as _dt
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any


# ── commandType enum ────────────────────────────────────────────
CT_SET_CELL_TEXT = "SET_CELL_TEXT"          # MVP-A 그대로 유지
CT_TYPE_TEXT = "TYPE_TEXT"
CT_REPLACE_TEXT_RANGE = "REPLACE_TEXT_RANGE"
CT_DELETE_TEXT_RANGE = "DELETE_TEXT_RANGE"
CT_SET_PARAGRAPH_TEXT_SAFE = "SET_PARAGRAPH_TEXT_SAFE"
CT_SPLIT_TEXT_RUN = "SPLIT_TEXT_RUN"
CT_MERGE_TEXT_RUNS = "MERGE_TEXT_RUNS"
# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
# 같은 문서 header.xml 에 이미 존재하는 charPrIDRef 로만 교체.
# 신규 charPr 생성 금지.
CT_APPLY_FORMAT = "APPLY_FORMAT"
# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01:
# Enter 키 → caret 위치 body paragraph 분할. inverse 는 PARA_DELETE.
CT_PARA_INSERT = "PARA_INSERT"
# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01: 사용자 command (Backspace at start).
CT_PARA_DELETE = "PARA_DELETE"

PARA_COMMAND_TYPES = {
    CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
    CT_SET_PARAGRAPH_TEXT_SAFE, CT_SPLIT_TEXT_RUN,
    CT_MERGE_TEXT_RUNS, CT_APPLY_FORMAT,
    CT_PARA_INSERT,
    CT_PARA_DELETE,
}

REASON_SECTION_BOUNDARY_NOT_SUPPORTED = "SECTION_BOUNDARY_NOT_SUPPORTED"
REASON_LIST_ITEM_NOT_SUPPORTED = "LIST_ITEM_NOT_SUPPORTED"
REASON_SOFT_BREAK_NOT_SUPPORTED = "SOFT_BREAK_NOT_SUPPORTED"
REASON_MULTI_PARA_RANGE_NOT_SUPPORTED = "MULTI_PARA_RANGE_NOT_SUPPORTED"
# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01
REASON_NO_PREV_PARAGRAPH = "NO_PREV_PARAGRAPH"
REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED = (
    "PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED")
# WEB-OFFICE-PARA-EDIT-STRUCTURE-SCOPE-BOUNDARY-REJECT-01
REASON_HEADER_SCOPE_NOT_SUPPORTED   = "HEADER_SCOPE_NOT_SUPPORTED"
REASON_FOOTER_SCOPE_NOT_SUPPORTED   = "FOOTER_SCOPE_NOT_SUPPORTED"
REASON_FOOTNOTE_SCOPE_NOT_SUPPORTED = "FOOTNOTE_SCOPE_NOT_SUPPORTED"
REASON_ENDNOTE_SCOPE_NOT_SUPPORTED  = "ENDNOTE_SCOPE_NOT_SUPPORTED"
REASON_CAPTION_SCOPE_NOT_SUPPORTED  = "CAPTION_SCOPE_NOT_SUPPORTED"
REASON_BODY_SCOPE_ONLY_SUPPORTED    = "BODY_SCOPE_ONLY_SUPPORTED"

# charPr policy for REPLACE_TEXT_RANGE multi-run cross
POLICY_ANCHOR_CHARPR = "ANCHOR_CHARPR"     # 기본
POLICY_FOCUS_CHARPR = "FOCUS_CHARPR"
POLICY_REQUIRES_REVIEW = "REQUIRES_REVIEW"

STATUS_PENDING = "PENDING"
STATUS_VALIDATED = "VALIDATED"
STATUS_REJECTED = "REJECTED"

REASON_MERGE_CHARPR_MISMATCH = "MERGE_CHARPR_MISMATCH"
REASON_EXPECTED_BEFORE_MISMATCH = "EXPECTED_BEFORE_MISMATCH_PARAGRAPH"
REASON_STALE_SESSION = "STALE_SESSION"
REASON_UNSAFE_MULTI_STYLE_PARA = "UNSAFE_MULTI_STYLE_PARA"
REASON_REQUIRES_REVIEW = "REQUIRES_REVIEW"
# WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01
REASON_CHARPR_MISSING_ON_RUN = "CHARPR_MISSING_ON_RUN"
REASON_CHARPR_SPLIT_SOURCE_MISSING = "CHARPR_SPLIT_SOURCE_MISSING"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


# ── 데이터 모델 ─────────────────────────────────────────────────

@dataclass
class ParaTextRun:
    runId: str
    text: str
    charPrIDRef: str | None = None


@dataclass
class Paragraph:
    paragraphId: str
    parPrIDRef: str | None
    runs: list[ParaTextRun] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    def char_pr_set(self) -> set[str | None]:
        return {r.charPrIDRef for r in self.runs}


@dataclass
class ParagraphTarget:
    paragraphId: str
    containerKind: str           # "cell" | "block"
    containerId: str
    sourceSha256: str
    cellCoord: dict | None = None  # {table,row,col} when containerKind=="cell"
    containerScope: dict | None = None  # RO-VIEW containerScope dict (kind/tableIndex/...)


@dataclass
class CaretPoint:
    runId: str
    offset: int


@dataclass
class TextRange:
    paragraphId: str
    anchor: CaretPoint
    focus: CaretPoint
    expectedBefore: str = ""


@dataclass
class EditCommandV2:
    commandId: str
    commandType: str
    target: dict           # ParagraphTarget.to_dict() or {"cellId":...}
    payload: dict          # 명령별 페이로드
    forward: dict          # in-memory paragraph 변형 명세
    inverse: dict          # 역연산 명세
    expectedBefore: str
    createdAt: str
    sourceDocumentHash: str
    commandGroupId: str
    status: str = STATUS_PENDING

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── 정규화 헬퍼 ──────────────────────────────────────────────────

def _next_run_id(paragraph: Paragraph) -> str:
    """paragraphId 기반 stable run id 신규 발급."""
    base = paragraph.paragraphId
    n = 0
    existing = {r.runId for r in paragraph.runs}
    while True:
        candidate = f"{base}_run{n}"
        if candidate not in existing:
            return candidate
        n += 1


def validate_run_charpr_integrity(paragraph: Paragraph) -> dict:
    """모든 run 의 charPrIDRef 가 non-null/non-empty 인지 검증.

    WEB-OFFICE-P3-RUN-SPLIT-MERGE-CHARPR-GUARD-01.
    """
    missing = [r.runId for r in paragraph.runs
               if not r.charPrIDRef]
    return {"valid": len(missing) == 0, "missingRunIds": missing}


def split_run(paragraph: Paragraph, run_id: str,
                        offset: int) -> tuple[Paragraph, dict | None]:
    """run_id 의 offset 지점에서 split.

    offset==0 또는 offset==len(text) 이면 NOOP — None 반환.
    좌·우 모두 원본 charPrIDRef 상속.
    charPrIDRef 가 null/empty 인 run 은 split 금지 (CHARPR_SPLIT_SOURCE_MISSING).
    """
    runs = paragraph.runs
    idx = next((i for i, r in enumerate(runs) if r.runId == run_id), -1)
    if idx < 0:
        raise KeyError(f"run not found: {run_id}")
    target = runs[idx]
    if offset <= 0 or offset >= len(target.text):
        return paragraph, None
    if not target.charPrIDRef:
        raise ValueError(REASON_CHARPR_SPLIT_SOURCE_MISSING)
    left_text = target.text[:offset]
    right_text = target.text[offset:]
    left = ParaTextRun(runId=target.runId, text=left_text,
                                          charPrIDRef=target.charPrIDRef)
    new_right_id = _next_run_id(paragraph)
    right = ParaTextRun(runId=new_right_id, text=right_text,
                                            charPrIDRef=target.charPrIDRef)
    new_runs = runs[:idx] + [left, right] + runs[idx + 1:]
    new_para = Paragraph(paragraphId=paragraph.paragraphId,
                                            parPrIDRef=paragraph.parPrIDRef,
                                            runs=new_runs)
    return new_para, {"leftRunId": left.runId,
                                "rightRunId": right.runId, "offset": offset}


def merge_runs(paragraph: Paragraph, left_run_id: str,
                          right_run_id: str) -> Paragraph:
    """인접 + 동일 charPrIDRef 인 두 run 을 merge.

    위반 시 ValueError(reason=MERGE_CHARPR_MISMATCH).
    """
    runs = paragraph.runs
    li = next((i for i, r in enumerate(runs)
                          if r.runId == left_run_id), -1)
    ri = next((i for i, r in enumerate(runs)
                          if r.runId == right_run_id), -1)
    if li < 0 or ri < 0:
        raise KeyError("run not found in merge_runs")
    if ri != li + 1:
        raise ValueError("runs not adjacent")
    if runs[li].charPrIDRef != runs[ri].charPrIDRef:
        raise ValueError(REASON_MERGE_CHARPR_MISMATCH)
    merged = ParaTextRun(runId=runs[li].runId,
                                            text=runs[li].text + runs[ri].text,
                                            charPrIDRef=runs[li].charPrIDRef)
    new_runs = runs[:li] + [merged] + runs[ri + 1:]
    return Paragraph(paragraphId=paragraph.paragraphId,
                            parPrIDRef=paragraph.parPrIDRef, runs=new_runs)


def normalize_paragraph(paragraph: Paragraph) -> Paragraph:
    """빈 run 제거 + 인접 동일 charPr run merge.

    paragraph 가 완전히 비면 빈 run 1개 유지 (W-known).
    """
    runs = [r for r in paragraph.runs if r.text != ""]
    if not runs:
        # 빈 paragraph — 첫 run 의 charPr 상속, 텍스트 ""
        existing_pr = (paragraph.runs[0].charPrIDRef
                                if paragraph.runs else None)
        return Paragraph(paragraphId=paragraph.paragraphId,
                                    parPrIDRef=paragraph.parPrIDRef,
                                    runs=[ParaTextRun(
                                        runId=paragraph.runs[0].runId
                                        if paragraph.runs
                                        else f"{paragraph.paragraphId}_run0",
                                        text="", charPrIDRef=existing_pr)])
    merged: list[ParaTextRun] = [runs[0]]
    for r in runs[1:]:
        prev = merged[-1]
        if prev.charPrIDRef == r.charPrIDRef:
            merged[-1] = ParaTextRun(runId=prev.runId,
                                                          text=prev.text + r.text,
                                                          charPrIDRef=prev.charPrIDRef)
        else:
            merged.append(r)
    return Paragraph(paragraphId=paragraph.paragraphId,
                            parPrIDRef=paragraph.parPrIDRef, runs=merged)


# ── 위치 변환: paragraph offset ↔ (runId, offset) ───────────────

def locate_offset(paragraph: Paragraph,
                              caret_offset: int) -> CaretPoint:
    """paragraph 시작부터의 character offset → (runId, offset_within_run)."""
    pos = 0
    for r in paragraph.runs:
        end = pos + len(r.text)
        if caret_offset <= end:
            return CaretPoint(runId=r.runId, offset=caret_offset - pos)
        pos = end
    # 끝점
    last = paragraph.runs[-1]
    return CaretPoint(runId=last.runId, offset=len(last.text))


def text_in_range(paragraph: Paragraph, anchor_off: int,
                                focus_off: int) -> str:
    a, b = sorted((anchor_off, focus_off))
    return paragraph.text[a:b]


# ── command factories ──────────────────────────────────────────

def make_type_text_command(
    *, target: ParagraphTarget, paragraph: Paragraph,
    caret_offset: int, insert_text: str,
    source_document_hash: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2 | None:
    """caret 위치에 insert_text 삽입. 빈 문자열이면 None."""
    if insert_text == "":
        return None
    cp = locate_offset(paragraph, caret_offset)
    # caret 좌측 run 의 charPrIDRef 상속 — caret 이 run 시작이면 그 run
    inherit_pr = next((r.charPrIDRef for r in paragraph.runs
                                          if r.runId == cp.runId), None)
    # WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 — caret 삽입은 빈 range slice
    # 기준 expectedBefore="" 로 writer adapter 의 slice 계약과 정렬한다.
    forward = {
        "kind": "TYPE_TEXT",
        "paragraphId": paragraph.paragraphId,
        "caretOffset": caret_offset,
        "rangeAnchor": caret_offset,
        "rangeFocus": caret_offset,
        "rangeStart": caret_offset,
        "rangeEnd": caret_offset,
        "insertText": insert_text,
        "afterText": insert_text,
        "inheritCharPrIDRef": inherit_pr,
    }
    inverse = {
        "kind": "DELETE_TEXT_RANGE",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": caret_offset,
        "rangeFocus": caret_offset + len(insert_text),
        "deletedText": insert_text,
        "deletedCharPrIDRef": inherit_pr,
    }
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_TYPE_TEXT,
        target=target_dict,
        payload={"caretOffset": caret_offset, "insertText": insert_text},
        forward=forward, inverse=inverse,
        expectedBefore="",
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


def make_replace_text_range_command(
    *, target: ParagraphTarget, paragraph: Paragraph,
    range_anchor: int, range_focus: int, after_text: str,
    source_document_hash: str,
    policy: str = POLICY_ANCHOR_CHARPR,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2:
    a, b = sorted((range_anchor, range_focus))
    before_text = paragraph.text[a:b]
    if before_text == after_text:
        raise ValueError("before == after — no command should be created")
    anchor_cp = locate_offset(paragraph, a)
    focus_cp = locate_offset(paragraph, b)
    anchor_pr = next((r.charPrIDRef for r in paragraph.runs
                                          if r.runId == anchor_cp.runId), None)
    focus_pr = next((r.charPrIDRef for r in paragraph.runs
                                          if r.runId == focus_cp.runId), None)
    multi = anchor_pr != focus_pr
    if multi and policy == POLICY_REQUIRES_REVIEW:
        raise ValueError(REASON_REQUIRES_REVIEW)
    if policy == POLICY_FOCUS_CHARPR:
        apply_pr = focus_pr
    else:
        apply_pr = anchor_pr
    forward = {
        "kind": "REPLACE_TEXT_RANGE",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": a, "rangeFocus": b,
        "afterText": after_text,
        "applyCharPrIDRef": apply_pr,
        "policy": policy,
    }
    inverse = {
        "kind": "REPLACE_TEXT_RANGE",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": a, "rangeFocus": a + len(after_text),
        "afterText": before_text,
        "applyCharPrIDRef": anchor_pr,
        "policy": policy,
    }
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_REPLACE_TEXT_RANGE,
        target=target_dict,
        payload={"rangeAnchor": a, "rangeFocus": b,
                          "afterText": after_text, "policy": policy},
        forward=forward, inverse=inverse,
        expectedBefore=before_text,
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


def make_delete_text_range_command(
    *, target: ParagraphTarget, paragraph: Paragraph,
    range_anchor: int, range_focus: int,
    source_document_hash: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2:
    a, b = sorted((range_anchor, range_focus))
    if a == b:
        raise ValueError("empty range — no command should be created")
    deleted_text = paragraph.text[a:b]
    anchor_cp = locate_offset(paragraph, a)
    anchor_pr = next((r.charPrIDRef for r in paragraph.runs
                                          if r.runId == anchor_cp.runId), None)
    forward = {
        "kind": "DELETE_TEXT_RANGE",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": a, "rangeFocus": b,
        "deletedText": deleted_text,
        "deletedCharPrIDRef": anchor_pr,
    }
    # inverse: 같은 위치에 deleted_text 를 REPLACE 로 복원
    inverse = {
        "kind": "REPLACE_TEXT_RANGE",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": a, "rangeFocus": a,
        "afterText": deleted_text,
        "applyCharPrIDRef": anchor_pr,
        "policy": POLICY_ANCHOR_CHARPR,
    }
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_DELETE_TEXT_RANGE,
        target=target_dict,
        payload={"rangeAnchor": a, "rangeFocus": b},
        forward=forward, inverse=inverse,
        expectedBefore=deleted_text,
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


def make_apply_format_command(
    *, target: ParagraphTarget, paragraph: Paragraph,
    range_anchor: int, range_focus: int,
    target_char_pr_id: str,
    source_document_hash: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2 | None:
    """WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01.

    paragraph offset [range_anchor, range_focus) 의 run charPrIDRef 를
    target_char_pr_id 로 교체. 신규 charPr 생성하지 않음 (writer 측에서
    header 존재 검증).
    """
    a, b = sorted((range_anchor, range_focus))
    if a == b:
        return None  # NOOP
    before_text = paragraph.text[a:b]
    # 영향 받는 run 들의 charPr 분포 — inverse 복원 자료
    before_segments: list[dict[str, Any]] = []
    pos = 0
    for r in paragraph.runs:
        rs = pos; re_ = pos + len(r.text)
        if rs >= b:
            break
        if re_ <= a or rs == re_:
            pos = re_
            continue
        seg_start = max(rs, a)
        seg_end = min(re_, b)
        before_segments.append({
            "segmentStart": seg_start,
            "segmentEnd": seg_end,
            "charPrIDRef": r.charPrIDRef,
        })
        pos = re_
    forward = {
        "kind": "APPLY_FORMAT",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": a, "rangeFocus": b,
        "rangeStart": a, "rangeEnd": b,
        "targetCharPrIDRef": str(target_char_pr_id),
        "beforeSegments": before_segments,
    }
    inverse = {
        "kind": "APPLY_FORMAT_INVERSE",
        "paragraphId": paragraph.paragraphId,
        "rangeAnchor": a, "rangeFocus": b,
        "restoreSegments": before_segments,
    }
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_APPLY_FORMAT,
        target=target_dict,
        payload={"rangeAnchor": a, "rangeFocus": b,
                          "targetCharPrIDRef": str(target_char_pr_id)},
        forward=forward, inverse=inverse,
        expectedBefore=before_text,
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


def make_split_text_run_command(
    *, target: ParagraphTarget, paragraph_id: str,
    run_id: str, offset: int,
    source_document_hash: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2:
    forward = {"kind": "SPLIT_TEXT_RUN",
                      "paragraphId": paragraph_id,
                      "runId": run_id, "offset": offset}
    inverse = {"kind": "MERGE_TEXT_RUNS",
                      "paragraphId": paragraph_id,
                      "leftRunId": run_id, "rightRunIdHint": "next"}
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_SPLIT_TEXT_RUN,
        target=target_dict,
        payload={"runId": run_id, "offset": offset},
        forward=forward, inverse=inverse,
        expectedBefore="",
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


def make_merge_text_runs_command(
    *, target: ParagraphTarget, paragraph_id: str,
    left_run_id: str, right_run_id: str,
    source_document_hash: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2:
    forward = {"kind": "MERGE_TEXT_RUNS",
                      "paragraphId": paragraph_id,
                      "leftRunId": left_run_id, "rightRunId": right_run_id}
    inverse = {"kind": "SPLIT_TEXT_RUN",
                      "paragraphId": paragraph_id,
                      "runId": left_run_id, "offsetHint": "boundary"}
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_MERGE_TEXT_RUNS,
        target=target_dict,
        payload={"leftRunId": left_run_id,
                          "rightRunId": right_run_id},
        forward=forward, inverse=inverse,
        expectedBefore="",
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


# ── in-memory 적용 (writer 호출 없음) ───────────────────────────

def apply_command_to_paragraph(paragraph: Paragraph,
                                                              cmd: EditCommandV2) -> Paragraph:
    """forward 의 의미대로 paragraph 사본을 변형. writer 미접촉."""
    kind = cmd.forward.get("kind")
    if kind == "TYPE_TEXT":
        return _apply_type_text(paragraph, cmd.forward)
    if kind == "REPLACE_TEXT_RANGE":
        return _apply_replace_range(paragraph, cmd.forward)
    if kind == "DELETE_TEXT_RANGE":
        return _apply_delete_range(paragraph, cmd.forward)
    if kind == "SPLIT_TEXT_RUN":
        p, _ = split_run(paragraph, cmd.forward["runId"],
                                      cmd.forward["offset"])
        return p
    if kind == "MERGE_TEXT_RUNS":
        return merge_runs(paragraph, cmd.forward["leftRunId"],
                                          cmd.forward["rightRunId"])
    if kind == "APPLY_FORMAT":
        return _apply_format(paragraph, cmd.forward)
    raise ValueError(f"unknown forward kind: {kind}")


def _apply_format(paragraph: Paragraph, fwd: dict) -> Paragraph:
    """in-memory model 측 ApplyFormat 시뮬레이션 — run split 후 charPr
    교체. paragraph.text 무변경.
    """
    a, b = fwd["rangeAnchor"], fwd["rangeFocus"]
    target_pr = str(fwd["targetCharPrIDRef"])
    # range 끝에서 먼저 split → 시작에서 split (REPLACE 패턴 재사용)
    end_cp = locate_offset(paragraph, b)
    p, _ = split_run(paragraph, end_cp.runId, end_cp.offset)
    start_cp = locate_offset(p, a)
    p, _ = split_run(p, start_cp.runId, start_cp.offset)
    new_runs: list[ParaTextRun] = []
    pos = 0
    for r in p.runs:
        rs = pos; re_ = pos + len(r.text)
        if rs >= a and re_ <= b and r.text:
            new_runs.append(ParaTextRun(
                runId=r.runId, text=r.text, charPrIDRef=target_pr))
        else:
            new_runs.append(r)
        pos = re_
    p2 = Paragraph(paragraphId=p.paragraphId,
                              parPrIDRef=p.parPrIDRef, runs=new_runs)
    return p2  # normalize 호출 안 함 — 같은 charPr 인접 run merge 는
                    # writer 책임이 아니라 viewer 정합 정도로 둔다.


def _apply_type_text(paragraph: Paragraph, fwd: dict) -> Paragraph:
    cp = locate_offset(paragraph, fwd["caretOffset"])
    # 해당 run 을 offset 에서 split
    p, _ = split_run(paragraph, cp.runId, cp.offset)
    # split 후 caret 좌측 run 식별 — caretOffset 위치 직전의 run
    insert_pr = fwd.get("inheritCharPrIDRef")
    # caret 좌측 run 의 인덱스
    pos = 0
    insert_at = 0
    for i, r in enumerate(p.runs):
        if pos == fwd["caretOffset"]:
            insert_at = i
            break
        pos += len(r.text)
        insert_at = i + 1
    new_run = ParaTextRun(runId=_next_run_id(p),
                                              text=fwd["insertText"],
                                              charPrIDRef=insert_pr)
    new_runs = p.runs[:insert_at] + [new_run] + p.runs[insert_at:]
    p2 = Paragraph(paragraphId=p.paragraphId,
                              parPrIDRef=p.parPrIDRef, runs=new_runs)
    return normalize_paragraph(p2)


def _apply_replace_range(paragraph: Paragraph, fwd: dict) -> Paragraph:
    a, b = fwd["rangeAnchor"], fwd["rangeFocus"]
    after = fwd["afterText"]
    apply_pr = fwd["applyCharPrIDRef"]
    # 범위 끝에서 split, 시작에서 split
    end_cp = locate_offset(paragraph, b)
    p, _ = split_run(paragraph, end_cp.runId, end_cp.offset)
    start_cp = locate_offset(p, a)
    p, _ = split_run(p, start_cp.runId, start_cp.offset)
    # 시작 offset 직후 ~ 끝 offset 직전 run 들 제거
    # 새 paragraph 의 run 들을 텍스트 누적으로 식별
    new_runs: list[ParaTextRun] = []
    pos = 0
    inserted = False

    def _try_insert() -> None:
        nonlocal inserted
        if inserted:
            return
        if after:
            new_runs.append(ParaTextRun(
                runId=_next_run_id(p), text=after,
                charPrIDRef=apply_pr))
        inserted = True

    for r in p.runs:
        run_start = pos
        run_end = pos + len(r.text)
        # empty range 또는 boundary 시점 insert 보장
        if not inserted and run_start >= a:
            _try_insert()
        if run_end <= a or run_start >= b:
            new_runs.append(r)
        else:
            _try_insert()
        pos = run_end
    if not inserted:
        _try_insert()
    p2 = Paragraph(paragraphId=p.paragraphId,
                              parPrIDRef=p.parPrIDRef, runs=new_runs)
    return normalize_paragraph(p2)


def _apply_delete_range(paragraph: Paragraph, fwd: dict) -> Paragraph:
    # DELETE = REPLACE with after=""
    fake = dict(fwd)
    fake["afterText"] = ""
    fake["applyCharPrIDRef"] = fwd.get("deletedCharPrIDRef")
    return _apply_replace_range(paragraph, fake)


# ── 정합성 검증 ─────────────────────────────────────────────────

def validate_expected_before(cmd: EditCommandV2,
                                                          paragraph: Paragraph) -> bool:
    """명령의 expectedBefore 가 paragraph 의 해당 슬라이스와 일치하는지."""
    if cmd.commandType == CT_TYPE_TEXT:
        # WEB-OFFICE-PARA-TYPE-TEXT-CONTRACT-01 — TYPE_TEXT 는 빈 range
        # slice 기준. expectedBefore=="" 이고 caret 이 paragraph 범위 안.
        co = int(cmd.forward.get("caretOffset", 0))
        if cmd.expectedBefore != "":
            return False
        if co < 0 or co > len(paragraph.text):
            return False
        return paragraph.text[co:co] == cmd.expectedBefore
    if cmd.commandType in {CT_REPLACE_TEXT_RANGE,
                                                CT_DELETE_TEXT_RANGE,
                                                CT_APPLY_FORMAT}:
        a = cmd.forward["rangeAnchor"]
        b = cmd.forward["rangeFocus"]
        return paragraph.text[a:b] == cmd.expectedBefore
    return True


def validate_charpr_preserved(before: Paragraph,
                                                              after: Paragraph) -> bool:
    """적용 후 charPr 집합이 원본 ⊆ 관계인지 (신규 0)."""
    new_set = {r.charPrIDRef for r in after.runs} - {None}
    orig_set = {r.charPrIDRef for r in before.runs} - {None}
    return new_set.issubset(orig_set)


def validate_parpr_preserved(before: Paragraph,
                                                              after: Paragraph) -> bool:
    return before.parPrIDRef == after.parPrIDRef


def validate_source_document_hash(cmd: EditCommandV2,
                                                                      current_hash: str) -> bool:
    return cmd.sourceDocumentHash == current_hash


# ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 ──────────────

def make_para_insert_command(
    *, target: ParagraphTarget, paragraph: Paragraph,
    caret_offset: int,
    source_document_hash: str,
    new_paragraph_id: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2:
    """caret 위치에서 paragraph 를 split — 두 paragraph 발급.

    원 paragraph 의 paragraphId 는 유지(앞쪽 paragraph), new_paragraph_id
    는 뒤쪽 paragraph. parPrIDRef 는 원 paragraph 와 동일 상속, 뒤쪽
    paragraph 의 첫 run charPrIDRef 는 caret 위치 활성 charPr (즉
    caret 좌측 run 의 charPrIDRef) 상속.

    inverse 는 CT_PARA_DELETE (뒤쪽 paragraph 를 제거하고 앞쪽으로 합침)
    — 사용자 command 로는 미발급되지만 inverse 페어로만 사용.
    """
    if caret_offset < 0 or caret_offset > len(paragraph.text):
        raise ValueError(
            f"caret_offset {caret_offset} out of range "
            f"[0, {len(paragraph.text)}]")
    before_text = paragraph.text[:caret_offset]
    after_text = paragraph.text[caret_offset:]
    cp = locate_offset(paragraph, caret_offset)
    inherit_pr = next((r.charPrIDRef for r in paragraph.runs
                                          if r.runId == cp.runId), None)
    forward = {
        "kind": "PARA_INSERT",
        "paragraphId": paragraph.paragraphId,
        "caretOffset": caret_offset,
        "newParagraphId": new_paragraph_id,
        "newParPrIDRef": paragraph.parPrIDRef,
        "newCharPrIDRef": inherit_pr,
        "beforeText": before_text,
        "afterText": after_text,
    }
    inverse = {
        "kind": "PARA_DELETE",
        "paragraphId": new_paragraph_id,
        "mergeIntoParagraphId": paragraph.paragraphId,
        "mergedText": after_text,
        "originalCaretOffset": caret_offset,
    }
    target_dict = asdict(target)
    if container_scope is not None:
        target_dict["containerScope"] = container_scope
    forward["containerScope"] = target_dict.get("containerScope")
    inverse["containerScope"] = target_dict.get("containerScope")
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_PARA_INSERT,
        target=target_dict,
        payload={"caretOffset": caret_offset,
                          "newParagraphId": new_paragraph_id},
        forward=forward, inverse=inverse,
        expectedBefore=paragraph.text,
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)


# ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 ──────────────

def make_para_delete_command(
    *, prev_paragraph: Paragraph, current_paragraph: Paragraph,
    source_document_hash: str,
    command_group_id: str | None = None,
    container_scope: dict | None = None,
) -> EditCommandV2:
    """Backspace at caret==0 — current_paragraph 를 prev_paragraph 끝으로 병합.

    forward : PARA_DELETE (current_paragraph 제거, prev_paragraph 로 병합)
    inverse : PARA_INSERT (prev_paragraph 를 merge_offset 위치에서 재분할)
    """
    merge_offset = len(prev_paragraph.text)
    cur_text = current_paragraph.text
    last_run = prev_paragraph.runs[-1] if prev_paragraph.runs else None
    inherit_pr = last_run.charPrIDRef if last_run else None
    scope = container_scope or asdict(
        current_paragraph).get("containerScope")
    forward = {
        "kind": "PARA_DELETE",
        "paragraphId": current_paragraph.paragraphId,
        "prevParagraphId": prev_paragraph.paragraphId,
        "mergedText": cur_text,
        "mergeOffset": merge_offset,
        "containerScope": scope,
    }
    inverse = {
        "kind": "PARA_INSERT",
        "paragraphId": prev_paragraph.paragraphId,
        "caretOffset": merge_offset,
        "newParagraphId": current_paragraph.paragraphId,
        "newParPrIDRef": current_paragraph.parPrIDRef,
        "newCharPrIDRef": inherit_pr,
        "beforeText": prev_paragraph.text,
        "afterText": cur_text,
        "containerScope": scope,
    }
    target_dict = {
        "paragraphId": current_paragraph.paragraphId,
        "containerScope": scope,
    }
    forward["containerScope"] = scope
    inverse["containerScope"] = scope
    return EditCommandV2(
        commandId=_uuid(), commandType=CT_PARA_DELETE,
        target=target_dict,
        payload={"prevParagraphId": prev_paragraph.paragraphId,
                          "mergeOffset": merge_offset},
        forward=forward, inverse=inverse,
        expectedBefore=cur_text,
        createdAt=_now_iso(),
        sourceDocumentHash=source_document_hash,
        commandGroupId=command_group_id or _uuid(),
        status=STATUS_PENDING)
