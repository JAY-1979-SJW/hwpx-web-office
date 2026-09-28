"""HWPX-SCHEDULE-AXIS-DETECTOR-01 / HWPX-SCHEDULE-BAR-RANGE-DETECTOR-01

공정표 날짜축·작업행·막대 구간 탐지 및 date range → col range 변환.

read-only 탐지만 수행한다.
apply_edit_plan / write_package / repair_for_server / fill_schedule_bars 호출 없음.
원본 fixture 수정 없음.
reports 산출물은 커밋 제외.
"""
from __future__ import annotations

import re
from typing import Any

from .parser_contract import (
    BarRangeInfo,
    DateColumnInfo,
    ProgressColumnInfo,
    ScheduleBarPlanCandidate,
    ScheduleBarRangeRequest,
    ScheduleDateRange,
    ScheduleInfo,
    TaskRowInfo,
    TimeAxisInfo,
)

# ── 날짜 패턴 ─────────────────────────────────────────────────────────────────

_RE_MONTH_KR = re.compile(r"^(\d{1,2})월$")
_RE_WEEK_KR = re.compile(r"^(\d{1,2})주(?:차)?$")
_RE_DAY_NUM = re.compile(r"^\d{1,2}$")
_RE_DATE_SLASH = re.compile(r"^\d{1,2}/\d{1,2}$")
_RE_DATE_DOT = re.compile(r"^\d{2,4}\.\d{1,2}\.\d{1,2}$")

_MONTH_LABELS = {f"{i}월" for i in range(1, 13)}
_WEEK_LABELS = {f"{i}주" for i in range(1, 60)} | {f"{i}주차" for i in range(1, 60)}
_PROGRESS_HEADERS = {"진행률", "진척률", "공정률", "완료율", "%", "progress"}

# 작업명 열 후보 헤더
_TASK_HEADERS = {"공종", "작업명", "세부공정", "내용", "항목", "공사명", "작업항목"}
# 기간 열 후보 헤더
_PERIOD_HEADERS = {"기간", "일정", "공사기간", "기간(일)", "period"}

_BAR_SYMBOLS = {"■", "□", "▪", "▫", "●", "○", "▶", "◀", "▲", "▽", "━", "─", "─", "·", "◾"}


def normalize_axis_label(text: str) -> str:
    """날짜 레이블을 정규화된 태그로 변환."""
    t = text.strip()
    m = _RE_MONTH_KR.match(t)
    if m:
        return f"month:{int(m.group(1))}"
    m = _RE_WEEK_KR.match(t)
    if m:
        return f"week:{int(m.group(1))}"
    if _RE_DAY_NUM.match(t):
        return f"day:{int(t)}"
    if _RE_DATE_SLASH.match(t) or _RE_DATE_DOT.match(t):
        return f"date:{t}"
    return f"label:{t}"


def infer_axis_unit(headers: list[str]) -> str:
    """헤더 목록에서 날짜축 단위 추론."""
    month_cnt = sum(1 for h in headers if _RE_MONTH_KR.match(h.strip()))
    week_cnt = sum(1 for h in headers if _RE_WEEK_KR.match(h.strip()))
    day_cnt = sum(1 for h in headers if _RE_DAY_NUM.match(h.strip()))
    date_cnt = sum(1 for h in headers if _RE_DATE_SLASH.match(h.strip()) or _RE_DATE_DOT.match(h.strip()))

    if month_cnt >= 2:
        return "month"
    if week_cnt >= 2:
        return "week"
    if day_cnt >= 3 or date_cnt >= 2:
        return "day"
    if month_cnt == 1:
        return "month"
    return "unknown"


def _is_bar_text(text: str) -> bool:
    return any(sym in text for sym in _BAR_SYMBOLS)


def _cells_by_row_col(table) -> dict[tuple[int, int], Any]:
    return {(c.row, c.col): c for c in getattr(table, "cells", [])}


# ── STEP 2: 날짜축 탐지 ───────────────────────────────────────────────────────

