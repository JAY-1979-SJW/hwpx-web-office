"""
HWPX-RECOGNITION-CORPUS-RESULTS-ANALYSIS-01

이미 수집·조사된 corpus 산출물(jsonl)을 pandas 로 분석해 분포·품질 지표를
낸다. 새로 문서를 열거나 분류하지 않는다 — 순수 집계·분석 전용.

입력(둘 다 이미 존재, 2026-09-29 확인):
    data/reports/hwpx_form_type_classification/per_file_form_type.jsonl
        (form_type_classifier.py 산출물, 5,266건)
    data/reports/hwpx_survey_drafts/survey_input_cells_raw.jsonl
        (survey_headers_and_input_cells.py 산출물, 145,763건)

form_field_catalog.build_summary() 와는 목적이 다르다 — 그쪽은 AI 자동채움
파이프라인에 넣을 "서식별 필드 카탈로그"를 만들고, 이 모듈은 그 원본
데이터 자체의 분포·품질(신뢰도, unknown 비율 등)을 사람이 살펴보기 위한
탐색적 분석이다. 코드 중복 없음 — 서로 다른 산출물을 만든다.

read-only: 원본 hwpx·jsonl 을 수정하지 않는다. AI/OCR/writer 호출 없음.
집계 전용(value_counts/mean)이라 pandas 3.0 Copy-on-Write 영향 없음
(2026-09-29 공식 문서 확인 — 체인 할당·inplace 를 안 쓰면 문제 없음).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
FORM_TYPE_JSONL = ROOT / "data/reports/hwpx_form_type_classification/per_file_form_type.jsonl"
SURVEY_JSONL = ROOT / "data/reports/hwpx_survey_drafts/survey_input_cells_raw.jsonl"

TOP_N_LABELS = 30


def _load_jsonl(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    return pd.read_json(path, lines=True)


def analyze_form_types(df: pd.DataFrame) -> dict[str, Any]:
    """서식 분류(domain/formKind/confidence) 분포."""
    if df.empty:
        return {"totalFiles": 0}
    low_conf = df[df["confidence"] < 0.5]
    return {
        "totalFiles": len(df),
        "domainCounts": df["domain"].value_counts().to_dict(),
        "formKindCounts": df["formKind"].value_counts().to_dict(),
        "confidenceMean": round(float(df["confidence"].mean()), 3),
        "confidenceMin": round(float(df["confidence"].min()), 3),
        "lowConfidenceCount": len(low_conf),
        "lowConfidenceRatio": round(len(low_conf) / len(df), 3),
    }


def analyze_survey_cells(df: pd.DataFrame) -> dict[str, Any]:
    """입력칸 조사(inputCellType/tableLayout/guessedField) 분포·품질."""
    if df.empty:
        return {"totalCells": 0}
    unknown_layout = df[df["tableLayout"] == "unknown"]
    unknown_field = df[df["guessedField"] == "unknown"]
    top_labels = df["adjacentLabel"].value_counts().head(TOP_N_LABELS).to_dict()
    return {
        "totalCells": len(df),
        "inputCellTypeCounts": df["inputCellType"].value_counts().to_dict(),
        "tableLayoutCounts": df["tableLayout"].value_counts().to_dict(),
        "unknownLayoutRatio": round(len(unknown_layout) / len(df), 3),
        "unknownGuessedFieldRatio": round(len(unknown_field) / len(df), 3),
        "fieldConfidenceMean": round(float(df["fieldConfidence"].mean()), 3),
        "topAdjacentLabels": top_labels,
    }


def run_analysis(
    form_type_path: Path = FORM_TYPE_JSONL, survey_path: Path = SURVEY_JSONL
) -> dict[str, Any]:
    form_types = analyze_form_types(_load_jsonl(form_type_path))
    survey = analyze_survey_cells(_load_jsonl(survey_path))
    return {
        "schemaVersion": "hwpx_recognition_corpus_results_analysis_v1",
        "formTypeClassification": form_types,
        "surveyInputCells": survey,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="JSON 그대로 출력")
    args = ap.parse_args()

    result = run_analysis()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    ft = result["formTypeClassification"]
    sv = result["surveyInputCells"]
    print(f"=== 서식 분류 (파일 {ft.get('totalFiles', 0)}건) ===")
    print("도메인 분포:", ft.get("domainCounts"))
    print("서식종류 분포:", ft.get("formKindCounts"))
    print(
        f"신뢰도 평균 {ft.get('confidenceMean')}, "
        f"0.5 미만 {ft.get('lowConfidenceCount')}건"
        f"({ft.get('lowConfidenceRatio', 0) * 100:.1f}%)"
    )
    print()
    print(f"=== 입력칸 조사 (셀 {sv.get('totalCells', 0)}건) ===")
    print("입력칸 유형 분포:", sv.get("inputCellTypeCounts"))
    print("표 레이아웃 분포:", sv.get("tableLayoutCounts"))
    print(f"레이아웃 unknown 비율: {sv.get('unknownLayoutRatio', 0) * 100:.1f}%")
    print(f"필드 unknown 비율: {sv.get('unknownGuessedFieldRatio', 0) * 100:.1f}%")
    print(f"필드 신뢰도 평균: {sv.get('fieldConfidenceMean')}")
    print(f"빈도 상위 {TOP_N_LABELS}개 라벨:")
    for label, count in sv.get("topAdjacentLabels", {}).items():
        print(f"  {label}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
