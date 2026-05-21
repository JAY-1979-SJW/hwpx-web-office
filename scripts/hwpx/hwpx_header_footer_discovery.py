"""Discover visible header/footer and master page structures in HWPX files."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


STRUCTURE_TERMS = [
    "<hm:",
    "<hp:masterPage",
    "masterPageCnt=\"1\"",
    "masterPageCnt=\"2\"",
    "headerIDRef",
    "footerIDRef",
    "<hp:header",
    "<hp:footer",
    "pageNumCtrl",
]

STRUCTURE_LOCAL_NAMES = {
    "header",
    "footer",
    "masterPage",
    "pageNumCtrl",
    "autoNum",
    "newNum",
    "startNum",
    "beginNum",
    "visibility",
}


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def _snippet(text: str, term: str, size: int = 240) -> str:
    index = text.find(term)
    if index < 0:
        return ""
    return text[max(0, index - size) : index + size].replace("\r", " ").replace("\n", " ")


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def _element_text(elem: ET.Element, limit: int = 80) -> str:
    text = "".join(elem.itertext()).strip()
    text = " ".join(text.split())
    return text[:limit]


def _parent_map(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def _xpath_for(elem: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    parts = [_local_name(elem.tag)]
    current = elem
    while current in parents:
        current = parents[current]
        parts.append(_local_name(current.tag))
    return "/" + "/".join(reversed(parts))


def _xml_structure_hits(entry: str, text: str) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except Exception:
        return hits
    parents = _parent_map(root)
    for elem in root.iter():
        name = _local_name(elem.tag)
        if name not in STRUCTURE_LOCAL_NAMES:
            continue
        hits.append(
            {
                "entry": entry,
                "local_name": name,
                "path": _xpath_for(elem, parents),
                "attributes": dict(elem.attrib),
                "text": _element_text(elem),
            }
        )
    return hits


def inspect_hwpx(path: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "file": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
        "zip_ok": False,
        "entry_count": 0,
        "header_footer_entries": [],
        "term_hits": [],
        "xml_structure_hits": [],
        "status": "UNKNOWN",
    }
    if not path.exists():
        row["status"] = "FILE_NOT_FOUND"
        return row
    try:
        with ZipFile(path) as zf:
            names = zf.namelist()
            row["zip_ok"] = True
            row["entry_count"] = len(names)
            row["header_footer_entries"] = [
                name
                for name in names
                if any(token in name.lower() for token in ("header", "footer", "master"))
            ]
            for name in names:
                if not name.lower().endswith(".xml"):
                    continue
                text = _decode(zf.read(name))
                for term in STRUCTURE_TERMS:
                    if term in text:
                        row["term_hits"].append(
                            {
                                "entry": name,
                                "term": term,
                                "snippet": _snippet(text, term),
                            }
                        )
                row["xml_structure_hits"].extend(_xml_structure_hits(name, text))
    except BadZipFile:
        row["status"] = "BAD_ZIP"
        return row
    except Exception as exc:  # noqa: BLE001
        row["status"] = "ERROR"
        row["error"] = str(exc)
        return row
    row["status"] = (
        "VISIBLE_HEADER_FOOTER_STRUCTURE_FOUND"
        if row["term_hits"] or row["xml_structure_hits"]
        else "STRUCTURE_NOT_FOUND"
    )
    return row


def discover(root: Path, include_tmp: bool = False, limit: int | None = None) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for path in root.rglob("*.hwpx"):
        if not include_tmp and "tmp" in path.parts:
            continue
        rows.append(inspect_hwpx(path))
        if limit is not None and len(rows) >= limit:
            break
    found = [row for row in rows if row["status"] == "VISIBLE_HEADER_FOOTER_STRUCTURE_FOUND"]
    return {
        "root": str(root),
        "include_tmp": include_tmp,
        "file_count": len(rows),
        "found_count": len(found),
        "status": "PASS" if found else "WARN",
        "rows": rows,
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "file",
        "size",
        "zip_ok",
        "entry_count",
        "status",
        "term_hit_count",
        "xml_hit_count",
        "header_footer_entries",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "file": row.get("file"),
                    "size": row.get("size"),
                    "zip_ok": row.get("zip_ok"),
                    "entry_count": row.get("entry_count"),
                    "status": row.get("status"),
                    "term_hit_count": len(row.get("term_hits", [])),
                    "xml_hit_count": len(row.get("xml_structure_hits", [])),
                    "header_footer_entries": ";".join(row.get("header_footer_entries", [])),
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover HWPX visible header/footer structures")
    parser.add_argument("--root", default=".", help="directory to scan")
    parser.add_argument("--include-tmp", action="store_true", help="include tmp directory")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-csv")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = discover(Path(args.root), include_tmp=bool(args.include_tmp), limit=args.limit)
    write_json(Path(args.out_json), report)
    if args.out_csv:
        write_csv(Path(args.out_csv), report["rows"])
    print(json.dumps({k: report[k] for k in ("status", "file_count", "found_count")}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
