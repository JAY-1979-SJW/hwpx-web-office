"""파일별 처리 + 목차 생성 — 배치 집계가 아니라 문서 1건씩 이력을 남긴다.

지시(2026-08-01, 대표님): "한번에 다하는게 아닌 파일별로 하고 목차를
생성하면?"

기존 배치(rebuild_form_derivations_batch·build_ai_interpretation_cache)는
스테이징 테이블에 결과를 쌓기만 해서, 사람이 "이 문서가 왜 이렇게
됐는지"를 한눈에 못 봤다. 이 모듈은 문서 1건마다 ①스키마 생성 →
②1차 AI 해석 → ③2차 독립 검증을 **순서대로** 돌리고, 매 건 완료 시
목차(JSONL + Markdown)에 한 줄씩 적는다 — 중간에 멈춰도 그때까지 목차는
읽을 수 있는 상태로 남는다(재개 가능·부분 결과 즉시 가시).

목차 한 줄 = 문서 하나의 전체 이력:
  파일명 · docType/formKind · 입력칸 수 · 죽은 서식이었는가 ·
  AI 해석 요약 · 2차 검증 일치율 · 최종 판정(되살림/보류/불일치 목록)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.hwpx.web_office.ai_doc_context import build_context_fields  # noqa: E402
from scripts.hwpx.web_office.ai_field_interpretation import (  # noqa: E402
    should_promote_to_user)
from scripts.hwpx.web_office.ai_field_verification import verify_fields  # noqa: E402
from scripts.hwpx.web_office.build_ai_interpretation_cache import (  # noqa: E402
    interpret_one)
from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # noqa: E402
from scripts.hwpx.web_office.form_input_schema import build_input_schema  # noqa: E402


def process_one(form_id: int, source_path: str, name: str,
                *, project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    """문서 1건 전 과정. 실패해도 예외를 던지지 않고 status 에 담는다."""
    row: dict[str, Any] = {"formId": form_id, "sourcePath": source_path,
                           "name": name}
    t0 = time.time()

    # ① 스키마 생성 — 순수 파싱, AI 없음
    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": source_path},
        project_root=project_root)
    if res.get("verdict") != "PASS":
        row.update({"stage": "SCHEMA", "status": "LOAD_FAILED",
                    "reason": res.get("reason")})
        return row
    dm, rp = res["documentModel"], res["renderPayload"]
    schema = build_input_schema(dm, rp, name=name or "", field_count=None)
    row.update({
        "docType": schema["docType"], "formKind": schema["formKind"],
        "inputCount": schema["inputCount"],
        "applicantCount": schema["applicantCount"],
        "officeCount": schema["officeCount"],
        "wasDead": schema["applicantCount"] == 0 and schema["inputCount"] > 0,
    })
    if not schema["inputs"]:
        row.update({"stage": "SCHEMA", "status": "NO_INPUTS"})
        row["elapsedSec"] = round(time.time() - t0, 1)
        return row

    # ② 1차 AI 해석 — 전 입력칸(roles=None, §4.6 파싱 우선)
    schema_json = json.dumps(schema["inputs"], ensure_ascii=False)
    interp_res = interpret_one(source_path, schema_json, schema["cleanName"])
    if interp_res.get("status") != "OK":
        row.update({"stage": "INTERPRET", "status": interp_res.get("status"),
                    "reason": interp_res.get("error")})
        row["elapsedSec"] = round(time.time() - t0, 1)
        return row
    interp = json.loads(interp_res["interpretations"])
    row.update({
        "authorCells": interp_res["author_count"],
        "notInputCells": interp_res["not_input_count"],
        "semanticCells": interp_res["semantic_count"],
    })

    # ③ 2차 독립 검증 — 1차를 보여주지 않고 다시 판정, 일치만 반영
    fields = build_context_fields(schema["inputs"], dm,
                                  title=schema["cleanName"], roles=None)
    v = verify_fields(fields, interp)
    if not v.get("ok"):
        row.update({"stage": "VERIFY", "status": v.get("error", "VERIFY_FAILED")})
        row["elapsedSec"] = round(time.time() - t0, 1)
        return row
    ag = v["agreement"]
    agreed_keys = set(ag["authorAgreed"])
    revived = [i for i in interp
              if should_promote_to_user(
                  i, doc_type=schema["docType"], form_kind=schema["formKind"],
                  form_applicant_count=schema["applicantCount"],
                  verified=(i["key"] in agreed_keys))]
    row.update({
        "stage": "DONE", "status": "OK",
        "agreementRate": ag["agreementRate"],
        "disagreedCount": len(ag["disagreed"]),
        "disagreedSamples": [d["label"] for d in ag["disagreed"][:5]],
        "revivedCount": len(revived),
        "revivedLabels": [r["label"][:24] for r in revived[:8]],
    })
    row["elapsedSec"] = round(time.time() - t0, 1)
    return row


def _md_row(r: dict[str, Any]) -> str:
    name = (r.get("name") or "")[:36]
    status = r.get("status", "?")
    dtype = f"{r.get('docType','-')}/{r.get('formKind','-')}"
    ic = r.get("inputCount", "-")
    dead = "죽음→" if r.get("wasDead") else ""
    rev = r.get("revivedCount")
    rev_s = f"{dead}{rev}칸" if rev is not None else "-"
    ar = r.get("agreementRate")
    ar_s = f"{ar:.2f}" if isinstance(ar, float) else "-"
    return (f"| #{r['formId']} | {name} | {dtype} | {ic} | {rev_s}"
           f" | {ar_s} | {status} | {r.get('elapsedSec','-')}s |")


def build_index(
    targets: list[tuple[int, str, str]], *,
    out_dir: Path, project_root: Path = PROJECT_ROOT,
    resume: bool = True,
) -> Path:
    """문서 목록을 1건씩 처리하며 목차(JSONL+Markdown)를 갱신한다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / "document_index.jsonl"
    md_path = out_dir / "document_index.md"

    done_ids: set[int] = set()
    if resume and jsonl_path.exists():
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    done_ids.add(json.loads(line)["formId"])
                except Exception:      # noqa: BLE001
                    pass

    rows: list[dict[str, Any]] = []
    if md_path.exists() and resume:
        pass  # 재작성은 끝에서 전체 rows 기준으로 다시 만든다
    if jsonl_path.exists() and resume:
        with jsonl_path.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rows.append(json.loads(line))
                except Exception:      # noqa: BLE001
                    pass

    with jsonl_path.open("a", encoding="utf-8") as jf:
        for form_id, source_path, name in targets:
            if resume and form_id in done_ids:
                continue
            row = process_one(form_id, source_path, name,
                              project_root=project_root)
            jf.write(json.dumps(row, ensure_ascii=False) + "\n")
            jf.flush()
            rows.append(row)
            _rewrite_markdown(md_path, rows)
            print(f"[{len(rows)}] #{form_id} {row.get('status')} "
                  f"{row.get('elapsedSec')}s", flush=True)
    return jsonl_path


