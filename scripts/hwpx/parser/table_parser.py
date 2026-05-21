"""HWPX Parser V2 — table parser (read-only).

section XML에서 표/행/셀을 파싱하여 TableInfo 목록을 반환한다.
기존 corpus profiler의 table parsing 로직을 wrapper 수준으로 재구성.
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

from .parser_contract import TableInfo, CellInfo
from .errors import WarnCode

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_TAG_TBL = f"{{{NS_HP}}}tbl"
_TAG_TR = f"{{{NS_HP}}}tr"
_TAG_TC = f"{{{NS_HP}}}tc"
_TAG_T = f"{{{NS_HP}}}t"
_TAG_CELLSPAN = f"{{{NS_HP}}}cellSpan"
_TAG_RUN = f"{{{NS_HP}}}run"
_TAG_P = f"{{{NS_HP}}}p"
_TAG_SUBLIST = f"{{{NS_HP}}}subList"


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\r\n\t]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", t)
    return t


def _cell_raw_text(tc: ET.Element) -> str:
    parts = []
    for elem in tc.iter():
        if elem.tag == _TAG_TBL:
            continue
        if elem.tag == _TAG_T and elem.text:
            parts.append(elem.text)
    return "".join(parts)


def _cell_span(tc: ET.Element) -> tuple[int, int]:
    for child in tc:
        if child.tag == _TAG_CELLSPAN:
            try:
                return (int(child.attrib.get("colSpan", "1")),
                        int(child.attrib.get("rowSpan", "1")))
            except ValueError:
                return 1, 1
    return 1, 1


def _extract_cell_style(tc: ET.Element, style_defs: dict) -> dict:
    """tc 요소에서 스타일 ID 참조와 결정값을 추출."""
    border_fill_id = tc.get("borderFillIDRef", "")
    char_pr_ids = list(dict.fromkeys(
        el.get("charPrIDRef", "") for el in tc.iter(_TAG_RUN)
        if el.get("charPrIDRef")
    ))
    para_pr_ids = list(dict.fromkeys(
        el.get("paraPrIDRef", "") for el in tc.iter(_TAG_P)
        if el.get("paraPrIDRef")
    ))

    fill_color: str | None = None
    font_height: int | None = None
    font_size_pt: float | None = None
    font_face: str | None = None
    font_name: str | None = None
    bold = False
    italic = False
    underline = False
    text_color: str | None = None
    border_summary = ""
    margin_left = margin_right = margin_top = margin_bottom = 0

    border_fill_defs: dict = style_defs.get("borderFill", {})
    char_pr_defs: dict = style_defs.get("charPr", {})
    para_pr_defs: dict = style_defs.get("paraPr", {})

    if border_fill_id and border_fill_id in border_fill_defs:
        bd = border_fill_defs[border_fill_id]
        fill_color = bd.get("fillColor")
        border_summary = bd.get("borderSummary", "")

    if char_pr_ids:
        cpd = char_pr_defs.get(char_pr_ids[0], {})
        font_height = cpd.get("height")
        font_size_pt = cpd.get("fontSizePt")
        font_face = cpd.get("fontFace")
        font_name = cpd.get("fontName")
        tc_color = cpd.get("textColor", "") or ""
        text_color = tc_color or None
        # bold/italic/underline은 셀 내 임의 run에 적용돼 있어도 셀 표시로 노출 (OR aggregate)
        for _cid in char_pr_ids:
            _cpd = char_pr_defs.get(_cid, {})
            if _cpd.get("bold"):
                bold = True
            if _cpd.get("italic"):
                italic = True
            if _cpd.get("underline"):
                underline = True

    para_align: str = ""
    if para_pr_ids:
        ppd = para_pr_defs.get(para_pr_ids[0], {})
        margin_left = ppd.get("marginLeft", 0)
        margin_right = ppd.get("marginRight", 0)
        margin_top = ppd.get("marginTop", 0)
        margin_bottom = ppd.get("marginBottom", 0)
        para_align = ppd.get("align", "") or ""

    h_align = tc.get("hAlign", tc.get("horizontalAlign", ""))
    if not h_align and para_align:
        h_align = para_align
    sl = tc.find(_TAG_SUBLIST)
    v_align = sl.get("vertAlign", "") if sl is not None else tc.get("vAlign", tc.get("verticalAlign", ""))

    return {
        "borderFillIDRef": border_fill_id or None,
        "charPrIDRefs": char_pr_ids,
        "paraPrIDRefs": para_pr_ids,
        "fillColor": fill_color,
        "fontHeight": font_height,
        "fontSizePt": font_size_pt,
        "fontFace": font_face,
        "fontName": font_name,
        "bold": bold,
        "italic": italic,
        "underline": underline,
        "textColor": text_color,
        "horizontalAlign": h_align,
        "verticalAlign": v_align,
        "marginLeft": margin_left,
        "marginRight": margin_right,
        "marginTop": margin_top,
        "marginBottom": margin_bottom,
        "borderSummary": border_summary,
    }


def _has_nested_table(tc: ET.Element) -> bool:
    return any(e.tag == _TAG_TBL for e in tc.iter())


def _cell_paragraphs(tc: ET.Element) -> list[str]:
    paras = []
    for p in tc.iter(f"{{{NS_HP}}}p"):
        texts = [t.text for t in p.iter(_TAG_T) if t.text]
        if texts:
            paras.append("".join(texts))
    return paras


def _parse_table_element(tbl: ET.Element, section_index: int,
                          table_index: int, block_index: int,
                          style_defs: dict | None = None) -> TableInfo:
    _style_defs = style_defs or {}
    table_id = f"t_s{section_index}_{table_index:03d}"
    rows_raw = [c for c in tbl if c.tag == _TAG_TR]

    cells: list[CellInfo] = []
    raw_rows: list[list[ET.Element]] = []
    for tr in rows_raw:
        raw_rows.append([c for c in tr if c.tag == _TAG_TC])

    row_count = len(raw_rows)
    col_count = max((len(r) for r in raw_rows), default=0)
    has_merged = False
    has_nested = False
    nested_count = 0

    for ri, row in enumerate(raw_rows):
        for ci, tc in enumerate(row):
            col_span, row_span = _cell_span(tc)
            if col_span > 1 or row_span > 1:
                has_merged = True
            nested = _has_nested_table(tc)
            if nested:
                has_nested = True
                nested_count += 1
            raw_text = _cell_raw_text(tc)
            norm_text = _normalize(raw_text)
            paras = _cell_paragraphs(tc)
            cell_id = f"{table_id}:r{ri}:c{ci}"
            style = _extract_cell_style(tc, _style_defs)

            # isLikelyLabel: 짧고 비어있지 않은 셀
            is_label = bool(norm_text) and len(norm_text) <= 20 and ci == 0
            # isLikelyInputSlot: 빈 셀 (라벨 오른쪽 첫 번째 후보)
            is_slot = not norm_text and ri > 0

            cells.append(CellInfo(
                cellId=cell_id,
                row=ri,
                col=ci,
                visualRow=ri,
                visualCol=ci,
                rowSpan=row_span,
                colSpan=col_span,
                isMergedOrigin=(col_span > 1 or row_span > 1),
                text=raw_text,
                normalizedText=norm_text,
                paragraphs=paras,
                charPrIDRefs=style["charPrIDRefs"],
                paraPrIDRefs=style["paraPrIDRefs"],
                borderFillIDRef=style["borderFillIDRef"],
                fillColor=style["fillColor"],
                fontHeight=style["fontHeight"],
                fontSizePt=style["fontSizePt"],
                fontFace=style["fontFace"],
                fontName=style["fontName"],
                bold=style["bold"],
                italic=style["italic"],
                underline=style["underline"],
                textColor=style["textColor"],
                horizontalAlign=style["horizontalAlign"],
                verticalAlign=style["verticalAlign"],
                marginLeft=style["marginLeft"],
                marginRight=style["marginRight"],
                marginTop=style["marginTop"],
                marginBottom=style["marginBottom"],
                borderSummary=style["borderSummary"],
                hasNestedTable=nested,
                isLikelyLabel=is_label,
                isLikelyInputSlot=is_slot,
            ))

    # 헤더 행 감지 (row 0 중심)
    header_row_candidates: list[int] = []
    header_texts: list[str] = []
    if raw_rows:
        first_row_cells = [c for c in cells if c.row == 0]
        texts_row0 = [c.normalizedText for c in first_row_cells if c.normalizedText]
        if texts_row0:
            avg_len = sum(len(t) for t in texts_row0) / len(texts_row0)
            # 병합 제목행 건너뜀
            if not (len(texts_row0) <= 2 and avg_len > 15):
                header_row_candidates = [0]
                header_texts = texts_row0

    return TableInfo(
        tableId=table_id,
        sectionIndex=section_index,
        blockIndex=block_index,
        tableIndex=table_index,
        rowCount=row_count,
        colCount=col_count,
        visualRowCount=row_count,
        visualColCount=col_count,
        hasMergedCells=has_merged,
        hasNestedTables=has_nested,
        nestedTableCount=nested_count,
        cells=cells,
        headerRowCandidates=header_row_candidates,
        headerTexts=header_texts,
        headerConfidence=0.8 if header_row_candidates else 0.0,
        warnings=[WarnCode.NESTED_TABLE_DETECTED] if has_nested else [],
    )


def parse_tables_from_section(section_xml: bytes, section_index: int,
                               start_block_index: int = 0,
                               style_defs: dict | None = None) -> list[TableInfo]:
    """section XML bytes에서 모든 표를 파싱해 TableInfo 목록 반환."""
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return []

    tables: list[TableInfo] = []
    table_index = 0
    block_index = start_block_index

    for elem in root.iter():
        if elem.tag == _TAG_TBL:
            tbl_info = _parse_table_element(
                elem, section_index, table_index, block_index, style_defs=style_defs
            )
            tables.append(tbl_info)
            table_index += 1
            block_index += 1

    return tables
