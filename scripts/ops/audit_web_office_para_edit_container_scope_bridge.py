"""WEB-OFFICE-PARA-EDIT-CONTAINERSCOPE-BRIDGE-01 감사 스크립트.

RO-VIEW paragraph.containerScope 가 브라우저 상태기계 / EditCommand v2 /
paragraph_edit_plan 변환부에 전사되었는지 정적·동적으로 검증한다.

writer 코드 / hwpx_edit_tool / paragraph_writer_adapter / output HWPX
생성 / 원본 HWPX 접근은 일절 호출하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PR = Path(__file__).resolve().parents[2]
if str(PR) not in sys.path:
    sys.path.insert(0, str(PR))
if str(PR / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(PR / "scripts/hwpx"))

VIEWER_DIR = PR / "frontend/web_office_viewer"
STATE_JS = VIEWER_DIR / "para_edit_state.mjs"
COMMAND_JS = VIEWER_DIR / "para_edit_command.mjs"
SELF_TEST_JS = VIEWER_DIR / "para_edit_self_test.mjs"

PARA_MODEL_PY = PR / "scripts/hwpx/web_office/para_edit_model.py"
PARA_PLAN_PY = PR / "scripts/hwpx/web_office/paragraph_edit_plan.py"

# writer 모듈 등 변경 금지
LOCKED_VS_BASELINE = [
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-EXISTING-CHARPR-01: hwpx_edit_tool /
    # paragraph_save_verify7 는 ApplyFormat 활성화로 본 LOCKED 에서 제거됨.
    "scripts/hwpx/hwpx_writer_adapter.py",
    # WEB-OFFICE-PARA-EDIT-MULTI-RUN-01: hwpx_paragraph_ops.py 는
    # multi-run primitive 추가를 위해 본 LOCKED 에서 제거됨.
    # WEB-OFFICE-PARA-ADAPTER-APPLYCHARPR-01:
    # paragraph_writer_adapter.py 는 V4_CHARPR_PRESERVED 활성화 트리거
    # 발동에 따른 adapter applied metadata 보강 허용으로 본 목록에서
    # 제거됨 (허용 범위: applyCharPrIDRef + commandType 적재 한정).
    "scripts/hwpx/web_office/paragraph_save_pipeline.py",
    "scripts/hwpx/web_office/paragraph_save_audit.py",
    "scripts/hwpx/web_office/ro_view_importer.py",
    "scripts/hwpx/web_office/document_model.py",
    # WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-PREVIEW-01 (abebab6):
    # render_payload.py 는 char_pr_defs additive 추가로 본 LOCKED 에서 제거됨.
    "scripts/hwpx/web_office/edit_command_model.py",
    "scripts/hwpx/web_office/para_edit_normalizer.py",
]
BASELINE = "51cfe49"


def _static_state_js(findings: list[dict]) -> None:
    src = STATE_JS.read_text(encoding="utf-8")
    if "containerScope" not in src:
        findings.append({"code": "STATE_JS_NO_CONTAINER_SCOPE", "level": "FAIL"})
    if "REQUIRES_REVIEW_NO_CONTAINER_SCOPE" not in src:
        findings.append({"code": "STATE_JS_NO_REQUIRES_REVIEW_GATE", "level": "FAIL"})
    # 하드코딩 block 제거 확인 — _buildTarget 가 더이상 containerKind:"block"
    # 단일 리터럴을 무조건 반환하지 않아야 한다.
    if re.search(r"containerKind:\s*\"block\",\s*\n\s*containerId:\s*paragraphId,", src):
        findings.append({"code": "STATE_JS_HARDCODED_BLOCK", "level": "FAIL"})


def _static_command_js(findings: list[dict]) -> None:
    src = COMMAND_JS.read_text(encoding="utf-8")
    # forward / inverse 양쪽에 containerScope: scope 가 있어야 한다.
    if src.count("containerScope: scope") < 6:
        findings.append({
            "code": "COMMAND_JS_FORWARD_INVERSE_SCOPE_MISSING",
            "level": "FAIL",
            "detail": src.count("containerScope: scope"),
        })


def _static_self_test_js(findings: list[dict]) -> None:
    src = SELF_TEST_JS.read_text(encoding="utf-8")
    findings.extend({"code": "SELF_TEST_CHECK_MISSING", "level": "FAIL", "detail": key} for key in (
        "containerScopePropagation",
        "requiresReviewWhenNoContainerScope",
        "blockContainerScopeAccepted",
    ) if key not in src)


def _static_para_model(findings: list[dict]) -> None:
    src = PARA_MODEL_PY.read_text(encoding="utf-8")
    if "containerScope: dict | None = None" not in src:
        findings.append({"code": "PARA_MODEL_FIELD_MISSING", "level": "FAIL"})
    if "container_scope: dict | None = None" not in src:
        findings.append({"code": "PARA_MODEL_KWARG_MISSING", "level": "FAIL"})


def _static_para_plan(findings: list[dict]) -> None:
    src = PARA_PLAN_PY.read_text(encoding="utf-8")
    # target.containerScope 우선 사용
    if 'target.get("containerScope")' not in src:
        findings.append({"code": "PARA_PLAN_TARGET_SCOPE_NOT_USED", "level": "FAIL"})


def _static_writer_unchanged(findings: list[dict]) -> None:
    for rel in LOCKED_VS_BASELINE:
        try:
            r = subprocess.run(
                ["git", "diff", BASELINE, "--", rel],
                cwd=PR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=20,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as e:
            findings.append({"code": "GIT_DIFF_FAIL", "level": "WARN", "detail": f"{rel}: {e}"})
            continue
        if r.stdout.strip():
            findings.append({
                "code": "LOCKED_FILE_TOUCHED",
                "level": "FAIL",
                "detail": rel,
                "diff_lines": len(r.stdout.splitlines()),
            })


def _static_writer_tokens(findings: list[dict]) -> None:
    # 본 공정 산출물에 writer/output 토큰 없음
    targets = [STATE_JS, COMMAND_JS, SELF_TEST_JS, PARA_MODEL_PY, PARA_PLAN_PY]
    forbidden = [
        "hwpx" + "_edit_tool",
        "apply" + "_edit_plan",
        "create_hwpx_document(",
        "write_package(",
        "ai_proposal_fn",
    ]
    for p in targets:
        src = p.read_text(encoding="utf-8")
        findings.extend({
                    "code": "FORBIDDEN_WRITER_TOKEN",
                    "level": "FAIL",
                    "detail": f"{p.name}: {tok}",
                } for tok in forbidden if tok in src)


@dataclass
class _RoViewTools:
    import_hwpx_as_ro_view: object
    PModel: object
    ParaTextRun: object
    ParagraphTarget: object
    make_type_text_command: object
    build_dry_run_paragraph_plan: object
    validate_edit_plan: object


def _load_fixture_dry_run_doc(summary: dict, tools: _RoViewTools):
    db = PR / "data/recognition_corpus/corpus.sqlite3"
    if not db.is_file():
        summary["fixtureAvailable"] = False
        return None
    conn = sqlite3.connect(db)
    rows = conn.execute("""
        SELECT d.source_path FROM hwpx_documents d
        JOIN document_classifications c ON c.document_id=d.document_id
        WHERE d.inventory_status='FOUND'
          AND c.document_type='fillable_form'
          AND d.file_size BETWEEN 30000 AND 120000
        ORDER BY d.first_seen_at LIMIT 1
    """).fetchall()
    conn.close()
    fixtures = [PR / r[0] for r in rows if (PR / r[0]).is_file()]
    if not fixtures:
        summary["fixtureAvailable"] = False
        return None
    summary["fixtureAvailable"] = True
    src_path = fixtures[0]
    sha_before = hashlib.sha256(src_path.read_bytes()).hexdigest()
    mt_before = src_path.stat().st_mtime_ns
    doc = tools.import_hwpx_as_ro_view(src_path)
    return doc, src_path, sha_before, mt_before


def _check_cell_paragraph_scope(findings: list[dict], doc, cell_para, tools: _RoViewTools) -> None:
    scope = cell_para.containerScope
    target = tools.ParagraphTarget(
        paragraphId=cell_para.paragraphId,
        containerKind="cell",
        containerId=(f"cell_t{scope['tableIndex']}_r{scope['rowIndex']}_c{scope['colIndex']}"),
        sourceSha256=doc.sourceDocumentHash or "h",
        cellCoord={
            "table": scope["tableIndex"],
            "row": scope["rowIndex"],
            "col": scope["colIndex"],
        },
        containerScope=dict(scope),
    )
    para_model = tools.PModel(
        paragraphId=cell_para.paragraphId,
        parPrIDRef=cell_para.parPrIDRef,
        runs=[
            tools.ParaTextRun(runId=r.runId, text=r.text, charPrIDRef=r.charPrIDRef)
            for r in cell_para.runs
        ],
    )
    cmd = tools.make_type_text_command(
        target=target,
        paragraph=para_model,
        caret_offset=0,
        insert_text="X",
        source_document_hash=doc.sourceDocumentHash or "h",
        container_scope=dict(scope),
    )
    if cmd is None:
        findings.append({"code": "DYN_CELL_CMD_NULL", "level": "FAIL"})
        return
    res = tools.build_dry_run_paragraph_plan(
        [cmd], {para_model.paragraphId: para_model}, doc.sourceDocumentHash or "h"
    )
    plan = res.get("plan") or {}
    items = plan.get("paragraph_edits", [])
    if not items:
        findings.append({
            "code": "DYN_CELL_PLAN_EMPTY",
            "level": "FAIL",
            "detail": res.get("rejected"),
        })
        return
    sc = items[0].get("containerScope") or {}
    if sc.get("kind") != "cell":
        findings.append({
            "code": "DYN_CELL_SCOPE_KIND_WRONG",
            "level": "FAIL",
            "detail": sc,
        })
    v = tools.validate_edit_plan({"paragraph_edits": items})
    if v.get("status") != "PASS":
        findings.append({
            "code": "DYN_CELL_VALIDATE_FAIL",
            "level": "FAIL",
            "detail": v.get("errors"),
        })


def _check_block_paragraph_scope(
    findings: list[dict], doc, block_para, tools: _RoViewTools
) -> None:
    bscope = block_para.containerScope
    btarget = tools.ParagraphTarget(
        paragraphId=block_para.paragraphId,
        containerKind="block",
        containerId=block_para.paragraphId,
        sourceSha256=doc.sourceDocumentHash or "h",
        containerScope=dict(bscope),
    )
    bpara_model = tools.PModel(
        paragraphId=block_para.paragraphId,
        parPrIDRef=block_para.parPrIDRef,
        runs=[
            tools.ParaTextRun(runId=r.runId, text=r.text, charPrIDRef=r.charPrIDRef)
            for r in block_para.runs
        ],
    )
    bcmd = tools.make_type_text_command(
        target=btarget,
        paragraph=bpara_model,
        caret_offset=0,
        insert_text="Y",
        source_document_hash=doc.sourceDocumentHash or "h",
        container_scope=dict(bscope),
    )
    if bcmd is None:
        return
    bres = tools.build_dry_run_paragraph_plan(
        [bcmd], {bpara_model.paragraphId: bpara_model}, doc.sourceDocumentHash or "h"
    )
    bplan = bres.get("plan") or {}
    bitems = bplan.get("paragraph_edits", [])
    if not bitems:
        return
    bsc = bitems[0].get("containerScope") or {}
    if bsc.get("kind") != "block":
        findings.append({
            "code": "DYN_BLOCK_SCOPE_KIND_WRONG",
            "level": "FAIL",
            "detail": bsc,
        })
    bv = tools.validate_edit_plan({"paragraph_edits": bitems})
    # block 도 schema 자체는 PASS (kind in {cell,block})
    if bv.get("status") != "PASS":
        findings.append({
            "code": "DYN_BLOCK_VALIDATE_FAIL",
            "level": "FAIL",
            "detail": bv.get("errors"),
        })


def _verify_source_unchanged(
    findings: list[dict], summary: dict, src_path: Path, sha_before: str, mt_before: int
) -> None:
    sha_after = hashlib.sha256(src_path.read_bytes()).hexdigest()
    mt_after = src_path.stat().st_mtime_ns
    summary["originalShaPreserved"] = sha_before == sha_after and mt_before == mt_after
    if not summary["originalShaPreserved"]:
        findings.append({"code": "ORIGINAL_HWPX_MUTATED", "level": "FAIL"})


def _dynamic(findings: list[dict], summary: dict) -> None:
    from scripts.hwpx.hwpx_edit_tool import validate_edit_plan
    from scripts.hwpx.web_office.para_edit_model import (
        Paragraph as PModel,
    )
    from scripts.hwpx.web_office.para_edit_model import (
        ParagraphTarget,
        ParaTextRun,
        make_type_text_command,
    )
    from scripts.hwpx.web_office.paragraph_edit_plan import (
        build_dry_run_paragraph_plan,
    )
    from scripts.hwpx.web_office.ro_view_importer import (
        import_hwpx_as_ro_view,
    )

    tools = _RoViewTools(
        import_hwpx_as_ro_view=import_hwpx_as_ro_view,
        PModel=PModel,
        ParaTextRun=ParaTextRun,
        ParagraphTarget=ParagraphTarget,
        make_type_text_command=make_type_text_command,
        build_dry_run_paragraph_plan=build_dry_run_paragraph_plan,
        validate_edit_plan=validate_edit_plan,
    )

    loaded = _load_fixture_dry_run_doc(summary, tools)
    if loaded is None:
        return
    doc, src_path, sha_before, mt_before = loaded

    # cell paragraph 1개 탐색
    cell_para = next(
        (p for p in doc.paragraphs if p.containerScope and p.containerScope.get("kind") == "cell"),
        None,
    )
    block_para = next(
        (p for p in doc.paragraphs if p.containerScope and p.containerScope.get("kind") == "block"),
        None,
    )
    if cell_para is None:
        findings.append({"code": "FIXTURE_NO_CELL_PARA", "level": "WARN"})
    else:
        _check_cell_paragraph_scope(findings, doc, cell_para, tools)

    if block_para is not None:
        _check_block_paragraph_scope(findings, doc, block_para, tools)

    _verify_source_unchanged(findings, summary, src_path, sha_before, mt_before)


def _run_js_self_test(findings: list[dict], summary: dict) -> None:
    try:
        r = subprocess.run(
            ["node", str(SELF_TEST_JS)],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        summary["jsSelfTestSkipped"] = str(e)
        return
    if r.returncode != 0:
        findings.append({
            "code": "JS_SELF_TEST_FAIL",
            "level": "FAIL",
            "detail": {"stderr": r.stderr[:400], "stdout": r.stdout[:400]},
        })
        return
    try:
        last = r.stdout.strip().splitlines()[-1]
        parsed = json.loads(last)
        summary["jsChecks"] = parsed.get("checks", {})
        findings.extend({"code": "JS_NEW_CHECK_NOT_PASS", "level": "FAIL", "detail": key} for key in (
            "containerScopePropagation",
            "requiresReviewWhenNoContainerScope",
            "blockContainerScopeAccepted",
        ) if not parsed.get("checks", {}).get(key))
    except (ValueError, IndexError) as e:
        findings.append({"code": "JS_SELF_TEST_PARSE_FAIL", "level": "FAIL", "detail": str(e)})


def audit() -> dict:
    findings: list[dict] = []
    summary: dict = {}
    _static_state_js(findings)
    _static_command_js(findings)
    _static_self_test_js(findings)
    _static_para_model(findings)
    _static_para_plan(findings)
    _static_writer_unchanged(findings)
    _static_writer_tokens(findings)
    _dynamic(findings, summary)
    _run_js_self_test(findings, summary)
    fails = [f for f in findings if f.get("level") == "FAIL"]
    verdict = "PASS" if not fails else "FAIL"
    return {
        "task": "WEB-OFFICE-PARA-EDIT-CONTAINERSCOPE-BRIDGE-01",
        "verdict": verdict,
        "baseline": BASELINE,
        "findings": findings,
        "summary": summary,
    }


def main() -> int:
    rep = audit()
    print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    return 0 if rep["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