def _rewrite_markdown(md_path: Path, rows: list[dict[str, Any]]) -> None:
    lines = [
        "# 문서별 처리 목차",
        "",
        "| 서식ID | 이름 | 유형 | 입력칸 | 되살림 | 검증일치율 | 상태 | 소요 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines += [_md_row(r) for r in rows]
    ok = sum(1 for r in rows if r.get("status") == "OK")
    revived_forms = sum(1 for r in rows if (r.get("revivedCount") or 0) > 0)
    revived_cells = sum(r.get("revivedCount") or 0 for r in rows)
    lines += ["", f"**합계**: {len(rows)}건 처리 · 성공 {ok} ·"
             f" 되살아난 서식 {revived_forms} · 되살린 칸 {revived_cells}"]
    md_path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import sqlite3

    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    con = sqlite3.connect(
        PROJECT_ROOT / "data/drafts/form_library/catalog.sqlite")
    rows = con.execute(
        "SELECT form_id, source_path, name FROM forms"
        " WHERE source_path LIKE '%onedrive_hwpx%' AND table_count > 0"
        " ORDER BY form_id LIMIT ?", (limit,)).fetchall()
    con.close()
    out = PROJECT_ROOT / "data" / "reports" / "hwpx_onedrive_document_index"
    path = build_index(rows, out_dir=out)
    print(f"\n목차: {path}")
