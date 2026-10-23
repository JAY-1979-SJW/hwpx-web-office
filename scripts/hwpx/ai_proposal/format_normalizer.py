"""Format normalizer — 거부 대신 자동 보정.

AI/사용자가 보낸 값이 semanticType과 형식이 안 맞으면:
- 가능한 경우: 자동 보정 시도 (예: "120억" → "12,000,000,000")
- 보정 실패: WARN으로 통과 (사람 보완 대기)
- 절대 AUTO_REJECT 하지 않음

CLAUDE.md §6 격리 유지 — evidence_ingestion 의존 없이 자체 규칙.
"""
from __future__ import annotations

import re


def normalize_value(*, semantic_type: str | None,
                          raw_value: str | None) -> dict:
    """semantic 별 정규화 시도.

    Returns:
      {
        normalizedValue: str | None,  # 보정 성공 시 표준 형식
        wasNormalized: bool,          # 보정 발생 여부
        normalizationRule: str | None,
        formatStatus: "OK" | "NORMALIZED" | "NEEDS_HUMAN",
        formatNote: str | None,
      }
    """
    if raw_value is None or not isinstance(raw_value, str):
        return _ok(None, status="NEEDS_HUMAN",
                      note="value is missing or non-string")
    v = raw_value.strip()
    if not v:
        return _ok(None, status="NEEDS_HUMAN", note="empty value")

    st = (semantic_type or "").upper()
    if st in ("CONTRACT_AMOUNT", "QUANTITY"):
        return _normalize_amount(v)
    if st in ("START_DATE", "END_DATE"):
        return _normalize_date(v)
    if st == "BUSINESS_REGISTRATION_NUMBER":
        return _normalize_bizno(v)
    if st == "PHONE":
        return _normalize_phone(v)
    if st in ("PROJECT_NAME", "COMPANY_NAME",
                  "REPRESENTATIVE_NAME", "SITE_MANAGER_NAME",
                  "ADDRESS", "FREE_TEXT", "MATERIAL_NAME",
                  "INSPECTION_ITEM", "ATTACHMENT_DOCUMENT"):
        return _normalize_freeform_text(v)
    if st in ("CHECKBOX", "YES_NO"):
        return _normalize_yes_no(v)
    # UNKNOWN / 기타 — pass-through
    return _ok(v, status="OK")


# ── per-semantic normalizers ────────────────────────────────────────────

_AMOUNT_UNIT_MAP = {
    "억": 100_000_000,
    "천만": 10_000_000,
    "백만": 1_000_000,
    "만": 10_000,
}


def _normalize_amount(v: str) -> dict:
    """금액 정규화. '120억', '1.2억', '1,200,000,000원', '120000000' 등 처리."""
    s = v.replace(" ", "").replace(",", "").replace("원", "")
    # 단위 처리
    for unit, mult in _AMOUNT_UNIT_MAP.items():
        if s.endswith(unit):
            head = s[: -len(unit)]
            try:
                num = float(head)
                amt = int(num * mult)
                return _ok(f"{amt:,}", status="NORMALIZED",
                              rule=f"unit:{unit}")
            except ValueError:
                pass
    # 순수 숫자
    digits = re.sub(r"[^\d]", "", s)
    if digits and digits == s.lstrip("0") or digits == s:
        try:
            amt = int(digits)
            if amt > 0:
                return _ok(f"{amt:,}",
                              status="NORMALIZED" if "," not in v else "OK",
                              rule="numeric")
        except ValueError:
            pass
    if digits:
        try:
            amt = int(digits)
            return _ok(f"{amt:,}", status="NORMALIZED",
                          rule="strip_non_digit")
        except ValueError:
            pass
    return _ok(v, status="NEEDS_HUMAN",
                  note="amount format unrecognized")


