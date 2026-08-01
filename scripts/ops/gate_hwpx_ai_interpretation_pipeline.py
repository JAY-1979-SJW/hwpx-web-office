"""AI 해석 공정 게이트 — CLAUDE.md §4.5/§4.6 준수를 기계로 강제한다.

지시(2026-08-01, 대표님): "위 방식을 운영규칙 훅 및 게이트 설치해"

무엇을 막는가
-------------
G1 파싱 우선(§4.6) — 빌드타임 해석이 규칙 역할로 AI 입력을 사전 축소하지
   않는다. 검측요청서처럼 전 칸이 관계자로 판정된 문서에서도 AI 는 칸을
   본다(행위 검증 — 소스 문자열 검사가 아니라 실제 호출 결과로 잰다).
G2 강등 두 신호(§4.6) — AI 단독 판정으로 입력칸을 죽이지 못한다.
G3 역할 교정 안전(§4.6) — 살아있는 서식·보호 구역(대장·증명발급)은
   역할을 바꾸지 못한다.
G4 값 미저장(§4) — 해석 캐시 산출물에 값(개인정보)이 들어가지 않는다.
G5 드라이 런 무기입(§4.5) — 드라이 런 경로가 HWPX 를 쓰지 않는다.
G6 어휘 동기 — 캐시가 쓰는 semantic 이 planner 어휘를 벗어나지 않는다.

사용
----
    python scripts/ops/gate_hwpx_ai_interpretation_pipeline.py
    (JSON 판정 출력 · 위반 시 종료코드 1)
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "hwpx"))

PASS_VERDICT = "PASS_HWPX_AI_INTERPRETATION_PIPELINE"
FAIL_VERDICT = "FAIL_HWPX_AI_INTERPRETATION_PIPELINE"


def _check(code: str, desc: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"code": code, "desc": desc,
            "status": "PASS" if ok else "FAIL",
            "detail": detail if not ok else ""}


def _doc_model() -> dict:
    """전 칸이 관계자로 판정된 문서를 본뜬 최소 모델(검측요청서 형상)."""
    return {
        "cells": [
            {"cellId": "cell_t_s0_000_r0_c0", "text": "검측부위"},
            {"cellId": "cell_t_s0_000_r0_c1", "text": ""},
            {"cellId": "cell_t_s0_000_r1_c0", "text": "검측요구일시"},
            {"cellId": "cell_t_s0_000_r1_c1", "text": ""},
        ],
        "paragraphs": [
            {"paragraphId": "par_b0_p0",
             "containerScope": {"kind": "block"},
             "runs": [{"text": "검측요청서"}]},
        ],
    }


def _all_office_inputs() -> list[dict]:
    return [
        {"label": "검측부위", "role": "office", "inputType": "text",
         "semantic": "", "subject": "self", "sensitive": False,
         "paragraphId": "par_t_s0_000_r0_c1_p0",
         "tableIndex": 0, "row": 0, "col": 1},
        {"label": "검측요구일시", "role": "office", "inputType": "text",
         "semantic": "", "subject": "self", "sensitive": False,
         "paragraphId": "par_t_s0_000_r1_c1_p0",
         "tableIndex": 0, "row": 1, "col": 1},
    ]


def run_gate() -> dict[str, Any]:
    from scripts.hwpx.web_office import build_ai_interpretation_cache as B
    from scripts.hwpx.web_office.ai_doc_context import build_context_fields
    from scripts.hwpx.web_office.ai_field_interpretation import (
        ALLOWED_SEMANTIC, interpret_fields, should_demote,
        should_promote_to_user)
    from scripts.hwpx.web_office.form_fill_planner import _PROMPT

    checks: list[dict[str, Any]] = []

    # ── G1 파싱 우선 ────────────────────────────────────────────
    seen = build_context_fields(_all_office_inputs(), _doc_model(),
                                title="검측요청서", roles=None)
    checks.append(_check(
        "G1a", "roles=None 이면 관계자 칸도 AI 가 본다",
        len(seen) == 2, f"AI 가 본 칸 {len(seen)} (기대 2)"))

    # 배치가 실제로 roles=None 을 넘기는가 — 호출부를 본다
    src = inspect.getsource(B.interpret_one)
    checks.append(_check(
        "G1b", "빌드타임 배치가 roles=None 으로 전 입력칸을 싣는다",
        "roles=None" in src,
        "build_ai_interpretation_cache.interpret_one 이 roles=None 미사용"))

    # 규칙 역할은 힌트로만 동승 — 필터가 아니다
    checks.append(_check(
        "G1c", "규칙 역할이 ruleRole 힌트로 동승한다",
        all(f.get("ruleRole") == "office" for f in seen),
        "ruleRole 힌트 누락"))

    # ── G2 강등 두 신호 ────────────────────────────────────────
    ai_alone = should_demote({"isInput": False, "confidence": 0.99,
                              "label": "검측부위"})
    both = should_demote({"isInput": False, "confidence": 0.9,
                          "label": "210mm×297mm(백상지 80g/m2)"})
    checks.append(_check(
        "G2a", "AI 단독 판정으로 입력칸을 죽이지 못한다",
        ai_alone is False, "정상 라벨이 AI 판정만으로 강등됨"))
    checks.append(_check(
        "G2b", "AI + 규칙이 합의하면 오염은 강등된다",
        both is True, "두 신호 합의에도 강등 안 됨"))

    # ── G3 역할 교정 안전 ──────────────────────────────────────
    live = should_promote_to_user(
        {"isInput": True, "filledBy": "작성자", "confidence": 0.99,
         "ruleRole": "office"},
        doc_type="신청신고", form_kind="민원신청", form_applicant_count=5)
    ledger = should_promote_to_user(
        {"isInput": True, "filledBy": "작성자", "confidence": 0.99,
         "ruleRole": "office"},
        doc_type="대장기록", form_kind="행정내부", form_applicant_count=0)
    dead = should_promote_to_user(
        {"isInput": True, "filledBy": "작성자", "confidence": 0.9,
         "ruleRole": "office"},
        doc_type="기타", form_kind="행정내부", form_applicant_count=0)
    checks.append(_check(
        "G3a", "살아있는 서식(신청인칸>0)의 역할은 못 바꾼다",
        live is False, "살아있는 서식이 교정 대상이 됨"))
    checks.append(_check(
        "G3b", "보호 구역(대장기록)은 못 바꾼다",
        ledger is False, "대장 안전규칙 위반"))
    checks.append(_check(
        "G3c", "죽은 업무문서는 되살린다",
        dead is True, "죽은 서식이 되살아나지 않음"))

    # ── G4 값 미저장 ───────────────────────────────────────────
    def _runner(prompt: str) -> str:
        return json.dumps([{
            "key": "par_t_s0_000_r0_c1_p0", "isInput": True,
            "filledBy": "작성자", "semantic": "", "meaning": "검측 부위",
            "profileKey": "", "question": "검측부위를 알려주세요",
            "confidence": 0.9,
            # 모델이 값을 실어 보내도 캐시에 들어가면 안 된다
            "value": "지하1층펌프실",
        }], ensure_ascii=False)

    out = interpret_fields(seen, runner=_runner)
    leaked = [r for r in out["interpretations"] if "value" in r]
    checks.append(_check(
        "G4", "해석 캐시 산출물에 값(개인정보)이 없다",
        not leaked, f"값 필드 유출 {len(leaked)}건"))

    # ── G5 드라이 런 무기입 ────────────────────────────────────
    dr_src = (ROOT / "scripts/hwpx/web_office/ai_fill_dry_run.py").read_text(
        encoding="utf-8")
    writes = [w for w in ("write_package", "write_xml", "fill_document_direct",
                          "apply_para_save_request", "shutil.copy")
              if w in dr_src]
    checks.append(_check(
        "G5", "드라이 런 경로가 HWPX 를 쓰지 않는다",
        not writes, f"쓰기 호출 발견: {writes}"))

    # ── G6 어휘 동기 ───────────────────────────────────────────
    checks.append(_check(
        "G6", "캐시 semantic 어휘가 planner 어휘를 포함한다",
        set(_PROMPT).issubset(ALLOWED_SEMANTIC),
        "planner 가 모르는 태그를 캐시가 쓸 수 있음"))

    failed = [c for c in checks if c["status"] != "PASS"]
    return {
        "schemaVersion": "hwpx_ai_interpretation_pipeline_gate_v1",
        "verdict": PASS_VERDICT if not failed else FAIL_VERDICT,
        "rules": ["CLAUDE.md §4.5", "CLAUDE.md §4.6"],
        "checksTotal": len(checks),
        "checksFailed": len(failed),
        "checks": checks,
        "failCodes": [c["code"] for c in failed],
    }


def main() -> int:
    result = run_gate()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == PASS_VERDICT else 1


if __name__ == "__main__":
    raise SystemExit(main())