def detect_time_axis(table) -> TimeAxisInfo:
    cells = _cells_by_row_col(table)
    rows = getattr(table, "rowCount", 0)
    cols = getattr(table, "colCount", 0)

    best_header_row: int = -1
    best_date_cols: list[DateColumnInfo] = []
    best_score: float = 0.0
    evidence: list[str] = []
    month_header_rows: list[int] = []
    week_header_rows: list[int] = []
    day_header_rows: list[int] = []

    for row_i in range(min(rows, 4)):
        date_cols: list[DateColumnInfo] = []
        for col_i in range(cols):
            cell = cells.get((row_i, col_i))
            if not cell:
                continue
            text = (getattr(cell, "normalizedText", "") or "").strip()
            if not text:
                continue
            norm = normalize_axis_label(text)
            conf = 0.0
            if norm.startswith("month:"):
                conf = 0.95
            elif norm.startswith("week:"):
                conf = 0.90
            elif norm.startswith("day:"):
                conf = 0.80
            elif norm.startswith("date:"):
                conf = 0.85
            if conf > 0:
                date_cols.append(DateColumnInfo(col=col_i, label=text, normalized=norm, confidence=conf))

        if len(date_cols) >= 2:
            score = len(date_cols) * sum(d.confidence for d in date_cols) / len(date_cols)
            if score > best_score:
                best_score = score
                best_header_row = row_i
                best_date_cols = date_cols

    if best_header_row == -1:
        return TimeAxisInfo(
            confidence=0.0,
            warnings=["날짜축 헤더 후보 없음 — REVIEW_REQUIRED"],
            evidence=["no_date_header_found"],
        )

    unit = infer_axis_unit([d.label for d in best_date_cols])
    evidence.append(f"header_row={best_header_row}")
    evidence.append(f"date_cols={[d.col for d in best_date_cols]}")
    evidence.append(f"unit={unit}")

    # 월/주/일 헤더 행 분류
    for d in best_date_cols:
        if d.normalized.startswith("month:"):
            if best_header_row not in month_header_rows:
                month_header_rows.append(best_header_row)
        elif d.normalized.startswith("week:"):
            if best_header_row not in week_header_rows:
                week_header_rows.append(best_header_row)
        elif d.normalized.startswith("day:"):
            if best_header_row not in day_header_rows:
                day_header_rows.append(best_header_row)

    axis_conf = min(0.99, best_score / (len(best_date_cols) + 1))
    return TimeAxisInfo(
        axisDirection="horizontal",
        unit=unit,
        headerRows=[best_header_row],
        dateColumns=best_date_cols,
        monthHeaderRows=month_header_rows,
        weekHeaderRows=week_header_rows,
        dayHeaderRows=day_header_rows,
        confidence=round(axis_conf, 3),
        evidence=evidence,
    )


# ── STEP 3: 작업행 탐지 ───────────────────────────────────────────────────────

def detect_task_rows(table, axis: TimeAxisInfo) -> list[TaskRowInfo]:
    cells = _cells_by_row_col(table)
    rows = getattr(table, "rowCount", 0)
    cols = getattr(table, "colCount", 0)

    skip_rows = set(axis.headerRows)
    date_col_set = {d.col for d in axis.dateColumns}

    # 작업명 열 후보 — 왼쪽에서 0번 또는 1번 열
    task_col = 0

    task_rows: list[TaskRowInfo] = []
    for row_i in range(rows):
        if row_i in skip_rows:
            continue
        cell0 = cells.get((row_i, task_col))
        text0 = (getattr(cell0, "normalizedText", "") or "").strip() if cell0 else ""
        if not text0:
            continue

        # 날짜축 영역 셀 확인 — 바 기호 또는 내용 있으면 작업행
        axis_texts = []
        for col_i in date_col_set:
            c = cells.get((row_i, col_i))
            t = (getattr(c, "normalizedText", "") or "").strip() if c else ""
            if t:
                axis_texts.append(t)

        left_texts = [text0]
        for col_i in range(1, min(2, cols)):
            if col_i in date_col_set:
                break
            c = cells.get((row_i, col_i))
            t = (getattr(c, "normalizedText", "") or "").strip() if c else ""
            if t:
                left_texts.append(t)

        conf = 0.80
        if axis_texts:
            conf = 0.90
        evidence = [f"left_text={text0!r}"]
        if axis_texts:
            evidence.append(f"axis_sample={axis_texts[:2]}")

        task_rows.append(TaskRowInfo(
            row=row_i,
            taskName=text0,
            trade="",
            leftText=left_texts,
            confidence=conf,
            evidence=evidence,
        ))

    return task_rows


