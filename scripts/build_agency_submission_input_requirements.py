from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


COMMON_REQUIRED = [
    "공사명",
    "현장주소",
    "발주자",
    "시공자 상호",
    "시공자 대표자",
    "시공자 주소",
    "시공자 연락처",
    "작성일",
    "제출기관",
]


PERSON_FIELDS = [
    "신청인 성명",
    "신청인 생년월일/법인등록번호",
    "신청인 주소",
    "신청인 연락처",
]


TRADE_REQUIRED = {
    "건축": ["건축주", "대지위치", "건축구분", "주용도", "건축면적", "연면적", "층수", "구조"],
    "소방": ["특정소방대상물명", "소재지", "소방시설 종류", "소방공사업체", "소방기술자", "공사기간"],
    "전기": ["전기사용장소", "설비용량", "수전전압", "공사계획 개요", "전기공사업체", "전기안전관리자"],
    "기계설비": ["기계설비 종류", "기계설비 시공자", "착공 예정일", "사용 전 검사 희망일"],
    "정보통신": ["정보통신공사명", "공사 종류", "시공자", "설계도서 목록", "사용전검사 희망일"],
    "가스": ["가스 종류", "시설 위치", "시설 종류", "저장능력/처리능력", "시공자", "검사 희망일"],
    "승강기": ["승강기 종류", "설치 장소", "제조/수입업자", "설치업자", "승강기 대수", "안전인증번호"],
    "상하수도/수자원": ["설치 위치", "배수/급수 설비 개요", "처리용량", "관경/연장", "시공자"],
    "폐기물/환경": ["사업장명", "사업장 소재지", "배출시설 종류", "방지시설 종류", "배출/처리량", "가동개시 예정일"],
    "안전/노동": ["공사금액", "공사기간", "공사종류", "유해위험요인", "안전관리 조직", "작성 책임자"],
    "건설공사 공통관리": ["도급계약 정보", "하도급 정보", "공사기간", "계약금액", "건설사업관리기술인"],
}


TITLE_REQUIRED_RULES = [
    (["착공"], ["착공 예정일", "착공 신고 대상 공종", "공사 예정 공정표", "현장대리인"]),
    (["사용승인"], ["사용승인 신청일", "공사 완료일", "감리완료 확인", "준공도서 목록"]),
    (["사용전", "사용 전"], ["검사 희망일", "검사 대상 설비", "시험성적서", "설계도/준공도"]),
    (["완공", "완성검사"], ["완공일", "완공 범위", "검사 대상", "시공 확인자료"]),
    (["감리"], ["감리자 상호", "감리자 등록번호", "감리기간", "감리원 명단", "감리결과"]),
    (["배치"], ["배치 기술자 성명", "등급/자격", "배치기간", "철수일", "변경사유"]),
    (["점검"], ["점검일", "점검기간", "점검자", "점검 결과", "보완/이행 조치"]),
    (["변경"], ["변경 전 내용", "변경 후 내용", "변경 사유", "변경일", "변경 증빙"]),
    (["연장"], ["기존 기한", "연장 요청 기한", "연장 사유", "증빙자료"]),
    (["공사계획"], ["공사계획 개요", "시공 방법", "주요 설비", "도면 목록", "공정표"]),
    (["굴착공사"], ["굴착 위치", "굴착 깊이", "굴착 기간", "지하매설물 확인", "협의 상대기관"]),
    (["하도급"], ["수급인", "하수급인", "하도급 공종", "하도급 금액", "하도급 기간"]),
    (["비산먼지"], ["발생사업 종류", "억제시설/조치", "공사면적", "공사기간", "현장 위치도"]),
    (["폐수", "배출시설"], ["배출시설 명세", "오염물질 종류", "방지시설 명세", "배출량", "측정자료"]),
    (["건설폐기물"], ["폐기물 종류", "예상 발생량", "처리업체", "처리방법", "운반계획"]),
    (["유해위험방지"], ["공사 개요", "위험공종", "안전대책", "도면", "안전관리계획"]),
]


ATTACHMENT_RULES = [
    (["건축ㆍ대수선ㆍ용도변경", "가설건축물", "대지위치"], ["위치도", "배치도", "설계도서", "토지/건축물 관련 증빙"]),
    (["착공"], ["공사계약서", "설계도서", "공정표", "감리계약서/감리자 지정서"]),
    (["감리"], ["감리계약서", "감리원 자격증명", "배치계획", "감리일지/결과자료"]),
    (["사용전", "사용 전", "완공", "완성검사"], ["준공도서", "시험성적서", "사진대지", "자재승인/검사자료"]),
    (["점검"], ["점검표", "현장사진", "보완조치 내역", "점검자 자격자료"]),
    (["변경"], ["변경 전후 도면", "변경 사유서", "변경 계약/승인 자료"]),
    (["하도급"], ["하도급계약서", "내역서", "하수급인 등록증", "보증서"]),
    (["폐기물"], ["폐기물 처리계획서", "위탁계약서", "운반/처리업 허가증"]),
    (["비산먼지", "배출시설", "폐수"], ["시설명세서", "방지시설 도면", "공정도", "측정자료"]),
    (["승강기"], ["승강기 사양서", "안전인증서", "설치도면", "검사신청 증빙"]),
]


