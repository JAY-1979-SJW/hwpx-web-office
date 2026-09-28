"""
HWPX-RECOGNITION-LABEL-TAXONOMY-AND-LAYOUT-SEED-01

label_taxonomy.py — 헤더/입력셀 라벨 → semantic field 정규화 모듈.

분류 결과:
    MAPPED_HIGH_CONFIDENCE      신뢰도 ≥ 0.90
    MAPPED_MEDIUM_CONFIDENCE    신뢰도 ≥ 0.60
    REVIEW_REQUIRED_LOW_CONFIDENCE  신뢰도 < 0.60
    IGNORED_PUBLIC_DOC_META     공문서 접수/결재/직인 영역
    IGNORED_DECORATIVE_OR_STAMP 장식/기호/도장 영역
    BACK_SIDE_HINT              (뒤쪽)/뒷면/앞쪽 페이지 마커
    SCHEDULE_CANDIDATE          공정표/일정표 후보
    UNKNOWN                     매핑 불가

절대 금지: AI API / OCR 호출 없음 / low confidence 자동 확정 없음
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# ── 분류 상수 ─────────────────────────────────────────────────────────────────
CLS_HIGH = "MAPPED_HIGH_CONFIDENCE"
CLS_MEDIUM = "MAPPED_MEDIUM_CONFIDENCE"
CLS_LOW = "REVIEW_REQUIRED_LOW_CONFIDENCE"
CLS_META = "IGNORED_PUBLIC_DOC_META"
CLS_DECO = "IGNORED_DECORATIVE_OR_STAMP"
CLS_BACK = "BACK_SIDE_HINT"
CLS_SCHED = "SCHEDULE_CANDIDATE"
CLS_UNKNOWN = "UNKNOWN"

# ── 공문서 메타 영역 (접수/결재/직인 계열) ────────────────────────────────────
_META_EXACT: set[str] = {
    "접수",
    "직인",
    "결재",
    "담당",
    "검토",
    "승인",
    "통보",
    "시행",
    "문서번호",
    "시행일자",
    "수신",
    "참조",
    "발신",
    "수신처",
    "발신처",
    "계장",
    "과장",
    "부장",
    "팀장",
    "국장",
    "처장",
    "차장",
    "기안",
    "전결",
    "대결",
    "전결기준",
    "인",
    "서명또는인",
    "신청서",
    "신고서",
    "신고필증",
    "처리절차",
    "신청서작성",
    "신고서작성",
    "신고필증작성",
    "신고필증교부",
}
_META_CONTAINS: tuple[str, ...] = (
    "결재란",
    "접수란",
    "처리란",
    "접수일",
    "접수부서",
    "신청서",
    "신고서",
    "처리기간",
    "수신기관",
)

# ── 장식/기호/도장 영역 ───────────────────────────────────────────────────────
_DECO_EXACT: set[str] = {
    "→",
    "‣",
    "■",
    "▶",
    "➡",
    "▲",
    "◆",
    "●",
    "○",
    "△",
    "※",
    "☆",
    "★",
    "◎",
    "·",
    "・",
    "•",
    ". . .",
    "…",
    "A",
    "B",
    "C",
    "Q",
    "I",
    "II",
    "III",
    "IV",
    "1",
    "2",
    "3",
    "4",
    "5",
}
_DECO_RE = re.compile(
    r"^[\s\-_=\*\#\@\!\?\,\.\;\:\'\"\`\~\^\&\%\$\|\(\)\[\]\{\}]+$"
    r"|^[0-9]+$"
    r"|^[가-힣]{1}$"  # 단일 한글 글자
    r"|^\([가-힣]{1}\)$"  # (가) 형식
    r"|^\([0-9]+쪽.*\)$"  # (N쪽) 형식
)

# ── 뒷면/앞면 페이지 마커 ─────────────────────────────────────────────────────
_BACK_RE = re.compile(
    r"뒤쪽|뒷면|앞쪽|앞면"
    r"|[(\[（]\s*뒤쪽\s*[)\]）]"
    r"|[(\[（]\s*뒷면\s*[)\]）]"
    r"|[(\[（]\s*앞쪽\s*[)\]）]"
    r"|[(\[（]\s*앞면\s*[)\]）]"
    r"|[(\[（]\s*제?\s*\d+\s*쪽\s*(중\s*제\s*\d+\s*쪽)?\s*[)\]）]"
    r"|\(\d+쪽중[제]?\d+쪽\)"
    r"|\d+\s*/\s*\d+\s*쪽",
    re.IGNORECASE,
)

# ── Semantic Field 매핑 규칙 ──────────────────────────────────────────────────
# (field_name, confidence, [exact_matches], [contains_patterns])
_FIELD_RULES: list[tuple[str, float, set[str], tuple[str, ...]]] = [
    # ── taskName ──────────────────────────────────────────────────────────────
    (
        "taskName",
        0.95,
        {
            "항목",
            "내용",
            "작업명",
            "업무내용",
            "공사내용",
        },
        (
            "검사항목",
            "점검항목",
            "평가항목",
            "확인항목",
            "조치사항",
            "불량내용",
            "요구사항분류",
            "보안요구사항",
            "구축기준",
            "1차검사항목",
            "2차검사항목",
            "차검사항목",
            "평가내용",
            "시정내용",
            "조치내용",
            "점검내용",
        ),
    ),
    # ── number / receiptNumber ─────────────────────────────────────────────────
    (
        "receiptNumber",
        0.95,
        {
            "접수번호",
            "접수일련번호",
        },
        (
            "접수번",
            "문서접수",
        ),
    ),
    (
        "number",
        0.95,
        {
            "번호",
            "연번",
            "일련번호",
            "순번",
            "일련",
        },
        (
            "고유번호",
            "관리번호",
            "점검번호",
            "요구사항고유번호",
            "발급번호",
            "법인등록번호",
        ),
    ),
    # ── inspectionStatus ──────────────────────────────────────────────────────
    (
        "inspectionStatus",
        0.95,
        {
            "검사결과",
            "점검결과",
            "검측결과",
            "확인결과",
            "적합",
            "부적합",
            "합격",
            "불합격",
        },
        (
            "검사기준",
            "점검기준",
            "검측기준",
            "판정기준",
            "조치결과",
            "조치확인",
            "시정여부",
            "이행여부",
            "검사항목",
            "점검항목",
            "검측항목",
            "소방시설부분완공",
            "소방시설공사완공",
            "소방시설공사위반",
        ),
    ),
    # ── remarks ───────────────────────────────────────────────────────────────
    (
        "remarks",
        0.95,
        {
            "비고",
            "참고",
            "특기사항",
            "비고란",
        },
        (
            "특이사항",
            "검토의견",
            "조치의견",
            "부연설명",
        ),
    ),
    # ── responsiblePerson ─────────────────────────────────────────────────────
    (
        "responsiblePerson",
        0.95,
        {
            "성명",
            "성명:",
            "성 명",
            "담당자",
            "책임자",
            "서명",
            "서명란",
            "서명또는인",
        },
        (
            "담당자명",
            "확인자",
            "지정자",
            "작성자",
            "관리자",
            "감리원",
            "검사원",
            "점검자",
        ),
    ),
    # ── quantity ──────────────────────────────────────────────────────────────
    (
        "quantity",
        0.95,
        {
            "수량",
            "수 량",
            "qty",
        },
        (
            "수량(개)",
            "수량(식)",
            "설치수량",
            "검사수량",
        ),
    ),
    # ── contractorName ────────────────────────────────────────────────────────
    (
        "contractorName",
        0.95,
        {
            "시공사",
            "도급사",
            "수급인",
            "업체명",
            "시공업체",
            "상호",
            "회사명",
            "회사명:",
            "법인명",
        },
        (
            "수급업체",
            "하수급인",
            "협력업체",
            "전문업체",
        ),
    ),
    # ── durationDays ─────────────────────────────────────────────────────────
    (
        "durationDays",
        0.95,
        {
            "기간",
            "공기",
            "공사기간",
            "시공기간",
            "작업기간",
        },
        (
            "공사기간",
            "계약기간",
            "이행기간",
            "수행기간",
        ),
    ),
    # ── startDate / endDate ───────────────────────────────────────────────────
    (
        "startDate",
        0.95,
        {
            "시작일",
            "착수일",
            "착공일",
            "공사시작일",
            "계약시작일",
        },
        (
            "착공예정일",
            "시작예정일",
            "착수예정일",
        ),
    ),
    (
        "endDate",
        0.95,
        {
            "종료일",
            "완료일",
            "준공일",
            "공사완료일",
            "공사종료일",
            "완공일",
        },
        (
            "준공예정일",
            "완료예정일",
            "종료예정일",
        ),
    ),
    # ── projectName / siteName ────────────────────────────────────────────────
    (
        "projectName",
        0.95,
        {
            "공사명",
            "사업명",
            "프로젝트명",
            "공사 명",
        },
        (
            "공사명칭",
            "사업명칭",
        ),
    ),
    (
        "siteName",
        0.95,
        {
            "현장명",
            "공사현장",
        },
        (
            "현장 명",
            "공사현장명",
        ),
    ),
    # ── documentTitle ─────────────────────────────────────────────────────────
    (
        "documentTitle",
        0.80,
        set(),
        (
            "신청서",
            "신고서",
            "확인서",
            "보고서",
            "계획서",
            "점검표",
            "평가서",
            "검토서",
            "결과보고서",
        ),
    ),
    # ── location ──────────────────────────────────────────────────────────────
    (
        "location",
        0.90,
        {
            "위치",
            "장소",
            "구간",
            "설치위치",
            "점검위치",
        },
        (
            "설치장소",
            "공사위치",
            "제조소",
            "저장소",
            "취급소",
            "제조소[",
            "저장소[",
            "취급소[",
        ),
    ),
    # ── testType / testItem / testMethod / testFrequency ──────────────────────
    (
        "testType",
        0.95,
        {"종별", "시험종별"},
        (
            "시험종류",
            "검사종류",
        ),
    ),
    (
        "testItem",
        0.95,
        {"시험종목", "시험항목"},
        (
            "검사종목",
            "시험목록",
        ),
    ),
    (
        "testMethod",
        0.95,
        {"시험방법", "검사방법"},
        (
            "시험 방법",
            "검사 방법",
        ),
    ),
    ("testFrequency", 0.95, {"시험빈도", "검사빈도", "점검빈도"}, ("시험 빈도",)),
    # ── specification / unit / unitPrice / amount ────────────────────────────
    (
        "spec",
        0.95,
        {"규격", "사양", "사 양", "재질"},
        (
            "규 격",
            "제품규격",
        ),
    ),
    ("unit", 0.95, {"단위", "단 위"}, ("측정단위",)),
    ("unitPrice", 0.90, {"단가", "단 가"}, ("단위가격",)),
    (
        "amount",
        0.90,
        {"금액", "계약금액"},
        (
            "총금액",
            "합계금액",
        ),
    ),
    # ── approvalDate / submitDate ─────────────────────────────────────────────
    (
        "reportDate",
        0.90,
        {"작성일", "보고일", "제출일", "신청일"},
        (
            "보고일자",
            "제출일자",
        ),
    ),
    ("approvalDate", 0.90, {"승인일", "결재일", "허가일"}, ("승인일자",)),
    # ── representativeName ────────────────────────────────────────────────────
    ("representativeName", 0.80, {"대표자", "대표이사"}, ("대표자명",)),
    # ── inspectionFrequency ───────────────────────────────────────────────────
    ("inspectionFrequency", 0.90, {"점검주기", "검사주기"}, ("점검 주기",)),
    # ── trade ────────────────────────────────────────────────────────────────
    (
        "trade",
        0.95,
        {"공종", "공정"},
        (
            "공 종",
            "세부공종",
        ),
    ),
    # ── progressRate ─────────────────────────────────────────────────────────
    (
        "progressRate",
        0.95,
        {
            "진행률",
            "진도율",
            "달성률",
            "완료율",
        },
        (
            "진행 율",
            "공정률",
        ),
    ),
    # ── materialStatus ────────────────────────────────────────────────────────
    (
        "materialStatus",
        0.90,
        {
            "자재",
            "자재명",
            "재료명",
            "자재명및규격",
        },
        (
            "자재현황",
            "자재상태",
        ),
    ),
]

# ── 공정표 후보 키워드 ────────────────────────────────────────────────────────
_SCHEDULE_KEYWORDS = (
    "공정표",
    "예정공정",
    "일정표",
    "공정관리",
    "공정계획",
    "gantt",
    "schedule",
    "진행률",
    "진도율",
    "공정명",
)

# ── 집계용 도메인 분류 헤더 (total/계/합계 등) ──────────────────────────────
_AGGREGATE_EXACT: set[str] = {
    "총계",
    "소계",
    "합계",
    "계",
    "평균",
    "누계",
    "합",
    "총합",
    "소합",
    "중간합계",
}


# ── 정규화 ────────────────────────────────────────────────────────────────────


def normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\r\n\t]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", t)
    return t


# ── 분류 결과 ─────────────────────────────────────────────────────────────────


@dataclass
class LabelClassification:
    rawText: str
    normalizedText: str
    classification: str
    semanticField: str
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rawText": self.rawText,
            "normalizedText": self.normalizedText,
            "classification": self.classification,
            "semanticField": self.semanticField,
            "confidence": round(self.confidence, 3),
            "evidence": self.evidence,
        }


# ── 메인 분류 함수 ────────────────────────────────────────────────────────────


def _classify_semantic_field(raw: str, norm: str, low: str) -> LabelClassification | None:
    for field_name, base_conf, exact_set, contains_pats in _FIELD_RULES:
        if norm in exact_set or low in {e.lower() for e in exact_set}:
            conf = base_conf
            cls = CLS_HIGH if conf >= 0.90 else CLS_MEDIUM
            return LabelClassification(raw, norm, cls, field_name, conf, [f"exact match: {norm}"])
        for pat in contains_pats:
            if pat in norm or pat.lower() in low:
                conf = base_conf * 0.85
                cls = CLS_HIGH if conf >= 0.90 else CLS_MEDIUM
                return LabelClassification(raw, norm, cls, field_name, conf, [f"contains: {pat}"])
    return None


def _classify_structural_marker(raw: str, norm: str, low: str) -> LabelClassification | None:
    # 2. 뒷면/앞면 마커 (DECO보다 먼저 — (8쪽중제3쪽) 등)
    if _BACK_RE.search(norm):
        return LabelClassification(raw, norm, CLS_BACK, "", 1.0, ["back/front side marker"])

    # 3. 장식/기호
    if norm in _DECO_EXACT or _DECO_RE.match(norm):
        return LabelClassification(raw, norm, CLS_DECO, "", 1.0, ["decorative pattern"])

    # 4. 공문서 메타
    if norm in _META_EXACT:
        return LabelClassification(raw, norm, CLS_META, "", 1.0, [f"exact meta: {norm}"])
    for pat in _META_CONTAINS:
        if pat in norm:
            return LabelClassification(
                raw, norm, CLS_META, "", 0.90, [f"contains meta pattern: {pat}"]
            )

    # 5. 집계 행 (총계/소계 등)
    if norm in _AGGREGATE_EXACT:
        return LabelClassification(
            raw, norm, CLS_DECO, "aggregate", 0.95, ["aggregate/total marker"]
        )

    # 6. 공정표 후보
    for kw in _SCHEDULE_KEYWORDS:
        if kw in norm or kw.lower() in low:
            return LabelClassification(
                raw, norm, CLS_SCHED, "schedule", 0.80, [f"schedule keyword: {kw}"]
            )
    return None


def classify_label(raw: str) -> LabelClassification:
    norm = normalize(raw)
    low = norm.lower()

    # 1. 빈 텍스트
    if not norm:
        return LabelClassification(raw, norm, CLS_DECO, "", 1.0, ["empty text"])

    marker_result = _classify_structural_marker(raw, norm, low)
    if marker_result is not None:
        return marker_result

    # 7. semantic field 매핑 (exact → contains 순)
    field_result = _classify_semantic_field(raw, norm, low)
    if field_result is not None:
        return field_result

    # 8. 길이·형태 기반 저신뢰 분류
    if len(norm) <= 3 and re.match(r"^[0-9]+$", norm):
        return LabelClassification(raw, norm, CLS_DECO, "", 0.80, ["short numeric token"])

    # 9. 날짜 패턴 헤더 (연-월-일 형식)
    if re.match(r"^\d{4}[-./]\d{1,2}", norm):
        return LabelClassification(
            raw, norm, CLS_SCHED, "dateHeader", 0.75, ["date pattern header"]
        )

    # 10. 완전 미매핑
    return LabelClassification(raw, norm, CLS_UNKNOWN, "", 0.0, ["no rule matched"])


# ── 배치 분류 ────────────────────────────────────────────────────────────────


def classify_batch(
    labels: list[str],
) -> list[LabelClassification]:
    return [classify_label(lbl) for lbl in labels]


def classify_with_counts(
    label_freq: list[dict],  # {normalizedText, totalOccurrences, fileCount, ...}
) -> dict[str, Any]:
    """survey header/input-cell dictionary를 받아 전체 taxonomy 결과를 반환."""
    results: list[dict] = []
    counters: dict[str, int] = {
        CLS_HIGH: 0,
        CLS_MEDIUM: 0,
        CLS_LOW: 0,
        CLS_META: 0,
        CLS_DECO: 0,
        CLS_BACK: 0,
        CLS_SCHED: 0,
        CLS_UNKNOWN: 0,
    }
    field_dist: dict[str, int] = {}

    for row in label_freq:
        raw = row.get("normalizedText") or row.get("adjacentLabel") or ""
        occ = row.get("totalOccurrences") or row.get("occurrences") or 0
        fcnt = row.get("fileCount", 0)

        clsf = classify_label(raw)
        counters[clsf.classification] = counters.get(clsf.classification, 0) + 1
        if clsf.semanticField:
            field_dist[clsf.semanticField] = field_dist.get(clsf.semanticField, 0) + occ

        results.append({
            **clsf.to_dict(),
            "occurrences": occ,
            "fileCount": fcnt,
        })

    return {
        "totalLabels": len(results),
        "classificationCounts": counters,
        "fieldDistribution": dict(sorted(field_dist.items(), key=lambda kv: kv[1], reverse=True)),
        "records": results,
    }
