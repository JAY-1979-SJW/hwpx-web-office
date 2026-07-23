"""문단 편집 저장 브리지 — 브라우저 명령 로그를 문단 저장 파이프라인에 잇는다.

배경(실측으로 확인된 구멍):
    브라우저 편집기는 문단 단위 명령(TYPE_TEXT 등)을 만드는데, HTTP 로
    노출된 저장 엔드포인트는 셀 명령(SET_CELL_TEXT)만 받는 /cell-save-apply
    하나뿐이었다. 문단 저장 파이프라인(paragraph_save_pipeline)은 있고
    시험도 통과하는데 경로가 안 뚫려 있어, 브라우저에서 채운 내용이
    파일로 나가지 못했다.

설계:
  · paragraphs_by_id 는 **서버가 원본을 다시 읽어 만든다.** 클라이언트가
    보낸 문단 내용을 그대로 믿으면 원본과 다른 전제로 검증이 통과해버린다.
    클라이언트에게서 받는 것은 '무엇을 어디에 했는가'(명령)뿐이다.
  · dryRunOnly 면 writer 를 켜지 않는다(allow_writer=False).
  · 출력은 항상 별도 파일 — 원본은 건드리지 않는다(V6_OUTPUT_ISOLATED).
"""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

from .para_edit_model import EditCommandV2, Paragraph, ParaTextRun
from .paragraph_save_pipeline import save_paragraph_edits

_ALLOWED_OPERATION = "PARA_SAVE_APPLY"
_PR = Path(__file__).resolve().parents[3]


def _hydrate_command(d: dict, scopes: dict[str, dict]) -> EditCommandV2:
    """클라이언트 JSON → EditCommandV2. 알 수 없는 키는 버린다.

    target 은 dict 여야 한다(plan 빌더가 target.get(...) 을 쓴다).
    containerScope 는 **원본 문서에서 뽑은 값**을 쓴다 — 클라이언트가 보낸
    스코프를 믿으면 셀 문단을 본문 문단이라 속여 경계 정책을 우회할 수 있다.
    """
    t = d.get("target") or {}
    pid = t.get("paragraphId") or d.get("paragraphId") or ""
    scope = scopes.get(pid)
    target = {
        "paragraphId": pid,
        "containerKind": (scope or {}).get("kind") or t.get("containerKind") or "block",
        "containerId": t.get("containerId") or "",
        "sourceSha256": t.get("sourceSha256") or d.get("sourceDocumentHash") or "",
        "cellCoord": t.get("cellCoord"),
        "containerScope": scope,
    }
    return EditCommandV2(
        commandId=d.get("commandId") or str(uuid.uuid4()),
        commandType=d.get("commandType") or d.get("type") or "",
        target=target,
        payload=d.get("payload") or {},
        forward=d.get("forward") or {},
        inverse=d.get("inverse") or {},
        expectedBefore=d.get("expectedBefore"),
        createdAt=d.get("createdAt") or "",
        sourceDocumentHash=d.get("sourceDocumentHash") or "",
        commandGroupId=d.get("commandGroupId"),
        status=d.get("status") or "PENDING",
    )


def _scopes_from_source(doc_model: dict) -> dict[str, dict]:
    """문단별 containerScope — 원본이 진실이다."""
    out: dict[str, dict] = {}
    for p in doc_model.get("paragraphs", []):
        pid = p.get("paragraphId")
        sc = p.get("containerScope")
        if pid and isinstance(sc, dict) and sc.get("kind"):
            out[pid] = dict(sc)
    return out


def _paragraphs_from_source(doc_model: dict) -> dict[str, Paragraph]:
    """원본을 다시 읽어 문단 맵을 만든다 — 클라이언트 내용을 믿지 않는다."""
    out: dict[str, Paragraph] = {}
    for p in doc_model.get("paragraphs", []):
        pid = p.get("paragraphId")
        if not pid:
            continue
        runs = [ParaTextRun(runId=r.get("runId") or f"{pid}_r{i}",
                            text=r.get("text") or "",
                            charPrIDRef=r.get("charPrIDRef"))
                for i, r in enumerate(p.get("runs") or [])]
        out[pid] = Paragraph(paragraphId=pid,
                             parPrIDRef=p.get("parPrIDRef"),
                             runs=runs)
    return out


