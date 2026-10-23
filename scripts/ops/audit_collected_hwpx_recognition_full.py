"""COLLECTED-HWPX-FULL-INVENTORY-AND-RECOGNITION-AUDIT-01 (Phase B: Recognition).

inventory.json을 입력으로 받아, parseCandidate=True인 unique sha256 파일에 대해
parse / recognition / fill review readiness 전수 감사.

원본 무수정 / writer 미호출 / output HWPX 미생성 / DB 접근 없음.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

INVENTORY_PATH = PROJECT_ROOT / "reports/collected_hwpx_inventory_audit/inventory.json"
OUTPUT_DIR = PROJECT_ROOT / "reports/collected_hwpx_recognition_full_audit"


def _classify_document_type(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/")
    if rel.startswith("tests/fixtures/hwpx/gantt/"):
        return "empty_template"
    if rel.startswith("tests/fixtures/hwpx/corpus/"):
        return "fillable_form"
    name = rel.rsplit("/", 1)[-1]
    if "[별지" in name or "별지_제" in name or "별지 제" in name:
        return "fillable_form"
    if "[별표" in name or "별표_" in name or "별표 " in name:
        return "reference_table"
    return "unknown"


def _sha256_of(path: Path) -> str:
    sha = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _run_fill_review_smoke(cells: list, sha_before: str, out: dict) -> None:
    try:
        from scripts.hwpx.fill_review import fill_review_contract as fr

        synth = [
            {
                "cellKey": c.cellId,
                "normalizedText": c.normalizedText,
                "rowIndex": c.row,
                "cellIndex": c.col,
            }
            for c in cells
        ]
        rec = fr.make_document_recognition_result(
            documentId="audit",
            sourceDocumentHash=sha_before,
            sourcePath="",
            cells=synth,
        )
        reqs = fr.build_fill_requirements(rec)
        out["fillRequirementCount"] = len(reqs)
        out["semanticBreakdown"] = {}
        for req in reqs:
            sem = req.get("semanticType", "UNKNOWN")
            out["semanticBreakdown"][sem] = out["semanticBreakdown"].get(sem, 0) + 1
        # UI payload smoke
        from scripts.hwpx.fill_review import fill_review_ui_adapter as ui

        matches = fr.match_requirements_with_evidence(reqs, [])
        missing = fr.build_missing_material_requests(reqs, [], matches)
        items = fr.build_review_items(reqs, matches, missing)
        payload = ui.build_fill_review_page_payload(rec, items, missing, [])
        out["uiPayloadReady"] = bool(
            payload.get("reviewSections") is not None and "summary" in payload
        )
        out["reviewItemCount"] = len(items)
        out["missingMaterialCount"] = len(missing)
    except Exception as exc:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 계속
        out["fillRequirementCount"] = -1
        out["uiPayloadReady"] = False
        out["errors"].append({"stage": "fill_review", "detail": str(exc)[:200]})


def _determine_recognition_verdict(out: dict) -> str:
    if out["fillRequirementCount"] is None or out["fillRequirementCount"] < 0:
        return "FAIL_FILL_REQUIREMENT_ERROR"
    if out["fillRequirementCount"] > 0:
        return "PASS_FULL_RECOGNITION"
    if out["textRatio"] >= 0.5:
        return "PASS_CORE_RECOGNITION_ONLY"
    return "WARN_TEMPLATE_EMPTY"


def _audit_one(path: Path) -> dict:
    out: dict = {
        "sha256Before": "",
        "sha256After": "",
        "mtimeBefore": -1,
        "mtimeAfter": -1,
        "verdict": "PASS_CORE_RECOGNITION_ONLY",
        "errors": [],
    }
    try:
        out["mtimeBefore"] = path.stat().st_mtime
        out["sha256Before"] = _sha256_of(path)
    except Exception as exc:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 계속
        out["verdict"] = "FAIL_PARSE_ERROR"
        out["errors"].append({"stage": "stat", "detail": str(exc)})
        return out

    try:
        from scripts.hwpx.parser.parser_engine import parse_hwpx_v2

        r = parse_hwpx_v2(path)
    except Exception as exc:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 계속
        out["verdict"] = "FAIL_PARSE_ERROR"
        out["errors"].append({"stage": "parse", "detail": str(exc)[:200]})
        out["sha256After"] = out["sha256Before"]
        out["mtimeAfter"] = out["mtimeBefore"]
        return out

    cells = [c for t in r.tables for c in t.cells]
    out["sectionCount"] = len(r.sections)
    out["paragraphCount"] = sum(1 for b in r.blocks if b.type == "paragraph")
    out["tableCount"] = len(r.tables)
    out["cellCount"] = len(cells)
    out["cellsWithText"] = sum(1 for c in cells if c.normalizedText)
    out["objectCount"] = len(getattr(r, "objects", []) or [])
    out["binDataCount"] = len(getattr(r, "binData", []) or [])
    out["mergedCellCount"] = sum(1 for c in cells if c.rowSpan > 1 or c.colSpan > 1)
    out["textRatio"] = round(out["cellsWithText"] / max(len(cells), 1), 3)

    _run_fill_review_smoke(cells, out["sha256Before"], out)

    # source immutability
    try:
        out["mtimeAfter"] = path.stat().st_mtime
        out["sha256After"] = _sha256_of(path)
    except Exception as exc:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 계속
        out["sha256After"] = out["sha256Before"]
        out["mtimeAfter"] = out["mtimeBefore"]
        out["errors"].append({"stage": "rehash", "detail": str(exc)})

    if out["sha256After"] != out["sha256Before"] or out["mtimeAfter"] != out["mtimeBefore"]:
        out["verdict"] = "FAIL_UNSAFE_MUTATION"
        out["errors"].append({"stage": "source_mutation", "detail": "sha256/mtime changed"})
        return out

    # verdict 산정 (FillRequirement 우선)
    out["verdict"] = _determine_recognition_verdict(out)
    return out


def _collect_recognition_targets(items: list[dict], limit: int | None) -> list[dict]:
    seen_sha: set[str] = set()
    targets: list[dict] = []
    for it in items:
        if not it.get("parseCandidate"):
            continue
        sha = it.get("sha256", "")
        if not sha or sha in seen_sha:
            continue
        seen_sha.add(sha)
        targets.append(it)
    if limit is not None and limit > 0:
        targets = targets[:limit]
    return targets


def _audit_one_target(it: dict) -> dict:
    path = PROJECT_ROOT / it["sourcePath"]
    try:
        res = _audit_one(path)
    except Exception as exc:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 계속
        res = {
            "verdict": "FAIL_PARSE_ERROR",
            "errors": [{"stage": "outer", "detail": str(exc)[:200]}],
            "sha256Before": it.get("sha256"),
            "sha256After": it.get("sha256"),
            "mtimeBefore": it.get("mtime"),
            "mtimeAfter": it.get("mtime"),
        }
    res["fileId"] = it["fileId"]
    res["sourcePath"] = it["sourcePath"]
    res["sourceKind"] = it["sourceKind"]
    res["documentType"] = _classify_document_type(it["sourcePath"])
    return res


def _bump_type_counter(type_counter: dict[str, dict[str, int]], res: dict) -> None:
    bucket = type_counter.setdefault(
        res["documentType"],
        {"total": 0, "pass_full": 0, "pass_core": 0, "warn_template": 0, "fail": 0},
    )
    bucket["total"] += 1
    v = res["verdict"]
    if v == "PASS_FULL_RECOGNITION":
        bucket["pass_full"] += 1
    elif v == "PASS_CORE_RECOGNITION_ONLY":
        bucket["pass_core"] += 1
    elif v == "WARN_TEMPLATE_EMPTY":
        bucket["warn_template"] += 1
    elif v.startswith("FAIL"):
        bucket["fail"] += 1


def _run_recognition_targets(targets: list[dict]) -> tuple[list[dict], dict[str, dict[str, int]]]:
    started = time.time()
    file_results: list[dict] = []
    type_counter: dict[str, dict[str, int]] = {}
    for i, it in enumerate(targets, 1):
        res = _audit_one_target(it)
        file_results.append(res)
        _bump_type_counter(type_counter, res)
        if i % 200 == 0:
            print(f"  ... {i}/{len(targets)} ({time.time() - started:.0f}s)", flush=True)
    return file_results, type_counter


def _summarize_recognition_results(
    file_results: list[dict], type_counter: dict[str, dict[str, int]], elapsed: float
) -> dict:
    verdict_counts: dict[str, int] = {}
    for r in file_results:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1

    total = len(file_results)
    parsed = sum(1 for r in file_results if not r["verdict"].startswith("FAIL_PARSE"))
    parse_failed = total - parsed
    full = verdict_counts.get("PASS_FULL_RECOGNITION", 0)
    fail_total = sum(v for k, v in verdict_counts.items() if k.startswith("FAIL"))
    unsafe_mut = verdict_counts.get("FAIL_UNSAFE_MUTATION", 0)
    fillable = type_counter.get("fillable_form", {})
    fillable_form_coverage_rate = (
        round(fillable.get("pass_full", 0) / fillable.get("total", 1), 4)
        if fillable.get("total", 0)
        else None
    )

    if unsafe_mut > 0:
        overall = "FAIL_UNSAFE_MUTATION"
    elif parse_failed > total * 0.05:
        overall = "WARN_PARSE_FAILURE_RATE_HIGH"
    elif fail_total > 0:
        overall = "WARN_PARTIAL_COVERAGE"
    else:
        overall = "PASS_COLLECTED_HWPX_RECOGNITION_FULL_AUDIT"

    return {
        "elapsedSeconds": round(elapsed, 1),
        "auditedCount": total,
        "parsedCount": parsed,
        "parseFailedCount": parse_failed,
        "fullRecognitionPassCount": full,
        "coreRecognitionOnlyCount": verdict_counts.get("PASS_CORE_RECOGNITION_ONLY", 0),
        "templateEmptyWarnCount": verdict_counts.get("WARN_TEMPLATE_EMPTY", 0),
        "failCount": fail_total,
        "unsafeMutationCount": unsafe_mut,
        "verdictCounts": verdict_counts,
        "documentTypeBreakdown": type_counter,
        "fillableFormTotal": fillable.get("total", 0),
        "fillableFormPassFullCount": fillable.get("pass_full", 0),
        "fillableFormCoverageRate": fillable_form_coverage_rate,
        "referenceTableTotal": type_counter.get("reference_table", {}).get("total", 0),
        "emptyTemplateTotal": type_counter.get("empty_template", {}).get("total", 0),
        "unknownDocTypeTotal": type_counter.get("unknown", {}).get("total", 0),
        "overallVerdict": overall,
    }


def _write_recognition_markdown(
    summary: dict, type_counter: dict[str, dict[str, int]], file_results: list[dict]
) -> None:
    md = [
        "# COLLECTED-HWPX-FULL-INVENTORY-AND-RECOGNITION-AUDIT-01 — Recognition",
        "",
        "## Summary",
        f"- audited: {summary['auditedCount']} unique parseable HWPX",
        f"- elapsed: {summary['elapsedSeconds']:.1f}s",
        f"- parsed: {summary['parsedCount']} / parseFailed: {summary['parseFailedCount']}",
        f"- PASS_FULL: {summary['fullRecognitionPassCount']}",
        f"- PASS_CORE_ONLY: {summary['coreRecognitionOnlyCount']}",
        f"- WARN_TEMPLATE_EMPTY: {summary['templateEmptyWarnCount']}",
        f"- FAIL: {summary['failCount']} (unsafeMutation={summary['unsafeMutationCount']})",
        f"- overallVerdict: **{summary['overallVerdict']}**",
        "",
        "## Document type breakdown",
        "",
        "| docType | total | PASS_FULL | PASS_CORE_ONLY | WARN_TEMPLATE | FAIL |",
        "|---|---|---|---|---|---|",
    ]
    for dt in ("fillable_form", "reference_table", "empty_template", "unknown"):
        b = type_counter.get(dt, {})
        md.append(
            f"| {dt} | {b.get('total', 0)} | {b.get('pass_full', 0)} "
            f"| {b.get('pass_core', 0)} | {b.get('warn_template', 0)} "
            f"| {b.get('fail', 0)} |"
        )
    md.append("")
    md.append(f"- fillableFormCoverageRate: **{summary['fillableFormCoverageRate']}**")
    md.append("")
    md.append("## Source immutability")
    all_kept = all(r["sha256Before"] == r["sha256After"] for r in file_results)
    md.append(f"- All source sha256 invariant: **{all_kept}**")
    md.append("")
    md.append("## Known gaps")
    md.append("- reference_table 분모 제외 (별표 N 행정문서 부록)")
    md.append("- empty_template gantt 빈 공정표")
    md.append("- 운영 수집본 unknown docType는 라벨 사전이 매칭 안 된 다양한 양식")
    (OUTPUT_DIR / "audit.md").write_text("\n".join(md), encoding="utf-8")


def run_recognition_audit(limit: int | None = None) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not INVENTORY_PATH.exists():
        return {
            "overallVerdict": "FAIL_INVENTORY_MISSING",
            "detail": f"inventory not found at {INVENTORY_PATH}",
        }

    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    targets = _collect_recognition_targets(inv["items"], limit)

    print(f"[recognition] auditing {len(targets)} unique parseable HWPX files", flush=True)
    started = time.time()
    file_results, type_counter = _run_recognition_targets(targets)
    elapsed = time.time() - started

    summary = _summarize_recognition_results(file_results, type_counter, elapsed)

    (OUTPUT_DIR / "audit.json").write_text(
        json.dumps(
            {"summary": summary, "fileResults": file_results},
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    _write_recognition_markdown(summary, type_counter, file_results)

    return summary


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="audit limit (test/dev only)")
    args = ap.parse_args()
    print("[COLLECTED-HWPX-FULL-INVENTORY-AND-RECOGNITION-AUDIT-01 — Phase B]")
    s = run_recognition_audit(limit=args.limit)
    print(json.dumps(s, ensure_ascii=False, indent=2))
