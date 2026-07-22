"""HWPX-FORM-TEMPLATE-STORE-01 감리검사.

셋팅→저장→로드→자동입력 전 흐름 + 안전 3종을 검증한다.
외부 의존 없음 — temp 디렉터리로 격리 실행.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "pipeline"))

import form_template_store as store  # noqa: E402

FIXED_NOW = datetime(2026, 7, 22, tzinfo=timezone.utc)


# ── 가짜 인식 결과 (form_recognizer 출력 형태 모사) ──────────────────

@dataclass
class FakeSlot:
    tableId: str
    fieldGuess: str
    labelText: str
    row: int
    col: int
    visualRow: int = 0
    visualCol: int = 0
    rowSpan: int = 1
    colSpan: int = 1


@dataclass
class FakeRecognition:
    formType: str = "application_form"
    tableRoles: dict = field(default_factory=dict)
    enhancedSlots: list = field(default_factory=list)
    unsafeTableIds: list = field(default_factory=list)


def _sample_recognition() -> FakeRecognition:
    return FakeRecognition(
        formType="application_form",
        tableRoles={"t1": "basic_info", "t2": "approval_stamp"},
        enhancedSlots=[
            FakeSlot("t1", "projectName", "공사명", row=0, col=1),
            FakeSlot("t1", "contractorName", "시공사", row=1, col=1),
            FakeSlot("t1", "reportDate", "작성일", row=2, col=1),
            # 직인표(t2)에도 슬롯이 있지만 unsafe로 제외되어야 함
            FakeSlot("t2", "inspector", "직인", row=0, col=0),
        ],
        unsafeTableIds=["t2"],
    )


def test_setup_excludes_unsafe_tables(tmp_dir: Path) -> None:
    """셋팅 — 직인표(t2) 슬롯은 바인딩에서 제외된다."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서",
        recognition_result=rec,
        confirmed_field_keys={"projectName", "contractorName", "reportDate", "inspector"},
        required_field_keys={"projectName"},
        now=FIXED_NOW,
    )
    keys = {b.fieldKey for b in tpl.bindings}
    assert keys == {"projectName", "contractorName", "reportDate"}, keys
    assert "inspector" not in keys  # 직인표 슬롯 차단
    assert tpl.excludedTableIds == ["t2"]
    print("PASS setup_excludes_unsafe_tables")


def test_save_load_roundtrip(tmp_dir: Path) -> None:
    """저장→로드 왕복 — 바인딩·지문 보존."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서", recognition_result=rec, now=FIXED_NOW)
    path = store.save_template(tpl, template_dir=tmp_dir)
    assert path.exists()
    loaded = store.load_template(tpl.templateId, template_dir=tmp_dir)
    assert loaded is not None
    assert loaded.structureFingerprint == tpl.structureFingerprint
    assert len(loaded.bindings) == len(tpl.bindings)
    print("PASS save_load_roundtrip")


def test_apply_produces_cell_writes(tmp_dir: Path) -> None:
    """자동입력 — 값 주입 시 셀 쓰기 계획 생성(재인식 없음)."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서", recognition_result=rec,
        required_field_keys={"projectName"}, now=FIXED_NOW)
    plan = store.apply_template(tpl, {
        "projectName": "행복아파트 신축공사",
        "contractorName": "대한건설",
        "reportDate": "2026-07-22",
    })
    assert plan.status == store.PLAN_READY
    written = {c.fieldKey: c.value for c in plan.cellWrites}
    assert written["projectName"] == "행복아파트 신축공사"
    assert written["contractorName"] == "대한건설"
    assert len(plan.cellWrites) == 3
    print("PASS apply_produces_cell_writes")


def test_missing_required_flags_needs_input(tmp_dir: Path) -> None:
    """필수 필드 값 누락 → NEEDS_INPUT."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서", recognition_result=rec,
        required_field_keys={"projectName"}, now=FIXED_NOW)
    plan = store.apply_template(tpl, {"contractorName": "대한건설"})
    assert plan.status == store.PLAN_NEEDS_INPUT
    assert "projectName" in plan.missingRequired
    print("PASS missing_required_flags_needs_input")


def test_fingerprint_mismatch_refuses_fill(tmp_dir: Path) -> None:
    """다른 구조 서식엔 블라인드 채움 거부."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서", recognition_result=rec, now=FIXED_NOW)

    # 구조가 바뀐(라벨 다른) 업로드 서식
    different = FakeRecognition(
        tableRoles={"t1": "basic_info"},
        enhancedSlots=[FakeSlot("t1", "projectName", "사업명칭", row=0, col=1)],
    )
    plan = store.apply_template(
        tpl, {"projectName": "X"}, uploaded_recognition=different)
    assert plan.status == store.PLAN_FINGERPRINT_MISMATCH
    assert plan.cellWrites == []
    print("PASS fingerprint_mismatch_refuses_fill")


def test_fingerprint_match_allows_fill(tmp_dir: Path) -> None:
    """같은 구조면 지문 대조 통과 후 채움."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서", recognition_result=rec, now=FIXED_NOW)
    # 동일 구조 재업로드
    same = _sample_recognition()
    plan = store.apply_template(
        tpl, {"projectName": "행복아파트"}, uploaded_recognition=same)
    assert plan.status == store.PLAN_READY
    assert len(plan.cellWrites) == 1
    print("PASS fingerprint_match_allows_fill")


def test_find_by_fingerprint(tmp_dir: Path) -> None:
    """지문으로 템플릿 검색 (formName 문자열 매칭보다 견고)."""
    rec = _sample_recognition()
    tpl = store.build_template_from_recognition(
        form_name="착공신고서", recognition_result=rec, now=FIXED_NOW)
    store.save_template(tpl, template_dir=tmp_dir)
    found = store.find_template_by_fingerprint(
        tpl.structureFingerprint, template_dir=tmp_dir)
    assert found is not None
    assert found.templateId == tpl.templateId
    print("PASS find_by_fingerprint")


def _run_all() -> int:
    import tempfile
    tests = [
        test_setup_excludes_unsafe_tables,
        test_save_load_roundtrip,
        test_apply_produces_cell_writes,
        test_missing_required_flags_needs_input,
        test_fingerprint_mismatch_refuses_fill,
        test_fingerprint_match_allows_fill,
        test_find_by_fingerprint,
    ]
    failed = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as td:
            try:
                t(Path(td))
            except AssertionError as exc:
                failed += 1
                print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
