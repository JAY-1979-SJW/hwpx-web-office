from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


AGENCY_BY_TRADE = {
    "건축": "시군구 건축허가 부서 / 허가권자",
    "소방": "관할 소방서 / 소방본부",
    "전기": "한국전기안전공사 / 한전 / 전기 인허가 기관",
    "기계설비": "시군구 기계설비 담당 부서 / 허가권자",
    "정보통신": "시군구 정보통신공사 사용전검사 담당 부서",
    "가스": "한국가스안전공사 / 시군구 가스 인허가 부서",
    "승강기": "한국승강기안전공단 / 승강기민원24",
    "상하수도/수자원": "시군구 상하수도 부서 / K-water 관련 부서",
    "폐기물/환경": "지자체 환경 부서 / 유역·지방환경청",
    "안전/노동": "고용노동부 / 산업안전보건공단 / 발주자",
    "건설공사 공통관리": "발주청 / 인허가기관 / 건설사업관리단",
}


PHASE_RULES = [
    ("인허가·승인", ["허가", "승인", "인가", "인증", "면제"]),
    ("신고", ["신고"]),
    ("착공 전", ["착공", "공사계획", "설치", "유해위험방지계획", "직접시공계획"]),
    ("시공 중", ["감리", "배치", "협의", "점검", "개선", "가동", "사용개시"]),
    ("검사·사용 전", ["사용전", "사용 전", "완성검사", "완공검사", "설치검사", "정기검사", "안전검사"]),
    ("준공·사용승인", ["사용승인", "완공", "준공"]),
    ("실적·보고", ["보고", "실적", "이행", "완료"]),
    ("변경·연장", ["변경", "연장"]),
    ("폐지·중지", ["폐지", "중지", "재개"]),
]


def slugify(value: str, limit: int = 90) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', "_", value)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    cleaned = cleaned[:limit].rstrip("._ ")
    return cleaned or "untitled"


def infer_phase(title: str) -> str:
    matches = [phase for phase, terms in PHASE_RULES if any(term in title for term in terms)]
    return " / ".join(dict.fromkeys(matches)) if matches else "기타 제출"


def keywords(row: dict[str, Any]) -> list[str]:
    text = f"{row.get('trade', '')} {row.get('law_name', '')} {row.get('title', '')}"
    tokens = re.split(r"[\s\[\]\(\),ㆍ/·]+", text)
    keep = []
    for token in tokens:
        token = token.strip()
        if len(token) >= 2 and token not in keep:
            keep.append(token)
    return keep[:40]


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [row for row in rows if row.get("path") or row.get("submission_path")]


def source_path(row: dict[str, Any]) -> Path:
    for key in ("submission_path", "path"):
        value = row.get(key)
        if not value:
            continue
        path = Path(value)
        if path.is_absolute():
            return path
        return ROOT / path
    raise ValueError("missing path")


def build_package(rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    forms_root = output_dir / "01_공종별"
    toc_root = output_dir / "00_목차"
    toc_root.mkdir(parents=True, exist_ok=True)

    indexed: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        src = source_path(row)
        if not src.is_file():
            continue
        trade = row.get("trade", "미분류")
        law_name = row.get("law_name", "미분류")
        title = row.get("title", src.stem)
        phase = infer_phase(title)
        agency = AGENCY_BY_TRADE.get(trade, "관할 기관 확인 필요")
        dst_dir = forms_root / slugify(trade, 50) / slugify(law_name, 80)
        dst_name = f"{index:03d}_{slugify(title, 120)}{src.suffix.lower()}"
        dst = dst_dir / dst_name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        indexed.append(
            {
                "no": index,
                "trade": trade,
                "agency": agency,
                "phase": phase,
                "law_name": law_name,
                "title": title,
                "file_path": str(dst.relative_to(output_dir)),
                "source_url": row.get("url", ""),
                "source_lsi_seq": row.get("lsi_seq", ""),
                "source_jo_link": row.get("jo_link", ""),
                "keywords": "|".join(keywords(row)),
            }
        )
    return indexed


def write_indexes(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    toc_root = output_dir / "00_목차"
    csv_path = toc_root / "공종별_기관제출서식_인덱스.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()) if rows else ["no"])
        writer.writeheader()
        writer.writerows(rows)

    search_rows = [
        {
            "no": row["no"],
            "trade": row["trade"],
            "agency": row["agency"],
            "phase": row["phase"],
            "title": row["title"],
            "file_path": row["file_path"],
            "keywords": row["keywords"].split("|") if row["keywords"] else [],
        }
        for row in rows
    ]
    (toc_root / "검색인덱스.json").write_text(
        json.dumps(search_rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["trade"], []).append(row)

    lines = [
        "# 기관 제출서류 목차",
        "",
        f"- 총 HWP 서식: {len(rows)}개",
        "- 구조: `01_공종별/<공종>/<근거 법령>/<서식 파일>`",
        "- 검색용 CSV: `00_목차/공종별_기관제출서식_인덱스.csv`",
        "- 검색용 JSON: `00_목차/검색인덱스.json`",
        "",
        "## 공종별 요약",
        "",
        "| 공종 | 수량 | 주 제출처 |",
        "| --- | ---: | --- |",
    ]
    for trade in sorted(grouped):
        lines.append(f"| {trade} | {len(grouped[trade])} | {AGENCY_BY_TRADE.get(trade, '관할 기관 확인 필요')} |")
    lines.extend(["", "## 상세 목차", ""])
    for trade in sorted(grouped):
        lines.extend([f"### {trade}", "", "| No | 제출시점 | 서식 | 파일 |", "| ---: | --- | --- | --- |"])
        for row in grouped[trade]:
            lines.append(f"| {row['no']} | {row['phase']} | {row['title']} | `{row['file_path']}` |")
        lines.append("")
    (toc_root / "기관제출서류_목차.md").write_text("\n".join(lines), encoding="utf-8")

    readme = [
        "# 기관 제출서류 로컬 패키지",
        "",
        "이 폴더는 법제처 HWP 원본 중 기관 제출용 후보만 별도 분류한 로컬 작업본이다.",
        "",
        "## 사용 순서",
        "",
        "1. `00_목차/기관제출서류_목차.md`에서 공종과 제출시점을 확인한다.",
        "2. 빠른 검색은 `00_목차/공종별_기관제출서식_인덱스.csv`를 엑셀로 연다.",
        "3. 원본 HWP는 `01_공종별` 아래에서 공종과 근거 법령별로 찾는다.",
        "",
        "## 주의",
        "",
        "기관 홈페이지 자체 양식과 법정 별지 양식이 다른 경우가 있으므로, 실제 제출 전 관할기관 공고/민원 안내와 대조해야 한다.",
    ]
    (output_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default="tmp/agency_submission_law_byl_hwp_submission_only_expanded_final_v2/submission_manifest.json",
    )
    parser.add_argument(
        "--output-dir",
        default="deliverables/기관제출서류_기관별확장_로컬패키지",
    )
    args = parser.parse_args()

    rows = load_rows(ROOT / args.manifest)
    output_dir = ROOT / args.output_dir
    indexed = build_package(rows, output_dir)
    write_indexes(output_dir, indexed)
    print(f"output_dir={output_dir}")
    print(f"forms={len(indexed)}")
    print(f"toc={output_dir / '00_목차' / '기관제출서류_목차.md'}")
    print(f"csv={output_dir / '00_목차' / '공종별_기관제출서식_인덱스.csv'}")


if __name__ == "__main__":
    main()
