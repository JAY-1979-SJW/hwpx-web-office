"""HWPX Parser Engine V2 — scripts/hwpx/parser 패키지.

read-only HWPX 구조 분석 엔진.
원본 수정 없음 / write_package / apply_edit_plan 호출 없음.
"""
from .parser_engine import parse_hwpx_v2
from .parser_contract import (
    ParserV2Result, PackageInfo, DocumentInfo,
    BlockInfo, TableInfo, CellInfo, StyleInfo,
    SemanticHints, InputSlotCandidate,
    ParserWarning, ParserError,
    SCHEMA_VERSION, ENGINE_VERSION,
)
from .errors import WarnCode, ErrCode

__all__ = [
    "parse_hwpx_v2",
    "ParserV2Result", "PackageInfo", "DocumentInfo",
    "BlockInfo", "TableInfo", "CellInfo", "StyleInfo",
    "SemanticHints", "InputSlotCandidate",
    "ParserWarning", "ParserError",
    "SCHEMA_VERSION", "ENGINE_VERSION",
    "WarnCode", "ErrCode",
]
