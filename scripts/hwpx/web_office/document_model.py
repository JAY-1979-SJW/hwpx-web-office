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
    # EDU-OFFICE-CONTRACT-01: 외부 소비자(edu 플랫폼 office_contract.py)가
    # documentModel.cells[].tableIndex 를 계약으로 명시하고 EditCommand의
    # forward/inverse set_cells[].table 값으로 그대로 쓴다. tableId(문자열)만
    # 있으면 소비자가 별도로 tables 리스트를 순회해 인덱스를 derive해야
    # 하는데, 이 매핑 없이 tableIndex를 직접 읽으면 undefined가 되어
    # 저장이 깨진다(실측: 37번 폴더 통합 실패 원인 확인) — 셀 생성 시점에
    # 인덱스를 함께 채워 계약을 실제로 만족시킨다.
    tableIndex: int
    row: int
    col: int
    rowSpan: int = 1
    colSpan: int = 1
    isCoveredByMerge: bool = False
    isMergedOrigin: bool = False
    header: str | None = None
    headerCell: bool | None = None
    borderFillIDRef: str | None = None
    borderFill: dict[str, Any] = field(default_factory=dict)
    cellMargin: dict[str, Any] = field(default_factory=dict)
    # WEB-OFFICE-RO-VIEW-TABLE-FORMAT-PRECISION-01: 셀 실측 크기(cellSz
    # width/height, HWPUNIT)와 수직정렬(subList vertAlign) — 표 서식 정밀화.
    cellSize: dict[str, Any] = field(default_factory=dict)
    vertAlign: str | None = None
    paragraphs: list[WebOfficeParagraph] = field(default_factory=list)
    text: str = ""
    # 파싱 시 입력칸 분류 — 프런트는 이 값을 단일 진실로 사용한다.
    # 문서에 [입력필요: ...] 마커가 있으면 XML 그대로(마커 셀만 입력칸),
    # 없으면 셀 서식 기반(빈칸+비헤더+비커버+무채색).
    isInputCell: bool = False
    # 마커 문서의 필드 라벨([입력필요: 문서번호] → "문서번호") — 뷰어가
    # placeholder 로 표시. 마커 없는 문서는 None.
    inputLabel: str | None = None
    # 사람 편집 가능 여부 — isInputCell(AI 자동입력 대상, 빈칸 전용)과는
    # 별개다. 이미 텍스트가 있는 칸도 사람은 클릭해 고치거나 지울 수
    # 있어야 하므로, 헤더/병합피복만 걸러내고 텍스트 유무는 안 본다.
    # AI-fill 가드("이미 채워진 칸은 안 덮어씀")는 isInputCell 로만 유지.
    isEditable: bool = False


@dataclass
class WebOfficeTable:
    tableId: str
    blockId: str
    sectionIndex: int
    rowCount: int
    colCount: int
    visualColCount: int
    hasMergedCells: bool = False
    tableSize: dict[str, Any] = field(default_factory=dict)
    position: dict[str, Any] = field(default_factory=dict)
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
    secPr: dict[str, Any] = field(default_factory=dict)
    startNum: dict[str, Any] = field(default_factory=dict)
    pagePr: dict[str, Any] = field(default_factory=dict)
    grid: dict[str, Any] = field(default_factory=dict)
    lineNumberShape: dict[str, Any] = field(default_factory=dict)
    pageBorderFills: list[dict[str, Any]] = field(default_factory=list)
    noteNumbering: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebOfficeObject:
    objectId: str
    sectionIndex: int
    kind: str         # "image" | "shape" | "ole" | "unknown"
    placeholder: bool = True
    rawAttrs: dict[str, Any] = field(default_factory=dict)
    position: dict[str, Any] = field(default_factory=dict)
    colPr: dict[str, Any] = field(default_factory=dict)
    containerScope: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebOfficeStyles:
    charPrCount: int = 0
    parPrCount: int = 0
    borderFillCount: int = 0
    styleCount: int = 0
    charPrDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    paraPrDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    fontFaceDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    styleDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    borderFillDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    beginNum: dict[str, Any] = field(default_factory=dict)
    numberingDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    memoPrDefs: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadataContainers: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class WebOfficeDocumentModel:
    schemaVersion: str
    engineVersion: str
    requestId: str
    documentId: str
    sourceDocumentHash: str
    sourceDocumentPath: str
    packageMetadata: dict[str, Any] = field(default_factory=dict)
    applicationSettings: dict[str, Any] = field(default_factory=dict)
    revisionTracking: dict[str, Any] = field(default_factory=dict)
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
