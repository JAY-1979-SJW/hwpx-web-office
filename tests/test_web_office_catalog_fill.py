"""WEB-OFFICE-CATALOG-FILL-01 — editor_api_route.call_catalog_fill 배선 감리.

참조 서식(이미 채워진 hwpx)을 upload_document_parser + corpus 카탈로그로
매칭해 대상 서식 칸을 채우는 새 엔드포인트(/api/web-office/catalog-fill).
AI/OCR 미사용 — 규칙 기반 파서만 쓴다(§9 준수 확인).

실제 form_library 원본 3건(이미 검증됨, generate_wired_forms.py의 DOCS와
동일)으로 실행한다 — mock 없음. 2026-09-29 실측(scripts/ops/audit_web_office_
catalog_fill_sample.py)에서 3건 중 2건 카탈로그 매칭 성공(66.7%) 확인됨.
"""

from __future__ import annotations

from pathlib import Path

PR = Path(__file__).resolve().parents[1]

REAL_FORM = (
    "data/drafts/form_library/0393790f0e_16b6afa1e14849fc_02910_045_"
    "[별지_제22호의3서식]_공사_감리자_지정_신청서.hwpx"
)
UNMATCHED_FORM = (
    "data/drafts/form_library/022e3f35e6_6ff3fe63f13a8199_01076_035_"
    "[별지_제17호서식]_소방시설공사_완공검사신청서__A.hwpx"
)


def test_call_catalog_fill_matches_real_catalog_entry():
    from scripts.hwpx.web_office import editor_api_route as route

    result = route.call_catalog_fill(
        {"referencePath": REAL_FORM, "sourcePath": REAL_FORM},
        project_root=PR,
    )
    assert result["status"] == "SUCCESS"
    assert result["data"]["formName"] == "공사 감리자 지정 신청서"
    # 참조=대상이 같은 빈 템플릿이라 추출값이 없어 proposals는 비지만,
    # 카탈로그 자체는 매칭돼 missingCount > 0 로 나온다(2026-09-29 실측 확인).
    assert result["data"]["missingCount"] > 0
    assert result["data"]["proposals"] == []


def test_call_catalog_fill_reports_unmatched_catalog_honestly():
    """2026-09-29 실측: 이 파일은 classify_form_type 결과가 카탈로그의
    formName과 안 맞아 매칭 실패한다 — 조용히 빈 결과를 주지 않고
    CATALOG_NOT_MATCHED 로 명확히 실패 보고하는지 고정한다."""
    from scripts.hwpx.web_office import editor_api_route as route

    result = route.call_catalog_fill(
        {"referencePath": UNMATCHED_FORM, "sourcePath": UNMATCHED_FORM},
        project_root=PR,
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
