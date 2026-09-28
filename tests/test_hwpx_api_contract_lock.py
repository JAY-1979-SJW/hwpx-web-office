"""HWPX-API-CONTRACT-LOCK-01 — 감리검사.

deterministic. writer/output 미생성, AI/OCR 미호출, secret 미출력.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def cn():
    from scripts.hwpx.api_contract import editor_command_contract as m

    return m


# ── T01 contract identity ───────────────────────────────────────────────────


def test_t01_contract_name(cn):
    assert cn.CONTRACT_NAME == "HWPX-API-CONTRACT-LOCK-01"


def test_t02_command_types_set(cn):
    assert len(cn.ALLOWED_COMMAND_TYPES) == 15
    for ct in (
        "replaceText",
        "replacePlaceholder",
        "updateTableCell",
        "addTableRow",
        "deleteTableRow",
        "validateDocument",
        "fillScheduleBars",
        "buildMonthlyScheduleTable",
        "buildDailyScheduleTable",
        "mergeCells",
        "splitCells",
        "setCellFill",
        "applyStyleFromSource",
        "autoFillFromAI",
        "autoDetectInputSlots",
    ):
        assert ct in cn.ALLOWED_COMMAND_TYPES


def test_t03_command_spec_complete(cn):
    for ct in cn.ALLOWED_COMMAND_TYPES:
        assert ct in cn.COMMAND_SPEC, ct
        assert "required_target" in cn.COMMAND_SPEC[ct]
        assert "required_payload" in cn.COMMAND_SPEC[ct]


# ── T10 envelope validation ────────────────────────────────────────────────


def test_t10_empty_command_fails(cn):
    errs = cn.validate_command_envelope({})
    assert "MISSING_COMMAND_TYPE" in errs
    assert "MISSING_ARTIFACT_ID" in errs


def test_t11_unknown_command_type(cn):
    errs = cn.validate_command_envelope({"commandType": "BOGUS", "artifactId": "a"})
    assert "UNKNOWN_COMMAND_TYPE" in errs


def test_t12_invalid_artifact_id(cn):
    errs = cn.validate_command_envelope({"commandType": "replaceText", "artifactId": "a/b/c"})
    assert "INVALID_ARTIFACT_ID_FORMAT" in errs


def test_t13_dry_run_not_bool(cn):
    errs = cn.validate_command_envelope({
        "commandType": "validateDocument",
        "artifactId": "a",
        "dryRun": "yes",
    })
    assert "DRY_RUN_NOT_BOOL" in errs


def test_t14_forbidden_fields(cn):
    errs = cn.validate_command_envelope({
        "commandType": "validateDocument",
        "artifactId": "a",
        "filesystemPath": "/etc/passwd",
    })
    assert any(e.startswith("FORBIDDEN_FIELD:filesystemPath") for e in errs)


def test_t15_forbidden_field_nested(cn):
    errs = cn.validate_command_envelope({
        "commandType": "validateDocument",
        "artifactId": "a",
        "payload": {"meta": {"token": "abc"}},
    })
    assert any("token" in e for e in errs)


# ── T20 body validation per command ────────────────────────────────────────


def test_t20_replace_text_missing(cn):
    errs = cn.validate_command_body({
        "commandType": "replaceText",
        "target": {},
        "payload": {},
    })
    assert "MISSING_TARGET:paragraphIndex" in errs
    assert "MISSING_PAYLOAD:oldText" in errs
    assert "MISSING_PAYLOAD:replacement" in errs


def test_t21_replace_text_valid(cn):
    errs = cn.validate_command_body({
        "commandType": "replaceText",
        "target": {"paragraphIndex": 0},
        "payload": {"oldText": "a", "replacement": "b"},
    })
    assert errs == []


def test_t22_update_table_cell_all(cn):
    errs = cn.validate_command_body({
        "commandType": "updateTableCell",
        "target": {"tableIndex": 0, "row": 0, "col": 1},
        "payload": {"value": "x"},
    })
    assert errs == []


def test_t23_update_table_cell_missing(cn):
    errs = cn.validate_command_body({
        "commandType": "updateTableCell",
        "target": {"tableIndex": 0},
        "payload": {},
    })
    assert "MISSING_TARGET:row" in errs
    assert "MISSING_TARGET:col" in errs
    assert "MISSING_PAYLOAD:value" in errs


def test_t24_validate_document_no_required(cn):
    errs = cn.validate_command_body({
        "commandType": "validateDocument",
        "target": {},
        "payload": {},
    })
    assert errs == []


def test_t25_replace_placeholder_required(cn):
    errs = cn.validate_command_body({
        "commandType": "replacePlaceholder",
        "target": {},
        "payload": {"key": "공사명", "value": "x"},
    })
    assert errs == []


def test_t26_add_table_row_values(cn):
    errs = cn.validate_command_body({
        "commandType": "addTableRow",
        "target": {"tableIndex": 0},
        "payload": {"values": ["a", "b"]},
    })
    assert errs == []


def test_t27_delete_table_row(cn):
    errs = cn.validate_command_body({
        "commandType": "deleteTableRow",
        "target": {"tableIndex": 0, "row": 1},
        "payload": {},
    })
    assert errs == []


# ── T30 full validate_command ──────────────────────────────────────────────


def test_t30_full_valid(cn):
    r = cn.validate_command({
        "commandType": "updateTableCell",
        "artifactId": "abc-123_X",
        "target": {"tableIndex": 0, "row": 0, "col": 1},
        "payload": {"value": "공사명"},
        "dryRun": True,
    })
    assert r["ok"] is True and r["errors"] == []


def test_t31_unknown_short_circuits_body(cn):
    r = cn.validate_command({
        "commandType": "BOGUS",
        "artifactId": "abc",
    })
    assert "UNKNOWN_COMMAND_TYPE" in r["errors"]
    assert not any(e.startswith("MISSING_TARGET:") for e in r["errors"])


# ── T40 build_command ──────────────────────────────────────────────────────


def test_t40_build_valid(cn):
    cmd = cn.build_command(
        command_type="replaceText",
        artifact_id="a1",
        target={"paragraphIndex": 0},
        payload={"oldText": "x", "replacement": "y"},
    )
    assert cmd["commandType"] == "replaceText"
    assert cmd["dryRun"] is True


def test_t41_build_invalid_raises(cn):
    with pytest.raises(cn.ContractViolation):
        cn.build_command(
            command_type="updateTableCell",
            artifact_id="a1",
            target={"tableIndex": 0},
            payload={},
        )


# ── T50 response validation ────────────────────────────────────────────────


def test_t50_valid_response(cn):
    r = cn.validate_response({
        "schemaVersion": "1.0",
        "engineVersion": "0.6.2",
        "artifactId": "a",
        "applied": False,
    })
    assert r["ok"] is True


def test_t51_missing_schema_version(cn):
    r = cn.validate_response({
        "engineVersion": "0.6.2",
        "artifactId": "a",
        "applied": False,
    })
    assert "MISSING_RESPONSE_KEY:schemaVersion" in r["errors"]


def test_t52_schema_version_mismatch(cn):
    r = cn.validate_response({
        "schemaVersion": "0.9",
        "engineVersion": "0.6.2",
        "artifactId": "a",
        "applied": False,
    })
    assert any("SCHEMA_VERSION_MISMATCH" in e for e in r["errors"])


def test_t53_engine_version_outside(cn):
    r = cn.validate_response({
        "schemaVersion": "1.0",
        "engineVersion": "1.0.0",
        "artifactId": "a",
        "applied": False,
    })
    assert any("ENGINE_VERSION_OUTSIDE_RANGE" in e for e in r["errors"])


def test_t54_applied_without_output(cn):
    r = cn.validate_response({
        "schemaVersion": "1.0",
        "engineVersion": "0.6.2",
        "artifactId": "a",
        "applied": True,
    })
    assert "APPLIED_WITHOUT_OUTPUT_ARTIFACT_ID" in r["errors"]


def test_t55_applied_with_output(cn):
    r = cn.validate_response({
        "schemaVersion": "1.0",
        "engineVersion": "0.6.2",
        "artifactId": "a",
        "applied": True,
        "outputArtifactId": "b",
    })
    assert r["ok"] is True


# ── T60 Java contract synchronization ──────────────────────────────────────
# 아래 5개는 src/main/java/... 를 직접 읽는다 — 02 저장소 분리(2026-05-22)
# 이전 시절의 Java 백엔드 흔적으로 33(office-analysis-engine) 소관이다.
# 2026-09-28 완성도 감사에서 실측 확인. 02↔33 통합 결정 대기. 이 파일의
# 나머지 T01-T59/T70+ 는 Python 쪽 계약만 검사해 Java 유무와 무관하므로
# 그대로 유지한다.
_JAVA_SKIP_REASON = (
    "Java 백엔드(src/main/java/...)는 33 저장소 소관 — 02 분리 이후 범위 밖 (02↔33 통합 결정 대기)"
)


@pytest.mark.skip(reason=_JAVA_SKIP_REASON)
def test_t60_envelope_fields_in_java(cn):
    fields = cn.java_command_envelope_fields()
    for required in ("commandId", "commandType", "artifactId", "target", "payload", "dryRun"):
        assert required in fields, required


@pytest.mark.skip(reason=_JAVA_SKIP_REASON)
def test_t61_schema_version_java_equals_python(cn):
    assert cn.java_response_schema_version() == cn.EXPECTED_SCHEMA_VERSION


@pytest.mark.skip(reason=_JAVA_SKIP_REASON)
def test_t62_engine_version_prefix_match(cn):
    jv = cn.java_response_engine_version()
    assert jv is not None
    assert jv.startswith(cn.EXPECTED_ENGINE_VERSION_PREFIX)


@pytest.mark.skip(reason=_JAVA_SKIP_REASON)
def test_t63_apply_engine_cases_covered(cn):
    cases = cn.java_apply_engine_command_types()
    # 모든 Java apply case가 Python contract에 존재
    overlap = cases & {
        "replaceText",
        "replacePlaceholder",
        "updateTableCell",
        "addTableRow",
        "deleteTableRow",
        "validateDocument",
    }
    for c in overlap:
        assert c in cn.ALLOWED_COMMAND_TYPES, c


@pytest.mark.skip(reason=_JAVA_SKIP_REASON)
def test_t64_full_sync_check(cn):
    res = cn.check_python_java_sync()
    assert res["ok"], res["findings"]


# ── T70 isolation + snapshot ──────────────────────────────────────────────


def test_t70_production_isolation(cn):
    res = cn.audit_api_contract_isolation()
    assert res["ok"], res["violations"]


def test_t71_module_no_writer(cn):
    src = Path(cn.__file__).read_text(encoding="utf-8")
    for needle in ("GenericEditPlanWriter", "writer_executor", "writer_adapter"):
        assert needle not in src


def test_t72_module_no_ai_ocr(cn):
    src = Path(cn.__file__).read_text(encoding="utf-8").lower()
    for needle in ("anthropic", "openai", "tesseract", "anthropic_api_key"):
        assert needle not in src


def test_t73_module_no_secret(cn):
    src = Path(cn.__file__).read_text(encoding="utf-8")
    for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
        assert needle not in src


def test_t74_snapshot_renders(cn):
    snap = cn.dump_contract_snapshot()
    assert snap["contractName"] == "HWPX-API-CONTRACT-LOCK-01"
    assert "allowedCommandTypes" in snap
    js = cn.dump_contract_snapshot_json()
    assert "allowedCommandTypes" in js
