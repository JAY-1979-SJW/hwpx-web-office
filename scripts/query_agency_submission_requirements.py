from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_requirements(package_dir: Path) -> list[dict[str, Any]]:
    path = package_dir / "03_입력요구사항" / "문서별_입력요구사항.json"
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def matches(row: dict[str, Any], query: str | None, trade: str | None, no: str | None) -> bool:
    if no and str(row["no"]) != str(no):
        return False
    if trade and trade not in row.get("trade", ""):
        return False
    if query:
        haystack = " ".join(
            [
                row.get("title", ""),
                row.get("trade", ""),
                row.get("agency", ""),
                row.get("phase", ""),
                " ".join(row.get("user_required_fields", [])),
                " ".join(row.get("required_attachments", [])),
            ]
        )
        if norm(query) not in norm(haystack):
            return False
    return True


def render_request(row: dict[str, Any]) -> str:
    lines = [
        f"# 사용자 자료 요청서 - {row['title']}",
        "",
        f"- 문서번호: {row['no']}",
        f"- 공종: {row['trade']}",
        f"- 제출처: {row['agency']}",
        f"- 제출시점: {row['phase']}",
        f"- 우선순위: {row['input_priority']}",
        f"- 원본 파일: `{row['file_path']}`",
        f"- 본문 확인: {'완료' if row.get('body_verified') else '미완료'}",
        "",
        "## 사용자가 제공해야 할 입력값",
        "",
    ]
    for idx, field in enumerate(row.get("user_required_fields", []), start=1):
        lines.append(f"{idx}. {field}: ")
    lines.extend(["", "## 자동입력 가능 공통값", ""])
    auto_fields = row.get("auto_fill_fields", [])
    if auto_fields:
        for field in auto_fields:
            lines.append(f"- {field}")
    else:
        lines.append("- 없음")
    lines.extend(["", "## 첨부/필요서류 확인", ""])
    for idx, attachment in enumerate(row.get("required_attachments", []), start=1):
        lines.append(f"{idx}. [ ] {attachment}")
    lines.extend(["", "## 입력 검증 기준", ""])
    for rule in row.get("validation_rules", []):
        lines.append(f"- {rule}")
    lines.extend(["", "## 사용자 안내 문구", "", row.get("user_prompt", "")])
    return "\n".join(lines).strip() + "\n"


def write_outputs(package_dir: Path, rows: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    for row in rows:
        filename = f"{int(row['no']):03d}_{re.sub(r'[\\\\/:*?\"<>|]+', '_', row['title'])[:80]}_자료요청서.md"
        path = output_dir / filename
        path.write_text(render_request(row), encoding="utf-8")
        summary.append(
            {
                "no": row["no"],
                "trade": row["trade"],
                "title": row["title"],
                "request_file": str(path.relative_to(package_dir)),
                "required_field_count": len(row.get("user_required_fields", [])),
                "attachment_count": len(row.get("required_attachments", [])),
            }
        )
    (output_dir / "자료요청서_생성목록.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="문서별 사용자 자료 요청서 생성")
    parser.add_argument("--package-dir", default="deliverables/기관제출서류_기관별확장_로컬패키지")
    parser.add_argument("--query", default="", help="문서명/입력항목/첨부서류 검색어")
    parser.add_argument("--trade", default="", help="공종 필터")
    parser.add_argument("--no", default="", help="문서번호")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--write", action="store_true", help="자료요청서 md 파일 생성")
    parser.add_argument("--output-dir", default="05_사용자자료요청")
    args = parser.parse_args()

    package_dir = ROOT / args.package_dir
    rows = [
        row
        for row in load_requirements(package_dir)
        if matches(row, args.query or None, args.trade or None, args.no or None)
    ]
    rows = rows[: args.limit if args.limit > 0 else None]
    for row in rows:
        print(f"{row['no']}\t{row['trade']}\t{row['title']}")
        print(f"  입력값 {len(row.get('user_required_fields', []))}개: {', '.join(row.get('user_required_fields', [])[:10])}")
        print(f"  첨부 {len(row.get('required_attachments', []))}개: {', '.join(row.get('required_attachments', [])[:5])}")
    if args.write:
        output_dir = package_dir / args.output_dir
        write_outputs(package_dir, rows, output_dir)
        print(f"written={len(rows)}")
        print(f"output_dir={output_dir}")


if __name__ == "__main__":
    main()
