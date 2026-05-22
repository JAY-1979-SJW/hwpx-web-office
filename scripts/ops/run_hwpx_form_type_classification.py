"""
HWPX-FORM-TYPE-CLASSIFICATION-01 — 실행 스크립트

파일명 기반으로 data/drafts 전체 파일의 서식 유형을 분류하고
data/reports/hwpx_form_type_classification/ 에 출력.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from hwpx.recognition_corpus.form_type_classifier import (
    classify_form_type,
    build_summary,
    FormTypeResult,
)

DEFAULT_INPUT  = PROJECT_ROOT / "data" / "drafts"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reports" / "hwpx_form_type_classification"


def _mask_id(path: Path, idx: int) -> str:
    h = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:10]
    return f"f{idx:05d}_{h}"


def run(input_dir: Path, output_dir: Path, limit: int, dry_run: bool) -> int:
    files = sorted(input_dir.rglob("*.hwpx"))
    if limit:
        files = files[:limit]

    print(f"[run] {len(files)}개 파일 서식 유형 분류 시작 (dry_run={dry_run})")

    results: list[FormTypeResult] = []
    for i, p in enumerate(files):
        mid = _mask_id(p, i)
        r = classify_form_type(p, mid)
        results.append(r)

    summary = build_summary(results)
    print(f"[run] 완료: {summary['totalFiles']}개, 별지서식 {summary['byeoljiFiles']}개")
    print(f"      도메인 기타: {summary['unknownDomain']}개, 서식종류 기타: {summary['unknownKind']}개")

    if dry_run:
        print("[dry_run] 출력 생략")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    # per-file JSONL
    out_jsonl = output_dir / "per_file_form_type.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    print(f"[출력] {out_jsonl}")

    # summary JSON
    out_json = output_dir / "form_type_summary.json"
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[출력] {out_json}")

    # summary MD
    md_lines = [
        "# HWPX 서식 유형 분류 요약\n",
        f"- 전체 파일: {summary['totalFiles']}개",
        f"- 별지서식 파일: {summary['byeoljiFiles']}개",
        "",
        "## 도메인별",
        "| 도메인 | 파일 수 |",
        "|--------|---------|",
    ]
    for d, c in summary["domainCounts"].items():
        md_lines.append(f"| {d} | {c} |")
    md_lines += [
        "",
        "## 서식종류별",
        "| 서식종류 | 파일 수 |",
        "|----------|---------|",
    ]
    for k, c in summary["formKindCounts"].items():
        md_lines.append(f"| {k} | {c} |")

    out_md = output_dir / "form_type_summary.md"
    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"[출력] {out_md}")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="HWPX 서식 유형 분류")
    ap.add_argument("--input-dir",  type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--limit",      type=int,  default=0)
    ap.add_argument("--dry-run",    action="store_true")
    args = ap.parse_args()
    return run(args.input_dir, args.output_dir, args.limit, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
