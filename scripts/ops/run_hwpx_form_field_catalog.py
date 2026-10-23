"""
HWPX-FORM-FIELD-CATALOG-SEED-01 — 실행 스크립트

출력: data/reports/hwpx_form_field_catalog/
  form_field_catalog.jsonl  — 서식별 전체 카탈로그
  form_field_catalog_summary.json
  form_field_catalog_summary.md
  notable_forms.json        — 필드 수 상위 30개 서식 상세
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from hwpx.recognition_corpus.form_field_catalog import (
    build_catalog,
    build_summary,
)

DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "reports" / "hwpx_form_field_catalog"


def run(output_dir: Path, dry_run: bool, verbose: bool) -> int:
    print("[run] 서식 필드 카탈로그 빌드 시작...")
    catalog = build_catalog(verbose=verbose)
    summary = build_summary(catalog)

    print(f"[run] 완료: {summary['totalForms']}개 서식, "
          f"{summary['totalFields']}개 필드 "
          f"(필수 {summary['requiredFields']}개, "
          f"서식당 평균 {summary['avgFieldsPerForm']}개)")
    print(f"      필드 있는 서식: {summary['formsWithFields']}개 "
          f"/ 필드 없는 서식: {summary['totalForms'] - summary['formsWithFields']}개")

    if dry_run:
        # 샘플 출력
        for e in catalog[:3]:
            d = e.to_dict()
            print(f"\n  [{d['domain']}] {d['formName']} — 필드 {d['fieldCount']}개 "
                  f"(필수 {d['requiredCount']}개)")
            for f in d["fields"][:5]:
                req = "★" if f["required"] else "○"
                auto = "✓" if f["autoFillable"] else " "
                sem = f.get("semanticField", "") or "-"
                print(f"    {req}{auto} {f['primaryLabel']!r:20s}  sem={sem:20s}  파일 {f['fileOccurrenceCount']}개")
        print("\n[dry_run] 출력 생략")
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)

    # JSONL
    out_jsonl = output_dir / "form_field_catalog.jsonl"
    with out_jsonl.open("w", encoding="utf-8") as fh:
        for e in catalog:
            fh.write(json.dumps(e.to_dict(), ensure_ascii=False) + "\n")
    print(f"[출력] {out_jsonl}")

    # summary JSON
    out_json = output_dir / "form_field_catalog_summary.json"
    out_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[출력] {out_json}")

    # summary MD
    md = _build_md(summary)
    out_md = output_dir / "form_field_catalog_summary.md"
    out_md.write_text(md, encoding="utf-8")
    print(f"[출력] {out_md}")

    # notable forms (필드 수 상위 30개)
    notable = sorted(catalog, key=lambda e: -len(e.fields))[:30]
    out_notable = output_dir / "notable_forms.json"
    out_notable.write_text(
        json.dumps([e.to_dict() for e in notable], ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[출력] {out_notable}")

    return 0


def _build_md(s: dict) -> str:
    lines = [
        "# HWPX 서식 필드 카탈로그 요약\n",
        f"- 서식 수: **{s['totalForms']}개** (필드 보유: {s['formsWithFields']}개)",
        f"- 전체 필드: **{s['totalFields']}개** (필수 {s['requiredFields']}개)",
        f"- 서식당 평균 필드: **{s['avgFieldsPerForm']}개**",
        "",
        "## 도메인별",
        "| 도메인 | 서식 수 |",
        "|--------|---------|",
    ]
    for d, c in s["domainCounts"].items():
        lines.append(f"| {d} | {c} |")
    lines += [
        "",
        "## 서식종류별",
        "| 종류 | 서식 수 |",
        "|------|---------|",
    ]
    for k, c in s["formKindCounts"].items():
        lines.append(f"| {k} | {c} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="HWPX 서식 필드 카탈로그 빌드")
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--dry-run",    action="store_true")
    ap.add_argument("--verbose",    action="store_true")
    args = ap.parse_args()
    return run(args.output_dir, args.dry_run, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
