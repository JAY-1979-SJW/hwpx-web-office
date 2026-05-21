from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


STAGES = [
    {
        "stage_id": "01_permit_consultation",
        "stage_name": "인허가·협의",
        "phase_terms": {"인허가", "허가", "신고", "협의", "조사", "보존", "전용허가", "점용", "신청", "공급협의"},
        "document_terms": ["허가", "신고", "협의", "조사", "점용", "전용", "공급", "사용신청"],
        "situation": "허가권자·관계기관 협의 또는 법정 신고가 필요한 경우",
    },
    {
        "stage_id": "02_contract_start_ready",
        "stage_name": "계약·착공 전",
        "phase_terms": {"계약", "착공 전", "착수", "설계", "계획", "심사", "예비인증"},
        "document_terms": ["계약", "착공 전", "착수", "계획", "설계", "심사", "예비인증", "착공신고"],
        "situation": "계약 이후 착공 전 승인·계획·설계 확인이 필요한 경우",
    },
    {
        "stage_id": "03_start",
        "stage_name": "착공·착수",
        "phase_terms": {"착공", "착수"},
        "document_terms": ["착공", "착수", "현장대리인", "예정공정"],
        "situation": "공사를 실제 시작하거나 착수계를 제출하는 경우",
    },
    {
        "stage_id": "04_construction",
        "stage_name": "시공 중",
        "phase_terms": {"시공", "시공 중", "설치", "작업", "제작", "반입", "반출", "회의"},
        "document_terms": ["시공", "설치", "작업", "제작", "반입", "반출", "회의록", "작업일보"],
        "situation": "현장 시공, 설치, 반입, 작업 진행 중 관리가 필요한 경우",
    },
    {
        "stage_id": "05_material_inspection_test",
        "stage_name": "자재승인·검측·시험",
        "phase_terms": {"자재승인", "검측", "시험", "품질", "검사", "점검"},
        "document_terms": ["자재", "승인", "검측", "시험", "성적서", "점검", "검사", "품질", "체크리스트"],
        "situation": "자재 승인, 검측 요청, 품질시험, 현장점검이 필요한 경우",
    },
    {
        "stage_id": "06_pre_use_completion",
        "stage_name": "사용 전·완공검사",
        "phase_terms": {"사용 전", "사용전검사", "완공", "영업 전", "탱크검사", "본인증", "사용승인", "시운전"},
        "document_terms": ["사용 전", "사용전", "완공", "완성검사", "설치검사", "시운전", "사용승인", "본인증"],
        "situation": "시설 사용 전 검사, 완공검사, 사용승인 준비가 필요한 경우",
    },
    {
        "stage_id": "07_completion_settlement",
        "stage_name": "준공·정산·납품",
        "phase_terms": {"준공", "기성", "납품", "완료", "처리", "복구"},
        "document_terms": ["준공", "기성", "정산", "납품", "완료", "완료보고", "복구", "성과품", "도서"],
        "situation": "준공, 기성, 정산, 전자납품, 완료보고가 필요한 경우",
    },
    {
        "stage_id": "08_operation_maintenance",
        "stage_name": "운영·유지관리·하자",
        "phase_terms": {"운영", "유지관리", "정기검사", "하자", "이행확인"},
        "document_terms": ["유지관리", "정기검사", "하자", "성능점검", "이행확인", "자체점검"],
        "situation": "준공 후 유지관리, 정기점검, 하자보수 관리가 필요한 경우",
    },
    {
        "stage_id": "09_change_closeout",
        "stage_name": "변경·보완·폐지",
        "phase_terms": {"변경", "보완", "재발급", "폐지", "철거", "해체", "조치", "연장"},
        "document_terms": ["변경", "보완", "재발급", "폐지", "철거", "해체", "조치", "연장"],
        "situation": "승인사항 변경, 보완, 폐지, 철거, 행정 조치가 필요한 경우",
    },
]


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def infer_stage_ids(document: str, phases: list[str]) -> list[str]:
    matched: list[str] = []
    phase_set = set(phases)
    for stage in STAGES:
        if phase_set & stage["phase_terms"]:
            matched.append(stage["stage_id"])
            continue
        if any(term in document for term in stage["document_terms"]):
            matched.append(stage["stage_id"])
    if not matched:
        matched.append("04_construction")
    return unique(matched)


