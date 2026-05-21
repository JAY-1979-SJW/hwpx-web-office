from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


EXTENSION_POLICY = [
    {
        "extension": ".hwp",
        "role": "기관 원본 한글 양식",
        "policy": "원본 보관. 자동 입력이 필요하면 hwpx 변환본을 별도 생성하고 원본은 유지한다.",
    },
    {
        "extension": ".hwpx",
        "role": "자동 입력/생성 가능한 한글 문서",
        "policy": "표 입력, 체크리스트, 공문, 제출목록 자동 생성 대상으로 사용한다.",
    },
    {
        "extension": ".pdf",
        "role": "고시/안내문/스캔 증빙/발급문서",
        "policy": "원본 제출 또는 참조용으로 보관. 텍스트 추출은 보조 처리만 수행한다.",
    },
    {
        "extension": ".docx",
        "role": "워드 양식/공문",
        "policy": "원본 포맷 유지. 필요 시 PDF 또는 HWPX 변환본을 별도 생성한다.",
    },
    {
        "extension": ".xlsx",
        "role": "내역서/목록/집계표",
        "policy": "수량표, 제출목록, 점검표, 공정표 등 표 중심 자료로 유지한다.",
    },
    {
        "extension": ".xls",
        "role": "구형 엑셀 양식",
        "policy": "원본 보관. 편집/자동화가 필요하면 xlsx 변환본을 별도 생성한다.",
    },
    {
        "extension": ".dwg",
        "role": "CAD 도면",
        "policy": "도면 원본으로 보관하고 제출목록에 도면번호/버전을 기록한다.",
    },
    {
        "extension": ".zip",
        "role": "기관 제출 묶음/전자납품",
        "policy": "제출 단위별 묶음 결과물로 사용한다. 내부 파일 목록 매니페스트를 함께 보관한다.",
    },
    {
        "extension": ".jpg/.png",
        "role": "사진대지/현장사진",
        "policy": "촬영일, 위치, 공종, 설명을 메타데이터 또는 제출목록에 기록한다.",
    },
]


DOCUMENT_EXTENSION_HINTS = [
    ("도면", [".dwg", ".pdf", ".hwpx"]),
    ("설계도서", [".pdf", ".dwg", ".hwpx"]),
    ("내역", [".xlsx", ".pdf"]),
    ("정산", [".xlsx", ".pdf"]),
    ("수불부", [".xlsx"]),
    ("공정표", [".xlsx", ".hwpx", ".pdf"]),
    ("사진", [".jpg", ".png", ".pdf", ".hwpx"]),
    ("성적서", [".pdf"]),
    ("확인증", [".pdf"]),
    ("증명서", [".pdf"]),
    ("신고필증", [".pdf"]),
    ("계약서", [".pdf"]),
    ("신청서", [".hwp", ".hwpx", ".pdf"]),
    ("신고서", [".hwp", ".hwpx", ".pdf"]),
    ("계획서", [".hwp", ".hwpx", ".pdf"]),
    ("보고서", [".hwp", ".hwpx", ".pdf"]),
    ("체크리스트", [".xlsx", ".hwpx", ".pdf"]),
]