_DATE_PATTERNS: tuple[tuple[re.Pattern, str], ...] = (
    (re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"), "{0}-{1:02d}-{2:02d}"),
    (re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$"), "{0}-{1:02d}-{2:02d}"),
    (re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"), "{0}-{1:02d}-{2:02d}"),
    (re.compile(r"^(\d{4})(\d{2})(\d{2})$"), "{0}-{1}-{2}"),
    (re.compile(r"^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일?$"),
        "{0}-{1:02d}-{2:02d}"),
)


def _normalize_date(v: str) -> dict:
    s = v.strip()
    for pat, fmt in _DATE_PATTERNS:
        m = pat.match(s)
        if m:
            try:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 1 <= mo <= 12 and 1 <= d <= 31:
                    norm = fmt.format(y, mo, d) if "{1:02d}" in fmt else fmt.format(y, m.group(2), m.group(3))
                    # safety: 표준화된 string으로
                    return _ok(f"{y:04d}-{mo:02d}-{d:02d}",
                                  status="OK" if v == f"{y:04d}-{mo:02d}-{d:02d}" else "NORMALIZED",
                                  rule=pat.pattern)
            except ValueError:
                pass
    return _ok(v, status="NEEDS_HUMAN", note="date format unrecognized")


_BIZNO_DIGITS_RE = re.compile(r"\d")


def _normalize_bizno(v: str) -> dict:
    digits = "".join(_BIZNO_DIGITS_RE.findall(v))
    if len(digits) == 10:
        norm = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        return _ok(norm,
                      status="OK" if v == norm else "NORMALIZED",
                      rule="bizno_digits10")
    return _ok(v, status="NEEDS_HUMAN",
                  note=f"biz reg number must be 10 digits (got {len(digits)})")


def _normalize_phone(v: str) -> dict:
    digits = "".join(_BIZNO_DIGITS_RE.findall(v))
    if len(digits) == 11 and digits.startswith("01"):
        norm = f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        return _ok(norm,
                      status="OK" if v == norm else "NORMALIZED",
                      rule="phone_mobile_11")
    if len(digits) == 10 and digits.startswith("02"):
        norm = f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
        return _ok(norm,
                      status="OK" if v == norm else "NORMALIZED",
                      rule="phone_seoul_10")
    if len(digits) >= 9:
        # 기타 지역번호 추정
        return _ok(v, status="NEEDS_HUMAN",
                      note=f"phone format ambiguous ({len(digits)} digits)")
    return _ok(v, status="NEEDS_HUMAN", note="phone digits insufficient")


def _normalize_freeform_text(v: str) -> dict:
    """텍스트 — 앞뒤 공백 제거, 중복 공백 1개로."""
    norm = re.sub(r"\s+", " ", v).strip()
    if norm == v:
        return _ok(v, status="OK")
    return _ok(norm, status="NORMALIZED", rule="trim_collapse_spaces")


def _normalize_yes_no(v: str) -> dict:
    s = v.strip().lower()
    if s in ("yes", "y", "예", "o", "v", "✓", "1", "true", "있음"):
        return _ok("Y", status="NORMALIZED" if v != "Y" else "OK",
                      rule="yes_alias")
    if s in ("no", "n", "아니오", "아니요", "x", "0", "false", "없음"):
        return _ok("N", status="NORMALIZED" if v != "N" else "OK",
                      rule="no_alias")
    return _ok(v, status="NEEDS_HUMAN", note="yes/no token unrecognized")


# ── helper ────────────────────────────────────────────────────────────

def _ok(value: str | None, *, status: str,
            rule: str | None = None, note: str | None = None) -> dict:
    return {
        "normalizedValue": value,
        "wasNormalized": status == "NORMALIZED",
        "normalizationRule": rule,
        "formatStatus": status,
        "formatNote": note,
    }


# ── batch helper ──────────────────────────────────────────────────────

def normalize_batch(items: list[dict]) -> dict:
    """items: [{semanticType, value}, ...] → normalize 결과 + 통계."""
    results: list[dict] = []
    counts = {"OK": 0, "NORMALIZED": 0, "NEEDS_HUMAN": 0}
    for it in items or []:
        r = normalize_value(
            semantic_type=it.get("semanticType"),
            raw_value=it.get("value"))
        counts[r["formatStatus"]] = counts.get(r["formatStatus"], 0) + 1
        results.append({**it, "normalization": r})
    return {"results": results, "counts": counts}
