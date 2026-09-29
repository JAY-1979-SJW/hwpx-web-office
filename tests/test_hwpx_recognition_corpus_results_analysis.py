"""HWPX-RECOGNITION-CORPUS-RESULTS-ANALYSIS-01 감리.

analyze_corpus_results.py 가 합성 데이터로 정확한 분포·비율을 내는지
고정한다. 실제 15만 행 jsonl 은 read하지 않는다(속도·재현성).
"""

from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("pandas")

from scripts.hwpx.recognition_corpus.analyze_corpus_results import (
    analyze_form_types,
    analyze_survey_cells,
    run_analysis,
)


def test_analyze_form_types_empty():
    assert analyze_form_types(pd.DataFrame()) == {"totalFiles": 0}


def test_analyze_form_types_distribution_and_confidence():
    df = pd.DataFrame([
        {"domain": "소방시설", "formKind": "신청서", "confidence": 0.9},
        {"domain": "소방시설", "formKind": "신고서", "confidence": 0.3},
        {"domain": "건축·건설", "formKind": "신청서", "confidence": 0.8},
    ])
    result = analyze_form_types(df)
    assert result["totalFiles"] == 3
    assert result["domainCounts"]["소방시설"] == 2
    assert result["domainCounts"]["건축·건설"] == 1
    assert result["formKindCounts"]["신청서"] == 2
    assert result["lowConfidenceCount"] == 1  # 0.3 < 0.5
    assert result["lowConfidenceRatio"] == round(1 / 3, 3)


def test_analyze_survey_cells_empty():
    assert analyze_survey_cells(pd.DataFrame()) == {"totalCells": 0}


def test_analyze_survey_cells_unknown_ratios_and_top_labels():
    df = pd.DataFrame([
        {
            "inputCellType": "form_field",
            "tableLayout": "unknown",
            "guessedField": "unknown",
            "fieldConfidence": 0.0,
            "adjacentLabel": "성명",
        },
        {
            "inputCellType": "form_field",
            "tableLayout": "form_table",
            "guessedField": "name",
            "fieldConfidence": 0.9,
            "adjacentLabel": "성명",
        },
        {
            "inputCellType": "header_column",
            "tableLayout": "unknown",
            "guessedField": "unknown",
            "fieldConfidence": 0.0,
            "adjacentLabel": "주소",
        },
    ])
    result = analyze_survey_cells(df)
    assert result["totalCells"] == 3
    assert result["inputCellTypeCounts"]["form_field"] == 2
    assert result["tableLayoutCounts"]["unknown"] == 2
    assert result["unknownLayoutRatio"] == round(2 / 3, 3)
    assert result["unknownGuessedFieldRatio"] == round(2 / 3, 3)
    assert result["topAdjacentLabels"]["성명"] == 2
    assert result["topAdjacentLabels"]["주소"] == 1


def test_run_analysis_handles_missing_files(tmp_path):
    """실제 corpus jsonl 경로가 없어도(신규 환경) 죽지 않고 0건으로 보고한다."""
    result = run_analysis(
        form_type_path=tmp_path / "no_such_file.jsonl",
        survey_path=tmp_path / "also_missing.jsonl",
    )
    assert result["formTypeClassification"] == {"totalFiles": 0}
    assert result["surveyInputCells"] == {"totalCells": 0}


def test_run_analysis_against_real_corpus_files_if_present():
    """실제 corpus 파일이 있으면(이 저장소엔 있음) 실측치를 낸다 —
    2026-09-29 확인: unknown 비율이 높게 나오는데, 이는 조사 시점이
    layout_classifier.py 실제 연결(2026-09-29 같은 세션 앞부분) 이전이라
    그렇다 — 이 테스트의 목적이 아니므로 숫자 자체는 단언하지 않는다."""
    result = run_analysis()
    ft = result["formTypeClassification"]
    sv = result["surveyInputCells"]
    if ft.get("totalFiles", 0) == 0:
        pytest.skip("corpus jsonl 없음(이 환경엔 수집 데이터 미배치)")
    assert ft["totalFiles"] > 0
    assert 0.0 <= ft["confidenceMean"] <= 1.0
    assert sv["totalCells"] > 0
    assert 0.0 <= sv["unknownLayoutRatio"] <= 1.0
