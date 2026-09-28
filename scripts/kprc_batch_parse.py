"""
kprc_batch_parse.py  --  KPRC 주요자재별_거래가격 PDF 배치 파서 (Haiku-only)

정책:
  - 모델: claude-haiku-4-5-20251001 고정 (상위 모델 fallback 금지)
  - ANTHROPIC_API_KEY 사용 금지 — Claude Code CLI 세션만 사용
  - 역순 처리 (최신월부터)
  - 배치당 실패/토큰/rowcount 집계 후 중단 판정

출력:
  <out>/parsed/<pdf_stem>.json        파일별 파싱 결과
  <out>/batch_summary_<batch>.json    배치 집계
  <out>/failed_files_<batch>.json     실패 파일 목록 (있을 때만)

사용:
  python kprc_batch_parse.py --pdfs "path/*.pdf" --batch 2026Q2 --out C:/tmp/kprc_batch
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import fitz
except ImportError:
    print("[ERROR] pymupdf 없음: pip install pymupdf", file=sys.stderr)
    sys.exit(2)


MODEL = "claude-haiku-4-5-20251001"  # 상위 모델 fallback 금지

PROMPT_CHART = """아래 이미지는 건설자재 가격 차트와 그 아래 표다.
표에서 데이터를 추출해 JSON만 반환하라 (설명 없이):

{
  "items": [
    {
      "품목명": "고장력철근",
      "규격": "SD400, KSD3504",
      "단위": "톤",
      "가격": [
        {"연도": 2026, "월": 1, "가격": 860000}
      ]
    }
  ]
}

규칙:
- 페이지 당 여러 품목 가능
- 표 하단의 연도/월 열 확인
- 숫자는 쉼표 제거한 정수
- 가격 없는 셀은 제외"""

PROMPT_TABLE = """아래 이미지는 건설자재 월별 가격표다.
표에서 데이터를 추출해 JSON만 반환하라 (설명 없이):

{
  "items": [
    {
      "품목명": "고장력철근",
      "규격": "SD400, 10mm",
      "단위": "톤",
      "가격": [
        {"연도": 2026, "월": 1, "가격": 860000}
      ]
    }
  ]
}