# ── STEP 4: 막대 구간 탐지 ────────────────────────────────────────────────────

def classify_bar_type(table, row: int, date_col_set: set[int]) -> tuple[str, list[str]]:
    cells = _cells_by_row_col(table)
    bar_texts = []
    fill_colors = []
    empty_count = 0

    for col_i in sorted(date_col_set):
        c = cells.get((row, col_i))
        if not c:
            empty_count += 1
            continue
        text = (getattr(c, "normalizedText", "") or "").strip()
        color = getattr(c, "fillColor", "") or ""
        merged = getattr(c, "isMergedOrigin", False)

        if color and color.lower() not in ("", "ffffff", "none", "auto"):
            fill_colors.append(color)
        if text:
            bar_texts.append(text)
        else:
            empty_count += 1

    total = len(date_col_set)
    if fill_colors:
        return "color_bar", [f"fill_colors={fill_colors[:3]}"]
    if not bar_texts and empty_count == total:
        return "empty_template", ["all_date_cells_empty"]
    has_bar_sym = any(_is_bar_text(t) for t in bar_texts)
    if has_bar_sym:
        non_empty = total - empty_count
        if non_empty >= total * 0.7:
            return "text_full", [f"bar_texts={bar_texts[:2]}"]
        return "text_partial", [f"bar_texts={bar_texts[:2]}", f"empty={empty_count}/{total}"]
    if bar_texts:
        return "text_partial", [f"bar_texts={bar_texts[:2]}"]
    return "empty_template", ["no_bar_content"]


def detect_bar_ranges(table, axis: TimeAxisInfo, task_rows: list[TaskRowInfo]) -> list[BarRangeInfo]:
    cells = _cells_by_row_col(table)
    date_col_set = {d.col for d in axis.dateColumns}
    if not date_col_set:
        return []

    sorted_date_cols = sorted(date_col_set)
    ranges: list[BarRangeInfo] = []

    for tr in task_rows:
        row_i = tr.row
        bar_type, evidence = classify_bar_type(table, row_i, date_col_set)

        # 연속 구간 탐지
        start_col: int | None = None
        end_col: int | None = None
        seg_texts: list[str] = []
        seg_colors: list[str] = []

        def flush(sc, ec, texts, colors):
            if sc is None:
                return None
            bt = bar_type
            fc = colors[0] if colors else ""
            txt = " ".join(texts) if texts else ""
            conf = 0.85 if bt in ("text_full", "color_bar") else (
                0.75 if bt == "text_partial" else 0.60
            )
            return BarRangeInfo(
                row=row_i, colStart=sc, colEnd=ec,
                barType=bt, text=txt[:40], fillColor=fc,
                confidence=conf, evidence=evidence,
            )

        for col_i in sorted_date_cols:
            c = cells.get((row_i, col_i))
            text = (getattr(c, "normalizedText", "") or "").strip() if c else ""
            color = (getattr(c, "fillColor", "") or "") if c else ""
            has_content = bool(text) or bool(color and color.lower() not in ("ffffff", "none", ""))

            if has_content:
                if start_col is None:
                    start_col = col_i
                end_col = col_i
                if text:
                    seg_texts.append(text)
                if color and color.lower() not in ("ffffff", "none", ""):
                    seg_colors.append(color)
            else:
                r = flush(start_col, end_col, seg_texts, seg_colors)
                if r:
                    ranges.append(r)
                start_col = None
                end_col = None
                seg_texts = []
                seg_colors = []

        r = flush(start_col, end_col, seg_texts, seg_colors)
        if r:
            ranges.append(r)

        # empty_template은 명시적으로 1개의 범위로 기록
        if bar_type == "empty_template" and not any(br.row == row_i for br in ranges):
            ranges.append(BarRangeInfo(
                row=row_i,
                colStart=sorted_date_cols[0],
                colEnd=sorted_date_cols[-1],
                barType="empty_template",
                text="",
                fillColor="",
                confidence=0.60,
                evidence=evidence,
            ))

    return ranges


