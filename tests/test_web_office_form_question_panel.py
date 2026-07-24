"""서식 질문 패널 감리 — 독립 브라우저 앞단.

app.mjs(메인 편집기, 병행 세션 영역)를 건드리지 않는 독립 패널. 기존
엔드포인트만 쓴다. TS/JS 런타임은 node self-test 로, 계약·안전 성질은
정적 검사로 검증한다(저장소의 프론트 contract 관례와 동일).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
FE = PR / "frontend" / "web_office_viewer"
MJS = FE / "form_question_panel.mjs"
HTML = FE / "form_question_panel.html"
SELFTEST = FE / "form_question_panel_self_test.mjs"


# ── 파일 존재 ───────────────────────────────────────────────────────────

def test_panel_files_exist():
    assert MJS.is_file()
    assert HTML.is_file()
    assert SELFTEST.is_file()


# ── 병행 세션 영역 불가침 ───────────────────────────────────────────────

def test_does_not_touch_main_app_files():
    """패널은 app.mjs / weboffice 를 import 하거나 <script src> 로 싣지 않는다.

    주석에서 'app.mjs 를 건드리지 않는다'고 설명하는 것은 허용 — 실제
    import/src 참조만 금지한다.
    """
    import re
    mjs = MJS.read_text(encoding="utf-8")
    html = HTML.read_text(encoding="utf-8")
    # import ... from "...app.mjs" 형태
    imports = re.findall(r'import\s+.*?from\s+["\']([^"\']+)["\']', mjs, re.S)
    for imp in imports:
        for bad in ("app.mjs", "weboffice", "coordinate_renderer"):
            assert bad not in imp, f"메인 앱 파일 import: {imp}"
    # <script src="...">
    srcs = re.findall(r'src\s*=\s*["\']([^"\']+)["\']', html)
    for s in srcs:
        for bad in ("app.mjs", "weboffice/", "coordinate_renderer"):
            assert bad not in s, f"메인 앱 파일 로드: {s}"


def test_uses_only_existing_endpoints():
    src = MJS.read_text(encoding="utf-8")
    for ep in ("hwpx-load", "fill-plan", "para-save-apply", "download/"):
        assert ep in src, f"엔드포인트 미사용: {ep}"


# ── §4 안전 성질 (정적) ─────────────────────────────────────────────────

def test_original_not_mutated_message():
    src = MJS.read_text(encoding="utf-8") + HTML.read_text(encoding="utf-8")
    assert "원본" in src and "sandbox" in src


def test_no_ai_or_ocr_direct_call():
    """패널이 AI/OCR 을 직접 부르지 않는다(§9 — 백엔드 경유만)."""
    src = MJS.read_text(encoding="utf-8")
    for bad in ("claude", "openai", "api.anthropic", "tesseract"):
        assert bad not in src.lower(), f"직접 호출 흔적: {bad}"


def test_inherits_charpr_not_creates():
    """기입 명령이 기존 charPr 를 상속(신규 생성 안 함)."""
    src = MJS.read_text(encoding="utf-8")
    assert "inheritCharPrIDRef" in src
    assert "createCharPr" not in src and "create_char_pr" not in src


def test_empty_value_not_filled_logic_present():
    """빈 값은 채우지 않는 방어가 코드에 있다."""
    src = MJS.read_text(encoding="utf-8")
    assert 'value === ""' in src or "value === ''" in src


# ── node self-test (런타임 로직) ────────────────────────────────────────

@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_node_self_test_passes():
    r = subprocess.run(["node", str(SELFTEST)], capture_output=True,
                       text=True, timeout=60, cwd=str(FE))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ALL PASS" in r.stdout
