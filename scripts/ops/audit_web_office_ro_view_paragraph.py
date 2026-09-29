"""RO_VIEW_PARAGRAPH_01 감리 스크립트.

정적: ro_view_importer 가 writer/edit_plan/mutation API 토큰을 포함하지 않음
       + document_model 의 dataclass 변경이 containerScope 1개로 한정
       + 변경 금지 파일이 1a999e3 대비 무변경

동적: corpus.sqlite3 에서 fillable_form HWPX 3건 샘플링,
       import_hwpx_as_ro_view 호출 후 paragraphId/runId 중복 0,
       containerScope/charPr/parPr 발급률, 원본 sha 사전=사후 확인.

return {"verdict": "PASS"|"FAIL", "findings": [...], "summary": {...}}
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))
if str(PR / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(PR / "scripts/hwpx"))

from scripts.hwpx.web_office.render_payload import (  # ruff: ignore[module-import-not-at-top-of-file]
    build_render_payload,
)
from scripts.hwpx.web_office.ro_view_importer import (  # ruff: ignore[module-import-not-at-top-of-file]
    import_hwpx_as_ro_view,
)

FORBIDDEN_TOKENS_IMPORTER = (
    "apply_edit_plan",
    "hwpx_edit_tool",
    "set_table_cell_text",
    "write_package",
    "HwpxValidator",
    "EditCommand",
    "package.write_xml",
    "package.save",
)

PROTECTED_FILES = (
    "scripts/hwpx/hwpx_edit_tool.py",
    "scripts/hwpx/hwpx_writer_adapter.py",
    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01:
    # paragraph_writer_adapter.py 는 V4_CHARPR_PRESERVED 활성화 트리거
    # 발동에 따른 adapter applied metadata 보강 허용으로 본 목록에서
    # 제거됨 (허용 범위: applyCharPrIDRef + commandType 적재 한정).
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    # paragraph_save_verify7.py: PARA_INSERT 준공(bb0939b)에서 V8 추가로 제거됨
    "scripts/hwpx/web_office/paragraph_save_audit.py",
    # paragraph_edit_plan.py: CONTAINERSCOPE_BRIDGE_01 자진신고 해제 (target.containerScope 우선 분기)
    "scripts/hwpx/web_office/edit_command_model.py",
    # para_edit_model.py: CONTAINERSCOPE_BRIDGE_01 자진신고 해제 (containerScope 필드 추가)
    "scripts/hwpx/web_office/para_edit_normalizer.py",
)

BASELINE = "bb0939b"  # PARA_INSERT 준공 후 갱신 (2a0cde8 → bb0939b)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _resolve_fixtures(limit: int = 3) -> list[Path]:
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        return _resolve_checked_in_fixtures(limit)
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            """
            SELECT d.source_path FROM hwpx_documents d
            JOIN document_classifications c ON c.document_id=d.document_id
            WHERE d.inventory_status='FOUND'
              AND c.document_type='fillable_form'
              AND d.file_size BETWEEN 30000 AND 120000
            ORDER BY d.first_seen_at LIMIT ?
        """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    fixtures = [PR / r[0] for r in rows if (PR / r[0]).is_file()]
    if len(fixtures) >= limit:
        return fixtures[:limit]
    fallback = _resolve_checked_in_fixtures(limit)
    merged = list(dict.fromkeys(fixtures + fallback))
    return merged[:limit]


def _resolve_checked_in_fixtures(limit: int) -> list[Path]:
    fixture_dir = PR / "tests/fixtures/hwpx/corpus"
    if not fixture_dir.is_dir():
        return []
    fixtures = sorted(p for p in fixture_dir.glob("*.hwpx") if 30000 <= p.stat().st_size <= 120000)
    return fixtures[:limit]


def _static_checks(findings: list[dict]) -> None:
    importer_src = (PR / "scripts/hwpx/web_office/ro_view_importer.py").read_text(encoding="utf-8")
    findings.extend({
                "code": "FORBIDDEN_TOKEN_IN_IMPORTER",
                "token": tok,
            } for tok in FORBIDDEN_TOKENS_IMPORTER if tok in importer_src)

    # document_model: containerScope 필드 존재 + baseline 대비 추가 변경 없음
    doc_model_path = PR / "scripts/hwpx/web_office/document_model.py"
    if "containerScope" not in doc_model_path.read_text(encoding="utf-8"):
        findings.append({"code": "DOCUMENT_MODEL_CONTAINER_SCOPE_MISSING"})
    try:
        diff = subprocess.run(
            ["git", "diff", BASELINE, "--", "scripts/hwpx/web_office/document_model.py"],
            cwd=PR,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=20,
        )
        added = [
            ln for ln in diff.stdout.splitlines() if ln.startswith("+") and not ln.startswith("+++")
        ]
        added_non_blank = [ln for ln in added if ln.strip(" +")]
        if len(added_non_blank) > 2:
            findings.append({
                "code": "DOCUMENT_MODEL_DIFF_TOO_LARGE",
                "addedLines": len(added_non_blank),
            })
    except Exception as exc:  # ruff: ignore[blind-except] - git diff 실패 사유 무관, finding 으로 기록
        findings.append({"code": "GIT_DIFF_FAIL", "file": "document_model.py", "reason": str(exc)})

    # 변경 금지 파일 git diff baseline 0 줄
    for f in PROTECTED_FILES:
        try:
            out = subprocess.run(
                ["git", "diff", BASELINE, "--", f],
                cwd=PR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=20,
            )
            if out.stdout.strip():
                findings.append({
                    "code": "PROTECTED_FILE_MODIFIED",
                    "file": f,
                })
        except Exception as exc:  # ruff: ignore[blind-except] - git diff 실패 사유 무관, finding 으로 기록
            findings.append({"code": "GIT_DIFF_FAIL", "file": f, "reason": str(exc)})


def _process_fixture(f: Path) -> dict:
    sha_before = _sha(f)
    mt_before = f.stat().st_mtime_ns
    doc = import_hwpx_as_ro_view(f)
    sha_after = _sha(f)
    mt_after = f.stat().st_mtime_ns
    mutated = not (sha_before == sha_after and mt_before == mt_after)

    par_ids = [p.paragraphId for p in doc.paragraphs]
    run_ids = [r.runId for p in doc.paragraphs for r in p.runs]
    dup_par = len(par_ids) != len(set(par_ids))
    dup_run = len(run_ids) != len(set(run_ids))

    n_par = len(doc.paragraphs) or 1
    n_runs = sum(len(p.runs) for p in doc.paragraphs) or 1
    n_scope = sum(1 for p in doc.paragraphs if p.containerScope is not None)
    n_charpr = sum(1 for p in doc.paragraphs for r in p.runs if r.charPrIDRef)
    n_parpr = sum(1 for p in doc.paragraphs if p.parPrIDRef)

    # render payload paragraph 에 containerScope 키 존재 확인
    payload = build_render_payload(doc)
    # paragraph_index 는 직접 노출되지 않고 blocks/cells 에 매개됨.
    # block paragraph 에 대해 containerScope 키 존재 확인.
    missing_scope_block_id = None
    for blk in payload.get("blocks", []):
        if blk.get("type") == "paragraph" and "paragraph" in blk:
            if "containerScope" not in blk["paragraph"]:
                missing_scope_block_id = blk.get("blockId")
                break

    return {
        "mutated": mutated,
        "dup_par": dup_par,
        "dup_run": dup_run,
        "scope_rate": n_scope / n_par,
        "charpr_rate": n_charpr / n_runs,
        "parpr_rate": n_parpr / n_par,
        "missing_scope_block_id": missing_scope_block_id,
    }


def _append_aggregate_findings(
    findings: list[dict], dup_par: int, dup_run: int, sha_ok: int, total: int
) -> None:
    if dup_par:
        findings.append({"code": "PARAGRAPH_ID_DUP", "count": dup_par})
    if dup_run:
        findings.append({"code": "RUN_ID_DUP", "count": dup_run})
    if sha_ok != total:
        findings.append({"code": "SHA_PRESERVED_PARTIAL", "ok": sha_ok, "total": total})


def _dynamic_checks(findings: list[dict], summary: dict) -> None:
    fixtures = _resolve_fixtures(3)
    summary["sampleCount"] = len(fixtures)
    if len(fixtures) < 3:
        findings.append({"code": "INSUFFICIENT_FIXTURES", "available": len(fixtures)})
        return

    rates_scope: list[float] = []
    rates_charpr: list[float] = []
    rates_parpr: list[float] = []
    dup_par = 0
    dup_run = 0
    sha_ok = 0
    for f in fixtures:
        r = _process_fixture(f)
        if r["mutated"]:
            findings.append({"code": "ORIGINAL_HWPX_MUTATED", "file": f.name})
        else:
            sha_ok += 1
        if r["dup_par"]:
            dup_par += 1
        if r["dup_run"]:
            dup_run += 1
        rates_scope.append(r["scope_rate"])
        rates_charpr.append(r["charpr_rate"])
        rates_parpr.append(r["parpr_rate"])
        if r["missing_scope_block_id"] is not None:
            findings.append({
                "code": "RENDER_PAYLOAD_PARAGRAPH_MISSING_SCOPE",
                "file": f.name,
                "blockId": r["missing_scope_block_id"],
            })

    _append_aggregate_findings(findings, dup_par, dup_run, sha_ok, len(fixtures))

    def _avg(xs: list[float]) -> float:
        return round(sum(xs) / len(xs), 4) if xs else 0.0

    summary["containerScopeRate"] = _avg(rates_scope)
    summary["charPrIDRefRate"] = _avg(rates_charpr)
    summary["parPrIDRefRate"] = _avg(rates_parpr)
    summary["paragraphIdDupSamples"] = dup_par
    summary["runIdDupSamples"] = dup_run
    summary["shaPreservedAll"] = sha_ok == len(fixtures)


def audit() -> dict:
    findings: list[dict] = []
    summary: dict = {}
    _static_checks(findings)
    _dynamic_checks(findings, summary)
    verdict = "PASS" if not findings else "FAIL"
    return {"verdict": verdict, "findings": findings, "summary": summary, "baseline": BASELINE}


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
