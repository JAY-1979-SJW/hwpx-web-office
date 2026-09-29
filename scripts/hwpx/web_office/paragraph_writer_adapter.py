"""Paragraph writer adapter (WRITER-PARA-PLAN-01).

paragraph_edits plan 을 받아 HwpxPackage 의 in-memory XML 에 단일 run
text range edit 을 적용한다. 본 어댑터는 input/output 파일 경로를 직접
다루지 않고, 호출자(HwpxPackage 보유자)가 mutation 이후 write_package
를 담당한다.

§11-6 자재 재사용: 본 어댑터는 hwpx_paragraph_ops 와 hwpx_table_ops 의
table/row/cell 탐색 helper 만 호출한다. 신규 mutation primitive 작성 금지.
"""
from __future__ import annotations
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))
_HX = _PR / "scripts" / "hwpx"
if str(_HX) not in sys.path:
    sys.path.insert(0, str(_HX))

from hwpx_package import HwpxPackage  # noqa: E402
from hwpx_table_ops import (  # noqa: E402
    find_table, row_elements, cell_elements,
)
from hwpx_paragraph_ops import (  # noqa: E402
    find_paragraph_in_cell, find_run_in_paragraph,
    paragraph_text, run_text,
    locate_run_for_paragraph_offset, detect_multi_run_range,
    apply_text_range_edit,
    apply_text_range_edit_multi_run,
    apply_charpr_to_range_existing,
    _is_safe_text_run,
    POLICY_ANCHOR_CHARPR, POLICY_REQUIRES_REVIEW,
    STATUS_OK, STATUS_RUN_TEXT_NODE_MISSING,
    STATUS_RANGE_OUT_OF_BOUNDS, STATUS_EXPECTED_BEFORE_MISMATCH,
    STATUS_UNSAFE_RUN_CHILDREN, STATUS_NEW_CHARPR_INTRODUCED,
    STATUS_RUN_SPAN_NOT_FOUND,
    STATUS_TARGET_CHARPR_NOT_IN_HEADER, STATUS_EMPTY_RANGE,
)


# ── reject reasons ─────────────────────────────────────────────
REASON_BODY_PARAGRAPH_NOT_SUPPORTED = "BODY_PARAGRAPH_NOT_SUPPORTED"
REASON_CELL_COORD_CONFLICT = "CELL_COORD_CONFLICT"
REASON_MULTI_RUN_RANGE_NOT_SUPPORTED = "MULTI_RUN_RANGE_NOT_SUPPORTED"
REASON_SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
REASON_TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
REASON_ROW_NOT_FOUND = "ROW_NOT_FOUND"
REASON_CELL_NOT_FOUND = "CELL_NOT_FOUND"
REASON_PARAGRAPH_NOT_FOUND = "PARAGRAPH_NOT_FOUND"
REASON_RUN_NOT_FOUND = "RUN_NOT_FOUND"
REASON_RANGE_OUT_OF_BOUNDS = "RANGE_OUT_OF_BOUNDS"
REASON_EXPECTED_BEFORE_MISMATCH = "EXPECTED_BEFORE_MISMATCH"
REASON_CHARPR_MISMATCH = "CHARPR_MISMATCH"
REASON_UNSUPPORTED_COMMAND_TYPE = "UNSUPPORTED_COMMAND_TYPE"
REASON_SCOPE_MISSING = "SCOPE_MISSING"
# WEB-OFFICE-BODY-PARAGRAPH-WRITER-01 신규 reject 사유.
REASON_SECTION_NOT_FOUND = "SECTION_NOT_FOUND"
REASON_BODY_BLOCK_NOT_PARAGRAPH = "BODY_BLOCK_NOT_PARAGRAPH"
# CLAUDE.md §4.2 머리말/꼬리말 텍스트 편집 신규 reject 사유.
REASON_HEADER_FOOTER_NOT_FOUND = "HEADER_FOOTER_NOT_FOUND"
# WEB-OFFICE-PARA-EDIT-MULTI-RUN-01 신규 reject 사유.
REASON_UNSAFE_RUN_CHILDREN = "UNSAFE_RUN_CHILDREN"
REASON_NEW_CHARPR_INTRODUCED = "NEW_CHARPR_INTRODUCED"
REASON_REQUIRES_REVIEW = "REQUIRES_REVIEW"
REASON_TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED = (
    "TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED")
# WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01 신규 reject 사유.
REASON_TARGET_CHARPR_NOT_IN_HEADER = "TARGET_CHARPR_NOT_IN_HEADER"
REASON_TARGET_PARAPR_NOT_IN_HEADER = "TARGET_PARAPR_NOT_IN_HEADER"
REASON_PARA_TEXT_MUTATED = "PARA_TEXT_MUTATED"
REASON_EMPTY_RANGE = "EMPTY_RANGE"

_SUPPORTED_COMMAND_TYPES = {
    "TYPE_TEXT", "REPLACE_TEXT_RANGE", "DELETE_TEXT_RANGE",
    "APPLY_FORMAT",
    # WEB-OFFICE-PARA-FORMAT-01(M2): 문단서식(paraPr) 교체.
    # header.xml 무수정 — 기존 paraPr id 로만 교체.
    "APPLY_PARA_FORMAT",
    # WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01:
    "PARA_INSERT",
    # WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01:
    "PARA_DELETE",
}

# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 reject 사유
REASON_SECTION_BOUNDARY_NOT_SUPPORTED = "SECTION_BOUNDARY_NOT_SUPPORTED"
REASON_LIST_ITEM_NOT_SUPPORTED = "LIST_ITEM_NOT_SUPPORTED"
REASON_PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED = (
    "PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED")
REASON_PARENT_NOT_FOUND = "PARENT_NOT_FOUND"
# WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01 reject 사유
REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED = (
    "PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED")
REASON_NO_PREV_PARAGRAPH = "NO_PREV_PARAGRAPH"


def _reject(item: dict, reason: str, **extra) -> dict:
    rec = {
        "reason": reason,
        "commandId": item.get("commandId"),
        "paragraphId": item.get("paragraphId"),
        "containerScope": item.get("containerScope"),
    }
    rec.update(extra)
    return rec


_HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _local_tag(elem) -> str:
    t = elem.tag
    if "}" in t:
        t = t.rsplit("}", 1)[-1]
    return t.lower()


_HH_NS = "http://www.hancom.co.kr/hwpml/2011/head"
_HEADER_CHARPR_IDS_CACHE: dict[int, set[str]] = {}


def _strip_lineseg(paragraph_elem: ET.Element) -> None:
    """텍스트가 바뀐 문단의 <hp:linesegarray> 를 통째로 제거한다.

    실측(2026-07-23): 텍스트 편집 후 lineseg 를 그대로(stale) 두면
    한컴이 원래의 좁은 1줄 자리에 글자를 욱여넣어 서로 겹쳐 뭉갠다.
    반면 linesegarray 요소 자체를 완전히 없애면 한컴이 셀 폭 기준으로
    올바르게 재조판(여러 줄로 줄바꿈 + 행 높이 자동 확장)한다 —
    "근사값을 넣는다"가 아니라 "완전히 비운다"가 맞는 처방이었다.

    (2026-07-24) 대표님 지시로 편집 경로에서는 더 이상 호출하지 않는다
    — 웹뷰어 자체 좌표 렌더러가 lineseg 없는 문단을 그릴 좌표를 못
    만들어(그 문단이 화면에서 통째로 사라짐) 저장 직후 화면이 클라
    이언트 캐시 오버레이("덧방")에 의존하게 되는 부작용이 있었다.
    후속 대체 로직은 _fix_lineseg_on_text_edit — 기존 lineseg 는
    보존하고, 줄 수가 늘어난다고 추정될 때만 부족한 줄만큼 근사
    lineseg 를 이어붙인다. 이 함수 자체는 과거 회귀 비교/문서화 목적
    으로 남겨두되 편집 경로에서는 미사용."""
    for child in list(paragraph_elem):
        if _local_tag(child) == "linesegarray":
            paragraph_elem.remove(child)


