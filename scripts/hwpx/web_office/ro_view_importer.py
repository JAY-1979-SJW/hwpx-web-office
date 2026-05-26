"""HWPX → WebOfficeDocumentModel 변환기 (read-only).

writer 호출·output HWPX 생성·원본 수정은 일절 하지 않는다.
parser_engine.parse_hwpx_v2 결과를 골조로 사용하고, hp:p / hp:run / hp:t
XML 을 직접 순회해 paragraph/run 정밀 측량 + containerScope 를 발급한다
(RO_VIEW_PARAGRAPH_01).

§11-6 자재 재사용: hwpx_package.HwpxPackage / local_name +
hwpx_paragraph_ops 의 paragraph helper 만 사용하며 mutation API
(write_xml / package save) 호출 0건.
"""
from __future__ import annotations
import hashlib
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))
if str(_PR / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(_PR / "scripts/hwpx"))

from scripts.hwpx.parser.parser_engine import parse_hwpx_v2  # noqa: E402
from scripts.hwpx.parser.style_parser import (  # noqa: E402
    parse_char_pr_defs,
    parse_font_face_defs,
    parse_font_face_table,
)
from hwpx_package import HwpxPackage, local_name  # noqa: E402
from hwpx_paragraph_ops import (  # noqa: E402
    find_paragraph_in_cell,
    paragraph_runs as _paragraph_runs,
)

