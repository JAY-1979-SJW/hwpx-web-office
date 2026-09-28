"""HWPX-EDIT-PLAN-WRITER-EXECUTOR-LIVE-MODE-SANDBOX-01

Writer Executor live mode — **sandbox 사본 한정** 첫 실 writer 호출 모듈.

절대 원칙:
- 원본 fixture는 절대 수정하지 않는다 (sha256 / mtime 무변경 검증).
- output 경로가 원본과 같으면 즉시 차단한다.
- 이번 공정에서 허용된 live operation은 setCellText 1종뿐이다.

처리 흐름:
  WriterCallPlan(READY_FOR_WRITER) + source HWPX + sandbox output path
  → 격리 sandbox 사본 작성
  → 사본에서 cell text만 수정 (charPr/borderFill/run 구조 보존)
  → re-parse하여 readback 검증
  → snapshot 비교로 구조/서식 보존 확인

이 모듈은 사본 파일에 한해 writer를 호출하지만, 원본 파일에 대해서는 절대로
호출하지 않으며 시스템 어디에도 원본을 덮어쓰지 않는다.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import generic_edit_plan_writer_adapter as adapter

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_HH = "http://www.hancom.co.kr/hwpml/2011/head"

# 이번 공정에서 사본에 적용 가능한 live operation type
ALLOWED_LIVE_OPERATION_TYPES: frozenset[str] = frozenset({
    "setCellText",
    "setCellHorizontalAlign",
    "setCellVerticalAlign",
    # HWPX-EDIT-PLAN-WRITER-LIVE-EXPAND-PARAGRAPH-TEXT-01 (section-level paragraphs)
    "setParagraphText",
    "replaceTextRun",
})

# align 허용값 (HWPX convention — 대소문자 무관 입력 허용, 내부 표준화)
ALLOWED_HORIZONTAL_ALIGN_VALUES: frozenset[str] = frozenset({
    "LEFT",
    "CENTER",
    "RIGHT",
    "JUSTIFY",
})
ALLOWED_VERTICAL_ALIGN_VALUES: frozenset[str] = frozenset({
    "TOP",
    "CENTER",
    "BOTTOM",
})

_OVERWRITE_OPS: frozenset[str] = frozenset({
    "setCellText",
    "setParagraphText",
    "setCellHorizontalAlign",
    "setCellVerticalAlign",
    "setCellFillColor",
    "setCellTextStyle",
    "replaceTextRun",
})

# 네임스페이스 prefix 등록 (재직렬화 시 보존)
ET.register_namespace("hp", NS_HP)
ET.register_namespace("hh", NS_HH)


# ── dataclass ────────────────────────────────────────────────────────────────


@dataclass
class AppliedCall:
    commandId: str
    operationId: str
    operationType: str
    writerMethod: str
    target: dict
    valueWritten: Any
    expectedBefore: Any
    actualAfter: Any
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "commandId": self.commandId,
            "operationId": self.operationId,
            "operationType": self.operationType,
            "writerMethod": self.writerMethod,
            "target": self.target,
            "valueWritten": self.valueWritten,
            "expectedBefore": self.expectedBefore,
            "actualAfter": self.actualAfter,
            "note": self.note,
        }


@dataclass
class SkippedCall:
    commandId: str
    operationId: str
    writerMethod: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "commandId": self.commandId,
            "operationId": self.operationId,
            "writerMethod": self.writerMethod,
            "reason": self.reason,
        }


@dataclass
class LiveFinding:
    code: str
    detail: str
    operationId: str | None = None

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail, "operationId": self.operationId}


@dataclass
class ReadbackResult:
    targetCellsVerified: int = 0
    untouchedCellNormalizedTextPreserved: bool = True
    tableCountPreserved: bool = True
    cellCountPreserved: bool = True
    rowSpanSumPreserved: bool = True
    colSpanSumPreserved: bool = True
    objectCountPreserved: bool = True
    binDataCountPreserved: bool = True
    horizontalAlignCountPreserved: bool = True
    verticalAlignCountPreserved: bool = True
    fontNameCountPreserved: bool = True
    fontSizeCountPreserved: bool = True
    textColorCountPreserved: bool = True
    divergences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "targetCellsVerified": self.targetCellsVerified,
            "untouchedCellNormalizedTextPreserved": self.untouchedCellNormalizedTextPreserved,
            "tableCountPreserved": self.tableCountPreserved,
            "cellCountPreserved": self.cellCountPreserved,
            "rowSpanSumPreserved": self.rowSpanSumPreserved,
            "colSpanSumPreserved": self.colSpanSumPreserved,
            "objectCountPreserved": self.objectCountPreserved,
            "binDataCountPreserved": self.binDataCountPreserved,
            "horizontalAlignCountPreserved": self.horizontalAlignCountPreserved,
            "verticalAlignCountPreserved": self.verticalAlignCountPreserved,
            "fontNameCountPreserved": self.fontNameCountPreserved,
            "fontSizeCountPreserved": self.fontSizeCountPreserved,
            "textColorCountPreserved": self.textColorCountPreserved,
            "divergences": self.divergences,
        }


@dataclass
class LiveSandboxResult:
    executorId: str = ""
    planId: str = ""
    verdict: str = "BLOCKED_NOT_READY_FOR_WRITER"
    outputPath: str = ""
    writerCalled: bool = False
    outputCreated: bool = False
    originalUnmodified: bool = True
    appliedCalls: list[AppliedCall] = field(default_factory=list)
    skippedCalls: list[SkippedCall] = field(default_factory=list)
    readback: ReadbackResult = field(default_factory=ReadbackResult)
    safetyFindings: list[LiveFinding] = field(default_factory=list)
    sourceSha256Before: str = ""
    sourceSha256After: str = ""

    def to_dict(self) -> dict:
        return {
            "executorId": self.executorId,
            "planId": self.planId,
            "verdict": self.verdict,
            "outputPath": self.outputPath,
            "writerCalled": self.writerCalled,
            "outputCreated": self.outputCreated,
            "originalUnmodified": self.originalUnmodified,
            "appliedCalls": [a.to_dict() for a in self.appliedCalls],
            "skippedCalls": [s.to_dict() for s in self.skippedCalls],
            "readback": self.readback.to_dict(),
            "safetyFindings": [f.to_dict() for f in self.safetyFindings],
            "sourceSha256Before": self.sourceSha256Before,
            "sourceSha256After": self.sourceSha256After,
        }


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────


def _parser_normalize(text: str) -> str:
    """parser table_parser._normalize와 동일한 정규화 (한글 사이 공백 제거 포함)."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\r\n\t]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", t)
    return t


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_table_id(table_id: str) -> tuple[int, int] | None:
    """t_s{section}_{tableIndex:03d} → (section_index, table_index_in_section)."""
    try:
        parts = table_id.split("_")
        section_idx = int(parts[1][1:])
        table_idx = int(parts[2])
        return section_idx, table_idx
    except (ValueError, IndexError):
        return None


