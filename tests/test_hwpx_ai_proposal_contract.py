"""HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01 — 감리검사.

deterministic. AI 호출 없음, writer 미호출, output 미생성, secret 미출력.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def apc():
    from scripts.hwpx.ai_proposal import ai_proposal_contract as m
    return m


@pytest.fixture
def tr():
    from scripts.hwpx.ai_proposal import target_resolver as m
    return m


@pytest.fixture
def cp():
    from scripts.hwpx.ai_proposal import confidence_policy as m
    return m


@pytest.fixture
def rib():
    from scripts.hwpx.ai_proposal import review_item_builder as m
    return m


def _proposal(pid="p1", label="공사명", value="○○건축공사",
                confidence=0.9, semantic="PROJECT_NAME", target_hint=None,
                evidence=None):
    p = {"proposalId": pid, "label": label, "value": value,
            "confidence": confidence, "semanticType": semantic}
    if target_hint:
        p["targetHint"] = target_hint
    if evidence:
        p["evidence"] = evidence
    return p


def _recognition_with_label(label="공사명", cell_key="t0:r0:c1"):
    return {
        "documentId": "doc-1",
        "labelOccurrences": [{
            "normalizedLabel": label,
            "cellKey": cell_key,
            "paragraphKey": None,
            "neighborText": "현장",
        }],
    }


# ── envelope 검증 ─────────────────────────────────────────────────────────

def test_t01_contract_name(apc):
    assert apc.CONTRACT_NAME == "HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01"


def test_t02_valid_envelope(apc):
    errs = apc.validate_proposal_envelope(_proposal())
    assert errs == []


def test_t03_missing_required(apc):
    errs = apc.validate_proposal_envelope({"label": "x"})
    assert "MISSING_FIELD:proposalId" in errs
    assert "MISSING_FIELD:value" in errs
    assert "MISSING_FIELD:confidence" in errs


def test_t04_confidence_out_of_range(apc):
    errs = apc.validate_proposal_envelope(_proposal(confidence=1.5))
    assert "CONFIDENCE_OUT_OF_RANGE" in errs


def test_t05_confidence_not_number(apc):
    errs = apc.validate_proposal_envelope(_proposal(confidence="high"))
    assert "CONFIDENCE_NOT_NUMBER" in errs


def test_t06_forbidden_field(apc):
    p = _proposal()
    p["apiKey"] = "sk-..."
    errs = apc.validate_proposal_envelope(p)
    assert any(e.startswith("FORBIDDEN_FIELD:apiKey") for e in errs)


def test_t07_batch_split(apc):
    res = apc.validate_proposal_batch([
        _proposal("p1"),
        {"label": "missing"},  # invalid
        _proposal("p2"),
    ])
    assert res["acceptedCount"] == 2
    assert res["rejectedCount"] == 1


def test_t08_duplicate_proposal_id(apc):
    res = apc.validate_proposal_batch([
        _proposal("p1"), _proposal("p1"),
    ])
    assert res["acceptedCount"] == 1
    assert res["rejectedCount"] == 1


# ── 개인정보 redaction ────────────────────────────────────────────────────

def test_t10_redact_phone(apc):
    r = apc.redact_proposal_value("연락처 010-1234-5678")
    assert r["containsSensitive"] is True
    assert "010-1234-5678" not in r["redactedPreview"]


def test_t11_redact_bizno(apc):
    r = apc.redact_proposal_value("123-45-67890")
    assert r["containsSensitive"] is True


def test_t12_redact_normal_text(apc):
    r = apc.redact_proposal_value("○○건축공사")
    assert r["containsSensitive"] is False
    assert r["valueHash"] and len(r["valueHash"]) == 64
    assert r["redactedPreview"] == "○○건축공사"


def test_t13_redact_preview_max_20(apc):
    r = apc.redact_proposal_value("a" * 50)
    assert len(r["redactedPreview"]) <= 20


# ── target resolver ──────────────────────────────────────────────────────

def test_t20_normalize_label(tr):
    assert tr.normalize_label("공사 명") == "공사명"
    assert tr.normalize_label("(공사명):") == "공사명"


def test_t21_resolve_single_candidate(tr):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = tr.resolve_target({"label": "공사명"}, rec)
    assert res["status"] == "RESOLVED"
    assert res["target"]["cellKey"] == "t0:r0:c1"


def test_t22_resolve_not_found(tr):
    res = tr.resolve_target({"label": "비존재"},
                                  _recognition_with_label("공사명"))
    assert res["status"] == "NOT_FOUND"


def test_t23_resolve_ambiguous(tr):
    rec = {
        "labelOccurrences": [
            {"normalizedLabel": "공사명", "cellKey": "t0:r0:c1"},
            {"normalizedLabel": "공사명", "cellKey": "t1:r0:c1"},
        ],
    }
    res = tr.resolve_target({"label": "공사명"}, rec)
    assert res["status"] == "AMBIGUOUS"
    assert len(res["candidates"]) == 2


def test_t24_resolve_with_explicit_hint(tr):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = tr.resolve_target(
        {"label": "공사명", "targetHint": {"cellKey": "override"}}, rec)
    assert res["status"] == "RESOLVED"
    assert res["target"]["cellKey"] == "override"


# ── confidence policy ─────────────────────────────────────────────────────

def test_t30_auto_approve_off_by_default(cp):
    assert cp.AUTO_APPROVE_ENABLED is False


def test_t31_high_confidence_resolved_still_review(cp):
    res = cp.classify(confidence=0.98, target_status="RESOLVED")
    assert res["decision"] == "READY_FOR_DECISION"
    assert res["tier"] == "HIGH"


def test_t32_low_confidence_rejected(cp):
    res = cp.classify(confidence=0.3, target_status="RESOLVED")
    assert res["decision"] == "AUTO_REJECT"
    assert res["tier"] == "LOW"


def test_t33_target_not_found_rejected(cp):
    res = cp.classify(confidence=0.99, target_status="NOT_FOUND")
    assert res["decision"] == "AUTO_REJECT"
    assert "TARGET_NOT_FOUND" in res["reason"]


def test_t34_target_ambiguous_hold(cp):
    res = cp.classify(confidence=0.9, target_status="AMBIGUOUS")
    assert res["decision"] == "HOLD"


def test_t35_conflict_hold(cp):
    res = cp.classify(confidence=0.99, target_status="RESOLVED",
                          has_conflict=True)
    assert res["decision"] == "HOLD"
    assert "CONFLICT" in res["reason"]


def test_t36_medium_confidence_review(cp):
    res = cp.classify(confidence=0.8, target_status="RESOLVED")
    assert res["decision"] == "READY_FOR_DECISION"
    assert res["tier"] == "MEDIUM"


# ── review_item_builder 통합 ─────────────────────────────────────────────

def test_t40_end_to_end_single(rib):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = rib.build_review_items_from_proposals(
        [_proposal("p1", confidence=0.9)], rec)
    assert res["summary"]["acceptedReadyForReview"] == 1
    item = res["reviewItems"][0]
    assert item["target"]["cellKey"] == "t0:r0:c1"
    assert item["decisionSource"] == "AI_ASSISTED"
    assert item["policyDecision"] == "READY_FOR_DECISION"


def test_t41_end_to_end_mixed(rib):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = rib.build_review_items_from_proposals([
        _proposal("p1", confidence=0.9),                    # READY
        _proposal("p2", label="비존재", confidence=0.99),    # AUTO_REJECT (NOT_FOUND)
        _proposal("p3", confidence=0.3),                    # AUTO_REJECT (LOW)
    ], rec)
    assert res["summary"]["acceptedReadyForReview"] == 1
    assert res["summary"]["rejected"] == 2


def test_t42_conflict_label_holds(rib):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = rib.build_review_items_from_proposals(
        [_proposal("p1", confidence=0.9)],
        rec, conflict_labels={"공사명"})
    assert res["summary"]["holds"] == 1


def test_t43_raw_value_redacted_in_output(rib):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = rib.build_review_items_from_proposals(
        [_proposal("p1", value="010-1234-5678", confidence=0.9)], rec)
    item = res["reviewItems"][0]
    assert item["containsSensitive"] is True
    assert "010-1234-5678" not in str(item)


def test_t44_invalid_proposals_kept_separate(rib):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = rib.build_review_items_from_proposals([
        {"label": "missing", "value": "x", "confidence": 0.9},  # MISSING proposalId
        _proposal("p1", confidence=0.9),
    ], rec)
    assert res["summary"]["rejected"] == 1
    assert res["summary"]["acceptedReadyForReview"] == 1


def test_t45_auto_approve_off_high_conf_still_review(rib):
    rec = _recognition_with_label("공사명", "t0:r0:c1")
    res = rib.build_review_items_from_proposals(
        [_proposal("p1", confidence=0.99)], rec)
    item = res["reviewItems"][0]
    assert item["policyDecision"] == "READY_FOR_DECISION"


# ── 격리 + 모듈 sanity ───────────────────────────────────────────────────

def test_t50_production_isolation(apc):
    res = apc.audit_ai_proposal_isolation()
    assert res["ok"], res["violations"]


def test_t51_no_ai_api_in_modules():
    from scripts.hwpx.ai_proposal import (
        ai_proposal_contract, target_resolver,
        confidence_policy, review_item_builder,
    )
    for mod in (ai_proposal_contract, target_resolver,
                  confidence_policy, review_item_builder):
        src = Path(mod.__file__).read_text(encoding="utf-8").lower()
        for needle in ("anthropic", "openai", "tesseract",
                          "anthropic_api_key", "claude_cli", "import requests"):
            assert needle not in src, f"{mod.__name__}: {needle}"


def test_t52_no_writer_in_modules():
    from scripts.hwpx.ai_proposal import (
        ai_proposal_contract, target_resolver,
        confidence_policy, review_item_builder,
    )
    for mod in (ai_proposal_contract, target_resolver,
                  confidence_policy, review_item_builder):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("GenericEditPlanWriter", "writer_executor",
                          "writer_adapter"):
            assert needle not in src


def test_t53_no_secret_in_modules():
    from scripts.hwpx.ai_proposal import (
        ai_proposal_contract, target_resolver,
        confidence_policy, review_item_builder,
    )
    for mod in (ai_proposal_contract, target_resolver,
                  confidence_policy, review_item_builder):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        for needle in ("DATABASE_URL", "password=", "haehan-ai.pem"):
            assert needle not in src


def test_t54_snapshot(apc):
    snap = apc.dump_contract_snapshot()
    assert snap["contractName"] == "HWPX-AI-AUTO-FILL-PROPOSAL-CONTRACT-01"
    assert "requiredFields" in snap
    assert "forbiddenFields" in snap