AGENCY_ONLY_FIELD_TERMS = [
    "접수번호",
    "접수일",
    "접수일자",
    "처리일",
    "처리일자",
    "처리기간",
    "수수료",
    "없음",
    "귀하",
    "담당",
    "확인",
    "발신기관명",
    "수신자",
]

NON_INPUT_FIELD_PATTERNS = [
    r"^\d+\s*일$",
    r"^년 월 일",
    r"^\(서명 또는 인\)$",
    r"^서명 또는 인$",
    r"^\(\)$",
    r"^원$",
    r"^제 호$",
]


AUTO_FILL_COMMON = [
    "작성일",
    "제출기관",
    "공사명",
    "현장주소",
    "시공자 상호",
    "시공자 대표자",
    "시공자 연락처",
]


def load_audit(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def unique(values: list[str]) -> list[str]:
    result = []
    for value in values:
        value = re.sub(r"\s+", " ", str(value)).strip()
        if value and value not in result:
            result.append(value)
    return result


def is_user_input_field(field: str) -> bool:
    field = re.sub(r"\s+", " ", str(field)).strip()
    if not field:
        return False
    if any(term in field for term in AGENCY_ONLY_FIELD_TERMS):
        return False
    if any(re.search(pattern, field) for pattern in NON_INPUT_FIELD_PATTERNS):
        return False
    return True


def match_rules(title: str, rules: list[tuple[list[str], list[str]]]) -> list[str]:
    values: list[str] = []
    for terms, fields in rules:
        if any(term in title for term in terms):
            values.extend(fields)
    return values


def priority(title: str) -> str:
    if any(term in title for term in ["착공", "사용승인", "사용전", "사용 전", "완공", "완성검사", "유해위험방지"]):
        return "높음"
    if any(term in title for term in ["변경", "점검", "감리", "배치", "공사계획"]):
        return "중간"
    return "보통"


def build_requirements(row: dict[str, Any], body_row: dict[str, Any] | None = None) -> dict[str, Any]:
    title = row["title"]
    trade = row["trade"]
    body_fields = body_row.get("body_field_candidates", []) if body_row else []
    body_attachments = body_row.get("body_attachment_candidates", []) if body_row else []
    required = unique(
        [
            *COMMON_REQUIRED,
            *PERSON_FIELDS,
            *TRADE_REQUIRED.get(trade, []),
            *match_rules(title, TITLE_REQUIRED_RULES),
            *body_fields,
        ]
    )
    required = [field for field in required if is_user_input_field(field)]
    auto_fill = [field for field in required if field in AUTO_FILL_COMMON]
    user_required = [field for field in required if field not in auto_fill]
    attachments = unique([*match_rules(title, ATTACHMENT_RULES), *body_attachments])
    if not attachments:
        attachments = ["관할기관 안내문 기준 첨부서류 확인"]
    optional = unique([field for field in row.get("input_field_candidates", []) if field not in required])
    return {
        "no": row["no"],
        "trade": trade,
        "agency": row["agency"],
        "phase": row["phase"],
        "document_type": row["document_type"],
        "title": title,
        "file_path": row["file_path"],
        "input_priority": priority(title),
        "body_verified": bool(body_row and body_row.get("extract_ok")),
        "body_text_path": body_row.get("text_path", "") if body_row else "",
        "body_field_candidates": body_fields,
        "body_attachment_candidates": body_attachments,
        "auto_fill_fields": auto_fill,
        "user_required_fields": user_required,
        "optional_fields": optional,
        "required_attachments": attachments,
        "user_prompt": make_prompt(title, user_required, attachments),
        "validation_rules": validation_rules(required),
    }


def make_prompt(title: str, fields: list[str], attachments: list[str]) -> str:
    field_text = ", ".join(fields[:12])
    if len(fields) > 12:
        field_text += f" 외 {len(fields) - 12}개"
    attachment_text = ", ".join(attachments[:6])
    return f"{title} 작성에 필요한 자료를 입력해 주세요. 필수 입력: {field_text}. 첨부 확인: {attachment_text}."


def validation_rules(fields: list[str]) -> list[str]:
    rules = []
    date_like = [field for field in fields if any(term in field for term in ["일", "기간", "기한"])]
    money_like = [field for field in fields if any(term in field for term in ["금액", "공사금액", "계약금액"])]
    contact_like = [field for field in fields if any(term in field for term in ["연락처", "전화"])]
    if date_like:
        rules.append("날짜/기간 필드는 YYYY-MM-DD 또는 시작일~종료일 형식 권장")
    if money_like:
        rules.append("금액 필드는 원 단위 숫자와 부가세 포함 여부 확인")
    if contact_like:
        rules.append("연락처 필드는 지역번호 또는 휴대전화 형식 확인")
    rules.append("자동입력 전 기존 셀 값이 있으면 덮어쓰기 전 사용자 확인")
    rules.append("입력 후 셀 넘침이 있으면 전체 입력 완료 후 글자 크기 일괄 축소")
    return rules


def write_outputs(package_dir: Path, rows: list[dict[str, Any]]) -> None:
    out_dir = package_dir / "03_입력요구사항"
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "문서별_입력요구사항.json"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = [
        "no",
        "trade",
        "agency",
        "phase",
        "document_type",
        "input_priority",
        "title",
        "file_path",
        "body_verified",
        "body_text_path",
        "body_field_candidates",
        "body_attachment_candidates",
        "auto_fill_fields",
        "user_required_fields",
        "optional_fields",
        "required_attachments",
        "validation_rules",
        "user_prompt",
    ]
    with (out_dir / "문서별_입력요구사항.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "|".join(row[k]) if isinstance(row.get(k), list) else row.get(k, "") for k in fields})

    by_trade = defaultdict(list)
    by_priority = defaultdict(list)
    for row in rows:
        by_trade[row["trade"]].append(row)
        by_priority[row["input_priority"]].append(row)

    lines = [
        "# 문서별 입력 요구사항 검토",
        "",
        f"- 대상 문서: {len(rows)}개",
        "- 목적: 자동입력 전에 사용자에게 받아야 할 자료와 자동으로 채울 수 있는 공통값을 문서별로 분리",
        f"- 본문 확인 반영: {sum(1 for row in rows if row['body_verified'])}개",
        "",
        "## 우선순위",
        "",
        "| 우선순위 | 수량 |",
        "| --- | ---: |",
    ]
    for key in ["높음", "중간", "보통"]:
        lines.append(f"| {key} | {len(by_priority.get(key, []))} |")
    lines.extend(["", "## 공종별 상세", ""])
    for trade in sorted(by_trade):
        lines.extend([f"### {trade}", "", "| No | 우선순위 | 본문확인 | 서식 | 사용자 필수 입력 | 첨부 확인 |", "| ---: | --- | --- | --- | --- | --- |"])
        for row in by_trade[trade]:
            lines.append(
                f"| {row['no']} | {row['input_priority']} | {'Y' if row['body_verified'] else 'N'} | {row['title']} | "
                f"{len(row['user_required_fields'])}개 | {len(row['required_attachments'])}개 |"
            )
        lines.append("")
    (out_dir / "문서별_입력요구사항_보고서.md").write_text("\n".join(lines), encoding="utf-8")

    template = {
        "project_common": {field: "" for field in COMMON_REQUIRED},
        "submitter_common": {field: "" for field in PERSON_FIELDS},
        "documents": [
            {
                "no": row["no"],
                "title": row["title"],
                "file_path": row["file_path"],
                "values": {field: "" for field in row["user_required_fields"]},
                "attachments_checked": {name: False for name in row["required_attachments"]},
            }
            for row in rows
        ],
    }
    (out_dir / "사용자입력_빈템플릿.json").write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--package-dir",
        default="deliverables/기관제출서류_기관별확장_로컬패키지",
    )
    args = parser.parse_args()
    package_dir = ROOT / args.package_dir
    audit_path = package_dir / "02_문서별점검" / "문서별_점검결과.json"
    audited = load_audit(audit_path)
    body_path = package_dir / "04_본문추출" / "본문기반_입력항목.json"
    body_by_no = {}
    if body_path.exists():
        body_rows = load_audit(body_path)
        body_by_no = {str(row["no"]): row for row in body_rows}
    rows = [build_requirements(row, body_by_no.get(str(row["no"]))) for row in audited]
    write_outputs(package_dir, rows)
    print(f"package_dir={package_dir}")
    print(f"documents={len(rows)}")
    print(f"high_priority={sum(1 for row in rows if row['input_priority'] == '높음')}")
    print(f"output_dir={package_dir / '03_입력요구사항'}")


if __name__ == "__main__":
    main()