# ── STEP 5: 진행률 열 탐지 ───────────────────────────────────────────────────

def detect_progress_column(table) -> ProgressColumnInfo | None:
    cells = _cells_by_row_col(table)
    rows = getattr(table, "rowCount", 0)
    cols = getattr(table, "colCount", 0)

    for row_i in range(min(rows, 4)):
        for col_i in range(cols):
            c = cells.get((row_i, col_i))
            text = (getattr(c, "normalizedText", "") or "").strip().lower() if c else ""
            if text in {h.lower() for h in _PROGRESS_HEADERS}:
                return ProgressColumnInfo(
                    col=col_i,
                    headerText=(getattr(c, "normalizedText", "") or "").strip(),
                    confidence=0.90,
                )
    return None


# ── STEP 1: 공정표 구조 전체 탐지 ─────────────────────────────────────────────

def detect_schedule_structure(parser_result) -> list[ScheduleInfo]:
    """ParserV2Result에서 공정표 구조를 탐지해 ScheduleInfo 목록으로 반환."""
    results: list[ScheduleInfo] = []
    tables = getattr(parser_result, "tables", [])

    for table in tables:
        axis = detect_time_axis(table)
        if axis.confidence < 0.30 and not axis.dateColumns:
            continue  # 날짜축 없는 테이블 스킵

        task_rows = detect_task_rows(table, axis)
        if not task_rows:
            continue

        bar_ranges = detect_bar_ranges(table, axis, task_rows)
        progress_col = detect_progress_column(table)

        # confidence 계산
        conf = round(
            axis.confidence * 0.50
            + (0.30 if task_rows else 0.0)
            + (0.10 if bar_ranges else 0.0)
            + (0.10 if progress_col else 0.0),
            3,
        )

        evidence = [f"tableId={table.tableId}", f"axis_unit={axis.unit}"]
        warnings: list[str] = list(getattr(axis, "warnings", []) or [])
        if not bar_ranges:
            warnings.append("bar_ranges_empty")
        if not task_rows:
            warnings.append("task_rows_empty")

        results.append(ScheduleInfo(
            tableId=getattr(table, "tableId", ""),
            scheduleType="gantt_bar_schedule",
            confidence=conf,
            timeAxis=axis,
            taskRows=task_rows,
            barRanges=bar_ranges,
            progressColumn=progress_col,
            warnings=warnings,
            evidence=evidence,
        ))

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# HWPX-SCHEDULE-BAR-RANGE-DETECTOR-01
# date range → col range 변환 및 bar plan candidate 생성
# ═══════════════════════════════════════════════════════════════════════════════

_RE_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
_RE_ISO_MONTH = re.compile(r"^(\d{4})-(\d{2})$")
_RE_SLASH_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})$")


# ── STEP 2: normalize 함수 ────────────────────────────────────────────────────

def normalize_month_label(label: str) -> str:
    """월 레이블을 'month:N' 형태로 반환."""
    t = label.strip()
    m = _RE_MONTH_KR.match(t)
    if m:
        return f"month:{int(m.group(1))}"
    if t.isdigit():
        v = int(t)
        if 1 <= v <= 12:
            return f"month:{v}"
    return ""


def normalize_week_label(label: str) -> str:
    t = label.strip()
    m = _RE_WEEK_KR.match(t)
    if m:
        return f"week:{int(m.group(1))}"
    # "제1주" 형태
    m2 = re.match(r"^제(\d+)주(?:차)?$", t)
    if m2:
        return f"week:{int(m2.group(1))}"
    return ""


def normalize_day_label(label: str) -> str:
    t = label.strip()
    if _RE_DAY_NUM.match(t):
        return f"day:{int(t)}"
    m = _RE_SLASH_DATE.match(t)
    if m:
        return f"date:{t}"
    return ""