def slugify(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "미분류"


def infer_expected_extensions(document: str) -> list[str]:
    matched: list[str] = []
    for keyword, extensions in DOCUMENT_EXTENSION_HINTS:
        if keyword in document:
            matched.extend(extensions)
    if not matched:
        matched.extend([".hwp", ".hwpx", ".pdf"])
    return list(dict.fromkeys(matched))


def load_phase_index(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_primary_order_rows(phase_index: dict[str, Any]) -> list[dict[str, Any]]:
    stage_names = phase_index["stage_names"]
    stage_order = {stage["stage_id"]: index for index, stage in enumerate(phase_index["stages"], start=1)}
    rows: list[dict[str, Any]] = []
    for trade in phase_index["trades"]:
        for item in trade["documents"]:
            primary_stage_id = item["primary_stage_id"]
            rows.append(
                {
                    "order": stage_order[primary_stage_id],
                    "stage_name": stage_names[primary_stage_id],
                    "trade_name": trade["trade_name"],
                    "document": item["document"],
                    "phase_source": item.get("phase_source", ""),
                    "phases": "; ".join(item.get("effective_phases", [])),
                    "submit_to": "; ".join(item.get("submit_to", [])),
                    "expected_extensions": "; ".join(infer_expected_extensions(item["document"])),
                    "status": "missing",
                    "assigned_file": "",
                    "note": "원본 양식 또는 증빙파일 배치 필요",
                }
            )
    rows.sort(key=lambda row: (row["order"], row["trade_name"], row["document"]))
    return rows


def write_extension_policy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["extension", "role", "policy"])
        writer.writeheader()
        writer.writerows(EXTENSION_POLICY)


def write_missing_checklist(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "order",
                "stage_name",
                "trade_name",
                "document",
                "expected_extensions",
                "submit_to",
                "phase_source",
                "phases",
                "status",
                "assigned_file",
                "note",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def write_readme(path: Path, rows: list[dict[str, Any]]) -> None:
    by_trade: dict[str, int] = defaultdict(int)
    by_stage: dict[str, int] = defaultdict(int)
    for row in rows:
        by_trade[row["trade_name"]] += 1
        by_stage[row["stage_name"]] += 1

    lines = [
        "# 기관 제출서류 패키지 구조",
        "",
        f"- 생성일: {date.today().isoformat()}",
        f"- 제출서류 행 수: {len(rows)}",
        "",
        "## 사용 원칙",
        "",
        "- 기관 원본 양식은 원본 확장자를 유지한다.",
        "- 자동 입력이 필요한 문서만 HWPX 변환본 또는 생성본을 별도로 둔다.",
        "- PDF, DOCX, XLSX, DWG, 이미지 증빙은 제출처 요구 형식을 우선한다.",
        "- 각 제출 폴더에는 `제출목록.csv`와 실제 파일을 함께 둔다.",
        "",
        "## 폴더",
        "",
        "- `00_확장자_처리정책`: 확장자별 보관/변환/제출 정책",
        "- `01_공종별`: 공종별 제출 패키지",
        "- `02_제출순서별`: 제출 단계별 패키지",
        "- `03_누락점검`: 원본 양식/증빙 배치 전 누락 체크리스트",
        "",
        "## 공종별 문서 수",
        "",
    ]
    for trade_name, count in sorted(by_trade.items()):
        lines.append(f"- {trade_name}: {count}건")

    lines.extend(["", "## 제출순서별 문서 수", ""])
    for stage_name, count in sorted(by_stage.items()):
        lines.append(f"- {stage_name}: {count}건")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def create_package_structure(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "00_확장자_처리정책").mkdir(parents=True, exist_ok=True)
    (output_dir / "01_공종별").mkdir(parents=True, exist_ok=True)
    (output_dir / "02_제출순서별").mkdir(parents=True, exist_ok=True)
    (output_dir / "03_누락점검").mkdir(parents=True, exist_ok=True)

    write_extension_policy(output_dir / "00_확장자_처리정책" / "확장자_처리정책.csv")
    write_missing_checklist(output_dir / "03_누락점검" / "기관제출서류_누락점검표.csv", rows)
    write_readme(output_dir / "README.md", rows)

    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_trade[row["trade_name"]].append(row)
        by_stage[f"{row['order']:02d}_{row['stage_name']}"].append(row)

    for trade_name, trade_rows in by_trade.items():
        trade_dir = output_dir / "01_공종별" / slugify(trade_name)
        trade_dir.mkdir(parents=True, exist_ok=True)
        write_missing_checklist(trade_dir / "제출목록.csv", trade_rows)
        (trade_dir / "원본양식").mkdir(exist_ok=True)
        (trade_dir / "증빙").mkdir(exist_ok=True)
        (trade_dir / "생성문서").mkdir(exist_ok=True)

    for stage_name, stage_rows in by_stage.items():
        stage_dir = output_dir / "02_제출순서별" / slugify(stage_name)
        stage_dir.mkdir(parents=True, exist_ok=True)
        write_missing_checklist(stage_dir / "제출목록.csv", stage_rows)
        (stage_dir / "원본양식").mkdir(exist_ok=True)
        (stage_dir / "증빙").mkdir(exist_ok=True)
        (stage_dir / "생성문서").mkdir(exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--phase-index",
        default="data/agency_submission_phase_situation_index.web_expanded.json",
    )
    parser.add_argument(
        "--output-dir",
        default="tmp/agency_submission_institution_package_structure",
    )
    args = parser.parse_args()

    phase_index = load_phase_index(Path(args.phase_index))
    rows = iter_primary_order_rows(phase_index)
    create_package_structure(Path(args.output_dir), rows)
    print(f"wrote {args.output_dir}")
    print(f"document_rows={len(rows)}")
    print(f"trade_count={len({row['trade_name'] for row in rows})}")
    print(f"stage_count={len({row['stage_name'] for row in rows})}")


if __name__ == "__main__":
    main()
