from __future__ import annotations

import argparse
import csv
import json
import re
import zlib
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import olefile

ROOT = Path(__file__).resolve().parents[1]
HWP_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")
HWPTAG_PARA_TEXT = 67
INVALID_FILENAME_RE = re.compile(r'[\\/:*?"<>|]+')
HWP_RECORD_TAGS = {
    16: "DOCUMENT_PROPERTIES",
    17: "ID_MAPPINGS",
    18: "BIN_DATA",
    19: "FACE_NAME",
    20: "BORDER_FILL",
    21: "CHAR_SHAPE",
    22: "TAB_DEF",
    23: "NUMBERING",
    24: "BULLET",
    25: "PARA_SHAPE",
    26: "STYLE",
    27: "DOC_DATA",
    28: "DISTRIBUTE_DOC_DATA",
    30: "COMPATIBLE_DOCUMENT",
    31: "LAYOUT_COMPATIBILITY",
    32: "TRACK_CHANGE",
    66: "PARA_HEADER",
    67: "PARA_TEXT",
    68: "PARA_CHAR_SHAPE",
    69: "PARA_LINE_SEG",
    70: "PARA_RANGE_TAG",
    71: "CTRL_HEADER",
    72: "LIST_HEADER",
    73: "PAGE_DEF",
    74: "FOOTNOTE_SHAPE",
    75: "PAGE_BORDER_FILL",
    76: "SHAPE_COMPONENT",
    77: "TABLE",
    78: "SHAPE_COMPONENT_LINE",
    79: "SHAPE_COMPONENT_RECTANGLE",
    80: "SHAPE_COMPONENT_ELLIPSE",
    81: "SHAPE_COMPONENT_ARC",
    82: "SHAPE_COMPONENT_POLYGON",
    83: "SHAPE_COMPONENT_CURVE",
    84: "OLE",
    85: "PICTURE",
    86: "CONTAINER",
    87: "CTRL_DATA",
    88: "EQEDIT",
    90: "SHAPE_COMPONENT_TEXTART",
    91: "FORM_OBJECT",
    92: "MEMO_SHAPE",
    93: "MEMO_LIST",
    94: "FORBIDDEN_CHAR",
    95: "CHART_DATA",
    96: "TRACK_CHANGE_CONTENT",
    97: "TRACK_CHANGE_AUTHOR",
    98: "VIDEO_DATA",
    115: "SHAPE_COMPONENT_UNKNOWN",
}
TEXT_ONLY_SUPPORTED_TAGS = {66, 67, 68, 69, 70}
FIDELITY_RISK_TAGS = {
    18,
    20,
    21,
    23,
    24,
    25,
    26,
    28,
    30,
    31,
    32,
    71,
    72,
    73,
    75,
    76,
    77,
    84,
    85,
    86,
    87,
    88,
    90,
    91,
    92,
    93,
    94,
    95,
    96,
    97,
    98,
    115,
}


FIELD_KEYWORDS = [
    "공사명",
    "현장명",
    "현장주소",
    "소재지",
    "대지위치",
    "위치",
    "주소",
    "신청인",
    "신고인",
    "건축주",
    "성명",
    "생년월일",
    "법인등록번호",
    "상호",
    "대표자",
    "전화번호",
    "연락처",
    "전자우편",
    "허가번호",
    "신고번호",
    "착공일",
    "착공예정일",
    "준공일",
    "준공예정일",
    "사용승인",
    "검사희망일",
    "검사일",
    "공사기간",
    "시공자",
    "설계자",
    "감리자",
    "감리원",
    "공사업자",
    "등록번호",
    "면허번호",
    "자격번호",
    "공사종류",
    "공사개요",
    "용도",
    "구조",
    "층수",
    "건축면적",
    "연면적",
    "대지면적",
    "건폐율",
    "용적률",
    "설비명",
    "시설명",
    "시설위치",
    "시설종류",
    "설비용량",
    "전압",
    "가스종류",
    "저장능력",
    "처리능력",
    "배출시설",
    "방지시설",
    "폐기물",
    "배출량",
    "처리량",
    "점검일",
    "점검기간",
    "점검자",
    "점검결과",
    "변경 전",
    "변경 후",
    "변경사유",
    "작성일",
    "제출일",
]


