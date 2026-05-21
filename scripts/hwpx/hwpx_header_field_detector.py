"""Infer input-required fields from HWPX table headers and labels."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from hwpx_package import HwpxPackage, local_name, text_nodes
from hwpx_table_ops import find_tables, get_table_cell_matrix


STOP_LABELS = {
    "구비서류",
    "처리기간",
    "수수료",
    "작성방법",
    "유의사항",
    "확인합니다",
    "귀하",
}

DATE_HINTS = ("일자", "일시", "일", "date")
PHONE_HINTS = ("전화", "연락처", "tel", "phone")
NUMBER_HINTS = ("면적", "수량", "금액", "량", "수", "number", "amount", "qty")
IDENTIFIER_HINTS = ("번호", "no", "id", "code")


def normalize_label(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", text or "")
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"^\s*\d+\s*[.)]\s*", "", text)
    text = text.replace(":", " ").replace("：", " ")
    text = re.sub(r"\s+", " ", text).strip(" .ㆍ·-_")
    return text


def normalize_key(text: str) -> str:
    return re.sub(r"[\s:_\-\[\]().ㆍ·]+", "", text or "").lower()


def is_empty_or_placeholder(text: str) -> bool:
    value = re.sub(r"\s+", "", text or "")
    if not value:
        return True
    if "입력필요" in value:
        return True
    if value in {"제", "호", "제호", "㎡", "년월일", "년월일시", "..." }:
        return True
    if set(value) <= {".", "ㆍ", "·", "-", "_", "(", ")", "[", "]"}:
        return True
    if re.fullmatch(r"0{2,}(?:[-.]0+)*", value):
        return True
    return False


def is_probable_label(text: str) -> bool:
    label = normalize_label(text)
    key = normalize_key(label)
    if not label or len(label) > 35:
        return False
    if len(label) < 2:
        return False
    if any(stop in key for stop in STOP_LABELS):
        return False
    if not re.search(r"[가-힣A-Za-z]", label):
        return False
    if re.fullmatch(r"\d+[년월일호㎡]*", key):
        return False
    if re.search(r"[:：]", text or ""):
        return True
    if any(token in key for token in DATE_HINTS + PHONE_HINTS + NUMBER_HINTS + IDENTIFIER_HINTS):
        return True
    compact_chars = re.sub(r"[^0-9A-Za-z가-힣]", "", label)
    if compact_chars:
        digit_count = sum(ch.isdigit() for ch in compact_chars)
        alpha_count = sum(ch.isascii() and ch.isalpha() for ch in compact_chars)
        korean_count = sum("가" <= ch <= "힣" for ch in compact_chars)
        if digit_count and digit_count + alpha_count > korean_count:
            return False
    return len(label) <= 12


def is_probable_top_header_label(text: str) -> bool:
    label = normalize_label(text)
    key = normalize_key(label)
    if not label or len(label) > 45:
        return False
    if any(stop in key for stop in STOP_LABELS):
        return False
    return bool(re.search(r"[가-힣A-Za-z]", label))


def field_type(label: str) -> str:
    key = normalize_key(label)
    if any(word in key for word in DATE_HINTS):
        return "date"
    if any(word in key for word in PHONE_HINTS):
        return "phone"
    if any(word in key for word in NUMBER_HINTS):
        return "number"
    if any(word in key for word in IDENTIFIER_HINTS):
        return "identifier"
    return "text"


def expected_format(label: str) -> str:
    kind = field_type(label)
    if kind == "date":
        return "YYYY.MM.DD"
    if kind == "phone":
        return "02-0000-0000 또는 010-0000-0000"
    if kind == "number":
        return "숫자"
    if kind == "identifier":
        return "문자/번호"
    return "문자"


def _cells(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for row in matrix.get("rows", []):
        result.extend(row.get("cells", []))
    return result


def _cell_index(matrix: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    return {(int(cell.get("visual_row", 0)), int(cell.get("visual_col", 0))): cell for cell in _cells(matrix)}


def _row_cells(matrix: dict[str, Any], visual_row: int) -> list[dict[str, Any]]:
    return sorted(
        [cell for cell in _cells(matrix) if int(cell.get("visual_row", -1)) == visual_row],
        key=lambda cell: int(cell.get("visual_col", 0)),
    )


def _right_target(matrix: dict[str, Any], label_cell: dict[str, Any]) -> dict[str, Any] | None:
    row = int(label_cell.get("visual_row", 0))
    label_col = int(label_cell.get("visual_col", 0))
    label_span = int(label_cell.get("colspan", 1) or 1)
    min_col = label_col + label_span
    for cell in _row_cells(matrix, row):
        col = int(cell.get("visual_col", 0))
        if col < min_col:
            continue
        if is_empty_or_placeholder(str(cell.get("text", ""))):
            return cell
        if col > min_col + 4:
            break
    return None


def _row_label_count(index: dict[tuple[int, int], dict[str, Any]], row: int) -> int:
    return sum(
        1
        for (candidate_row, _candidate_col), cell in index.items()
        if candidate_row == row and is_probable_label(str(cell.get("text", "")))
    )


def _below_target(index: dict[tuple[int, int], dict[str, Any]], label_cell: dict[str, Any]) -> dict[str, Any] | None:
    row = int(label_cell.get("visual_row", 0))
    col = int(label_cell.get("visual_col", 0))
    above = index.get((row - 1, col))
    if (
        above
        and _row_label_count(index, row) < 2
        and is_probable_label(str(above.get("text", "")))
        and not is_empty_or_placeholder(str(above.get("text", "")))
    ):
        return None
    for row_offset in (1, 2):
        candidate = index.get((row + row_offset, col))
        if candidate and is_empty_or_placeholder(str(candidate.get("text", ""))):
            return candidate
    return None


def _inline_target(label_cell: dict[str, Any]) -> bool:
    text = str(label_cell.get("text", ""))
    compact = normalize_key(text)
    if "[입력필요" in text:
        return True
    if text.strip().endswith((":","：")):
        return True
    if compact in {"제호", "제"}:
        return True
    return False


def _candidate(
    table_index: int,
    label_cell: dict[str, Any],
    target_cell: dict[str, Any],
    label: str,
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    before_text = str(target_cell.get("text", ""))
    return {
        "table": table_index,
        "label": label,
        "key": normalize_key(label),
        "type": field_type(label),
        "expected_format": expected_format(label),
        "target": {
            "row": int(target_cell.get("visual_row", 0)),
            "col": int(target_cell.get("visual_col", 0)),
            "rowspan": int(target_cell.get("rowspan", 1) or 1),
            "colspan": int(target_cell.get("colspan", 1) or 1),
            "current_text": before_text,
            "empty_or_placeholder": is_empty_or_placeholder(before_text),
        },
        "header": {
            "row": int(label_cell.get("visual_row", 0)),
            "col": int(label_cell.get("visual_col", 0)),
            "text": str(label_cell.get("text", "")),
        },
        "reason": reason,
        "confidence": round(confidence, 2),
        "prompt": f"{label} 값을 입력해 주세요.",
    }


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in text_nodes(paragraph)).strip()


def _has_ancestor(parent_map: dict[ET.Element, ET.Element], elem: ET.Element, names: set[str]) -> bool:
    current = parent_map.get(elem)
    while current is not None:
        if local_name(current.tag) in names:
            return True
        current = parent_map.get(current)
    return False


def top_level_paragraphs(package: HwpxPackage, *, section_limit: int = 1, paragraph_limit: int = 80) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = []
    for section_index, entry in enumerate(package.section_entries()[:section_limit]):
        root = package.read_xml(entry)
        parent_map = {child: parent for parent in root.iter() for child in list(parent)}
        order = 0
        for elem in root.iter():
            if local_name(elem.tag) != "p":
                continue
            if _has_ancestor(parent_map, elem, {"tbl", "tc", "subList"}):
                continue
            text = _paragraph_text(elem)
            if not text:
                continue
            paragraphs.append(
                {
                    "section": section_index,
                    "entry": entry,
                    "paragraph_order": order,
                    "paragraph_id": elem.attrib.get("id"),
                    "text": text,
                }
            )
            order += 1
            if len(paragraphs) >= paragraph_limit:
                return paragraphs
    return paragraphs


def _paragraph_has_missing_value(text: str) -> bool:
    value_part = split_label_value(text).get("value", "")
    compact = normalize_key(value_part)
    if not compact:
        return True
    if re.search(r"(19|20)?\d{0,2}년월일", compact):
        return True
    if set(compact) <= {"년", "월", "일", "층", "㎡", "m", "2", "국", "선", "구", "내", "회", "호", "제"}:
        return True
    return False


def split_label_value(text: str) -> dict[str, str]:
    value = str(text or "").strip()
    match = re.search(r"[:：]", value)
    if not match:
        return {"label": "", "value": value}
    raw_label = value[: match.start()]
    raw_value = value[match.end() :]
    label = normalize_label(raw_label)
    return {"label": label, "value": raw_value.strip()}


def _top_header_candidate(paragraph: dict[str, Any], label: str, confidence: float) -> dict[str, Any]:
    text = str(paragraph.get("text", ""))
    return {
        "table": None,
        "source": "top_header_paragraph",
        "label": label,
        "key": normalize_key(label),
        "type": field_type(label),
        "expected_format": expected_format(label),
        "target": {
            "kind": "paragraph",
            "section": paragraph.get("section"),
            "paragraph_order": paragraph.get("paragraph_order"),
            "paragraph_id": paragraph.get("paragraph_id"),
            "current_text": text,
            "empty_or_placeholder": _paragraph_has_missing_value(text),
        },
        "header": {
            "section": paragraph.get("section"),
            "paragraph_order": paragraph.get("paragraph_order"),
            "text": text,
        },
        "reason": "TOP_HEADER_PARAGRAPH",
        "confidence": round(confidence, 2),
        "prompt": f"{label} 값을 입력해 주세요.",
    }


def detect_top_header_input_fields(package: HwpxPackage) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    for paragraph in top_level_paragraphs(package):
        text = str(paragraph.get("text", ""))
        parsed = split_label_value(text)
        label = parsed["label"]
        if not label or not is_probable_top_header_label(label):
            continue
        confidence = 0.86 if _paragraph_has_missing_value(text) else 0.74
        fields.append(_top_header_candidate(paragraph, label, confidence))
    return {"status": "PASS", "field_count": len(fields), "fields": fields}


def detect_table_input_fields(package: HwpxPackage, table_index: int) -> dict[str, Any]:
    matrix = get_table_cell_matrix(package, table_index)
    if matrix.get("status") != "PASS":
        return {"status": matrix.get("status"), "table": table_index, "fields": []}
    index = _cell_index(matrix)
    fields: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for cell in _cells(matrix):
        raw_label = str(cell.get("text", ""))
        label = normalize_label(raw_label)
        if not is_probable_label(label):
            continue
        targets: list[tuple[dict[str, Any], str, float]] = []
        if _inline_target(cell):
            targets.append((cell, "INLINE_LABEL_CELL", 0.72))
        right = _right_target(matrix, cell)
        if right is not None:
            targets.append((right, "RIGHT_EMPTY_CELL", 0.9 if "[입력필요" in str(right.get("text", "")) else 0.82))
        below = _below_target(index, cell)
        if below is not None and right is None:
            targets.append((below, "COLUMN_HEADER_BELOW_EMPTY_CELL", 0.78))
        for target, reason, confidence in targets:
            key = (int(target.get("visual_row", 0)), int(target.get("visual_col", 0)), normalize_key(label))
            if key in seen:
                continue
            seen.add(key)
            fields.append(_candidate(table_index, cell, target, label, reason, confidence))
    fields.sort(key=lambda item: (-float(item["confidence"]), item["table"], item["target"]["row"], item["target"]["col"], item["label"]))
    return {
        "status": "PASS",
        "table": table_index,
        "row_count": len(matrix.get("rows", [])),
        "field_count": len(fields),
        "fields": fields,
    }


def detect_input_fields(package: HwpxPackage, *, table_limit: int | None = None, min_confidence: float = 0.7) -> dict[str, Any]:
    tables = find_tables(package)
    limit = len(tables) if table_limit is None else min(table_limit, len(tables))
    table_reports = []
    fields = []
    for table_index in range(limit):
        report = detect_table_input_fields(package, table_index)
        table_reports.append({k: v for k, v in report.items() if k != "fields"})
        fields.extend([field for field in report.get("fields", []) if float(field.get("confidence", 0)) >= min_confidence])
    top_header = detect_top_header_input_fields(package)
    fields.extend([field for field in top_header.get("fields", []) if float(field.get("confidence", 0)) >= min_confidence])
    deduped = []
    seen_targets: set[tuple[Any, ...]] = set()
    def confidence_key(item: dict[str, Any]) -> tuple[Any, ...]:
        target = item["target"]
        if target.get("kind") == "paragraph":
            return (-float(item["confidence"]), -1, int(target.get("paragraph_order") or 0), 0)
        return (-float(item["confidence"]), int(item["table"]), int(target["row"]), int(target["col"]))

    for field in sorted(fields, key=confidence_key):
        target = field["target"]
        if target.get("kind") == "paragraph":
            target_key = ("paragraph", target.get("section"), target.get("paragraph_order"), field["key"])
        else:
            target_key = ("table", int(field["table"]), int(target["row"]), int(target["col"]))
        if target_key in seen_targets:
            continue
        seen_targets.add(target_key)
        deduped.append(field)
    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        target = item["target"]
        if target.get("kind") == "paragraph":
            return (-1, int(target.get("section") or 0), int(target.get("paragraph_order") or 0), 0, -float(item["confidence"]))
        return (int(item["table"]), int(target["row"]), int(target["col"]), 0, -float(item["confidence"]))

    deduped.sort(key=sort_key)
    return {
        "status": "PASS",
        "table_count": len(tables),
        "scanned_table_count": limit,
        "field_count": len(deduped),
        "fields": deduped,
        "tables": table_reports,
        "top_header": {k: v for k, v in top_header.items() if k != "fields"},
        "input_template": {field["label"]: "" for field in deduped},
    }


def input_request_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# HWPX 헤더 기반 입력 필요 항목",
        "",
        "문서의 표 헤더와 라벨을 분석해 입력해야 할 후보 항목을 추출했습니다.",
        "",
    ]
    for field in report.get("fields", []):
        target = field["target"]
        if target.get("kind") == "paragraph":
            location = f"section={target.get('section')}, paragraph={target.get('paragraph_order')}"
        else:
            location = f"table={field['table']}, row={target['row']}, col={target['col']}"
        lines.append(f"- {field['label']} ({field['expected_format']}) {location}, confidence={field['confidence']}")
    lines.append("")
    lines.append("JSON 입력 템플릿:")
    lines.append("")
    lines.append("```json")
    import json

    lines.append(json.dumps(report.get("input_template", {}), ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)


__all__ = [
    "detect_input_fields",
    "detect_table_input_fields",
    "detect_top_header_input_fields",
    "input_request_markdown",
    "is_empty_or_placeholder",
    "is_probable_label",
    "normalize_label",
    "normalize_key",
]
