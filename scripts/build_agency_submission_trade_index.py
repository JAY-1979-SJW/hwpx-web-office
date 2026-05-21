from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


TRADE_ALIASES = {
    "전기": {"전기", "전기공급", "전기안전"},
    "승강기": {"승강기", "엘리베이터", "리프트"},
}

TRADE_ORDER = [
    "건축",
    "토목",
    "기계설비",
    "승강기",
    "전기",
    "정보통신",
    "소방",
    "가스",
    "상하수도/수자원",
    "전문공종",
    "환경",
    "해체·석면",
    "산업안전보건",
    "인증·협의",
    "인허가·점용",
    "가설·광고물",
    "장비·양중",
    "건설공사 공통관리",
    "계약·성과품",
]

SPLIT_SUBCATEGORY_TRADES = {
    "승강기": {
        "submit_to": ["한국승강기안전공단", "행정안전부", "시·군·구 승강기 담당부서", "감리자"],
        "keywords": [
            "승강기",
            "엘리베이터",
            "리프트",
            "설치검사",
            "안전인증",
            "검사합격증명",
            "정기검사",
            "자체점검",
            "유지관리",
        ],
        "fields": [
            "승강기번호",
            "승강기 종류",
            "정격속도",
            "정격하중",
            "정원",
            "층수",
            "제조사",
            "설치위치",
            "검사일",
            "검사기관",
            "합격번호",
            "판정",
        ],
    }
}


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def normalize_term(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def canonical_trade(domain: str) -> str:
    domain = (domain or "미분류").strip()
    for canonical, aliases in TRADE_ALIASES.items():
        if domain in aliases:
            return canonical
    return domain


def split_agency_by_special_subcategories(agency: dict[str, Any]) -> list[dict[str, Any]]:
    agencies = [dict(agency)]
    for subcategory in agency.get("subcategories", []):
        name = str(subcategory.get("name", "")).strip()
        if name not in SPLIT_SUBCATEGORY_TRADES:
            continue

        split_rule = SPLIT_SUBCATEGORY_TRADES[name]
        split_documents = unique(list(subcategory.get("documents", [])))
        split_keywords = unique([name, *split_rule["keywords"]])
        split_fields = unique([*agency.get("fields", []), *split_rule["fields"]])
        split_submit_to = unique([*split_rule["submit_to"], *agency.get("submit_to", [])])
        split_agency = {
            "agency": f"{name}/전문검사",
            "domain": name,
            "submit_to": split_submit_to,
            "documents": split_documents,
            "keywords": split_keywords,
            "fields": split_fields,
            "subcategories": [{**subcategory, "name": name}],
            "sources": agency.get("sources", []),
        }
        agencies.append(split_agency)

    return agencies


def trade_sort_key(name: str) -> tuple[int, str]:
    try:
        return (TRADE_ORDER.index(name), name)
    except ValueError:
        return (len(TRADE_ORDER), name)


def build_index(seed: dict[str, Any]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for agency in seed.get("agencies", []):
        for split_agency in split_agency_by_special_subcategories(agency):
            grouped[canonical_trade(split_agency.get("domain", ""))].append(split_agency)

    trades: list[dict[str, Any]] = []
    term_index: dict[str, list[dict[str, str]]] = defaultdict(list)

    for trade_name in sorted(grouped, key=trade_sort_key):
        agencies = grouped[trade_name]
        documents: list[str] = []
        keywords: list[str] = []
        fields: list[str] = []
        sources: list[str] = []
        subcategories: list[dict[str, Any]] = []
        agency_names: list[str] = []
        submit_to: list[str] = []

        for agency in agencies:
            agency_name = agency.get("agency", "")
            agency_names.append(agency_name)
            submit_to.extend(agency.get("submit_to", []))
            documents.extend(agency.get("documents", []))
            keywords.extend(agency.get("keywords", []))
            fields.extend(agency.get("fields", []))
            sources.extend(agency.get("sources", []))
            for subcategory in agency.get("subcategories", []):
                copied = dict(subcategory)
                copied["agency"] = agency_name
                subcategories.append(copied)

        documents = unique(documents)
        keywords = unique(keywords)
        fields = unique(fields)
        sources = unique(sources)
        agency_names = unique(agency_names)
        submit_to = unique(submit_to)
        aliases = sorted(TRADE_ALIASES.get(trade_name, {trade_name}))

        trade_id = normalize_term(trade_name)
        trade_entry = {
            "trade_id": trade_id,
            "trade_name": trade_name,
            "aliases": aliases,
            "agencies": agency_names,
            "submit_to": submit_to,
            "document_count": len(documents),
            "keyword_count": len(keywords),
            "field_count": len(fields),
            "documents": documents,
            "keywords": keywords,
            "fields": fields,
            "subcategories": subcategories,
            "sources": sources,
        }
        trades.append(trade_entry)

        for term_type, values in (
            ("trade", [trade_name, *aliases]),
            ("agency", agency_names),
            ("submit_to", submit_to),
            ("document", documents),
            ("keyword", keywords),
            ("field", fields),
        ):
            for value in values:
                term = normalize_term(value)
                if not term:
                    continue
                term_index[term].append(
                    {
                        "type": term_type,
                        "value": value,
                        "trade_id": trade_id,
                        "trade_name": trade_name,
                    }
                )

    compact_term_index = {
        term: dedupe_hits(hits) for term, hits in sorted(term_index.items())
    }

    return {
        "version": seed.get("version", ""),
        "generated_date": date.today().isoformat(),
        "source": "data/agency_submission_taxonomy.seed.json",
        "trade_count": len(trades),
        "trades": trades,
        "term_index": compact_term_index,
    }


def dedupe_hits(hits: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, str]] = []
    for hit in hits:
        key = (hit["type"], hit["value"], hit["trade_id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(hit)
    return out


def render_markdown(index: dict[str, Any]) -> str:
    lines = [
        "# 기관별 시공사 제출서류 공종별 인덱스",
        "",
        f"생성일: {index['generated_date']}",
        f"원본: `{index['source']}`",
        "",
        "## 목차",
        "",
    ]

    for idx, trade in enumerate(index["trades"], start=1):
        lines.append(
            f"{idx}. {trade['trade_name']} - 문서 {trade['document_count']}건, "
            f"키워드 {trade['keyword_count']}건, 입력필드 {trade['field_count']}건"
        )

    lines.extend(["", "## 빠른 탐색 인덱스", ""])
    lines.append("| 공종 | 대표 키워드 | 대표 문서 | 제출처/기관 |")
    lines.append("|---|---|---|---|")
    for trade in index["trades"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    trade["trade_name"],
                    ", ".join(trade["keywords"][:12]),
                    ", ".join(trade["documents"][:10]),
                    ", ".join(trade["agencies"][:6]),
                ]
            )
            + " |"
        )

    for idx, trade in enumerate(index["trades"], start=1):
        lines.extend(
            [
                "",
                f"## {idx}. {trade['trade_name']}",
                "",
                f"- 별칭: {', '.join(trade['aliases'])}",
                f"- 관련 기관/분류: {', '.join(trade['agencies'])}",
                f"- 제출처: {', '.join(trade['submit_to'][:12])}",
                "",
                "### 대표 문서",
                "",
            ]
        )
        for document in trade["documents"]:
            lines.append(f"- {document}")

        lines.extend(["", "### 탐색 키워드", ""])
        lines.append(", ".join(trade["keywords"]) or "-")

        lines.extend(["", "### 주요 입력 필드", ""])
        lines.append(", ".join(trade["fields"]) or "-")

        if trade["subcategories"]:
            lines.extend(["", "### 하위 분류", ""])
            lines.append("| 하위분류 | 단계 | 대표 문서 | 구조패턴 |")
            lines.append("|---|---|---|---|")
            for subcategory in trade["subcategories"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            str(subcategory.get("name", "")),
                            ", ".join(subcategory.get("phase", [])),
                            ", ".join(subcategory.get("documents", [])),
                            ", ".join(subcategory.get("structure_patterns", [])),
                        ]
                    )
                    + " |"
                )

        lines.extend(["", "### 출처", ""])
        for source in trade["sources"]:
            lines.append(f"- {source}")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/agency_submission_taxonomy.seed.json")
    parser.add_argument("--json-output", default="data/agency_submission_trade_index.json")
    parser.add_argument("--md-output", default="docs/agency_submission_trade_index.md")
    args = parser.parse_args()

    seed_path = Path(args.input)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    index = build_index(seed)

    json_path = Path(args.json_output)
    md_path = Path(args.md_output)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(index), encoding="utf-8")

    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    print(f"trade_count={index['trade_count']} term_count={len(index['term_index'])}")


if __name__ == "__main__":
    main()