# 한 문단의 추정 보정이 넘어서는 안 되는 안전 상한(HWPUNIT). A4 인쇄
# 가능 높이의 보수적 근사치(coord_styles.parse_page_geometry 기본
# 페이지 높이 84186 HWPUNIT 대비 여유 있게 낮춰 잡음) — 이 함수는
# header.xml 의 실제 페이지 규격에 접근하지 않으므로(paragraph_elem
# 만 받음) 정확한 페이지 경계 대신 "명백히 페이지를 넘는" 수준만
# 걸러내는 안전장치다. 실제 페이지 폭/여백 기반 정밀 판정은 여기서
# 하지 않는다 — 대표님 지시("페이지 초과 시 경고 정도로 막아두면
# 충분") 수준의 최소 가드.
_LINESEG_FIX_PAGE_OVERFLOW_GUARD_HU = 70000

_LINESEG_FIX_AUDIT_DIR = _PR / "data/audit/web_office_lineseg_fix"


def _log_lineseg_fix(*, context: dict[str, Any] | None, extra: int,
                      capacity: int, before_len: int, after_len: int,
                      capped: bool, capped_at: int | None) -> None:
    """근사 보정 발동 기록 — append-only JSONL(data/audit, CLAUDE.md §5).

    실측(2026-07-24) 대표님 지적: 이건 근사 보정이라 언젠가 정확도가
    어긋나는 문서가 나온다. 그때 "어느 문서·문단에서 몇 줄을 보정했는지"
    가 안 남아 있으면 원인 추적이 불가능해진다 — 지난 휴리스틱 가드
    (오버랩 방지 가드 등) 때와 같은 이유로 반드시 남긴다.
    """
    import datetime as _dt
    import json as _json
    rec = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "event": "LINESEG_FIX_ON_TEXT_EDIT",
        "sourcePath": (context or {}).get("sourcePath"),
        "paragraphId": (context or {}).get("paragraphId"),
        "containerScope": (context or {}).get("containerScope"),
        "beforeLen": before_len,
        "afterLen": after_len,
        "estimatedCapacityCharsPerLine": capacity,
        "extraLinesAppended": extra,
        "pageOverflowGuardTriggered": capped,
        "cappedAtLine": capped_at,
    }
    try:
        _LINESEG_FIX_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        today = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        p = _LINESEG_FIX_AUDIT_DIR / f"{today}.jsonl"
        with p.open("a", encoding="utf-8") as fp:
            fp.write(_json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass  # 로그 실패가 편집 자체를 막지는 않는다


def _fix_lineseg_on_text_edit(paragraph_elem: ET.Element,
                               before_text: str,
                               after_text: str,
                               *, context: dict[str, Any] | None = None
                               ) -> None:
    """텍스트 편집 후 lineseg 처리 (2026-07-24, 대표님 지시).

    "lineseg 삭제 로직을 제거하고, 텍스트 편집 시 기존 lineseg를
    보존한다. 줄 수가 늘어난 경우에만 해당 문단의 lineseg를 추정
    보정한다. 한컴 COM은 편집 경로에서 호출하지 않는다."

    기존 lineseg 들의 textpos 경계로 "한컴이 실제로 배치했던 줄당
    문자수(capacity)"를 역산한다 — 근사 폭/폰트 계산이 아니라 한컴
    자신의 과거 결과를 기준으로 삼는 편이 더 신뢰할 수 있다. 편집 후
    텍스트가 그 capacity 로 기존 줄 수 안에 다 안 들어간다고 추정되면
    (줄 수 증가), 마지막 lineseg 를 복제해 부족한 줄만큼만 근사
    좌표로 이어붙인다. 줄 수가 늘지 않으면(같거나 줄어들면)
    linesegarray 는 전혀 건드리지 않고 그대로 보존한다.

    새로 이어붙이는 lineseg 의 vertpos/textpos 는 어디까지나 추정치
    — 한컴이 실제로 열면 스스로 재조판해 정확한 값으로 대체한다.
    본 함수의 목적은 "완전히 비워서 화면에서 사라지게" 하지 않고,
    최소한 그럴듯한 임시 좌표를 남겨 자체 좌표 렌더러가 계속 무언가
    그릴 수 있게 하는 것뿐이다.

    경계 케이스(대표님 지적, 2026-07-24) — 알려진 미해결 사항:
      · 줄 수가 "줄어드는" 경우는 대칭 처리하지 않는다(지시 범위 밖).
        저장 파일 자체는 한컴이 재조판하므로 무해하지만, 화면에서는
        문단 아래에 뜬 공간이 보일 수 있다. 실제로 관측되면 그때
        대칭 로직을 추가한다.
      · 페이지 경계를 넘는 수준의 증가는 _LINESEG_FIX_PAGE_OVERFLOW_GUARD_HU
        에서 증분을 멈추고 경고를 남긴다(아래) — 근사치가 실제 페이지
        수까지 넘겨 배치를 크게 어긋나게 하는 것을 막는 최소 가드.
    """
    import xml.etree.ElementTree as _ET  # noqa: WPS433
    arr = next((c for c in paragraph_elem
                if _local_tag(c) == "linesegarray"), None)
    if arr is None:
        return
    segs = [c for c in arr if _local_tag(c) == "lineseg"]
    n = len(segs)
    if n == 0 or len(after_text) <= len(before_text):
        return  # 늘지 않음(또는 lineseg 없음) — 손대지 않고 보존
    positions = [int(float(s.get("textpos", "0") or "0")) for s in segs]
    bounds = positions + [len(before_text)]
    counts = [bounds[i + 1] - bounds[i] for i in range(n)]
    # capacity — "꽉 찬 줄"의 문자수 추정. 마지막 줄은 보통 덜 차 있어
    # 대표값에서 제외(줄이 1개뿐이면 그 줄 자체가 유일한 근거).
    capacity = max(counts) if n == 1 else max(counts[:-1])
    if capacity <= 0:
        return
    estimated_lines = math.ceil(len(after_text) / capacity)
    if estimated_lines <= n:
        return  # 추정상 줄 수 증가 없음 — 보존
    extra = estimated_lines - n
    last_attrib = dict(segs[-1].attrib)
    vertpos0 = float(last_attrib.get("vertpos", "0") or "0")
    spacing = (float(last_attrib.get("spacing", "0") or "0")
               or float(last_attrib.get("vertsize", "0") or "0"))
    base_textpos = bounds[-2] if n > 1 else 0
    capped = False
    capped_at: int | None = None
    added = 0
    for i in range(1, extra + 1):
        new_vertpos = vertpos0 + spacing * i
        if new_vertpos - vertpos0 > _LINESEG_FIX_PAGE_OVERFLOW_GUARD_HU:
            capped = True
            capped_at = i
            break
        new_attrib = dict(last_attrib)
        new_attrib["vertpos"] = str(int(new_vertpos))
        new_attrib["textpos"] = str(
            min(len(after_text) - 1, base_textpos + capacity * i))
        new_el = _ET.SubElement(arr, segs[-1].tag)
        new_el.attrib.update(new_attrib)
        added += 1
    _log_lineseg_fix(context=context, extra=added, capacity=capacity,
                      before_len=len(before_text), after_len=len(after_text),
                      capped=capped, capped_at=capped_at)


def _read_header_para_pr_ids(package: HwpxPackage) -> set[str]:
    """Contents/header.xml 의 <hh:paraPr id="N"> id 집합 (M2 문단서식 검증용)."""
    header_bytes: bytes | None = None
    for entry in ("Contents/header.xml", "Contents\\header.xml"):
        if entry in package.entries:
            header_bytes = package.entries[entry]
            break
    if header_bytes is None:
        for name, data in package.entries.items():
            if name.replace("\\", "/").endswith("Contents/header.xml"):
                header_bytes = data
                break
    if header_bytes is None:
        return set()
    try:
        root = ET.fromstring(header_bytes)
    except ET.ParseError:
        return set()
    ids: set[str] = set()
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] != "paraPr":
            continue
        pid = el.attrib.get("id")
        if pid is not None:
            ids.add(str(pid))
    return ids