def choose_primary_stage_id(document: str, stage_ids: list[str]) -> str:
    priority_terms = [
        ("09_change_closeout", ["변경", "보완", "재발급", "폐지", "철거", "해체", "연장"]),
        ("08_operation_maintenance", ["유지관리", "정기검사", "하자", "성능점검", "자체점검"]),
        ("07_completion_settlement", ["준공", "정산", "납품", "완료보고", "완료", "복구"]),
        ("06_pre_use_completion", ["사용승인", "사용 전", "사용전", "완공", "완성검사", "설치검사", "본인증", "시운전"]),
        ("02_contract_start_ready", ["관리자 배치계획", "배치계획", "관리계획", "시공계획", "안전계획", "품질계획"]),
        ("05_material_inspection_test", ["검측", "시험", "성적서", "품질", "자재승인", "안전인증"]),
        ("03_start", ["착공", "착수"]),
        ("02_contract_start_ready", ["계약", "계획", "설계", "심사", "예비인증"]),
        ("01_permit_consultation", ["허가", "신고", "협의", "점용", "전용"]),
        ("04_construction", ["시공", "설치", "작업", "제작", "반입", "반출"]),
    ]
    for stage_id, terms in priority_terms:
        if stage_id in stage_ids and any(term in document for term in terms):
            return stage_id
    return stage_ids[0]


def corrected_phase_labels(stage_ids: list[str]) -> list[str]:
    stage_names = {stage["stage_id"]: stage["stage_name"] for stage in STAGES}
    return [f"보정:{stage_names[stage_id]}" for stage_id in stage_ids]


def build_document_phase_rows(index: dict[str, Any]) -> list[dict[str, Any]]:
    phase_by_trade_doc: dict[tuple[str, str], list[str]] = defaultdict(list)
    subcategory_by_trade_doc: dict[tuple[str, str], list[str]] = defaultdict(list)

    for trade in index.get("trades", []):
        trade_name = trade["trade_name"]
        for subcategory in trade.get("subcategories", []):
            phases = [str(value) for value in subcategory.get("phase", [])]
            subcategory_name = str(subcategory.get("name", ""))
            for document in subcategory.get("documents", []):
                key = (trade_name, str(document))
                phase_by_trade_doc[key].extend(phases)
                subcategory_by_trade_doc[key].append(subcategory_name)

    rows: list[dict[str, Any]] = []
    for trade in index.get("trades", []):
        trade_name = trade["trade_name"]
        for document in trade.get("documents", []):
            key = (trade_name, str(document))
            phases = unique(phase_by_trade_doc.get(key, []))
            stage_ids = infer_stage_ids(str(document), phases)
            corrected = not phases
            rows.append(
                {
                    "trade_name": trade_name,
                    "document": str(document),
                    "stage_ids": stage_ids,
                    "primary_stage_id": choose_primary_stage_id(str(document), stage_ids),
                    "raw_phases": phases,
                    "effective_phases": phases or corrected_phase_labels(stage_ids),
                    "phase_source": "source" if not corrected else "corrected_rule",
                    "subcategories": unique(subcategory_by_trade_doc.get(key, [])),
                    "agencies": trade.get("agencies", []),
                    "submit_to": trade.get("submit_to", []),
                    "keywords": trade.get("keywords", []),
                }
            )
    return rows


