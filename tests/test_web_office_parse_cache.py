"""파싱 캐시 감리 — 캐시가 조용히 낡지 않는가.

캐시의 유일한 치명적 실패는 "파서가 바뀌었는데 옛 결과를 계속 돌려주는 것"
이다. 속도는 덤이고 이게 본질이라, 무효화 장치를 여기서 고정한다.

  ① 파서 소스가 바뀌면 버전이 바뀐다 (→ 캐시 자동 무효화)
  ② 버전이 다르면 저장 경로가 갈린다 (→ 옛 항목을 새 파서가 집지 않는다)
  ③ 왕복 보존 — 넣은 것과 꺼낸 것이 같다
  ④ requestId 는 꺼낼 때마다 새로 발급된다 (호출 단위 식별자 의미 유지)
  ⑤ PARSER_SOURCES 에 실재하지 않는 경로가 없다 (오타로 감시가 비는 것 방지)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PR))

from scripts.hwpx.web_office import parse_cache as PC  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_version_cache():
    """`parser_version` 은 모듈 전역에 값을 물고 있다.

    monkeypatch 로 가짜 PARSER_SOURCES 를 쓴 테스트가 그 전역에 가짜 버전을
    남기면, 뒤따르는 실문서 대조 테스트가 엉뚱한 캐시 경로를 보고 조용히
    skip 된다(실제로 그렇게 넘어갔다). 매 테스트마다 비운다.
    """
    PC._parser_version = None
    yield
    PC._parser_version = None


# ── ① 파서가 바뀌면 버전이 바뀐다 ───────────────────────────────

def test_parser_version_changes_when_a_parser_source_changes(tmp_path,
                                                             monkeypatch):
    """감시 목록의 파일 내용이 바뀌면 버전이 달라져야 한다."""
    probe = tmp_path / "fake_parser.py"
    probe.write_text("x = 1\n", encoding="utf-8")
    rel = probe.relative_to(tmp_path).as_posix()

    monkeypatch.setattr(PC, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(PC, "PARSER_SOURCES", [rel])

    v1 = PC.parser_version(refresh=True)
    probe.write_text("x = 2\n", encoding="utf-8")
    v2 = PC.parser_version(refresh=True)

    assert v1 != v2, "파서 소스가 바뀌었는데 캐시 버전이 그대로다 — 캐시가 낡는다"


def test_parser_version_stable_when_nothing_changes(tmp_path, monkeypatch):
    """반대로, 안 바뀌면 버전도 그대로여야 한다(불필요한 전량 재파싱 방지)."""
    probe = tmp_path / "fake_parser.py"
    probe.write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(PC, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(PC, "PARSER_SOURCES",
                        [probe.relative_to(tmp_path).as_posix()])
    assert PC.parser_version(refresh=True) == PC.parser_version(refresh=True)


def test_missing_parser_source_still_yields_version(tmp_path, monkeypatch):
    """감시 대상이 사라져도 죽지 않고, 버전이 달라져 안전한 쪽으로 실패한다."""
    monkeypatch.setattr(PC, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(PC, "PARSER_SOURCES", ["없는파일.py"])
    v_missing = PC.parser_version(refresh=True)
    (tmp_path / "없는파일.py").write_text("y = 1\n", encoding="utf-8")
    v_present = PC.parser_version(refresh=True)
    assert v_missing and v_present and v_missing != v_present


# ── ② 버전이 다르면 경로가 갈린다 ───────────────────────────────

def test_entry_path_separates_versions():
    d = "a" * 64
    p1 = PC.entry_path(d, version="ver00000001")
    p2 = PC.entry_path(d, version="ver00000002")
    assert p1 != p2
    assert p1.name == p2.name == f"{d}.json.gz"
    # 한 폴더에 수만 개가 쌓이지 않도록 앞 2자로 가른다
    assert p1.parent.name == d[:2]


def test_read_entry_misses_on_other_version(tmp_path, monkeypatch):
    monkeypatch.setattr(PC, "CACHE_ROOT", tmp_path)
    d = "b" * 64
    PC.write_entry(d, {"verdict": "PASS"}, version="verA")
    assert PC.read_entry(d, version="verA") is not None
    assert PC.read_entry(d, version="verB") is None, (
        "다른 파서 버전의 캐시를 집었다 — 무효화가 안 된다")


# ── ③ 왕복 보존 ────────────────────────────────────────────────

def test_round_trip_preserves_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(PC, "CACHE_ROOT", tmp_path)
    payload = {
        "verdict": "PASS",
        "documentModel": {"paragraphs": [{"text": "가나다 ㎜ 라마"}],
                          "requestId": "orig"},
        "renderPayload": {"tables": [{"cells": [{"row": 0, "col": 1,
                                                 "text": "성명"}]}]},
    }
    d = "c" * 64
    PC.write_entry(d, payload, version="v1")
    got = PC.read_entry(d, version="v1")
    assert got == payload


def test_corrupt_entry_is_treated_as_miss(tmp_path, monkeypatch):
    """반쪽 파일이 남아도 죽지 않고 다시 파싱하도록 miss 처리한다."""
    monkeypatch.setattr(PC, "CACHE_ROOT", tmp_path)
    d = "d" * 64
    p = PC.entry_path(d, version="v1")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"not gzip at all")
    assert PC.read_entry(d, version="v1") is None


# ── ④ requestId 는 꺼낼 때마다 새로 ────────────────────────────

def test_request_id_refreshed_on_read():
    payload = {"documentModel": {"requestId": "same-every-time"}}
    a = PC._refresh_volatile(json.loads(json.dumps(payload)))
    b = PC._refresh_volatile(json.loads(json.dumps(payload)))
    assert a["documentModel"]["requestId"] != "same-every-time"
    assert a["documentModel"]["requestId"] != b["documentModel"]["requestId"], (
        "캐시를 읽은 호출들이 같은 requestId 를 달고 나간다 — 추적이 엉킨다")


def test_volatile_field_excluded_from_comparison():
    a = {"documentModel": {"requestId": "x", "paragraphs": []}}
    b = {"documentModel": {"requestId": "y", "paragraphs": []}}
    assert PC._without_volatile(a) == PC._without_volatile(b)
    # 원본은 건드리지 않는다
    assert a["documentModel"]["requestId"] == "x"


def test_volatile_exclusion_does_not_hide_real_difference():
    """requestId 만 빼고, 실제 내용 차이는 그대로 드러나야 한다."""
    a = {"documentModel": {"requestId": "x", "paragraphs": [{"text": "성명"}]}}
    b = {"documentModel": {"requestId": "y", "paragraphs": [{"text": "명칭"}]}}
    assert PC._without_volatile(a) != PC._without_volatile(b)


# ── ⑤ 감시 목록이 실재하는가 ───────────────────────────────────

def test_parser_sources_all_exist():
    """오타나 파일 이동으로 감시 목록에 구멍이 나면 캐시가 낡는다.

    (없어도 버전은 나오지만, 그건 사고 대응이지 정상 상태가 아니다.)
    """
    missing = [rel for rel in PC.PARSER_SOURCES
               if not (PC.PROJECT_ROOT / rel).is_file()]
    assert not missing, f"PARSER_SOURCES 에 없는 경로: {missing}"


def test_parser_sources_cover_core_modules():
    """파싱 결과를 직접 만드는 핵심 모듈이 빠지지 않았는지."""
    must = [
        "scripts/hwpx/web_office/ro_view_importer.py",
        "scripts/hwpx/web_office/render_payload.py",
        "scripts/hwpx/parser/table_parser.py",
        "scripts/hwpx/parser/parser_engine.py",
    ]
    for rel in must:
        assert rel in PC.PARSER_SOURCES, f"{rel} 이 캐시 무효화 감시에서 빠졌다"


# ── ⑥ 실제 문서 왕복 (캐시가 있으면) ───────────────────────────

def test_cached_load_matches_fresh_parse_on_real_document():
    """캐시본이 지금 파서 결과와 같은지 — 있을 때만 확인한다."""
    from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor
    root = PC.CACHE_ROOT / PC.parser_version()
    if not root.is_dir():
        pytest.skip("캐시 없음")
    entries = list(root.rglob("*.json.gz"))
    if not entries:
        pytest.skip("캐시 항목 없음")
    cached = PC.read_entry(entries[0].name.replace(".json.gz", ""))
    if cached is None:
        pytest.skip("캐시 항목 판독 불가")
    rel = cached.get("sourcePath")
    if not rel or not (PC.PROJECT_ROOT / rel).is_file():
        pytest.skip("원본 부재")
    fresh = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": rel},
        project_root=PC.PROJECT_ROOT)
    assert (PC._without_volatile(cached) == PC._without_volatile(fresh)), (
        f"캐시가 낡았다: {rel}")
