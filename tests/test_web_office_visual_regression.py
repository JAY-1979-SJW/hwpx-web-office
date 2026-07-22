"""WEB-OFFICE-VISUAL-REGRESSION — 고정 시각 회귀셋(한컴 원본 대조 게이트).

핀 고정된 대표 HWPX 를 좌표 렌더러로 그려 각 문서 내장 한컴 원본 렌더
(PrvImage)와 격자선 위치를 대조한다. 기준선(baseline) 아래로 떨어지면
실패 → 렌더 회귀를 커밋 전에 잡는다.

기준선은 현재 known-good 값에서 여유를 둔 하한이다. 회귀 방지가 목적이라
개선(값 상승)은 통과하고, 악화(값 하락)만 잡는다. Chrome 없으면 skip.

재현성: data/drafts 는 파이프라인이 계속 생성해 유동적이므로, 검증된
fresh·무PII 문서를 tests/fixtures/hwpx/regression/ 로 복사해 핀 고정했다.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))
sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.ops.audit_web_office_visual_fidelity import (  # noqa: E402
    compare_one, _renderer_js, _chrome)

# name: (상대경로, 최소 within2px, 최대 median px, 대표 실패모드)
PINNED = {
    "simple_form": (
        "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx",
        0.72, 2.0, "단순 표 폼 (기준 케이스)"),
    "nested_signature": (
        "tests/fixtures/hwpx/corpus/fx_stamp_approval_legal.hwpx",
        0.68, 2.0, "셀 내 중첩표(서명블록) 하단 배치"),
    "nested_valign_center": (
        "tests/fixtures/hwpx/regression/reg_nested_valign_center.hwpx",
        0.80, 2.0, "vAlign=CENTER 셀 + 중첩표 voff 정합"),
    # 현재 롱테일(세로 미세 과대) — 악화만 잡는 느슨한 하한.
    "detail_form_watch": (
        "tests/fixtures/hwpx/regression/reg_detail_form.hwpx",
        0.18, 14.0, "세부 폼 세로 과대(추적용 하한)"),
}


@pytest.fixture(scope="module")
def _env():
    chrome = _chrome()
    if not chrome:
        pytest.skip("헤드리스 Chrome/Edge 없음 — 시각 회귀 게이트 skip")
    return chrome, _renderer_js()


@pytest.mark.parametrize("name", list(PINNED))
def test_visual_regression_gridlines(name, _env):
    chrome, rjs = _env
    rel, min_w2, max_med, desc = PINNED[name]
    path = PR / rel
    if not path.is_file():
        # .hwpx 는 저장소 관례상 gitignore(로컬/프로비저닝 제공). 부재 시
        # 게이트 skip — manifest(visual_regression_manifest.json)로 pin 정의.
        pytest.skip(f"핀 문서 미제공(로컬 전용): {rel}")
    with tempfile.TemporaryDirectory() as td:
        rec = compare_one(path, chrome, Path(td), rjs, PR)

    assert rec["verdict"] not in ("ERROR",), \
        f"[{name}] 렌더/추출 오류: {rec.get('error')}"
    # 정답지 신선도 훼손(파이프라인 재fill 등)은 게이트 대상 아님 — 알림만.
    if rec["verdict"] == "STALE":
        pytest.skip(f"[{name}] 정답지 실효(PrvImage<XML) — 픽셀 대조 불가")

    w2 = rec.get("gridWithin2px")
    med = rec.get("gridMedianAbsPx")
    assert w2 is not None and med is not None, \
        f"[{name}] 격자선 미검출 (gl={rec.get('gridlinesTruth')})"
    assert w2 >= min_w2, (
        f"[{name}] {desc}: 격자선 2px이내 비율 {w2:.3f} < 기준 {min_w2} "
        f"(median={med}px) — 렌더 회귀")
    assert med <= max_med, (
        f"[{name}] {desc}: 격자선 중앙값 오차 {med}px > 기준 {max_med}px "
        f"(within2px={w2:.3f}) — 렌더 회귀")