def normalize_schedule_date(value: str, axis_unit: str = "unknown") -> str:
    """날짜/라벨 입력을 axis_unit에 맞는 정규화 태그로 변환.

    반환 예: 'month:5', 'week:3', 'day:15', 'date:5/20'
    """
    if not value:
        return ""
    t = value.strip()

    # ISO 날짜 (YYYY-MM-DD or YYYY-MM)
    m = _RE_ISO_DATE.match(t)
    if m:
        month = int(m.group(2))
        day = int(m.group(3)) if m.group(3) else None
        if axis_unit in ("month", "unknown"):
            return f"month:{month}"
        if axis_unit == "day" and day:
            return f"day:{day}"
        return f"month:{month}"

    # 월 레이블
    norm = normalize_month_label(t)
    if norm:
        return norm

    # 주 레이블
    norm = normalize_week_label(t)
    if norm:
        return norm

    # 일 레이블
    norm = normalize_day_label(t)
    if norm:
        return norm

    return f"label:{t}"


def extract_month_from_date(value: str) -> int | None:
    t = value.strip()
    m = _RE_ISO_DATE.match(t)
    if m:
        return int(m.group(2))
    norm = normalize_month_label(t)
    if norm.startswith("month:"):
        return int(norm.split(":")[1])
    return None


def extract_day_from_date(value: str) -> int | None:
    t = value.strip()
    m = _RE_ISO_DATE.match(t)
    if m and m.group(3):
        return int(m.group(3))
    norm = normalize_day_label(t)
    if norm.startswith("day:"):
        return int(norm.split(":")[1])
    return None


# ── STEP 3: date range → col range 변환 ──────────────────────────────────────

def map_date_range_to_columns(
    time_axis: TimeAxisInfo,
    start_date: str,
    end_date: str,
) -> tuple[int, int, ScheduleDateRange]:
    """timeAxis.dateColumns 기준으로 start/end를 colStart/colEnd로 변환.

    반환: (colStart, colEnd, ScheduleDateRange)
    colStart=-1이면 매핑 실패.
    """
    warnings: list[str] = []
    norm_start = normalize_schedule_date(start_date, time_axis.unit)
    norm_end = normalize_schedule_date(end_date, time_axis.unit)

    date_range = ScheduleDateRange(
        startDate=start_date,
        endDate=end_date,
        normalizedStart=norm_start,
        normalizedEnd=norm_end,
        unit=time_axis.unit,
    )

    if not time_axis.dateColumns:
        warnings.append("no_date_columns_in_axis")
        date_range.warnings = warnings
        return -1, -1, date_range

    col_map: dict[str, int] = {d.normalized: d.col for d in time_axis.dateColumns}
    sorted_cols = sorted(time_axis.dateColumns, key=lambda d: d.col)

    col_start = col_map.get(norm_start, -1)
    col_end = col_map.get(norm_end, -1)

    # 범위 시작/끝이 직접 매핑 안 되면 인접 탐색 (같은 unit prefix)
    if col_start == -1:
        for d in sorted_cols:
            if d.normalized == norm_start:
                col_start = d.col
                break
        if col_start == -1:
            warnings.append(f"start_not_in_axis: {norm_start}")

    if col_end == -1:
        for d in reversed(sorted_cols):
            if d.normalized == norm_end:
                col_end = d.col
                break
        if col_end == -1:
            warnings.append(f"end_not_in_axis: {norm_end}")

    # 부분 매핑 처리
    if col_start == -1 and col_end != -1:
        col_start = sorted_cols[0].col
        warnings.append("start_out_of_range_clamped_to_first_col")
    if col_end == -1 and col_start != -1:
        col_end = sorted_cols[-1].col
        warnings.append("end_out_of_range_clamped_to_last_col")
    if col_start == -1 and col_end == -1:
        warnings.append("no_range_match")
        date_range.warnings = warnings
        return -1, -1, date_range

    # start > end 검사
    if col_start > col_end:
        warnings.append(f"start_col({col_start}) > end_col({col_end}): reversed or invalid range")
        date_range.warnings = warnings
        return col_start, col_end, date_range

    # 레이블 기록
    start_dc = next((d for d in sorted_cols if d.col == col_start), None)
    end_dc = next((d for d in sorted_cols if d.col == col_end), None)
    date_range.startLabel = start_dc.label if start_dc else ""
    date_range.endLabel = end_dc.label if end_dc else ""
    date_range.warnings = warnings

    return col_start, col_end, date_range


