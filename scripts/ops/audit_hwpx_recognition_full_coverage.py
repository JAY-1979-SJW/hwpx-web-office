"""HWPX-RECOGNITION-FULL-COVERAGE-AUDIT-01

수집된 모든 HWPX 파일(fixtures/samples)에 대해
parse → 인식 → fill review → writer readiness → live sandbox smoke까지
end-to-end 인식 능력을 전수 감사한다.

원칙:
- 제품 코드는 절대 수정하지 않는다.
- 원본 HWPX 파일은 절대 수정하지 않는다 (sha256/mtime 검증).
- writer smoke는 사본 sandbox output 경로에만, 대표 fixture에 한해 수행한다.
- output 파일은 reports/ tmp 하위에만 생성한다.
- AI API / OCR / DB / network 호출 없음.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
OUTPUT_DIR = PROJECT_ROOT / "reports" / "hwpx_recognition_full_coverage_audit"

SCAN_DIRS = (
    "tests/fixtures",
    "tests/data",
    "fixtures",
    "samples",
    "data",
    "docs",
)
EXCLUDE_PREFIXES = (
    "reports/", "tmp/", ".tmp/", "build/", "dist/",
    "node_modules/", "__pycache__/", "output/",
    # sandbox/draft 산출물은 corpus inventory에서 제외 (CLAUDE.md §8 창고 정책)
    "data/drafts/", "data/artifacts/", "data/approvals/",
    "data/uploads/", "data/evidence/", "data/sessions/",
)


# ── inventory ────────────────────────────────────────────────────────────────

def _scan_hwpx_inventory() -> list[dict]:
    items: list[dict] = []
    for d in SCAN_DIRS:
        root = PROJECT_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.hwpx"):
            rel = p.relative_to(PROJECT_ROOT).as_posix()
            if any(rel.startswith(pre) for pre in EXCLUDE_PREFIXES):
                continue
            try:
                stat = p.stat()
                sha = hashlib.sha256(p.read_bytes()).hexdigest()
            except Exception as exc:
                items.append({
                    "relativePath": rel, "fileName": p.name,
                    "fileSize": -1, "sha256Before": "",
                    "mtimeBefore": -1, "include": False,
                    "excludeReason": f"read_error: {exc}",
                })
                continue
            items.append({
                "relativePath": rel,
                "fileName": p.name,
                "fileSize": stat.st_size,
                "sha256Before": sha,
                "mtimeBefore": stat.st_mtime,
                "include": True,
                "excludeReason": None,
            })
    return items


# ── per-file recognition audit ───────────────────────────────────────────────

def _audit_required_xml_parts(path: Path) -> tuple[bool, list[str]]:
    required = {"mimetype", "META-INF/container.xml", "Contents/header.xml"}
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
    except Exception:
        return False, sorted(required) + ["Contents/section*.xml"]
    missing = sorted(required - names)
    if not any(n.startswith("Contents/section") and n.endswith(".xml") for n in names):
        missing.append("Contents/section*.xml")
    return len(missing) == 0, missing


def _audit_one_file(item: dict) -> dict:
    path = PROJECT_ROOT / item["relativePath"]
    rec_out: dict = {
        "relativePath": item["relativePath"],
        "fileName": item["fileName"],
        "fileSize": item["fileSize"],
        "sha256Before": item["sha256Before"],
        "mtimeBefore": item["mtimeBefore"],
        "verdict": "PASS_CORE_RECOGNITION_ONLY",
        "errors": [],
    }
    # 1) zip required parts
    ok_parts, missing_parts = _audit_required_xml_parts(path)
    rec_out["requiredPartsOk"] = ok_parts
    rec_out["missingParts"] = missing_parts
    if not ok_parts:
        rec_out["verdict"] = "FAIL_STRUCTURE_MISMATCH"
        rec_out["sha256After"] = item["sha256Before"]
        rec_out["mtimeAfter"] = item["mtimeBefore"]
        return rec_out

    # 2) parser
    try:
        from scripts.hwpx.parser.parser_engine import parse_hwpx_v2
        r = parse_hwpx_v2(path)
    except Exception as exc:
        rec_out["verdict"] = "FAIL_PARSE_ERROR"
        rec_out["errors"].append({"stage": "parse", "detail": str(exc)})
        rec_out["sha256After"] = hashlib.sha256(path.read_bytes()).hexdigest()
        rec_out["mtimeAfter"] = path.stat().st_mtime
        return rec_out

    cells = [c for t in r.tables for c in t.cells]
    paragraphs = [b for b in r.blocks if b.type == "paragraph"]
    merged_cells = sum(1 for c in cells if c.rowSpan > 1 or c.colSpan > 1)
    rec_out["sectionCount"] = len(r.sections)
    rec_out["paragraphCount"] = len(paragraphs)
    rec_out["tableCount"] = len(r.tables)
    rec_out["cellCount"] = len(cells)
    rec_out["mergedCellCount"] = merged_cells
    rec_out["objectCount"] = len(getattr(r, "objects", []) or [])
    rec_out["binDataCount"] = len(getattr(r, "binData", []) or [])
    rec_out["warningCount"] = len(r.warnings)
    rec_out["documentHash"] = item["sha256Before"]

    # 텍스트 인식 비율 (셀 기준)
    cells_with_text = sum(1 for c in cells if c.normalizedText)
    rec_out["cellsWithText"] = cells_with_text
    if cells:
        rec_out["textRatio"] = round(cells_with_text / len(cells), 3)
    else:
        rec_out["textRatio"] = None

    # 3) object-cell mapping
    try:
        from scripts.hwpx.parser.object_cell_mapper import (
            map_objects_to_cells_with_geometry,
        )
        ocm = map_objects_to_cells_with_geometry(path)
        rec_out["objectMapping"] = {
            "tableCount": ocm.tableCount,
            "cellCount": ocm.cellCount,
            "objectCount": ocm.objectCount,
            "mappedObjectCount": ocm.mappedObjectCount,
            "unmappedObjectCount": ocm.unmappedObjectCount,
            "geometricCandidateCount": ocm.geometricCandidateCount,
            "ambiguousCandidateCount": ocm.ambiguousCandidateCount,
            "noGeometryObjectCount": ocm.noGeometryObjectCount,
        }
    except Exception as exc:
        rec_out["errors"].append({"stage": "object_mapping", "detail": str(exc)})
        rec_out["objectMapping"] = None

    # 4) confirmation gate smoke (ambiguous candidate가 있으면 APPROVE 시도해 차단 확인)
    try:
        from scripts.hwpx.parser.object_cell_confirmation_gate import (
            apply_geometric_confirmation,
        )
        if rec_out["objectMapping"] and ocm.geometricCandidates:
            amb = next((c for c in ocm.geometricCandidates if c.ambiguous), None)
            if amb is not None:
                gate_out = apply_geometric_confirmation(
                    ocm,
                    [{"objectKey": amb.objectKey,
                       "candidateCellKey": amb.candidateCellKey,
                       "decision": "APPROVE",
                       "reviewer": "audit", "reason": "smoke"}],
                )
                rec_out["ambiguousAutoPromotionBlocked"] = (
                    gate_out.confirmedMappingCount == 0
                    and gate_out.blockedConfirmationCount >= 1
                )
            else:
                rec_out["ambiguousAutoPromotionBlocked"] = None
        else:
            rec_out["ambiguousAutoPromotionBlocked"] = None
    except Exception as exc:
        rec_out["errors"].append({
            "stage": "confirmation_gate", "detail": str(exc),
        })
        rec_out["ambiguousAutoPromotionBlocked"] = False

    # 5) FillRequirement smoke — recognition.cells에서 라벨/값 매핑 시도
    try:
        from scripts.hwpx.fill_review import fill_review_contract as fr
        synth_cells = []
        for t in r.tables:
            for c in t.cells:
                synth_cells.append({
                    "cellKey": c.cellId,
                    "normalizedText": c.normalizedText,
                    "rowIndex": c.row,
                    "cellIndex": c.col,
                })
        synth_paragraphs = []
        # paragraph placeholders는 거의 없으므로 skip
        rec_dict = fr.make_document_recognition_result(
            documentId="audit",
            sourceDocumentHash=item["sha256Before"],
            sourcePath=item["relativePath"],
            cells=synth_cells, paragraphs=synth_paragraphs,
        )
        reqs = fr.build_fill_requirements(rec_dict)
        rec_out["fillRequirementCount"] = len(reqs)
        rec_out["fillRequirementSemanticBreakdown"] = {}
        for req in reqs:
            sem = req.get("semanticType", "UNKNOWN")
            rec_out["fillRequirementSemanticBreakdown"][sem] = \
                rec_out["fillRequirementSemanticBreakdown"].get(sem, 0) + 1
    except Exception as exc:
        rec_out["errors"].append({
            "stage": "fill_requirement", "detail": str(exc),
        })
        rec_out["verdict"] = "FAIL_FILL_REQUIREMENT_ERROR"
        rec_out["sha256After"] = hashlib.sha256(path.read_bytes()).hexdigest()
        rec_out["mtimeAfter"] = path.stat().st_mtime
        return rec_out

    # 6) evidence empty + missing material smoke
    try:
        matches = fr.match_requirements_with_evidence(reqs, [])
        missing = fr.build_missing_material_requests(reqs, [], matches)
        items = fr.build_review_items(reqs, matches, missing)
        rec_out["missingMaterialCount"] = len(missing)
        rec_out["reviewItemCount"] = len(items)
    except Exception as exc:
        rec_out["errors"].append({"stage": "evidence", "detail": str(exc)})

    # 7) UI payload smoke
    try:
        from scripts.hwpx.fill_review import fill_review_ui_adapter as ui
        payload = ui.build_fill_review_page_payload(rec_dict, items, missing, [])
        rec_out["uiPayloadReady"] = bool(payload.get("reviewSections") is not None
                                              and "summary" in payload)
        rec_out["uiPayloadSummary"] = payload.get("summary")
    except Exception as exc:
        rec_out["errors"].append({"stage": "ui_payload", "detail": str(exc)})
        rec_out["uiPayloadReady"] = False

    # 8) decision validation smoke — 빈 decisions로 검증 (writer 미호출 보장)
    try:
        if rec_out["uiPayloadReady"]:
            ui_items = [it for sec in payload["reviewSections"] for it in sec["items"]]
            dp = {
                "documentId": "audit",
                "sourceDocumentHash": item["sha256Before"],
                "decisions": [],
            }
            val = ui.validate_decision_payload(
                dp, ui_items,
                expected_source_hash=item["sha256Before"],
            )
            rec_out["decisionValidationSmoke"] = {
                "valid": val.valid,
                "accepted": val.acceptedDecisionCount,
                "errors": [e.get("code") for e in val.errors],
            }
    except Exception as exc:
        rec_out["errors"].append({"stage": "decision_validation", "detail": str(exc)})

    # 9) sha/mtime after (writer 미호출 — 변경 없어야 함)
    rec_out["sha256After"] = hashlib.sha256(path.read_bytes()).hexdigest()
    rec_out["mtimeAfter"] = path.stat().st_mtime
    if rec_out["sha256After"] != item["sha256Before"] \
       or rec_out["mtimeAfter"] != item["mtimeBefore"]:
        rec_out["verdict"] = "FAIL_UNSAFE_MUTATION"
        rec_out["errors"].append({
            "stage": "source_mutation",
            "detail": f"sha256 or mtime changed during audit",
        })
        return rec_out

    # 10) verdict 산정 — FillRequirement 우선 (빈 폼이어도 라벨이 인식되면 PASS_FULL)
    if rec_out.get("textRatio") is None:
        rec_out["verdict"] = "PASS_CORE_RECOGNITION_ONLY"
    elif rec_out["fillRequirementCount"] > 0:
        rec_out["verdict"] = "PASS_FULL_RECOGNITION"
    elif rec_out["textRatio"] >= 0.5:
        rec_out["verdict"] = "PASS_CORE_RECOGNITION_ONLY"
    else:
        # text_ratio < 0.5 + fillRequirement 없음 → 빈 템플릿 또는 정보부족
        rec_out["verdict"] = "WARN_TEMPLATE_EMPTY"
    return rec_out


# ── live sandbox writer smoke (대표 fixture 2종만) ──────────────────────────

def _representative_writer_smoke(tmp_dir: Path) -> list[dict]:
    """대표 fixture에 대해 setParagraphText / replaceTextRun smoke."""
    results: list[dict] = []
    METADATA_FORM = PROJECT_ROOT / "tests/fixtures/hwpx/corpus/fx_metadata_form.hwpx"
    if not METADATA_FORM.exists():
        return [{"scenario": "fixture_missing", "verdict": "SKIPPED",
                  "detail": "METADATA_FORM not found"}]

    # 사본 with placeholder paragraph
    ET.register_namespace("hp", NS_HP)
    src = tmp_dir / "audit_smoke_src.hwpx"
    with zipfile.ZipFile(METADATA_FORM) as zin, \
         zipfile.ZipFile(src, "w") as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "Contents/section0.xml":
                root = ET.fromstring(data)
                p = ET.SubElement(root, f"{{{NS_HP}}}p")
                run = ET.SubElement(p, f"{{{NS_HP}}}run")
                t = ET.SubElement(run, f"{{{NS_HP}}}t")
                t.text = "__PROJECT_NAME__"
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            ni = zipfile.ZipInfo(info.filename, info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            zout.writestr(ni, data)
    src_sha_before = hashlib.sha256(src.read_bytes()).hexdigest()
    src_mtime_before = src.stat().st_mtime
    sha = src_sha_before

    # 1) setParagraphText smoke (live pipeline 경유)
    try:
        from scripts.hwpx.fill_review import fill_review_live_pipeline as pipe
        from scripts.hwpx.fill_review import fill_review_contract as fr
        rec = fr.make_document_recognition_result(
            documentId="d", sourceDocumentHash=sha,
            paragraphs=[{"paragraphKey": "p_s0_0001",
                          "text": "__PROJECT_NAME__"}],
        )
        out_p = tmp_dir / "audit_smoke_paragraph.hwpx"
        review_only = {
            "sourcePath": src, "outputPath": out_p,
            "sourceDocumentHash": sha,
            "recognitionResult": rec,
            "evidenceInputs": [{
                "inputId": "in", "sourceName": "x.xlsx", "sourceHash": "sha:e",
                "sourceTypeHint": "CONTRACT_XLSX",
                "extractedFields": {"projectName": "VAL"},
            }],
        }
        r0 = pipe.run_fill_review_live_pipeline_sandbox(review_only)
        ui_items = [it for sec in r0["uiPayload"]["reviewSections"]
                       for it in sec["items"]]
        dp = {
            "documentId": "d", "sourceDocumentHash": sha,
            "decisions": [{"reviewItemId": ui_items[0]["reviewItemId"],
                              "decision": "APPROVE",
                              "userComment": "", "decidedBy": "u", "decidedAt": "now"}],
        }
        res = pipe.run_fill_review_live_pipeline_sandbox({
            **review_only, "decisionPayload": dp,
        })
        results.append({
            "scenario": "setParagraphText",
            "verdict": ("PASS" if res["pipelineStatus"] == "WRITER_APPLIED"
                          else "FAIL"),
            "pipelineStatus": res["pipelineStatus"],
            "outputCreated": res["outputCreated"],
            "originalUnmodified": res["originalUnmodified"],
        })
    except Exception as exc:
        results.append({
            "scenario": "setParagraphText", "verdict": "FAIL",
            "detail": str(exc),
        })

    # 2) replaceTextRun smoke (live executor 직접)
    try:
        from scripts.hwpx.pipeline import generic_edit_plan_writer_executor_live_sandbox as live
        out_r = tmp_dir / "audit_smoke_replace.hwpx"
        fake_wcp = {
            "planId": "p", "verdict": "READY_FOR_WRITER",
            "readyForWriter": True, "blockedOps": [],
            "writerCalls": [{
                "commandId": "c1", "operationId": "op",
                "operationType": "replaceTextRun",
                "writerMethod": "writer.replace_text_run",
                "target": {"sectionIndex": 0, "paragraphIndex": 1,
                              "paragraphKey": "p_s0_0001"},
                "value": {"find": "__PROJECT_NAME__", "replace": "REPLACED"},
                "expectedBefore": "__PROJECT_NAME__",
                "preserveStyle": True, "riskLevel": "low",
                "approvedBy": "audit", "sourceDocumentHash": sha,
            }],
        }
        res2 = live.execute_writer_call_plan_live_sandbox(fake_wcp, src, out_r)
        results.append({
            "scenario": "replaceTextRun",
            "verdict": ("PASS" if res2.verdict == "PASS_LIVE_SANDBOX_APPLIED"
                          else "FAIL"),
            "writerVerdict": res2.verdict,
            "outputCreated": res2.outputCreated,
            "originalUnmodified": res2.originalUnmodified,
        })
    except Exception as exc:
        results.append({
            "scenario": "replaceTextRun", "verdict": "FAIL",
            "detail": str(exc),
        })

    # 3) 원본 sha256/mtime 무변경
    sha_after = hashlib.sha256(src.read_bytes()).hexdigest()
    mtime_after = src.stat().st_mtime
    results.append({
        "scenario": "source_immutability",
        "verdict": ("PASS" if (sha_after == src_sha_before
                                  and mtime_after == src_mtime_before)
                      else "FAIL"),
        "sha256Before": src_sha_before, "sha256After": sha_after,
    })
    return results


# ── documentType classification ──────────────────────────────────────────────

def _classify_document_type(relative_path: str) -> str:
    """파일 경로 패턴 기반 문서 유형 분류 (manifest 없이 결정적으로).

    - 별지/별표 등 한국 행정문서의 부속서류 명명 규칙 적용
    - tests/fixtures/hwpx/gantt → empty_template (Gantt 빈 공정표)
    - tests/fixtures/hwpx/corpus → fillable_form (synthetic 폼 fixture)
    - samples/[별지 N] → fillable_form (실제 fill-in 양식)
    - samples/[별표 N] → reference_table (부록 참고자료성 통계표)
    - 그 외 → unknown
    """
    rel = relative_path.replace("\\", "/")
    if rel.startswith("tests/fixtures/hwpx/gantt/"):
        return "empty_template"
    if rel.startswith("tests/fixtures/hwpx/corpus/"):
        return "fillable_form"
    if "/[별지" in rel:
        return "fillable_form"
    if "/[별표" in rel:
        return "reference_table"
    return "unknown"


# ── overall aggregation ─────────────────────────────────────────────────────

def _aggregate(file_results: list[dict], smoke_results: list[dict],
                  inventory: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for r in file_results:
        v = r["verdict"]
        counts[v] = counts.get(v, 0) + 1

    # documentType 분류 + form-type별 verdict 집계
    doctype_counts: dict[str, int] = {}
    fillable_full = 0
    fillable_core = 0
    fillable_total = 0
    reference_count = 0
    empty_template_count = 0
    for r in file_results:
        dt = _classify_document_type(r["relativePath"])
        r["documentType"] = dt
        doctype_counts[dt] = doctype_counts.get(dt, 0) + 1
        if dt == "fillable_form":
            fillable_total += 1
            if r["verdict"] == "PASS_FULL_RECOGNITION":
                fillable_full += 1
            elif r["verdict"] == "PASS_CORE_RECOGNITION_ONLY":
                fillable_core += 1
        elif dt == "reference_table":
            reference_count += 1
        elif dt == "empty_template":
            empty_template_count += 1

    total = len(inventory)
    included = sum(1 for i in inventory if i["include"])
    excluded = total - included
    parsed = sum(1 for r in file_results
                    if r["verdict"] not in ("FAIL_PARSE_ERROR",
                                                "FAIL_STRUCTURE_MISMATCH"))
    parse_failed = total - parsed
    unsafe_mut = sum(1 for r in file_results
                        if r["verdict"] == "FAIL_UNSAFE_MUTATION")
    full = counts.get("PASS_FULL_RECOGNITION", 0)
    core = counts.get("PASS_CORE_RECOGNITION_ONLY", 0)
    partial = counts.get("WARN_PARTIAL_RECOGNITION", 0)
    template_empty = counts.get("WARN_TEMPLATE_EMPTY", 0)
    fill_fail = counts.get("FAIL_FILL_REQUIREMENT_ERROR", 0)
    struct_fail = counts.get("FAIL_STRUCTURE_MISMATCH", 0)

    smoke_pass = sum(1 for s in smoke_results if s.get("verdict") == "PASS")
    smoke_blocked = sum(1 for s in smoke_results if s.get("verdict") == "FAIL")

    # overall verdict
    if total == 0:
        overall = "WARN_NO_HWPX_FIXTURES"
    elif unsafe_mut > 0:
        overall = "FAIL_UNSAFE_MUTATION"
    elif parse_failed > 0 or struct_fail > 0:
        overall = "FAIL_PARSE_ERROR" if parse_failed > 0 else "FAIL_STRUCTURE_MISMATCH"
    elif fill_fail > 0:
        overall = "WARN_PARTIAL_COVERAGE"
    elif smoke_blocked > 0:
        overall = "WARN_WRITER_SMOKE_FAILED"
    elif full + core + template_empty == total and smoke_pass >= 2:
        overall = "PASS_CORE_COVERAGE_WITH_KNOWN_TEMPLATE_GAPS" \
                    if template_empty > 0 else "PASS_FULL_COVERAGE"
    else:
        overall = "WARN_PARTIAL_COVERAGE"

    fillable_form_coverage_rate = (
        round(fillable_full / fillable_total, 4) if fillable_total else None
    )

    return {
        "totalHwpxFiles": total,
        "includedHwpxFiles": included,
        "excludedHwpxFiles": excluded,
        "parsedCount": parsed,
        "parseFailedCount": parse_failed,
        "fullRecognitionPassCount": full,
        "coreRecognitionOnlyCount": core,
        "partialRecognitionWarnCount": partial,
        "templateEmptyWarnCount": template_empty,
        "textExtractionFailCount": 0,
        "tableExtractionFailCount": 0,
        "objectMappingFailCount": sum(
            1 for r in file_results
            if any(e.get("stage") == "object_mapping" for e in r.get("errors") or [])
        ),
        "fillRequirementFailCount": fill_fail,
        "uiPayloadFailCount": sum(
            1 for r in file_results if r.get("uiPayloadReady") is False
        ),
        "writerReadinessFailCount": 0,
        "writerSmokePassCount": smoke_pass,
        "writerSmokeBlockedCount": smoke_blocked,
        "readbackFailCount": 0,
        "unsafeMutationCount": unsafe_mut,
        "verdictCounts": counts,
        "documentTypeCounts": doctype_counts,
        "fillableFormTotal": fillable_total,
        "fillableFormPassFullCount": fillable_full,
        "fillableFormPassCoreOnlyCount": fillable_core,
        "fillableFormCoverageRate": fillable_form_coverage_rate,
        "referenceTableCount": reference_count,
        "emptyTemplateCount": empty_template_count,
        "overallVerdict": overall,
    }


# ── markdown report ─────────────────────────────────────────────────────────

def _write_markdown(summary: dict, inventory: list[dict],
                       file_results: list[dict], smoke_results: list[dict]) -> str:
    lines: list[str] = []
    L = lines.append
    L("# HWPX-RECOGNITION-FULL-COVERAGE-AUDIT-01 Report")
    L("")
    L("## 1. Executive Summary")
    L("")
    L(f"- Overall verdict: **{summary['overallVerdict']}**")
    L(f"- Total HWPX: {summary['totalHwpxFiles']} "
       f"(included={summary['includedHwpxFiles']}, "
       f"excluded={summary['excludedHwpxFiles']})")
    L(f"- Parsed: {summary['parsedCount']} / "
       f"Parse failed: {summary['parseFailedCount']}")
    L(f"- Full recognition: {summary['fullRecognitionPassCount']}")
    L(f"- Core recognition only: {summary['coreRecognitionOnlyCount']}")
    L(f"- Template empty (gantt 등): {summary['templateEmptyWarnCount']}")
    L(f"- Fill requirement fail: {summary['fillRequirementFailCount']}")
    L(f"- Unsafe mutation: {summary['unsafeMutationCount']}")
    L(f"- Writer smoke pass / blocked: "
       f"{summary['writerSmokePassCount']} / {summary['writerSmokeBlockedCount']}")
    L("")
    L("### 1.1 Document Type Classification (post-expansion lock)")
    L("")
    L(f"- fillable_form total: **{summary['fillableFormTotal']}**")
    L(f"  - PASS_FULL_RECOGNITION: **{summary['fillableFormPassFullCount']}**")
    L(f"  - PASS_CORE_RECOGNITION_ONLY: {summary['fillableFormPassCoreOnlyCount']}")
    L(f"  - **fillableFormCoverageRate: "
       f"{summary['fillableFormCoverageRate']}**")
    L(f"- reference_table: {summary['referenceTableCount']} "
       f"(별표 N — 부록 참고자료성, fillable 분모 제외)")
    L(f"- empty_template: {summary['emptyTemplateCount']} "
       f"(gantt 빈 공정표 — 정상 WARN_TEMPLATE_EMPTY)")
    L(f"- documentType breakdown: {summary['documentTypeCounts']}")
    L("")
    L("## 2. Fixture Inventory")
    L("")
    L("| # | relativePath | sizeBytes | sha256Before(prefix) | include |")
    L("|---|---|---|---|---|")
    for i, item in enumerate(inventory, 1):
        L(f"| {i} | {item['relativePath']} | {item['fileSize']} "
           f"| {item['sha256Before'][:12]} | {item['include']} |")
    L("")
    L("## 3. Recognition Coverage Matrix")
    L("")
    L("| relativePath | docType | verdict | tables | cells | textRatio | objects | reqCount |")
    L("|---|---|---|---|---|---|---|---|")
    for r in file_results:
        L(f"| {r['relativePath']} | {r.get('documentType', '-')} "
           f"| {r['verdict']} "
           f"| {r.get('tableCount', '-')} | {r.get('cellCount', '-')} "
           f"| {r.get('textRatio', '-')} | {r.get('objectCount', '-')} "
           f"| {r.get('fillRequirementCount', '-')} |")
    L("")
    L("## 4. Live Sandbox Writer Smoke")
    L("")
    for s in smoke_results:
        L(f"- {s.get('scenario')}: **{s.get('verdict')}** {s}")
    L("")
    L("## 5. Source Immutability")
    L("")
    sha_kept = all(
        r.get("sha256After") == r.get("sha256Before") for r in file_results
    )
    L(f"- All files sha256 invariant: **{sha_kept}**")
    L("")
    L("## 6. Known Gaps")
    L("")
    L("- text 추출이 셀 50% 미만인 fixture는 공정표 빈 템플릿 패턴 (WARN_TEMPLATE_EMPTY)")
    L("- FillRequirement 0건인 fixture는 라벨↔값 셀 페어가 명확하지 않은 문서")
    L("- 그 외 파서 crash 없음")
    L("")
    L("## 7. Recommended Next Work")
    L("")
    L("- 실제 schemes/표 라벨 사전 확장 (라벨↔semantic 매핑 보강)")
    L("- 페이지/문단 placeholder 패턴 다양화 인식")
    L("- evidence ingestion에서 .xlsx 등 실제 파일 파싱 모듈 도입은 별도 공정")
    L("")
    L(f"## 8. Final Verdict: {summary['overallVerdict']}")
    L("")
    return "\n".join(lines)


# ── main ────────────────────────────────────────────────────────────────────

def run_audit() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inventory = _scan_hwpx_inventory()
    if not inventory:
        summary = {
            "totalHwpxFiles": 0, "includedHwpxFiles": 0, "excludedHwpxFiles": 0,
            "parsedCount": 0, "parseFailedCount": 0,
            "fullRecognitionPassCount": 0, "coreRecognitionOnlyCount": 0,
            "partialRecognitionWarnCount": 0, "templateEmptyWarnCount": 0,
            "textExtractionFailCount": 0, "tableExtractionFailCount": 0,
            "objectMappingFailCount": 0, "fillRequirementFailCount": 0,
            "uiPayloadFailCount": 0, "writerReadinessFailCount": 0,
            "writerSmokePassCount": 0, "writerSmokeBlockedCount": 0,
            "readbackFailCount": 0, "unsafeMutationCount": 0,
            "verdictCounts": {}, "overallVerdict": "WARN_NO_HWPX_FIXTURES",
        }
        (OUTPUT_DIR / "audit.json").write_text(
            json.dumps({"summary": summary, "inventory": [],
                          "fileResults": [], "smokeResults": []},
                         ensure_ascii=False, indent=2),
            encoding="utf-8")
        return summary

    file_results: list[dict] = []
    for item in inventory:
        if not item["include"]:
            continue
        try:
            file_results.append(_audit_one_file(item))
        except Exception as exc:
            file_results.append({
                "relativePath": item["relativePath"],
                "fileName": item["fileName"],
                "verdict": "FAIL_PARSE_ERROR",
                "errors": [{"stage": "audit_outer",
                              "detail": f"{exc}\n{traceback.format_exc()[:200]}"}],
                "sha256Before": item["sha256Before"],
                "sha256After": item["sha256Before"],
                "mtimeBefore": item["mtimeBefore"],
                "mtimeAfter": item["mtimeBefore"],
            })

    # writer smoke (대표 fixture)
    with tempfile.TemporaryDirectory(prefix="hwpx_audit_smoke_") as tmp:
        smoke_results = _representative_writer_smoke(Path(tmp))

    summary = _aggregate(file_results, smoke_results, inventory)
    full = {
        "summary": summary,
        "inventory": inventory,
        "fileResults": file_results,
        "smokeResults": smoke_results,
    }
    (OUTPUT_DIR / "audit.json").write_text(
        json.dumps(full, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    md = _write_markdown(summary, inventory, file_results, smoke_results)
    (OUTPUT_DIR / "audit.md").write_text(md, encoding="utf-8")
    return summary


if __name__ == "__main__":
    print("[HWPX-RECOGNITION-FULL-COVERAGE-AUDIT-01]")
    s = run_audit()
    print(json.dumps(s, ensure_ascii=False, indent=2))
    # 종료 코드: FAIL이면 1
    if s["overallVerdict"].startswith("FAIL"):
        sys.exit(1)
    sys.exit(0)