ATTACHMENT_KEYWORDS = [
    "첨부서류",
    "구비서류",
    "제출서류",
    "도면",
    "설계도서",
    "위치도",
    "배치도",
    "평면도",
    "계약서",
    "내역서",
    "시험성적서",
    "사진",
    "자격증",
    "등록증",
    "허가증",
    "확인서",
    "증명서",
]


def normalize_text(text: str) -> str:
    for artifact in ["捤獥", "汤捯", "氠瑢", "漠杳"]:
        text = text.replace(artifact, " ")
    text = re.sub(r"[ༀ-࿿Ā]+", " ", text)
    text = text.replace("\x00", "")
    text = re.sub(r"[\u0001-\u0008\u000b\u000c\u000e-\u001f]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def read_file_header(ole: olefile.OleFileIO) -> dict[str, Any]:
    data = ole.openstream("FileHeader").read()
    props = int.from_bytes(data[36:40], "little") if len(data) >= 40 else 0
    return {
        "signature": data[:32].decode("latin1", errors="ignore"),
        "compressed": bool(props & 0x01),
        "encrypted": bool(props & 0x02),
        "distributable": bool(props & 0x04),
        "script": bool(props & 0x08),
        "drm": bool(props & 0x10),
    }


def decompress_if_needed(data: bytes, compressed: bool) -> bytes:
    if not compressed:
        return data
    for wbits in (-15, 15):
        try:
            return zlib.decompress(data, wbits)
        except zlib.error:
            continue
    return data


def iter_records(data: bytes):
    offset = 0
    total = len(data)
    while offset + 4 <= total:
        header = int.from_bytes(data[offset : offset + 4], "little")
        offset += 4
        tag_id = header & 0x3FF
        level = (header >> 10) & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if offset + 4 > total:
                break
            size = int.from_bytes(data[offset : offset + 4], "little")
            offset += 4
        if size < 0 or offset + size > total:
            break
        yield tag_id, level, data[offset : offset + size]
        offset += size


def clean_para_text(payload: bytes) -> str:
    text = payload.decode("utf-16le", errors="ignore")
    for artifact in ["捤獥", "汤捯", "氠瑢", "漠杳"]:
        text = text.replace(artifact, " ")
    text = re.sub(r"[ༀ-࿿Ā]+", " ", text)
    text = re.sub(r"[\u0000-\u001f]", " ", text)
    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_table_record_payload(payload: bytes) -> dict[str, Any]:
    """Parse stable, low-risk metadata from a HWP TABLE record payload.

    The binary table record contains much more geometry than this parser exposes.
    For now we only trust the consistently observed row/column counts and keep a
    short payload prefix for future decoder audits.
    """
    result: dict[str, Any] = {
        "payload_size": len(payload),
        "payload_prefix_hex": payload[:48].hex(" "),
        "source_row_count": None,
        "source_col_count": None,
        "row_cell_counts": [],
        "row_cell_count_total": 0,
    }
    if len(payload) >= 8:
        row_count = int.from_bytes(payload[4:6], "little")
        col_count = int.from_bytes(payload[6:8], "little")
        if 0 < row_count <= 2000:
            result["source_row_count"] = row_count
        if 0 < col_count <= 2000:
            result["source_col_count"] = col_count
        if (
            result["source_row_count"]
            and result["source_col_count"]
            and len(payload) >= 18 + row_count * 2
        ):
            counts = [
                int.from_bytes(payload[offset : offset + 2], "little")
                for offset in range(18, 18 + row_count * 2, 2)
            ]
            if all(0 < count <= col_count for count in counts):
                result["row_cell_counts"] = counts
                result["row_cell_count_total"] = sum(counts)
    return result


def _distributed_col_spans(col_count: int, cell_count: int) -> list[int]:
    if col_count <= 0 or cell_count <= 0 or cell_count > col_count:
        return []
    base = col_count // cell_count
    remainder = col_count % cell_count
    return [base + (1 if index < remainder else 0) for index in range(cell_count)]


def _append_cell_text(rows: list[list[str]], row_index: int, col_index: int, text: str) -> None:
    if not rows or not text:
        return
    existing = rows[row_index][col_index]
    rows[row_index][col_index] = f"{existing}\n{text}" if existing else text


def _parse_row_col_counts(source_row_count: object, source_col_count: object) -> tuple[int, int]:
    try:
        return int(source_row_count or 0), int(source_col_count or 0)
    except (TypeError, ValueError):
        return 0, 0


def _parse_cell_counts(row_cell_counts: object) -> list[int]:
    if not isinstance(row_cell_counts, list):
        return []
    counts = []
    for value in row_cell_counts:
        try:
            counts.append(int(value))
        except (TypeError, ValueError):
            return []
    return counts


def _reconstruct_rows_by_cell_counts(
    paragraphs: list[str], counts: list[int], row_count: int, col_count: int
) -> tuple[list[list[str]], dict[str, dict[str, int]], list[str]] | None:
    rows = [["" for _col in range(col_count)] for _row in range(row_count)]
    merged_cells: dict[str, dict[str, int]] = {}
    covered_cells: list[str] = []
    paragraph_index = 0
    last_anchor = (row_count - 1, 0)
    for row_index, cell_count in enumerate(counts):
        spans = _distributed_col_spans(col_count, cell_count)
        if not spans:
            return None
        col_index = 0
        for col_span in spans:
            if paragraph_index < len(paragraphs):
                rows[row_index][col_index] = paragraphs[paragraph_index]
                paragraph_index += 1
            last_anchor = (row_index, col_index)
            if col_span > 1:
                merged_cells[f"{row_index},{col_index}"] = {"colSpan": col_span, "rowSpan": 1}
                covered_cells.extend(
                    f"{row_index},{covered_col}"
                    for covered_col in range(col_index + 1, min(col_index + col_span, col_count))
                )
            col_index += col_span
    for paragraph in paragraphs[paragraph_index:]:
        _append_cell_text(rows, last_anchor[0], last_anchor[1], paragraph)
    return rows, merged_cells, covered_cells


def _reconstruct_rows_by_grid(
    paragraphs: list[str], row_count: int, col_count: int
) -> list[list[str]]:
    rows = [["" for _col in range(col_count)] for _row in range(row_count)]
    capacity = row_count * col_count
    for index, paragraph in enumerate(paragraphs):
        if index < capacity:
            rows[index // col_count][index % col_count] = paragraph
        else:
            existing = rows[-1][-1]
            rows[-1][-1] = f"{existing}\n{paragraph}" if existing else paragraph
    return rows


def reconstruct_table_rows(
    paragraphs: list[str],
    source_row_count: object = None,
    source_col_count: object = None,
    row_cell_counts: object = None,
) -> tuple[list[list[str]], str, dict[str, Any]]:
    row_count, col_count = _parse_row_col_counts(source_row_count, source_col_count)
    counts = _parse_cell_counts(row_cell_counts)
    if (
        row_count > 0
        and col_count > 0
        and len(counts) == row_count
        and sum(counts) > 0
        and all(0 < count <= col_count for count in counts)
    ):
        reconstructed = _reconstruct_rows_by_cell_counts(paragraphs, counts, row_count, col_count)
        if reconstructed is None:
            return reconstruct_table_rows(paragraphs, source_row_count, source_col_count)
        rows, merged_cells, covered_cells = reconstructed
        defaults = {"mergedCells": merged_cells, "coveredCells": covered_cells}
        return rows, "source_row_cell_counts", defaults
    if row_count > 0 and col_count > 0:
        rows = _reconstruct_rows_by_grid(paragraphs, row_count, col_count)
        return rows, "source_grid_row_major", {}
    return [[paragraph] for paragraph in paragraphs], "one_text_paragraph_per_row", {}


def finalize_table_block(block: dict[str, Any]) -> dict[str, Any]:
    paragraphs = [str(item) for item in block.get("paragraphs", []) if str(item)]
    rows, reconstruction, defaults = reconstruct_table_rows(
        paragraphs,
        block.get("source_row_count"),
        block.get("source_col_count"),
        block.get("row_cell_counts"),
    )
    block["rows"] = rows
    block["reconstruction"] = reconstruction
    block["reconstructed_row_count"] = len(rows)
    block["reconstructed_col_count"] = max((len(row) for row in rows), default=0)
    if defaults:
        block.update(defaults)
    return block


def _extract_section_record_data(
    ole: olefile.OleFileIO,
    name: str,
    header: dict[str, Any],
    record_counts: Counter,
) -> dict[str, Any]:
    raw = ole.openstream(name).read()
    data = decompress_if_needed(raw, header["compressed"])
    texts = []
    blocks: list[dict[str, Any]] = []
    active_table: dict[str, Any] | None = None
    per_section = Counter()
    for record_index, (tag_id, level, payload) in enumerate(iter_records(data)):
        record_counts[tag_id] += 1
        per_section[tag_id] += 1
        if tag_id == 77:
            if active_table is not None and active_table["paragraphs"]:
                blocks.append(finalize_table_block(active_table))
            table_meta = parse_table_record_payload(payload)
            active_table = {
                "type": "table",
                "section": name,
                "record_index": record_index,
                "level": level,
                **table_meta,
                "rows": [],
                "paragraphs": [],
                "reconstruction": "one_text_paragraph_per_row",
            }
        if tag_id == HWPTAG_PARA_TEXT:
            para = clean_para_text(payload)
            if para:
                texts.append(para)
                if active_table is not None and level > int(active_table.get("level", -1)):
                    active_table["paragraphs"].append(para)
                else:
                    if active_table is not None and active_table["paragraphs"]:
                        blocks.append(finalize_table_block(active_table))
                        active_table = None
                    blocks.append({"type": "paragraph", "text": para})
    if active_table is not None and active_table["paragraphs"]:
        blocks.append(finalize_table_block(active_table))
    section_text = normalize_text("\n".join(texts))
    section_table_blocks = [block for block in blocks if block.get("type") == "table"]
    return {
        "name": name,
        "paragraphs": len(texts),
        "text": section_text,
        "record_counts": dict(per_section),
        "blocks": blocks,
        "table_blocks": section_table_blocks,
    }


def _infer_table_reconstruction_mode(table_blocks: list[dict[str, Any]]) -> str:
    if any(block.get("reconstruction") == "source_row_cell_counts" for block in table_blocks):
        return "source_row_cell_counts"
    if any(block.get("reconstruction") == "source_grid_row_major" for block in table_blocks):
        return "source_grid_row_major"
    return "one_text_paragraph_per_row"


def _build_table_shapes(table_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "section": block.get("section"),
            "record_index": block.get("record_index"),
            "source_row_count": block.get("source_row_count"),
            "source_col_count": block.get("source_col_count"),
            "row_cell_counts": block.get("row_cell_counts"),
            "row_cell_count_total": block.get("row_cell_count_total"),
            "reconstruction": block.get("reconstruction"),
            "reconstructed_row_count": block.get(
                "reconstructed_row_count", len(block.get("rows", []))
            ),
            "reconstructed_col_count": block.get(
                "reconstructed_col_count",
                max((len(row) for row in block.get("rows", [])), default=0),
            ),
            "payload_size": block.get("payload_size"),
        }
        for block in table_blocks
    ]


def _build_feature_inventory(
    section_names: list[str],
    bindata_streams: list[str],
    table_blocks: list[dict[str, Any]],
    record_counts: Counter,
    section_record_counts: dict[str, dict[int, int]],
) -> dict[str, Any]:
    risk_tags = {
        str(tag): {
            "name": HWP_RECORD_TAGS.get(tag, f"UNKNOWN_{tag}"),
            "count": count,
        }
        for tag, count in sorted(record_counts.items())
        if tag in FIDELITY_RISK_TAGS or tag not in TEXT_ONLY_SUPPORTED_TAGS
    }
    return {
        "section_count": len(section_names),
        "bindata_count": len(bindata_streams),
        "bindata_streams": bindata_streams,
        "table_count": len(table_blocks),
        "reconstructed_table_count": len(table_blocks),
        "table_reconstruction": _infer_table_reconstruction_mode(table_blocks),
        "table_shapes": _build_table_shapes(table_blocks),
        "risk_record_tags": risk_tags,
        "section_record_counts": {
            name: {str(k): v for k, v in counts.items()}
            for name, counts in section_record_counts.items()
        },
    }


def extract_hwp_text(path: Path) -> dict[str, Any]:
    if path.read_bytes()[:8] != HWP_SIGNATURE:
        return {"ok": False, "error": "INPUT_NOT_HWP", "text": "", "sections": []}
    try:
        ole = olefile.OleFileIO(str(path))
    except Exception as exc:  # ruff: ignore[blind-except]
        return {"ok": False, "error": f"OLE_OPEN_FAILED: {exc}", "text": "", "sections": []}
    with ole:
        header = read_file_header(ole)
        if header["encrypted"]:
            return {
                "ok": False,
                "error": "ENCRYPTED_HWP",
                "header": header,
                "text": "",
                "sections": [],
            }
        section_names = []
        for item in ole.listdir(streams=True, storages=False):
            name = "/".join(item)
            if len(item) == 2 and item[0] == "BodyText" and item[1].startswith("Section"):
                section_names.append(name)
        section_names.sort(key=lambda value: int(re.sub(r"\D", "", value) or 0))
        sections = []
        full_parts = []
        table_blocks = []
        record_counts = Counter()
        section_record_counts: dict[str, dict[int, int]] = {}
        for name in section_names:
            section_data = _extract_section_record_data(ole, name, header, record_counts)
            section_record_counts[name] = section_data["record_counts"]
            table_blocks.extend(section_data["table_blocks"])
            sections.append(section_data)
            if section_data["text"]:
                full_parts.append(section_data["text"])
        full_text = normalize_text("\n".join(full_parts))
        bindata_streams = [
            "/".join(item)
            for item in ole.listdir(streams=True, storages=False)
            if item and item[0] == "BinData"
        ]
        feature_inventory = _build_feature_inventory(
            section_names, bindata_streams, table_blocks, record_counts, section_record_counts
        )
        return {
            "ok": bool(full_text),
            "error": "" if full_text else "NO_TEXT_EXTRACTED",
            "header": header,
            "sections": sections,
            "record_counts": dict(record_counts),
            "record_tag_names": {
                str(tag): HWP_RECORD_TAGS.get(tag, f"UNKNOWN_{tag}")
                for tag in sorted(record_counts)
            },
            "feature_inventory": feature_inventory,
            "text": full_text,
        }


def split_candidate_lines(text: str) -> list[str]:
    rough = re.split(r"[\n\r]| {2,}|[□■※]", text)
    lines = []
    for item in rough:
        item = re.sub(r"\s+", " ", item).strip(" :-ㆍ·,")
        if 2 <= len(item) <= 80:
            lines.append(item)
    return lines


def extract_fields_from_text(text: str) -> list[str]:
    fields = []
    lines = split_candidate_lines(text)
    for line in lines:
        for keyword in FIELD_KEYWORDS:
            if keyword in line:
                fields.append(keyword)
        if re.fullmatch(r"[가-힣A-Za-z0-9ㆍ·()/ ]{2,20}", line) and any(
            hint in line
            for hint in [
                "명",
                "자",
                "일",
                "번호",
                "주소",
                "기간",
                "면적",
                "용도",
                "종류",
                "위치",
                "능력",
            ]
        ):
            fields.append(line)
    result = []
    for field in fields:
        field = re.sub(r"\s+", " ", field).strip()
        if field and field not in result:
            result.append(field)
    return result


def extract_attachments_from_text(text: str) -> list[str]:
    attachments = []
    lines = split_candidate_lines(text)
    capture = False
    for line in lines:
        if any(keyword in line for keyword in ["첨부서류", "구비서류", "제출서류"]):
            capture = True
            attachments.append(line)
            continue
        if capture and len(attachments) < 20:
            if any(keyword in line for keyword in ATTACHMENT_KEYWORDS) or re.match(
                r"^\d+[.)]", line
            ):
                attachments.append(line)
        if capture and any(term in line for term in ["처리절차", "작성방법", "유의사항"]):
            capture = False
    for line in lines:
        if any(keyword in line for keyword in ATTACHMENT_KEYWORDS):
            attachments.append(line)
    result = []
    for item in attachments:
        item = re.sub(r"\s+", " ", item).strip()
        if 2 <= len(item) <= 120 and item not in result:
            result.append(item)
    return result[:30]


def safe_text_filename(value: object, limit: int = 80) -> str:
    cleaned = INVALID_FILENAME_RE.sub("_", str(value or "untitled")).strip(" ._")
    return (cleaned or "untitled")[:limit]


def read_index(package_dir: Path) -> list[dict[str, str]]:
    path = package_dir / "00_목차" / "공종별_기관제출서식_인덱스.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def audit_package(package_dir: Path) -> list[dict[str, Any]]:
    rows = read_index(package_dir)
    results = []
    text_dir = package_dir / "04_본문추출" / "본문텍스트"
    text_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        file_path = package_dir / row["file_path"]
        extracted = extract_hwp_text(file_path)
        fields = extract_fields_from_text(extracted.get("text", ""))
        attachments = extract_attachments_from_text(extracted.get("text", ""))
        text_rel = ""
        if extracted.get("text"):
            safe_title = safe_text_filename(row.get("title", "untitled"))
            text_path = text_dir / f"{int(row['no']):03d}_{safe_title}.txt"
            text_path.write_text(extracted["text"], encoding="utf-8")
            text_rel = str(text_path.relative_to(package_dir))
        results.append({
            "no": row["no"],
            "trade": row["trade"],
            "agency": row["agency"],
            "phase": row["phase"],
            "title": row["title"],
            "file_path": row["file_path"],
            "extract_ok": extracted["ok"],
            "extract_error": extracted.get("error", ""),
            "paragraph_count": sum(
                section.get("paragraphs", 0) for section in extracted.get("sections", [])
            ),
            "text_length": len(extracted.get("text", "")),
            "body_field_candidates": fields,
            "body_field_count": len(fields),
            "body_attachment_candidates": attachments,
            "body_attachment_count": len(attachments),
            "text_path": text_rel,
        })
    return results


def write_outputs(package_dir: Path, rows: list[dict[str, Any]]) -> None:
    out_dir = package_dir / "04_본문추출"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "본문기반_입력항목.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    fields = [
        "no",
        "trade",
        "agency",
        "phase",
        "title",
        "file_path",
        "extract_ok",
        "extract_error",
        "paragraph_count",
        "text_length",
        "body_field_count",
        "body_field_candidates",
        "body_attachment_count",
        "body_attachment_candidates",
        "text_path",
    ]
    with (out_dir / "본문기반_입력항목.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                k: "|".join(map(str, row[k])) if isinstance(row.get(k), list) else row.get(k, "")
                for k in fields
            })
    by_trade = defaultdict(list)
    for row in rows:
        by_trade[row["trade"]].append(row)
    lines = [
        "# 본문 기반 입력항목 추출 보고서",
        "",
        f"- 대상 문서: {len(rows)}개",
        f"- 본문 추출 성공: {sum(1 for row in rows if row['extract_ok'])}개",
        f"- 본문 추출 실패: {sum(1 for row in rows if not row['extract_ok'])}개",
        f"- 평균 본문 라벨 후보: {round(sum(row['body_field_count'] for row in rows) / max(len(rows), 1), 1)}개",
        "",
        "## 공종별 요약",
        "",
        "| 공종 | 문서 | 추출성공 | 평균 라벨 | 평균 첨부후보 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for trade in sorted(by_trade):
        items = by_trade[trade]
        lines.append(
            f"| {trade} | {len(items)} | {sum(1 for row in items if row['extract_ok'])} | "
            f"{round(sum(row['body_field_count'] for row in items) / len(items), 1)} | "
            f"{round(sum(row['body_attachment_count'] for row in items) / len(items), 1)} |"
        )
    lines.extend([
        "",
        "## 문서별 상세",
        "",
        "| No | 공종 | 서식 | 본문라벨 | 첨부후보 | 본문텍스트 |",
        "| ---: | --- | --- | ---: | ---: | --- |",
    ])
    for row in rows:
        lines.append(
            f"| {row['no']} | {row['trade']} | {row['title']} | {row['body_field_count']} | "
            f"{row['body_attachment_count']} | `{row['text_path']}` |"
        )
    (out_dir / "본문기반_입력항목_보고서.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", default="deliverables/기관제출서류_기관별확장_로컬패키지")
    args = parser.parse_args()
    package_dir = ROOT / args.package_dir
    rows = audit_package(package_dir)
    write_outputs(package_dir, rows)
    print(f"package_dir={package_dir}")
    print(f"documents={len(rows)}")
    print(f"extract_ok={sum(1 for row in rows if row['extract_ok'])}")
    print(f"extract_failed={sum(1 for row in rows if not row['extract_ok'])}")
    print(f"output_dir={package_dir / '04_본문추출'}")


if __name__ == "__main__":
    main()
