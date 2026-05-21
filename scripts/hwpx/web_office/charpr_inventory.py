"""WEB-OFFICE-PARA-EDIT-FORMAT-CHARPR-INVENTORY-01 — read-only charPr inventory.

ApplyFormat 본공사 전, HWPX 의 paragraph/run charPrIDRef 사용 현황과
header.xml 의 charPr 정의를 매핑해 가시화한다.

본 모듈은 writer / output / 원본 mutation 을 일절 호출하지 않는다.
입력 HWPX 의 sha256/mtime 을 변경하지 않는다.
"""
from __future__ import annotations
import hashlib
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))
_HX = _PR / "scripts" / "hwpx"
if str(_HX) not in sys.path:
    sys.path.insert(0, str(_HX))

from hwpx_package import HwpxPackage  # noqa: E402
from scripts.hwpx.parser.style_parser import (  # noqa: E402
    parse_char_pr_defs, parse_font_face_table)
from scripts.hwpx.web_office.ro_view_importer import (  # noqa: E402
    import_hwpx_as_ro_view)


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _read_header_bytes(package: HwpxPackage) -> bytes | None:
    for entry in ("Contents/header.xml", "Contents\\header.xml"):
        if entry in package.entries:
            return package.entries[entry]
    for name, data in package.entries.items():
        if name.replace("\\", "/").endswith("Contents/header.xml"):
            return data
    return None


def _attrs_for(char_pr_defs: dict[str, dict],
                          char_pr_id: str | None) -> dict[str, Any]:
    if char_pr_id is None:
        return {"fontName": None, "fontFace": None,
                  "fontSizePt": None, "height": None,
                  "textColor": None, "bold": None, "italic": None,
                  "underline": None}
    d = char_pr_defs.get(str(char_pr_id))
    if d is None:
        return {"fontName": None, "fontFace": None,
                  "fontSizePt": None, "height": None,
                  "textColor": None, "bold": None, "italic": None,
                  "underline": None}
    return {
        "fontName": d.get("fontName"),
        "fontFace": d.get("fontFace"),
        "fontSizePt": d.get("fontSizePt"),
        "height": d.get("height"),
        "textColor": d.get("textColor") or None,
        "bold": d.get("bold"),
        "italic": d.get("italic"),
        "underline": d.get("underline"),
    }


def paragraph_char_pr_inventory(
    source_hwpx: Path,
    *, paragraph_id: str | None = None,
    include_unused_header: bool = True,
) -> dict[str, Any]:
    """HWPX 한 건의 charPr inventory 를 산출한다.

    Parameters
    ----------
    source_hwpx :
        대상 HWPX 경로 (read-only, mutation 0).
    paragraph_id :
        지정 시 해당 paragraph 만 paragraphInventory 에 적재. None 이면
        모든 paragraph.
    include_unused_header :
        header.xml 에는 정의되어 있으나 본문에서 한 번도 참조되지 않은
        charPr id 도 unusedHeaderCharPrIds 에 적재할지.

    Returns
    -------
    dict with keys:
        sourcePath, sourceSha256, headerCharPrCount,
        paragraphInventory: {paragraphId: [
            {charPrId, usageCount, totalRuns, fontName, fontFace,
                fontSizePt, height, textColor, bold, italic, underline,
                inHeader}
        ]},
        documentInventory: [동일 schema, 문서 전체 집계],
        danglingCharPrIDRefs: 본문 참조 - header 정의 없는 id 목록,
        unusedHeaderCharPrIds: header 정의 - 본문 미참조 id 목록.
    """
    source_hwpx = Path(source_hwpx)
    sha_before = _sha256(source_hwpx)
    mt_before = source_hwpx.stat().st_mtime_ns

    package = HwpxPackage(source_hwpx)
    header_bytes = _read_header_bytes(package)
    if header_bytes is None:
        char_pr_defs: dict[str, dict] = {}
    else:
        font_table = parse_font_face_table(header_bytes)
        char_pr_defs = parse_char_pr_defs(header_bytes, font_table)

    doc = import_hwpx_as_ro_view(source_hwpx)

    paragraph_inventory: dict[str, list[dict]] = {}
    document_counter: Counter[str | None] = Counter()
    document_total_runs = 0

    for par in doc.paragraphs:
        run_prs = [r.charPrIDRef for r in par.runs]
        # documentInventory 는 paragraph_id 필터와 무관하게 문서 전체 집계
        document_total_runs += len(run_prs)
        for pr in run_prs:
            document_counter[pr] += 1
        if paragraph_id is not None and par.paragraphId != paragraph_id:
            continue
        per_para = Counter(run_prs)
        entries: list[dict] = []
        for cid, cnt in per_para.items():
            attrs = _attrs_for(char_pr_defs, cid)
            entries.append({
                "charPrId": cid,
                "usageCount": cnt,
                "totalRuns": len(run_prs),
                "inHeader": (cid is not None
                                      and str(cid) in char_pr_defs),
                **attrs,
            })
        # usageCount 내림차순 + None 마지막
        entries.sort(key=lambda e: (
            e["charPrId"] is None, -e["usageCount"]))
        paragraph_inventory[par.paragraphId] = entries

    document_inventory: list[dict] = []
    for cid, cnt in document_counter.items():
        attrs = _attrs_for(char_pr_defs, cid)
        document_inventory.append({
            "charPrId": cid,
            "usageCount": cnt,
            "totalRuns": document_total_runs,
            "inHeader": cid is not None and str(cid) in char_pr_defs,
            **attrs,
        })
    document_inventory.sort(key=lambda e: (
        e["charPrId"] is None, -e["usageCount"]))

    body_referenced = {str(cid) for cid in document_counter
                              if cid is not None}
    header_ids = set(char_pr_defs.keys())
    dangling = sorted(body_referenced - header_ids)
    unused = (sorted(header_ids - body_referenced)
                  if include_unused_header else [])

    # 원본 무변경 사후 확인
    assert _sha256(source_hwpx) == sha_before, (
        "charPr inventory must not modify source HWPX")
    assert source_hwpx.stat().st_mtime_ns == mt_before, (
        "charPr inventory must not touch source mtime")

    return {
        "sourcePath": str(source_hwpx),
        "sourceSha256": sha_before,
        "headerCharPrCount": len(char_pr_defs),
        "paragraphInventory": paragraph_inventory,
        "documentInventory": document_inventory,
        "danglingCharPrIDRefs": dangling,
        "unusedHeaderCharPrIds": unused,
    }


def char_pr_defs_only(source_hwpx: Path) -> dict[str, dict]:
    """header.xml 의 charPr 정의 dict 만 (id → 속성). RO-VIEW additive
    참조용. 본문 분석 없음.
    """
    source_hwpx = Path(source_hwpx)
    package = HwpxPackage(source_hwpx)
    header_bytes = _read_header_bytes(package)
    if header_bytes is None:
        return {}
    return parse_char_pr_defs(
        header_bytes, parse_font_face_table(header_bytes))
