"""WebOfficeDocumentModel v1 — read-only viewer 최소 스키마.

설계서 §4 DocumentModel schema 의 RO-VIEW 부분만 구현. 편집 명령 /
commandLog / dirty 등 편집 관련 필드는 Phase 2 이상에서 도입.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
from . import SCHEMA_VERSION, ENGINE_VERSION


@dataclass
class WebOfficeTextRun:
    runId: str
    text: str
    charPrIDRef: str | None = None


@dataclass
class WebOfficeParagraph:
    paragraphId: str
    text: str
    parPrIDRef: str | None = None
    runs: list[WebOfficeTextRun] = field(default_factory=list)
    containerScope: dict | None = None  # NEW (RO_VIEW_PARAGRAPH_01)


@dataclass
class WebOfficeCell:
    cellId: str
    tableId: str
    row: int
    col: int
    rowSpan: int = 1
    colSpan: int = 1
    isCoveredByMerge: bool = False
    isMergedOrigin: bool = False
    header: str | None = None
    headerCell: bool | None = None
    cellMargin: dict[str, Any] = field(default_factory=dict)
    paragraphs: list[WebOfficeParagraph] = field(default_factory=list)
    text: str = ""


@dataclass
class WebOfficeTable:
    tableId: str
    blockId: str
    sectionIndex: int
    rowCount: int
    colCount: int
    visualColCount: int
    hasMergedCells: bool = False
    inMargin: dict[str, Any] = field(default_factory=dict)
    outMargin: dict[str, Any] = field(default_factory=dict)
    cellIds: list[str] = field(default_factory=list)


@dataclass
class WebOfficeBlock:
    blockId: str
    type: str        # "paragraph" | "table" | "object"
    sectionIndex: int
    blockIndex: int
    ref: str | None = None     # paragraphId / tableId / objectId


@dataclass
class WebOfficeSection:
    sectionIndex: int
    sourceXmlPath: str | None = None


@dataclass
class WebOfficeObject:
    objectId: str
    sectionIndex: int
    kind: str         # "image" | "shape" | "ole" | "unknown"
    placeholder: bool = True


@dataclass
class WebOfficeStyles:
    charPrCount: int = 0
    parPrCount: int = 0
    borderFillCount: int = 0
    charPrDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    paraPrDefs: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class WebOfficeDocumentModel:
    schemaVersion: str
    engineVersion: str
    requestId: str
    documentId: str
    sourceDocumentHash: str
    sourceDocumentPath: str
    sections: list[WebOfficeSection] = field(default_factory=list)
    blocks: list[WebOfficeBlock] = field(default_factory=list)
    paragraphs: list[WebOfficeParagraph] = field(default_factory=list)
    tables: list[WebOfficeTable] = field(default_factory=list)
    cells: list[WebOfficeCell] = field(default_factory=list)
    objects: list[WebOfficeObject] = field(default_factory=list)
    styles: WebOfficeStyles = field(default_factory=WebOfficeStyles)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def fixed_schema_version() -> str:
        return SCHEMA_VERSION

    @staticmethod
    def fixed_engine_version() -> str:
        return ENGINE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