def build_index(index: dict[str, Any]) -> dict[str, Any]:
    rows = build_document_phase_rows(index)
    stage_lookup = {
        stage["stage_id"]: {
            "stage_id": stage["stage_id"],
            "stage_name": stage["stage_name"],
            "situation": stage["situation"],
            "phase_terms": sorted(stage["phase_terms"]),
            "document_terms": stage["document_terms"],
        }
        for stage in STAGES
    }
    by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_trade: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in rows:
        compact = {
            "trade_name": row["trade_name"],
            "document": row["document"],
            "primary_stage_id": row["primary_stage_id"],
            "raw_phases": row["raw_phases"],
            "effective_phases": row["effective_phases"],
            "phase_source": row["phase_source"],
            "subcategories": row["subcategories"],
            "submit_to": row["submit_to"],
        }
        by_trade[row["trade_name"]].append(compact | {"stage_ids": row["stage_ids"]})
        for stage_id in row["stage_ids"]:
            by_stage[stage_id].append(compact)

    corrected_rows = [row for row in rows if row["phase_source"] == "corrected_rule"]
    unphased = [row for row in rows if not row["effective_phases"]]
    return {
        "generated_date": date.today().isoformat(),
        "source": "data/agency_submission_trade_index.json",
        "stage_count": len(STAGES),
        "document_row_count": len(rows),
        "unphased_document_count": len(unphased),
        "corrected_document_count": len(corrected_rows),
        "stages": [
            {
                "stage_id": stage["stage_id"],
                "stage_name": stage["stage_name"],
                "situation": stage["situation"],
                "documents": by_stage.get(stage["stage_id"], []),
            }
            for stage in STAGES
        ],
        "trades": [
            {"trade_name": trade_name, "documents": docs}
            for trade_name, docs in sorted(by_trade.items())
        ],
        "coverage_audit": {
            "trade_unphased_counts": dict(
                sorted(
                    {
                        trade: sum(1 for row in unphased if row["trade_name"] == trade)
                        for trade in {row["trade_name"] for row in unphased}
                    }.items()
                )
            ),
            "trade_corrected_counts": dict(
                sorted(
                    {
                        trade: sum(1 for row in corrected_rows if row["trade_name"] == trade)
                        for trade in {row["trade_name"] for row in corrected_rows}
                    }.items()
                )
            ),
            "corrected_documents": [
                {
                    "trade_name": row["trade_name"],
                    "document": row["document"],
                    "corrected_stage_ids": row["stage_ids"],
                    "primary_stage_id": row["primary_stage_id"],
                    "effective_phases": row["effective_phases"],
                }
                for row in corrected_rows
            ],
            "unphased_documents": [
                {
                    "trade_name": row["trade_name"],
                    "document": row["document"],
                    "inferred_stage_ids": row["stage_ids"],
                }
                for row in unphased
            ]
        },
        "stage_names": {stage["stage_id"]: stage["stage_name"] for stage in STAGES},
        "stage_lookup": stage_lookup,
    }


def render_markdown(phase_index: dict[str, Any]) -> str:
    stage_names = phase_index["stage_names"]
    lines = [
        "# 전공종 제출순서·상황별 제출서류 인덱스",
        "",
        f"- 생성일: {phase_index['generated_date']}",
        f"- 문서 행 수: {phase_index['document_row_count']}",
        f"- 원 단계 미기재 문서 수: {phase_index['unphased_document_count']}",
        f"- 보정 단계 적용 문서 수: {phase_index['corrected_document_count']}",
        "",
        "## 제출순서 목차",
        "",
    ]
    for stage in phase_index["stages"]:
        lines.append(
            f"- {stage['stage_name']}: {stage['situation']} "
            f"({len(stage['documents'])}건)"
        )

    for stage in phase_index["stages"]:
        lines.extend(["", f"## {stage['stage_name']}", "", stage["situation"], ""])
        lines.append("| 공종 | 제출서류 | 원 단계 | 제출처 |")
        lines.append("|---|---|---|---|")
        for item in stage["documents"]:
            lines.append(
                "| "
                + " | ".join(
                    [
                        item["trade_name"],
                        item["document"],
                        ", ".join(item.get("effective_phases", [])),
                        ", ".join(item.get("submit_to", [])[:4]),
                    ]
                )
                + " |"
            )

    lines.extend(["", "## 공종별 제출순서", ""])
    for trade in phase_index["trades"]:
        lines.extend(["", f"### {trade['trade_name']}", ""])
        lines.append("| 제출순서 | 제출서류 | 원 단계 |")
        lines.append("|---|---|---|")
        sorted_docs = sorted(
            trade["documents"],
            key=lambda item: item["primary_stage_id"],
        )
        for item in sorted_docs:
            lines.append(
                "| "
                + " | ".join(
                    [
                        ", ".join(stage_names[stage_id] for stage_id in item["stage_ids"]),
                        item["document"],
                        ", ".join(item.get("effective_phases", [])),
                    ]
                )
                + " |"
            )

    return "\n".join(lines) + "\n"


