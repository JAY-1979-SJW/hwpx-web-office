"""WEB-OFFICE-CATALOG-FILL-01 — editor_api_route.call_catalog_fill 배선 감리.

참조 서식(이미 채워진 hwpx)을 upload_document_parser + corpus 카탈로그로
매칭해 대상 서식 칸을 채우는 새 엔드포인트(/api/web-office/catalog-fill).
AI/OCR 미사용 — 규칙 기반 파서만 쓴다(§9 준수 확인).

깨끗한 CI 에서도 돌도록 합성 입력만 쓴다: tests/fixtures 의 합성 hwpx 를 서식 파일명으로
복사하고(분류기는 파일명 stem 만 본다), 카탈로그는 임시 jsonl 1항목으로 대체한다.
실제 서식·실제 카탈로그 기준 검증은 수동 점검(별도,
scripts/ops/audit_web_office_catalog_fill_sample.py)으로 한다.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[1]

SYNTHETIC_HWPX = PR / "tests" / "fixtures" / "hwpx" / "corpus" / "fx_synthetic_metadata_form.hwpx"
MATCHED_NAME = "[별지_제22호의3서식]_공사_감리자_지정_신청서.hwpx"
UNMATCHED_NAME = "[별지_제17호서식]_소방시설공사_완공검사신청서__A.hwpx"
MATCHED_FORM_NAME = "공사 감리자 지정 신청서"


def _use_synthetic_catalog(monkeypatch, tmp_path: Path) -> None:
    """load_catalog_entry 의 기본 카탈로그 경로를 합성 jsonl(1항목)로 바꾼다."""
    catalog = tmp_path / "catalog.jsonl"
    entry = {
        "formId": "form_synthetic",
        "formName": MATCHED_FORM_NAME,
        "fields": [
            {
                "primaryLabel": "합성필드가",
                "labels": ["합성필드가"],
                "semanticField": "",
                "autoFillable": False,
                "inputCellTypes": ["header_column"],
                "required": True,
                "fileOccurrenceCount": 1,
                "totalOccurrenceCount": 1,
                "sourceEvidenceHint": "",
            }
        ],
    }
    catalog.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")

    scripts_dir = str(PR / "scripts")
    if scripts_dir not in sys.path:
        monkeypatch.syspath_prepend(scripts_dir)
    from hwpx.recognition_corpus import form_field_catalog as ffc

    original = ffc.load_catalog_entry
    monkeypatch.setattr(
        ffc, "load_catalog_entry", lambda form_name: original(form_name, catalog_jsonl=catalog)
    )


def _copy_form(tmp_path: Path, name: str) -> str:
    dest = tmp_path / name
    shutil.copyfile(SYNTHETIC_HWPX, dest)
    return dest.name


def test_call_catalog_fill_matches_catalog_entry(monkeypatch, tmp_path):
    from scripts.hwpx.web_office import editor_api_route as route

    _use_synthetic_catalog(monkeypatch, tmp_path)
    form = _copy_form(tmp_path, MATCHED_NAME)
    result = route.call_catalog_fill(
        {"referencePath": form, "sourcePath": form}, project_root=tmp_path
    )
    assert result["status"] == "SUCCESS"
    assert result["data"]["formName"] == MATCHED_FORM_NAME
    # 카탈로그 필드(합성필드가)는 합성 hwpx 에 값이 없어 제안은 비고 missingCount > 0.
    assert result["data"]["missingCount"] > 0
    assert result["data"]["proposals"] == []


def test_call_catalog_fill_reports_unmatched_catalog_honestly(monkeypatch, tmp_path):
    """카탈로그에 없는 formName 이면 조용히 빈 결과를 주지 않고
    CATALOG_NOT_MATCHED 로 명확히 실패 보고하는지 고정한다."""
    from scripts.hwpx.web_office import editor_api_route as route

    _use_synthetic_catalog(monkeypatch, tmp_path)
    form = _copy_form(tmp_path, UNMATCHED_NAME)
    result = route.call_catalog_fill(
        {"referencePath": form, "sourcePath": form}, project_root=tmp_path
    )
    assert result["status"] == "FAILED"
    assert result["errors"][0]["code"] == "CATALOG_NOT_MATCHED"


def test_call_catalog_fill_missing_paths_rejected():
    from scripts.hwpx.web_office import editor_api_route as route

    result = route.call_catalog_fill({"referencePath": "", "sourcePath": ""})
    assert result["status"] == "FAILED"
    assert result["errors"][0]["code"] == "PATH_MISSING"


def test_call_catalog_fill_missing_file_rejected():
    from scripts.hwpx.web_office import editor_api_route as route

    result = route.call_catalog_fill(
        {"referencePath": "no/such/file.hwpx", "sourcePath": "also/missing.hwpx"},
        project_root=PR,
    )
    assert result["status"] == "FAILED"
    assert result["errors"][0]["code"] == "FILE_NOT_FOUND"


def test_call_catalog_fill_no_ai_or_ocr_import():
    """§9 준수 — 이 함수가 있는 모듈 소스에 AI/OCR 호출 흔적이 catalog_fill
    함수 범위 안에는 없어야 한다(파일 전체가 아니라 함수 소스만 검사)."""
    import inspect

    from scripts.hwpx.web_office import editor_api_route as route

    src = inspect.getsource(route.call_catalog_fill).lower()
    for bad in ("claude", "openai", "api.anthropic", "tesseract"):
        assert bad not in src, f"AI/OCR 흔적: {bad}"