def apply_para_save_request(
    request: dict[str, Any],
    *,
    project_root: Path = _PR,
    output_dir: Path,
    load_document,
) -> dict[str, Any]:
    """문단 저장 요청 처리.

    load_document(rel_path) → {"documentModel": ...} 를 돌려주는 호출자 제공
    함수. 로드 경계검증(§4)은 그 함수가 이미 수행한다.
    """
    if not isinstance(request, dict):
        return {"verdict": "REJECTED", "reason": "REQUEST_NOT_OBJECT"}
    if request.get("operation") != _ALLOWED_OPERATION:
        return {"verdict": "REJECTED", "reason": "UNSUPPORTED_OPERATION"}
    dry_run = request.get("dryRunOnly", False)
    if not isinstance(dry_run, bool):
        return {"verdict": "REJECTED", "reason": "DRY_RUN_ONLY_NOT_BOOL"}
    rel = request.get("sourcePath")
    if not isinstance(rel, str) or not rel:
        return {"verdict": "REJECTED", "reason": "SOURCE_PATH_MISSING"}
    raw_log = request.get("commandLog") or []
    if not isinstance(raw_log, list) or not raw_log:
        return {"verdict": "NOOP", "reason": "COMMAND_LOG_EMPTY"}

    loaded = load_document(rel)
    doc = (loaded or {}).get("documentModel") or {}
    if not doc.get("paragraphs"):
        return {"verdict": "REJECTED", "reason": "SOURCE_LOAD_FAILED"}

    paragraphs = _paragraphs_from_source(doc)
    scopes = _scopes_from_source(doc)
    commands = [_hydrate_command(c, scopes) for c in raw_log
                if isinstance(c, dict)]
    unknown = [c.commandId for c in commands
               if (c.target or {}).get("paragraphId") not in paragraphs]
    if unknown:
        return {"verdict": "REJECTED", "reason": "TARGET_PARAGRAPH_NOT_IN_SOURCE",
                "detail": unknown[:5]}

    src = project_root / rel
    if not src.is_file():
        return {"verdict": "REJECTED", "reason": "SOURCE_FILE_MISSING"}

    # 문서 해시는 **실제 파일**에서 계산한다. 요청이 보낸 값을 그대로 넘기면
    # 클라이언트 값끼리 비교가 되어 검증이 무의미해진다(vacuous). 로더가
    # 돌려주는 sourceDocumentHash 가 곧 파일 sha256 이므로, 파일에서 다시
    # 계산해 넘기면 '로드 이후 원본이 바뀐 상태에서의 저장'이 정확히 걸린다.
    current_hash = hashlib.sha256(src.read_bytes()).hexdigest()

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"para_save_{uuid.uuid4().hex[:12]}.hwpx"

    result = save_paragraph_edits(
        source_path=src, output_path=out_path,
        command_log=commands, paragraphs_by_id=paragraphs,
        source_document_hash=current_hash,
        project_root=project_root,
        allow_writer=not dry_run)

    verify7 = result.get("verify7") or {}
    return {
        "operation": _ALLOWED_OPERATION,
        "verdict": result.get("verdict"),
        "dryRun": dry_run,
        "acceptedCount": len(result.get("accepted") or []),
        "rejected": result.get("rejected") or [],
        "sourceUnchanged": result.get("sourceUnchanged"),
        "outputCreated": result.get("outputCreated"),
        "outputFileName": out_path.name if result.get("outputCreated") else None,
        "outputPath": str(out_path) if result.get("outputCreated") else None,
        "verify7Verdict": verify7.get("verdict"),
        "verify7Results": verify7.get("results") or {},
        "notes": result.get("notes") or [],
    }
