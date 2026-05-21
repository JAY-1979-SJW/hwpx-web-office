"""HWPX Parser V2 — 출력 JSON 계약 dataclass 정의.

docs/contracts/hwpx_parser_engine_v2_contract.md 와 필드명이 일치해야 한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "v2"
ENGINE_VERSION = "0.1.0"


@dataclass
class ParserWarning:
    code: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


@dataclass
class ParserError:
    code: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "detail": self.detail}


@dataclass
class PackageInfo:
    entryCount: int = 0
    hasMimetype: bool = False
    mimetypeValue: str = ""
    mimetypeCompressType: int = -1
    hasContentHpf: bool = False
    hasContainerXml: bool = False
    hasHeaderXml: bool = False
    sectionFileCount: int = 0
    xmlDecodeOk: bool = True
    packageWarnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entryCount": self.entryCount,
            "hasMimetype": self.hasMimetype,
            "mimetypeValue": self.mimetypeValue,
            "mimetypeCompressType": self.mimetypeCompressType,
            "hasContentHpf": self.hasContentHpf,
            "hasContainerXml": self.hasContainerXml,
            "hasHeaderXml": self.hasHeaderXml,
            "sectionFileCount": self.sectionFileCount,
            "xmlDecodeOk": self.xmlDecodeOk,
            "packageWarnings": self.packageWarnings,
        }


@dataclass
class DocumentInfo:
    titleCandidate: str | None = None
    fullText: str = ""
    paragraphCount: int = 0
    blockCount: int = 0
    tableCount: int = 0
    imageCount: int = 0
    drawingCount: int = 0

    def to_dict(self) -> dict:
        return {
            "titleCandidate": self.titleCandidate,
            "fullText": self.fullText[:2000],
            "paragraphCount": self.paragraphCount,
            "blockCount": self.blockCount,
            "tableCount": self.tableCount,
            "imageCount": self.imageCount,
            "drawingCount": self.drawingCount,
        }


@dataclass
class BlockInfo:
    blockIndex: int = 0
    sectionIndex: int = 0
    type: str = "unknown"   # paragraph / table / image / drawing / page_marker / unknown
    text: str | None = None
    tableId: str | None = None
    sourceXmlPath: str = ""
    orderKey: str = ""

    def to_dict(self) -> dict:
        return {
            "blockIndex": self.blockIndex,
            "sectionIndex": self.sectionIndex,
            "type": self.type,
            "text": self.text,
            "tableId": self.tableId,
            "sourceXmlPath": self.sourceXmlPath,
            "orderKey": self.orderKey,
        }


@dataclass
class CellInfo:
    cellId: str = ""
    row: int = 0
    col: int = 0
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1
    isMergedOrigin: bool = False
    isCoveredByMerge: bool = False
    originCellId: str | None = None
    text: str = ""
    normalizedText: str = ""
    paragraphs: list[str] = field(default_factory=list)
    charPrIDRefs: list[str] = field(default_factory=list)
    paraPrIDRefs: list[str] = field(default_factory=list)
    borderFillIDRef: str | None = None
    fillColor: str | None = None
    fontHeight: int | None = None
    fontSizePt: float | None = None
    fontFace: str | None = None
    fontName: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    textColor: str | None = None
    horizontalAlign: str = ""
    verticalAlign: str = ""
    marginLeft: int = 0
    marginRight: int = 0
    marginTop: int = 0
    marginBottom: int = 0
    borderSummary: str = ""
    hasNestedTable: bool = False
    nestedTableIds: list[str] = field(default_factory=list)
    isLikelyLabel: bool = False
    isLikelyInputSlot: bool = False
    warnings: list[str] = field(default_factory=list)
    styleWarnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cellId": self.cellId,
            "row": self.row,
            "col": self.col,
            "visualRow": self.visualRow,
            "visualCol": self.visualCol,
            "rowSpan": self.rowSpan,
            "colSpan": self.colSpan,
            "isMergedOrigin": self.isMergedOrigin,
            "isCoveredByMerge": self.isCoveredByMerge,
            "originCellId": self.originCellId,
            "text": self.text,
            "normalizedText": self.normalizedText,
            "paragraphs": self.paragraphs,
            "charPrIDRefs": self.charPrIDRefs,
            "paraPrIDRefs": self.paraPrIDRefs,
            "borderFillIDRef": self.borderFillIDRef,
            "fillColor": self.fillColor,
            "fontHeight": self.fontHeight,
            "fontSizePt": self.fontSizePt,
            "fontFace": self.fontFace,
            "fontName": self.fontName,
            "bold": self.bold,
            "italic": self.italic,
            "underline": self.underline,
            "textColor": self.textColor,
            "horizontalAlign": self.horizontalAlign,
            "verticalAlign": self.verticalAlign,
            "marginLeft": self.marginLeft,
            "marginRight": self.marginRight,
            "marginTop": self.marginTop,
            "marginBottom": self.marginBottom,
            "borderSummary": self.borderSummary,
            "hasNestedTable": self.hasNestedTable,
            "nestedTableIds": self.nestedTableIds,
            "isLikelyLabel": self.isLikelyLabel,
            "isLikelyInputSlot": self.isLikelyInputSlot,
            "warnings": self.warnings,
            "styleWarnings": self.styleWarnings,
        }


@dataclass
class TableInfo:
    tableId: str = ""
    sectionIndex: int = 0
    blockIndex: int = 0
    tableIndex: int = 0
    layoutGuess: str = "unknown"
    confidence: float = 0.0
    classificationEvidence: list[str] = field(default_factory=list)
    rowCount: int = 0
    colCount: int = 0
    visualRowCount: int = 0
    visualColCount: int = 0
    hasMergedCells: bool = False
    hasNestedTables: bool = False
    nestedTableCount: int = 0
    rows: list[list[str]] = field(default_factory=list)
    cells: list[CellInfo] = field(default_factory=list)
    headerRowCandidates: list[int] = field(default_factory=list)
    headerTexts: list[str] = field(default_factory=list)
    headerConfidence: float = 0.0
    inputSlotHints: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "sectionIndex": self.sectionIndex,
            "blockIndex": self.blockIndex,
            "tableIndex": self.tableIndex,
            "layoutGuess": self.layoutGuess,
            "confidence": self.confidence,
            "classificationEvidence": self.classificationEvidence,
            "rowCount": self.rowCount,
            "colCount": self.colCount,
            "visualRowCount": self.visualRowCount,
            "visualColCount": self.visualColCount,
            "hasMergedCells": self.hasMergedCells,
            "hasNestedTables": self.hasNestedTables,
            "nestedTableCount": self.nestedTableCount,
            "rows": self.rows,
            "cells": [c.to_dict() for c in self.cells],
            "headerRowCandidates": self.headerRowCandidates,
            "headerTexts": self.headerTexts,
            "headerConfidence": self.headerConfidence,
            "inputSlotHints": self.inputSlotHints,
            "warnings": self.warnings,
        }


@dataclass
class StyleInfo:
    charPrCount: int = 0
    paraPrCount: int = 0
    borderFillCount: int = 0
    charPr: dict = field(default_factory=dict)
    paraPr: dict = field(default_factory=dict)
    borderFill: dict = field(default_factory=dict)
    colorPalette: list[str] = field(default_factory=list)
    referencedCharPrIds: list[str] = field(default_factory=list)
    referencedParaPrIds: list[str] = field(default_factory=list)
    referencedBorderFillIds: list[str] = field(default_factory=list)
    danglingRefs: list[str] = field(default_factory=list)
    styleWarnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "charPr": {"count": self.charPrCount, "defs": self.charPr},
            "paraPr": {"count": self.paraPrCount, "defs": self.paraPr},
            "borderFill": {"count": self.borderFillCount, "defs": self.borderFill},
            "colorPalette": self.colorPalette,
            "referencedCharPrIds": self.referencedCharPrIds,
            "referencedParaPrIds": self.referencedParaPrIds,
            "referencedBorderFillIds": self.referencedBorderFillIds,
            "danglingRefs": self.danglingRefs,
            "styleWarnings": self.styleWarnings,
        }


@dataclass
class SemanticHints:
    detectedFields: dict[str, Any] = field(default_factory=dict)
    headerDictionary: list[dict] = field(default_factory=list)
    documentTypeCandidates: list[str] = field(default_factory=list)
    businessTypeCandidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "detectedFields": self.detectedFields,
            "headerDictionary": self.headerDictionary,
            "documentTypeCandidates": self.documentTypeCandidates,
            "businessTypeCandidates": self.businessTypeCandidates,
        }


@dataclass
class InputSlotCandidate:
    slotId: str = ""
    tableId: str = ""
    tableRole: str = "unknown"
    source: str = ""  # label_right / label_below / label_value_pair / merged_input_cell / blank_after_known_header / metadata_form_slot / data_table_append_slot / status_cell / schedule_range / manual_candidate
    labelText: str = ""
    fieldGuess: str = ""
    row: int = 0
    col: int = 0
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1
    confidence: float = 0.0
    autoEditAllowed: bool = False
    reviewRequired: bool = False
    reviewRequiredReason: str | None = None
    unsafeReason: str | None = None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "slotId": self.slotId,
            "tableId": self.tableId,
            "tableRole": self.tableRole,
            "source": self.source,
            "labelText": self.labelText,
            "fieldGuess": self.fieldGuess,
            "targetCell": {
                "tableId": self.tableId,
                "row": self.row,
                "col": self.col,
                "visualRow": self.visualRow,
                "visualCol": self.visualCol,
                "rowSpan": self.rowSpan,
                "colSpan": self.colSpan,
            },
            "row": self.row,
            "col": self.col,
            "visualRow": self.visualRow,
            "visualCol": self.visualCol,
            "rowSpan": self.rowSpan,
            "colSpan": self.colSpan,
            "confidence": self.confidence,
            "autoEditAllowed": self.autoEditAllowed,
            "reviewRequired": self.reviewRequired,
            "reviewRequiredReason": self.reviewRequiredReason,
            "unsafeReason": self.unsafeReason,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


@dataclass
class BinDataInfo:
    binId: str = ""
    href: str = ""
    format: str = ""
    sourceTag: str = "binItem"

    def to_dict(self) -> dict:
        return {
            "binId": self.binId,
            "href": self.href,
            "format": self.format,
            "sourceTag": self.sourceTag,
        }


@dataclass
class ObjectInfo:
    objectId: str = ""
    objectType: str = "unknown"   # picture / rect / line / ellipse / container / arc / curve / polygon
    sectionIndex: int = 0
    sourcePath: str = ""
    binDataRef: str | None = None
    width: int | None = None
    height: int | None = None
    posX: int | None = None
    posY: int | None = None
    rawTag: str = ""

    def to_dict(self) -> dict:
        return {
            "objectId": self.objectId,
            "objectType": self.objectType,
            "sectionIndex": self.sectionIndex,
            "sourcePath": self.sourcePath,
            "binDataRef": self.binDataRef,
            "width": self.width,
            "height": self.height,
            "posX": self.posX,
            "posY": self.posY,
            "rawTag": self.rawTag,
        }


@dataclass
class ParserV2Result:
    schemaVersion: str = SCHEMA_VERSION
    engineVersion: str = ENGINE_VERSION
    requestId: str = ""
    inputFileName: str = ""
    inputFileType: str = "hwpx"
    parserMode: str = "HWPX_XML"
    package: PackageInfo = field(default_factory=PackageInfo)
    document: DocumentInfo = field(default_factory=DocumentInfo)
    sections: list[str] = field(default_factory=list)
    blocks: list[BlockInfo] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)
    styles: StyleInfo = field(default_factory=StyleInfo)
    semanticHints: SemanticHints = field(default_factory=SemanticHints)
    inputSlotCandidates: list[InputSlotCandidate] = field(default_factory=list)
    schedules: list[ScheduleInfo] = field(default_factory=list)
    objects: list[ObjectInfo] = field(default_factory=list)
    binData: list[BinDataInfo] = field(default_factory=list)
    warnings: list[ParserWarning] = field(default_factory=list)
    errors: list[ParserError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schemaVersion": self.schemaVersion,
            "engineVersion": self.engineVersion,
            "requestId": self.requestId,
            "inputFileName": self.inputFileName,
            "inputFileType": self.inputFileType,
            "parserMode": self.parserMode,
            "package": self.package.to_dict(),
            "document": self.document.to_dict(),
            "sections": self.sections,
            "blocks": [b.to_dict() for b in self.blocks],
            "tables": [t.to_dict() for t in self.tables],
            "styles": self.styles.to_dict(),
            "semanticHints": self.semanticHints.to_dict(),
            "inputSlotCandidates": [s.to_dict() for s in self.inputSlotCandidates],
            "schedules": [s.to_dict() for s in self.schedules],
            "objects": [o.to_dict() for o in self.objects],
            "binData": [b.to_dict() for b in self.binData],
            "warnings": [w.to_dict() for w in self.warnings],
            "errors": [e.to_dict() for e in self.errors],
        }


@dataclass
class DateColumnInfo:
    col: int = 0
    label: str = ""
    normalized: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "col": self.col,
            "label": self.label,
            "normalized": self.normalized,
            "confidence": self.confidence,
        }


@dataclass
class TimeAxisInfo:
    axisDirection: str = "horizontal"
    unit: str = "unknown"
    headerRows: list[int] = field(default_factory=list)
    dateColumns: list[DateColumnInfo] = field(default_factory=list)
    monthHeaderRows: list[int] = field(default_factory=list)
    weekHeaderRows: list[int] = field(default_factory=list)
    dayHeaderRows: list[int] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "axisDirection": self.axisDirection,
            "unit": self.unit,
            "headerRows": self.headerRows,
            "dateColumns": [d.to_dict() for d in self.dateColumns],
            "monthHeaderRows": self.monthHeaderRows,
            "weekHeaderRows": self.weekHeaderRows,
            "dayHeaderRows": self.dayHeaderRows,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


@dataclass
class TaskRowInfo:
    row: int = 0
    taskName: str = ""
    trade: str = ""
    leftText: list[str] = field(default_factory=list)
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "taskName": self.taskName,
            "trade": self.trade,
            "leftText": self.leftText,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class BarRangeInfo:
    row: int = 0
    colStart: int = 0
    colEnd: int = 0
    barType: str = "unknown_bar"
    text: str = ""
    fillColor: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "row": self.row,
            "colStart": self.colStart,
            "colEnd": self.colEnd,
            "barType": self.barType,
            "text": self.text,
            "fillColor": self.fillColor,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class ProgressColumnInfo:
    col: int = -1
    headerText: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "col": self.col,
            "headerText": self.headerText,
            "confidence": self.confidence,
        }


@dataclass
class ScheduleInfo:
    tableId: str = ""
    scheduleType: str = "gantt_bar_schedule"
    confidence: float = 0.0
    timeAxis: TimeAxisInfo = field(default_factory=TimeAxisInfo)
    taskRows: list[TaskRowInfo] = field(default_factory=list)
    barRanges: list[BarRangeInfo] = field(default_factory=list)
    progressColumn: ProgressColumnInfo | None = None
    warnings: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "scheduleType": self.scheduleType,
            "confidence": self.confidence,
            "timeAxis": self.timeAxis.to_dict(),
            "taskRows": [r.to_dict() for r in self.taskRows],
            "barRanges": [b.to_dict() for b in self.barRanges],
            "progressColumn": self.progressColumn.to_dict() if self.progressColumn else None,
            "warnings": self.warnings,
            "evidence": self.evidence,
        }


@dataclass
class ScheduleDateRange:
    startDate: str = ""
    endDate: str = ""
    startLabel: str = ""
    endLabel: str = ""
    normalizedStart: str = ""
    normalizedEnd: str = ""
    unit: str = "unknown"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "startDate": self.startDate,
            "endDate": self.endDate,
            "startLabel": self.startLabel,
            "endLabel": self.endLabel,
            "normalizedStart": self.normalizedStart,
            "normalizedEnd": self.normalizedEnd,
            "unit": self.unit,
            "warnings": self.warnings,
        }


@dataclass
class ScheduleBarPlanCandidate:
    tableId: str = ""
    row: int = -1
    taskName: str = ""
    colStart: int = -1
    colEnd: int = -1
    axisUnit: str = "unknown"
    startLabel: str = ""
    endLabel: str = ""
    color: str = ""
    text: str = ""
    textAt: str = "center"
    confidence: float = 0.0
    source: str = "calculated_from_dates"
    existingBarType: str = ""
    conflict: str = "no_conflict"
    reviewRequired: bool = False
    reviewRequiredReason: str | None = None
    evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "row": self.row,
            "taskName": self.taskName,
            "colStart": self.colStart,
            "colEnd": self.colEnd,
            "axisUnit": self.axisUnit,
            "startLabel": self.startLabel,
            "endLabel": self.endLabel,
            "color": self.color,
            "text": self.text,
            "textAt": self.textAt,
            "confidence": self.confidence,
            "source": self.source,
            "existingBarType": self.existingBarType,
            "conflict": self.conflict,
            "reviewRequired": self.reviewRequired,
            "reviewRequiredReason": self.reviewRequiredReason,
            "evidence": self.evidence,
            "warnings": self.warnings,
        }


@dataclass
class ScheduleAxisMappingResult:
    tableId: str = ""
    axisUnit: str = "unknown"
    dateRange: ScheduleDateRange = field(default_factory=ScheduleDateRange)
    candidates: list[ScheduleBarPlanCandidate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "axisUnit": self.axisUnit,
            "dateRange": self.dateRange.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class ScheduleBarRangeRequest:
    taskName: str = ""
    row: int | None = None
    trade: str = ""
    startDate: str = ""
    endDate: str = ""
    color: str = ""
    text: str = ""
    textAt: str = "center"

    def to_dict(self) -> dict:
        return {
            "taskName": self.taskName,
            "row": self.row,
            "trade": self.trade,
            "startDate": self.startDate,
            "endDate": self.endDate,
            "color": self.color,
            "text": self.text,
            "textAt": self.textAt,
        }


@dataclass
class ScheduleBarEditPlanItem:
    """fill_schedule_bars 한 항목. hwpx_edit_tool 키와 호환."""
    table: int = 0
    tableId: str = ""
    taskRow: int = -1
    startCol: int = -1
    endCol: int = -1
    color: str = "92D050"
    text: str = ""
    textAt: str = "center"
    shrinkToFit: bool = True
    preserveText: bool = True
    overwrite: bool = False
    conflict: str = "no_conflict"
    confidence: float = 0.0
    sourceCandidateId: str = ""
    reviewRequired: bool = False
    reviewRequiredReason: str | None = None
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "table": self.table,
            "tableId": self.tableId,
            "task_row": self.taskRow,
            "start_col": self.startCol,
            "end_col": self.endCol,
            "color": self.color,
            "text": self.text,
            "text_at": self.textAt,
            "shrink_to_fit": self.shrinkToFit,
            "preserve_text": self.preserveText,
            "overwrite": self.overwrite,
            "conflict": self.conflict,
            "confidence": self.confidence,
            "reviewRequired": self.reviewRequired,
            "reviewRequiredReason": self.reviewRequiredReason,
        }

    def to_fill_plan_dict(self) -> dict:
        """fill_schedule_bars 실행에 필요한 키만 반환."""
        return {
            "table": self.table,
            "task_row": self.taskRow,
            "start_col": self.startCol,
            "end_col": self.endCol,
            "color": self.color,
            "text": self.text,
            "text_at": self.textAt,
            "shrink_to_fit": self.shrinkToFit,
        }


@dataclass
class ScheduleBarPlanDecision:
    action: str = "REVIEW_REQUIRED"  # AUTO_PLAN_ALLOWED | REVIEW_REQUIRED | SKIP | FAIL
    reason: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {"action": self.action, "reason": self.reason, "confidence": self.confidence}


@dataclass
class ScheduleBarEditPlan:
    tableId: str = ""
    items: list[ScheduleBarEditPlanItem] = field(default_factory=list)
    autoAllowedCount: int = 0
    reviewRequiredCount: int = 0
    skipCount: int = 0
    failCount: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "fill_schedule_bars": [i.to_fill_plan_dict() for i in self.items
                                   if i.reviewRequired is False and i.startCol >= 0],
            "allItems": [i.to_dict() for i in self.items],
            "autoAllowedCount": self.autoAllowedCount,
            "reviewRequiredCount": self.reviewRequiredCount,
            "skipCount": self.skipCount,
            "failCount": self.failCount,
            "warnings": self.warnings,
            "errors": self.errors,
        }


@dataclass
class ScheduleBarPlanBuildResult:
    plans: list[ScheduleBarEditPlan] = field(default_factory=list)
    totalCandidates: int = 0
    totalAutoAllowed: int = 0
    totalReviewRequired: int = 0
    totalFail: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "plans": [p.to_dict() for p in self.plans],
            "totalCandidates": self.totalCandidates,
            "totalAutoAllowed": self.totalAutoAllowed,
            "totalReviewRequired": self.totalReviewRequired,
            "totalFail": self.totalFail,
            "warnings": self.warnings,
        }


@dataclass
class ScheduleBarReviewItem:
    """REVIEW_REQUIRED 후보 1건 — 사람이 승인/거부할 검토 항목."""
    itemId: str = ""
    tableId: str = ""
    taskRow: int = -1
    taskName: str = ""
    startCol: int = -1
    endCol: int = -1
    color: str = ""
    text: str = ""
    conflict: str = ""
    reviewRequiredReason: str = ""
    existingBarType: str = ""
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "itemId": self.itemId,
            "tableId": self.tableId,
            "taskRow": self.taskRow,
            "taskName": self.taskName,
            "startCol": self.startCol,
            "endCol": self.endCol,
            "color": self.color,
            "text": self.text,
            "conflict": self.conflict,
            "reviewRequiredReason": self.reviewRequiredReason,
            "existingBarType": self.existingBarType,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


@dataclass
class ScheduleBarReviewDecision:
    """검토자의 한 항목에 대한 승인/거부 결정."""
    itemId: str = ""
    verdict: str = "PENDING"   # APPROVED | REJECTED | DEFERRED
    reason: str = ""
    reviewedBy: str = "human"

    def to_dict(self) -> dict:
        return {
            "itemId": self.itemId,
            "verdict": self.verdict,
            "reason": self.reason,
            "reviewedBy": self.reviewedBy,
        }


@dataclass
class ScheduleBarReviewList:
    """REVIEW_REQUIRED 후보 전체 목록."""
    tableId: str = ""
    items: list[ScheduleBarReviewItem] = field(default_factory=list)
    autoAllowedItems: list[ScheduleBarEditPlanItem] = field(default_factory=list)
    failedItems: list[ScheduleBarEditPlanItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "reviewRequiredCount": len(self.items),
            "autoAllowedCount": len(self.autoAllowedItems),
            "failedCount": len(self.failedItems),
            "reviewItems": [i.to_dict() for i in self.items],
            "autoAllowedItems": [i.to_dict() for i in self.autoAllowedItems],
            "failedItems": [i.to_dict() for i in self.failedItems],
            "warnings": self.warnings,
        }


@dataclass
class ScheduleBarGateOutput:
    """게이트 통과 후 실행 가능한 fill plan + 거부/보류 목록."""
    tableId: str = ""
    approvedItems: list[ScheduleBarEditPlanItem] = field(default_factory=list)
    rejectedItems: list[ScheduleBarReviewItem] = field(default_factory=list)
    deferredItems: list[ScheduleBarReviewItem] = field(default_factory=list)
    pendingItems: list[ScheduleBarReviewItem] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_fill_plan_dict(self) -> dict:
        """approvedItems만 fill_schedule_bars 실행 대상으로 반환."""
        return {
            "fill_schedule_bars": [i.to_fill_plan_dict() for i in self.approvedItems],
        }

    def to_dict(self) -> dict:
        return {
            "tableId": self.tableId,
            "approvedCount": len(self.approvedItems),
            "rejectedCount": len(self.rejectedItems),
            "deferredCount": len(self.deferredItems),
            "pendingCount": len(self.pendingItems),
            "fill_schedule_bars": [i.to_fill_plan_dict() for i in self.approvedItems],
            "rejectedItems": [i.to_dict() for i in self.rejectedItems],
            "deferredItems": [i.to_dict() for i in self.deferredItems],
            "pendingItems": [i.to_dict() for i in self.pendingItems],
            "warnings": self.warnings,
        }


def make_request_id() -> str:
    return str(uuid.uuid4())
