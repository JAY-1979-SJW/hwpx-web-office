"""
HWPX-RECOGNITION-LABEL-TAXONOMY-AND-LAYOUT-SEED-01

layout_classifier.py — 표 메타데이터 기반 레이아웃 분류 모듈.

레이아웃 타입:
    HEADER_COLUMN_FORM       헤더 기반 입력셀 구조 (header_column 다수)
    LABEL_ADJACENT_FORM      2-col 라벨-값 쌍 구조
    FORM_FIELD_INLINE        form_table 내 인라인 입력 셀
    PUBLIC_DOC_APPROVAL_FORM 공문서 접수/결재/직인 영역
    BACK_SIDE_FORM           뒤쪽/앞쪽/뒷면 페이지 구조
    GANTT_LIKE_SCHEDULE      날짜 기반 Gantt 공정표
    HORIZONTAL_SCHEDULE      가로 날짜 축 일정표
    TABLE_LIST_ONLY          데이터 목록형 (입력셀 없음)
    UNKNOWN                  미분류
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ── 레이아웃 타입 상수 ────────────────────────────────────────────────────────
LT_HEADER_COL      = "HEADER_COLUMN_FORM"
LT_LABEL_ADJ       = "LABEL_ADJACENT_FORM"
LT_FORM_INLINE     = "FORM_FIELD_INLINE"
LT_APPROVAL        = "PUBLIC_DOC_APPROVAL_FORM"
LT_BACK_SIDE       = "BACK_SIDE_FORM"
LT_GANTT           = "GANTT_LIKE_SCHEDULE"
LT_H_SCHEDULE      = "HORIZONTAL_SCHEDULE"
LT_LIST_ONLY       = "TABLE_LIST_ONLY"
LT_UNKNOWN         = "UNKNOWN"

# ── 공문서 승인 영역 키워드 ──────────────────────────────────────────────────
_APPROVAL_KEYWORDS = frozenset({
    "접수", "직인", "결재", "담당", "검토", "승인", "기안",
    "전결", "대결", "서명", "서명란", "인", "날인", "확인인",
    "계장", "과장", "부장", "팀장", "국장", "처장", "차장",
})
# ── 뒤쪽 마커 ────────────────────────────────────────────────────────────────
_BACK_PATTERN = re.compile(
    r"뒤?쪽|뒷?\s*면|앞\s*쪽?|앞\s*면"
    r"|[(\[]\s*제?\s*\d+\s*쪽"
    r"|\d+\s*/\s*\d+\s*쪽",
    re.IGNORECASE,
)
# ── 날짜 헤더 패턴 ───────────────────────────────────────────────────────────
_DATE_PATTERN = re.compile(
    r"^\d{4}[-./]\d{1,2}([-./]\d{1,2})?$"
    r"|^\d{1,2}월$"
    r"|^\d{1,2}주차?$"
    r"|^Q[1-4]$"
    r"|^\d{4}년$"
    r"|^\d{1,2}[-./]\d{1,2}$",
    re.IGNORECASE,
)
# ── 공정 키워드 ──────────────────────────────────────────────────────────────
_SCHEDULE_KEYWORDS = frozenset({
    "공종", "작업명", "시작일", "착수일", "종료일", "완료일",
    "기간", "공기", "진행률", "공정명", "task", "start", "end",
    "duration", "공정표",
})


@dataclass
class LayoutClassification:
    layoutType: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layoutType": self.layoutType,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
        }


# ── 분류 함수 ─────────────────────────────────────────────────────────────────

def classify_layout(
    header_texts: list[str],
    input_cell_types: dict[str, int],   # {"header_column": N, "label_adjacent": M, ...}
    total_cells: int,
    empty_cells: int,
    row_count: int,
    col_count: int,
    input_cell_count: int,
) -> LayoutClassification:
    """
    표 수준 메타데이터로 레이아웃을 분류.

    Args:
        header_texts: 정규화된 헤더 텍스트 목록
        input_cell_types: 입력셀 타입별 카운트
        total_cells: 전체 셀 수
        empty_cells: 빈 셀 수
        row_count: 행 수
        col_count: 열 수
        input_cell_count: 입력셀 후보 총 수
    """
    evidence: list[str] = []
    n_hdr_col = input_cell_types.get("header_column", 0)
    n_lbl_adj = input_cell_types.get("label_adjacent", 0)
    n_form    = input_cell_types.get("form_field", 0)

    # ── 1. 뒤쪽/앞쪽 형식 ────────────────────────────────────────────────────
    back_hits = sum(1 for h in header_texts if _BACK_PATTERN.search(h))
    if back_hits >= 1:
        evidence.append(f"back/front page marker in headers ({back_hits})")
        return LayoutClassification(LT_BACK_SIDE, 0.90, evidence)

    # ── 2. 공문서 승인/결재 영역 ──────────────────────────────────────────────
    approval_hits = sum(1 for h in header_texts if h in _APPROVAL_KEYWORDS)
    if approval_hits >= 2 or (approval_hits >= 1 and total_cells <= 20):
        conf = min(0.70 + approval_hits * 0.05, 0.95)
        evidence.append(f"approval/stamp keywords ({approval_hits}): {[h for h in header_texts if h in _APPROVAL_KEYWORDS][:5]}")
        return LayoutClassification(LT_APPROVAL, conf, evidence)

    # ── 3. Gantt 공정표 ───────────────────────────────────────────────────────
    date_cols = sum(1 for h in header_texts if _DATE_PATTERN.match(h))
    if date_cols >= 4 and col_count >= 6:
        conf = min(0.70 + 0.04 * date_cols, 0.95)
        evidence.append(f"date columns={date_cols}, col_count={col_count}")
        return LayoutClassification(LT_GANTT, conf, evidence)

    # ── 4. 수평 일정표 ────────────────────────────────────────────────────────
    sched_hits = sum(1 for h in header_texts if h.lower() in _SCHEDULE_KEYWORDS)
    if date_cols >= 1 and sched_hits >= 2:
        evidence.append(f"date_cols={date_cols}, schedule_keywords={sched_hits}")
        return LayoutClassification(LT_H_SCHEDULE, 0.80, evidence)
    if sched_hits >= 3 and row_count >= 3:
        layout_t = LT_H_SCHEDULE if col_count > row_count else "VERTICAL_SCHEDULE"
        evidence.append(f"schedule_keywords={sched_hits}, rows={row_count}, cols={col_count}")
        return LayoutClassification(layout_t, 0.75, evidence)

    # ── 5. label_adjacent form ────────────────────────────────────────────────
    if n_lbl_adj > 0 and col_count == 2:
        conf = min(0.70 + n_lbl_adj * 0.02, 0.92)
        evidence.append(f"label_adjacent={n_lbl_adj}, col_count=2")
        return LayoutClassification(LT_LABEL_ADJ, conf, evidence)

    # ── 6. form_field (form_table 내 인라인) ─────────────────────────────────
    if n_form > 0:
        conf = min(0.65 + n_form * 0.03, 0.90)
        evidence.append(f"form_field={n_form}")
        return LayoutClassification(LT_FORM_INLINE, conf, evidence)

    # ── 7. header_column form ────────────────────────────────────────────────
    if n_hdr_col > 0 and total_cells > 0:
        empty_ratio = empty_cells / total_cells
        if empty_ratio >= 0.20:
            conf = min(0.65 + empty_ratio * 0.5, 0.92)
            evidence.append(f"header_column={n_hdr_col}, empty_ratio={empty_ratio:.2f}")
            return LayoutClassification(LT_HEADER_COL, conf, evidence)

    # ── 8. 목록형 (입력셀 없고 데이터 행 다수) ───────────────────────────────
    if input_cell_count == 0 and row_count >= 3:
        evidence.append(f"no input cells, rows={row_count}")
        return LayoutClassification(LT_LIST_ONLY, 0.70, evidence)

    # ── 9. 미분류 ─────────────────────────────────────────────────────────────
    evidence.append(
        f"no rule matched: hdr_col={n_hdr_col} lbl_adj={n_lbl_adj} "
        f"rows={row_count} cols={col_count} empty_ratio="
        f"{(empty_cells/total_cells if total_cells else 0):.2f}"
    )
    return LayoutClassification(LT_UNKNOWN, 0.0, evidence)


# ── 파일 수준 레이아웃 요약 분류 ────────────────────────────────────────────

def classify_file_layout(
    header_texts_all: list[str],
    input_type_dist: dict[str, int],
    total_cells: int,
    empty_cells: int,
    table_count: int,
) -> LayoutClassification:
    """파일 전체 수준의 레이아웃 분류 (표 단위 분류의 집계 버전)."""
    evidence: list[str] = []
    n_hdr_col = input_type_dist.get("header_column", 0)
    n_lbl_adj = input_type_dist.get("label_adjacent", 0)
    n_form    = input_type_dist.get("form_field", 0)
    total_input = n_hdr_col + n_lbl_adj + n_form

    # 뒤쪽 마커
    back_hits = sum(1 for h in header_texts_all if _BACK_PATTERN.search(h))
    if back_hits >= table_count * 0.5 and back_hits >= 1:
        evidence.append(f"back_side headers={back_hits}")
        return LayoutClassification(LT_BACK_SIDE, 0.85, evidence)

    # 결재 영역 지배
    approval_hits = sum(1 for h in header_texts_all if h in _APPROVAL_KEYWORDS)
    if approval_hits >= len(header_texts_all) * 0.4 and approval_hits >= 3:
        evidence.append(f"approval headers={approval_hits}/{len(header_texts_all)}")
        return LayoutClassification(LT_APPROVAL, 0.80, evidence)

    # header_column 지배적
    if total_input > 0 and n_hdr_col / total_input >= 0.90:
        evidence.append(f"header_column dominates: {n_hdr_col}/{total_input}")
        return LayoutClassification(LT_HEADER_COL, 0.88, evidence)

    # label_adjacent 지배적
    if total_input > 0 and n_lbl_adj / total_input >= 0.60:
        evidence.append(f"label_adjacent dominates: {n_lbl_adj}/{total_input}")
        return LayoutClassification(LT_LABEL_ADJ, 0.80, evidence)

    if total_input == 0 and table_count >= 1:
        evidence.append("no input cells detected")
        return LayoutClassification(LT_LIST_ONLY, 0.65, evidence)

    evidence.append("mixed layout")
    return LayoutClassification(LT_UNKNOWN, 0.30, evidence)


# ── 배치 분류: survey per-file 결과를 받아 레이아웃 재분류 ────────────────────

def reclassify_from_survey(
    per_file_records: list[dict],
) -> list[dict[str, Any]]:
    """
    survey_per_file.jsonl 레코드를 받아 HEADER_COLUMN_FORM 등 새 레이아웃 타입으로 분류.
    """
    results = []
    for rec in per_file_records:
        fid = rec.get("maskedFileId", "")
        input_dist = {"header_column": 0, "label_adjacent": 0, "form_field": 0}
        # layoutCounter는 구버전 분류기 결과 — inputCellCount로 우선 처리
        # per-file record에 inputCellType 분포가 없으면 inputCellCount로 추정
        ic_count = rec.get("inputCellCount", 0)
        tc = rec.get("totalCells", 1) or 1
        ec = rec.get("emptyCells", 0)
        tables = rec.get("tableCount", 0)
        hdrs = []  # raw header texts는 per-file record에 없음 — layoutCounter로 힌트 추출

        # layoutCounter에서 힌트
        lc = rec.get("layoutCounter", {})
        if lc.get("form_table", 0) > 0:
            input_dist["form_field"] += lc["form_table"]
        if lc.get("vertical_table", 0) > 0 or lc.get("horizontal_table", 0) > 0:
            input_dist["label_adjacent"] += lc.get("vertical_table", 0)
        # 나머지는 header_column으로 간주
        remaining = ic_count - sum(input_dist.values())
        if remaining > 0:
            input_dist["header_column"] += remaining

        lc_result = classify_file_layout(
            header_texts_all=hdrs,
            input_type_dist=input_dist,
            total_cells=tc,
            empty_cells=ec,
            table_count=tables,
        )
        results.append({
            "maskedFileId": fid,
            **lc_result.to_dict(),
            "tableCount": tables,
            "inputCellCount": ic_count,
            "emptyCellCount": ec,
        })
    return results
