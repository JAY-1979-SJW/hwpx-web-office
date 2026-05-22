"""HWPX-FIXTURE-SELECTION-01: fixture 기반 회귀 테스트.

fixture_manifest.json 기준으로 모든 fixture 파일이:
- 존재하고 ZIP으로 열리며
- corpus profiler가 정상 스캔하고
- 기대 layout type 최소 1개 이상 출력하는지 검증한다.

layoutGuess 값을 완전히 고정하지 않고 최소 조건만 검사하므로
분류기 개선 시에도 쉽게 유지 가능하다.
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "hwpx" / "corpus"
MANIFEST_PATH = FIXTURE_DIR / "fixture_manifest.json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "local"))
from hwpx_corpus_profiler import parse_args, run_profiler  # noqa: E402


# ── manifest 로드 ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def manifest() -> dict:
    assert MANIFEST_PATH.exists(), f"fixture_manifest.json 없음: {MANIFEST_PATH}"
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def fixtures(manifest) -> list[dict]:
    return manifest["fixtures"]


# ── 1. manifest 구조 검증 ─────────────────────────────────────────────────────

def test_manifest_loads(manifest):
    assert "fixtures" in manifest
    assert len(manifest["fixtures"]) >= 3, "fixture 최소 3개 이상 필요"


def test_manifest_has_required_fields(fixtures):
    required = {"fixtureId", "category", "fileName", "sourcePathHash",
                "sizeBytes", "expectedLayoutTypes", "expectedTableCountMin"}
    for f in fixtures:
        missing = required - set(f.keys())
        assert not missing, f"{f['fixtureId']}: 필수 필드 누락 {missing}"


# ── 2. 파일 존재 + ZIP 열기 ───────────────────────────────────────────────────

def test_all_fixture_files_exist(fixtures):
    for f in fixtures:
        path = FIXTURE_DIR / f["fileName"]
        assert path.exists(), f"fixture 파일 없음: {path}"


def test_all_fixture_files_are_valid_zip(fixtures):
    for f in fixtures:
        path = FIXTURE_DIR / f["fileName"]
        assert zipfile.is_zipfile(path), f"ZIP 아님: {path}"


def test_fixture_sizes_match_manifest(fixtures):
    for f in fixtures:
        path = FIXTURE_DIR / f["fileName"]
        actual_size = path.stat().st_size
        assert actual_size == f["sizeBytes"], (
            f"{f['fileName']}: 크기 불일치 manifest={f['sizeBytes']} actual={actual_size}"
        )


# ── 3. mimetype 확인 ──────────────────────────────────────────────────────────

def test_fixture_mimetype_valid(fixtures):
    valid_mimetypes = {"application/hwp+zip", "application/owpml", ""}
    for f in fixtures:
        path = FIXTURE_DIR / f["fileName"]
        with zipfile.ZipFile(path) as zf:
            if "mimetype" in zf.namelist():
                mt = zf.read("mimetype").decode("utf-8", errors="replace").strip()
                assert mt in valid_mimetypes, f"{f['fileName']}: unexpected mimetype {mt!r}"


# ── 4. corpus profiler 스캔 가능 ─────────────────────────────────────────────

@pytest.fixture(scope="session")
def fixture_scan_result(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixture_scan")
    args = parse_args([
        "--root", str(FIXTURE_DIR),
        "--out", str(out),
        "--max-files", "0",
        "--anonymize-paths",
    ])
    result = run_profiler(args)
    catalog_path = out / "table_catalog.jsonl"
    catalog = []
    if catalog_path.exists():
        catalog = [json.loads(l) for l in catalog_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    inv_path = out / "inventory.jsonl"
    inv = []
    if inv_path.exists():
        inv = [json.loads(l) for l in inv_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    fails_path = out / "parse_failures.jsonl"
    fails = []
    if fails_path.exists():
        fails = [json.loads(l) for l in fails_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {"result": result, "catalog": catalog, "inv": inv, "fails": fails, "out": out}


def test_profiler_scans_all_fixtures(fixtures, fixture_scan_result):
    scanned = fixture_scan_result["result"]["scanned"]
    # synthetic fixture는 manifest 외 파일이므로 >= 비교
    assert scanned >= len(fixtures), f"스캔 수 {scanned} < fixture 수 {len(fixtures)}"


def test_profiler_all_zip_ok(fixture_scan_result):
    assert fixture_scan_result["result"]["zip_ok"] == fixture_scan_result["result"]["scanned"]


def test_profiler_produces_table_catalog(fixture_scan_result):
    catalog = fixture_scan_result["catalog"]
    assert len(catalog) >= 1, "table_catalog 비어있음"


# ── 5. expectedTableCountMin 충족 ────────────────────────────────────────────

def test_total_table_count_meets_minimum(fixtures, fixture_scan_result):
    catalog = fixture_scan_result["catalog"]
    total_expected_min = sum(f["expectedTableCountMin"] for f in fixtures)
    assert len(catalog) >= total_expected_min, (
        f"총 table 수 {len(catalog)} < 기대 최소값 {total_expected_min}"
    )


# ── 6. expectedLayoutTypes 최소 1개 감지 ────────────────────────────────────

def test_expected_layout_types_detected(fixtures, fixture_scan_result):
    catalog = fixture_scan_result["catalog"]
    all_layouts = {t.get("layoutGuess", "unknown") for t in catalog}
    for f in fixtures:
        expected = set(f["expectedLayoutTypes"])
        found = expected & all_layouts
        assert found, (
            f"{f['fixtureId']}: expected layouts {expected} 중 하나도 감지되지 않음. "
            f"실제 layouts: {all_layouts}"
        )


# ── 7. expectedHasMergedCells ─────────────────────────────────────────────────

def test_merged_cells_detected_where_expected(fixtures, fixture_scan_result):
    catalog = fixture_scan_result["catalog"]
    any_merged = any(t.get("hasMergedCells") for t in catalog)
    expected_merged = any(f["expectedHasMergedCells"] for f in fixtures)
    if expected_merged:
        assert any_merged, "병합 셀이 기대되지만 감지되지 않음"


# ── 8. expectedHasNestedTables ────────────────────────────────────────────────

def test_nested_tables_detected_where_expected(fixtures, fixture_scan_result):
    catalog = fixture_scan_result["catalog"]
    any_nested = any(t.get("hasNestedTables") for t in catalog)
    expected_nested = any(f["expectedHasNestedTables"] for f in fixtures)
    if expected_nested:
        assert any_nested, "중첩 표가 기대되지만 감지되지 않음"


# ── 9. parser 실패 없음 (경고만 허용) ────────────────────────────────────────

def test_no_fatal_parse_failures(fixtures, fixture_scan_result):
    fails = fixture_scan_result["fails"]
    # ZIP_OPEN 실패는 불허
    fatal_fails = [f for f in fails if f.get("stage") == "ZIP_OPEN"]
    assert not fatal_fails, f"ZIP 열기 실패 fixture 존재: {fatal_fails}"


# ── 10. 절대경로 미노출 ───────────────────────────────────────────────────────

def test_no_absolute_path_in_catalog(fixture_scan_result):
    out = fixture_scan_result["out"]
    catalog_path = out / "table_catalog.jsonl"
    if catalog_path.exists():
        content = catalog_path.read_text(encoding="utf-8")
        # Windows 드라이브 문자 절대경로 패턴
        import re
        abs_pattern = re.compile(r"[A-Za-z]:\\\\")
        assert not abs_pattern.search(content), "table_catalog에 절대경로 노출됨"
