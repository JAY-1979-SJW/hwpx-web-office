"""
HWPX-HEADER-INPUT-CELL-SURVEY-01

HWPX 파일 전체를 read-only로 전수 조사하여
- 표별 헤더(정규화 텍스트, 위치, 추정 필드명)
- 입력셀 후보(빈 셀 또는 단일 공백 셀의 좌표·라벨 맥락)
를 수집한다.

절대 금지:
- 원본 HWPX 수정 없음 / writer 호출 없음
- corpus.sqlite3 생성·수정 없음
- AI API / OCR 호출 없음
- 절대경로 / 원본 파일명 / 셀 내 PII 값 보고서 저장 없음
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import traceback
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

# ── namespaces ────────────────────────────────────────────────────────────────
NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_OPF = "http://www.idpf.org/2007/opf/"

# ── 입력셀 타입 ────────────────────────────────────────────────────────────────
ITYPE_LABEL_ADJACENT = "label_adjacent"   # 2-col 표: 왼쪽 라벨, 오른쪽 빈 셀
ITYPE_HEADER_COLUMN  = "header_column"    # 헤더 아래 데이터행 빈 셀
ITYPE_FORM_FIELD     = "form_field"       # form_table 내 빈 값 셀

# ── 표 분류용 키워드 (profiler 공유) ──────────────────────────────────────────
SCHEDULE_HEADER_KW = (
    "공종", "작업명", "공사명", "시작일", "착수일", "종료일", "완료일", "준공일",
    "기간", "공기", "진행률", "진도율", "예정", "실적", "task", "start", "end", "duration",
)
DATE_HEADER_RE = [
    re.compile(r"^\d{4}[-./]\d{1,2}[-./]\d{1,2}"),
    re.compile(r"^\d{4}[-./]\d{1,2}$"),
    re.compile(r"^\d{1,2}[-./]\d{1,2}"),
    re.compile(r"^\d{1,2}월"),
    re.compile(r"^\d{1,2}주차?"),
    re.compile(r"^Q[1-4]"),
    re.compile(r"^\d{4}년"),
]
FORM_LABEL_KW = (
    "공사명", "현장명", "사업명", "시공사", "감리자",
    "접수번호", "접수일", "발신", "수신", "문서번호", "보고일",
    "작성자", "작성일", "승인자", "검토자", "제출일", "수신처",
)
FIELD_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("projectName",        ("공사명", "사업명", "프로젝트명")),
    ("siteName",           ("현장명", "현장",)),
    ("contractorName",     ("시공사", "도급사", "수급인", "업체명", "회사명", "상호")),
    ("reportDate",         ("작성일", "보고일", "제출일")),
    ("receiptNumber",      ("접수번호", "접수번", "문서번호", "접수")),
    ("number",             ("번호",)),
    ("trade",              ("공종", "공정", "trade")),
    ("taskName",           ("작업명", "task", "내용", "항목")),
    ("startDate",          ("시작일", "착수일", "착공일", "start")),
    ("endDate",            ("종료일", "완료일", "준공일", "end")),
    ("durationDays",       ("기간", "공기", "duration")),
    ("responsiblePerson",  ("담당자", "책임자", "성명", "지정자")),
    ("progressRate",       ("진행률", "진도율", "달성률", "progress")),
    ("materialStatus",     ("자재", "재료", "material")),
    ("inspectionStatus",   ("검측", "검사", "inspection")),
    ("remarks",            ("비고", "참고", "remark", "note")),
    ("quantity",           ("수량", "량")),
    ("unit",               ("단위", "unit")),
    ("spec",               ("규격", "사양", "spec")),
    ("amount",             ("금액", "단가", "amount", "price")),
    ("location",           ("위치", "장소", "구간")),
]

# ── PII 탐지 (셀 값 보고서 저장 차단용) ────────────────────────────────────
_PII_RE = [
    re.compile(r"\d{2,3}-\d{3,4}-\d{4}"),
    re.compile(r"\d{3}-\d{2}-\d{5}"),
    re.compile(r"\d{6}-[1-4]\d{6}"),
]


# ── 식별자 유틸 ───────────────────────────────────────────────────────────────

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()


def masked_file_id(path: Path, index: int) -> str:
    h = _sha256(str(path.resolve()))
    return f"f{index:05d}_{h[:10]}"


def file_content_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        h.update(str(path).encode())
    return h.hexdigest()


# ── 텍스트 정규화 ─────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\r\n\t]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", t)
    return t


def guess_field(norm: str) -> tuple[str, float]:
    if not norm:
        return "unknown", 0.0
    low = norm.lower()
    for fname, hints in FIELD_HINTS:
        for h in hints:
            if h in norm or h.lower() in low:
                return fname, (0.95 if (norm == h or low == h.lower()) else 0.75)
    return "unknown", 0.0


def is_date_like(text: str) -> bool:
    n = normalize(text)
    return any(p.search(n) for p in DATE_HEADER_RE)


def _has_pii(text: str) -> bool:
    return any(p.search(text) for p in _PII_RE)


# ── XML 파싱 헬퍼 ─────────────────────────────────────────────────────────────

def _cell_text(cell: ET.Element) -> str:
    parts = []
    for elem in cell.iter():
        if elem.tag == f"{{{NS_HP}}}tbl":
            continue
        if elem.tag == f"{{{NS_HP}}}t" and elem.text:
            parts.append(elem.text)
    return "".join(parts)


def _cell_span(cell: ET.Element) -> tuple[int, int]:
    for child in cell:
        if child.tag == f"{{{NS_HP}}}cellSpan":
            try:
                return (
                    int(child.attrib.get("colSpan", "1")),
                    int(child.attrib.get("rowSpan", "1")),
                )
            except ValueError:
                return 1, 1
    return 1, 1


def _table_grid(tbl: ET.Element) -> list[list[ET.Element]]:
    rows = [c for c in tbl if c.tag == f"{{{NS_HP}}}tr"]
    return [[c for c in row if c.tag == f"{{{NS_HP}}}tc"] for row in rows]


def _detect_header_rows(grid: list[list[ET.Element]]) -> list[int]:
    candidates = []
    for i in range(min(3, len(grid))):
        row = grid[i]
        if not row:
            continue
        texts = [normalize(_cell_text(c)) for c in row]
        non_empty = [t for t in texts if t]
        if not non_empty:
            continue
        avg_len = sum(len(t) for t in non_empty) / len(non_empty)
        col_count = len(row)
        if i == 0 and len(non_empty) <= 2 and avg_len > 15:
            continue
        if avg_len <= 14 and len(non_empty) >= max(1, col_count // 2):
            candidates.append(i)
            break
    return candidates


# ── 표 레이아웃 간이 분류 ─────────────────────────────────────────────────────

def _classify_layout(
    grid: list[list[ET.Element]],
    header_texts: list[str],
) -> str:
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)
    total = sum(len(r) for r in grid)
    if total == 0:
        return "empty"

    norm_hdrs = [normalize(t) for t in header_texts]
    blob = " ".join(norm_hdrs)
    schedule_hits = sum(1 for kw in SCHEDULE_HEADER_KW if kw in blob)
    date_cols = sum(1 for t in norm_hdrs if is_date_like(t))

    if date_cols >= 3 and cols >= 5:
        return "gantt_like"
    if schedule_hits >= 3:
        return "vertical_schedule" if rows > cols else "horizontal_schedule"
    if date_cols >= 1 and schedule_hits >= 1:
        return "horizontal_schedule"

    form_hits = sum(
        1 for row in grid for c in row
        if any(kw in normalize(_cell_text(c)) for kw in FORM_LABEL_KW)
    )
    if form_hits >= 2 and rows <= 8:
        return "form_table"

    if cols <= 2 and rows >= 4:
        return "vertical_table"
    if rows <= 2 and cols >= 3:
        return "horizontal_table"
    return "unknown"


# ── 입력셀 탐지 ───────────────────────────────────────────────────────────────

@dataclass
class InputCell:
    maskedFileId: str
    sectionIndex: int
    tableIndex: int
    tableLayout: str
    rowIndex: int
    colIndex: int
    inputCellType: str
    adjacentLabel: str        # 라벨 텍스트 (필드명 수준, 값 아님)
    guessedField: str
    fieldConfidence: float
    colSpan: int
    rowSpan: int
    isInHeaderZone: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "maskedFileId": self.maskedFileId,
            "sectionIndex": self.sectionIndex,
            "tableIndex": self.tableIndex,
            "tableLayout": self.tableLayout,
            "rowIndex": self.rowIndex,
            "colIndex": self.colIndex,
            "inputCellType": self.inputCellType,
            "adjacentLabel": self.adjacentLabel,
            "guessedField": self.guessedField,
            "fieldConfidence": round(self.fieldConfidence, 3),
            "colSpan": self.colSpan,
            "rowSpan": self.rowSpan,
            "isInHeaderZone": self.isInHeaderZone,
        }


def _find_input_cells(
    fid: str,
    sec_idx: int,
    tbl_idx: int,
    grid: list[list[ET.Element]],
    header_row_idxs: list[int],
    layout: str,
) -> list[InputCell]:
    results: list[InputCell] = []
    header_zone = set(header_row_idxs)
    rows = len(grid)
    cols = max((len(r) for r in grid), default=0)

    for ri, row in enumerate(grid):
        for ci, cell in enumerate(row):
            raw = _cell_text(cell).strip()
            norm_val = normalize(raw)
            cs, rs = _cell_span(cell)

            # 빈 셀 판정: 텍스트 없거나 공백/줄바꿈만
            is_empty = len(norm_val) == 0

            if not is_empty:
                continue

            # 헤더행 자체는 입력셀 후보에서 제외
            if ri in header_zone:
                continue

            itype: str | None = None
            label: str = ""
            gfield = "unknown"
            gconf = 0.0

            # ── 타입 1: label_adjacent (2-col 표, 왼쪽 라벨 + 오른쪽 빈 셀) ──
            if cols == 2 and ci == 1:
                left_norm = normalize(_cell_text(row[0])) if row else ""
                if left_norm and len(left_norm) <= 20:
                    itype = ITYPE_LABEL_ADJACENT
                    label = left_norm
                    gfield, gconf = guess_field(label)

            # ── 타입 2: form_field (form_table 내 빈 값 셀) ──
            if itype is None and layout == "form_table":
                # 같은 행에 라벨 후보가 있으면 form_field
                row_labels = [
                    normalize(_cell_text(c))
                    for j, c in enumerate(row) if j != ci and normalize(_cell_text(c))
                ]
                if row_labels:
                    candidate_label = min(row_labels, key=len)
                    if len(candidate_label) <= 20:
                        itype = ITYPE_FORM_FIELD
                        label = candidate_label
                        gfield, gconf = guess_field(label)

            # ── 타입 3: header_column (헤더 아래 데이터행 빈 셀) ──
            if itype is None and header_row_idxs and ri > max(header_row_idxs):
                header_row = grid[header_row_idxs[-1]]
                if ci < len(header_row):
                    hdr_norm = normalize(_cell_text(header_row[ci]))
                    if hdr_norm and len(hdr_norm) <= 20:
                        itype = ITYPE_HEADER_COLUMN
                        label = hdr_norm
                        gfield, gconf = guess_field(label)

            if itype is None:
                continue

            results.append(InputCell(
                maskedFileId=fid,
                sectionIndex=sec_idx,
                tableIndex=tbl_idx,
                tableLayout=layout,
                rowIndex=ri,
                colIndex=ci,
                inputCellType=itype,
                adjacentLabel=label,
                guessedField=gfield,
                fieldConfidence=gconf,
                colSpan=cs,
                rowSpan=rs,
                isInHeaderZone=(ri in header_zone),
            ))

    return results


# ── 헤더 레코드 ───────────────────────────────────────────────────────────────

@dataclass
class HeaderRecord:
    maskedFileId: str
    sectionIndex: int
    tableIndex: int
    tableLayout: str
    rowIndex: int
    colIndex: int
    normalizedText: str
    guessedField: str
    fieldConfidence: float
    isDateLike: bool
    colSpan: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "maskedFileId": self.maskedFileId,
            "sectionIndex": self.sectionIndex,
            "tableIndex": self.tableIndex,
            "tableLayout": self.tableLayout,
            "rowIndex": self.rowIndex,
            "colIndex": self.colIndex,
            "normalizedText": self.normalizedText,
            "guessedField": self.guessedField,
            "fieldConfidence": round(self.fieldConfidence, 3),
            "isDateLike": self.isDateLike,
            "colSpan": self.colSpan,
        }


# ── 파일별 처리 ───────────────────────────────────────────────────────────────

@dataclass
class FileResult:
    maskedFileId: str
    fileHash: str
    fileSize: int
    sectionCount: int
    tableCount: int
    totalCells: int
    emptyCells: int
    headerCount: int
    inputCellCount: int
    layoutCounter: dict[str, int]
    fieldCounter: dict[str, int]
    parseStatus: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "maskedFileId": self.maskedFileId,
            "fileHash": self.fileHash,
            "fileSize": self.fileSize,
            "sectionCount": self.sectionCount,
            "tableCount": self.tableCount,
            "totalCells": self.totalCells,
            "emptyCells": self.emptyCells,
            "headerCount": self.headerCount,
            "inputCellCount": self.inputCellCount,
            "layoutCounter": self.layoutCounter,
            "fieldCounter": self.fieldCounter,
            "parseStatus": self.parseStatus,
            "warnings": self.warnings,
        }


def _survey_file(
    path: Path,
    fid: str,
) -> tuple[FileResult, list[HeaderRecord], list[InputCell]]:
    now = datetime.now(tz=timezone.utc).isoformat()
    warnings: list[str] = []
    headers: list[HeaderRecord] = []
    inputs: list[InputCell] = []

    size = 0
    try:
        size = path.stat().st_size
    except OSError:
        pass

    fhash = file_content_hash(path)

    # ZIP 열기
    try:
        zf_handle = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, Exception) as exc:
        return (
            FileResult(fid, fhash, size, 0, 0, 0, 0, 0, 0, {}, {},
                       "BROKEN_ZIP", [str(exc)]),
            headers, inputs,
        )

    section_count = 0
    table_count = 0
    total_cells = 0
    empty_cells = 0
    layout_ctr: Counter = Counter()
    field_ctr: Counter = Counter()

    with zf_handle as zf:
        names = zf.namelist()
        section_files = sorted(
            n for n in names if re.match(r"Contents/section\d+\.xml$", n)
        )
        if not section_files or "Contents/content.hpf" not in names:
            return (
                FileResult(fid, fhash, size, 0, 0, 0, 0, 0, 0, {}, {},
                           "MISSING_XML", ["no section files or content.hpf"]),
                headers, inputs,
            )

        section_count = len(section_files)

        for sec_idx, sec_name in enumerate(section_files):
            try:
                raw = zf.read(sec_name)
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                warnings.append(f"{sec_name}: XML parse error: {exc}")
                continue
            except Exception as exc:
                warnings.append(f"{sec_name}: read error: {exc}")
                continue

            tables = list(root.iter(f"{{{NS_HP}}}tbl"))
            for tbl_idx, tbl in enumerate(tables):
                table_count += 1
                grid = _table_grid(tbl)

                # 셀 집계
                for row in grid:
                    for cell in row:
                        total_cells += 1
                        if not normalize(_cell_text(cell)):
                            empty_cells += 1

                header_row_idxs = _detect_header_rows(grid)

                # 헤더 텍스트 수집
                hdr_texts: list[str] = []
                for hri in header_row_idxs:
                    if hri >= len(grid):
                        continue
                    for ci, cell in enumerate(grid[hri]):
                        norm = normalize(_cell_text(cell))
                        if not norm:
                            continue
                        cs, _ = _cell_span(cell)
                        gf, gc = guess_field(norm)
                        hdr_texts.append(norm)
                        field_ctr[gf] += 1
                        headers.append(HeaderRecord(
                            maskedFileId=fid,
                            sectionIndex=sec_idx,
                            tableIndex=tbl_idx,
                            tableLayout="",   # fill after layout classify
                            rowIndex=hri,
                            colIndex=ci,
                            normalizedText=norm,
                            guessedField=gf,
                            fieldConfidence=gc,
                            isDateLike=is_date_like(norm),
                            colSpan=cs,
                        ))

                layout = _classify_layout(grid, hdr_texts)
                layout_ctr[layout] += 1

                # layout을 header records에 역주입
                for hr in headers:
                    if (hr.maskedFileId == fid
                            and hr.sectionIndex == sec_idx
                            and hr.tableIndex == tbl_idx
                            and not hr.tableLayout):
                        hr.tableLayout = layout

                # 입력셀 탐지
                icells = _find_input_cells(fid, sec_idx, tbl_idx, grid,
                                           header_row_idxs, layout)
                inputs.extend(icells)
                for ic in icells:
                    if ic.guessedField != "unknown":
                        field_ctr[f"input:{ic.guessedField}"] += 1

    result = FileResult(
        maskedFileId=fid,
        fileHash=fhash,
        fileSize=size,
        sectionCount=section_count,
        tableCount=table_count,
        totalCells=total_cells,
        emptyCells=empty_cells,
        headerCount=len(headers),
        inputCellCount=len(inputs),
        layoutCounter=dict(layout_ctr),
        fieldCounter=dict(field_ctr),
        parseStatus="PASS" if not warnings else "PARTIAL",
        warnings=warnings[:10],
    )
    return result, headers, inputs


# ── 집계 사전 ────────────────────────────────────────────────────────────────

def _build_header_dict(
    all_headers: list[HeaderRecord],
) -> list[dict[str, Any]]:
    norm_map: dict[str, dict] = {}
    for hr in all_headers:
        key = hr.normalizedText
        if key not in norm_map:
            norm_map[key] = {
                "normalizedText": key,
                "guessedField": hr.guessedField,
                "fieldConfidence": hr.fieldConfidence,
                "isDateLike": hr.isDateLike,
                "fileCount": set(),
                "tableCount": set(),
                "totalOccurrences": 0,
                "colIndexCounter": Counter(),
                "layoutCounter": Counter(),
            }
        e = norm_map[key]
        e["fileCount"].add(hr.maskedFileId)
        e["tableCount"].add(f"{hr.maskedFileId}:{hr.sectionIndex}:{hr.tableIndex}")
        e["totalOccurrences"] += 1
        e["colIndexCounter"][hr.colIndex] += 1
        e["layoutCounter"][hr.tableLayout] += 1

    rows = []
    for key, e in norm_map.items():
        rows.append({
            "normalizedText": key,
            "guessedField": e["guessedField"],
            "fieldConfidence": round(e["fieldConfidence"], 3),
            "isDateLike": e["isDateLike"],
            "fileCount": len(e["fileCount"]),
            "tableCount": len(e["tableCount"]),
            "totalOccurrences": e["totalOccurrences"],
            "commonColIndexes": [i for i, _ in e["colIndexCounter"].most_common(3)],
            "layoutDistribution": dict(e["layoutCounter"].most_common()),
        })
    rows.sort(key=lambda r: r["totalOccurrences"], reverse=True)
    return rows


def _build_input_cell_dict(
    all_inputs: list[InputCell],
) -> list[dict[str, Any]]:
    label_map: dict[str, dict] = {}
    for ic in all_inputs:
        key = (ic.adjacentLabel, ic.inputCellType)
        k = f"{ic.adjacentLabel}|{ic.inputCellType}"
        if k not in label_map:
            label_map[k] = {
                "adjacentLabel": ic.adjacentLabel,
                "inputCellType": ic.inputCellType,
                "guessedField": ic.guessedField,
                "fieldConfidence": ic.fieldConfidence,
                "fileCount": set(),
                "occurrences": 0,
                "layoutCounter": Counter(),
            }
        e = label_map[k]
        e["fileCount"].add(ic.maskedFileId)
        e["occurrences"] += 1
        e["layoutCounter"][ic.tableLayout] += 1

    rows = []
    for k, e in label_map.items():
        rows.append({
            "adjacentLabel": e["adjacentLabel"],
            "inputCellType": e["inputCellType"],
            "guessedField": e["guessedField"],
            "fieldConfidence": round(e["fieldConfidence"], 3),
            "fileCount": len(e["fileCount"]),
            "occurrences": e["occurrences"],
            "layoutDistribution": dict(e["layoutCounter"].most_common()),
        })
    rows.sort(key=lambda r: r["occurrences"], reverse=True)
    return rows


# ── 보고서 출력 ───────────────────────────────────────────────────────────────

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {
                k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                for k, v in r.items()
            }
            w.writerow(row)


def _build_summary_md(
    summary: dict[str, Any],
    hdr_dict: list[dict],
    icd: list[dict],
) -> str:
    lines = [
        "# HWPX 헤더·입력셀 전수조사 보고서",
        "",
        f"- 스캔 파일 수: {summary['totalFiles']}",
        f"- 표 수: {summary['totalTables']}",
        f"- 전체 셀: {summary['totalCells']}",
        f"- 빈 셀(입력셀 후보 포함): {summary['totalEmptyCells']}",
        f"- 헤더 레코드: {summary['totalHeaders']}",
        f"- 입력셀 후보: {summary['totalInputCells']}",
        f"- 고유 헤더 종류: {summary['uniqueHeaders']}",
        f"- 고유 입력셀 라벨: {summary['uniqueInputLabels']}",
        f"- 조사 시각: {summary['profiledAt']}",
        "",
        "## 헤더 빈도 TOP 50",
        "",
        "| 헤더 | 파일수 | 발생횟수 | 추정 필드 | 신뢰도 |",
        "|------|--------|----------|-----------|--------|",
    ]
    for r in hdr_dict[:50]:
        lines.append(
            f"| {r['normalizedText']} | {r['fileCount']} | {r['totalOccurrences']}"
            f" | {r['guessedField']} | {r['fieldConfidence']} |"
        )
    lines += [
        "",
        "## 입력셀 라벨 빈도 TOP 50",
        "",
        "| 라벨 | 타입 | 파일수 | 발생횟수 | 추정 필드 |",
        "|------|------|--------|----------|-----------|",
    ]
    for r in icd[:50]:
        lines.append(
            f"| {r['adjacentLabel']} | {r['inputCellType']} | {r['fileCount']}"
            f" | {r['occurrences']} | {r['guessedField']} |"
        )
    lines += [
        "",
        "## 표 레이아웃 분포",
        "",
    ]
    lc: Counter = Counter()
    for f in summary.get("layoutDistribution", {}).items():
        lc[f[0]] = f[1]
    for layout, cnt in lc.most_common():
        lines.append(f"- {layout}: {cnt}")
    return "\n".join(lines) + "\n"


def _write_reports(
    output_dir: Path,
    file_results: list[FileResult],
    all_headers: list[HeaderRecord],
    all_inputs: list[InputCell],
    hdr_dict: list[dict],
    icd: list[dict],
    summary: dict[str, Any],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # per-file summary
    p = output_dir / "survey_per_file.jsonl"
    _write_jsonl(p, [r.to_dict() for r in file_results])
    paths["per_file"] = p

    # header records (raw)
    p = output_dir / "survey_headers_raw.jsonl"
    _write_jsonl(p, [h.to_dict() for h in all_headers])
    paths["headers_raw"] = p

    # input cell records (raw)
    p = output_dir / "survey_input_cells_raw.jsonl"
    _write_jsonl(p, [ic.to_dict() for ic in all_inputs])
    paths["input_cells_raw"] = p

    # header dictionary (aggregate)
    p = output_dir / "survey_header_dictionary.json"
    _write_json(p, hdr_dict)
    paths["header_dict"] = p

    hdr_csv_fields = [
        "normalizedText", "guessedField", "fieldConfidence", "isDateLike",
        "fileCount", "tableCount", "totalOccurrences", "commonColIndexes",
        "layoutDistribution",
    ]
    p = output_dir / "survey_header_dictionary.csv"
    _write_csv(p, hdr_dict, hdr_csv_fields)
    paths["header_dict_csv"] = p

    # input cell dictionary (aggregate)
    p = output_dir / "survey_input_cell_dictionary.json"
    _write_json(p, icd)
    paths["input_cell_dict"] = p

    icd_csv_fields = [
        "adjacentLabel", "inputCellType", "guessedField", "fieldConfidence",
        "fileCount", "occurrences", "layoutDistribution",
    ]
    p = output_dir / "survey_input_cell_dictionary.csv"
    _write_csv(p, icd, icd_csv_fields)
    paths["input_cell_dict_csv"] = p

    # summary JSON
    p = output_dir / "survey_summary.json"
    _write_json(p, summary)
    paths["summary_json"] = p

    # summary MD
    md = _build_summary_md(summary, hdr_dict, icd)
    p = output_dir / "survey_summary.md"
    p.write_text(md, encoding="utf-8")
    paths["summary_md"] = p

    return paths


# ── 전수조사 메인 ─────────────────────────────────────────────────────────────

def discover_hwpx(
    input_dir: Path,
    pattern: str = "*.hwpx",
    limit: int = 0,
) -> list[Path]:
    import fnmatch
    files = [p for p in input_dir.rglob("*")
             if fnmatch.fnmatch(p.name, pattern) and p.is_file()]
    files.sort()
    if limit and limit > 0:
        files = files[:limit]
    return files


def run_survey(
    input_dir: Path,
    output_dir: Path,
    pattern: str = "*.hwpx",
    limit: int = 0,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict[str, Any]:
    files = discover_hwpx(input_dir, pattern, limit)

    file_results: list[FileResult] = []
    all_headers: list[HeaderRecord] = []
    all_inputs: list[InputCell] = []

    for i, path in enumerate(files):
        fid = masked_file_id(path, i)
        if verbose:
            print(f"[{i+1}/{len(files)}] {fid}", file=sys.stderr)
        try:
            fr, hdrs, ics = _survey_file(path, fid)
        except Exception as exc:
            tb = traceback.format_exc(limit=2)
            fr = FileResult(fid, "", 0, 0, 0, 0, 0, 0, 0, {}, {},
                            "ERROR", [f"{exc}", tb[-200:]])
        file_results.append(fr)
        all_headers.extend(hdrs)
        all_inputs.extend(ics)

    # 집계
    hdr_dict = _build_header_dict(all_headers)
    icd = _build_input_cell_dict(all_inputs)

    layout_dist: Counter = Counter()
    for fr in file_results:
        for k, v in fr.layoutCounter.items():
            layout_dist[k] += v

    field_dist: Counter = Counter()
    for h in all_headers:
        if h.guessedField != "unknown":
            field_dist[h.guessedField] += 1

    summary: dict[str, Any] = {
        "totalFiles": len(files),
        "parsedOk": sum(1 for r in file_results if r.parseStatus in ("PASS", "PARTIAL")),
        "parseErrors": sum(1 for r in file_results if r.parseStatus in ("BROKEN_ZIP", "MISSING_XML", "ERROR")),
        "totalTables": sum(r.tableCount for r in file_results),
        "totalCells": sum(r.totalCells for r in file_results),
        "totalEmptyCells": sum(r.emptyCells for r in file_results),
        "totalHeaders": len(all_headers),
        "totalInputCells": len(all_inputs),
        "uniqueHeaders": len(hdr_dict),
        "uniqueInputLabels": len(icd),
        "inputCellTypeDistribution": dict(Counter(ic.inputCellType for ic in all_inputs).most_common()),
        "layoutDistribution": dict(layout_dist.most_common()),
        "topFields": dict(field_dist.most_common(20)),
        "profiledAt": datetime.now(tz=timezone.utc).isoformat(),
    }

    if not dry_run:
        _write_reports(output_dir, file_results, all_headers, all_inputs,
                       hdr_dict, icd, summary)

    return summary


# ── CLI ────────────────────────────────────────────────────────────────────────

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="HWPX 헤더·입력셀 전수조사 (read-only)"
    )
    p.add_argument("--input-dir", required=True,
                   help="스캔할 HWPX 루트 디렉터리")
    p.add_argument("--output-dir", required=True,
                   help="보고서 출력 디렉터리")
    p.add_argument("--limit", type=int, default=0,
                   help="최대 스캔 파일 수 (0=제한 없음)")
    p.add_argument("--dry-run", action="store_true", default=False,
                   help="스캔만 수행, 파일 미생성")
    p.add_argument("--include-pattern", default="*.hwpx",
                   help="파일 glob 패턴 (기본: *.hwpx)")
    p.add_argument("--verbose", action="store_true", default=False)
    p.add_argument("--json", dest="output_json", action="store_true", default=False,
                   help="요약 JSON을 stdout에 출력")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_survey(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        pattern=args.include_pattern,
        limit=args.limit,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    if args.output_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"전수조사 완료: {summary['totalFiles']}개 파일 / "
            f"표 {summary['totalTables']}개 / "
            f"헤더 {summary['totalHeaders']}개 / "
            f"입력셀 {summary['totalInputCells']}개"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
