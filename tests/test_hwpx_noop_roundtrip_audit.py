"""HWPX-EDIT-NO-OP-ROUNDTRIP-AUDIT-01 단위/통합 테스트."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))


def _import_audit():
    spec = importlib.util.spec_from_file_location(
        "hwpx_noop_roundtrip_audit",
        PROJECT_ROOT / "scripts/local/hwpx_noop_roundtrip_audit.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit_mod():
    return _import_audit()


@pytest.fixture(scope="module")
def audit_summary(audit_mod):
    return audit_mod.run_audit()


# ── T01: 전체 6/6 PASS ────────────────────────────────────────────────────────

def test_all_six_documents_pass_noop_roundtrip(audit_summary):
    assert audit_summary["pass"] == 6, audit_summary


def test_audit_verdict_is_pass(audit_summary):
    assert audit_summary["auditVerdict"] == "PASS"


def test_no_failures_or_blockers(audit_summary):
    assert audit_summary["failSnapshot"] == 0
    assert audit_summary["failEntries"] == 0
    assert audit_summary["failRequired"] == 0
    assert audit_summary["blockerOriginalMutated"] == 0


# ── T02: 원본 무수정 ──────────────────────────────────────────────────────────

def test_all_originals_unmodified(audit_summary):
    assert audit_summary["allOriginalUnmodified"] is True
    for d in audit_summary["documents"]:
        assert d["srcSha256Before"] == d["srcSha256After"], f"{d['docTag']} 원본 sha256 변경"


# ── T03: zip 구조 보존 ────────────────────────────────────────────────────────

def test_entry_names_preserved(audit_summary):
    for d in audit_summary["documents"]:
        assert d["entryNamesMatch"] is True, f"{d['docTag']}: entry 이름 변경"
        assert d["entryCountBefore"] == d["entryCountAfter"]


def test_entry_crc_preserved(audit_summary):
    """no-op 사본은 모든 entry CRC/size가 원본과 동일해야 한다."""
    for d in audit_summary["documents"]:
        assert d["entryCrcMatch"] is True, f"{d['docTag']}: entry CRC 변경"


def test_required_files_preserved(audit_summary):
    for d in audit_summary["documents"]:
        assert d["dstRequiredOk"] is True, f"{d['docTag']}: 필수 파일 누락"
        assert d["missingAfter"] == []


# ── T04: parser snapshot 보존 ─────────────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "tableCount", "cellCount", "cells_with_text",
    "cells_merged_origin", "cells_covered_by_merge",
    "cells_with_horizontalAlign", "cells_with_verticalAlign",
    "cells_with_fontSizePt", "cells_with_fontName",
    "cells_with_bold", "cells_with_italic", "cells_with_underline",
    "cells_with_textColor", "cells_with_nested_table",
    "rowSpanSum", "colSpanSum", "visualRowSum", "visualColSum",
    "normalizedTextDigest", "objectCount", "binDataCount", "scheduleCount",
])
def test_snapshot_metric_preserved(audit_summary, key):
    for d in audit_summary["documents"]:
        b = d["snapshotBefore"][key]
        a = d["snapshotAfter"][key]
        assert a == b, f"{d['docTag']} {key}: before={b} after={a}"


# ── T05: 빈 템플릿 분류 유지 (회귀) ───────────────────────────────────────────

def test_noop_outputs_exist_under_reports(audit_summary):
    for d in audit_summary["documents"]:
        p = PROJECT_ROOT / d["noopOutputRelPath"]
        assert p.exists(), f"{d['docTag']} no-op 사본 미생성"
        # output은 reports/ 하위에만 있어야 한다 (편집 산출물 격리)
        assert "reports/hwpx_noop_roundtrip_audit" in d["noopOutputRelPath"]


# ── T06: 일반 합리성 ──────────────────────────────────────────────────────────

def test_table_and_cell_counts_positive(audit_summary):
    for d in audit_summary["documents"]:
        assert d["snapshotBefore"]["tableCount"] >= 1
        assert d["snapshotBefore"]["cellCount"] >= 1