def _read_header_char_pr_ids(package: HwpxPackage) -> set[str]:
    """package 의 Contents/header.xml 에서 <hh:charPr id="N"> 의 id 집합.

    package 단위 캐시 (id(package)) — 동일 package 에 대해 반복 호출 시
    파싱 비용 절감. APPLY_FORMAT 은 header.xml 무수정이므로 캐시 무효화
    걱정 없음.
    """
    cached = _HEADER_CHARPR_IDS_CACHE.get(id(package))
    if cached is not None:
        return cached
    header_bytes: bytes | None = None
    for entry in ("Contents/header.xml", "Contents\\header.xml"):
        if entry in package.entries:
            header_bytes = package.entries[entry]
            break
    if header_bytes is None:
        for name, data in package.entries.items():
            if name.replace("\\", "/").endswith("Contents/header.xml"):
                header_bytes = data
                break
    if header_bytes is None:
        result: set[str] = set()
    else:
        try:
            root = ET.fromstring(header_bytes)
            ids: set[str] = set()
            for el in root.iter(f"{{{_HH_NS}}}charPr"):
                cid = el.get("id", "")
                if cid:
                    ids.add(str(cid))
            result = ids
        except Exception:  # noqa: BLE001
            result = set()
    _HEADER_CHARPR_IDS_CACHE[id(package)] = result
    return result


def _resolve_body_paragraph(package: HwpxPackage, section_idx: int,
                                                          block_idx: int):
    """containerScope.kind="block" 의 (sectionIndex, blockIndex) →
    (entry, root, paragraph_elem) 또는 (None, reason).

    blockIndex 의 의미는 block_parser.parse_blocks_from_section 과 동일하다:
    section root 의 직계 자식을 순회하며 hp:p, hp:tbl, drawing/image,
    paragraph/table 을 자손에 가진 wrapper 만 block 으로 카운트.
    """
    secs = package.section_entries()
    if section_idx < 0 or section_idx >= len(secs):
        return None, REASON_SECTION_NOT_FOUND
    entry = secs[section_idx]
    try:
        root = package.read_xml(entry)
    except Exception:  # noqa: BLE001
        return None, REASON_SECTION_NOT_FOUND
    cur = 0
    for elem in list(root):
        tag = _local_tag(elem)
        is_block = False
        elem_kind = None
        if tag == "p":
            is_block = True
            elem_kind = "paragraph"
        elif tag == "tbl":
            is_block = True
            elem_kind = "table"
        elif tag in ("drawing", "pic"):
            is_block = True
            elem_kind = "drawing"
        elif tag in ("img",):
            is_block = True
            elem_kind = "image"
        else:
            has_p = any(_local_tag(c) == "p" for c in elem.iter())
            has_tbl = any(_local_tag(c) == "tbl" for c in elem.iter())
            if has_p or has_tbl:
                is_block = True
                elem_kind = "paragraph" if has_p and not has_tbl \
                                                    else "table"
        if not is_block:
            continue
        if cur == block_idx:
            if elem_kind != "paragraph" or tag != "p":
                return None, REASON_BODY_BLOCK_NOT_PARAGRAPH
            return (entry, root, elem), None
        cur += 1
    return None, REASON_PARAGRAPH_NOT_FOUND


def _resolve_header_footer_paragraph(
    package: HwpxPackage, section_idx: int, kind: str,
    object_id: str, paragraph_index: int):
    """containerScope.kind="header"/"footer" 의 (sectionIndex, objectId,
    paragraphIndex) → (entry, root, paragraph_elem) 또는 (None, reason).

    CLAUDE.md §4.2 — <hp:header>/<hp:footer> 안 문단의 텍스트 내용
    편집만 허용(구조 변경·표 구조 변경은 그대로 금지). object_id 는
    header/footer element 의 @id 속성(같은 섹션에 여러 개 있을 수
    있음 — BOTH_PAGE/EVEN_PAGE/ODD_PAGE 등)."""
    secs = package.section_entries()
    if section_idx < 0 or section_idx >= len(secs):
        return None, REASON_SECTION_NOT_FOUND
    entry = secs[section_idx]
    try:
        root = package.read_xml(entry)
    except Exception:  # noqa: BLE001
        return None, REASON_SECTION_NOT_FOUND

    container = next(
        (e for e in root.iter()
         if _local_tag(e) == kind and e.get("id") == str(object_id)),
        None)
    if container is None:
        return None, REASON_HEADER_FOOTER_NOT_FOUND

    paras = [e for e in container.iter() if _local_tag(e) == "p"]
    if paragraph_index < 0 or paragraph_index >= len(paras):
        return None, REASON_PARAGRAPH_NOT_FOUND
    return (entry, root, paras[paragraph_index]), None


def _resolve_cell(package: HwpxPackage, table_idx: int, row_idx: int,
                  col_idx: int):
    """(entry, root, cell_elem) 또는 (None, reason) 반환."""
    found = find_table(package, table_idx)
    if not found:
        return None, REASON_TABLE_NOT_FOUND
    entry, root, table = found
    rows = row_elements(table)
    if row_idx < 0 or row_idx >= len(rows):
        return None, REASON_ROW_NOT_FOUND
    cells = cell_elements(rows[row_idx])
    if col_idx < 0 or col_idx >= len(cells):
        return None, REASON_CELL_NOT_FOUND
    return (entry, root, cells[col_idx]), None


# ── WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01 helpers ────────

def _allocate_new_paragraph_id(section_root) -> str:
    """section_root 의 모든 hp:p id 중 max+1 을 문자열로 반환.

    HWPX paragraph id 는 sparse 정수 (corpus 100% non-contiguous, max
    값이 2^31 까지 올라가는 경우도 있음). 단순 max+1 정책으로 충돌 회피.
    """
    max_id = -1
    for elem in section_root.iter():
        if _local_tag(elem) != "p":
            continue
        pid = elem.attrib.get("id")
        if pid is None:
            continue
        try:
            n = int(pid)
        except ValueError:
            continue
        if n > max_id:
            max_id = n
    return str(max_id + 1) if max_id >= 0 else "1"


def _paragraph_has_section_break(paragraph_elem) -> bool:
    """paragraph 내부에 hp:secPr/hp:secPpr 가 있으면 section break paragraph."""
    for child in paragraph_elem.iter():
        if _local_tag(child) in ("secpr", "secppr"):
            return True
    return False


def _paragraph_has_inline_list(paragraph_elem) -> bool:
    """paragraph 내부에 hp:numPr (list/numbering inline) 가 있는지."""
    for child in paragraph_elem.iter():
        if _local_tag(child) == "numpr":
            return True
    return False


def _find_parent(root, target):
    """root 자손 중 target 의 부모 element 반환. 없으면 None."""
    for parent in root.iter():
        for child in list(parent):
            if child is target:
                return parent
    return None


def _iter_paragraphs(root):
    """root 안의 모든 hp:p element 를 순서대로 yield."""
    for elem in root.iter():
        if _local_tag(elem) == "p":
            yield elem


def _set_run_first_t_text(run_elem, text: str) -> None:
    """hp:run 의 첫 hp:t 텍스트만 교체. 다른 child 보존."""
    for child in run_elem:
        if _local_tag(child) == "t":
            child.text = text
            return
    # hp:t 가 없으면 추가
    import xml.etree.ElementTree as _ET
    t = _ET.SubElement(run_elem, f"{{{_HP_NS}}}t")
    t.text = text


