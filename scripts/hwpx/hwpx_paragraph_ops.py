"""HWPX paragraph/run XML primitives (WRITER-PARA-PLAN-01).

cell 내부 paragraph (<hp:p>) / run (<hp:run>) / text node (<hp:t>) 를
좌표 기반으로 찾아 단일 run text range edit 을 수행한다.

본 모듈은 writer/output 책임을 갖지 않는다. 호출자가 package.write_xml
및 package.write_package 를 담당한다.

§11-6: 신규 도구가 아닌 평면 helper — 기존 hwpx_package 자재를 호출만 한다.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET
from typing import Any

from hwpx_package import local_name


# ── 상태 enum ───────────────────────────────────────────────────
STATUS_OK = "OK"
STATUS_RUN_TEXT_NODE_MISSING = "RUN_TEXT_NODE_MISSING"
STATUS_RANGE_OUT_OF_BOUNDS = "RANGE_OUT_OF_BOUNDS"
STATUS_EXPECTED_BEFORE_MISMATCH = "EXPECTED_BEFORE_MISMATCH"
STATUS_MULTI_RUN_RANGE_NOT_SUPPORTED = "MULTI_RUN_RANGE_NOT_SUPPORTED"


# ── paragraph / run discovery ──────────────────────────────────

def _is_paragraph(elem: ET.Element) -> bool:
    return local_name(elem.tag).lower() == "p"


def _is_run(elem: ET.Element) -> bool:
    return local_name(elem.tag).lower() == "run"


def _is_text_node(elem: ET.Element) -> bool:
    return local_name(elem.tag).lower() == "t"


def find_paragraph_in_cell(cell_elem: ET.Element,
                            paragraph_index: int) -> ET.Element | None:
    """cell 내 <hp:p> 자손을 순서대로 탐색해 paragraph_index 위치 반환."""
    paragraphs: list[ET.Element] = [
        e for e in cell_elem.iter() if _is_paragraph(e)
    ]
    if paragraph_index < 0 or paragraph_index >= len(paragraphs):
        return None
    return paragraphs[paragraph_index]


def find_run_in_paragraph(paragraph_elem: ET.Element,
                          run_index: int) -> ET.Element | None:
    """paragraph 내 <hp:run> 자식을 순서대로 탐색해 run_index 위치 반환."""
    runs = [c for c in paragraph_elem.iter() if _is_run(c)]
    if run_index < 0 or run_index >= len(runs):
        return None
    return runs[run_index]


def paragraph_runs(paragraph_elem: ET.Element) -> list[ET.Element]:
    return [c for c in paragraph_elem.iter() if _is_run(c)]


def paragraph_text(paragraph_elem: ET.Element) -> str:
    """paragraph 내 <hp:t> 텍스트 모두 concat."""
    parts: list[str] = []
    for elem in paragraph_elem.iter():
        if _is_text_node(elem):
            parts.append(elem.text or "")
    return "".join(parts)


def run_text(run_elem: ET.Element) -> str:
    """run 내 첫 <hp:t> text 또는 ""."""
    for elem in run_elem.iter():
        if _is_text_node(elem):
            return elem.text or ""
    return ""


def _first_text_node_in_run(run_elem: ET.Element) -> ET.Element | None:
    for elem in run_elem.iter():
        if _is_text_node(elem):
            return elem
    return None


# ── single-run text range edit ─────────────────────────────────

def apply_text_range_edit(
    paragraph_elem: ET.Element,
    run_elem: ET.Element,
    range_start: int,
    range_end: int,
    after_text: str,
    *,
    expected_before: str | None = None,
) -> dict[str, Any]:
    """단일 run text 를 [range_start:range_end] 슬라이스를 after_text 로 교체.

    range_* 는 해당 run 의 text node 기준 offset (0..len(run_text)).
    expected_before 가 주어지면 run_text[range_start:range_end] 와 일치
    검증.

    Returns dict with keys: status, beforeText, afterText, charPrIDRef,
    paraPrIDRef, runIndexInPara.
    charPrIDRef/paraPrIDRef 는 run/paragraph 의 attrib 그대로 (변경 없음).
    """
    text_node = _first_text_node_in_run(run_elem)
    if text_node is None:
        return {
            "status": STATUS_RUN_TEXT_NODE_MISSING,
            "beforeText": None,
            "afterText": None,
            "charPrIDRef": run_elem.attrib.get("charPrIDRef"),
            "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
            "runIndexInPara": _index_of(paragraph_runs(paragraph_elem),
                                        run_elem),
        }
    original = text_node.text or ""
    if (range_start < 0 or range_end < range_start
            or range_end > len(original)):
        return {
            "status": STATUS_RANGE_OUT_OF_BOUNDS,
            "beforeText": original,
            "afterText": None,
            "charPrIDRef": run_elem.attrib.get("charPrIDRef"),
            "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
            "runIndexInPara": _index_of(paragraph_runs(paragraph_elem),
                                        run_elem),
        }
    slice_before = original[range_start:range_end]
    if (expected_before is not None
            and slice_before != expected_before):
        return {
            "status": STATUS_EXPECTED_BEFORE_MISMATCH,
            "beforeText": slice_before,
            "expectedBefore": expected_before,
            "afterText": None,
            "charPrIDRef": run_elem.attrib.get("charPrIDRef"),
            "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
            "runIndexInPara": _index_of(paragraph_runs(paragraph_elem),
                                        run_elem),
        }
    new_text = original[:range_start] + after_text + original[range_end:]
    text_node.text = new_text
    return {
        "status": STATUS_OK,
        "beforeText": original,
        "afterText": new_text,
        "sliceBefore": slice_before,
        "sliceAfter": after_text,
        "charPrIDRef": run_elem.attrib.get("charPrIDRef"),
        "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
        "runIndexInPara": _index_of(paragraph_runs(paragraph_elem),
                                    run_elem),
    }


def _index_of(seq: list[ET.Element], elem: ET.Element) -> int:
    for i, e in enumerate(seq):
        if e is elem:
            return i
    return -1


# ── multi-run cross detector ───────────────────────────────────

def detect_multi_run_range(
    paragraph_elem: ET.Element,
    range_anchor: int,
    range_focus: int,
) -> bool:
    """paragraph 전체 텍스트 기준 [anchor, focus) 가 단일 run 안에 들어가지
    않으면 True (multi-run cross).

    paragraph 의 각 run text 길이를 누적해 [a, b) 가 한 run 의 [start, end]
    구간 내부면 single-run.
    """
    a, b = sorted((range_anchor, range_focus))
    pos = 0
    for run in paragraph_runs(paragraph_elem):
        rt = run_text(run)
        rs = pos
        re_ = pos + len(rt)
        if a >= rs and b <= re_:
            return False
        pos = re_
    return True


# ── multi-run text range edit (WEB-OFFICE-PARA-EDIT-MULTI-RUN-01) ─

STATUS_UNSAFE_RUN_CHILDREN = "UNSAFE_RUN_CHILDREN"
STATUS_NEW_CHARPR_INTRODUCED = "NEW_CHARPR_INTRODUCED"
STATUS_RUN_SPAN_NOT_FOUND = "RUN_SPAN_NOT_FOUND"

POLICY_ANCHOR_CHARPR = "ANCHOR_CHARPR"
POLICY_FOCUS_CHARPR = "FOCUS_CHARPR"
POLICY_REQUIRES_REVIEW = "REQUIRES_REVIEW"


def _is_safe_text_run(run_elem: ET.Element) -> bool:
    """run 이 hp:t 한 개만 자식으로 갖는 순수 텍스트 run 인지.

    1차 공정 안전 정책: 비텍스트 child (hp:ctrl, hp:br, hp:lineBreak,
    hp:fld, hp:secPr 등) 가 섞인 run 은 multi-run 처리 시 reject 한다.
    """
    children = list(run_elem)
    if len(children) != 1:
        return False
    return _is_text_node(children[0])


def _build_parent_map(
    paragraph_elem: ET.Element,
) -> dict[int, ET.Element]:
    """paragraph 서브트리에서 run elements 의 parent 매핑."""
    parents: dict[int, ET.Element] = {}
    for parent in paragraph_elem.iter():
        for child in list(parent):
            parents[id(child)] = parent
    return parents


def apply_text_range_edit_multi_run(
    paragraph_elem: ET.Element,
    range_start: int,
    range_end: int,
    after_text: str,
    *,
    apply_charpr_idref: str | None,
    policy: str = POLICY_ANCHOR_CHARPR,
    expected_before: str | None = None,
) -> dict[str, Any]:
    """paragraph 전체 offset [range_start, range_end) 를 multi-run 범위로
    분해해 REPLACE / DELETE 적용.

    동작 요약:
      - run span 의 anchor / middle / focus 를 식별한다.
      - 모든 span 내부 run 은 순수 텍스트 run (hp:t 한 개) 이어야 한다.
      - anchor run 의 text = anchor_text[:local_s] + after_text 로 치환.
      - focus run 의 text = focus_text[local_e:] 로 단축.
      - 중간 runs 는 paragraph 에서 제거.
      - charPrIDRef: policy 에 따라 anchor 또는 focus 의 charPr 가 유지.
        신규 charPr 는 일절 생성하지 않는다.

    Returns dict (status + 보조 정보). status==STATUS_OK 이면 변경 완료.
    """
    if policy == POLICY_REQUIRES_REVIEW:
        return {"status": "REQUIRES_REVIEW",
                  "policy": policy}
    if range_end < range_start:
        return {"status": STATUS_RANGE_OUT_OF_BOUNDS}
    runs = paragraph_runs(paragraph_elem)
    if not runs:
        return {"status": STATUS_RUN_SPAN_NOT_FOUND}
    para_full = paragraph_text(paragraph_elem)
    if range_start < 0 or range_end > len(para_full):
        return {"status": STATUS_RANGE_OUT_OF_BOUNDS,
                  "paragraphLen": len(para_full)}
    if (expected_before is not None
            and para_full[range_start:range_end] != expected_before):
        return {"status": STATUS_EXPECTED_BEFORE_MISMATCH,
                  "sliceBefore": para_full[range_start:range_end],
                  "expectedBefore": expected_before}

    # run span 분해
    anchor_idx = -1; focus_idx = -1
    anchor_local_s = 0; focus_local_e = 0
    pos = 0
    span_offsets: list[tuple[int, int]] = []
    for i, r in enumerate(runs):
        rt = run_text(r)
        rs = pos; re_ = pos + len(rt)
        span_offsets.append((rs, re_))
        if anchor_idx < 0 and range_start < re_:
            # anchor 위치: range_start 가 들어가는 run.
            # boundary 케이스: range_start == re_ 이면 다음 run 에 anchor.
            anchor_idx = i
            anchor_local_s = range_start - rs
        # focus: range_end 가 들어가는 run. range_end == re_ 면 이 run
        # 의 끝까지 포함 → focus 도 이 run.
        if focus_idx < 0 and range_end <= re_:
            focus_idx = i
            focus_local_e = range_end - rs
        pos = re_
    # range_start 가 paragraph 끝과 동일 → anchor = 마지막 run, 끝.
    if anchor_idx < 0:
        anchor_idx = len(runs) - 1
        anchor_local_s = len(run_text(runs[anchor_idx]))
    if focus_idx < 0:
        focus_idx = len(runs) - 1
        focus_local_e = len(run_text(runs[focus_idx]))
    if focus_idx < anchor_idx:
        return {"status": STATUS_RUN_SPAN_NOT_FOUND,
                  "anchorIndex": anchor_idx, "focusIndex": focus_idx}
    if anchor_idx == focus_idx:
        # 단일 run 케이스 — multi-run 전용 회로 외부에서 처리해야 함.
        return {"status": "SINGLE_RUN_RANGE",
                  "anchorIndex": anchor_idx}

    span_runs = runs[anchor_idx:focus_idx + 1]
    for r in span_runs:
        if not _is_safe_text_run(r):
            return {"status": STATUS_UNSAFE_RUN_CHILDREN,
                      "runIndex": runs.index(r)}

    anchor_run = span_runs[0]
    focus_run = span_runs[-1]
    middle_runs = span_runs[1:-1]

    anchor_pr = anchor_run.attrib.get("charPrIDRef")
    focus_pr = focus_run.attrib.get("charPrIDRef")
    orig_charpr_set = {r.attrib.get("charPrIDRef") for r in runs}

    # 정책에 따른 chosen_pr 산출 (anchor 기본, FOCUS 시 focus).
    # writer 단계 검증 원칙: apply_charpr_idref 가 주어지면 그 값이
    # 원본 charPr 집합 안에 있어야 한다 (신규 charPr 도입 차단).
    # policy 매칭은 command 발급 측 (model) 의 책임이므로 writer 는
    # apply_charpr_idref 의 원본 집합 소속만 강제한다.
    if policy == POLICY_FOCUS_CHARPR:
        chosen_pr = focus_pr
    else:
        chosen_pr = anchor_pr
    if (apply_charpr_idref is not None
            and apply_charpr_idref not in orig_charpr_set):
        return {"status": STATUS_NEW_CHARPR_INTRODUCED,
                  "applyCharPrIDRef": apply_charpr_idref,
                  "origCharPrSet":
                      sorted(str(x) for x in orig_charpr_set)}

    # 본 변경: anchor run 텍스트 = anchor_text[:local_s] + after_text
    anchor_t = _first_text_node_in_run(anchor_run)
    focus_t = _first_text_node_in_run(focus_run)
    if anchor_t is None or focus_t is None:
        return {"status": STATUS_RUN_TEXT_NODE_MISSING}
    anchor_orig = anchor_t.text or ""
    focus_orig = focus_t.text or ""
    anchor_t.text = anchor_orig[:anchor_local_s] + after_text
    focus_t.text = focus_orig[focus_local_e:]

    # POLICY_FOCUS_CHARPR 인 경우 anchor run 의 charPr 를 focus_pr 로
    # 변경할 수 있지만, "신규 charPr 생성 금지" 원칙 상 기존 charPr
    # 집합 안에서만 허용. anchor run 의 charPr 를 운영 변경하면 원래
    # anchor 텍스트도 영향을 받으므로 1차 공정에서는 anchor 의 charPr
    # 를 그대로 유지한다 (chosen_pr 는 정합 검증 신호로만 사용).
    # (FOCUS_CHARPR 의 effective charPr 변경은 후속 공정에서 처리.)

    # 중간 runs 제거
    parents = _build_parent_map(paragraph_elem)
    for r in middle_runs:
        parent = parents.get(id(r))
        if parent is None:
            return {"status": STATUS_RUN_SPAN_NOT_FOUND,
                      "detail": "middle run parent not found"}
        parent.remove(r)

    # 검증: 적용 후 charPr 집합 ⊆ 원본 집합
    after_set = {r.attrib.get("charPrIDRef")
                              for r in paragraph_runs(paragraph_elem)}
    if not after_set.issubset(orig_charpr_set):
        return {"status": STATUS_NEW_CHARPR_INTRODUCED,
                  "afterCharPrSet": sorted(str(x) for x in after_set),
                  "origCharPrSet":
                      sorted(str(x) for x in orig_charpr_set)}

    return {
        "status": STATUS_OK,
        "anchorIndex": anchor_idx,
        "focusIndex": focus_idx,
        "removedMiddleRuns": len(middle_runs),
        "appliedCharPrIDRef": anchor_pr,
        "policyCharPr": chosen_pr,
        "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
        "policy": policy,
    }


# ── ApplyFormat (existing charPr) primitive ────────────────────
# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01

STATUS_TARGET_CHARPR_NOT_IN_HEADER = "TARGET_CHARPR_NOT_IN_HEADER"
STATUS_EMPTY_RANGE = "EMPTY_RANGE"


def _clone_run_element(src: ET.Element) -> ET.Element:
    """src run elem 의 얕은 clone — attrib 복사 + hp:t 한 자식만.

    _is_safe_text_run 통과 run 에서만 호출되어야 한다.
    """
    new_run = ET.Element(src.tag, dict(src.attrib))
    src_t = _first_text_node_in_run(src)
    if src_t is not None:
        new_t = ET.SubElement(new_run, src_t.tag, dict(src_t.attrib))
        new_t.text = src_t.text
    return new_run


def apply_charpr_to_range_existing(
    paragraph_elem: ET.Element,
    range_start: int,
    range_end: int,
    target_char_pr_id: str,
    *,
    header_char_pr_ids: set[str],
    expected_before: str | None = None,
) -> dict[str, Any]:
    """paragraph offset [range_start, range_end) 의 run segment 에
    targetCharPrIDRef 를 적용. run split 은 필요한 경우만 수행한다.

    원칙:
      - paragraph.text 무변경
      - header.xml 무변경 (target_char_pr_id 는 header_char_pr_ids 안)
      - 위험 child 가 있는 run 은 reject
      - 선택 range 밖 텍스트/charPr 보존
      - 신규 charPr id 생성 없음

    Returns: status + beforeSegments (역연산 자료) + afterRunCharPrs +
              affectedRunCount 등.
    """
    if range_end < range_start:
        return {"status": STATUS_RANGE_OUT_OF_BOUNDS}
    if range_end == range_start:
        return {"status": STATUS_EMPTY_RANGE}
    if target_char_pr_id is None or str(target_char_pr_id) == "":
        return {"status": STATUS_TARGET_CHARPR_NOT_IN_HEADER,
                  "targetCharPrIDRef": target_char_pr_id}
    if str(target_char_pr_id) not in header_char_pr_ids:
        return {"status": STATUS_TARGET_CHARPR_NOT_IN_HEADER,
                  "targetCharPrIDRef": target_char_pr_id,
                  "headerCharPrIds": sorted(header_char_pr_ids)[:20]}

    runs = paragraph_runs(paragraph_elem)
    if not runs:
        return {"status": STATUS_RUN_SPAN_NOT_FOUND}
    para_full = paragraph_text(paragraph_elem)
    if range_start < 0 or range_end > len(para_full):
        return {"status": STATUS_RANGE_OUT_OF_BOUNDS,
                  "paragraphLen": len(para_full)}
    if (expected_before is not None
            and para_full[range_start:range_end] != expected_before):
        return {"status": STATUS_EXPECTED_BEFORE_MISMATCH,
                  "sliceBefore": para_full[range_start:range_end],
                  "expectedBefore": expected_before}

    # run offset 표 + 영향 받는 run idx 추출 + 안전 검증
    pos = 0
    run_spans: list[tuple[int, int]] = []  # [(rs, re)]
    for r in runs:
        rt = run_text(r)
        run_spans.append((pos, pos + len(rt)))
        pos += len(rt)

    # 영향 받는 run: range 와 겹치는 모든 run
    affected_indexes: list[int] = []
    for i, (rs, re_) in enumerate(run_spans):
        if rs >= range_end:
            break
        if re_ <= range_start:
            continue
        # 겹침 (run text 비어있는 경우는 무시)
        if rs == re_:
            continue
        affected_indexes.append(i)
    if not affected_indexes:
        return {"status": STATUS_RUN_SPAN_NOT_FOUND}

    # 모든 영향 run 은 단일 hp:t safe run 이어야 함
    for i in affected_indexes:
        if not _is_safe_text_run(runs[i]):
            return {"status": STATUS_UNSAFE_RUN_CHILDREN,
                      "runIndex": i}

    # 역연산 자료: before run charPr 분포
    before_segments: list[dict[str, Any]] = []
    for i in affected_indexes:
        rs, re_ = run_spans[i]
        seg_start = max(rs, range_start)
        seg_end = min(re_, range_end)
        before_segments.append({
            "runIndexBefore": i,
            "segmentStart": seg_start,
            "segmentEnd": seg_end,
            "charPrIDRef": runs[i].attrib.get("charPrIDRef"),
        })

    # 적용: 각 영향 run 에 대해 (좌단편 / 중간 = target charPr 적용 /
    # 우단편) split. 중간 segment 가 run 전체이면 split 없이 attrib 변경.
    parents = _build_parent_map(paragraph_elem)
    # 안정성: range 내림차순으로 처리해 인덱스 영향 최소화 — 하지만
    # parent 의 child list 가 변하므로 각 처리 시점에 parent.index 로
    # 위치 결정.
    for i in sorted(affected_indexes, reverse=True):
        run = runs[i]
        rs, re_ = run_spans[i]
        seg_start = max(rs, range_start)
        seg_end = min(re_, range_end)
        local_s = seg_start - rs
        local_e = seg_end - rs
        rt_node = _first_text_node_in_run(run)
        if rt_node is None:
            return {"status": STATUS_RUN_TEXT_NODE_MISSING,
                      "runIndex": i}
        full_text = rt_node.text or ""
        parent = parents.get(id(run))
        if parent is None:
            return {"status": STATUS_RUN_SPAN_NOT_FOUND,
                      "detail": "run parent not found"}
        run_pos_in_parent = list(parent).index(run)

        left_text = full_text[:local_s]
        mid_text = full_text[local_s:local_e]
        right_text = full_text[local_e:]

        if local_s == 0 and local_e == len(full_text):
            # run 전체가 range 내 → attrib 만 변경, split 없음
            run.set("charPrIDRef", str(target_char_pr_id))
            continue

        # split 필요. 좌/중/우 run 생성 (비어있는 단편은 생략 가능)
        new_runs_to_insert: list[ET.Element] = []
        if left_text:
            left_run = _clone_run_element(run)
            left_t = _first_text_node_in_run(left_run)
            if left_t is not None:
                left_t.text = left_text
            new_runs_to_insert.append(left_run)
        if mid_text:
            mid_run = _clone_run_element(run)
            mid_run.set("charPrIDRef", str(target_char_pr_id))
            mid_t = _first_text_node_in_run(mid_run)
            if mid_t is not None:
                mid_t.text = mid_text
            new_runs_to_insert.append(mid_run)
        if right_text:
            right_run = _clone_run_element(run)
            right_t = _first_text_node_in_run(right_run)
            if right_t is not None:
                right_t.text = right_text
            new_runs_to_insert.append(right_run)

        # 원본 run 제거 후 분할 run 삽입
        parent.remove(run)
        for offset, new_r in enumerate(new_runs_to_insert):
            parent.insert(run_pos_in_parent + offset, new_r)

    # 사후: paragraph.text 가 무변경인지 self-check
    after_text = paragraph_text(paragraph_elem)
    if after_text != para_full:
        return {"status": "TEXT_CHANGED_UNEXPECTEDLY",
                  "before": para_full, "after": after_text}

    after_runs = paragraph_runs(paragraph_elem)
    after_char_pr_set = {r.attrib.get("charPrIDRef")
                                            for r in after_runs}
    # 신규 charPr 도입 차단 (header 안에 있는지만 확인 — 이미 위에서 검증)
    if (str(target_char_pr_id) not in header_char_pr_ids
            and target_char_pr_id is not None):
        return {"status": STATUS_NEW_CHARPR_INTRODUCED,
                  "targetCharPrIDRef": target_char_pr_id}

    return {
        "status": STATUS_OK,
        "targetCharPrIDRef": str(target_char_pr_id),
        "affectedRunCount": len(affected_indexes),
        "beforeSegments": before_segments,
        "afterRunCharPrs": [r.attrib.get("charPrIDRef")
                                              for r in after_runs],
        "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
    }


def locate_run_for_paragraph_offset(
    paragraph_elem: ET.Element,
    range_anchor: int,
    range_focus: int,
) -> tuple[ET.Element | None, int, int]:
    """paragraph offset [a, b) 를 포함하는 단일 run 을 찾고, 해당 run text
    기준의 local (start, end) 을 반환.

    multi-run cross 또는 OOB 면 (None, -1, -1) 반환.
    """
    a, b = sorted((range_anchor, range_focus))
    pos = 0
    for run in paragraph_runs(paragraph_elem):
        rt = run_text(run)
        rs = pos
        re_ = pos + len(rt)
        if a >= rs and b <= re_:
            return run, a - rs, b - rs
        pos = re_
    return None, -1, -1
