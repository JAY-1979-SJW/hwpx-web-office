from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def find_or_create_agency(seed: dict[str, Any], domain: str, agency_name: str) -> dict[str, Any]:
    for agency in seed.setdefault("agencies", []):
        if agency.get("domain") == domain and agency.get("agency") == agency_name:
            return agency
    agency = {
        "agency": agency_name,
        "domain": domain,
        "submit_to": [],
        "documents": [],
        "keywords": [],
        "fields": [],
        "subcategories": [],
        "sources": [],
    }
    seed["agencies"].append(agency)
    return agency


def merge(seed: dict[str, Any], expansion: dict[str, Any]) -> dict[str, Any]:
    seed = json.loads(json.dumps(seed, ensure_ascii=False))
    for record in expansion.get("records", []):
        agency = find_or_create_agency(seed, record["domain"], record["agency"])
        agency["documents"] = unique([*agency.get("documents", []), *record.get("documents", [])])
        agency["keywords"] = unique([*agency.get("keywords", []), *record.get("keywords", [])])
        agency["sources"] = unique([*agency.get("sources", []), record["source_url"]])
        agency.setdefault("subcategories", []).append(
            {
                "name": record["source_title"],
                "phase": [record["stage"]],
                "documents": record.get("documents", []),
                "structure_patterns": ["official_form", "attachment_checklist"],
                "source_url": record["source_url"],
            }
        )
    seed["version"] = f"{seed.get('version', 'seed')}+web-expansion"
    seed["web_expansion"] = {
        "version": expansion.get("version"),
        "record_count": len(expansion.get("records", [])),
    }
    return seed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="data/agency_submission_taxonomy.seed.json")
    parser.add_argument("--expansion", default="data/agency_submission_web_source_expansion.json")
    parser.add_argument("--output", default="data/agency_submission_taxonomy.web_expanded.json")
    args = parser.parse_args()

    seed = json.loads(Path(args.seed).read_text(encoding="utf-8"))
    expansion = json.loads(Path(args.expansion).read_text(encoding="utf-8"))
    merged = merge(seed, expansion)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    docs = [doc for agency in merged.get("agencies", []) for doc in agency.get("documents", [])]
    sources = [src for agency in merged.get("agencies", []) for src in agency.get("sources", [])]
    print(f"wrote {output_path}")
    print(f"agencies={len(merged.get('agencies', []))}")
    print(f"documents_raw={len(docs)} unique={len(set(docs))}")
    print(f"sources_raw={len(sources)} unique={len(set(sources))}")
    print(f"web_expansion_records={len(expansion.get('records', []))}")


if __name__ == "__main__":
    main()
