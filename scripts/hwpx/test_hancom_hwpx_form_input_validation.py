from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hancom_hwpx_form_input import choose_output_value_for_cell, validate_supplied_field


def test_validate_supplied_field_accepts_common_date_and_phone_formats() -> None:
    assert validate_supplied_field("착공일", "2026.05.01") == []
    assert validate_supplied_field("완공일", "2026년 05월 31일") == []
    assert validate_supplied_field("감리자 전화번호", "02-0000-0000") == []
    assert validate_supplied_field("시공사 전화번호", "01012345678") == []


def test_validate_supplied_field_warns_on_bad_business_formats() -> None:
    warnings = []
    warnings.extend(validate_supplied_field("착공일", "다음달"))
    warnings.extend(validate_supplied_field("감리자 전화번호", "전화 없음"))
    warnings.extend(validate_supplied_field("건축면적", "오천㎡"))
    warnings.extend(validate_supplied_field("접수번호", "1"))

    assert {item["type"] for item in warnings} == {
        "DATE_FORMAT_WARN",
        "PHONE_FORMAT_WARN",
        "NUMBER_FORMAT_WARN",
        "IDENTIFIER_TOO_SHORT_WARN",
    }


def test_choose_output_value_for_cell_compacts_safe_values_to_fit() -> None:
    narrow_cell = {"cell_width": 6000, "cell_margin": {"left": "100", "right": "100"}, "sublist": {"lineWrap": "BREAK"}}

    received = choose_output_value_for_cell("[입력필요: 접수일시]", "접수일시", "2026년 05월 11일 10:00", narrow_cell)
    identifier = choose_output_value_for_cell("제 [입력필요: 정보통신공사업 등록번호] 호", "정보통신공사업 등록번호", "정보통신-임시-0001", narrow_cell)
    item_name = choose_output_value_for_cell("[입력필요: 품명]", "품명", "UTP 케이블", narrow_cell)

    assert received["layout_compaction"]["status"] == "APPLIED"
    assert received["output_value"] == "05.11"
    assert identifier["output_value"] == "제 0001 호"
    assert item_name["output_value"] == "UTP케이블"
