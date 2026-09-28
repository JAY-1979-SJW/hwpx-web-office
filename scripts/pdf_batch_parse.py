"""
pdf_batch_parse.py
──────────────────
수집 완료된 PDF를 전수 스캔·파싱하는 배치 실행기.

단계:
  scan  : PDF 디렉터리 재귀 스캔 → pdf_parse_queue.jsonl 생성/갱신
  parse : 큐에서 pending/failed 행을 꺼내 파일별 텍스트·표·메타·OCR fallback 수행
  report: 집계 리포트(JSON/CSV) 생성

사용:
  python pdf_batch_parse.py scan   --root ~/Downloads/kpi_pdf --work ~/Downloads/pdf_batch
  python pdf_batch_parse.py parse  --work ~/Downloads/pdf_batch --workers 4
  python pdf_batch_parse.py report --work ~/Downloads/pdf_batch

원칙:
  - 원본 PDF는 읽기 전용 (수정 금지)
  - 실패를 숨기지 않는다: error_type/error_message를 반드시 기록
  - OCR은 fallback: 텍스트 길이가 페이지당 임계치 미만이거나 추출 예외 시에만
  - 재실행 안전: 큐의 parse_status가 success/partial/skipped 인 행은 건너뜀
  - 원자적 상태 저장: 큐는 .tmp 쓰기 후 os.replace
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

# ── 상수 ──────────────────────────────────────────────────────────────────────
OCR_MIN_CHARS_PER_PAGE = 20  # 페이지당 이 미만이면 OCR fallback 대상
OCR_MAX_PAGES = 30  # OCR 과부하 방지: 상한
TABLE_MAX_PAGES = 50  # 표 추출 페이지 상한 (대형 PDF 병목 방지)
SNIPPET_CHARS = 400


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def short_id(path: Path, size: int, mtime: float) -> str:
    h = hashlib.sha1()
    h.update(str(path).encode("utf-8", "replace"))
    h.update(f"|{size}|{int(mtime)}".encode())
    return h.hexdigest()[:16]


def file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


# ── scan ─────────────────────────────────────────────────────────────────────
def _load_existing_queue(queue_path: Path) -> dict[str, dict]:
    existing: dict[str, dict] = {}
    with queue_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing[r["file_path"]] = r
    return existing


def _scan_one_pdf(p: Path, existing: dict[str, dict]) -> tuple[dict, str]:
    """단일 PDF 파일 처리. (row, category) 반환 — category: stat_error/skipped_small/reused/new."""
    try:
        st = p.stat()
    except OSError as e:
        return {
            "file_id": short_id(p, 0, 0),
            "file_path": str(p),
            "file_name": p.name,
            "file_size": 0,
            "modified_at": None,
            "file_hash": None,
            "parse_status": "failed",
            "error_type": "stat_error",
            "error_message": str(e),
            "queued_at": now_iso(),
        }, "stat_error"
    if st.st_size < 1024:
        return {
            "file_id": short_id(p, st.st_size, st.st_mtime),
            "file_path": str(p),
            "file_name": p.name,
            "file_size": st.st_size,
            "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "file_hash": None,
            "parse_status": "skipped",
            "error_type": "tiny_file",
            "error_message": f"size<{1024}",
            "queued_at": now_iso(),
        }, "skipped_small"
    key = str(p)
    prev = existing.get(key)
    fid = short_id(p, st.st_size, st.st_mtime)
    if (
        prev
        and prev.get("file_id") == fid
        and prev.get("parse_status") in ("success", "partial", "skipped")
    ):
        return prev, "reused"
    return {
        "file_id": fid,
        "file_path": key,
        "file_name": p.name,
        "file_size": st.st_size,
        "modified_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        "file_hash": None,  # sha256은 parse 단계에서 채움(비용)
        "parse_status": "pending",
        "queued_at": now_iso(),
    }, "new"


def cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    work = Path(args.work).expanduser().resolve()
    if not root.is_dir():
        print(f"[scan] ERROR: root not found: {root}", file=sys.stderr)
        return 2
    work.mkdir(parents=True, exist_ok=True)
    queue_path = work / "pdf_parse_queue.jsonl"

    existing: dict[str, dict] = {}
    if queue_path.exists() and not args.rebuild:
        existing = _load_existing_queue(queue_path)

    rows: list[dict] = []
    found = 0
    new_cnt = 0
    reuse_cnt = 0
    skipped_small = 0

    for p in root.rglob("*.pdf"):
        if not p.is_file():
            continue
        found += 1
        row, category = _scan_one_pdf(p, existing)
        rows.append(row)
        if category == "skipped_small":
            skipped_small += 1
        elif category == "reused":
            reuse_cnt += 1
        elif category == "new":
            new_cnt += 1

    tmp = queue_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    Path(tmp).replace(queue_path)

    print(f"[scan] root           : {root}")
    print(f"[scan] queue          : {queue_path}")
    print(f"[scan] 총 PDF         : {found:,}")
    print(f"[scan] 신규/재처리대상: {new_cnt:,}")
    print(f"[scan] 재사용(완결)   : {reuse_cnt:,}")
    print(f"[scan] 1KB 미만 skip  : {skipped_small:,}")
    return 0


# ── parse (워커 진입) ────────────────────────────────────────────────────────
@dataclass
class ParseResult:
    file_id: str
    file_name: str
    source_path: str
    parse_status: str  # success | partial | failed | skipped
    text_extracted: bool
    text_length: int
    table_count: int
    used_ocr: bool
    ocr_reason: str | None
    page_count: int | None
    error_type: str | None
    error_message: str | None
    parsed_at: str
    file_hash: str | None = None
    text_snippet: str | None = None
    duration_ms: int | None = None


def _safe_text_len(s: str) -> int:
    if not s:
        return 0
    # 공백/제어문자 제외하고 의미있는 문자 수
    return len(re.sub(r"\s", "", s))


def _parse_one(task: dict, work_dir: str, ocr_enabled: bool) -> dict:
    """단일 PDF 처리. 예외는 내부에서 모두 잡아 result로 반환."""
    t0 = time.time()
    src = Path(task["file_path"])
    work = Path(work_dir)
    parsed_dir = work / "output" / "pdf_parsed"
    text_dir = work / "output" / "pdf_text"
    tables_dir = work / "output" / "pdf_tables"
    logs_dir = work / "output" / "pdf_logs"
    for d in (parsed_dir, text_dir, tables_dir, logs_dir):
        d.mkdir(parents=True, exist_ok=True)

    fid = task["file_id"]
    log_path = logs_dir / f"{fid}.log"

    def log(msg: str):
        with log_path.open("a", encoding="utf-8") as lf:
            lf.write(f"[{now_iso()}] {msg}\n")

    log(f"START file={src}")

    # 열기 + 메타
    try:
        import fitz  # PyMuPDF
    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        res = ParseResult(
            file_id=fid,
            file_name=src.name,
            source_path=str(src),
            parse_status="failed",
            text_extracted=False,
            text_length=0,
            table_count=0,
            used_ocr=False,
            ocr_reason=None,
            page_count=None,
            error_type="import_error",
            error_message=f"PyMuPDF import failed: {e}",
            parsed_at=now_iso(),
        )
        return asdict(res)

    try:
        doc = fitz.open(str(src))
    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        log(f"OPEN_FAIL {e}")
        res = ParseResult(
            file_id=fid,
            file_name=src.name,
            source_path=str(src),
            parse_status="failed",
            text_extracted=False,
            text_length=0,
            table_count=0,
            used_ocr=False,
            ocr_reason=None,
            page_count=None,
            error_type="open_error",
            error_message=str(e)[:500],
            parsed_at=now_iso(),
            duration_ms=int((time.time() - t0) * 1000),
        )
        return asdict(res)

    page_count = doc.page_count
    # 메타 + 텍스트 추출
    meta = {}
    try:
        meta = dict(doc.metadata or {})
    except Exception:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        meta = {}

    text_parts: list[str] = []
    text_errors: list[str] = []
    for i in range(page_count):
        try:
            text_parts.append(doc[i].get_text("text") or "")
        except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
            text_errors.append(f"page{i + 1}:{type(e).__name__}:{e}")
            text_parts.append("")
    text_all = "\n".join(text_parts)
    text_len = _safe_text_len(text_all)

    used_ocr = False
    ocr_reason: str | None = None
    # OCR fallback 판단
    threshold = OCR_MIN_CHARS_PER_PAGE * max(page_count, 1)
    need_ocr = (text_len < threshold) or (text_errors and text_len == 0)
    if need_ocr and ocr_enabled:
        if page_count > OCR_MAX_PAGES:
            ocr_reason = f"need_ocr_skipped_pages>{OCR_MAX_PAGES}"
            log(f"OCR_SKIP pages={page_count}>{OCR_MAX_PAGES}")
        else:
            ocr_reason = f"text_len<{threshold}"
            log(f"OCR_START reason={ocr_reason}")
            try:
                ocr_text = _run_ocr(src, page_count)
                if ocr_text:
                    # OCR 결과가 기존보다 더 길 때만 채택
                    if _safe_text_len(ocr_text) > text_len:
                        text_all = ocr_text
                        text_len = _safe_text_len(text_all)
                        used_ocr = True
                        log(f"OCR_OK new_len={text_len}")
                    else:
                        log("OCR_DISCARDED not_longer")
            except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
                log(f"OCR_FAIL {type(e).__name__}:{e}")
                text_errors.append(f"ocr:{type(e).__name__}:{e}")

    # 표 추출 (PyMuPDF find_tables — pdfplumber 대비 3-5배 빠름)
    # 페이지 상한 TABLE_MAX_PAGES 초과 시 앞부분만 스캔 (대형 PDF 병목 방지)
    tables: list[dict] = []
    table_errors: list[str] = []
    try:
        n = min(page_count, TABLE_MAX_PAGES)
        if page_count > TABLE_MAX_PAGES:
            table_errors.append(f"truncated_to_first_{TABLE_MAX_PAGES}_pages_of_{page_count}")
        for i in range(n):
            try:
                finder = doc[i].find_tables()
                tlist = getattr(finder, "tables", None) or list(finder)
                for ti, tb in enumerate(tlist):
                    try:
                        rows = tb.extract()
                    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
                        table_errors.append(f"page{i + 1}_tbl{ti}:{type(e).__name__}:{e}")
                        continue
                    tables.append({"page": i + 1, "table_idx": ti, "rows": rows})
            except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
                table_errors.append(f"page{i + 1}:{type(e).__name__}:{e}")
    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        table_errors.append(f"global:{type(e).__name__}:{e}")

    doc.close()

    # 산출물 쓰기
    try:
        (text_dir / f"{fid}.txt").write_text(text_all, encoding="utf-8")
    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        log(f"TEXT_WRITE_FAIL {e}")

    try:
        with (tables_dir / f"{fid}.json").open("w", encoding="utf-8") as tf:
            json.dump(
                {"file_id": fid, "tables": tables, "table_errors": table_errors},
                tf,
                ensure_ascii=False,
            )
    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        log(f"TABLE_WRITE_FAIL {e}")

    # 해시 (성공/부분성공 시에만 기록 — 비용 고려)
    try:
        fhash = file_sha256(src)
    except Exception:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        fhash = None

    # 상태 결정
    error_type = None
    error_message = None
    if text_len == 0 and not tables:
        status = "failed"
        error_type = "no_content"
        error_message = "; ".join(text_errors[:3] + table_errors[:2]) or "empty_text_and_tables"
    elif text_errors or table_errors:
        status = "partial"
        error_type = "partial_extract"
        error_message = "; ".join(text_errors[:3] + table_errors[:2])[:500]
    else:
        status = "success"

    snippet = text_all[:SNIPPET_CHARS].replace("\n", " ")
    res = ParseResult(
        file_id=fid,
        file_name=src.name,
        source_path=str(src),
        parse_status=status,
        text_extracted=(text_len > 0),
        text_length=text_len,
        table_count=len(tables),
        used_ocr=used_ocr,
        ocr_reason=ocr_reason,
        page_count=page_count,
        error_type=error_type,
        error_message=error_message,
        parsed_at=now_iso(),
        file_hash=fhash,
        text_snippet=snippet,
        duration_ms=int((time.time() - t0) * 1000),
    )
    d = asdict(res)
    d["meta"] = {k: v for k, v in meta.items() if isinstance(v, (str, int, float))}
    d["text_errors"] = text_errors[:10]
    d["table_errors"] = table_errors[:10]

    # 파일별 결과 JSON
    try:
        with (parsed_dir / f"{fid}.json").open("w", encoding="utf-8") as pf:
            json.dump(d, pf, ensure_ascii=False)
    except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
        log(f"RESULT_WRITE_FAIL {e}")

    log(
        f"END status={status} text_len={text_len} tables={len(tables)} ocr={used_ocr} dur_ms={d['duration_ms']}"
    )
    return d


def _run_ocr(pdf_path: Path, page_count: int) -> str:
    """pdf2image + pytesseract (kor+eng) — fallback 전용."""
    import pytesseract
    from pdf2image import convert_from_path

    limit = min(page_count, OCR_MAX_PAGES)
    imgs = convert_from_path(str(pdf_path), dpi=200, first_page=1, last_page=limit)
    out = []
    for img in imgs:
        txt = pytesseract.image_to_string(img, lang="kor+eng")
        out.append(txt or "")
    return "\n".join(out)


# ── parse 드라이버 ───────────────────────────────────────────────────────────
def _iter_queue(queue_path: Path) -> Iterable[dict]:
    with queue_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _write_queue(queue_path: Path, rows: list[dict]):
    tmp = queue_path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    Path(tmp).replace(queue_path)


def cmd_parse(args: argparse.Namespace) -> int:
    work = Path(args.work).expanduser().resolve()
    queue_path = work / "pdf_parse_queue.jsonl"
    if not queue_path.exists():
        print(f"[parse] ERROR: queue not found: {queue_path}", file=sys.stderr)
        return 2

    rows = list(_iter_queue(queue_path))
    # 재처리 대상: pending 또는 (failed AND --retry-failed)

    def needs_run(r):
        s = r.get("parse_status")
        if s == "pending":
            return True
        if s == "failed" and args.retry_failed:
            return True
        return False

    todo = [r for r in rows if needs_run(r)]
    if args.limit:
        todo = todo[: args.limit]

    total = len(rows)
    print(f"[parse] queue total={total:,} todo={len(todo):,} workers={args.workers} ocr={args.ocr}")
    if not todo:
        return 0

    # 상태 빠른 반영 위해 index 유지
    idx = {r["file_path"]: i for i, r in enumerate(rows)}
    done = 0
    flush_every = max(10, len(todo) // 50)

    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_parse_one, t, str(work), args.ocr): t for t in todo}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                res = fut.result()
            except Exception as e:  # ruff: ignore[blind-except] -- 이 단계만 기록 후 다음 단계/파일 계속
                res = {
                    "file_id": t["file_id"],
                    "file_name": t["file_name"],
                    "source_path": t["file_path"],
                    "parse_status": "failed",
                    "text_extracted": False,
                    "text_length": 0,
                    "table_count": 0,
                    "used_ocr": False,
                    "ocr_reason": None,
                    "page_count": None,
                    "error_type": "worker_exception",
                    "error_message": f"{type(e).__name__}:{e}",
                    "parsed_at": now_iso(),
                }
            # 큐 행 갱신
            row = rows[idx[t["file_path"]]]
            row["parse_status"] = res["parse_status"]
            row["text_length"] = res.get("text_length")
            row["table_count"] = res.get("table_count")
            row["used_ocr"] = res.get("used_ocr")
            row["ocr_reason"] = res.get("ocr_reason")
            row["page_count"] = res.get("page_count")
            row["error_type"] = res.get("error_type")
            row["error_message"] = res.get("error_message")
            row["file_hash"] = res.get("file_hash") or row.get("file_hash")
            row["parsed_at"] = res.get("parsed_at")
            row["duration_ms"] = res.get("duration_ms")
            done += 1
            if done % flush_every == 0 or done == len(todo):
                _write_queue(queue_path, rows)
                print(
                    f"[parse] progress {done:,}/{len(todo):,} "
                    f"status={res['parse_status']} file={res['file_name']}"
                )

    _write_queue(queue_path, rows)
    print(f"[parse] done {done:,}/{len(todo):,}")
    return 0


# ── report ───────────────────────────────────────────────────────────────────
def cmd_report(args: argparse.Namespace) -> int:
    work = Path(args.work).expanduser().resolve()
    queue_path = work / "pdf_parse_queue.jsonl"
    if not queue_path.exists():
        print(f"[report] ERROR: queue not found: {queue_path}", file=sys.stderr)
        return 2
    rows = list(_iter_queue(queue_path))

    total = len(rows)
    counts = {"success": 0, "partial": 0, "failed": 0, "skipped": 0, "pending": 0}
    ocr_used = 0
    table_ok = 0
    text_lens = []
    err_reason = {}
    for r in rows:
        s = r.get("parse_status", "pending")
        counts[s] = counts.get(s, 0) + 1
        if r.get("used_ocr"):
            ocr_used += 1
        if (r.get("table_count") or 0) > 0:
            table_ok += 1
        tl = r.get("text_length")
        if isinstance(tl, int):
            text_lens.append(tl)
        if s in ("failed", "partial"):
            k = r.get("error_type") or "unknown"
            err_reason[k] = err_reason.get(k, 0) + 1

    avg_text = int(sum(text_lens) / len(text_lens)) if text_lens else 0
    top5 = sorted(err_reason.items(), key=lambda kv: kv[1], reverse=True)[:5]

    summary = {
        "generated_at": now_iso(),
        "total": total,
        "counts": counts,
        "ocr_used": ocr_used,
        "table_extracted": table_ok,
        "avg_text_length": avg_text,
        "top_failure_reasons": top5,
    }
    out_json = work / "output" / "pdf_parse_report.json"
    out_csv = work / "output" / "pdf_parse_report.csv"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with out_json.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    fieldnames = [
        "file_id",
        "file_name",
        "file_path",
        "file_size",
        "modified_at",
        "page_count",
        "parse_status",
        "text_length",
        "table_count",
        "used_ocr",
        "ocr_reason",
        "error_type",
        "error_message",
        "duration_ms",
        "parsed_at",
    ]
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"[report] total           : {total:,}")
    for k, v in counts.items():
        print(f"[report] {k:<15s}: {v:,}")
    print(f"[report] OCR used       : {ocr_used:,}")
    print(f"[report] table_extracted: {table_ok:,}")
    print(f"[report] avg_text_length: {avg_text:,}")
    print(f"[report] top failures   : {top5}")
    print(f"[report] summary JSON   : {out_json}")
    print(f"[report] detail  CSV    : {out_csv}")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser(description="PDF 배치 파싱기 (scan/parse/report)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_scan = sub.add_parser("scan", help="PDF 디렉터리 스캔 → 큐 생성/갱신")
    ap_scan.add_argument("--root", required=True)
    ap_scan.add_argument("--work", required=True)
    ap_scan.add_argument("--rebuild", action="store_true", help="기존 큐 무시하고 재생성")
    ap_scan.set_defaults(func=cmd_scan)

    ap_parse = sub.add_parser("parse", help="큐 pending/failed 재처리")
    ap_parse.add_argument("--work", required=True)
    ap_parse.add_argument("--workers", type=int, default=4)
    ap_parse.add_argument("--limit", type=int, default=0, help="처리 건수 상한 (0=무제한)")
    ap_parse.add_argument("--retry-failed", action="store_true", help="failed 행도 재시도")
    ap_parse.add_argument(
        "--ocr",
        dest="ocr",
        action="store_true",
        default=True,
        help="OCR fallback 활성화 (default: on)",
    )
    ap_parse.add_argument(
        "--no-ocr", dest="ocr", action="store_false", help="OCR fallback 비활성화"
    )
    ap_parse.set_defaults(func=cmd_parse)

    ap_rep = sub.add_parser("report", help="집계 리포트 생성")
    ap_rep.add_argument("--work", required=True)
    ap_rep.set_defaults(func=cmd_report)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