def _section_xml_name_for_index(zip_names: list[str], section_index: int) -> str | None:
    sec_paths = sorted(n for n in zip_names if "section" in n and n.endswith(".xml"))
    if 0 <= section_index < len(sec_paths):
        return sec_paths[section_index]
    return None


# ── paragraph (section-level) helpers ────────────────────────────────────────

_TAG_P = f"{{{NS_HP}}}p"
_TAG_T = f"{{{NS_HP}}}t"
_TAG_RUN = f"{{{NS_HP}}}run"
_TAG_TBL_FULL = f"{{{NS_HP}}}tbl"


def _format_paragraph_key(section_idx: int, paragraph_idx: int) -> str:
    return f"p_s{section_idx}_{paragraph_idx:04d}"


def _parse_paragraph_key(pk: str) -> tuple[int, int] | None:
    """'p_s{section}_{paragraph:04d}' → (section_idx, paragraph_idx)."""
    if not pk or not isinstance(pk, str):
        return None
    parts = pk.split("_")
    if len(parts) != 3 or parts[0] != "p" or not parts[1].startswith("s"):
        return None
    try:
        return int(parts[1][1:]), int(parts[2])
    except (ValueError, IndexError):
        return None


def _resolve_paragraph_target(target: dict) -> tuple[int, int] | None:
    """target dict에서 (section_idx, paragraph_idx) 산출. 우선순위:
    paragraphKey > (sectionIndex + paragraphIndex).
    """
    if not isinstance(target, dict):
        return None
    pk = target.get("paragraphKey")
    if pk:
        parsed = _parse_paragraph_key(pk)
        if parsed is None:
            return None
        return parsed
    sec = target.get("sectionIndex")
    pi = target.get("paragraphIndex")
    if sec is None or pi is None:
        return None
    try:
        return int(sec), int(pi)
    except (ValueError, TypeError):
        return None


def _section_root_top_level_paragraphs(root) -> list:
    """section root의 직접 자식 중 <hp:p>만 순서대로 반환."""
    return [c for c in list(root) if c.tag == _TAG_P]


def _paragraph_visible_text(p_elem) -> str:
    """문단의 visible text 추출. 중첩 tbl 내부는 제외."""
    parts: list[str] = []

    def walk(e):
        if e.tag == _TAG_TBL_FULL:
            return
        if e.tag == _TAG_T and e.text:
            parts.append(e.text)
        for c in list(e):
            walk(c)

    for c in list(p_elem):
        walk(c)
    return "".join(parts)


def _paragraph_text_run_elements(p_elem) -> list:
    """문단 내 (중첩 tbl 제외) <hp:t> 요소 목록."""
    ts: list = []

    def walk(e):
        if e.tag == _TAG_TBL_FULL:
            return
        if e.tag == _TAG_T:
            ts.append(e)
        for c in list(e):
            walk(c)

    for c in list(p_elem):
        walk(c)
    return ts


def _section_paragraph_text_map(section_xml: bytes, section_idx: int) -> dict:
    """section XML에서 {paragraphKey: visibleText} 산출."""
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return {}
    result: dict[str, str] = {}
    for idx, p in enumerate(_section_root_top_level_paragraphs(root)):
        result[_format_paragraph_key(section_idx, idx)] = _paragraph_visible_text(p)
    return result


def _modify_paragraph_text_in_section_xml(
    section_xml: bytes, paragraph_idx: int, new_value: str, expected_before
) -> tuple[bytes, bool, str | None]:
    """setParagraphText 적용. return (xml_bytes, modified, failure_reason)."""
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return section_xml, False, "parse_error"
    paragraphs = _section_root_top_level_paragraphs(root)
    if not 0 <= paragraph_idx < len(paragraphs):
        return section_xml, False, "target_not_found"
    target_p = paragraphs[paragraph_idx]
    current_visible = _paragraph_visible_text(target_p)
    if expected_before is not None:
        if _parser_normalize(current_visible) != _parser_normalize(str(expected_before)):
            return section_xml, False, "expected_before_mismatch"
    ts = _paragraph_text_run_elements(target_p)
    if ts:
        ts[0].text = new_value if new_value is not None else ""
        for t in ts[1:]:
            t.text = ""
    else:
        first_run = target_p.find(_TAG_RUN)
        target_parent = first_run if first_run is not None else target_p
        new_t = ET.SubElement(target_parent, _TAG_T)
        new_t.text = new_value if new_value is not None else ""
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, True, None


