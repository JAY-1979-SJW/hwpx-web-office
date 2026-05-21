from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def join_items(items: list[str]) -> str:
    return " | ".join(item for item in items if item)


def compact_items(items: list[str], limit: int = 14) -> str:
    if len(items) <= limit:
        return ", ".join(items)
    return ", ".join(items[:limit]) + f" 외 {len(items) - limit}개"


def build_rows(package_dir: Path) -> list[dict[str, Any]]:
    req_rows = load_json(package_dir / "03_입력요구사항" / "문서별_입력요구사항.json")
    body_rows = {
        str(row["no"]): row
        for row in load_json(package_dir / "04_본문추출" / "본문기반_입력항목.json")
    }
    rows = []
    for row in req_rows:
        body = body_rows.get(str(row["no"]), {})
        rows.append(
            {
                "문서번호": row["no"],
                "공종": row["trade"],
                "문서명": row["title"],
                "제출처": row["agency"],
                "제출시점": row["phase"],
                "우선순위": row["input_priority"],
                "본문확인": "완료" if row.get("body_verified") else "미완료",
                "입력해야_할_내용": row.get("user_required_fields", []),
                "자동입력_가능_공통값": row.get("auto_fill_fields", []),
                "요구_또는_첨부서류": row.get("required_attachments", []),
                "본문에서_확인된_입력라벨": body.get("body_field_candidates", []),
                "본문에서_확인된_첨부문구": body.get("body_attachment_candidates", []),
                "입력검증기준": row.get("validation_rules", []),
                "원본파일": row["file_path"],
                "본문텍스트": row.get("body_text_path", ""),
                "자료요청서": f"05_사용자자료요청/{int(row['no']):03d}_*.md",
                "입력항목수": len(row.get("user_required_fields", [])),
                "요구서류수": len(row.get("required_attachments", [])),
            }
        )
    return rows


def write_outputs(package_dir: Path, rows: list[dict[str, Any]]) -> None:
    out_dir = package_dir / "06_전체요구사항정리"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_rows = rows
    (out_dir / "문서별_요구서류_입력사항_전체정리.json").write_text(
        json.dumps(json_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    csv_fields = [
        "문서번호",
        "공종",
        "문서명",
        "제출처",
        "제출시점",
        "우선순위",
        "본문확인",
        "입력항목수",
        "요구서류수",
        "입력해야_할_내용",
        "자동입력_가능_공통값",
        "요구_또는_첨부서류",
        "본문에서_확인된_입력라벨",
        "본문에서_확인된_첨부문구",
        "입력검증기준",
        "원본파일",
        "본문텍스트",
        "자료요청서",
    ]
    with (out_dir / "문서별_요구서류_입력사항_전체정리.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=csv_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: join_items(row[field]) if isinstance(row.get(field), list) else row.get(field, "")
                    for field in csv_fields
                }
            )

    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_trade[row["공종"]].append(row)

    lines = [
        "# 문서별 요구서류 및 입력사항 전체 정리",
        "",
        f"- 대상 문서: {len(rows)}개",
        f"- 본문 확인 완료: {sum(1 for row in rows if row['본문확인'] == '완료')}개",
        f"- 전체 입력항목: {sum(row['입력항목수'] for row in rows)}개",
        f"- 전체 요구/첨부서류 항목: {sum(row['요구서류수'] for row in rows)}개",
        "",
        "## 공통 요청자료",
        "",
        "대부분 문서에서 반복되는 공통값은 다음 항목이다. 실제 문서별 추가 입력값은 아래 상세표를 따른다.",
        "",
        "- 공사명",
        "- 현장주소",
        "- 발주자",
        "- 신청인/신고인 인적사항",
        "- 시공자 상호, 대표자, 주소, 연락처",
        "- 제출기관",
        "- 작성일 또는 제출일",
        "",
        "## 공종별 요약",
        "",
        "| 공종 | 문서수 | 입력항목 합계 | 요구서류 합계 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for trade in sorted(by_trade):
        items = by_trade[trade]
        lines.append(
            f"| {trade} | {len(items)} | {sum(row['입력항목수'] for row in items)} | "
            f"{sum(row['요구서류수'] for row in items)} |"
        )

    lines.extend(["", "## 문서별 상세", ""])
    for trade in sorted(by_trade):
        lines.extend([f"### {trade}", ""])
        for row in by_trade[trade]:
            lines.extend(
                [
                    f"#### {row['문서번호']}. {row['문서명']}",
                    "",
                    f"- 제출처: {row['제출처']}",
                    f"- 제출시점: {row['제출시점']}",
                    f"- 우선순위: {row['우선순위']}",
                    f"- 원본파일: `{row['원본파일']}`",
                    f"- 본문텍스트: `{row['본문텍스트']}`",
                    "",
                    "입력해야 할 내용:",
                ]
            )
            for idx, item in enumerate(row["입력해야_할_내용"], start=1):
                lines.append(f"{idx}. {item}")
            lines.extend(["", "요구 또는 첨부서류:"])
            for idx, item in enumerate(row["요구_또는_첨부서류"], start=1):
                lines.append(f"{idx}. {item}")
            lines.extend(["", "요약:", ""])
            lines.append(f"- 입력: {compact_items(row['입력해야_할_내용'])}")
            lines.append(f"- 서류: {compact_items(row['요구_또는_첨부서류'])}")
            lines.append("")

    (out_dir / "문서별_요구서류_입력사항_전체정리.md").write_text(
        "\n".join(lines),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-dir", default="deliverables/기관제출서류_기관별확장_로컬패키지")
    args = parser.parse_args()
    package_dir = ROOT / args.package_dir
    rows = build_rows(package_dir)
    write_outputs(package_dir, rows)
    print(f"package_dir={package_dir}")
    print(f"documents={len(rows)}")
    print(f"input_items={sum(row['입력항목수'] for row in rows)}")
    print(f"attachment_items={sum(row['요구서류수'] for row in rows)}")
    print(f"output_dir={package_dir / '06_전체요구사항정리'}")


if __name__ == "__main__":
    main()
