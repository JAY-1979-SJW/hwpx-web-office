"""HWPX-API-CONTRACT-LOCK-01 — operations audit (준공검사).

E동(출입구) 규격서가 Java 측 contract와 동기화되었는지, 외부 호출자가
신뢰 가능한 형태인지 검증. PASS/WARN/FAIL.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def run_audit() -> dict:
    from scripts.hwpx.api_contract import editor_command_contract as cn

    findings: list[dict] = []

    def add(check: str, ok: bool, detail: object = "") -> None:
        findings.append({
            "check": check,
            "status": "PASS" if ok else "FAIL",
            "ok": bool(ok),
            "detail": detail,
        })

    # 1. 규격서 자체
    mod = PROJECT_ROOT / "scripts/hwpx/api_contract/editor_command_contract.py"
    add("contract_module_exists", mod.is_file(),
          str(mod.relative_to(PROJECT_ROOT)))
    add("contract_name_locked",
          cn.CONTRACT_NAME == "HWPX-API-CONTRACT-LOCK-01",
          cn.CONTRACT_NAME)
    add("15_command_types_locked", len(cn.ALLOWED_COMMAND_TYPES) == 15,
          {"count": len(cn.ALLOWED_COMMAND_TYPES),
            "types": sorted(cn.ALLOWED_COMMAND_TYPES)})

    # 2. envelope sanity
    valid_cmd = {
        "commandType": "validateDocument",
        "artifactId": "abc-123",
        "target": {}, "payload": {}, "dryRun": True,
    }
    add("valid_envelope_accepted",
          cn.validate_command(valid_cmd)["ok"],
          {"input": valid_cmd})

    # 3. 금지 필드
    bad = {"commandType": "validateDocument", "artifactId": "x",
              "credential": "secret"}
    errs = cn.validate_command(bad)["errors"]
    add("forbidden_field_blocked",
          any(e.startswith("FORBIDDEN_FIELD:credential") for e in errs),
          {"errors": errs})

    # 4. 모든 command별 build_command 성공
    samples = {
        "replaceText": (
            {"paragraphIndex": 0}, {"oldText": "a", "replacement": "b"}),
        "replacePlaceholder": ({}, {"key": "k", "value": "v"}),
        "updateTableCell": (
            {"tableIndex": 0, "row": 1, "col": 2}, {"value": "x"}),
        "addTableRow": ({"tableIndex": 0}, {"values": ["a"]}),
        "deleteTableRow": ({"tableIndex": 0, "row": 1}, {}),
        "validateDocument": ({}, {}),
        # V2 확장 9개
        "fillScheduleBars": (
            {"tableIndex": 0}, {"barPlan": [{"row": 1, "start": 1, "end": 5}]}),
        "buildMonthlyScheduleTable": (
            {"tableIndex": 0},
            {"items": [], "firstMonth": "2026-05", "monthCount": 3}),
        "buildDailyScheduleTable": (
            {"tableIndex": 0},
            {"items": [], "startDate": "2026-05-19", "dayCount": 7}),
        "mergeCells": (
            {"tableIndex": 0, "row": 1, "col": 2},
            {"rowSpan": 2, "colSpan": 1}),
        "splitCells": ({"tableIndex": 0, "row": 1, "col": 2}, {}),
        "setCellFill": (
            {"tableIndex": 0, "row": 1, "col": 2}, {"color": "#FFCC00"}),
        "applyStyleFromSource": (
            {"targetType": "cell"}, {"sourceRef": "src-cell-1"}),
        "autoFillFromAI": ({}, {"proposals": []}),
        "autoDetectInputSlots": ({}, {}),
    }
    build_ok: list[str] = []
    build_fail: list[str] = []
    for ct, (tgt, pl) in samples.items():
        try:
            cn.build_command(command_type=ct, artifact_id="a1",
                                target=tgt, payload=pl)
            build_ok.append(ct)
        except Exception as e:
            build_fail.append(f"{ct}:{e}")
    add("all_command_builders_succeed", not build_fail,
          {"ok": build_ok, "fail": build_fail})

    # 5. 응답 검증
    valid_resp = {
        "schemaVersion": "1.0", "engineVersion": "0.6.2",
        "artifactId": "a", "applied": False,
    }
    add("valid_response_accepted",
          cn.validate_response(valid_resp)["ok"],
          {"input": valid_resp})

    applied_no_output = {
        "schemaVersion": "1.0", "engineVersion": "0.6.2",
        "artifactId": "a", "applied": True,
    }
    add("applied_without_output_blocked",
          "APPLIED_WITHOUT_OUTPUT_ARTIFACT_ID" in
            cn.validate_response(applied_no_output)["errors"],
          {"errors": cn.validate_response(applied_no_output)["errors"]})

    # 6. Java contract 동기화
    sync = cn.check_python_java_sync()
    add("python_java_contract_synced", sync["ok"], sync)

    # 7. 방화구획
    iso = cn.audit_api_contract_isolation()
    add("production_import_isolation", iso["ok"], iso)

    # 8. 모듈 내 금지물
    src = mod.read_text(encoding="utf-8")
    bad_writer = ("GenericEditPlanWriter", "writer_executor",
                    "writer_adapter")
    add("no_writer_in_module",
          not any(n in src for n in bad_writer),
          {"checked": bad_writer})
    bad_ai = ("anthropic", "openai", "tesseract", "ANTHROPIC_API_KEY")
    add("no_ai_ocr_in_module",
          not any(n.lower() in src.lower() for n in bad_ai),
          {"checked": bad_ai})
    bad_secret = ("DATABASE_URL", "password=", "haehan-ai.pem")
    add("no_secret_in_module",
          not any(n in src for n in bad_secret),
          {"checked": bad_secret})

    # 9. 인접 동 (B, D) 호환
    try:
        from scripts.hwpx.recognition_corpus import (
            xml_deep_structure_analyzer, audit_learning_log_contract,
        )
        _ = (xml_deep_structure_analyzer, audit_learning_log_contract)
        add("adjacent_dong_compat", True, "B+D dong loadable")
    except Exception as e:
        add("adjacent_dong_compat", False, str(e))

    fails = [f for f in findings if f["status"] == "FAIL"]
    summary = {
        "verdict": "PASS" if not fails else "FAIL",
        "total": len(findings),
        "pass": sum(1 for f in findings if f["status"] == "PASS"),
        "fail": len(fails),
    }
    return {
        "auditName": "HWPX-API-CONTRACT-LOCK-01",
        "contractVersion": cn.CONTRACT_VERSION,
        "snapshot": cn.dump_contract_snapshot(),
        "summary": summary,
        "findings": findings,
    }


def main() -> int:
    report = run_audit()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["summary"]["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