def _find_single_text_run_with(ts, find_str: str) -> ET.Element | None:
    for t in ts:
        if t.text and (find_str in t.text):
            if t.text.count(find_str) == 1:
                return t
            return None
    return None


def _replace_text_run_in_section_xml(
    section_xml: bytes, paragraph_idx: int, find_str: str, replace_str: str, expected_before
) -> tuple[bytes, bool, str | None]:
    """replaceTextRun 적용. return (xml_bytes, modified, failure_reason)."""
    if find_str is None or find_str == "":
        return section_xml, False, "invalid_find_text"
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return section_xml, False, "parse_error"
    paragraphs = _section_root_top_level_paragraphs(root)
    if not 0 <= paragraph_idx < len(paragraphs):
        return section_xml, False, "target_not_found"
    target_p = paragraphs[paragraph_idx]
    visible_raw = _paragraph_visible_text(target_p)
    if expected_before is not None:
        if _parser_normalize(visible_raw) != _parser_normalize(str(expected_before)):
            return section_xml, False, "expected_before_mismatch"
    occurrences = visible_raw.count(find_str)
    if occurrences == 0:
        return section_xml, False, "find_text_not_found"
    if occurrences >= 2:
        return section_xml, False, "ambiguous_text_run"
    # 정확히 1회 occurrence — 어느 단일 <hp:t> 안에 있는지 확인
    ts = _paragraph_text_run_elements(target_p)
    target_t = _find_single_text_run_with(ts, find_str)
    if target_t is None:
        # find가 run 경계에 걸쳐 단일 t 내부에 없음
        return section_xml, False, "run_boundary_unsupported"
    replace_value = replace_str if replace_str is not None else ""
    target_t.text = target_t.text.replace(find_str, replace_value, 1)
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, True, None


def _find_cell_element(root, table_index: int, row: int, col: int):
    """root에서 (table_index, row, col) tc 요소를 반환. 없으면 None."""
    tbl_count = 0
    for tbl in root.iter(f"{{{NS_HP}}}tbl"):
        if tbl_count != table_index:
            tbl_count += 1
            continue
        tr_idx = 0
        for tr in list(tbl):
            if tr.tag != f"{{{NS_HP}}}tr":
                continue
            if tr_idx == row:
                tc_idx = 0
                for tc in list(tr):
                    if tc.tag != f"{{{NS_HP}}}tc":
                        continue
                    if tc_idx == col:
                        return tc
                    tc_idx += 1
                return None
            tr_idx += 1
        return None
    return None


def _modify_cell_halign_in_section_xml(
    section_xml: bytes, table_index: int, row: int, col: int, new_value: str
) -> tuple[bytes, bool]:
    """대상 셀의 hAlign 속성을 new_value로 설정 (대문자 정규화).

    parser는 tc[@hAlign] 또는 tc[@horizontalAlign]을 먼저 읽으므로 tc 속성에 직접 기록한다.
    """
    normalized = (new_value or "").strip().upper()
    if normalized not in ALLOWED_HORIZONTAL_ALIGN_VALUES:
        return section_xml, False
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return section_xml, False
    tc = _find_cell_element(root, table_index, row, col)
    if tc is None:
        return section_xml, False
    tc.set("hAlign", normalized)
    # 혼동을 피하기 위해 다른 속성 이름은 그대로 유지 (overwrite 없음)
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, True


def _modify_cell_valign_in_section_xml(
    section_xml: bytes, table_index: int, row: int, col: int, new_value: str
) -> tuple[bytes, bool]:
    """대상 셀의 vertAlign을 new_value로 설정.

    parser 우선순위: <hp:subList vertAlign=...> 가 있으면 그 값. 그 외 tc[@vAlign] 폴백.
    sandbox 사본에서는 subList가 있으면 거기에, 없으면 tc에 기록한다.
    """
    normalized = (new_value or "").strip().upper()
    if normalized not in ALLOWED_VERTICAL_ALIGN_VALUES:
        return section_xml, False
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return section_xml, False
    tc = _find_cell_element(root, table_index, row, col)
    if tc is None:
        return section_xml, False
    sl = tc.find(f"{{{NS_HP}}}subList")
    if sl is not None:
        sl.set("vertAlign", normalized)
    else:
        tc.set("vAlign", normalized)
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, True


def _find_target_cell(tbl: ET.Element, row: int, col: int) -> ET.Element | None:
    tr_idx = 0
    for tr in list(tbl):
        if tr.tag != f"{{{NS_HP}}}tr":
            continue
        if tr_idx == row:
            tc_idx = 0
            for tc in list(tr):
                if tc.tag != f"{{{NS_HP}}}tc":
                    continue
                if tc_idx == col:
                    return tc
                tc_idx += 1
            return None
        tr_idx += 1
    return None


def _apply_cell_text(tc: ET.Element, new_value: str) -> bool:
    t_elements = list(tc.iter(f"{{{NS_HP}}}t"))
    if t_elements:
        t_elements[0].text = new_value
        for t in t_elements[1:]:
            t.text = ""
        return True
    # <hp:t>가 없으면 첫 p>run에 신규 t 삽입
    for p in tc.iter(f"{{{NS_HP}}}p"):
        run = p.find(f"{{{NS_HP}}}run")
        target_parent = run if run is not None else p
        new_t = ET.SubElement(target_parent, f"{{{NS_HP}}}t")
        new_t.text = new_value
        return True
    return False


