"""HWPX Parser V2 — 통합 파서 엔진.

parse_hwpx_v2(path) → ParserV2Result

처리 순서:
1. package_reader
2. style_parser
3. block_parser (section별)
4. table_parser (section별)
5. layout_classifier (table별)
6. input_slot_detector
7. ParserV2Result 조립

원칙: read-only, fail-fast 금지, crash 최소화.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .block_parser import parse_blocks_from_section
from .errors import ErrCode, WarnCode
from .input_slot_detector import detect_input_slots
from .layout_classifier import enrich_table_layout
from .object_parser import parse_bin_data_from_header, parse_objects_from_section
from .package_reader import read_header_xml, read_package_info, read_section_xmls
from .parser_contract import (
    DocumentInfo,
    ParserError,
    ParserV2Result,
    ParserWarning,
    SemanticHints,
    make_request_id,
)
from .schedule_detector import detect_schedule_structure
from .style_parser import (
    enrich_style_info,
    parse_style_summary,
)
from .table_parser import parse_tables_from_section


def _load_style_info(path: Path, result: ParserV2Result) -> tuple[object, bytes | None]:
    header_raw: bytes | None = None
    try:
        header_raw = read_header_xml(path)
        if header_raw:
            style_info = parse_style_summary(header_raw)
        else:
            from .parser_contract import StyleInfo

            style_info = StyleInfo()
    except Exception as exc:  # ruff: ignore[blind-except] — 원인 무관하게 warning 기록 후 기본 StyleInfo로 계속
        from .parser_contract import StyleInfo

        style_info = StyleInfo()
        result.warnings.append(ParserWarning(WarnCode.SECTION_PARSE_WARN, f"header.xml: {exc}"))
    return style_info, header_raw


def _load_sections_and_enrich(
    path: Path, header_raw: bytes | None, style_info: object, result: ParserV2Result
) -> dict[str, bytes]:
    # ── 3. section XML 로드 ──────────────────────────────────────────────────
    section_xmls_map: dict[str, bytes] = {}
    try:
        section_xmls_map = read_section_xmls(path)
        result.sections = sorted(section_xmls_map.keys())
    except Exception as exc:  # ruff: ignore[blind-except] — 원인 무관하게 error 기록 후 계속
        result.errors.append(ParserError(ErrCode.SECTION_READ_FAIL, str(exc)))

    # style 보강 (section refs)
    try:
        enrich_style_info(style_info, list(section_xmls_map.values()))
    except Exception as exc:  # ruff: ignore[blind-except] — 형제 블록들과 동일하게 원인 무관 warning 기록
        result.warnings.append(ParserWarning(WarnCode.SECTION_PARSE_WARN, f"style_enrich: {exc}"))
    result.styles = style_info

    # ── 3.5 binData 파싱 (header.xml) ─────────────────────────────────────────
    try:
        if header_raw:
            result.binData = parse_bin_data_from_header(header_raw)
    except Exception as exc:  # ruff: ignore[blind-except] — 원인 무관하게 warning 기록 후 계속
        result.warnings.append(ParserWarning(WarnCode.SECTION_PARSE_WARN, f"binData: {exc}"))

    return section_xmls_map


def _parse_all_sections(
    section_xmls_map: dict[str, bytes], style_defs: dict, result: ParserV2Result
) -> tuple[list, list, list]:
    # ── 4. block + table + object 파싱 ───────────────────────────────────────
    all_blocks = []
    all_tables = []
    all_objects = []
    block_offset = 0

    for si, (section_path, raw) in enumerate(sorted(section_xmls_map.items())):
        try:
            blocks = parse_blocks_from_section(raw, si, source_path=section_path)
            all_blocks.extend(blocks)
        except Exception as exc:  # ruff: ignore[blind-except] — 이 섹션만 warning, 나머지 섹션 계속 파싱
            result.warnings.append(
                ParserWarning(WarnCode.SECTION_PARSE_WARN, f"{section_path}: {exc}")
            )
        try:
            tables = parse_tables_from_section(
                raw, si, start_block_index=block_offset, style_defs=style_defs
            )
            all_tables.extend(tables)
            block_offset += len(tables)
        except Exception as exc:  # ruff: ignore[blind-except] — 이 섹션만 warning, 나머지 섹션 계속 파싱
            result.warnings.append(
                ParserWarning(WarnCode.TABLE_PARSE_WARN, f"{section_path}: {exc}")
            )
        try:
            objs = parse_objects_from_section(raw, si, source_path=section_path)
            all_objects.extend(objs)
        except Exception as exc:  # ruff: ignore[blind-except] — 이 섹션만 warning, 나머지 섹션 계속 파싱
            result.warnings.append(
                ParserWarning(WarnCode.SECTION_PARSE_WARN, f"object_parser {section_path}: {exc}")
            )

    return all_blocks, all_tables, all_objects


def _classify_table_layouts(all_tables: list) -> None:
    # ── 5. layout 분류 ───────────────────────────────────────────────────────
    for table in all_tables:
        try:
            enrich_table_layout(table)
        except Exception:  # ruff: ignore[blind-except] — 이 표만 classifier_error 로 기록, 나머지 표 계속 분류
            table.layoutGuess = "unknown"
            table.classificationEvidence = ["classifier_error"]


def _detect_slots_and_schedules(all_tables: list, result: ParserV2Result) -> None:
    # ── 6. input slot 탐지 ───────────────────────────────────────────────────
    try:
        slots = detect_input_slots(all_tables)
        result.inputSlotCandidates = slots
    except Exception as exc:  # ruff: ignore[blind-except] — 원인 무관하게 warning 기록 후 계속
        result.warnings.append(ParserWarning(WarnCode.LOW_CONFIDENCE_SLOT, str(exc)))

    # ── 7. schedule 구조 탐지 ────────────────────────────────────────────────
    # all_tables를 직접 전달 (result.tables는 step 8에서 할당되므로)
    try:

        class _TableHolder:
            tables = all_tables

        result.schedules = detect_schedule_structure(_TableHolder())
    except Exception as exc:  # ruff: ignore[blind-except] — 원인 무관하게 warning 기록 후 계속
        result.warnings.append(
            ParserWarning(WarnCode.LOW_CONFIDENCE_SLOT, f"schedule_detector: {exc}")
        )


def parse_hwpx_v2(path: Path, request_id: str | None = None) -> ParserV2Result:
    """HWPX 파일을 읽어 ParserV2Result를 반환. 실패해도 최대한 구조를 채워 반환."""
    rid = request_id or make_request_id()
    file_name = hashlib.sha256(path.name.encode()).hexdigest()[:16]
    result = ParserV2Result(requestId=rid, inputFileName=file_name)

    # ── 1. package 정보 ─────────────────────────────────────────────────────
    try:
        pkg_info, pkg_warns = read_package_info(path)
        result.package = pkg_info
        result.warnings.extend(pkg_warns)
    except Exception as exc:  # ruff: ignore[blind-except] — 원인 무관하게 error 기록 후 최대한 구조 반환
        result.errors.append(ParserError(ErrCode.ZIP_OPEN_FAIL, str(exc)))
        return result

    if not result.package.xmlDecodeOk:
        result.warnings.append(ParserWarning(WarnCode.PACKAGE_STRUCTURE_WARN, "xmlDecodeOk=False"))

    # ── 2. style 정보 ────────────────────────────────────────────────────────
    style_info, header_raw = _load_style_info(path, result)

    # cell enrichment에 전달할 style def 딕셔너리
    _style_defs: dict = {
        "charPr": style_info.charPr,
        "paraPr": style_info.paraPr,
        "borderFill": style_info.borderFill,
    }

    section_xmls_map = _load_sections_and_enrich(path, header_raw, style_info, result)

    all_blocks, all_tables, all_objects = _parse_all_sections(section_xmls_map, _style_defs, result)
    result.objects = all_objects

    _classify_table_layouts(all_tables)
    _detect_slots_and_schedules(all_tables, result)

    # ── 8. document 요약 ────────────────────────────────────────────────────
    para_blocks = [b for b in all_blocks if b.type in ("paragraph", "page_marker")]
    full_text_parts = [b.text for b in para_blocks if b.text]
    title_candidate = full_text_parts[0] if full_text_parts else None

    result.document = DocumentInfo(
        titleCandidate=title_candidate,
        fullText=" ".join(full_text_parts)[:3000],
        paragraphCount=len(para_blocks),
        blockCount=len(all_blocks),
        tableCount=len(all_tables),
        imageCount=sum(1 for b in all_blocks if b.type == "image"),
        drawingCount=sum(1 for b in all_blocks if b.type == "drawing"),
    )

    result.blocks = all_blocks
    result.tables = all_tables

    # semantic hints (skeleton: 기본값만)
    result.semanticHints = SemanticHints(
        documentTypeCandidates=[],
        businessTypeCandidates=[],
    )

    return result