# ── STEP 4: task row 매칭 ─────────────────────────────────────────────────────

def find_task_row(
    task_rows: list[TaskRowInfo],
    task_name: str | None = None,
    row: int | None = None,
    trade: str | None = None,
) -> tuple[TaskRowInfo | None, float, list[str], str | None]:
    """task row를 찾아 (matched, confidence, evidence, reviewRequiredReason) 반환."""

    # 우선순위 1: 명시 row
    if row is not None:
        for tr in task_rows:
            if tr.row == row:
                return tr, 0.98, [f"explicit_row={row}"], None
        return None, 0.0, [f"row={row}_not_found"], f"row {row} not found in task_rows"

    if not task_name:
        return None, 0.0, ["no_task_name_or_row"], "task_name required"

    # 우선순위 2: exact match
    for tr in task_rows:
        if tr.taskName == task_name:
            return tr, 0.95, [f"exact_match={task_name!r}"], None

    # 우선순위 3: contains match
    candidates = [tr for tr in task_rows if task_name in tr.taskName or tr.taskName in task_name]
    if len(candidates) == 1:
        return candidates[0], 0.80, [f"contains_match={task_name!r}"], None
    if len(candidates) > 1:
        # 가장 짧은 것 (가장 구체적)
        best = min(candidates, key=lambda t: len(t.taskName))
        return best, 0.65, [f"multi_contains_match={task_name!r}", f"selected={best.taskName!r}"], \
               f"multiple matches for {task_name!r}"

    # 우선순위 4: trade + taskName
    if trade:
        for tr in task_rows:
            if trade in (tr.trade or "") or trade in " ".join(tr.leftText or []):
                return tr, 0.60, [f"trade_match={trade!r}"], f"matched via trade only"

    return None, 0.0, [f"no_match_for={task_name!r}"], f"task not found: {task_name!r}"


# ── STEP 5: bar plan candidate 생성 ──────────────────────────────────────────

def build_schedule_bar_plan_candidate(
    schedule_info: ScheduleInfo,
    request: ScheduleBarRangeRequest,
) -> ScheduleBarPlanCandidate:
    """ScheduleInfo + request로 BarPlanCandidate를 생성한다."""
    axis = schedule_info.timeAxis
    table_id = schedule_info.tableId
    evidence: list[str] = []
    warnings: list[str] = []

    # task row 매칭
    matched_tr, tr_conf, tr_evidence, tr_warn = find_task_row(
        schedule_info.taskRows,
        task_name=request.taskName or None,
        row=request.row,
        trade=request.trade or None,
    )
    evidence.extend(tr_evidence)
    if tr_warn:
        warnings.append(tr_warn)

    row = matched_tr.row if matched_tr else -1
    task_name = matched_tr.taskName if matched_tr else request.taskName

    # date → col 변환
    col_start, col_end, date_range = map_date_range_to_columns(
        axis, request.startDate, request.endDate
    )
    warnings.extend(date_range.warnings)
    evidence.append(f"colStart={col_start}, colEnd={col_end}")

    # source 결정
    source = "calculated_from_dates"
    if col_start == -1 and col_end == -1:
        source = "no_axis_match"

    # confidence 계산
    conf = round(tr_conf * 0.5 + (0.50 if col_start != -1 else 0.0), 3)
    review_required = (col_start == -1 or col_end == -1 or col_start > col_end
                       or matched_tr is None or bool(warnings))
    review_reason: str | None = "; ".join(warnings) if warnings else None

    # 기존 barRange 탐색
    existing_bar_type = ""
    for br in schedule_info.barRanges:
        if br.row == row:
            existing_bar_type = br.barType
            break

    # 충돌 검사
    conflict = detect_bar_conflict(
        [br for br in schedule_info.barRanges if br.row == row],
        col_start, col_end,
    )

    return ScheduleBarPlanCandidate(
        tableId=table_id,
        row=row,
        taskName=task_name,
        colStart=col_start,
        colEnd=col_end,
        axisUnit=axis.unit,
        startLabel=date_range.startLabel,
        endLabel=date_range.endLabel,
        color=request.color,
        text=request.text,
        textAt=request.textAt,
        confidence=conf,
        source=source,
        existingBarType=existing_bar_type,
        conflict=conflict,
        reviewRequired=review_required,
        reviewRequiredReason=review_reason,
        evidence=evidence,
        warnings=warnings,
    )


