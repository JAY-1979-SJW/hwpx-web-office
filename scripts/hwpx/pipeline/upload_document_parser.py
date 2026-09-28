"""
HWPX-UPLOAD-PARSER-01

upload_document_parser.py — 업로드된 HWPX에서 필드 값을 추출.

전략:
  A. 수평 라벨-값 쌍: 같은 행에서 [라벨][값] 패턴
  B. 수직 헤더-데이터: 헤더 행 → 데이터 행 값
  C. 단락 텍스트: "라벨: 값" 패턴

출력: ExtractedField 목록 (fieldKey, value, confidence, sourceLabel, location)

read-only: 파일 쓰기 함수 미참조.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
NS_HS = "http://www.hancom.co.kr/hwpml/2011/section"

# PII 필터
_PII_RE = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")
# 값으로 보기 어려운 텍스트 패턴
_NOISE_RE = re.compile(r"^[\[\]○●□■※\s]+$|^\d{1,2}$|^[-─]+$")

# 값처럼 보이는 패턴 (confidence boost에 사용)
_DATE_RE = re.compile(r"\d{4}[-./년]\s*\d{1,2}[-./월]")
_COMPANY_RE = re.compile(r"\(주\)|주식회사|유한회사|합자|합명|협동조합|조합|공사$|공단$")
_ADDR_RE = re.compile(r"[가-힣]+시|[가-힣]+구|[가-힣]+동|[가-힣]+로|[가-힣]+길")
_AMOUNT_RE = re.compile(r"\d[\d,]+원|\d+\s*[mMkKgG]")
# 값으로 분류되면 안 되는 라벨 말미 패턴
_LABEL_TAIL = re.compile(
    r"[명번호일자기간량자처]$|서류$|사항$|내용$|종류$|여부$|방법$|등급$|등록$|신청$|신고$|분야$|현황$|조건$"
)
# 단락 텍스트에서 라벨:값 추출
_PARA_KV_RE = re.compile(r"(.{2,15})[:\s：]\s*(.{2,50})")


@dataclass
class ExtractedField:
    fieldKey: str  # semanticField
    value: str  # 추출된 값
    confidence: float
    sourceLabel: str  # 인접 라벨 텍스트
    location: str  # sec{i}_tbl{j}_row{k}_col{l}
    extractMethod: str  # horizontal / vertical / paragraph

    def to_dict(self) -> dict[str, Any]:
        return {
            "fieldKey": self.fieldKey,
            "value": self.value,
            "confidence": round(self.confidence, 3),
            "sourceLabel": self.sourceLabel,
            "location": self.location,
            "extractMethod": self.extractMethod,
        }


@dataclass
class ParseResult:
    maskedStem: str
    formName: str
    domain: str
    formKind: str
    extractedFields: list[ExtractedField] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "maskedStem": self.maskedStem,
            "formName": self.formName,
            "domain": self.domain,
            "formKind": self.formKind,
            "fieldCount": len(self.extractedFields),
            "extractedFields": [f.to_dict() for f in self.extractedFields],
            "warnings": self.warnings,
        }


# ── XML 헬퍼 ─────────────────────────────────────────────────────────────────


def _cell_text(cell: ET.Element) -> str:
    parts = []
    for t in cell.iter(f"{{{NS_HP}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts).strip()


def _para_text(para: ET.Element) -> str:
    parts = []
    for t in para.iter(f"{{{NS_HP}}}t"):
        if t.text:
            parts.append(t.text)
    return "".join(parts).strip()


def _is_noise(text: str) -> bool:
    return not text or _NOISE_RE.match(text) is not None or _PII_RE.search(text) is not None


def _value_score(text: str) -> float:
    """텍스트가 '값'처럼 보이는 정도 (0~1). 높을수록 값일 가능성 높음."""
    if not text or len(text) < 2:
        return 0.0
    score = 0.3
    if _DATE_RE.search(text):
        score += 0.4
    if _COMPANY_RE.search(text):
        score += 0.4
    if _ADDR_RE.search(text):
        score += 0.3
    if _AMOUNT_RE.search(text):
        score += 0.4
    if _LABEL_TAIL.search(text):
        score -= 0.4  # 라벨 말미 패턴 있으면 감점
    return max(0.0, min(1.0, score))


# ── 테이블 파싱 ───────────────────────────────────────────────────────────────


def _scan_forward_for_value(
    row: list[str], ci: int, clf, classify_fn, label_classes: set
) -> tuple[str, float] | None:
    """`ci` 다음 몇 칸 안에서 라벨이 아닌 값 셀을 찾아 (value, confidence) 를 반환한다."""
    from hwpx.recognition_corpus.label_taxonomy import CLS_HIGH

    for vi in range(ci + 1, min(ci + 5, len(row))):
        val = row[vi]
        if not _is_noise(val):
            val_clf = classify_fn(val)
            # 값 셀이 어떤 종류의 라벨이라도 값으로 쓰지 않음
            if val_clf.classification in label_classes:
                break
            # 라벨 말미 패턴이 있는 텍스트는 값이 아님
            if _LABEL_TAIL.search(val):
                break
            vs = _value_score(val)
            if vs < 0.3:
                break  # 값처럼 보이지 않으면 추출 안 함
            conf = (0.80 if clf.classification == CLS_HIGH else 0.65) * max(0.7, vs + 0.5)
            return val, conf
    return None


def _parse_table_horizontal(
    rows_data: list[list[str]],
    sec_idx: int,
    tbl_idx: int,
    classify_fn,
    label_classes: set,
) -> list[ExtractedField]:
    """Pattern A: 수평 라벨-값 쌍."""
    from hwpx.recognition_corpus.label_taxonomy import CLS_HIGH, CLS_MEDIUM

    results: list[ExtractedField] = []
    for ri, row in enumerate(rows_data):
        for ci, cell_txt in enumerate(row):
            if _is_noise(cell_txt):
                continue
            clf = classify_fn(cell_txt)
            if not (clf.semanticField and clf.classification in (CLS_HIGH, CLS_MEDIUM)):
                continue
            found = _scan_forward_for_value(row, ci, clf, classify_fn, label_classes)
            if found is None:
                continue
            val, conf = found
            results.append(
                ExtractedField(
                    fieldKey=clf.semanticField,
                    value=val,
                    confidence=conf,
                    sourceLabel=cell_txt,
                    location=f"sec{sec_idx}_tbl{tbl_idx}_row{ri}_col{ci}",
                    extractMethod="horizontal",
                )
            )
    return results


def _classify_header_row(header_row: list[str], classify_fn) -> list[tuple[str, object] | None]:
    from hwpx.recognition_corpus.label_taxonomy import CLS_HIGH, CLS_MEDIUM

    header_clf: list[tuple[str, object] | None] = []
    for txt in header_row:
        if _is_noise(txt):
            header_clf.append(None)
            continue
        c = classify_fn(txt)
        if c.semanticField and c.classification in (CLS_HIGH, CLS_MEDIUM):
            header_clf.append((txt, c))
        else:
            header_clf.append(None)
    return header_clf


def _extract_from_data_row(
    header_clf: list[tuple[str, object] | None],
    data_row: list[str],
    ri: int,
    loc_prefix: str,
    classify_fn,
    label_classes: set,
) -> list[ExtractedField]:
    from hwpx.recognition_corpus.label_taxonomy import CLS_HIGH

    row_results: list[ExtractedField] = []
    for ci, hclf in enumerate(header_clf):
        if hclf is None or ci >= len(data_row):
            continue
        lbl_txt, lbl_clf = hclf
        val = data_row[ci]
        if _is_noise(val):
            continue
        val_clf = classify_fn(val)
        if val_clf.classification in label_classes:
            continue
        conf = 0.70 if lbl_clf.classification == CLS_HIGH else 0.55
        row_results.append(
            ExtractedField(
                fieldKey=lbl_clf.semanticField,
                value=val,
                confidence=conf,
                sourceLabel=lbl_txt,
                location=f"{loc_prefix}_row{ri}_col{ci}",
                extractMethod="vertical",
            )
        )
    return row_results


def _parse_table_vertical(
    rows_data: list[list[str]],
    sec_idx: int,
    tbl_idx: int,
    classify_fn,
    label_classes: set,
) -> list[ExtractedField]:
    """Pattern B: 수직 헤더→데이터 (헤더 행의 각 열 라벨 → 아래 행 같은 열 값)."""
    loc_prefix = f"sec{sec_idx}_tbl{tbl_idx}"
    results: list[ExtractedField] = []
    for ri in range(len(rows_data) - 1):
        header_row = rows_data[ri]
        data_row = rows_data[ri + 1]
        header_clf = _classify_header_row(header_row, classify_fn)

        known_headers = sum(1 for x in header_clf if x is not None)
        if known_headers == 0:
            continue
        if known_headers < len([t for t in header_row if not _is_noise(t)]) * 0.4:
            continue  # 헤더 행 인식률 부족

        results.extend(
            _extract_from_data_row(header_clf, data_row, ri, loc_prefix, classify_fn, label_classes)
        )
    return results


def _parse_table(
    tbl: ET.Element,
    sec_idx: int,
    tbl_idx: int,
    classify_fn,
) -> list[ExtractedField]:
    from hwpx.recognition_corpus.label_taxonomy import (
        CLS_BACK,
        CLS_DECO,
        CLS_HIGH,
        CLS_MEDIUM,
        CLS_META,
        CLS_SCHED,
    )

    rows_data: list[list[str]] = []
    for row in tbl.findall(f"{{{NS_HP}}}tr"):
        cells_text = [_cell_text(c) for c in row.findall(f"{{{NS_HP}}}tc")]
        rows_data.append(cells_text)

    label_classes = {CLS_HIGH, CLS_MEDIUM, CLS_META, CLS_DECO, CLS_BACK, CLS_SCHED}

    results = _parse_table_horizontal(rows_data, sec_idx, tbl_idx, classify_fn, label_classes)
    results += _parse_table_vertical(rows_data, sec_idx, tbl_idx, classify_fn, label_classes)
    return results


# ── 단락 파싱 ─────────────────────────────────────────────────────────────────


def _parse_paragraphs(
    sec: ET.Element,
    sec_idx: int,
    classify_fn,
) -> list[ExtractedField]:
    from hwpx.recognition_corpus.label_taxonomy import CLS_HIGH, CLS_MEDIUM

    results = []
    for pi, para in enumerate(sec.findall(f".//{{{NS_HP}}}p")):
        txt = _para_text(para)
        if not txt or len(txt) < 5 or len(txt) > 200:
            continue
        m = _PARA_KV_RE.search(txt)
        if not m:
            continue
        lbl_raw, val_raw = m.group(1).strip(), m.group(2).strip()
        if _is_noise(val_raw):
            continue
        clf = classify_fn(lbl_raw)
        if clf.semanticField and clf.classification in (CLS_HIGH, CLS_MEDIUM):
            results.append(
                ExtractedField(
                    fieldKey=clf.semanticField,
                    value=val_raw[:100],
                    confidence=0.55,
                    sourceLabel=lbl_raw,
                    location=f"sec{sec_idx}_para{pi}",
                    extractMethod="paragraph",
                )
            )
    return results


# ── 중복 제거: 같은 fieldKey + value 조합 중 confidence 최고 하나만 ─────────────

MIN_CONFIDENCE = 0.60


def _deduplicate(fields: list[ExtractedField]) -> list[ExtractedField]:
    # 최소 신뢰도 필터
    fields = [f for f in fields if f.confidence >= MIN_CONFIDENCE]
    seen: dict[tuple, ExtractedField] = {}
    for f in fields:
        key = (f.fieldKey, f.value)
        if key not in seen or f.confidence > seen[key].confidence:
            seen[key] = f
    return sorted(seen.values(), key=lambda f: -f.confidence)


# ── 메인 파서 ─────────────────────────────────────────────────────────────────


def parse_hwpx(path: Path) -> ParseResult:
    """
    HWPX 파일에서 입력 필드 값을 추출.

    Args:
        path: HWPX 파일 경로
    Returns:
        ParseResult
    """
    import hashlib

    from hwpx.recognition_corpus.form_type_classifier import classify_form_type
    from hwpx.recognition_corpus.label_taxonomy import classify_label

    masked_stem = "file_" + hashlib.sha256(path.stem.encode("utf-8")).hexdigest()[:12]
    ft = classify_form_type(path)

    result = ParseResult(
        maskedStem=masked_stem,
        formName=ft.formName,
        domain=ft.domain,
        formKind=ft.formKind,
    )

    if not path.exists():
        result.warnings.append("file_not_found")
        return result

    try:
        with zipfile.ZipFile(path, "r") as z:
            section_names = sorted(
                n for n in z.namelist() if re.match(r"Contents/section\d+\.xml", n, re.IGNORECASE)
            )
            all_fields: list[ExtractedField] = []

            for sec_idx, sec_name in enumerate(section_names):
                try:
                    xml_bytes = z.read(sec_name)
                    root = ET.fromstring(xml_bytes.decode("utf-8"))
                except Exception as e:  # ruff: ignore[blind-except]
                    result.warnings.append(f"parse_error_{sec_name}: {e}")
                    continue

                # 단락 파싱
                all_fields.extend(_parse_paragraphs(root, sec_idx, classify_label))

                # 테이블 파싱
                for tbl_idx, tbl in enumerate(root.findall(f".//{{{NS_HP}}}tbl")):
                    all_fields.extend(_parse_table(tbl, sec_idx, tbl_idx, classify_label))

    except zipfile.BadZipFile:
        result.warnings.append("bad_zip")
        return result
    except Exception as e:  # ruff: ignore[blind-except]
        result.warnings.append(f"unexpected_error: {e}")
        return result

    result.extractedFields = _deduplicate(all_fields)
    return result


def parse_batch(paths: list[Path]) -> list[ParseResult]:
    return [parse_hwpx(p) for p in paths]
