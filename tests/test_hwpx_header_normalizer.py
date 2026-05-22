"""Tests for hwpx_corpus_profiler header normalizer and field guesser improvements."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "local"))

from hwpx_corpus_profiler import normalize_header, guess_field


# ── normalize_header ──────────────────────────────────────────────────────────

def test_korean_inter_char_spaces_removed():
    assert normalize_header("공 사 명") == "공사명"
    assert normalize_header("접 수 번 호") == "접수번호"
    assert normalize_header("비 고") == "비고"
    assert normalize_header("호 칭 지 름") == "호칭지름"
    assert normalize_header("시 작 일") == "시작일"
    assert normalize_header("종 료 일") == "종료일"
    assert normalize_header("가 스 명") == "가스명"
    assert normalize_header("작 업 명") == "작업명"
    assert normalize_header("번 호") == "번호"


def test_mixed_korean_english_spaces_preserved():
    """숫자/영문이 섞인 헤더는 공백을 과도하게 제거하지 않는다."""
    assert normalize_header("No. 1") == "No. 1"
    assert normalize_header("DN 100") == "DN 100"


def test_nfkc_normalization():
    result = normalize_header("１２３")  # fullwidth 123
    assert result == "123"


def test_empty_and_whitespace():
    assert normalize_header("") == ""
    assert normalize_header("   ") == ""
    assert normalize_header("\n\t ") == ""


def test_leading_trailing_whitespace_stripped():
    assert normalize_header("  비고  ") == "비고"


def test_multi_space_collapsed():
    assert normalize_header("시작  일") == "시작일"  # 한글 사이이므로 제거됨


def test_newline_in_header():
    assert normalize_header("공사\n명") == "공사명"


# ── guess_field ───────────────────────────────────────────────────────────────

def test_guess_projectName():
    field, conf = guess_field("공사명")
    assert field == "projectName"
    assert conf >= 0.9


def test_guess_receiptNumber():
    field, conf = guess_field("접수번호")
    assert field == "receiptNumber"
    assert conf >= 0.9


def test_guess_remarks():
    field, conf = guess_field("비고")
    assert field == "remarks"
    assert conf >= 0.9


def test_guess_nominalDiameter():
    field, conf = guess_field("호칭지름")
    assert field == "nominalDiameter"
    assert conf >= 0.9


def test_guess_gasName():
    field, conf = guess_field("가스명")
    assert field == "gasName"
    assert conf >= 0.9


def test_guess_pressure():
    field, conf = guess_field("압력")
    assert field == "pressure"
    assert conf >= 0.9


def test_guess_material():
    field, conf = guess_field("재질")
    assert field == "material"
    assert conf >= 0.9


def test_guess_length():
    field, conf = guess_field("연장")
    assert field == "length"
    assert conf >= 0.9


def test_guess_number():
    field, conf = guess_field("번호")
    assert field == "number"
    assert conf >= 0.9


def test_guess_startDate():
    field, conf = guess_field("시작일")
    assert field == "startDate"
    assert conf >= 0.9


def test_guess_endDate():
    field, conf = guess_field("종료일")
    assert field == "endDate"
    assert conf >= 0.9


def test_guess_unknown_preserved():
    field, conf = guess_field("xyz_unknown_field")
    assert field == "unknown"
    assert conf == 0.0


# ── round-trip: spaced Korean → normalized → guessed ─────────────────────────

def test_roundtrip_spaced_korean_to_field():
    cases = [
        ("공 사 명",   "projectName"),
        ("접 수 번 호", "receiptNumber"),
        ("비 고",      "remarks"),
        ("호 칭 지 름", "nominalDiameter"),
        ("가 스 명",   "gasName"),
        ("시 작 일",   "startDate"),
        ("종 료 일",   "endDate"),
    ]
    for raw, expected_field in cases:
        norm = normalize_header(raw)
        field, conf = guess_field(norm)
        assert field == expected_field, (
            f"raw={raw!r} norm={norm!r} got field={field!r}, expected={expected_field!r}"
        )
        assert conf >= 0.9, f"low confidence {conf} for {raw!r}"
