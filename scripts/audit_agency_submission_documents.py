from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HWP_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")


COMMON_FIELDS = [
    "공사명",
    "현장명",
    "대지위치",
    "신청인",
    "신고인",
    "성명",
    "상호",
    "대표자",
    "주소",
    "전화번호",
    "착공예정일",
    "준공예정일",
    "공사기간",
    "시공자",
    "감리자",
    "설계자",
    "허가번호",
    "신고번호",
    "작성일",
    "제출일",
]


TRADE_FIELDS = {
    "건축": ["건축주", "건축면적", "연면적", "용도", "구조", "층수", "건폐율", "용적률"],
    "소방": ["특정소방대상물", "소방시설 종류", "소방공사감리자", "완공일", "점검기간", "점검자"],
    "전기": ["수전전압", "설비용량", "전기안전관리자", "전기사용장소", "공사계획", "사용전점검일"],
    "기계설비": ["기계설비 종류", "착공 전 확인번호", "검사대상 설비", "사용 전 검사일"],
    "정보통신": ["정보통신공사 종류", "감리원", "사용전검사 대상", "설계도서"],
    "가스": ["가스종류", "저장능력", "시설위치", "시공감리", "완성검사일", "정기검사일"],
    "승강기": ["승강기 종류", "제조업자", "설치장소", "승강기번호", "안전인증번호"],
    "상하수도/수자원": ["배수설비", "급수설비", "처리용량", "유입수량", "상수도관망", "하수관로"],
    "폐기물/환경": ["배출시설", "방지시설", "폐기물 종류", "처리량", "가동개시일", "배출구"],
    "안전/노동": ["공사금액", "공사기간", "유해위험요인", "안전보건관리비", "계획서 작성자"],
    "건설공사 공통관리": ["도급자", "하도급자", "계약금액", "직접시공", "기성실적", "건설사업관리기술인"],
}


TITLE_FIELD_RULES = [
    (["착공"], ["착공일", "착공예정일", "시공자", "감리자"]),
    (["사용승인", "사용전", "사용 전"], ["사용예정일", "검사희망일", "완료일", "검사자"]),
    (["완공", "완성검사"], ["완공일", "완성검사 희망일", "시공내용", "검사대상"]),
    (["감리"], ["감리자", "감리원", "감리기간", "감리결과", "배치기간"]),
    (["점검"], ["점검일", "점검기간", "점검자", "점검결과", "조치사항"]),
    (["변경"], ["변경 전", "변경 후", "변경사유", "변경일"]),
    (["공사계획"], ["공사계획 개요", "공사기간", "설비개요", "도면 첨부"]),
    (["배출", "폐수", "대기", "비산먼지"], ["오염물질", "배출량", "방지시설", "측정결과"]),
    (["하도급"], ["수급인", "하수급인", "하도급금액", "하도급기간", "하도급내용"]),
]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        return list(csv.DictReader(fp))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def infer_fields(row: dict[str, str]) -> list[str]:
    title = row.get("title", "")
    trade = row.get("trade", "")
    fields = [*COMMON_FIELDS, *TRADE_FIELDS.get(trade, [])]
    for terms, extra_fields in TITLE_FIELD_RULES:
        if any(term in title for term in terms):
            fields.extend(extra_fields)
    return unique(fields)


def infer_submitter(title: str) -> str:
    if any(term in title for term in ["감리", "배치"]):
        return "감리자/감리업자/시공자"
    if any(term in title for term in ["점검", "검사"]):
        return "시공자/관리주체/검사 신청자"
    if any(term in title for term in ["허가", "신고", "신청"]):
        return "건축주/사업자/시공자"
    if "보고" in title:
        return "시공자/관리주체"
    return "제출자 확인 필요"


def infer_risks(row: dict[str, str], size: int, duplicate_count: int, signature_ok: bool) -> list[str]:
    title = row.get("title", "")
    risks = []
    if not signature_ok:
        risks.append("HWP 시그니처 불일치")
    if duplicate_count > 1:
        risks.append("동일 해시 중복 파일 존재")
    if size < 8_000:
        risks.append("파일 크기가 작아 빈 양식/단순 양식 여부 확인 필요")
    if any(term in title for term in ["등록", "자격", "인증", "사업허가"]) and not any(
        term in title for term in ["공사계획", "사용전", "완공", "착공", "감리", "배수설비", "비산먼지", "배출시설"]
    ):
        risks.append("사업자/인증 성격 가능성: 실제 공사 제출 대상인지 관할기관 확인 필요")
    if any(term in title for term in ["영문", "Foreign", "Application Form"]):
        risks.append("영문 병기 양식: 국내 제출 자동입력 필드 매핑 확인 필요")
    return risks or ["특이사항 없음"]


def classify_document_type(title: str) -> str:
    if "신청서" in title:
        return "신청서"
    if "신고서" in title:
        return "신고서"
    if "보고서" in title:
        return "보고서"
    if "계획서" in title:
        return "계획서"
    if "확인서" in title:
        return "확인서"
    if "협의서" in title:
        return "협의서"
    return "기타"