def write_csv(path: Path, phase_index: dict[str, Any]) -> None:
    stage_names = phase_index["stage_names"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=["stage_name", "trade_name", "document", "phase_source", "phases", "submit_to"],
        )
        writer.writeheader()
        for stage in phase_index["stages"]:
            for item in stage["documents"]:
                writer.writerow(
                    {
                        "stage_name": stage_names[stage["stage_id"]],
                        "trade_name": item["trade_name"],
                        "document": item["document"],
                        "phase_source": item.get("phase_source", ""),
                        "phases": "; ".join(item.get("effective_phases", [])),
                        "submit_to": "; ".join(item.get("submit_to", [])),
                    }
                )


def write_primary_order_csv(path: Path, phase_index: dict[str, Any]) -> None:
    stage_names = phase_index["stage_names"]
    stage_order = {stage["stage_id"]: index for index, stage in enumerate(phase_index["stages"], start=1)}
    rows: list[dict[str, Any]] = []
    for trade in phase_index["trades"]:
        for item in trade["documents"]:
            primary_stage_id = item["primary_stage_id"]
            secondary_stage_ids = [
                stage_id for stage_id in item["stage_ids"] if stage_id != primary_stage_id
            ]
            rows.append(
                {
                    "order": stage_order[primary_stage_id],
                    "stage_name": stage_names[primary_stage_id],
                    "trade_name": trade["trade_name"],
                    "document": item["document"],
                    "also_used_in": "; ".join(stage_names[stage_id] for stage_id in secondary_stage_ids),
                    "phase_source": item.get("phase_source", ""),
                    "phases": "; ".join(item.get("effective_phases", [])),
                    "submit_to": "; ".join(item.get("submit_to", [])),
                }
            )

    rows.sort(key=lambda row: (row["order"], row["trade_name"], row["document"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "order",
                "stage_name",
                "trade_name",
                "document",
                "also_used_in",
                "phase_source",
                "phases",
                "submit_to",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/agency_submission_trade_index.json")
    parser.add_argument("--json-output", default="data/agency_submission_phase_situation_index.json")
    parser.add_argument("--md-output", default="docs/agency_submission_phase_situation_index.md")
    parser.add_argument("--csv-output", default="data/agency_submission_phase_situation_index.csv")
    parser.add_argument("--primary-order-csv-output", default="data/agency_submission_primary_submission_order.csv")
    args = parser.parse_args()

    source_index = json.loads(Path(args.input).read_text(encoding="utf-8"))
    phase_index = build_index(source_index)

    json_path = Path(args.json_output)
    md_path = Path(args.md_output)
    csv_path = Path(args.csv_output)
    primary_order_csv_path = Path(args.primary_order_csv_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(phase_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(phase_index), encoding="utf-8")
    write_csv(csv_path, phase_index)
    write_primary_order_csv(primary_order_csv_path, phase_index)

    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"wrote {csv_path}")
    print(f"wrote {primary_order_csv_path}")
    print(
        "stage_count="
        f"{phase_index['stage_count']} document_rows={phase_index['document_row_count']} "
        f"unphased={phase_index['unphased_document_count']}"
    )


if __name__ == "__main__":
    main()
