"""
HWPX-FORM-TYPE-CLASSIFICATION-01

form_type_classifier.py — 파일명 기반 서식 유형 분류 모듈.

서식명(formName): [별지_제N호서식]_서식명 에서 추출한 한글 명칭
도메인(domain):  소방시설/건축·건설/기계설비/정보통신/가스·위험물/전기/승강기/기타
서식종류(formKind): 신청서/신고서/확인서/보고서/점검표/허가증/…/기타

read-only: 파일 내용은 읽지 않음. 파일명만 사용.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── 도메인 시드 ──────────────────────────────────────────────────────────────
DOMAIN_RULES: list[tuple[str, re.Pattern]] = [
    ("소방시설",    re.compile(r"소방")),
    ("기계설비",    re.compile(r"기계설비|설비")),
    ("정보통신",    re.compile(r"정보통신|통신")),
    ("가스·위험물", re.compile(r"가스|액화석유|lpg|LPG|위험물")),
    ("전기",        re.compile(r"전기")),
    ("건축·건설",   re.compile(r"건축|건설|공사|현장|시공|준공|착공")),
    ("승강기",      re.compile(r"승강기|엘리베이터")),
    ("환경·폐기물", re.compile(r"환경|폐기물")),
]

# ── 서식종류 시드 (순서 중요: 더 구체적인 것 먼저) ───────────────────────────
KIND_RULES: list[tuple[str, re.Pattern]] = [
    ("확인증",   re.compile(r"확인증")),
    ("확인서",   re.compile(r"확인서")),
    ("신청서",   re.compile(r"신청서")),
    ("신고서",   re.compile(r"신고서")),
    ("보고서",   re.compile(r"보고서")),
    ("계획서",   re.compile(r"계획서")),
    ("점검표",   re.compile(r"점검표")),
    ("점검서",   re.compile(r"점검서")),
    ("통지서",   re.compile(r"통지서|통보서")),
    ("허가증",   re.compile(r"허가증")),
    ("등록증",   re.compile(r"등록증")),
    ("협의서",   re.compile(r"협의서")),
    ("명세서",   re.compile(r"명세서")),
    ("결과서",   re.compile(r"결과서")),
    ("검사표",   re.compile(r"검사표")),
    ("검사서",   re.compile(r"검사서")),
    ("지정서",   re.compile(r"지정서|지정증")),
    ("인증서",   re.compile(r"인증서")),
    ("증명서",   re.compile(r"증명서")),
    ("설계서",   re.compile(r"설계서")),
    ("준공서",   re.compile(r"준공서|준공계")),
    ("처리서",   re.compile(r"처리서|처리부")),
    ("조서",     re.compile(r"조서")),
    ("신청",     re.compile(r"신청$")),
    ("신고",     re.compile(r"신고$")),
    ("등록",     re.compile(r"등록$")),
    ("허가",     re.compile(r"허가$")),
    ("확인",     re.compile(r"확인$")),
]

# ── 별지 서식 번호 추출 ────────────────────────────────────────────────────────
_BYEOLJI_PAT = re.compile(
    r"\[별지[_\s]*제(\d+(?:호의\d+)?)[_\s]*호?서식\]",
    re.IGNORECASE,
)
# ── 서식명 추출 패턴 ──────────────────────────────────────────────────────────
# 패턴: [번호_][번호_][별지_제N호서식]_서식명__filled
# 또는: 서식명__filled
_FORM_NAME_PAT = re.compile(
    r"(?:\[[^\]]+\][_\s]*)+"  # [별지_제N호서식] 포함 bracket groups
    r"(.+?)(?:__filled)?$",
)
_FILLED_SUFFIX = re.compile(r"__filled$", re.IGNORECASE)
_LEADING_NUM   = re.compile(r"^[0-9a-f]{4,}[_\-]")  # hash prefix
_NUM_PREFIX    = re.compile(r"^\d{3,}_")              # 숫자 prefix


@dataclass
class FormTypeResult:
    maskedFileId: str
    originalStem: str          # stem (without .hwpx, without path)
    formName: str              # 추출된 서식명 (빈 문자열 가능)
    byeoljiNumber: str         # 제N호서식 번호 (없으면 "")
    domain: str                # 도메인
    formKind: str              # 서식종류
    confidence: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "maskedFileId":  self.maskedFileId,
            "originalStem":  self.originalStem,
            "formName":      self.formName,
            "byeoljiNumber": self.byeoljiNumber,
            "domain":        self.domain,
            "formKind":      self.formKind,
            "confidence":    round(self.confidence, 3),
            "evidence":      self.evidence,
        }


def _mask_stem(stem: str) -> str:
    return "file_" + hashlib.sha256(stem.encode("utf-8")).hexdigest()[:12]


def _extract_form_name(stem: str) -> tuple[str, str]:
    """(byeoljiNumber, formName) 추출."""
    s = stem

    # byeolji 번호 추출
    bm = _BYEOLJI_PAT.search(s)
    byeolji_num = bm.group(1) if bm else ""

    # __filled 제거
    s = _FILLED_SUFFIX.sub("", s)

    # bracket groups 제거
    if "[" in s:
        m = _FORM_NAME_PAT.search(s)
        if m:
            form_name = m.group(1).strip("_").strip()
        else:
            form_name = re.sub(r"\[[^\]]+\]", "", s).strip("_").strip()
    else:
        # bracket 없는 경우: leading hash/num 제거
        s2 = _LEADING_NUM.sub("", s)
        s2 = _NUM_PREFIX.sub("", s2)
        form_name = s2.strip()

    # 앞뒤 숫자/언더스코어 정리
    form_name = re.sub(r"^[_\s0-9]+|[_\s]+$", "", form_name)
    form_name = form_name.replace("_", " ").strip()

    return byeolji_num, form_name


def classify_form_type(path: Path, masked_id: str = "") -> FormTypeResult:
    """파일 경로(파일명)로부터 서식 유형을 분류."""
    stem = path.stem
    if not masked_id:
        masked_id = _mask_stem(stem)

    byeolji_num, form_name = _extract_form_name(stem)
    evidence: list[str] = []
    conf = 0.0

    if form_name:
        evidence.append(f"formName={form_name!r}")
        conf = 0.70

    if byeolji_num:
        evidence.append(f"byeolji={byeolji_num}")
        conf = min(conf + 0.15, 0.95)

    # 도메인 분류
    domain = "기타"
    search_text = form_name or stem
    for d, pat in DOMAIN_RULES:
        if pat.search(search_text):
            domain = d
            evidence.append(f"domain_keyword_match={d}")
            conf = min(conf + 0.05, 0.95)
            break

    # 서식종류 분류
    form_kind = "기타"
    for k, pat in KIND_RULES:
        if pat.search(search_text):
            form_kind = k
            evidence.append(f"kind_keyword_match={k}")
            conf = min(conf + 0.05, 0.95)
            break

    if domain == "기타" and form_kind == "기타":
        conf = max(conf, 0.30)

    return FormTypeResult(
        maskedFileId=masked_id,
        originalStem=stem,
        formName=form_name,
        byeoljiNumber=byeolji_num,
        domain=domain,
        formKind=form_kind,
        confidence=conf,
        evidence=evidence,
    )


def classify_batch(
    paths: list[Path],
    masked_ids: list[str] | None = None,
) -> list[FormTypeResult]:
    """배치 분류."""
    if masked_ids is None:
        masked_ids = [""] * len(paths)
    return [classify_form_type(p, mid) for p, mid in zip(paths, masked_ids)]


def build_summary(results: list[FormTypeResult]) -> dict[str, Any]:
    """분류 결과 요약 dict 생성."""
    from collections import Counter
    domain_counts: Counter = Counter()
    kind_counts:   Counter = Counter()
    byeolji_count = 0

    for r in results:
        domain_counts[r.domain] += 1
        kind_counts[r.formKind] += 1
        if r.byeoljiNumber:
            byeolji_count += 1

    return {
        "totalFiles":       len(results),
        "byeoljiFiles":     byeolji_count,
        "domainCounts":     dict(domain_counts.most_common()),
        "formKindCounts":   dict(kind_counts.most_common()),
        "unknownDomain":    domain_counts.get("기타", 0),
        "unknownKind":      kind_counts.get("기타", 0),
    }