def _apply_para_insert(section_root, paragraph_elem, *,
                                                  caret_offset: int,
                                                  new_paragraph_id: str,
                                                  new_par_pr_idref: str | None,
                                                  new_char_pr_idref: str | None,
                                                  expected_before: str | None,
                                                  ) -> dict:
    """body paragraph 분할 — caret 위치에서 두 paragraph 로 split.

    원 paragraph_elem 은 앞쪽 paragraph 가 되고 (id 유지), 신규 hp:p
    element 가 그 뒤에 삽입된다.

    returns: {"status": "OK", ...} 또는 {"status": REASON, ...}
    """
    import xml.etree.ElementTree as _ET
    import copy as _copy

    full_text = paragraph_text(paragraph_elem)
    if caret_offset < 0 or caret_offset > len(full_text):
        return {"status": REASON_RANGE_OUT_OF_BOUNDS,
                          "caretOffset": caret_offset,
                          "paragraphLen": len(full_text)}
    if expected_before is not None and full_text != expected_before:
        return {"status": REASON_EXPECTED_BEFORE_MISMATCH,
                          "current": full_text,
                          "expected": expected_before}
    if _paragraph_has_section_break(paragraph_elem):
        return {"status": REASON_SECTION_BOUNDARY_NOT_SUPPORTED}
    if _paragraph_has_inline_list(paragraph_elem):
        return {"status": REASON_LIST_ITEM_NOT_SUPPORTED}

    # parent 탐색 (section root 의 직계 또는 그 아래 wrapper)
    parent = _find_parent(section_root, paragraph_elem)
    if parent is None:
        return {"status": REASON_PARENT_NOT_FOUND}

    # run 별로 위치 매핑
    runs_in_para = [c for c in list(paragraph_elem)
                                    if _local_tag(c) == "run"]
    run_spans: list[tuple] = []  # (run_elem, start, end, text)
    pos = 0
    for r in runs_in_para:
        rt = run_text(r)
        run_spans.append((r, pos, pos + len(rt), rt))
        pos += len(rt)

    # 신규 paragraph element 구성
    new_para = _ET.Element(paragraph_elem.tag,
                                                      dict(paragraph_elem.attrib))
    new_para.set("id", new_paragraph_id)
    if new_par_pr_idref is not None:
        new_para.set("paraPrIDRef", new_par_pr_idref)

    # 신규 paragraph 의 child = caret 우측 run 들
    has_after_run = False
    for r_elem, r_start, r_end, r_text in run_spans:
        if r_end <= caret_offset:
            continue  # 이 run 은 앞쪽 paragraph 전속
        if r_start >= caret_offset:
            # 이 run 전체를 신규 paragraph 로 옮김 (deepcopy)
            new_run = _copy.deepcopy(r_elem)
            new_para.append(new_run)
            has_after_run = True
        else:
            # caret 가 이 run 을 분할
            local_off = caret_offset - r_start
            new_run = _copy.deepcopy(r_elem)
            _set_run_first_t_text(new_run, r_text[local_off:])
            new_para.append(new_run)
            has_after_run = True

    if not has_after_run:
        # caret == paragraph 끝 — 신규 paragraph 는 빈 run 1개
        empty_run = _ET.SubElement(new_para, f"{{{_HP_NS}}}run")
        if new_char_pr_idref is not None:
            empty_run.set("charPrIDRef", new_char_pr_idref)
        _ET.SubElement(empty_run, f"{{{_HP_NS}}}t")

    # 원 paragraph 변형 — caret 좌측만 남김
    has_before_run = False
    new_orig_children: list = []
    for child in list(paragraph_elem):
        if _local_tag(child) != "run":
            new_orig_children.append(child)
            continue
        # 이 run 의 span 찾기
        span = next((s for s in run_spans if s[0] is child), None)
        if span is None:
            new_orig_children.append(child)
            continue
        _r, r_start, r_end, r_text = span
        if r_end <= caret_offset:
            new_orig_children.append(child)
            has_before_run = True
        elif r_start >= caret_offset:
            # 우측 run — 원 paragraph 에서 제거
            pass
        else:
            local_off = caret_offset - r_start
            _set_run_first_t_text(child, r_text[:local_off])
            new_orig_children.append(child)
            has_before_run = True

    # paragraph 의 모든 child 를 비우고 new_orig_children 으로 재구성
    for child in list(paragraph_elem):
        paragraph_elem.remove(child)
    for child in new_orig_children:
        paragraph_elem.append(child)

    if not has_before_run:
        # caret == 0 — 원 paragraph 는 빈 run 1개로
        empty_run = _ET.SubElement(paragraph_elem, f"{{{_HP_NS}}}run")
        if new_char_pr_idref is not None:
            empty_run.set("charPrIDRef", new_char_pr_idref)
        _ET.SubElement(empty_run, f"{{{_HP_NS}}}t")

    # 신규 paragraph 를 원 paragraph 바로 뒤에 삽입
    idx = list(parent).index(paragraph_elem)
    parent.insert(idx + 1, new_para)

    return {
        "status": "OK",
        "newParagraphId": new_paragraph_id,
        "newParPrIDRef": new_par_pr_idref,
        "newCharPrIDRef": new_char_pr_idref,
        "beforeText": full_text[:caret_offset],
        "afterText": full_text[caret_offset:],
        "originalParagraphId": paragraph_elem.attrib.get("id"),
    }


def _apply_para_delete(section_root, prev_paragraph_elem,
                                                 current_paragraph_elem, *,
                                                 expected_before: str | None,
                                                 ) -> dict:
    """body paragraph 병합 — current_paragraph_elem 을 prev_paragraph_elem 끝으로 병합.

    current_paragraph_elem 의 run 들을 prev_paragraph_elem 끝에 붙이고
    current_paragraph_elem 을 XML 에서 제거한다.

    returns: {"status": "OK", ...} 또는 {"status": REASON, ...}
    """
    import copy as _copy

    cur_text = paragraph_text(current_paragraph_elem)
    if expected_before is not None and cur_text != expected_before:
        return {"status": REASON_EXPECTED_BEFORE_MISMATCH,
                          "current": cur_text, "expected": expected_before}
    if _paragraph_has_section_break(prev_paragraph_elem):
        return {"status": REASON_SECTION_BOUNDARY_NOT_SUPPORTED}
    if _paragraph_has_inline_list(current_paragraph_elem):
        return {"status": REASON_LIST_ITEM_NOT_SUPPORTED}

    parent = _find_parent(section_root, current_paragraph_elem)
    if parent is None:
        return {"status": REASON_PARENT_NOT_FOUND}

    prev_text = paragraph_text(prev_paragraph_elem)

    # prev 의 마지막 run 이 빈 텍스트면 제거 (split 잔재)
    prev_runs = [c for c in list(prev_paragraph_elem)
                               if _local_tag(c) == "run"]
    if (len(prev_runs) > 1
            and run_text(prev_runs[-1]).strip() == ""
            and run_text(prev_runs[-1]) == ""):
        prev_paragraph_elem.remove(prev_runs[-1])

    # cur 의 run 들을 prev 끝에 deepcopy 로 이식
    cur_runs = [c for c in list(current_paragraph_elem)
                              if _local_tag(c) == "run"]
    first_cur_run_is_empty = (len(cur_runs) >= 1
                              and run_text(cur_runs[0]) == "")
    start_idx = 1 if (first_cur_run_is_empty and len(cur_runs) > 1) else 0
    for r in cur_runs[start_idx:]:
        prev_paragraph_elem.append(_copy.deepcopy(r))

    # current paragraph 를 XML 에서 제거
    parent.remove(current_paragraph_elem)

    return {
        "status": "OK",
        "removedParagraphId": current_paragraph_elem.attrib.get("id"),
        "prevParagraphId": prev_paragraph_elem.attrib.get("id"),
        "prevText": prev_text,
        "curText": cur_text,
        "mergedText": prev_text + cur_text,
    }


