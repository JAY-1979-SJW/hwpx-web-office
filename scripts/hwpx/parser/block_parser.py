"""HWPX Parser V2 — block parser (read-only).

section XML에서 본문 블록 순서를 BlockInfo 목록으로 복원한다.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET

from .parser_contract import BlockInfo

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_TAG_P = f"{{{NS_HP}}}p"
_TAG_TBL = f"{{{NS_HP}}}tbl"
_TAG_T = f"{{{NS_HP}}}t"

_PAGE_MARKER_RE = re.compile(
    r"[(\[]\s*\d+\s*쪽\s*(중\s*제\s*\d+\s*쪽)?\s*[)\]]"
    r"|제\s*\d+\s*쪽"
    r"|\d+\s*/\s*\d+\s*쪽"
)
_DRAWING_TAGS = {
    f"{{{NS_HP}}}drawing",
    f"{{{NS_HP}}}pic",
}
_IMAGE_TAGS = {
    f"{{{NS_HP}}}img",
}


def _para_text(p: ET.Element) -> str:
    """이 문단 자체의 텍스트만 반환한다.

    HWPX는 표(hp:tbl)가 문단 안에 컨트롤로 중첩될 수 있다. 그 표의 셀
    내용은 parse_tables_from_section이 셀 단위로 정확하게 별도 파싱하므로,
    여기서 재귀적으로 다시 긁으면 문서 요약(titleCandidate/fullText)에
    표 전체 내용이 중복으로 섞여 들어간다(2026-09-29 python-hwpx 교차
    검증으로 확인). 중첩된 hp:tbl 서브트리는 건너뛴다.
    """
    parts: list[str] = []

    def _walk(elem: ET.Element) -> None:
        for child in elem:
            if child.tag == _TAG_TBL:
                continue
            if child.tag == _TAG_T and child.text:
                parts.append(child.text)
            _walk(child)

    _walk(p)
    return "".join(parts)


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\r\n\t]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_blocks_from_section(
    section_xml: bytes, section_index: int, source_path: str = ""
) -> list[BlockInfo]:
    """section XML에서 최상위 블록 순서를 BlockInfo 목록으로 반환."""
    try:
        root = ET.fromstring(section_xml)
    except ET.ParseError:
        return []

    blocks: list[BlockInfo] = []
    block_index = 0
    table_count_in_section = 0

    # section root의 직계 자식 순서 순회
    for elem in root:
        order_key = f"s{section_index}:b{block_index:04d}"

        if elem.tag == _TAG_P:
            text = _para_text(elem)
            norm = _normalize(text)
            btype = "page_marker" if _PAGE_MARKER_RE.search(text) else "paragraph"
            blocks.append(
                BlockInfo(
                    blockIndex=block_index,
                    sectionIndex=section_index,
                    type=btype,
                    text=norm or None,
                    sourceXmlPath=source_path,
                    orderKey=order_key,
                )
            )

        elif elem.tag == _TAG_TBL:
            table_id = f"t_s{section_index}_{table_count_in_section:03d}"
            blocks.append(
                BlockInfo(
                    blockIndex=block_index,
                    sectionIndex=section_index,
                    type="table",
                    tableId=table_id,
                    sourceXmlPath=source_path,
                    orderKey=order_key,
                )
            )
            table_count_in_section += 1

        elif elem.tag in _DRAWING_TAGS:
            blocks.append(
                BlockInfo(
                    blockIndex=block_index,
                    sectionIndex=section_index,
                    type="drawing",
                    sourceXmlPath=source_path,
                    orderKey=order_key,
                )
            )

        elif elem.tag in _IMAGE_TAGS:
            blocks.append(
                BlockInfo(
                    blockIndex=block_index,
                    sectionIndex=section_index,
                    type="image",
                    sourceXmlPath=source_path,
                    orderKey=order_key,
                )
            )

        else:
            # sub-elements: p/tbl 포함 여부 확인
            has_p = any(c.tag == _TAG_P for c in elem.iter())
            has_tbl = any(c.tag == _TAG_TBL for c in elem.iter())
            if has_p or has_tbl:
                btype = "table" if has_tbl else "paragraph"
                blocks.append(
                    BlockInfo(
                        blockIndex=block_index,
                        sectionIndex=section_index,
                        type=btype,
                        sourceXmlPath=source_path,
                        orderKey=order_key,
                    )
                )
            else:
                continue  # 빈 wrapper는 블록으로 세지 않음

        block_index += 1

    return blocks