def audit(package_dir: Path) -> list[dict[str, Any]]:
    index_path = package_dir / "00_목차" / "공종별_기관제출서식_인덱스.csv"
    rows = read_csv_rows(index_path)
    raw: list[dict[str, Any]] = []
    hashes: Counter[str] = Counter()

    for row in rows:
        file_path = package_dir / row["file_path"]
        data_head = file_path.read_bytes()[:8] if file_path.is_file() else b""
        file_hash = sha256(file_path) if file_path.is_file() else ""
        hashes[file_hash] += 1
        raw.append(
            {
                **row,
                "absolute_path": str(file_path),
                "exists": file_path.is_file(),
                "size_bytes": file_path.stat().st_size if file_path.is_file() else 0,
                "sha256": file_hash,
                "hwp_signature_ok": data_head == HWP_SIGNATURE,
            }
        )

    audited = []
    for row in raw:
        title = row.get("title", "")
        file_hash = row.get("sha256", "")
        fields = infer_fields(row)
        risks = infer_risks(row, int(row["size_bytes"]), hashes[file_hash], bool(row["hwp_signature_ok"]))
        audited.append(
            {
                **row,
                "document_type": classify_document_type(title),
                "submitter": infer_submitter(title),
                "duplicate_count": hashes[file_hash],
                "input_field_candidates": fields,
                "input_field_count": len(fields),
                "review_status": "자동점검 완료" if row["hwp_signature_ok"] else "파일 확인 필요",
                "risks": risks,
            }
        )
    return audited


def write_outputs(package_dir: Path, rows: list[dict[str, Any]]) -> None:
    out_dir = package_dir / "02_문서별점검"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "문서별_점검결과.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    csv_fields = [
        "no",
        "trade",
        "agency",
        "phase",
        "document_type",
        "submitter",
        "title",
        "file_path",
        "exists",
        "size_bytes",
        "sha256",
        "duplicate_count",
        "hwp_signature_ok",
        "input_field_count",
        "input_field_candidates",
        "risks",
        "review_status",
    ]
    with (out_dir / "문서별_점검결과.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=csv_fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "|".join(map(str, row[key])) if isinstance(row.get(key), list) else row.get(key, "")
                    for key in csv_fields
                }
            )

    grouped = defaultdict(list)
    for row in rows:
        grouped[row["trade"]].append(row)

    lines = [
        "# 문서별 자동 점검 결과",
        "",
        f"- 점검 문서: {len(rows)}개",
        f"- HWP 시그니처 정상: {sum(1 for row in rows if row['hwp_signature_ok'])}개",
        f"- 파일 누락: {sum(1 for row in rows if not row['exists'])}개",
        f"- 중복 해시 문서: {sum(1 for row in rows if row['duplicate_count'] > 1)}개",
        "",
        "## 공종별 수량",
        "",
        "| 공종 | 수량 |",
        "| --- | ---: |",
    ]
    for trade in sorted(grouped):
        lines.append(f"| {trade} | {len(grouped[trade])} |")
    lines.extend(["", "## 문서별 상세", ""])
    for trade in sorted(grouped):
        lines.extend([f"### {trade}", "", "| No | 유형 | 제출시점 | 서식 | 입력필드 후보 | 점검 |", "| ---: | --- | --- | --- | ---: | --- |"])
        for row in grouped[trade]:
            lines.append(
                f"| {row['no']} | {row['document_type']} | {row['phase']} | {row['title']} | "
                f"{row['input_field_count']} | {', '.join(row['risks'])} |"
            )
        lines.append("")
    (out_dir / "문서별_점검보고서.md").write_text("\n".join(lines), encoding="utf-8")

    by_hash = defaultdict(list)
    for row in rows:
        by_hash[row["sha256"]].append(row)
    duplicates = [items for items in by_hash.values() if len(items) > 1]
    duplicate_lines = ["# 중복 파일 점검", ""]
    if not duplicates:
        duplicate_lines.append("동일 SHA-256 해시 중복 파일은 없다.")
    else:
        for items in duplicates:
            duplicate_lines.append(f"## {items[0]['sha256']}")
            for item in items:
                duplicate_lines.append(f"- {item['no']} {item['title']} (`{item['file_path']}`)")
            duplicate_lines.append("")
    (out_dir / "중복파일_점검.md").write_text("\n".join(duplicate_lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package-dir",
        default="deliverables/기관제출서류_기관별확장_로컬패키지",
    )
    args = parser.parse_args()
    package_dir = ROOT / args.package_dir
    rows = audit(package_dir)
    write_outputs(package_dir, rows)
    print(f"package_dir={package_dir}")
    print(f"documents={len(rows)}")
    print(f"hwp_signature_ok={sum(1 for row in rows if row['hwp_signature_ok'])}")
    print(f"missing={sum(1 for row in rows if not row['exists'])}")
    print(f"duplicate_hash_docs={sum(1 for row in rows if row['duplicate_count'] > 1)}")
    print(f"output_dir={package_dir / '02_문서별점검'}")


if __name__ == "__main__":
    main()