def _compute_local_range(paragraph_elem, run_elem, item) -> tuple[
        int, int, str | None]:
    """plan entry 의 rangeStart/rangeEnd 가 paragraph 전체 offset 인지,
    run-local offset 인지 구분해 local (run-내) start/end 와 reason 반환.

    우선 paragraph 전체 offset 으로 간주해 single-run 매칭을 시도. 매칭
    실패 시 multi-run 으로 처리 (reason).
    """
    rs = int(item.get("rangeStart", 0))
    re_ = int(item.get("rangeEnd", 0))
    # paragraph 전체 offset 으로 시도
    located_run, lo_s, lo_e = locate_run_for_paragraph_offset(
        paragraph_elem, rs, re_)
    if located_run is run_elem and lo_s >= 0:
        return lo_s, lo_e, None
    # paragraph offset 으로는 매칭 안 됨 — multi-run 가능성
    if detect_multi_run_range(paragraph_elem, rs, re_):
        return -1, -1, REASON_MULTI_RUN_RANGE_NOT_SUPPORTED
    # run-local offset 으로 해석 (fallback)
    rt = run_text(run_elem)
    if rs < 0 or re_ > len(rt) or re_ < rs:
        return -1, -1, REASON_RANGE_OUT_OF_BOUNDS
    return rs, re_, None


