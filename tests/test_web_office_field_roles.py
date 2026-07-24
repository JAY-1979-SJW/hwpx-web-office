"""서식 입력 스키마 회귀 — 칸 역할 분류 정확도를 정답셋으로 고정한다.

정답셋 3종(tests/fixtures/web_office/):
    field_role_ground_truth  ①튜닝셋   규칙을 보며 고친 셋 — 과적합 상한
    field_role_holdout       ②검증셋   1차 수정 후 측정 → 다시 보정에 사용
    field_role_testset       ③최종셋   규칙 수정에 쓰지 않은 셋 — 진짜 실력

세 셋을 모두 지키는 이유: ①만 보면 100% 가 나와 개선을 착각하게 된다.
실제로 초기안은 ①에서 100% 였지만 ③에서 68.3% 였다. 임계값은 현재
측정치보다 약간 낮게 잡아 우연한 변동은 통과시키되 실질 퇴행은 잡는다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402
from scripts.hwpx.web_office.form_field_roles import _self_test as roles_self_test  # noqa: E402
from scripts.hwpx.web_office.form_input_schema import (  # noqa: E402
    _self_test as schema_self_test,
    build_input_schema,
)
from scripts.hwpx.web_office.form_taxonomy import (  # noqa: E402
    _self_test as taxonomy_self_test,
    classify_document,
)

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "web_office"

# (정답셋, 최소 역할 정확도)
# 측정치 (2026-07-24 재측정, 텍스트 수리·역할/의미 분리 후):
#   ① 94.7%(143/151)  ② 93.2%(110/118)  ③ 95.2%(99/104)
# ③(무오염 최종셋)은 라벨 드리프트 0 — 텍스트 수리 후에도 정확히 매칭된다.
# 좌표·배치 정확성은 별도로 40서식 기입 전수시험(356칸 유출 0)으로 검증했다.
# ②의 하한이 측정치(93.2%)에 근접하니 변동에 유의 — 라벨 조각화 서식
# (연결납세방식 등)의 드리프트 7건이 끌어내린 값이다.
ACCURACY_FLOOR = [
    ("field_role_ground_truth", 0.93),
    ("field_role_holdout", 0.93),
    ("field_role_testset", 0.85),
]


def _load(fixture: str) -> list[dict]:
    return json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))


def _measure(fixture: str) -> tuple[int, int]:
    """(맞은 칸, 전체 칸)"""
    hit = total = 0
    for form in _load(fixture):
        res = load_hwpx_for_editor(
            {"operation": "HWPX_EDITOR_LOAD", "sourcePath": form["sourcePath"]},
            project_root=PROJECT_ROOT)
        assert res.get("verdict") == "PASS", form["sourcePath"]
        schema = build_input_schema(res["documentModel"], res["renderPayload"],
                                    name=form["name"],
                                    field_count=len(form["fields"]))
        pred = {i["label"]: i["role"] for i in schema["inputs"]}
        for f in form["fields"]:
            role = pred.get(f["label"]) or next(
                (v for k, v in pred.items() if k.endswith(" " + f["label"])), None)
            if role is None:
                role = "noise"          # 스키마에 없으면 잡음으로 걸러진 것
            total += 1
            hit += (role == f["role"])
    return hit, total


@pytest.mark.parametrize("module_test", [
    pytest.param(taxonomy_self_test, id="form_taxonomy"),
    pytest.param(roles_self_test, id="form_field_roles"),
    pytest.param(schema_self_test, id="form_input_schema"),
])
def test_module_self_tests_pass(module_test):
    failures = [line for line in module_test() if line.startswith("FAIL")]
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("fixture,floor", ACCURACY_FLOOR)
def test_role_accuracy_floor(fixture, floor):
    hit, total = _measure(fixture)
    assert total > 0, f"{fixture}: 측정 대상 없음"
    acc = hit / total
    assert acc >= floor, (
        f"{fixture} 역할 정확도 {acc:.1%} ({hit}/{total}) < 하한 {floor:.0%} — 퇴행")


def test_noise_never_swallows_real_inputs():
    """잡음 제외가 실입력칸을 삼키면 안 된다(초기 설계의 치명적 실패 방식).

    정답이 applicant/office 인 칸이 스키마에서 사라진 비율을 본다.
    """
    kept = dropped = 0
    for fixture, _ in ACCURACY_FLOOR:
        for form in _load(fixture):
            res = load_hwpx_for_editor(
                {"operation": "HWPX_EDITOR_LOAD", "sourcePath": form["sourcePath"]},
                project_root=PROJECT_ROOT)
            schema = build_input_schema(res["documentModel"], res["renderPayload"],
                                        name=form["name"],
                                        field_count=len(form["fields"]))
            labels = {i["label"] for i in schema["inputs"]}
            for f in form["fields"]:
                if f["role"] == "noise":
                    continue
                present = f["label"] in labels or any(
                    l.endswith(" " + f["label"]) for l in labels)
                kept += present
                dropped += not present
    total = kept + dropped
    assert total > 0
    assert kept / total >= 0.85, (
        f"실입력칸 보존율 {kept/total:.1%} ({kept}/{total}) — 잡음 규칙이 과하다")


def test_sensitive_fields_are_flagged():
    """주민등록번호 같은 민감칸은 반드시 표시된다(값은 다루지 않는다)."""
    rp = {"tables": [{"cells": [
        {"row": 0, "col": 0, "text": "주민등록번호"},
        {"row": 0, "col": 1, "text": ""},
    ]}]}
    dm = {"paragraphs": [{"containerScope": {
        "kind": "cell", "tableIndex": 0, "rowIndex": 0, "colIndex": 1}, "runs": []}]}
    schema = build_input_schema(dm, rp, name="어떤 신청서.hwpx", field_count=1)
    assert schema["sensitiveCount"] == 1
    assert schema["inputs"][0]["semantic"] == "residentNo"


def test_ledger_keeps_fields_but_marks_office():
    """대장·내부문서도 입력칸을 지우지 않고 역할만 관공서로 단다."""
    rp = {"tables": [{"cells": [
        {"row": 0, "col": 0, "text": "일련번호"}, {"row": 0, "col": 1, "text": ""},
        {"row": 1, "col": 0, "text": "성명"}, {"row": 1, "col": 1, "text": ""},
    ]}]}
    cell = lambda r: {"containerScope": {"kind": "cell", "tableIndex": 0,
                                         "rowIndex": r, "colIndex": 1}, "runs": []}
    dm = {"paragraphs": [cell(0), cell(1)]}
    schema = build_input_schema(dm, rp, name="채혈금지대상자 관리대장.hwpx",
                                field_count=2)
    assert schema["docType"] == "대장기록"
    assert schema["inputCount"] == 2, "대장이라고 칸을 지우면 안 된다"
    assert schema["applicantCount"] == 0


def test_deleted_stub_is_not_fillable():
    """'삭제 2014 7 29' 형태의 빈 껍데기는 채움 대상이 아니다."""
    r = classify_document("삭제 2014 7 29.hwpx", 0)
    assert r["fillable"] is False
    assert r["reason"] == "DELETED_STUB"