from . import SCHEMA_VERSION, ENGINE_VERSION
from .document_model import (
    WebOfficeBlock,
    WebOfficeCell,
    WebOfficeDocumentModel,
    WebOfficeObject,
    WebOfficeParagraph,
    WebOfficeSection,
    WebOfficeStyles,
    WebOfficeTable,
    WebOfficeTextRun,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_paragraph_id(section_index: int, block_index: int,
                                          local_index: int = 0,
                                          table_id: str | None = None,
                                          row: int | None = None,
                                          col: int | None = None) -> str:
    if table_id is not None and row is not None and col is not None:
        return f"par_{table_id}_r{row}_c{col}_p{local_index}"
    return f"par_s{section_index}_b{block_index}_p{local_index}"


def _stable_block_id(block_type: str, section_index: int,
                                  block_index: int,
                                  ref: str | None = None) -> str:
    if block_type == "table" and ref:
        return f"blk_table_{ref}"
    return f"blk_{block_type}_s{section_index}_b{block_index}"


def _stable_cell_id(table_id: str, row: int, col: int) -> str:
    return f"cell_{table_id}_r{row}_c{col}"


def _stable_object_id(section_index: int, obj_index: int) -> str:
    return f"obj_s{section_index}_i{obj_index}"


def _stable_run_id(paragraph_id: str, run_index: int) -> str:
    return f"{paragraph_id}_run{run_index}"


# ── XML 직접 파싱 helper (read-only) ────────────────────────────────

def _inline_text_content(elem: ET.Element) -> str:
    local = local_name(elem.tag).lower()
    if local == "linebreak":
        parts = ["\n"]
    elif local == "fwspace":
        parts = [" "]
    else:
        parts = [elem.text or ""]
    for child in list(elem):
        parts.append(_inline_text_content(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _run_text_concat(run_elem: ET.Element) -> str:
    """run inline text in document order, preserving line/fixed spaces."""
    parts: list[str] = []
    for child in list(run_elem):
        parts.append(_inline_text_content(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _has_readable_inline_text(elem: ET.Element) -> bool:
    for e in elem.iter():
        if local_name(e.tag).lower() in {"t", "linebreak", "fwspace"}:
            return True
    return False


def _extract_runs_from_paragraph_elem(
    paragraph_elem: ET.Element,
) -> tuple[list[WebOfficeTextRun], str | None, str | None]:
    """paragraph element 에서 hp:run 자손을 순회해 runs + parPrIDRef 추출.

    Returns (runs, parPrIDRef, degraded_reason).
    degraded_reason != None 이면 multi-run 분해 불가 → 호출자가
    RO_VIEW_RUN_PRECISION_DEGRADED warning 적재.

    runId 는 임시 placeholder ("__run_idx_N__") 로 두고,
    호출자가 paragraphId 확정 후 _stable_run_id 로 갱신한다.
    """
    par_pr_id_ref = paragraph_elem.attrib.get("paraPrIDRef")
    run_elems = _paragraph_runs(paragraph_elem)
    if not run_elems:
        # hp:run 0개 — paragraph text 만 합성 run 1개로 fallback
        # paragraph 내 hp:t / hp:lineBreak 직접 수집
        full_text = _run_text_concat(paragraph_elem)
        return (
            [WebOfficeTextRun(runId="__run_idx_0__",
                                       text=full_text, charPrIDRef=None)],
            par_pr_id_ref,
            "no_hp_run_children",
        )
    runs: list[WebOfficeTextRun] = []
    any_text_node_seen = False
    for i, r in enumerate(run_elems):
        # hp:t 또는 hp:lineBreak 자손이 있는지 확인
        if _has_readable_inline_text(r):
            any_text_node_seen = True
        text = _run_text_concat(r)
        char_pr = r.attrib.get("charPrIDRef")
        runs.append(WebOfficeTextRun(
            runId=f"__run_idx_{i}__",
            text=text, charPrIDRef=char_pr))
    if not any_text_node_seen:
        # run 은 있으나 hp:t 가 모두 없음 → 분해 의미 없음. 단일 합성으로 폴딩.
        merged = "".join(r.text for r in runs)
        char_pr = runs[0].charPrIDRef if runs else None
        return (
            [WebOfficeTextRun(runId="__run_idx_0__",
                                       text=merged, charPrIDRef=char_pr)],
            par_pr_id_ref,
            "no_hp_t_children",
        )
    return runs, par_pr_id_ref, None


def _iter_paragraphs_in_cell_elem(
    cell_elem: ET.Element,
) -> list[ET.Element]:
    """cell element 의 hp:p 자손을 순서대로 반환."""
    return [e for e in cell_elem.iter()
                if local_name(e.tag).lower() == "p"]


def _find_cell_elem(
    section_root: ET.Element, row: int, col: int,
    table_position_in_section: int | None,
) -> ET.Element | None:
    """section root 안에서 (row, col) 좌표의 hp:tc 자손을 찾는다.

    table_position_in_section 이 주어지면 그 인덱스의 table 만 검색.
    매칭은 hp:tc 의 cellAddr (rowAddr / colAddr) attribute 기반.
    """
    # tables in section, in document order
    tables: list[ET.Element] = [
        e for e in section_root.iter()
        if local_name(e.tag).lower() == "tbl"
    ]
    if not tables:
        return None
    if table_position_in_section is not None:
        if 0 <= table_position_in_section < len(tables):
            candidates = [tables[table_position_in_section]]
        else:
            candidates = tables
    else:
        candidates = tables
    for tbl in candidates:
        for tc in tbl.iter():
            if local_name(tc.tag).lower() != "tc":
                continue
            # cellAddr child 확인
            for child in tc:
                if local_name(child.tag).lower() == "celladdr":
                    try:
                        r = int(child.attrib.get("rowAddr", "-1"))
                        c = int(child.attrib.get("colAddr", "-1"))
                    except (TypeError, ValueError):
                        r, c = -1, -1
                    if r == row and c == col:
                        return tc
    return None


def _find_table_elem(
    section_root: ET.Element,
    table_position_in_section: int | None,
) -> ET.Element | None:
    tables: list[ET.Element] = [
        e for e in section_root.iter()
        if local_name(e.tag).lower() == "tbl"
    ]
    if not tables:
        return None
    if table_position_in_section is not None:
        if 0 <= table_position_in_section < len(tables):
            return tables[table_position_in_section]
    return tables[0]


def _direct_child_attrs(elem: ET.Element | None, wanted: str) -> dict[str, Any]:
    if elem is None:
        return {}
    for child in list(elem):
        if local_name(child.tag).lower() == wanted.lower():
            return dict(child.attrib)
    return {}


def _section_layout_attrs(section_root: ET.Element | None) -> dict[str, Any]:
    if section_root is None:
        return {}
    sec_pr = _descendant_by_local(section_root, "secPr")
    if sec_pr is None:
        return {}
    page_border_fills: list[dict[str, Any]] = []
    for child in list(sec_pr):
        if local_name(child.tag) != "pageBorderFill":
            continue
        payload = dict(child.attrib)
        offset = _direct_child_attrs(child, "offset")
        if offset:
            payload["offset"] = offset
        page_border_fills.append(payload)
    return {
        "secPr": dict(sec_pr.attrib),
        "pagePr": _direct_child_attrs(sec_pr, "pagePr"),
        "grid": _direct_child_attrs(sec_pr, "grid"),
        "lineNumberShape": _direct_child_attrs(sec_pr, "lineNumberShape"),
        "pageBorderFills": page_border_fills,
    }


def _normalize_header_flag(value: str | None) -> bool | None:
    """hp:tc header attribute를 보수적으로 boolean으로 정규화한다."""
    if value is None:
        return None
    v = value.strip().lower()
    if v in {"1", "true", "yes"}:
        return True
    if v in {"0", "false", "no"}:
        return False
    return None


def _iter_top_level_paragraphs_in_section(
    section_root: ET.Element,
) -> list[tuple[int, ET.Element]]:
    """section root 의 top-level (table 밖) hp:p 를 blockIndex 순서로 반환.

    blockIndex 는 parser_engine 의 block_offset 과 동일한 의미가 아니라,
    section 내부 top-level child 순번(top-level paragraph 만 카운트). 단순
    매칭용으로 (paragraph 의 등장 순서)로 enumerate.
    """
    result: list[tuple[int, ET.Element]] = []
    # section root 의 직계 자식 중 hp:sec > hp:p 형태. parser_contract 는
    # hp:p 가 section 의 직계 자식 또는 hp:sec 자식. 안전하게 root.iter()
    # 중 ancestor 가 hp:tc / hp:tbl 이 아닌 hp:p 만 골라낸다.
    # ancestor 추적이 ET 에서는 비싸므로, 우리는 section root 의 직계
    # 자식만 본다 (대부분의 HWPX 는 root 가 hp:sec, 그 직계 자식이 hp:p
    # 또는 hp:tbl).
    # 다층 구조 대비: section_root 자체와 그 직계 자식 hp:sec 도 검사.
    candidates_roots: list[ET.Element] = [section_root]
    for child in list(section_root):
        if local_name(child.tag).lower() == "sec":
            candidates_roots.append(child)
    seen = set()
    idx = 0
    for root in candidates_roots:
        for child in list(root):
            if local_name(child.tag).lower() == "p":
                key = id(child)
                if key in seen:
                    continue
                seen.add(key)
                result.append((idx, child))
                idx += 1
    return result


def _load_package_safely(source_hwpx: Path) -> HwpxPackage | None:
    """HwpxPackage 로드. 실패 시 None (호출자가 fallback)."""
    try:
        return HwpxPackage(source_hwpx)
    except Exception:
        return None


def _read_section_root(
    package: HwpxPackage, source_xml_path: str | None,
) -> ET.Element | None:
    if not source_xml_path:
        return None
    entry = source_xml_path.replace("\\", "/")
    if entry not in package.entries:
        # try basename match
        for name in package.section_entries():
            if name.endswith(entry) or entry.endswith(name):
                entry = name
                break
        else:
            return None
    try:
        return package.read_xml(entry)
    except Exception:
        return None


def _read_header_bytes(package: HwpxPackage | None) -> bytes | None:
    if package is None:
        return None
    for entry in ("Contents/header.xml", "Contents\\header.xml"):
        if entry in package.entries:
            return package.entries[entry]
    for name, data in package.entries.items():
        if name.replace("\\", "/").endswith("Contents/header.xml"):
            return data
    return None


def _child_by_local(elem: ET.Element, wanted: str) -> ET.Element | None:
    for child in list(elem):
        if local_name(child.tag) == wanted:
            return child
    return None


def _children_by_local(elem: ET.Element, wanted: str) -> list[ET.Element]:
    return [child for child in list(elem) if local_name(child.tag) == wanted]


def _descendant_by_local(elem: ET.Element, wanted: str) -> ET.Element | None:
    for child in _effective_descendants(elem):
        if local_name(child.tag) == wanted:
            return child
    return None


def _selected_switch_branch(switch_elem: ET.Element) -> ET.Element | None:
    """Select the effective branch for HWPX compatibility switch wrappers."""
    default_branch: ET.Element | None = None
    for child in list(switch_elem):
        child_local = local_name(child.tag)
        if child_local == "case":
            return child
        if child_local == "default" and default_branch is None:
            default_branch = child
    return default_branch


def _effective_children(elem: ET.Element) -> list[ET.Element]:
    children: list[ET.Element] = []
    for child in list(elem):
        if local_name(child.tag) == "switch":
            branch = _selected_switch_branch(child)
            if branch is not None:
                children.extend(list(branch))
        else:
            children.append(child)
    return children


def _effective_descendants(elem: ET.Element) -> list[ET.Element]:
    result: list[ET.Element] = []
    for child in _effective_children(elem):
        result.append(child)
        result.extend(_effective_descendants(child))
    return result


def _extract_tab_pr_defs(header: ET.Element) -> dict[str, dict[str, Any]]:
    defs: dict[str, dict[str, Any]] = {}
    for tab_pr in header.iter():
        if local_name(tab_pr.tag) != "tabPr":
            continue
        tab_pr_id = tab_pr.attrib.get("id")
        if tab_pr_id is None:
            continue
        tab_items = [
            dict(item.attrib)
            for item in _effective_descendants(tab_pr)
            if local_name(item.tag) == "tabItem"
        ]
        defs[str(tab_pr_id)] = {
            "tabPrId": str(tab_pr_id),
            "autoTabLeft": tab_pr.attrib.get("autoTabLeft"),
            "autoTabRight": tab_pr.attrib.get("autoTabRight"),
            "tabItems": tab_items,
            "tabItemCount": len(tab_items),
        }
    return defs


def _extract_border_fill_defs_from_header(header: ET.Element) -> dict[str, dict[str, Any]]:
    defs: dict[str, dict[str, Any]] = {}
    for border_fill in header.iter():
        if local_name(border_fill.tag) != "borderFill":
            continue
        border_fill_id = border_fill.attrib.get("id")
        if border_fill_id is None:
            continue
        payload: dict[str, Any] = {
            "borderFillId": str(border_fill_id),
            "rawAttrs": dict(border_fill.attrib),
            "sides": {},
            "diagonal": {},
            "slash": {},
            "backSlash": {},
        }
        sides: dict[str, dict[str, Any]] = {}
        for child in list(border_fill):
            child_name = local_name(child.tag)
            if child_name in {"leftBorder", "rightBorder", "topBorder", "bottomBorder"}:
                sides[child_name] = dict(child.attrib)
            elif child_name in {"diagonal", "slash", "backSlash"}:
                payload[child_name] = dict(child.attrib)
        payload["sides"] = sides
        defs[str(border_fill_id)] = payload
    return defs


def _extract_border_fill_defs(package: HwpxPackage | None) -> dict[str, dict[str, Any]]:
    if package is None or "Contents/header.xml" not in package.entries:
        return {}
    try:
        header = package.read_xml("Contents/header.xml")
    except Exception:
        return {}
    return _extract_border_fill_defs_from_header(header)


def _extract_para_pr_defs(package: HwpxPackage | None) -> dict[str, dict[str, Any]]:
    if package is None or "Contents/header.xml" not in package.entries:
        return {}
    try:
        header = package.read_xml("Contents/header.xml")
    except Exception:
        return {}

    tab_pr_defs = _extract_tab_pr_defs(header)
    border_fill_defs = _extract_border_fill_defs_from_header(header)
    defs: dict[str, dict[str, Any]] = {}
    for para_pr in header.iter():
        if local_name(para_pr.tag) != "paraPr":
            continue
        para_pr_id = para_pr.attrib.get("id")
        if para_pr_id is None:
            continue

        tab_pr_id = para_pr.attrib.get("tabPrIDRef")
        tab_pr = tab_pr_defs.get(str(tab_pr_id)) if tab_pr_id is not None else None
        align = _descendant_by_local(para_pr, "align")
        auto_spacing = _descendant_by_local(para_pr, "autoSpacing")
        break_setting = _descendant_by_local(para_pr, "breakSetting")
        line_spacing = _descendant_by_local(para_pr, "lineSpacing")
        border = _descendant_by_local(para_pr, "border")
        margin = _descendant_by_local(para_pr, "margin")
        margin_payload: dict[str, dict[str, str | None]] = {}
        if margin is not None:
            for key in ("intent", "left", "right", "prev", "next"):
                item = _child_by_local(margin, key)
                if item is not None:
                    margin_payload[key] = {
                        "value": item.attrib.get("value"),
                        "relative": item.attrib.get("relative"),
                    }

        defs[str(para_pr_id)] = {
            "paraPrId": str(para_pr_id),
            "tabPrIDRef": tab_pr_id,
            "align": dict(align.attrib) if align is not None else {},
            "autoSpacing": (
                dict(auto_spacing.attrib) if auto_spacing is not None else {}
            ),
            "breakSetting": (
                dict(break_setting.attrib) if break_setting is not None else {}
            ),
            "lineSpacing": (
                dict(line_spacing.attrib) if line_spacing is not None else {}
            ),
            "border": dict(border.attrib) if border is not None else {},
            "borderFill": (
                border_fill_defs.get(str(border.attrib.get("borderFillIDRef")), {})
                if border is not None and border.attrib.get("borderFillIDRef") is not None
                else {}
            ),
            "margin": margin_payload,
            "tabPr": tab_pr or {},
            "tabItems": list(tab_pr.get("tabItems", [])) if tab_pr else [],
            "tabItemCount": int(tab_pr.get("tabItemCount", 0)) if tab_pr else 0,
        }
    return defs


def _extract_char_pr_defs(package: HwpxPackage | None) -> dict[str, dict[str, Any]]:
    header_bytes = _read_header_bytes(package)
    if header_bytes is None:
        return {}
    try:
        return parse_char_pr_defs(
            header_bytes, parse_font_face_table(header_bytes))
    except Exception:
        return {}


def _extract_font_face_defs(package: HwpxPackage | None) -> dict[str, dict[str, Any]]:
    header_bytes = _read_header_bytes(package)
    if header_bytes is None:
        return {}
    try:
        return parse_font_face_defs(header_bytes)
    except Exception:
        return {}


def _extract_style_defs(package: HwpxPackage | None) -> dict[str, dict[str, Any]]:
    if package is None or "Contents/header.xml" not in package.entries:
        return {}
    try:
        header = package.read_xml("Contents/header.xml")
    except Exception:
        return {}

    defs: dict[str, dict[str, Any]] = {}
    for style in header.iter():
        if local_name(style.tag) != "style":
            continue
        style_id = style.attrib.get("id")
        if style_id is None:
            continue
        payload = {
            "styleId": str(style_id),
            "type": style.attrib.get("type"),
            "name": style.attrib.get("name"),
            "engName": style.attrib.get("engName"),
            "paraPrIDRef": style.attrib.get("paraPrIDRef"),
            "charPrIDRef": style.attrib.get("charPrIDRef"),
            "nextStyleIDRef": style.attrib.get("nextStyleIDRef"),
            "langID": style.attrib.get("langID"),
            "lockForm": style.attrib.get("lockForm"),
            "rawAttrs": dict(style.attrib),
        }
        defs[str(style_id)] = payload
    return defs


def import_hwpx_as_ro_view(
    source_hwpx: Path
) -> WebOfficeDocumentModel:
    """HWPX 한 건을 WebOfficeDocumentModel 로 변환한다.

    - 원본 파일을 수정하지 않는다 (read-only).
    - writer / edit plan / package save 류 API 를 호출하지 않는다.
    - paragraph/run 은 hp:p / hp:run / hp:t XML 을 직접 순회해 측량한다.
    """
    source_hwpx = Path(source_hwpx)
    sha = _sha256(source_hwpx)
    parsed = parse_hwpx_v2(source_hwpx)

    # HwpxPackage 는 read-only 로만 사용 — write_xml / save 호출 0건.
    package = _load_package_safely(source_hwpx)
    border_fill_defs = _extract_border_fill_defs(package)
    section_roots_cache: dict[str, ET.Element | None] = {}

    def _section_root_for(path: str | None) -> ET.Element | None:
        if package is None or not path:
            return None
        if path in section_roots_cache:
            return section_roots_cache[path]
        root = _read_section_root(package, path)
        section_roots_cache[path] = root
        return root

    sections: list[WebOfficeSection] = []
    for i, sec_path in enumerate(parsed.sections or []):
        sec_root = _section_root_for(str(sec_path) if sec_path is not None else None)
        layout = _section_layout_attrs(sec_root)
        sections.append(WebOfficeSection(
            sectionIndex=i,
            sourceXmlPath=str(sec_path) if sec_path is not None else None,
            secPr=layout.get("secPr", {}),
            pagePr=layout.get("pagePr", {}),
            grid=layout.get("grid", {}),
            lineNumberShape=layout.get("lineNumberShape", {}),
            pageBorderFills=layout.get("pageBorderFills", [])))

    section_xml_path_by_index: dict[int, str | None] = {
        i: s.sourceXmlPath for i, s in enumerate(sections)
    }

    # section 내 table 등장순(idx) 캐시 — section index 별로 hp:tbl 순서.
    # table dict: sectionIndex -> list of table elems (document order)
    # 우리는 cell 찾을 때 "section 내 몇 번째 hp:tbl?" 을 알아야 한다.
    # parser_engine 의 TableInfo 는 blockIndex 를 갖지만, blockIndex 가
    # top-level paragraph 와 합쳐진 글로벌 인덱스인지 section-local 인지
    # 구현마다 달라, 안전하게 section 내 table 순서 = section 의 tables 중
    # 같은 sectionIndex 의 N 번째로 정의한다.
    section_table_order: dict[int, int] = {}
    table_section_order_idx: dict[str, int] = {}
    for t in (parsed.tables or []):
        cur = section_table_order.get(t.sectionIndex, 0)
        table_section_order_idx[t.tableId] = cur
        section_table_order[t.sectionIndex] = cur + 1

    tables: list[WebOfficeTable] = []
    cells: list[WebOfficeCell] = []
    paragraphs: list[WebOfficeParagraph] = []
    warnings: list[dict[str, Any]] = []
    tableid_to_idx: dict[str, int] = {}

    for ti, t in enumerate(parsed.tables or []):
        tid = t.tableId
        tableid_to_idx[tid] = ti
        cell_ids: list[str] = []
        sec_path = section_xml_path_by_index.get(t.sectionIndex)
        sec_root = _section_root_for(sec_path)
        table_pos = table_section_order_idx.get(tid)
        table_elem = (
            _find_table_elem(sec_root, table_pos)
            if sec_root is not None else None
        )
        table_size = _direct_child_attrs(table_elem, "sz")
        in_margin = _direct_child_attrs(table_elem, "inMargin")
        out_margin = _direct_child_attrs(table_elem, "outMargin")
        for c in t.cells or []:
            cell_id = _stable_cell_id(tid, c.row, c.col)
            cell_ids.append(cell_id)
            cell_pars: list[WebOfficeParagraph] = []
            header_attr: str | None = None
            header_cell: bool | None = None
            border_fill_id_ref: str | None = None
            border_fill: dict[str, Any] = {}
            cell_margin: dict[str, Any] = {}

            # ── XML 직접 파싱 시도 ──────────────────────────────
            par_elems: list[ET.Element] = []
            xml_fallback = False
            if sec_root is not None:
                cell_elem = _find_cell_elem(sec_root, c.row, c.col,
                                                              table_pos)
                if cell_elem is not None:
                    header_attr = cell_elem.attrib.get("header")
                    header_cell = _normalize_header_flag(header_attr)
                    border_fill_id_ref = cell_elem.attrib.get("borderFillIDRef")
                    if border_fill_id_ref is not None:
                        border_fill = border_fill_defs.get(str(border_fill_id_ref), {})
                    cell_margin = _direct_child_attrs(cell_elem, "cellMargin")
                    par_elems = _iter_paragraphs_in_cell_elem(cell_elem)

            if not par_elems and (c.paragraphs or []):
                xml_fallback = True

            if par_elems:
                for pi, p_elem in enumerate(par_elems):
                    par_id = _stable_paragraph_id(
                        section_index=t.sectionIndex,
                        block_index=t.blockIndex,
                        local_index=pi,
                        table_id=tid, row=c.row, col=c.col)
                    runs, par_pr, degraded = (
                        _extract_runs_from_paragraph_elem(p_elem))
                    # runId 확정
                    runs = [WebOfficeTextRun(
                        runId=_stable_run_id(par_id, ri),
                        text=r.text, charPrIDRef=r.charPrIDRef)
                                 for ri, r in enumerate(runs)]
                    text = "".join(r.text for r in runs)
                    if degraded:
                        warnings.append({
                            "code": "RO_VIEW_RUN_PRECISION_DEGRADED",
                            "paragraphId": par_id,
                            "reason": degraded,
                        })
                    par = WebOfficeParagraph(
                        paragraphId=par_id, text=text,
                        parPrIDRef=par_pr,
                        runs=runs,
                        containerScope={
                            "kind": "cell",
                            "tableIndex": ti,
                            "rowIndex": c.row,
                            "colIndex": c.col,
                            "paragraphIndex": pi,
                        })
                    cell_pars.append(par)
                    paragraphs.append(par)
            else:
                # XML 직접 파싱 실패 또는 paragraphs 없음 → 기존 합성 fallback
                if xml_fallback:
                    warnings.append({
                        "code": "RO_VIEW_PARAGRAPH_XML_FALLBACK",
                        "reason": "cell_xml_unavailable",
                        "tableId": tid, "row": c.row, "col": c.col,
                    })
                for pi, par_text in enumerate(c.paragraphs or []):
                    par_id = _stable_paragraph_id(
                        section_index=t.sectionIndex,
                        block_index=t.blockIndex,
                        local_index=pi,
                        table_id=tid, row=c.row, col=c.col)
                    run_id = _stable_run_id(par_id, 0)
                    par = WebOfficeParagraph(
                        paragraphId=par_id, text=par_text or "",
                        parPrIDRef=(c.paraPrIDRefs[0]
                                            if c.paraPrIDRefs else None),
                        runs=[WebOfficeTextRun(
                            runId=run_id, text=par_text or "",
                            charPrIDRef=(c.charPrIDRefs[0]
                                                    if c.charPrIDRefs else None))],
                        containerScope={
                            "kind": "cell",
                            "tableIndex": ti,
                            "rowIndex": c.row,
                            "colIndex": c.col,
                            "paragraphIndex": pi,
                        })
                    if xml_fallback:
                        warnings.append({
                            "code": "RO_VIEW_RUN_PRECISION_DEGRADED",
                            "paragraphId": par_id,
                            "reason": "cell_xml_unavailable",
                        })
                    cell_pars.append(par)
                    paragraphs.append(par)

            cells.append(WebOfficeCell(
                cellId=cell_id, tableId=tid,
                row=c.row, col=c.col,
                rowSpan=c.rowSpan or 1, colSpan=c.colSpan or 1,
                isCoveredByMerge=bool(c.isCoveredByMerge),
                isMergedOrigin=bool(c.isMergedOrigin),
                header=header_attr,
                headerCell=header_cell,
                borderFillIDRef=border_fill_id_ref,
                borderFill=border_fill,
                cellMargin=cell_margin,
                paragraphs=cell_pars,
                text=c.normalizedText or ""))
        tables.append(WebOfficeTable(
            tableId=tid,
            blockId=_stable_block_id("table", t.sectionIndex,
                                                      t.blockIndex, ref=tid),
            sectionIndex=t.sectionIndex,
            rowCount=t.rowCount, colCount=t.colCount,
            visualColCount=t.visualColCount,
            hasMergedCells=bool(t.hasMergedCells),
            tableSize=table_size,
            inMargin=in_margin,
            outMargin=out_margin,
            cellIds=cell_ids))

    # ── body (top-level) paragraph 처리 ─────────────────────────────
    # section 별 top-level paragraph elem 캐시
    section_top_paragraphs_cache: dict[int, list[tuple[int, ET.Element]]] = {}

    def _top_paragraphs_for(section_index: int) -> list[tuple[int, ET.Element]]:
        if section_index in section_top_paragraphs_cache:
            return section_top_paragraphs_cache[section_index]
        sec_path = section_xml_path_by_index.get(section_index)
        sec_root = _section_root_for(sec_path)
        if sec_root is None:
            section_top_paragraphs_cache[section_index] = []
            return []
        out = _iter_top_level_paragraphs_in_section(sec_root)
        section_top_paragraphs_cache[section_index] = out
        return out

    # parser_engine 의 paragraph block 순서 == section 내 top-level p 순서 라
    # 가정. section 별로 paragraph block 만 추려 index 매칭.
    section_para_block_counter: dict[int, int] = {}

    blocks: list[WebOfficeBlock] = []
    for t in parsed.tables or []:
        blocks.append(WebOfficeBlock(
            blockId=_stable_block_id("table", t.sectionIndex,
                                                      t.blockIndex, ref=t.tableId),
            type="table",
            sectionIndex=t.sectionIndex,
            blockIndex=t.blockIndex,
            ref=t.tableId))
    for b in parsed.blocks or []:
        ref = None
        if b.type == "table" and getattr(b, "tableId", None):
            ref = b.tableId
        elif b.type == "paragraph":
            sec_i = b.sectionIndex
            blk_i = b.blockIndex
            par_id = _stable_paragraph_id(
                section_index=sec_i,
                block_index=blk_i, local_index=0)
            # body paragraph 측량
            top_paras = _top_paragraphs_for(sec_i)
            local_para_idx = section_para_block_counter.get(sec_i, 0)
            section_para_block_counter[sec_i] = local_para_idx + 1

            runs: list[WebOfficeTextRun] = []
            par_pr: str | None = None
            degraded_reason: str | None = None
            text_value: str = b.text or ""
            if local_para_idx < len(top_paras):
                _, p_elem = top_paras[local_para_idx]
                raw_runs, par_pr, degraded_reason = (
                    _extract_runs_from_paragraph_elem(p_elem))
                runs = [WebOfficeTextRun(
                    runId=_stable_run_id(par_id, ri),
                    text=r.text, charPrIDRef=r.charPrIDRef)
                              for ri, r in enumerate(raw_runs)]
                text_value = "".join(r.text for r in runs)
            else:
                # XML 매칭 실패 → 단일 합성 run + warning
                degraded_reason = "body_paragraph_xml_unavailable"
                runs = [WebOfficeTextRun(
                    runId=_stable_run_id(par_id, 0),
                    text=text_value, charPrIDRef=None)]

            if degraded_reason:
                warnings.append({
                    "code": "RO_VIEW_RUN_PRECISION_DEGRADED",
                    "paragraphId": par_id,
                    "reason": degraded_reason,
                })

            par = WebOfficeParagraph(
                paragraphId=par_id, text=text_value,
                parPrIDRef=par_pr,
                runs=runs,
                containerScope={
                    "kind": "block",
                    "sectionIndex": sec_i,
                    "blockIndex": blk_i,
                    "paragraphIndex": 0,
                })
            paragraphs.append(par)
            ref = par_id
        blocks.append(WebOfficeBlock(
            blockId=_stable_block_id(b.type, b.sectionIndex,
                                                      b.blockIndex, ref=ref),
            type=b.type,
            sectionIndex=b.sectionIndex,
            blockIndex=b.blockIndex,
            ref=ref))

    objects: list[WebOfficeObject] = []
    for oi, obj in enumerate(parsed.objects or []):
        kind = getattr(obj, "type", None) or getattr(obj, "kind",
                                                                            "unknown")
        sec_idx = getattr(obj, "sectionIndex", 0) or 0
        objects.append(WebOfficeObject(
            objectId=_stable_object_id(sec_idx, oi),
            sectionIndex=sec_idx,
            kind=str(kind),
            placeholder=True))

    style_info = parsed.styles
    char_pr_defs = _extract_char_pr_defs(package)
    para_pr_defs = _extract_para_pr_defs(package)
    font_face_defs = _extract_font_face_defs(package)
    style_defs = _extract_style_defs(package)
    styles = WebOfficeStyles(
        charPrCount=len(getattr(style_info, "charPr", []) or []),
        parPrCount=len(getattr(style_info, "parPr", []) or []),
        borderFillCount=len(getattr(style_info, "borderFill", []) or []),
        styleCount=len(style_defs),
        charPrDefs=char_pr_defs,
        paraPrDefs=para_pr_defs,
        fontFaceDefs=font_face_defs,
        styleDefs=style_defs,
        borderFillDefs=border_fill_defs)

    for w in (parsed.warnings or []):
        if isinstance(w, dict):
            warnings.append(w)
        else:
            warnings.append({"message": str(w)})

    document_id = f"doc_{sha[:16]}"
    return WebOfficeDocumentModel(
        schemaVersion=SCHEMA_VERSION,
        engineVersion=ENGINE_VERSION,
        requestId=str(parsed.requestId or ""),
        documentId=document_id,
        sourceDocumentHash=sha,
        sourceDocumentPath=str(source_hwpx),
        sections=sections, blocks=blocks,
        paragraphs=paragraphs, tables=tables,
        cells=cells, objects=objects, styles=styles,
        warnings=warnings)