def apply_paragraph_edits_plan(
    package: HwpxPackage,
    plan_items: list[dict],
    source_document_hash: str | None = None,
    *,
    dry_run: bool = False,
    conflict_cells: set[tuple[int, int, int]] | None = None,
) -> dict[str, Any]:
    """paragraph_edits plan 적용.

    Parameters
    ----------
    package : HwpxPackage (mutation 대상)
    plan_items : paragraph_edits 항목 list
    source_document_hash : 일관성 검증용 (각 item.sourceDocumentHash 와 비교).
        None 이면 검사 생략.
    dry_run : True 면 검증만, mutation 0.
    conflict_cells : set_cells 와 같은 (table,row,col) 충돌 검사용.
    """
    applied: list[dict] = []
    rejected: list[dict] = []
    touched_entries: set[str] = set()
    conflict_cells = conflict_cells or set()

    for item in plan_items:
        if not isinstance(item, dict):
            rejected.append({"reason": "INVALID_ITEM"})
            continue

        ct = item.get("commandType")
        if ct not in _SUPPORTED_COMMAND_TYPES:
            rejected.append(_reject(item,
                                    REASON_UNSUPPORTED_COMMAND_TYPE,
                                    commandType=ct))
            continue

        if (source_document_hash is not None
                and item.get("sourceDocumentHash") not in
                (None, source_document_hash)):
            rejected.append(_reject(item, REASON_SOURCE_HASH_MISMATCH,
                                    itemHash=item.get(
                                        "sourceDocumentHash"),
                                    sourceHash=source_document_hash))
            continue

        scope = item.get("containerScope") or {}
        kind = scope.get("kind")
        if not kind:
            rejected.append(_reject(item, REASON_SCOPE_MISSING))
            continue
        if kind not in ("cell", "block", "header", "footer"):
            rejected.append(_reject(item, REASON_SCOPE_MISSING,
                                    kind=kind))
            continue

        if kind == "cell":
            try:
                table_idx = int(scope["tableIndex"])
                row_idx = int(scope["rowIndex"])
                col_idx = int(scope["colIndex"])
                para_idx = int(scope["paragraphIndex"])
            except (KeyError, ValueError, TypeError) as e:
                rejected.append(_reject(item, REASON_SCOPE_MISSING,
                                        detail=str(e)))
                continue
            if (table_idx, row_idx, col_idx) in conflict_cells:
                rejected.append(_reject(item,
                                        REASON_CELL_COORD_CONFLICT,
                                        table=table_idx, row=row_idx,
                                        col=col_idx))
                continue
            resolved, err = _resolve_cell(package, table_idx, row_idx,
                                          col_idx)
            if err is not None:
                rejected.append(_reject(item, err,
                                        table=table_idx, row=row_idx,
                                        col=col_idx))
                continue
            entry, root, cell_elem = resolved
            paragraph_elem = find_paragraph_in_cell(cell_elem,
                                                      para_idx)
            if paragraph_elem is None:
                rejected.append(_reject(item,
                                        REASON_PARAGRAPH_NOT_FOUND,
                                        paragraphIndex=para_idx))
                continue
        elif kind in ("header", "footer"):
            # CLAUDE.md §4.2 — 머리말/꼬리말 안 문단 텍스트 편집.
            try:
                sec_idx = int(scope["sectionIndex"])
                object_id = str(scope["objectId"])
                para_idx = int(scope["paragraphIndex"])
            except (KeyError, ValueError, TypeError) as e:
                rejected.append(_reject(item, REASON_SCOPE_MISSING,
                                        detail=str(e)))
                continue
            resolved, err = _resolve_header_footer_paragraph(
                package, sec_idx, kind, object_id, para_idx)
            if err is not None:
                rejected.append(_reject(item, err,
                                        sectionIndex=sec_idx,
                                        objectId=object_id,
                                        paragraphIndex=para_idx))
                continue
            entry, root, paragraph_elem = resolved
        else:
            # WEB-OFFICE-BODY-PARAGRAPH-WRITER-01 — body paragraph 경로.
            try:
                sec_idx = int(scope["sectionIndex"])
                blk_idx = int(scope["blockIndex"])
            except (KeyError, ValueError, TypeError) as e:
                rejected.append(_reject(item, REASON_SCOPE_MISSING,
                                        detail=str(e)))
                continue
            resolved, err = _resolve_body_paragraph(
                package, sec_idx, blk_idx)
            if err is not None:
                rejected.append(_reject(item, err,
                                        sectionIndex=sec_idx,
                                        blockIndex=blk_idx))
                continue
            entry, root, paragraph_elem = resolved

        # WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-INSERT-01: PARA_INSERT 분기.
        # run_idx 해석 없이 paragraph 자체를 분할한다. cell scope 는 1차
        # reject — body scope 한정.
        if ct == "PARA_INSERT":
            if kind != "block":
                rejected.append(_reject(item,
                              REASON_PARA_INSERT_CELL_SCOPE_NOT_SUPPORTED,
                              kind=kind))
                continue
            caret_offset = item.get("caretOffset")
            if caret_offset is None:
                rejected.append(_reject(item, REASON_SCOPE_MISSING,
                              detail="PARA_INSERT requires caretOffset"))
                continue
            try:
                caret_offset = int(caret_offset)
            except (TypeError, ValueError):
                rejected.append(_reject(item, REASON_RANGE_OUT_OF_BOUNDS,
                              caretOffset=caret_offset))
                continue
            # newParagraphId 는 호출자가 미지정 시 max+1 자동 발급
            new_pid = item.get("newParagraphId")
            if not new_pid:
                new_pid = _allocate_new_paragraph_id(root)
            new_parpr = item.get("newParPrIDRef") \
                                  or paragraph_elem.attrib.get("paraPrIDRef")
            new_charpr = item.get("newCharPrIDRef")
            expected_before = item.get("expectedBefore")
            if dry_run:
                applied.append({
                    "commandId": item.get("commandId"),
                    "paragraphId": item.get("paragraphId"),
                    "commandType": ct,
                    "caretOffset": caret_offset,
                    "newParagraphId": new_pid,
                    "newParPrIDRef": new_parpr,
                    "newCharPrIDRef": new_charpr,
                    "containerScope": scope,
                    "paraStructIntegrity": True,
                    "dryRun": True,
                })
                continue
            mut = _apply_para_insert(
                root, paragraph_elem,
                caret_offset=caret_offset,
                new_paragraph_id=new_pid,
                new_par_pr_idref=new_parpr,
                new_char_pr_idref=new_charpr,
                expected_before=expected_before)
            if mut["status"] != "OK":
                rejected.append(_reject(item, mut["status"], **{
                              k: v for k, v in mut.items() if k != "status"}))
                continue
            package.write_xml(entry, root)
            touched_entries.add(entry)
            applied.append({
                "commandId": item.get("commandId"),
                "paragraphId": item.get("paragraphId"),
                "commandType": ct,
                "caretOffset": caret_offset,
                "newParagraphId": mut["newParagraphId"],
                "newParPrIDRef": mut["newParPrIDRef"],
                "newCharPrIDRef": mut["newCharPrIDRef"],
                "beforeText": mut["beforeText"],
                "afterText": mut["afterText"],
                "applyCharPrIDRef": mut["newCharPrIDRef"],
                "paraPrIDRef":
                    paragraph_elem.attrib.get("paraPrIDRef"),
                "containerScope": scope,
                "entry": entry,
                "paraStructIntegrity": True,
                "dryRun": False,
            })
            continue

        # WEB-OFFICE-PARA-EDIT-STRUCTURE-PARA-DELETE-01: PARA_DELETE 분기.
        if ct == "PARA_DELETE":
            if kind != "block":
                rejected.append(_reject(item,
                              REASON_PARA_DELETE_CELL_SCOPE_NOT_SUPPORTED,
                              kind=kind))
                continue
            prev_pid = item.get("prevParagraphId")
            if not prev_pid:
                rejected.append(_reject(item, REASON_SCOPE_MISSING,
                              detail="PARA_DELETE requires prevParagraphId"))
                continue
            # prev paragraph element 탐색
            prev_elem = None
            for child in _iter_paragraphs(root):
                if child.attrib.get("id") == prev_pid:
                    prev_elem = child
                    break
            if prev_elem is None:
                rejected.append(_reject(item, REASON_NO_PREV_PARAGRAPH,
                              prevParagraphId=prev_pid))
                continue
            expected_before = item.get("expectedBefore")
            if dry_run:
                applied.append({
                    "commandId": item.get("commandId"),
                    "paragraphId": item.get("paragraphId"),
                    "commandType": ct,
                    "prevParagraphId": prev_pid,
                    "containerScope": scope,
                    "paraStructIntegrity": True,
                    "dryRun": True,
                })
                continue
            mut = _apply_para_delete(
                root, prev_elem, paragraph_elem,
                expected_before=expected_before)
            if mut["status"] != "OK":
                rejected.append(_reject(item, mut["status"], **{
                              k: v for k, v in mut.items() if k != "status"}))
                continue
            package.write_xml(entry, root)
            touched_entries.add(entry)
            applied.append({
                "commandId": item.get("commandId"),
                "paragraphId": item.get("paragraphId"),
                "commandType": ct,
                "prevParagraphId": prev_pid,
                "removedParagraphId": mut["removedParagraphId"],
                "mergedText": mut["mergedText"],
                "paraPrIDRef": prev_elem.attrib.get("paraPrIDRef"),
                "containerScope": scope,
                "entry": entry,
                "paraStructIntegrity": True,
                "dryRun": False,
            })
            continue

        # run_index 결정 — scope.runIndex 가 있으면 그 값, 없으면 0
        run_idx = int(scope.get("runIndex", 0) or 0)
        run_elem = find_run_in_paragraph(paragraph_elem, run_idx)
        if run_elem is None:
            rejected.append(_reject(item, REASON_RUN_NOT_FOUND,
                                    runIndex=run_idx))
            continue

        # multi-run cross detection (paragraph offset 기준)
        rs_raw = int(item.get("rangeStart", 0))
        re_raw = int(item.get("rangeEnd", 0))
        para_full = paragraph_text(paragraph_elem)
        if rs_raw < 0 or re_raw > len(para_full) or re_raw < rs_raw:
            # 혹시 run-local offset 일 수도 있으니 마지막에 검사
            rt = run_text(run_elem)
            if not (0 <= rs_raw <= re_raw <= len(rt)):
                rejected.append(_reject(item,
                                        REASON_RANGE_OUT_OF_BOUNDS,
                                        rangeStart=rs_raw,
                                        rangeEnd=re_raw,
                                        paragraphLen=len(para_full),
                                        runLen=len(rt)))
                continue

        # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01:
        # APPLY_FORMAT 은 paragraph.text 무변경 + 선택 range run 의
        # charPrIDRef 를 targetCharPrIDRef (header.xml 에 이미 존재하는
        # id) 로 교체. 신규 charPr / header.xml mutation 일절 없음.
        if ct == "APPLY_FORMAT":
            target_pr_raw = item.get("targetCharPrIDRef")
            if (target_pr_raw is None
                    or str(target_pr_raw) == ""):
                rejected.append(_reject(
                    item, REASON_TARGET_CHARPR_NOT_IN_HEADER,
                    targetCharPrIDRef=target_pr_raw))
                continue
            target_pr = str(target_pr_raw)
            header_ids = _read_header_char_pr_ids(package)
            if target_pr not in header_ids:
                rejected.append(_reject(
                    item, REASON_TARGET_CHARPR_NOT_IN_HEADER,
                    targetCharPrIDRef=target_pr))
                continue
            if rs_raw == re_raw:
                rejected.append(_reject(item, REASON_EMPTY_RANGE,
                                        rangeStart=rs_raw,
                                        rangeEnd=re_raw))
                continue
            expected_before = item.get("expectedBefore")
            para_slice = para_full[rs_raw:re_raw]
            if (expected_before is not None
                    and para_slice != expected_before):
                rejected.append(_reject(
                    item, REASON_EXPECTED_BEFORE_MISMATCH,
                    sliceBefore=para_slice,
                    expectedBefore=expected_before))
                continue
            if dry_run:
                applied.append({
                    "commandId": item.get("commandId"),
                    "paragraphId": item.get("paragraphId"),
                    "runId": item.get("runId"),
                    "rangeStart": rs_raw,
                    "rangeEnd": re_raw,
                    "afterText": para_slice,
                    "charPrIDRef": target_pr,
                    "applyCharPrIDRef": target_pr,
                    "targetCharPrIDRef": target_pr,
                    "commandType": ct,
                    "paraPrIDRef":
                        paragraph_elem.attrib.get("paraPrIDRef"),
                    "containerScope": scope,
                    "applyFormatExistingCharPr": True,
                    "dryRun": True,
                })
                continue
            af = apply_charpr_to_range_existing(
                paragraph_elem, rs_raw, re_raw, target_pr,
                header_char_pr_ids=header_ids,
                expected_before=para_slice)
            af_status = af.get("status")
            if af_status != STATUS_OK:
                mapping = {
                    STATUS_UNSAFE_RUN_CHILDREN:
                        REASON_UNSAFE_RUN_CHILDREN,
                    STATUS_NEW_CHARPR_INTRODUCED:
                        REASON_NEW_CHARPR_INTRODUCED,
                    STATUS_RUN_SPAN_NOT_FOUND:
                        REASON_RUN_NOT_FOUND,
                    STATUS_EXPECTED_BEFORE_MISMATCH:
                        REASON_EXPECTED_BEFORE_MISMATCH,
                    STATUS_RANGE_OUT_OF_BOUNDS:
                        REASON_RANGE_OUT_OF_BOUNDS,
                    STATUS_RUN_TEXT_NODE_MISSING:
                        "RUN_TEXT_NODE_MISSING",
                    STATUS_TARGET_CHARPR_NOT_IN_HEADER:
                        REASON_TARGET_CHARPR_NOT_IN_HEADER,
                    STATUS_EMPTY_RANGE: REASON_EMPTY_RANGE,
                }
                rejected.append(_reject(
                    item, mapping.get(af_status, af_status),
                    mutation=af))
                continue
            package.write_xml(entry, root)
            touched_entries.add(entry)
            applied.append({
                "commandId": item.get("commandId"),
                "paragraphId": item.get("paragraphId"),
                "runId": item.get("runId"),
                "rangeStart": rs_raw,
                "rangeEnd": re_raw,
                "afterText": para_slice,
                "charPrIDRef": target_pr,
                "applyCharPrIDRef": target_pr,
                "targetCharPrIDRef": target_pr,
                "afterCharPrIDRef": target_pr,
                "beforeCharPrRuns": af.get("beforeSegments"),
                "afterRunCharPrs": af.get("afterRunCharPrs"),
                "affectedRunCount": af.get("affectedRunCount"),
                "commandType": ct,
                "paraPrIDRef": af.get("paraPrIDRef"),
                "containerScope": scope,
                "entry": entry,
                "applyFormatExistingCharPr": True,
                "dryRun": False,
            })
            continue

        # WEB-OFFICE-PARA-FORMAT-01(M2): APPLY_PARA_FORMAT —
        # 문단 요소의 paraPrIDRef 만 기존 header id 로 교체.
        # 텍스트/run 일절 무변경, header.xml 무수정(§4 유지).
        if ct == "APPLY_PARA_FORMAT":
            target_ppr_raw = item.get("targetParaPrIDRef")
            if target_ppr_raw is None or str(target_ppr_raw) == "":
                rejected.append(_reject(
                    item, REASON_TARGET_PARAPR_NOT_IN_HEADER,
                    targetParaPrIDRef=target_ppr_raw))
                continue
            target_ppr = str(target_ppr_raw)
            if target_ppr not in _read_header_para_pr_ids(package):
                rejected.append(_reject(
                    item, REASON_TARGET_PARAPR_NOT_IN_HEADER,
                    targetParaPrIDRef=target_ppr))
                continue
            # 텍스트 불변 검증: expectedBefore 는 문단 전체 텍스트
            expected_before = item.get("expectedBefore")
            if (expected_before is not None
                    and para_full != expected_before):
                rejected.append(_reject(
                    item, REASON_EXPECTED_BEFORE_MISMATCH,
                    sliceBefore=para_full,
                    expectedBefore=expected_before))
                continue
            before_ppr = paragraph_elem.attrib.get("paraPrIDRef")
            if dry_run:
                applied.append({
                    "commandId": item.get("commandId"),
                    "paragraphId": item.get("paragraphId"),
                    "afterText": para_full,
                    "commandType": ct,
                    "beforeParaPrIDRef": before_ppr,
                    "targetParaPrIDRef": target_ppr,
                    "paraPrIDRef": target_ppr,
                    "containerScope": scope,
                    "entry": entry,
                    "applyParaFormatExistingParaPr": True,
                    "dryRun": True,
                })
                continue
            paragraph_elem.set("paraPrIDRef", target_ppr)
            package.write_xml(entry, root)
            touched_entries.add(entry)
            applied.append({
                "commandId": item.get("commandId"),
                "paragraphId": item.get("paragraphId"),
                "afterText": para_full,
                "commandType": ct,
                "beforeParaPrIDRef": before_ppr,
                "targetParaPrIDRef": target_ppr,
                "afterParaPrIDRef": target_ppr,
                "paraPrIDRef": target_ppr,
                "containerScope": scope,
                "entry": entry,
                "applyParaFormatExistingParaPr": True,
                "dryRun": False,
            })
            continue

        # WEB-OFFICE-PARA-EDIT-TYPE-MULTI-RUN-02:
        # TYPE_TEXT point caret 가 scope.runIndex 가 가리키는 run 밖에 있을
        # 때, paragraph offset 으로 caret 가 실제로 속한 run 을 다시 찾아
        # 단일-run insert 경로로 라우팅한다. 신규 primitive 미사용 —
        # apply_text_range_edit 그대로 호출.
        if (ct == "TYPE_TEXT" and rs_raw == re_raw
                and 0 <= rs_raw <= len(para_full)):
            type_target_run, type_local_s, _type_local_e = (
                locate_run_for_paragraph_offset(
                    paragraph_elem, rs_raw, re_raw))
            if (type_target_run is not None
                    and type_target_run is not run_elem):
                expected_before = item.get("expectedBefore")
                if expected_before is None or expected_before != "":
                    rejected.append(_reject(
                        item, REASON_EXPECTED_BEFORE_MISMATCH,
                        sliceBefore="",
                        expectedBefore=expected_before,
                        detail="TYPE_TEXT 는 expectedBefore=='' 필수"))
                    continue
                if not _is_safe_text_run(type_target_run):
                    rejected.append(_reject(
                        item, REASON_UNSAFE_RUN_CHILDREN,
                        rangeStart=rs_raw, rangeEnd=re_raw,
                        detail="target run 은 순수 텍스트 run 이어야 함"))
                    continue
                target_pr = type_target_run.attrib.get("charPrIDRef")
                apply_pr = item.get("applyCharPrIDRef")
                if apply_pr is not None and apply_pr != target_pr:
                    rejected.append(_reject(
                        item, REASON_CHARPR_MISMATCH,
                        applyCharPrIDRef=apply_pr,
                        runCharPrIDRef=target_pr))
                    continue
                after_text = item.get("afterText",
                                                      item.get("insertText", ""))
                if dry_run:
                    applied.append({
                        "commandId": item.get("commandId"),
                        "paragraphId": item.get("paragraphId"),
                        "runId": item.get("runId"),
                        "rangeStart": rs_raw,
                        "rangeEnd": re_raw,
                        "afterText": after_text,
                        "charPrIDRef": target_pr,
                        "applyCharPrIDRef":
                            apply_pr if apply_pr is not None
                            else target_pr,
                        "commandType": ct,
                        "paraPrIDRef":
                            paragraph_elem.attrib.get("paraPrIDRef"),
                        "containerScope": scope,
                        "typeMultiRun": True,
                        "dryRun": True,
                    })
                    continue
                mutation = apply_text_range_edit(
                    paragraph_elem, type_target_run,
                    type_local_s, type_local_s,
                    after_text, expected_before="")
                if mutation["status"] != STATUS_OK:
                    mapping = {
                        STATUS_RUN_TEXT_NODE_MISSING:
                            "RUN_TEXT_NODE_MISSING",
                        STATUS_RANGE_OUT_OF_BOUNDS:
                            REASON_RANGE_OUT_OF_BOUNDS,
                        STATUS_EXPECTED_BEFORE_MISMATCH:
                            REASON_EXPECTED_BEFORE_MISMATCH,
                    }
                    rejected.append(_reject(
                        item,
                        mapping.get(mutation["status"],
                                            mutation["status"]),
                        mutation=mutation))
                    continue
                _fix_lineseg_on_text_edit(
                    paragraph_elem, para_full,
                    para_full[:rs_raw] + after_text + para_full[rs_raw:],
                    context={"sourcePath": str(package.path),
                             "paragraphId": item.get("paragraphId"),
                             "containerScope": scope})
                package.write_xml(entry, root)
                touched_entries.add(entry)
                applied.append({
                    "commandId": item.get("commandId"),
                    "paragraphId": item.get("paragraphId"),
                    "runId": item.get("runId"),
                    "rangeStart": rs_raw,
                    "rangeEnd": re_raw,
                    "afterText": after_text,
                    "charPrIDRef": mutation["charPrIDRef"],
                    "applyCharPrIDRef":
                        apply_pr if apply_pr is not None else target_pr,
                    "commandType": ct,
                    "paraPrIDRef": mutation["paraPrIDRef"],
                    "containerScope": scope,
                    "entry": entry,
                    "typeMultiRun": True,
                    "dryRun": False,
                })
                continue

        if detect_multi_run_range(paragraph_elem, rs_raw, re_raw):
            # paragraph 전체 offset 기준 multi-run. 우선 run-local
            # offset 으로 재해석 가능하면 기존 단일-run 경로 진입.
            rt = run_text(run_elem)
            if 0 <= rs_raw <= re_raw <= len(rt):
                pass  # single-run path 진입 (아래)
            elif ct == "TYPE_TEXT":
                # rs_raw != re_raw 거나 caret 가 paragraph 범위 밖.
                rejected.append(_reject(
                    item,
                    REASON_TYPE_TEXT_MULTI_RUN_NOT_SUPPORTED,
                    rangeStart=rs_raw, rangeEnd=re_raw))
                continue
            else:
                # WEB-OFFICE-PARA-EDIT-MULTI-RUN-01: REPLACE/DELETE
                # multi-run 활성화 경로.
                policy = item.get("policy") or POLICY_ANCHOR_CHARPR
                if policy == POLICY_REQUIRES_REVIEW:
                    rejected.append(_reject(item,
                                            REASON_REQUIRES_REVIEW,
                                            policy=policy))
                    continue
                expected_before = item.get("expectedBefore")
                para_slice = para_full[rs_raw:re_raw]
                if (expected_before is not None
                        and para_slice != expected_before):
                    rejected.append(_reject(
                        item, REASON_EXPECTED_BEFORE_MISMATCH,
                        sliceBefore=para_slice,
                        expectedBefore=expected_before))
                    continue
                after_text = item.get("afterText", "")
                if ct == "DELETE_TEXT_RANGE":
                    after_text = ""
                apply_pr = item.get("applyCharPrIDRef")
                if dry_run:
                    applied.append({
                        "commandId": item.get("commandId"),
                        "paragraphId": item.get("paragraphId"),
                        "runId": item.get("runId"),
                        "rangeStart": rs_raw,
                        "rangeEnd": re_raw,
                        "afterText": after_text,
                        "charPrIDRef": apply_pr,
                        "applyCharPrIDRef": apply_pr,
                        "commandType": ct,
                        "paraPrIDRef":
                            paragraph_elem.attrib.get("paraPrIDRef"),
                        "containerScope": scope,
                        "policy": policy,
                        "multiRun": True,
                        "dryRun": True,
                    })
                    continue
                mr = apply_text_range_edit_multi_run(
                    paragraph_elem, rs_raw, re_raw, after_text,
                    apply_charpr_idref=apply_pr,
                    policy=policy,
                    expected_before=para_slice)
                mr_status = mr.get("status")
                if mr_status != STATUS_OK:
                    mr_reason_map = {
                        STATUS_UNSAFE_RUN_CHILDREN:
                            REASON_UNSAFE_RUN_CHILDREN,
                        STATUS_NEW_CHARPR_INTRODUCED:
                            REASON_NEW_CHARPR_INTRODUCED,
                        STATUS_RUN_SPAN_NOT_FOUND:
                            REASON_RUN_NOT_FOUND,
                        STATUS_EXPECTED_BEFORE_MISMATCH:
                            REASON_EXPECTED_BEFORE_MISMATCH,
                        STATUS_RANGE_OUT_OF_BOUNDS:
                            REASON_RANGE_OUT_OF_BOUNDS,
                        STATUS_RUN_TEXT_NODE_MISSING:
                            "RUN_TEXT_NODE_MISSING",
                        "REQUIRES_REVIEW": REASON_REQUIRES_REVIEW,
                        "SINGLE_RUN_RANGE":
                            REASON_MULTI_RUN_RANGE_NOT_SUPPORTED,
                    }
                    rejected.append(_reject(
                        item, mr_reason_map.get(mr_status, mr_status),
                        mutation=mr))
                    continue
                _fix_lineseg_on_text_edit(
                    paragraph_elem, para_full,
                    para_full[:rs_raw] + after_text + para_full[re_raw:],
                    context={"sourcePath": str(package.path),
                             "paragraphId": item.get("paragraphId"),
                             "containerScope": scope})
                package.write_xml(entry, root)
                touched_entries.add(entry)
                applied.append({
                    "commandId": item.get("commandId"),
                    "paragraphId": item.get("paragraphId"),
                    "runId": item.get("runId"),
                    "rangeStart": rs_raw,
                    "rangeEnd": re_raw,
                    "afterText": after_text,
                    "charPrIDRef": mr.get("appliedCharPrIDRef"),
                    "applyCharPrIDRef": apply_pr,
                    "commandType": ct,
                    "paraPrIDRef": mr.get("paraPrIDRef"),
                    "containerScope": scope,
                    "entry": entry,
                    "policy": policy,
                    "multiRun": True,
                    "removedMiddleRuns":
                        mr.get("removedMiddleRuns"),
                    "dryRun": False,
                })
                continue

        # local range 계산
        local_s, local_e, range_err = _compute_local_range(
            paragraph_elem, run_elem, item)
        if range_err is not None:
            rejected.append(_reject(item, range_err,
                                    rangeStart=rs_raw,
                                    rangeEnd=re_raw))
            continue

        rt = run_text(run_elem)
        slice_before = rt[local_s:local_e]
        expected_before = item.get("expectedBefore")
        if (expected_before is not None
                and slice_before != expected_before):
            rejected.append(_reject(item, REASON_EXPECTED_BEFORE_MISMATCH,
                                    sliceBefore=slice_before,
                                    expectedBefore=expected_before))
            continue

        # charPrIDRef 보존 검증 — applyCharPrIDRef 가 주어지면 run 의
        # 현재 charPrIDRef 와 동일해야 함 (신규 charPr 금지).
        apply_pr = item.get("applyCharPrIDRef")
        run_pr = run_elem.attrib.get("charPrIDRef")
        if apply_pr is not None and apply_pr != run_pr:
            rejected.append(_reject(item, REASON_CHARPR_MISMATCH,
                                    applyCharPrIDRef=apply_pr,
                                    runCharPrIDRef=run_pr))
            continue

        after_text = item.get("afterText", "")
        if ct == "DELETE_TEXT_RANGE":
            after_text = ""

        if dry_run:
            applied.append({
                "commandId": item.get("commandId"),
                "paragraphId": item.get("paragraphId"),
                "runId": item.get("runId"),
                "rangeStart": rs_raw,
                "rangeEnd": re_raw,
                "afterText": after_text,
                "charPrIDRef": run_pr,
                # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 — V4 활성화
                # 트리거: plan item 의 applyCharPrIDRef 를 그대로 기록.
                # 신규 charPr 생성·수정은 일절 없음 (run 의 현재
                # charPrIDRef 와 동일성은 REASON_CHARPR_MISMATCH 게이트
                # 에서 사전 검증됨).
                "applyCharPrIDRef": item.get("applyCharPrIDRef"),
                "commandType": ct,
                "paraPrIDRef": paragraph_elem.attrib.get("paraPrIDRef"),
                "containerScope": scope,
                "dryRun": True,
            })
            continue

        # 본 실행
        mutation = apply_text_range_edit(
            paragraph_elem, run_elem, local_s, local_e, after_text,
            expected_before=slice_before)
        if mutation["status"] != STATUS_OK:
            mapping = {
                STATUS_RUN_TEXT_NODE_MISSING: "RUN_TEXT_NODE_MISSING",
                STATUS_RANGE_OUT_OF_BOUNDS:
                    REASON_RANGE_OUT_OF_BOUNDS,
                STATUS_EXPECTED_BEFORE_MISMATCH:
                    REASON_EXPECTED_BEFORE_MISMATCH,
            }
            rejected.append(_reject(item,
                                    mapping.get(mutation["status"],
                                                mutation["status"]),
                                    mutation=mutation))
            continue
        _fix_lineseg_on_text_edit(
            paragraph_elem, para_full,
            para_full[:rs_raw] + after_text + para_full[re_raw:],
            context={"sourcePath": str(package.path),
                     "paragraphId": item.get("paragraphId"),
                     "containerScope": scope})
        package.write_xml(entry, root)
        touched_entries.add(entry)
        applied.append({
            "commandId": item.get("commandId"),
            "paragraphId": item.get("paragraphId"),
            "runId": item.get("runId"),
            "rangeStart": rs_raw,
            "rangeEnd": re_raw,
            "afterText": after_text,
            "charPrIDRef": mutation["charPrIDRef"],
            # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01 — V4 활성화.
            "applyCharPrIDRef": item.get("applyCharPrIDRef"),
            "commandType": ct,
            "paraPrIDRef": mutation["paraPrIDRef"],
            "containerScope": scope,
            "entry": entry,
            "dryRun": False,
        })

    return {
        "applied": applied,
        "rejected": rejected,
        "operationCount": len(applied) + len(rejected),
        "touchedEntries": sorted(touched_entries),
    }