# ── STEP 6: 충돌 검사 ────────────────────────────────────────────────────────

def detect_bar_conflict(
    existing_ranges: list[BarRangeInfo],
    col_start: int,
    col_end: int,
) -> str:
    """새 candidate와 기존 barRanges의 충돌 유형을 반환."""
    if col_start == -1 or col_end == -1:
        return "outside_axis_range"

    if not existing_ranges:
        return "no_conflict"

    for br in existing_ranges:
        bt = br.barType
        ex_s, ex_e = br.colStart, br.colEnd

        # 범위 겹침 판단
        overlap = not (col_end < ex_s or col_start > ex_e)
        if not overlap:
            continue

        if bt == "empty_template":
            return "replaces_existing_empty_template"
        if bt in ("text_full", "color_bar"):
            return "overlaps_existing_bar"
        if bt == "text_partial":
            # 완전 포함이면 replace, 부분 겹치면 overlap
            if col_start <= ex_s and col_end >= ex_e:
                return "overlaps_existing_bar"
            return "extends_existing_bar"

    return "no_conflict"


# ── STEP 7: empty_template 후보 자동 생성 ────────────────────────────────────

def generate_empty_template_bar_candidates(
    schedule_info: ScheduleInfo,
    default_start: str | None = None,
    default_end: str | None = None,
) -> list[ScheduleBarPlanCandidate]:
    """빈 공정표에서 각 task row의 입력 가능 range 후보를 생성한다."""
    axis = schedule_info.timeAxis
    candidates: list[ScheduleBarPlanCandidate] = []

    if not axis.dateColumns:
        return candidates

    sorted_cols = sorted(axis.dateColumns, key=lambda d: d.col)
    default_col_start = sorted_cols[0].col
    default_col_end = sorted_cols[-1].col
    default_start_label = sorted_cols[0].label
    default_end_label = sorted_cols[-1].label

    # request로 범위가 주어진 경우 우선 사용
    req_col_start = default_col_start
    req_col_end = default_col_end
    req_start_label = default_start_label
    req_end_label = default_end_label
    req_warnings: list[str] = []

    if default_start and default_end:
        cs, ce, dr = map_date_range_to_columns(axis, default_start, default_end)
        if cs != -1:
            req_col_start = cs
            req_col_end = ce
            req_start_label = dr.startLabel
            req_end_label = dr.endLabel
            req_warnings = dr.warnings

    for tr in schedule_info.taskRows:
        existing_bar_type = ""
        for br in schedule_info.barRanges:
            if br.row == tr.row:
                existing_bar_type = br.barType
                break

        conflict = detect_bar_conflict(
            [br for br in schedule_info.barRanges if br.row == tr.row],
            req_col_start, req_col_end,
        )
        source = "empty_template_candidate"
        conf = 0.70 if not req_warnings else 0.55

        candidates.append(ScheduleBarPlanCandidate(
            tableId=schedule_info.tableId,
            row=tr.row,
            taskName=tr.taskName,
            colStart=req_col_start,
            colEnd=req_col_end,
            axisUnit=axis.unit,
            startLabel=req_start_label,
            endLabel=req_end_label,
            color="",
            text="",
            textAt="center",
            confidence=conf,
            source=source,
            existingBarType=existing_bar_type,
            conflict=conflict,
            reviewRequired=bool(req_warnings),
            reviewRequiredReason="; ".join(req_warnings) if req_warnings else None,
            evidence=[f"row={tr.row}", f"taskName={tr.taskName!r}",
                      f"colStart={req_col_start}", f"colEnd={req_col_end}"],
            warnings=list(req_warnings),
        ))

    return candidates
