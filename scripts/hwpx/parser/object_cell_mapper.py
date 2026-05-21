"""HWPX-RECOGNITION-OBJECT-IN-CELL-MAPPING-01

XML 구조 기반 객체↔셀 매핑 (read-only).

객체(pic/rect/line/ellipse/container/arc/curve/polygon)가 어느 hp:tc 셀의
descendant인지 식별하고, 셀 외부 객체는 OUT_OF_CELL로 분류한다.
좌표 추론 기반 매핑은 이번 공정 범위 밖이다.

이 모듈은 writer를 호출하지 않으며 원본 파일은 절대 수정되지 않는다.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_TAG_TBL = f"{{{NS_HP}}}tbl"
_TAG_TR = f"{{{NS_HP}}}tr"
_TAG_TC = f"{{{NS_HP}}}tc"
_TAG_CELLSPAN = f"{{{NS_HP}}}cellSpan"
_TAG_T = f"{{{NS_HP}}}t"

# object_parser와 동일한 8종 객체 태그 매핑
_OBJECT_TAG_TO_TYPE: dict[str, str] = {
    "pic": "picture",
    "rect": "rect",
    "line": "line",
    "ellipse": "ellipse",
    "container": "container",
    "arc": "arc",
    "curve": "curve",
    "polygon": "polygon",
}
_IMAGE_LIKE_TYPES: frozenset[str] = frozenset({"picture", "container"})


@dataclass
class ObjectCellMappingEntry:
    objectKey: str
    objectType: str
    objectRawTag: str
    sectionIndex: int
    tableIndex: int | None
    rowIndex: int | None
    cellIndex: int | None
    cellKey: str | None
    cellText: str | None
    rowSpan: int | None
    colSpan: int | None
    binDataRef: str | None
    confidence: float
    reason: str
    isImageLike: bool = False

    def to_dict(self) -> dict:
        return {
            "objectKey": self.objectKey,
            "objectType": self.objectType,
            "objectRawTag": self.objectRawTag,
            "sectionIndex": self.sectionIndex,
            "tableIndex": self.tableIndex,
            "rowIndex": self.rowIndex,
            "cellIndex": self.cellIndex,
            "cellKey": self.cellKey,
            "cellText": self.cellText,
            "rowSpan": self.rowSpan,
            "colSpan": self.colSpan,
            "binDataRef": self.binDataRef,
            "confidence": self.confidence,
            "reason": self.reason,
            "isImageLike": self.isImageLike,
        }


@dataclass
class GeometricCandidateEntry:
    """OUT_OF_CELL 객체에 대한 좌표 기반 추론 후보. confidence < 1.0 보장."""
    objectKey: str
    objectType: str
    candidateCellKey: str | None
    tableIndex: int | None
    rowIndex: int | None
    cellIndex: int | None
    cellText: str | None
    overlapRatio: float | None
    centerDistance: float | None
    confidence: float
    reason: str
    ambiguous: bool = False

    def to_dict(self) -> dict:
        return {
            "objectKey": self.objectKey,
            "objectType": self.objectType,
            "candidateCellKey": self.candidateCellKey,
            "tableIndex": self.tableIndex,
            "rowIndex": self.rowIndex,
            "cellIndex": self.cellIndex,
            "cellText": self.cellText,
            "overlapRatio": self.overlapRatio,
            "centerDistance": self.centerDistance,
            "confidence": self.confidence,
            "reason": self.reason,
            "ambiguous": self.ambiguous,
        }


@dataclass
class ObjectCellMappingResult:
    documentHash: str = ""
    sourcePath: str = ""
    tableCount: int = 0
    cellCount: int = 0
    objectCount: int = 0
    mappedObjectCount: int = 0
    unmappedObjectCount: int = 0
    mappings: list[ObjectCellMappingEntry] = field(default_factory=list)
    # geometric inference (이번 공정 추가, 기본값은 비어 있음)
    geometricCandidates: list[GeometricCandidateEntry] = field(default_factory=list)
    geometricCandidateCount: int = 0
    geometricMappedCandidateCount: int = 0
    ambiguousCandidateCount: int = 0
    noGeometryObjectCount: int = 0
    coordinateUnit: str = "UNKNOWN"
    # confirmation gate (HWPX-RECOGNITION-OBJECT-CELL-GEOMETRIC-CONFIRMATION-GATE-01)
    # 기본은 비활성. apply_geometric_confirmation 호출 시에만 채워진다.
    confirmationApplied: bool = False
    confirmationDecisionCount: int = 0
    confirmedMappingCount: int = 0
    rejectedCandidateCount: int = 0
    heldCandidateCount: int = 0
    blockedConfirmationCount: int = 0
    confirmationResults: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "documentHash": self.documentHash,
            "sourcePath": self.sourcePath,
            "tableCount": self.tableCount,
            "cellCount": self.cellCount,
            "objectCount": self.objectCount,
            "mappedObjectCount": self.mappedObjectCount,
            "unmappedObjectCount": self.unmappedObjectCount,
            "mappings": [m.to_dict() for m in self.mappings],
            "geometricCandidates": [g.to_dict() for g in self.geometricCandidates],
            "geometricCandidateCount": self.geometricCandidateCount,
            "geometricMappedCandidateCount": self.geometricMappedCandidateCount,
            "ambiguousCandidateCount": self.ambiguousCandidateCount,
            "noGeometryObjectCount": self.noGeometryObjectCount,
            "coordinateUnit": self.coordinateUnit,
            "confirmationApplied": self.confirmationApplied,
            "confirmationDecisionCount": self.confirmationDecisionCount,
            "confirmedMappingCount": self.confirmedMappingCount,
            "rejectedCandidateCount": self.rejectedCandidateCount,
            "heldCandidateCount": self.heldCandidateCount,
            "blockedConfirmationCount": self.blockedConfirmationCount,
            "confirmationResults": [
                (r.to_dict() if hasattr(r, "to_dict") else dict(r))
                for r in self.confirmationResults
            ],
        }


# ── 헬퍼 ──────────────────────────────────────────────────────────────────────

def _parser_normalize(text: str) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(r"[\r\n\t]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"(?<=[가-힣]) (?=[가-힣])", "", t)
    return t


def _cell_span(tc: ET.Element) -> tuple[int, int]:
    for child in tc:
        if child.tag == _TAG_CELLSPAN:
            try:
                return (int(child.attrib.get("colSpan", "1")),
                        int(child.attrib.get("rowSpan", "1")))
            except ValueError:
                return 1, 1
    return 1, 1


def _cell_normalized_text(tc: ET.Element) -> str:
    parts = []
    for el in tc.iter():
        if el.tag == _TAG_TBL:
            continue   # nested table 내부 텍스트는 셀 자체 텍스트로 보지 않음
        if el.tag == _TAG_T and el.text:
            parts.append(el.text)
    return _parser_normalize("".join(parts))


def _find_bin_data_ref(elem: ET.Element) -> str | None:
    for descendant in elem.iter():
        bid = descendant.get("binaryItemIDRef", "") if hasattr(descendant, "get") else ""
        if bid:
            return bid
    return None


# ── 메인 매핑 함수 ────────────────────────────────────────────────────────────

def map_objects_to_cells(source_path: Path) -> ObjectCellMappingResult:
    """HWPX 파일에서 객체↔셀 매핑을 계산. read-only / 원본 무수정."""
    source_path = Path(source_path)
    raw = source_path.read_bytes()
    doc_hash = hashlib.sha256(raw).hexdigest()

    section_xmls: dict[str, bytes] = {}
    with zipfile.ZipFile(source_path) as zf:
        for n in sorted(zf.namelist()):
            if "section" in n and n.endswith(".xml"):
                section_xmls[n] = zf.read(n)

    return _map_from_section_xmls(
        list(section_xmls.values()),
        document_hash=doc_hash,
        source_path=str(source_path).replace("\\", "/"),
    )


def _map_from_section_xmls(section_xmls: list[bytes],
                              document_hash: str = "",
                              source_path: str = "") -> ObjectCellMappingResult:
    """section XML bytes 리스트를 직접 받아 매핑 산출 (테스트 보조 API)."""
    mappings: list[ObjectCellMappingEntry] = []
    seen_object_keys: set[str] = set()
    table_count_global = 0
    cell_count_global = 0

    for section_idx, raw in enumerate(section_xmls):
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue

        section_table_counter = [0]
        section_obj_counter = [0]
        section_cell_counter = [0]
        cell_stack: list[dict] = []
        local_mappings: list[ObjectCellMappingEntry] = []

        def walk(elem: ET.Element) -> None:
            tag = elem.tag.split("}")[-1]

            if tag == "tbl":
                table_idx_in_section = section_table_counter[0]
                section_table_counter[0] += 1
                global_table_idx = table_count_global + table_idx_in_section
                row_idx = 0
                for tr in list(elem):
                    if tr.tag != _TAG_TR:
                        continue
                    col_idx = 0
                    for tc in list(tr):
                        if tc.tag != _TAG_TC:
                            continue
                        col_span, row_span = _cell_span(tc)
                        cell_text = _cell_normalized_text(tc)
                        cell_key = (f"t_s{section_idx}_"
                                      f"{table_idx_in_section:03d}:r{row_idx}:c{col_idx}")
                        cell_info = {
                            "tableIndex": global_table_idx,
                            "rowIndex": row_idx,
                            "cellIndex": col_idx,
                            "cellKey": cell_key,
                            "rowSpan": row_span,
                            "colSpan": col_span,
                            "cellText": cell_text,
                        }
                        cell_stack.append(cell_info)
                        section_cell_counter[0] += 1
                        for child in list(tc):
                            walk(child)
                        cell_stack.pop()
                        col_idx += 1
                    row_idx += 1
                return

            obj_type = _OBJECT_TAG_TO_TYPE.get(tag)
            if obj_type is not None:
                raw_id = elem.get("id", "")
                seq = section_obj_counter[0]
                section_obj_counter[0] += 1
                object_key = f"obj:s{section_idx}:{raw_id or 'auto'}:{seq:04d}"
                # 안전: duplicate key 방지 (이론상 불가하지만 한번 더 확인)
                while object_key in seen_object_keys:
                    seq += 1
                    object_key = f"obj:s{section_idx}:{raw_id or 'auto'}:{seq:04d}"
                seen_object_keys.add(object_key)

                bin_ref = _find_bin_data_ref(elem)
                is_image_like = (obj_type in _IMAGE_LIKE_TYPES) or (bin_ref is not None)

                if cell_stack:
                    top = cell_stack[-1]
                    entry = ObjectCellMappingEntry(
                        objectKey=object_key, objectType=obj_type, objectRawTag=tag,
                        sectionIndex=section_idx,
                        tableIndex=top["tableIndex"], rowIndex=top["rowIndex"],
                        cellIndex=top["cellIndex"], cellKey=top["cellKey"],
                        cellText=top["cellText"],
                        rowSpan=top["rowSpan"], colSpan=top["colSpan"],
                        binDataRef=bin_ref, confidence=1.0,
                        reason="DESCENDANT_OF_TC", isImageLike=is_image_like,
                    )
                else:
                    entry = ObjectCellMappingEntry(
                        objectKey=object_key, objectType=obj_type, objectRawTag=tag,
                        sectionIndex=section_idx,
                        tableIndex=None, rowIndex=None, cellIndex=None,
                        cellKey=None, cellText=None,
                        rowSpan=None, colSpan=None, binDataRef=bin_ref,
                        confidence=0.0, reason="OUT_OF_CELL",
                        isImageLike=is_image_like,
                    )
                local_mappings.append(entry)
                # object의 children에는 재귀하지 않는다 (그룹/컨테이너 단위로 1건)
                return

            for child in list(elem):
                walk(child)

        for child in list(root):
            walk(child)

        mappings.extend(local_mappings)
        table_count_global += section_table_counter[0]
        cell_count_global += section_cell_counter[0]

    mapped = sum(1 for m in mappings if m.cellKey is not None)
    unmapped = sum(1 for m in mappings if m.cellKey is None)
    return ObjectCellMappingResult(
        documentHash=document_hash,
        sourcePath=source_path,
        tableCount=table_count_global,
        cellCount=cell_count_global,
        objectCount=len(mappings),
        mappedObjectCount=mapped,
        unmappedObjectCount=unmapped,
        mappings=mappings,
    )


# ── geometric inference (XML ancestry 매핑은 변경 없음) ──────────────────────

# overlap 점수 차이가 이 미만이면 ambiguous로 분류
_AMBIGUITY_OVERLAP_DELTA: float = 0.05
# confidence 상한
_CONF_CENTER_INSIDE_CELL_MAX: float = 0.8
_CONF_BBOX_OVERLAP_MAX: float = 0.8
_CONF_NEAREST_CELL_MAX: float = 0.6


def _int_or_none(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _extract_bbox(elem: ET.Element) -> tuple[int, int, int, int] | None:
    """element에서 (x, y, width, height) 추출. 없으면 None."""
    x = _int_or_none(elem.get("x"))
    y = _int_or_none(elem.get("y"))
    w = _int_or_none(elem.get("width"))
    h = _int_or_none(elem.get("height"))
    if all(v is not None for v in (x, y, w, h)):
        return x, y, w, h
    # 자식 <hp:bbox x y width height/>
    bbox = elem.find(f"{{{NS_HP}}}bbox")
    if bbox is not None:
        bx = _int_or_none(bbox.get("x"))
        by = _int_or_none(bbox.get("y"))
        bw = _int_or_none(bbox.get("width"))
        bh = _int_or_none(bbox.get("height"))
        if all(v is not None for v in (bx, by, bw, bh)):
            return bx, by, bw, bh
    # 객체용 패턴: <hp:offset x y/> + <hp:curSz width height/> (또는 orgSz)
    off = elem.find(f"{{{NS_HP}}}offset")
    sz = elem.find(f"{{{NS_HP}}}curSz")
    if sz is None:
        sz = elem.find(f"{{{NS_HP}}}orgSz")
    if off is not None and sz is not None:
        ox = _int_or_none(off.get("x"))
        oy = _int_or_none(off.get("y"))
        sw = _int_or_none(sz.get("width"))
        sh = _int_or_none(sz.get("height"))
        if all(v is not None for v in (ox, oy, sw, sh)):
            return ox, oy, sw, sh
    return None


def _bbox_overlap_area(a: tuple[int, int, int, int],
                        b: tuple[int, int, int, int]) -> float:
    ax1, ay1, aw, ah = a
    ax2, ay2 = ax1 + aw, ay1 + ah
    bx1, by1, bw, bh = b
    bx2, by2 = bx1 + bw, by1 + bh
    ix = max(0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0, min(ay2, by2) - max(ay1, by1))
    return float(ix * iy)


def _bbox_area(a: tuple[int, int, int, int]) -> float:
    return float(a[2]) * float(a[3])


def _bbox_center(a: tuple[int, int, int, int]) -> tuple[float, float]:
    return (a[0] + a[2] / 2.0, a[1] + a[3] / 2.0)


def _center_inside(point: tuple[float, float], bbox: tuple[int, int, int, int]) -> bool:
    return (bbox[0] <= point[0] <= bbox[0] + bbox[2]
            and bbox[1] <= point[1] <= bbox[1] + bbox[3])


def _euclid(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    dx = p1[0] - p2[0]; dy = p1[1] - p2[1]
    return (dx * dx + dy * dy) ** 0.5


def _collect_geometry_from_section_xmls(section_xmls: list[bytes]):
    """section XMLs에서 cell/object의 bbox를 수집해 dict로 반환.

    cellKey, objectKey는 _map_from_section_xmls와 동일 규칙으로 발급.
    """
    cell_geom: dict[str, dict] = {}   # cellKey → {bbox, tableIndex, rowIndex, cellIndex, rowSpan, colSpan, cellText}
    object_geom: dict[str, dict] = {} # objectKey → {bbox, objectType}
    seen_object_keys: set[str] = set()
    table_count_global = 0

    for section_idx, raw in enumerate(section_xmls):
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue

        section_table_counter = [0]
        section_obj_counter = [0]
        cell_stack: list[dict] = []

        def walk(elem: ET.Element) -> None:
            tag = elem.tag.split("}")[-1]
            if tag == "tbl":
                tbl_idx = section_table_counter[0]
                section_table_counter[0] += 1
                row_idx = 0
                for tr in list(elem):
                    if tr.tag != _TAG_TR:
                        continue
                    col_idx = 0
                    for tc in list(tr):
                        if tc.tag != _TAG_TC:
                            continue
                        col_span, row_span = _cell_span(tc)
                        cell_text = _cell_normalized_text(tc)
                        cell_key = f"t_s{section_idx}_{tbl_idx:03d}:r{row_idx}:c{col_idx}"
                        bbox = _extract_bbox(tc)
                        cell_geom[cell_key] = {
                            "tableIndex": table_count_global + tbl_idx,
                            "rowIndex": row_idx, "cellIndex": col_idx,
                            "rowSpan": row_span, "colSpan": col_span,
                            "cellText": cell_text, "bbox": bbox,
                        }
                        cell_stack.append({"cellKey": cell_key})
                        for child in list(tc):
                            walk(child)
                        cell_stack.pop()
                        col_idx += 1
                    row_idx += 1
                return

            obj_type = _OBJECT_TAG_TO_TYPE.get(tag)
            if obj_type is not None:
                raw_id = elem.get("id", "")
                seq = section_obj_counter[0]
                section_obj_counter[0] += 1
                object_key = f"obj:s{section_idx}:{raw_id or 'auto'}:{seq:04d}"
                while object_key in seen_object_keys:
                    seq += 1
                    object_key = f"obj:s{section_idx}:{raw_id or 'auto'}:{seq:04d}"
                seen_object_keys.add(object_key)
                object_geom[object_key] = {
                    "objectType": obj_type,
                    "bbox": _extract_bbox(elem),
                    "inCellStack": bool(cell_stack),
                }
                return

            for child in list(elem):
                walk(child)

        for child in list(root):
            walk(child)
        table_count_global += section_table_counter[0]

    return cell_geom, object_geom


def map_objects_to_cells_with_geometry(source_path: Path) -> ObjectCellMappingResult:
    """기본 매핑 위에 좌표 추론 candidate를 덧붙여 반환.

    - 기존 mappings[]는 변경하지 않는다 (XML ancestry confidence=1.0 보존).
    - OUT_OF_CELL 객체에 한해 geometricCandidates를 채운다.
    - 좌표가 없으면 NO_GEOMETRY 1건. 셀 bbox가 전혀 없으면 NO_CELL_GEOMETRY 1건.
    - 모호한 경우 ambiguous=true, 단일 확정 mapping으로 승격하지 않는다.
    """
    source_path = Path(source_path)
    raw = source_path.read_bytes()
    doc_hash = hashlib.sha256(raw).hexdigest()
    section_xmls: list[bytes] = []
    with zipfile.ZipFile(source_path) as zf:
        for n in sorted(zf.namelist()):
            if "section" in n and n.endswith(".xml"):
                section_xmls.append(zf.read(n))
    base = _map_from_section_xmls(
        section_xmls, document_hash=doc_hash,
        source_path=str(source_path).replace("\\", "/"),
    )
    return _augment_with_geometric_candidates(base, section_xmls)


def map_objects_to_cells_with_geometry_from_section_xmls(
        section_xmls: list[bytes], document_hash: str = "",
        source_path: str = "") -> ObjectCellMappingResult:
    """section XML 직접 입력용 테스트 보조 API."""
    base = _map_from_section_xmls(section_xmls,
                                       document_hash=document_hash,
                                       source_path=source_path)
    return _augment_with_geometric_candidates(base, section_xmls)


def _augment_with_geometric_candidates(base: ObjectCellMappingResult,
                                            section_xmls: list[bytes]) -> ObjectCellMappingResult:
    cell_geom, object_geom = _collect_geometry_from_section_xmls(section_xmls)

    has_any_cell_bbox = any(g["bbox"] is not None for g in cell_geom.values())
    has_any_object_bbox = any(g["bbox"] is not None for g in object_geom.values())
    if has_any_cell_bbox or has_any_object_bbox:
        base.coordinateUnit = "HWPX_UNIT"
    else:
        base.coordinateUnit = "UNKNOWN"

    seen_pair: set[tuple[str, str | None]] = set()
    candidates: list[GeometricCandidateEntry] = []
    no_geometry_count = 0
    ambiguous_object_keys: set[str] = set()

    out_of_cell_objects = [m for m in base.mappings
                              if m.reason == "OUT_OF_CELL"]

    for m in out_of_cell_objects:
        obj_info = object_geom.get(m.objectKey, {})
        obj_bbox = obj_info.get("bbox")
        if obj_bbox is None:
            entry = GeometricCandidateEntry(
                objectKey=m.objectKey, objectType=m.objectType,
                candidateCellKey=None, tableIndex=None, rowIndex=None,
                cellIndex=None, cellText=None,
                overlapRatio=None, centerDistance=None,
                confidence=0.0, reason="NO_GEOMETRY",
            )
            pair = (entry.objectKey, entry.candidateCellKey)
            if pair not in seen_pair:
                seen_pair.add(pair)
                candidates.append(entry)
                no_geometry_count += 1
            continue

        if not has_any_cell_bbox:
            entry = GeometricCandidateEntry(
                objectKey=m.objectKey, objectType=m.objectType,
                candidateCellKey=None, tableIndex=None, rowIndex=None,
                cellIndex=None, cellText=None,
                overlapRatio=None, centerDistance=None,
                confidence=0.0, reason="NO_CELL_GEOMETRY",
            )
            pair = (entry.objectKey, entry.candidateCellKey)
            if pair not in seen_pair:
                seen_pair.add(pair)
                candidates.append(entry)
                no_geometry_count += 1
            continue

        # 후보 셀 점수 계산
        obj_center = _bbox_center(obj_bbox)
        obj_area = max(1.0, _bbox_area(obj_bbox))
        candidate_scores: list[tuple[str, dict, float, float, bool]] = []
        # (cellKey, cell_geom_record, overlap_ratio, center_distance, center_inside)

        for cell_key, g in cell_geom.items():
            cell_bbox = g["bbox"]
            if cell_bbox is None:
                continue
            ov = _bbox_overlap_area(obj_bbox, cell_bbox)
            overlap_ratio = ov / obj_area
            center_distance = _euclid(obj_center, _bbox_center(cell_bbox))
            center_inside = _center_inside(obj_center, cell_bbox)
            candidate_scores.append(
                (cell_key, g, overlap_ratio, center_distance, center_inside)
            )

        if not candidate_scores:
            entry = GeometricCandidateEntry(
                objectKey=m.objectKey, objectType=m.objectType,
                candidateCellKey=None, tableIndex=None, rowIndex=None,
                cellIndex=None, cellText=None,
                overlapRatio=None, centerDistance=None,
                confidence=0.0, reason="NO_CELL_GEOMETRY",
            )
            pair = (entry.objectKey, entry.candidateCellKey)
            if pair not in seen_pair:
                seen_pair.add(pair)
                candidates.append(entry)
                no_geometry_count += 1
            continue

        center_inside_hits = [c for c in candidate_scores if c[4]]
        overlap_hits = [c for c in candidate_scores if c[2] > 0]

        if center_inside_hits:
            # 중심점이 cell bbox 내부 → CENTER_INSIDE_CELL
            top_overlap = max(c[2] for c in center_inside_hits)
            top_n = sorted(center_inside_hits, key=lambda c: -c[2])
            # ambiguous: 동일/유사 score 후보 2개 이상
            is_ambiguous = (len(center_inside_hits) >= 2
                              and (top_overlap - top_n[1][2]) < _AMBIGUITY_OVERLAP_DELTA)
            for ck, g, overlap_ratio, dist, _ in top_n:
                conf = min(_CONF_CENTER_INSIDE_CELL_MAX,
                            0.5 + 0.3 * min(1.0, overlap_ratio))
                entry = GeometricCandidateEntry(
                    objectKey=m.objectKey, objectType=m.objectType,
                    candidateCellKey=ck, tableIndex=g["tableIndex"],
                    rowIndex=g["rowIndex"], cellIndex=g["cellIndex"],
                    cellText=g["cellText"],
                    overlapRatio=round(overlap_ratio, 4),
                    centerDistance=round(dist, 2),
                    confidence=round(conf, 3),
                    reason="CENTER_INSIDE_CELL", ambiguous=is_ambiguous,
                )
                pair = (entry.objectKey, entry.candidateCellKey)
                if pair in seen_pair:
                    continue
                seen_pair.add(pair)
                candidates.append(entry)
            if is_ambiguous:
                ambiguous_object_keys.add(m.objectKey)
        elif overlap_hits:
            # bbox 일부 overlap → BBOX_OVERLAP
            top_overlap = max(c[2] for c in overlap_hits)
            top_n = sorted(overlap_hits, key=lambda c: -c[2])
            is_ambiguous = (len(overlap_hits) >= 2
                              and (top_overlap - top_n[1][2]) < _AMBIGUITY_OVERLAP_DELTA)
            for ck, g, overlap_ratio, dist, _ in top_n:
                conf = min(_CONF_BBOX_OVERLAP_MAX, 0.3 + 0.5 * min(1.0, overlap_ratio))
                entry = GeometricCandidateEntry(
                    objectKey=m.objectKey, objectType=m.objectType,
                    candidateCellKey=ck, tableIndex=g["tableIndex"],
                    rowIndex=g["rowIndex"], cellIndex=g["cellIndex"],
                    cellText=g["cellText"],
                    overlapRatio=round(overlap_ratio, 4),
                    centerDistance=round(dist, 2),
                    confidence=round(conf, 3),
                    reason="BBOX_OVERLAP", ambiguous=is_ambiguous,
                )
                pair = (entry.objectKey, entry.candidateCellKey)
                if pair in seen_pair:
                    continue
                seen_pair.add(pair)
                candidates.append(entry)
            if is_ambiguous:
                ambiguous_object_keys.add(m.objectKey)
        else:
            # overlap 없음 → NEAREST_CELL 단일 후보 (가장 가까운 셀)
            nearest = min(candidate_scores, key=lambda c: c[3])
            ck, g, _ov, dist, _ = nearest
            # 거리가 가까울수록 confidence 높음 (상한 0.6)
            # 정규화 기준: 객체 자체 크기로 정규화
            obj_diag = (obj_bbox[2] ** 2 + obj_bbox[3] ** 2) ** 0.5 or 1.0
            normalized = max(0.0, 1.0 - dist / (obj_diag * 4.0))
            conf = min(_CONF_NEAREST_CELL_MAX, 0.2 + 0.4 * normalized)
            entry = GeometricCandidateEntry(
                objectKey=m.objectKey, objectType=m.objectType,
                candidateCellKey=ck, tableIndex=g["tableIndex"],
                rowIndex=g["rowIndex"], cellIndex=g["cellIndex"],
                cellText=g["cellText"],
                overlapRatio=0.0, centerDistance=round(dist, 2),
                confidence=round(conf, 3),
                reason="NEAREST_CELL", ambiguous=False,
            )
            pair = (entry.objectKey, entry.candidateCellKey)
            if pair not in seen_pair:
                seen_pair.add(pair)
                candidates.append(entry)

    base.geometricCandidates = candidates
    base.geometricCandidateCount = len(candidates)
    base.geometricMappedCandidateCount = sum(1 for c in candidates if c.confidence > 0)
    base.ambiguousCandidateCount = sum(1 for c in candidates if c.ambiguous)
    base.noGeometryObjectCount = no_geometry_count
    return base
