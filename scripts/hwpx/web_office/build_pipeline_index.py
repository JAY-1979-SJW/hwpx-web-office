"""단계별 SQL 스테이징을 조인해 목차를 만든다 — 재계산 없음, 순수 SQL.

지시(2026-08-02, 대표님): "파싱하고 검증하고 단계별로 해야 하고
목차 생성은? DB, SQL?"

`build_document_index.py`(문서 1건씩 즉석 재계산)와 다르다 — 이 모듈은
아무것도 다시 계산하지 않는다. 4단계 스테이징 테이블을 그대로 조인만
한다:

    forms                          (파싱·승격 결과 — rebuild_form_derivations_batch)
    schema_address_verification    (좌표 검증 — verify_schema_addresses)
    ai_field_interpretation        (AI 1차 해석 — build_ai_interpretation_cache)
    ai_field_verification          (AI 2차 독립 검증 — build_ai_interpretation_cache --verify)

각 문서가 지금 어느 단계까지 갔는지, 그 단계에서 뭐가 나왔는지 한 행으로
보여준다. 대용량(수만 건)에서도 빠르다 — 파일을 다시 열지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CATALOG = PROJECT_ROOT / "data" / "drafts" / "form_library" / "catalog.sqlite"

STAGE_NONE = "0_미착수"
STAGE_PARSED = "1_파싱완료"
STAGE_ADDR_OK = "2_좌표검증PASS"
STAGE_ADDR_FAIL = "2_좌표검증FAIL"
STAGE_AI1 = "3_AI1차해석"
STAGE_AI2 = "4_AI2차검증"


def _stage(row: dict) -> str:
    if row.get("v2_status") == "OK":
        return STAGE_AI2
    if row.get("v1_status") == "OK":
        return STAGE_AI1
    if row.get("addr_verdict") == "PASS":
        return STAGE_ADDR_OK
    if row.get("addr_verdict") == "FAIL":
        return STAGE_ADDR_FAIL
    if row.get("has_schema"):
        return STAGE_PARSED
    return STAGE_NONE


def query_index(*, scope: str | None = None,
                project_root: Path = PROJECT_ROOT) -> list[dict[str, Any]]:
    con = sqlite3.connect(CATALOG)
    have = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    sql = """
        SELECT f.form_id, f.clean_name, f.name, f.doc_type, f.form_kind,
               f.input_count, f.applicant_count, f.office_count,
               (f.input_schema IS NOT NULL AND f.input_schema != '') AS has_schema,
    """
    sql += ("""av.verdict AS addr_verdict, av.ok_cells, av.fail_cells,
    """ if "schema_address_verification" in have else "NULL, NULL, NULL,\n    ")
    sql += ("""ai1.status AS v1_status, ai1.author_count, ai1.not_input_count,
               ai1.semantic_count,
    """ if "ai_field_interpretation" in have else
           "NULL, NULL, NULL, NULL,\n    ")
    sql += ("""ai2.status AS v2_status, ai2.agreement_rate, ai2.disagreed_count
    """ if "ai_field_verification" in have else "NULL, NULL, NULL\n    ")
    sql += "FROM forms f\n"
    if "schema_address_verification" in have:
        sql += "LEFT JOIN schema_address_verification av ON av.form_id=f.form_id\n"
    if "ai_field_interpretation" in have:
        sql += "LEFT JOIN ai_field_interpretation ai1 ON ai1.form_id=f.form_id\n"
    if "ai_field_verification" in have:
        sql += "LEFT JOIN ai_field_verification ai2 ON ai2.form_id=f.form_id\n"
    params: list[Any] = []
    if scope:
        sql += "WHERE f.source_path LIKE ?\n"
        params.append(f"%{scope}%")
    sql += "ORDER BY f.form_id"

    cols = ["form_id", "clean_name", "name", "doc_type", "form_kind",
            "input_count", "applicant_count", "office_count", "has_schema",
            "addr_verdict", "ok_cells", "fail_cells",
            "v1_status", "author_count", "not_input_count", "semantic_count",
            "v2_status", "agreement_rate", "disagreed_count"]
    rows = [dict(zip(cols, r)) for r in con.execute(sql, params).fetchall()]
    con.close()
    for r in rows:
        r["stage"] = _stage(r)
    return rows


def write_index(rows: list[dict[str, Any]], *, out_dir: Path,
                basename: str = "pipeline_index") -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_dir / f"{basename}.jsonl"
    md_path = out_dir / f"{basename}.md"

    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    stage_counts = Counter(r["stage"] for r in rows)
    lines = ["# 파이프라인 목차 (SQL 조인 — 재계산 없음)", "",
             f"전체 {len(rows)}건", ""]
    for st in sorted(stage_counts):
        lines.append(f"- {st}: {stage_counts[st]}건")
    lines += ["", "| 서식ID | 이름 | 유형 | 입력칸 | 좌표검증 | AI1차 | AI2차일치율 | 단계 |",
             "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        name = (r["clean_name"] or r["name"] or "")[:34]
        dtype = f"{r['doc_type'] or '-'}/{r['form_kind'] or '-'}"
        addr = r["addr_verdict"] or "-"
        v1 = r["v1_status"] or "-"
        ar = f"{r['agreement_rate']:.2f}" if isinstance(
            r.get("agreement_rate"), float) else "-"
        lines.append(f"| #{r['form_id']} | {name} | {dtype} |"
                     f" {r['input_count'] or 0} | {addr} | {v1} | {ar} |"
                     f" {r['stage']} |")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return jsonl_path, md_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default=None)
    ap.add_argument("--out", default="hwpx_pipeline_index")
    a = ap.parse_args()
    rows = query_index(scope=a.scope)
    out_dir = PROJECT_ROOT / "data" / "reports" / a.out
    jsonl_path, md_path = write_index(rows, out_dir=out_dir)
    from collections import Counter
    print(f"목차 {len(rows)}건 생성")
    print("단계 분포:", dict(Counter(r["stage"] for r in rows)))
    print("JSONL:", jsonl_path)
    print("MD   :", md_path)


if __name__ == "__main__":
    main()