규칙:
- 가격 없는 셀은 제외
- 숫자는 쉼표 제거한 정수
- 품목명·규격·단위는 표에 있는 그대로"""


def log(msg: str):
    print(f"[KPRC PARSE] {msg}", flush=True)


def render_page(pdf: Path, page_idx: int, scale: float, out_dir: Path) -> Path:
    doc = fitz.open(str(pdf))
    mat = fitz.Matrix(scale, scale)
    pix = doc[page_idx].get_pixmap(matrix=mat)
    out = out_dir / f"{pdf.stem}__p{page_idx:02d}.png"
    pix.save(str(out))
    doc.close()
    return out


def call_claude(prompt: str, image_path: Path, timeout: int = 180) -> dict:
    """Claude Code CLI Haiku 호출.
    반환: {ok, items, input_tokens, output_tokens, total_tokens, duration_ms, err}"""
    full_prompt = f"{prompt}\n\n이미지 파일 경로: {image_path}"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [
                "claude",
                "-p",
                full_prompt,
                "--tools",
                "Read",
                "--model",
                MODEL,
                "--dangerously-skip-permissions",
                "--output-format",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "err": "timeout",
            "items": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    except OSError as e:
        return {
            "ok": False,
            "err": f"subprocess: {e}",
            "items": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    if proc.returncode != 0:
        return {
            "ok": False,
            "err": f"rc={proc.returncode} stderr={proc.stderr[:200]}",
            "items": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    try:
        resp = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "err": f"cli_json_decode: {e}",
            "items": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    usage = resp.get("usage", {}) or {}
    input_tokens = (
        int(usage.get("input_tokens") or 0)
        + int(usage.get("cache_read_input_tokens") or 0)
        + int(usage.get("cache_creation_input_tokens") or 0)
    )
    output_tokens = int(usage.get("output_tokens") or 0)
    # 모델 검증 — 혹시라도 상위 모델로 fallback되면 실패 처리
    used_model = resp.get("model") or resp.get("modelUsed") or ""
    if used_model and "haiku" not in used_model.lower():
        return {
            "ok": False,
            "err": f"unexpected_model: {used_model}",
            "items": [],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    result_text = resp.get("result") or ""
    m = re.search(r"\{.*\}", result_text, re.DOTALL)
    if not m:
        return {
            "ok": False,
            "err": "no_json_in_result",
            "items": [],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "duration_ms": int((time.time() - t0) * 1000),
        }
    try:
        items = json.loads(m.group()).get("items", [])
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "err": f"inner_json_decode: {e}",
            "items": [],
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "duration_ms": int((time.time() - t0) * 1000),
        }

    return {
        "ok": True,
        "err": None,
        "items": items,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "duration_ms": int((time.time() - t0) * 1000),
    }


def parse_pdf(pdf: Path, pages_dir: Path, year_min: int = 2023) -> dict:
    """PDF 1개 파싱.
    반환: {ok, pdf, n_pages, rows, pivot, usage:{input/output/total}, pages:[call results]}"""
    pages_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf))
    n = doc.page_count
    doc.close()

    all_rows = []
    calls = []
    agg_in = agg_out = 0

    for i in range(n):
        scale = 2.0 if i < 4 else 2.5
        prompt = PROMPT_CHART if i < 4 else PROMPT_TABLE
        img = render_page(pdf, i, scale, pages_dir)
        r = call_claude(prompt, img)
        try:
            img.unlink(missing_ok=True)
        except OSError:
            pass

        calls.append({
            "page": i + 1,
            "ok": r["ok"],
            "err": r.get("err"),
            "n_items": len(r.get("items", [])),
            "input_tokens": r["input_tokens"],
            "output_tokens": r["output_tokens"],
            "total_tokens": r["total_tokens"],
            "duration_ms": r["duration_ms"],
        })
        agg_in += r["input_tokens"]
        agg_out += r["output_tokens"]

        if r["ok"]:
            src_label = "차트페이지" if i < 4 else "종합표"
            for item in r["items"]:
                for p in item.get("가격", []):
                    y = p.get("연도")
                    m = p.get("월")
                    v = p.get("가격")
                    if not isinstance(y, int) or v is None:
                        continue
                    if y < year_min:
                        continue
                    all_rows.append({
                        "품목명": item.get("품목명", ""),
                        "규격": item.get("규격", ""),
                        "단위": item.get("단위", ""),
                        "연도": y,
                        "월": m,
                        "가격": v,
                        "출처": src_label,
                    })
        log(
            f"  page {i + 1}/{n}  ok={r['ok']}  items={len(r.get('items', []))}  tok_in={r['input_tokens']} tok_out={r['output_tokens']}"
        )

    # 중복 제거 (품목, 규격, 연, 월)
    seen = set()
    dedup = []
    for row in all_rows:
        k = (row["품목명"], row["규격"], row["연도"], row["월"])
        if k in seen:
            continue
        seen.add(k)
        dedup.append(row)

    # pivot
    pivot_map = {}
    for r in dedup:
        k = f"{r['품목명']}|{r['규격']}"
        if k not in pivot_map:
            pivot_map[k] = {"품목명": r["품목명"], "규격": r["규격"], "단위": r["단위"], "가격": []}
        pivot_map[k]["가격"].append({"연도": r["연도"], "월": r["월"], "가격": r["가격"]})

    any_ok = any(c["ok"] for c in calls)
    all_ok = all(c["ok"] for c in calls)
    return {
        "ok": all_ok,
        "partial": any_ok and not all_ok,
        "pdf": pdf.name,
        "n_pages": n,
        "rows": dedup,
        "pivot": list(pivot_map.values()),
        "usage": {
            "input_tokens": agg_in,
            "output_tokens": agg_out,
            "total_tokens": agg_in + agg_out,
        },
        "pages": calls,
    }


def anomaly_check(rows: list[dict]) -> dict:
    prices = [r["가격"] for r in rows if isinstance(r.get("가격"), (int, float))]
    if not prices:
        return {"n_rows": 0, "price_min": None, "price_max": None, "suspicious_zero": 0}
    suspicious = sum(1 for p in prices if p <= 0)
    return {
        "n_rows": len(rows),
        "price_min": min(prices),
        "price_max": max(prices),
        "suspicious_zero_or_negative": suspicious,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", nargs="+", required=True, help="대상 PDF 경로 (공백 구분)")
    ap.add_argument("--batch", required=True, help="배치 이름 (로그/파일명)")
    ap.add_argument("--out", required=True, help="출력 디렉토리")
    ap.add_argument("--year-min", type=int, default=2023)
    args = ap.parse_args()

    out_dir = Path(args.out)
    parsed_dir = out_dir / "parsed"
    pages_dir = out_dir / "pages"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    pages_dir.mkdir(parents=True, exist_ok=True)

    # 최신순 역순 정렬 (파일명 prefix YYYYMMDD 기준)
    pdfs = [Path(p) for p in args.pdfs]
    pdfs = [p for p in pdfs if p.exists()]
    pdfs.sort(reverse=True)

    log(f"batch={args.batch}  model={MODEL}  n_pdfs={len(pdfs)}")
    log("대상 파일 (최신순):")
    for p in pdfs:
        log(f"  - {p.name}")

    batch_start = time.time()
    results = []
    failed = []
    total_in = total_out = total_rows = 0

    for idx, pdf in enumerate(pdfs, 1):
        log(f"[{idx}/{len(pdfs)}] {pdf.name}")
        t0 = time.time()
        try:
            res = parse_pdf(pdf, pages_dir, year_min=args.year_min)
        except Exception as e:  # noqa: BLE001 — 이 PDF만 실패 기록, 나머지 배치 계속
            log(f"  FATAL  {type(e).__name__}: {e}")
            failed.append({"pdf": pdf.name, "err": f"{type(e).__name__}: {e}"})
            continue
        elapsed = time.time() - t0

        anom = anomaly_check(res["rows"])
        rec = {
            "pdf": res["pdf"],
            "ok": res["ok"],
            "partial": res["partial"],
            "n_pages": res["n_pages"],
            "n_rows": len(res["rows"]),
            "n_items": len(res["pivot"]),
            "usage": res["usage"],
            "anomaly": anom,
            "elapsed_sec": round(elapsed, 2),
        }
        results.append(rec)
        total_in += res["usage"]["input_tokens"]
        total_out += res["usage"]["output_tokens"]
        total_rows += len(res["rows"])

        # 파일별 JSON 저장
        out_path = parsed_dir / f"{pdf.stem}.json"
        out_path.write_text(
            json.dumps(
                {
                    "pdf": pdf.name,
                    "생성일시": datetime.now().isoformat(timespec="seconds"),
                    "model": MODEL,
                    "n_pages": res["n_pages"],
                    "n_rows": len(res["rows"]),
                    "n_items": len(res["pivot"]),
                    "usage": res["usage"],
                    "anomaly": anom,
                    "rows": res["rows"],
                    "pivot": res["pivot"],
                    "pages": res["pages"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if not res["ok"]:
            failed.append({
                "pdf": pdf.name,
                "partial": res["partial"],
                "fail_pages": [c for c in res["pages"] if not c["ok"]],
            })

        log(
            f"  → rows={len(res['rows'])}  tok_in={res['usage']['input_tokens']:,}  "
            f"tok_out={res['usage']['output_tokens']:,}  elapsed={elapsed:.1f}s"
        )

    total_elapsed = time.time() - batch_start
    ok_cnt = sum(1 for r in results if r["ok"])
    fail_cnt = len(pdfs) - ok_cnt
    total_tok = total_in + total_out
    avg_tok_per_file = (total_tok / len(pdfs)) if pdfs else 0
    avg_tok_per_row = (total_tok / total_rows) if total_rows else 0

    summary = {
        "batch": args.batch,
        "생성일시": datetime.now().isoformat(timespec="seconds"),
        "model": MODEL,
        "n_pdfs": len(pdfs),
        "n_success": ok_cnt,
        "n_failed": fail_cnt,
        "total_rows": total_rows,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_tokens": total_tok,
        "avg_tokens_per_file": round(avg_tok_per_file, 1),
        "avg_tokens_per_row": round(avg_tok_per_row, 2),
        "total_elapsed_sec": round(total_elapsed, 2),
        "files": results,
    }
    summary_path = out_dir / f"batch_summary_{args.batch}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if failed:
        failed_path = out_dir / f"failed_files_{args.batch}.json"
        failed_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")

    log("=" * 60)
    log(f"BATCH {args.batch}  완료")
    log(f"  files={len(pdfs)}  ok={ok_cnt}  fail={fail_cnt}")
    log(f"  rows={total_rows:,}")
    log(f"  tokens  in={total_in:,}  out={total_out:,}  total={total_tok:,}")
    log(f"  avg/file={avg_tok_per_file:,.0f}  avg/row={avg_tok_per_row:,.2f}")
    log(f"  elapsed={total_elapsed:.1f}s")
    log(f"  summary: {summary_path}")


if __name__ == "__main__":
    main()