def _modify_cell_text_in_section_xml(
    section_xml: bytes, table_index: int, row: int, col: int, new_value: str
) -> tuple[bytes, bool]:
    """section XML에서 (table_index, row, col) 셀의 텍스트만 수정.

    구조(charPr/borderFill/run/p) 보존, 첫 번째 <hp:t>에 new_value 기록, 나머지 <hp:t>은 비움.
    return (new_xml_bytes, modified)
    """
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return section_xml, False

    tbl_count = 0
    modified = False
    for tbl in root.iter(f"{{{NS_HP}}}tbl"):
        if tbl_count != table_index:
            tbl_count += 1
            continue
        # 일치 테이블
        tc = _find_target_cell(tbl, row, col)
        if tc is not None:
            modified = _apply_cell_text(tc, new_value)
        break

    if not modified:
        return section_xml, False
    new_bytes = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return new_bytes, True


def _write_sandbox_zip(
    source_path: Path, output_path: Path, section_modifications: dict[str, bytes]
) -> None:
    """원본 zip을 사본으로 복사하되 section_modifications에 있는 항목은 새 바이트로 교체."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source_path, "r") as zin, zipfile.ZipFile(output_path, "w") as zout:
        infos = zin.infolist()
        ordered = sorted(infos, key=lambda i: 0 if i.filename == "mimetype" else 1)
        for info in ordered:
            if info.filename in section_modifications:
                data = section_modifications[info.filename]
            else:
                data = zin.read(info.filename)
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            zout.writestr(new_info, data)


def _snapshot(parser_result, hwpx_path: Path | None = None) -> dict:
    cells = [c for t in parser_result.tables for c in t.cells]
    snap = {
        "tableCount": len(parser_result.tables),
        "cellCount": len(cells),
        "rowSpanSum": sum(c.rowSpan for c in cells),
        "colSpanSum": sum(c.colSpan for c in cells),
        "objectCount": len(getattr(parser_result, "objects", []) or []),
        "binDataCount": len(getattr(parser_result, "binData", []) or []),
        "cells_with_horizontalAlign": sum(1 for c in cells if c.horizontalAlign),
        "cells_with_verticalAlign": sum(1 for c in cells if c.verticalAlign),
        "cells_with_fontName": sum(1 for c in cells if getattr(c, "fontName", None)),
        "cells_with_fontSizePt": sum(1 for c in cells if c.fontSizePt),
        "cells_with_textColor": sum(1 for c in cells if getattr(c, "textColor", None)),
        "cellNormText": {c.cellId: c.normalizedText for c in cells},
        "cellHAlign": {c.cellId: (c.horizontalAlign or "") for c in cells},
        "cellVAlign": {c.cellId: (c.verticalAlign or "") for c in cells},
        "paragraphText": {},
    }
    # 섹션 레벨 paragraphText 맵 (paragraphKey → raw visible text)
    if hwpx_path is not None:
        try:
            with zipfile.ZipFile(hwpx_path) as zf:
                sec_names = sorted(
                    n for n in zf.namelist() if "section" in n and n.endswith(".xml")
                )
                for sec_idx, name in enumerate(sec_names):
                    snap["paragraphText"].update(
                        _section_paragraph_text_map(zf.read(name), sec_idx)
                    )
        except (KeyError, zipfile.BadZipFile, OSError, ET.ParseError):
            pass
    return snap


# ── 메인 함수 ────────────────────────────────────────────────────────────────


def execute_writer_call_plan_live_sandbox(
    writer_call_plan, source_path: Path, sandbox_output_path: Path
) -> LiveSandboxResult:
    """sandbox 사본에 한해 writerCallPlan을 실제 적용한다.

    원본 파일은 절대 수정되지 않는다 (sha256/mtime 검증).
    setCellText 외 operation은 이번 공정에서 차단된다.
    """
    wcp = (
        writer_call_plan.to_dict()
        if hasattr(writer_call_plan, "to_dict")
        else dict(writer_call_plan or {})
    )
    source_path = Path(source_path)
    sandbox_output_path = Path(sandbox_output_path)
    plan_id = wcp.get("planId", "")

    result = LiveSandboxResult(
        executorId=str(uuid.uuid4()),
        planId=plan_id,
        outputPath=str(sandbox_output_path).replace("\\", "/"),
    )

    # 1) 원본 sha256 기록 (변경 검증용)
    if not source_path.exists():
        result.verdict = "BLOCKED_NOT_READY_FOR_WRITER"
        result.safetyFindings.append(
            LiveFinding(
                "SOURCE_NOT_FOUND",
                f"source={source_path}",
            )
        )
        return result
    source_sha_before = _sha256(source_path)
    source_mtime_before = source_path.stat().st_mtime
    result.sourceSha256Before = source_sha_before

    # 2) sandbox path가 원본을 덮어쓰면 즉시 차단
    try:
        same_path = source_path.resolve() == sandbox_output_path.resolve()
    except OSError:
        same_path = str(source_path) == str(sandbox_output_path)
    if same_path:
        result.verdict = "BLOCKED_UNSAFE_OUTPUT_PATH"
        result.safetyFindings.append(
            LiveFinding(
                "OUTPUT_OVERWRITES_SOURCE",
                f"sandbox output path equals source path={source_path}",
            )
        )
        result.sourceSha256After = _sha256(source_path)
        result.originalUnmodified = result.sourceSha256After == source_sha_before
        return result

    # 3) adapter readiness
    if not wcp.get("readyForWriter") or wcp.get("verdict") != "READY_FOR_WRITER":
        result.verdict = "BLOCKED_NOT_READY_FOR_WRITER"
        result.safetyFindings.append(
            LiveFinding(
                "ADAPTER_NOT_READY",
                f"writer adapter verdict={wcp.get('verdict')!r} "
                f"readyForWriter={wcp.get('readyForWriter')}",
            )
        )
        result.sourceSha256After = _sha256(source_path)
        result.originalUnmodified = result.sourceSha256After == source_sha_before
        return result

    calls = wcp.get("writerCalls", []) or []
    if not calls:
        result.verdict = "BLOCKED_NOT_READY_FOR_WRITER"
        result.safetyFindings.append(
            LiveFinding(
                "NO_WRITER_CALLS",
                "writerCalls is empty",
            )
        )
        result.sourceSha256After = _sha256(source_path)
        result.originalUnmodified = result.sourceSha256After == source_sha_before
        return result

    # 4) 각 call 검증 + setCellText만 적용 후보로 분리
    valid_methods = set(adapter.OPERATION_TO_WRITER_METHOD.values())
    fatal_verdict: str | None = None
    accepted_calls: list[dict] = []

    for raw in calls:
        c = raw if isinstance(raw, dict) else (raw.to_dict() if hasattr(raw, "to_dict") else {})
        cmd_id = c.get("commandId", "")
        op_id = c.get("operationId", "")
        method = c.get("writerMethod", "")
        op_type = c.get("operationType", "")

        if method not in valid_methods:
            result.skippedCalls.append(
                SkippedCall(
                    cmd_id,
                    op_id,
                    method,
                    "writer_method_not_whitelisted",
                )
            )
            result.safetyFindings.append(
                LiveFinding(
                    "WRITER_METHOD_NOT_WHITELISTED",
                    f"writerMethod={method!r}",
                    op_id,
                )
            )
            fatal_verdict = fatal_verdict or "BLOCKED_UNSAFE_WRITER_METHOD"
            continue

        if op_type in _OVERWRITE_OPS and "expectedBefore" not in c:
            result.skippedCalls.append(
                SkippedCall(
                    cmd_id,
                    op_id,
                    method,
                    "expected_before_missing",
                )
            )
            result.safetyFindings.append(
                LiveFinding(
                    "EXPECTED_BEFORE_MISSING",
                    "",
                    op_id,
                )
            )
            fatal_verdict = fatal_verdict or "BLOCKED_EXPECTED_BEFORE_MISSING"
            continue

        if not c.get("sourceDocumentHash"):
            result.skippedCalls.append(
                SkippedCall(
                    cmd_id,
                    op_id,
                    method,
                    "source_document_hash_missing",
                )
            )
            result.safetyFindings.append(
                LiveFinding(
                    "SOURCE_HASH_MISSING",
                    "",
                    op_id,
                )
            )
            fatal_verdict = fatal_verdict or "BLOCKED_SOURCE_HASH_MISSING"
            continue

        if op_type not in ALLOWED_LIVE_OPERATION_TYPES:
            result.skippedCalls.append(
                SkippedCall(
                    cmd_id,
                    op_id,
                    method,
                    "unsupported_live_operation",
                )
            )
            result.safetyFindings.append(
                LiveFinding(
                    "UNSUPPORTED_LIVE_OPERATION",
                    f"operationType={op_type!r} not in {sorted(ALLOWED_LIVE_OPERATION_TYPES)}",
                    op_id,
                )
            )
            fatal_verdict = fatal_verdict or "BLOCKED_UNSUPPORTED_LIVE_OPERATION"
            continue

        accepted_calls.append(c)

    if fatal_verdict and not accepted_calls:
        result.verdict = fatal_verdict
        result.sourceSha256After = _sha256(source_path)
        result.originalUnmodified = result.sourceSha256After == source_sha_before
        return result

    # 5) 사본 작성: section 단위 수정 누적
    # source zip의 entry 목록과 section 매핑 파악
    with zipfile.ZipFile(source_path) as zf:
        zip_names = zf.namelist()
        section_xml_bytes_by_name: dict[str, bytes] = {}
        for name in zip_names:
            if "section" in name and name.endswith(".xml"):
                section_xml_bytes_by_name[name] = zf.read(name)

    section_modifications: dict[str, bytes] = {}
    applied_with_target_info: list[tuple[dict, str]] = []  # (call, section_name)

    _PARAGRAPH_OP_TYPES = {"setParagraphText", "replaceTextRun"}
    _PARAGRAPH_FAILURE_TO_VERDICT = {
        "expected_before_mismatch": "BLOCKED_EXPECTED_BEFORE_MISMATCH",
        "target_not_found": "BLOCKED_TARGET_NOT_FOUND",
        "find_text_not_found": "BLOCKED_FIND_TEXT_NOT_FOUND",
        "ambiguous_text_run": "BLOCKED_AMBIGUOUS_TEXT_RUN",
        "run_boundary_unsupported": "BLOCKED_RUN_BOUNDARY_UNSUPPORTED",
        "invalid_find_text": "BLOCKED_INVALID_FIND_TEXT",
    }
    _PARAGRAPH_FAILURE_TO_FINDING = {
        "expected_before_mismatch": "EXPECTED_BEFORE_MISMATCH",
        "target_not_found": "TARGET_NOT_FOUND",
        "find_text_not_found": "FIND_TEXT_NOT_FOUND",
        "ambiguous_text_run": "AMBIGUOUS_TEXT_RUN",
        "run_boundary_unsupported": "RUN_BOUNDARY_UNSUPPORTED",
        "invalid_find_text": "INVALID_FIND_TEXT",
    }

    for c in accepted_calls:
        target = c.get("target") or {}
        new_value = c.get("value")
        op_type = c.get("operationType", "")

        # ── paragraph ops 분기 ────────────────────────────────────────────────
        if op_type in _PARAGRAPH_OP_TYPES:
            resolved = _resolve_paragraph_target(target)
            if resolved is None:
                result.skippedCalls.append(
                    SkippedCall(
                        c.get("commandId", ""),
                        c.get("operationId", ""),
                        c.get("writerMethod", ""),
                        "paragraph_target_unparseable",
                    )
                )
                result.safetyFindings.append(
                    LiveFinding(
                        "TARGET_NOT_FOUND",
                        "paragraph target lacks paragraphKey or (sectionIndex+paragraphIndex)",
                        c.get("operationId", ""),
                    )
                )
                fatal_verdict = fatal_verdict or "BLOCKED_TARGET_NOT_FOUND"
                continue
            section_idx, paragraph_idx = resolved
            section_name = _section_xml_name_for_index(zip_names, section_idx)
            if section_name is None:
                result.skippedCalls.append(
                    SkippedCall(
                        c.get("commandId", ""),
                        c.get("operationId", ""),
                        c.get("writerMethod", ""),
                        "section_not_found",
                    )
                )
                fatal_verdict = fatal_verdict or "BLOCKED_TARGET_NOT_FOUND"
                continue
            current_xml = section_modifications.get(section_name) or section_xml_bytes_by_name.get(
                section_name, b""
            )
            if op_type == "setParagraphText":
                new_xml, modified, failure = _modify_paragraph_text_in_section_xml(
                    current_xml,
                    paragraph_idx,
                    str(new_value) if new_value is not None else "",
                    c.get("expectedBefore"),
                )
            else:  # replaceTextRun
                # find/replace는 op 상단 또는 op.value(dict)에서 추출
                val_dict = c.get("value") if isinstance(c.get("value"), dict) else {}
                find_str = c.get("find")
                if find_str is None:
                    find_str = val_dict.get("find") if isinstance(val_dict, dict) else None
                replace_str = c.get("replace")
                if replace_str is None:
                    replace_str = val_dict.get("replace") if isinstance(val_dict, dict) else None
                new_xml, modified, failure = _replace_text_run_in_section_xml(
                    current_xml,
                    paragraph_idx,
                    find_str,
                    replace_str,
                    c.get("expectedBefore"),
                )
            if failure:
                result.skippedCalls.append(
                    SkippedCall(
                        c.get("commandId", ""),
                        c.get("operationId", ""),
                        c.get("writerMethod", ""),
                        failure,
                    )
                )
                result.safetyFindings.append(
                    LiveFinding(
                        _PARAGRAPH_FAILURE_TO_FINDING.get(failure, failure.upper()),
                        f"operationType={op_type!r} reason={failure}",
                        c.get("operationId", ""),
                    )
                )
                fatal_verdict = fatal_verdict or _PARAGRAPH_FAILURE_TO_VERDICT.get(
                    failure, "BLOCKED_NOT_READY_FOR_WRITER"
                )
                continue
            if not modified:
                result.skippedCalls.append(
                    SkippedCall(
                        c.get("commandId", ""),
                        c.get("operationId", ""),
                        c.get("writerMethod", ""),
                        "paragraph_not_modified",
                    )
                )
                continue
            section_modifications[section_name] = new_xml
            applied_with_target_info.append((c, section_name))
            continue

        # ── cell ops 분기 (기존 로직) ────────────────────────────────────────
        table_id = target.get("tableId", "")
        row = target.get("row")
        col = target.get("col")
        parsed = _parse_table_id(table_id)
        if parsed is None or row is None or col is None:
            result.skippedCalls.append(
                SkippedCall(
                    c.get("commandId", ""),
                    c.get("operationId", ""),
                    c.get("writerMethod", ""),
                    "target_unparseable",
                )
            )
            continue
        section_idx, table_idx = parsed
        section_name = _section_xml_name_for_index(zip_names, section_idx)
        if section_name is None:
            result.skippedCalls.append(
                SkippedCall(
                    c.get("commandId", ""),
                    c.get("operationId", ""),
                    c.get("writerMethod", ""),
                    "section_not_found",
                )
            )
            continue

        current_xml = section_modifications.get(section_name) or section_xml_bytes_by_name.get(
            section_name, b""
        )
        if op_type == "setCellText":
            new_xml, modified = _modify_cell_text_in_section_xml(
                current_xml,
                table_idx,
                row,
                col,
                str(new_value or ""),
            )
            invalid_align = False
        elif op_type == "setCellHorizontalAlign":
            normalized = str(new_value or "").strip().upper()
            invalid_align = normalized not in ALLOWED_HORIZONTAL_ALIGN_VALUES
            if invalid_align:
                modified = False
                new_xml = current_xml
            else:
                new_xml, modified = _modify_cell_halign_in_section_xml(
                    current_xml,
                    table_idx,
                    row,
                    col,
                    normalized,
                )
        elif op_type == "setCellVerticalAlign":
            normalized = str(new_value or "").strip().upper()
            invalid_align = normalized not in ALLOWED_VERTICAL_ALIGN_VALUES
            if invalid_align:
                modified = False
                new_xml = current_xml
            else:
                new_xml, modified = _modify_cell_valign_in_section_xml(
                    current_xml,
                    table_idx,
                    row,
                    col,
                    normalized,
                )
        else:
            # 방어선 (ALLOWED_LIVE_OPERATION_TYPES 외 — 위에서 이미 차단되지만 한번 더)
            modified = False
            new_xml = current_xml
            invalid_align = False

        if invalid_align:
            result.skippedCalls.append(
                SkippedCall(
                    c.get("commandId", ""),
                    c.get("operationId", ""),
                    c.get("writerMethod", ""),
                    "invalid_align_value",
                )
            )
            result.safetyFindings.append(
                LiveFinding(
                    "INVALID_ALIGN_VALUE",
                    f"operationType={op_type!r} value={new_value!r}",
                    c.get("operationId", ""),
                )
            )
            fatal_verdict = fatal_verdict or "BLOCKED_INVALID_ALIGN_VALUE"
            continue

        if not modified:
            result.skippedCalls.append(
                SkippedCall(
                    c.get("commandId", ""),
                    c.get("operationId", ""),
                    c.get("writerMethod", ""),
                    "target_cell_not_found_in_section",
                )
            )
            continue
        section_modifications[section_name] = new_xml
        applied_with_target_info.append((c, section_name))

    if not section_modifications:
        # invalid align이 우선 사유면 그것을 verdict로 보고
        result.verdict = fatal_verdict or "BLOCKED_NOT_READY_FOR_WRITER"
        if result.verdict != "BLOCKED_INVALID_ALIGN_VALUE":
            result.safetyFindings.append(
                LiveFinding(
                    "NO_APPLICABLE_CALLS",
                    "no accepted call resulted in a section modification",
                )
            )
        result.sourceSha256After = _sha256(source_path)
        result.originalUnmodified = result.sourceSha256After == source_sha_before
        return result

    # 6) 사본 작성 (이 시점이 유일한 writer 호출 — 사본 경로에 한해)
    _write_sandbox_zip(source_path, sandbox_output_path, section_modifications)
    result.writerCalled = True
    result.outputCreated = sandbox_output_path.exists()

    # 7) 원본 무수정 검증 (즉시)
    source_sha_after = _sha256(source_path)
    source_mtime_after = source_path.stat().st_mtime
    result.sourceSha256After = source_sha_after
    result.originalUnmodified = (
        source_sha_after == source_sha_before and source_mtime_after == source_mtime_before
    )
    if not result.originalUnmodified:
        result.verdict = "FAIL_ORIGINAL_MUTATED"
        result.safetyFindings.append(
            LiveFinding(
                "ORIGINAL_MUTATED",
                f"sha_before={source_sha_before} sha_after={source_sha_after}",
            )
        )
        return result

    # 8) readback: 원본 + 사본 모두 파싱하여 비교
    from ..parser.parser_engine import parse_hwpx_v2

    before = parse_hwpx_v2(source_path)
    after = parse_hwpx_v2(sandbox_output_path)
    snap_before = _snapshot(before, source_path)
    snap_after = _snapshot(after, sandbox_output_path)

    rb = result.readback

    # 8-1) 대상 셀/문단 검증: op_type별로 어떤 속성이 바뀌어야 하는지 분기
    target_cell_ids: set[str] = set()
    target_paragraph_keys: set[str] = set()
    # cell_id → set of "text"/"halign"/"valign" — 그 cell에서 변경이 허용된 속성
    touched_attrs_by_cell: dict[str, set[str]] = {}
    for c, _section_name in applied_with_target_info:
        target = c.get("target") or {}
        op_type = c.get("operationType", "")

        # paragraph ops 처리
        if op_type in {"setParagraphText", "replaceTextRun"}:
            resolved = _resolve_paragraph_target(target)
            if resolved is None:
                continue
            section_idx, paragraph_idx = resolved
            paragraph_key = _format_paragraph_key(section_idx, paragraph_idx)
            target_paragraph_keys.add(paragraph_key)
            actual_after = snap_after["paragraphText"].get(paragraph_key, "")
            if op_type == "setParagraphText":
                new_value = str(c.get("value") or "")
                ok = actual_after == new_value
                value_written = new_value
            else:  # replaceTextRun
                val_dict = c.get("value") if isinstance(c.get("value"), dict) else {}
                find_str = (
                    c.get("find")
                    if c.get("find") is not None
                    else (val_dict.get("find") if isinstance(val_dict, dict) else None)
                )
                replace_str = (
                    c.get("replace")
                    if c.get("replace") is not None
                    else (val_dict.get("replace") if isinstance(val_dict, dict) else "")
                )
                before_raw = snap_before["paragraphText"].get(paragraph_key, "")
                expected_text = before_raw.replace(
                    find_str or "", replace_str if replace_str is not None else "", 1
                )
                ok = actual_after == expected_text
                value_written = {"find": find_str, "replace": replace_str}
            if ok:
                rb.targetCellsVerified += 1
            else:
                rb.divergences.append(
                    f"target_{op_type}_not_applied {paragraph_key}: actual={actual_after!r}"
                )
            result.appliedCalls.append(
                AppliedCall(
                    commandId=c.get("commandId", ""),
                    operationId=c.get("operationId", ""),
                    operationType=op_type,
                    writerMethod=c.get("writerMethod", ""),
                    target=dict(target),
                    valueWritten=value_written,
                    expectedBefore=c.get("expectedBefore"),
                    actualAfter=actual_after,
                    note="sandbox_paragraph_applied",
                )
            )
            continue

        # cell ops
        tid = target.get("tableId")
        row = target.get("row")
        col = target.get("col")
        cell_id = f"{tid}:r{row}:c{col}"
        target_cell_ids.add(cell_id)
        attr_bucket = touched_attrs_by_cell.setdefault(cell_id, set())

        if op_type == "setCellText":
            actual_after = snap_after["cellNormText"].get(cell_id, "")
            normalized_expected = _parser_normalize(str(c.get("value") or ""))
            ok = actual_after == normalized_expected or (
                normalized_expected and normalized_expected in actual_after
            )
            attr_bucket.add("text")
        elif op_type == "setCellHorizontalAlign":
            normalized_expected = str(c.get("value") or "").strip().upper()
            actual_after = snap_after["cellHAlign"].get(cell_id, "")
            ok = actual_after.upper() == normalized_expected
            attr_bucket.add("halign")
        elif op_type == "setCellVerticalAlign":
            normalized_expected = str(c.get("value") or "").strip().upper()
            actual_after = snap_after["cellVAlign"].get(cell_id, "")
            ok = actual_after.upper() == normalized_expected
            attr_bucket.add("valign")
        else:
            actual_after = ""
            ok = False

        if ok:
            rb.targetCellsVerified += 1
        else:
            rb.divergences.append(
                f"target_{op_type}_not_applied {cell_id}: "
                f"expected~{c.get('value')!r}, actual={actual_after!r}"
            )
        result.appliedCalls.append(
            AppliedCall(
                commandId=c.get("commandId", ""),
                operationId=c.get("operationId", ""),
                operationType=op_type,
                writerMethod=c.get("writerMethod", ""),
                target=dict(c.get("target") or {}),
                valueWritten=c.get("value"),
                expectedBefore=c.get("expectedBefore"),
                actualAfter=actual_after,
                note="sandbox_applied",
            )
        )

    # 8-2) 비대상 셀: 3개 속성 (text/halign/valign) 모두 보존
    #      대상 셀: 변경되지 않은 속성은 보존되어야 함
    for cid, text_before in snap_before["cellNormText"].items():
        touched = touched_attrs_by_cell.get(cid, set())
        if "text" not in touched and snap_after["cellNormText"].get(cid) != text_before:
            rb.untouchedCellNormalizedTextPreserved = False
            rb.divergences.append(
                f"non_target_text_changed {cid}: "
                f"before={text_before!r}, after={snap_after['cellNormText'].get(cid)!r}"
            )
        if "halign" not in touched:
            if snap_after["cellHAlign"].get(cid, "") != snap_before["cellHAlign"].get(cid, ""):
                rb.divergences.append(
                    f"non_target_halign_changed {cid}: "
                    f"before={snap_before['cellHAlign'].get(cid)!r}, "
                    f"after={snap_after['cellHAlign'].get(cid)!r}"
                )
        if "valign" not in touched:
            if snap_after["cellVAlign"].get(cid, "") != snap_before["cellVAlign"].get(cid, ""):
                rb.divergences.append(
                    f"non_target_valign_changed {cid}: "
                    f"before={snap_before['cellVAlign'].get(cid)!r}, "
                    f"after={snap_after['cellVAlign'].get(cid)!r}"
                )

    # 8-2b) 비대상 paragraph: 텍스트 보존
    for pkey, text_before in (snap_before.get("paragraphText") or {}).items():
        if pkey in target_paragraph_keys:
            continue
        if (snap_after.get("paragraphText") or {}).get(pkey) != text_before:
            rb.divergences.append(
                f"non_target_paragraph_changed {pkey}: "
                f"before={text_before!r}, "
                f"after={(snap_after.get('paragraphText') or {}).get(pkey)!r}"
            )

    # 8-3) 구조 / 서식 카운터 보존
    def _eq(key: str) -> bool:
        return snap_before[key] == snap_after[key]

    rb.tableCountPreserved = _eq("tableCount")
    rb.cellCountPreserved = _eq("cellCount")
    rb.rowSpanSumPreserved = _eq("rowSpanSum")
    rb.colSpanSumPreserved = _eq("colSpanSum")
    rb.objectCountPreserved = _eq("objectCount")
    rb.binDataCountPreserved = _eq("binDataCount")
    rb.horizontalAlignCountPreserved = _eq("cells_with_horizontalAlign")
    rb.verticalAlignCountPreserved = _eq("cells_with_verticalAlign")
    rb.fontNameCountPreserved = _eq("cells_with_fontName")
    rb.fontSizeCountPreserved = _eq("cells_with_fontSizePt")
    rb.textColorCountPreserved = _eq("cells_with_textColor")
    for k in (
        "tableCount",
        "cellCount",
        "rowSpanSum",
        "colSpanSum",
        "objectCount",
        "binDataCount",
        "cells_with_horizontalAlign",
        "cells_with_verticalAlign",
        "cells_with_fontName",
        "cells_with_fontSizePt",
        "cells_with_textColor",
    ):
        if snap_before[k] != snap_after[k]:
            rb.divergences.append(f"{k} before={snap_before[k]} after={snap_after[k]}")

    # 8-4) 최종 verdict
    if rb.divergences:
        result.verdict = "FAIL_READBACK_MISMATCH"
    else:
        result.verdict = "PASS_LIVE_SANDBOX_APPLIED"
    return result
