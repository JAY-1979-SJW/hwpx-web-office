"""HWPX-FORM-INDEX-AND-RECOMMEND-01 — 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

JSONL = (
    PROJECT_ROOT / "data" / "reports"
    / "hwpx_form_type_classification" / "per_file_form_type.jsonl"
)


def test_form_index_importable():
    from hwpx.recognition_corpus import form_index as fi
    assert hasattr(fi, "FormIndex")
    assert hasattr(fi, "recommend")
    assert hasattr(fi, "get_index")


def test_form_index_loads():
    if not JSONL.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    from hwpx.recognition_corpus.form_index import FormIndex
    idx = FormIndex.load(JSONL)
    stats = idx.stats()
    assert stats["totalForms"] > 0


def test_deduplication():
    """동일 서식명은 1개로 집계."""
    if not JSONL.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    from hwpx.recognition_corpus.form_index import FormIndex
    idx = FormIndex.load(JSONL)
    # 5266개 파일 → 고유 서식 수가 더 적어야 함
    raw_count = sum(1 for _ in JSONL.read_text("utf-8").splitlines() if _.strip())
    assert idx.stats()["totalForms"] < raw_count


@pytest.mark.parametrize("query,expected_domain", [
    ("소방 완공검사 신청서", "소방시설"),
    ("가스 신고서",         "가스·위험물"),
    ("기계설비 검사 확인증", "기계설비"),
])
def test_recommend_returns_correct_domain(query, expected_domain):
    if not JSONL.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    from hwpx.recognition_corpus.form_index import FormIndex
    idx = FormIndex.load(JSONL)
    results = idx.search(query, top_n=5)
    assert results, f"'{query}' → 결과 없음"
    top = results[0]
    assert top.domain == expected_domain, (
        f"'{query}' → domain={top.domain} (expected {expected_domain}), formName={top.formName}"
    )


def test_recommend_result_structure():
    if not JSONL.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    from hwpx.recognition_corpus.form_index import FormIndex
    idx = FormIndex.load(JSONL)
    results = idx.search("신청서", top_n=3)
    assert results
    r = results[0]
    d = r.to_dict()
    for key in ("formName", "domain", "formKind", "byeoljiNumber", "fileCount", "score", "matchedTokens"):
        assert key in d, f"key missing: {key}"
    assert d["score"] > 0
    assert d["fileCount"] >= 1


def test_empty_query_returns_empty():
    if not JSONL.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    from hwpx.recognition_corpus.form_index import FormIndex
    idx = FormIndex.load(JSONL)
    assert idx.search("") == []


def test_static_index_exported():
    static = PROJECT_ROOT / "data" / "reports" / "hwpx_form_type_classification" / "form_index_static.json"
    if not static.exists():
        pytest.skip("form_index_static.json 미생성")
    data = json.loads(static.read_text("utf-8"))
    assert "forms" in data
    assert len(data["forms"]) > 0
    rec = data["forms"][0]
    for key in ("n", "d", "k", "b"):
        assert key in rec


def test_no_pii_in_recommend_output():
    """추천 결과에 PII 패턴 없음."""
    import re
    if not JSONL.exists():
        pytest.skip("per_file_form_type.jsonl 미생성")
    from hwpx.recognition_corpus.form_index import FormIndex
    idx = FormIndex.load(JSONL)
    results = idx.search("신청서 검사", top_n=20)
    pii_re = re.compile(r"\d{2,3}-\d{3,4}-\d{4}|\d{3}-\d{2}-\d{5}")
    for r in results:
        out = json.dumps(r.to_dict(), ensure_ascii=False)
        assert not pii_re.search(out), f"PII in output: {out}"


def test_server_importable():
    """form_recommend_server가 import 가능."""
    import importlib.util
    srv = PROJECT_ROOT / "scripts" / "ops" / "form_recommend_server.py"
    assert srv.exists()
    spec = importlib.util.spec_from_file_location("form_recommend_server", srv)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "app")
    assert hasattr(mod, "form_recommend")
