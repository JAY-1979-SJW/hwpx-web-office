"""HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01.

B동 (XML 정밀 진단동) — 9개 reason_code 진단 함수 contract.

A동(인식)이 못 풀어낸 케이스를 진단하여 xml_deep_analyzer_need_flags 후보로
변환한다. 본 모듈은 결정론적(deterministic) 진단만 수행한다.

방화구획 (CLAUDE.md §6):
- writer 미호출
- output HWPX 미생성
- AI / OCR 미호출
- secret / DB URL 출력 금지
- production 모듈(fill_review_contract, live_pipeline, ui_adapter,
  evidence_ingestion_contract)에서 본 모듈 import 금지
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

CONTRACT_NAME = "HWPX-XML-DEEP-STRUCTURE-ANALYZER-CONTRACT-01"
ANALYZER_VERSION = "v2"  # v2: 9 진단실 내부 정밀화 (context detail 풍부화)
# v1 → v2: 시그니처/enum/반환 키는 동일. context 안에 추가 detail 제공.

ALLOWED_REASON_CODE: frozenset[str] = frozenset({
    "RUN_BOUNDARY_UNSUPPORTED",
    "CHECKBOX_OR_SHAPE_NEEDED",
    "OBJECT_ANCHOR_NEEDED",
    "STYLE_RESOLUTION_NEEDED",
    "CELL_INTERNAL_PARAGRAPH_NEEDED",
    "MERGED_CELL_GEOMETRY_NEEDED",
    "READBACK_MISMATCH",
    "TARGET_AMBIGUOUS",
    "LABEL_CONTEXT_INSUFFICIENT",
})
ALLOWED_SEVERITY: frozenset[str] = frozenset({"LOW", "MEDIUM", "HIGH"})

REQUIRED_ANALYZER_NAMES: tuple[str, ...] = (
    "analyze_run_boundary",
    "analyze_checkbox_or_shape",
    "analyze_object_anchor",
    "analyze_style_resolution",
    "analyze_cell_internal_paragraph",
    "analyze_merged_cell_geometry",
    "analyze_readback_mismatch",
    "analyze_target_ambiguous",
    "analyze_label_context_sufficiency",
)

# HWPX namespace는 문서별로 다를 수 있어, 진단 함수는 namespace-agnostic하게
# local-name() 기준으로 판정한다.
_HP_RUN_LOCAL = "run"
_HP_PARA_LOCAL = "p"
_HP_TEXT_LOCAL = "t"
_HP_CELL_LOCAL = "tc"
_HP_TABLE_LOCAL = "tbl"
_HP_SHAPE_LOCALS = ("rect", "ellipse", "line", "polygon", "shape", "compoundShape", "container")
_HP_CHECKBOX_HINTS = ("checkbox", "checkButton", "buttonCheck", "formCheck", "ctrlCheck")
_HP_OBJECT_LOCALS = ("pic", "ole", "video", "equation", "drawingObject", "objectAnchor")


def _local(tag: str) -> str:
    """ET tag에서 namespace 제거한 local name."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _iter_local(elem: ET.Element, local: str):
    """주어진 local-name과 일치하는 후손 노드 yield."""
    for node in elem.iter():
        if _local(node.tag) == local:
            yield node


def _make_flag(
    *,
    reason_code: str,
    severity: str,
    target_key: str | None = None,
    normalized_label: str | None = None,
    context: dict | None = None,
) -> dict:
    if reason_code not in ALLOWED_REASON_CODE:
        raise ValueError(f"invalid reason_code: {reason_code}")
    if severity not in ALLOWED_SEVERITY:
        raise ValueError(f"invalid severity: {severity}")
    return {
        "reason_code": reason_code,
        "severity": severity,
        "target_key": target_key,
        "normalized_label": normalized_label,
        "context": context or {},
        "analyzer_version": ANALYZER_VERSION,
    }


# ── 1) RUN_BOUNDARY_UNSUPPORTED ──────────────────────────────────────────────


def analyze_run_boundary(
    paragraph_xml: str, *, target_key: str | None = None, normalized_label: str | None = None
) -> dict | None:
    """한 paragraph 내 run 경계 분할이 writer가 지원할 수 없는 형태인지 진단.

    detection rule:
      - run 개수 >= 2 이면서, 동일 텍스트 영역이 여러 run으로 쪼개진 경우
        (예: "공사명: " + "[___]" + " 검측" — writer가 어디에 쓸지 모름)
      - text-bearing run이 3개 이상이면 HIGH
    """
    try:
        root = ET.fromstring(paragraph_xml)
    except ET.ParseError as e:
        return _make_flag(
            reason_code="RUN_BOUNDARY_UNSUPPORTED",
            severity="HIGH",
            target_key=target_key,
            normalized_label=normalized_label,
            context={"parseError": str(e)},
        )
    runs = list(_iter_local(root, _HP_RUN_LOCAL))
    if not runs:
        return None
    text_runs: list[str] = []
    empty_runs = 0
    for r in runs:
        texts = [t.text or "" for t in _iter_local(r, _HP_TEXT_LOCAL)]
        joined = "".join(texts)
        if joined.strip():
            text_runs.append(joined)
        else:
            empty_runs += 1
    if len(text_runs) <= 1:
        return None
    severity = "HIGH" if len(text_runs) >= 3 else "MEDIUM"
    # v2 정밀화: 각 run의 길이 / 첫·끝 미리보기 / 비어있는 run 카운트
    run_lengths = [len(t) for t in text_runs]
    head_preview = text_runs[0][:8] if text_runs else ""
    tail_preview = text_runs[-1][:8] if text_runs else ""
    return _make_flag(
        reason_code="RUN_BOUNDARY_UNSUPPORTED",
        severity=severity,
        target_key=target_key,
        normalized_label=normalized_label,
        context={
            "runCount": len(runs),
            "textRunCount": len(text_runs),
            "emptyRunCount": empty_runs,
            "runLengths": run_lengths,
            "firstRunHead": head_preview,
            "lastRunHead": tail_preview,
        },
    )


# ── 2) CHECKBOX_OR_SHAPE_NEEDED ──────────────────────────────────────────────


def analyze_checkbox_or_shape(
    element_xml: str, *, target_key: str | None = None, normalized_label: str | None = None
) -> dict | None:
    """대상이 텍스트가 아니라 checkbox/도형(체크 표시 등) 입력을 요구하는지.

    detection rule:
      - element 내 checkbox 힌트가 있으면 HIGH (writer가 직접 못 씀)
      - shape류 자식이 있고 텍스트 입력 위치로 의심되면 MEDIUM
    """
    try:
        root = ET.fromstring(element_xml)
    except ET.ParseError:
        return None
    text_lower = element_xml.lower()
    if any(hint.lower() in text_lower for hint in _HP_CHECKBOX_HINTS):
        return _make_flag(
            reason_code="CHECKBOX_OR_SHAPE_NEEDED",
            severity="HIGH",
            target_key=target_key,
            normalized_label=normalized_label,
            context={"checkboxHint": True},
        )
    shape_nodes = [n for n in root.iter() if _local(n.tag) in _HP_SHAPE_LOCALS]
    if shape_nodes:
        return _make_flag(
            reason_code="CHECKBOX_OR_SHAPE_NEEDED",
            severity="MEDIUM",
            target_key=target_key,
            normalized_label=normalized_label,
            context={"shapeNodeCount": len(shape_nodes)},
        )
    return None


# ── 3) OBJECT_ANCHOR_NEEDED ──────────────────────────────────────────────────


def analyze_object_anchor(
    element_xml: str, *, target_key: str | None = None, normalized_label: str | None = None
) -> dict | None:
    """객체(이미지/도식/식)의 anchor 결정이 필요한 위치인지 진단."""
    try:
        root = ET.fromstring(element_xml)
    except ET.ParseError:
        return None
    objs = [n for n in root.iter() if _local(n.tag) in _HP_OBJECT_LOCALS]
    if not objs:
        return None
    severity = "HIGH" if len(objs) >= 2 else "MEDIUM"
    return _make_flag(
        reason_code="OBJECT_ANCHOR_NEEDED",
        severity=severity,
        target_key=target_key,
        normalized_label=normalized_label,
        context={
            "objectNodeCount": len(objs),
            "objectKinds": sorted({_local(n.tag) for n in objs}),
        },
    )


# ── 4) STYLE_RESOLUTION_NEEDED ───────────────────────────────────────────────


def analyze_style_resolution(
    paragraph_xml: str, *, target_key: str | None = None, normalized_label: str | None = None
) -> dict | None:
    """run별 charPr/parPr 스타일 ID가 충돌(여러 종류)할 때 진단.

    writer가 텍스트를 쓰면 어느 스타일을 따를지 모호하므로 진단 필요.
    """
    try:
        root = ET.fromstring(paragraph_xml)
    except ET.ParseError:
        return None
    char_ids: set[str] = set()
    par_ids: set[str] = set()
    lang_ids: set[str] = set()
    for r in _iter_local(root, _HP_RUN_LOCAL):
        cid = r.attrib.get("charPrIDRef") or r.attrib.get("charPr")
        if cid:
            char_ids.add(cid)
        lid = r.attrib.get("langId") or r.attrib.get("lang")
        if lid:
            lang_ids.add(lid)
    # paragraph-level style IDs
    for p in _iter_local(root, _HP_PARA_LOCAL):
        pid = p.attrib.get("parPrIDRef") or p.attrib.get("parPr")
        if pid:
            par_ids.add(pid)
    # 어느 한 차원이라도 2개 이상이면 충돌
    if len(char_ids) <= 1 and len(par_ids) <= 1 and len(lang_ids) <= 1:
        return None
    distinct_total = max(len(char_ids), len(par_ids), len(lang_ids))
    severity = "HIGH" if distinct_total >= 3 else "MEDIUM"
    return _make_flag(
        reason_code="STYLE_RESOLUTION_NEEDED",
        severity=severity,
        target_key=target_key,
        normalized_label=normalized_label,
        context={
            "distinctCharPrIds": sorted(char_ids),
            "distinctParPrIds": sorted(par_ids),
            "distinctLangIds": sorted(lang_ids),
        },
    )


# ── 5) CELL_INTERNAL_PARAGRAPH_NEEDED ────────────────────────────────────────


def analyze_cell_internal_paragraph(
    cell_xml: str, *, target_key: str | None = None, normalized_label: str | None = None
) -> dict | None:
    """셀 안에 paragraph가 0개거나 2개 이상이면 단순 setCellText로 못 쓴다.

    detection rule:
      - paragraph 0개 → writer가 빈 셀에 paragraph를 만들어야 함 (HIGH)
      - paragraph >= 2개 → 어느 paragraph에 쓸지 모호 (MEDIUM)
    """
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return None
    paras = list(_iter_local(root, _HP_PARA_LOCAL))
    n = len(paras)
    if n == 1:
        return None
    # v2 정밀화: 빈 paragraph vs 내용 paragraph 분류
    empty_paras = 0
    content_paras = 0
    for p in paras:
        joined = "".join((t.text or "") for t in _iter_local(p, _HP_TEXT_LOCAL))
        if joined.strip():
            content_paras += 1
        else:
            empty_paras += 1
    severity = "HIGH" if n == 0 else "MEDIUM"
    return _make_flag(
        reason_code="CELL_INTERNAL_PARAGRAPH_NEEDED",
        severity=severity,
        target_key=target_key,
        normalized_label=normalized_label,
        context={
            "paragraphCount": n,
            "emptyParagraphCount": empty_paras,
            "contentParagraphCount": content_paras,
        },
    )


# ── 6) MERGED_CELL_GEOMETRY_NEEDED ───────────────────────────────────────────


def _merge_span_int(v: str | None) -> int:
    try:
        return int(v) if v is not None else 1
    except ValueError:
        return 1


def _scan_merged_cells(cells: list) -> dict:
    findings: dict = {}
    horizontal_merges = 0
    vertical_merges = 0
    bidirectional = 0
    hidden_cells = 0
    for c in cells:
        row_span = _merge_span_int(c.attrib.get("rowSpan") or c.attrib.get("rowAddr"))
        col_span = _merge_span_int(c.attrib.get("colSpan") or c.attrib.get("colAddr"))
        hidden = c.attrib.get("hidden") in ("1", "true", "True")
        if row_span > 1 or col_span > 1 or hidden:
            findings.setdefault("mergedCells", []).append({
                "rowSpan": row_span,
                "colSpan": col_span,
                "hidden": hidden,
            })
            if hidden:
                hidden_cells += 1
            if row_span > 1 and col_span > 1:
                bidirectional += 1
            elif row_span > 1:
                vertical_merges += 1
            elif col_span > 1:
                horizontal_merges += 1
    if findings:
        # v2 정밀화: 병합 방향별 카운트
        findings["horizontalMergeCount"] = horizontal_merges
        findings["verticalMergeCount"] = vertical_merges
        findings["bidirectionalMergeCount"] = bidirectional
        findings["hiddenCellCount"] = hidden_cells
    return findings


def analyze_merged_cell_geometry(
    cell_xml: str, *, target_key: str | None = None, normalized_label: str | None = None
) -> dict | None:
    """병합 셀(rowSpan/colSpan > 1) 또는 hidden cell 진단."""
    try:
        root = ET.fromstring(cell_xml)
    except ET.ParseError:
        return None

    cells = list(_iter_local(root, _HP_CELL_LOCAL))
    if not cells and _local(root.tag) == _HP_CELL_LOCAL:
        cells = [root]
    if not cells:
        return None
    findings = _scan_merged_cells(cells)
    if not findings:
        return None
    severity = "HIGH" if len(findings["mergedCells"]) >= 2 else "MEDIUM"
    return _make_flag(
        reason_code="MERGED_CELL_GEOMETRY_NEEDED",
        severity=severity,
        target_key=target_key,
        normalized_label=normalized_label,
        context=findings,
    )


# ── 7) READBACK_MISMATCH ─────────────────────────────────────────────────────


def analyze_readback_mismatch(
    *,
    expected_hash: str | None,
    actual_hash: str | None,
    divergence_code: str | None = None,
    target_key: str | None = None,
    normalized_label: str | None = None,
) -> dict | None:
    """writer 적용 후 readback hash 비교 — 불일치 시 진단."""
    if expected_hash is None or actual_hash is None:
        return None
    if expected_hash == actual_hash:
        return None
    return _make_flag(
        reason_code="READBACK_MISMATCH",
        severity="HIGH",
        target_key=target_key,
        normalized_label=normalized_label,
        context={
            "expectedHash": expected_hash,
            "actualHash": actual_hash,
            "divergenceCode": divergence_code or "TEXT_MISMATCH",
        },
    )


# ── 8) TARGET_AMBIGUOUS ──────────────────────────────────────────────────────


def analyze_target_ambiguous(
    *, candidate_targets: list[str], normalized_label: str | None = None
) -> dict | None:
    """라벨 1개에 대해 후보 target_key가 2개 이상이면 모호."""
    if not candidate_targets:
        return None
    uniq = sorted(set(candidate_targets))
    if len(uniq) <= 1:
        return None
    severity = "HIGH" if len(uniq) >= 3 else "MEDIUM"
    # v2 정밀화: 후보 간 자카드 유사도 (key 토큰 기준)
    similarity_max = _max_pairwise_jaccard(uniq)
    return _make_flag(
        reason_code="TARGET_AMBIGUOUS",
        severity=severity,
        target_key=None,
        normalized_label=normalized_label,
        context={
            "candidateTargets": uniq,
            "candidateCount": len(uniq),
            "maxPairwiseSimilarity": similarity_max,
        },
    )


def _tokenize_target_key(k: str) -> set[str]:
    return {t for t in re.split(r"[:/_\-\.]+", k or "") if t}


def _max_pairwise_jaccard(keys: list[str]) -> float:
    """key 리스트의 페어별 자카드 유사도 중 최대값."""
    best = 0.0
    for i in range(len(keys)):
        ti = _tokenize_target_key(keys[i])
        for j in range(i + 1, len(keys)):
            tj = _tokenize_target_key(keys[j])
            if not ti and not tj:
                continue
            inter = len(ti & tj)
            union = len(ti | tj) or 1
            j_score = inter / union
            best = max(best, j_score)
    return round(best, 4)


# ── 9) LABEL_CONTEXT_INSUFFICIENT ────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w가-힣]+", re.UNICODE)


def analyze_label_context_sufficiency(
    *,
    normalized_label: str | None,
    neighbor_text: str | None,
    occurrence_count: int = 0,
    document_count: int = 0,
) -> dict | None:
    """라벨 자체의 의미 식별 가능성 진단.

    rule:
      - label 길이 < 2 → HIGH
      - 라벨이 흔한 단어이면서 neighbor 컨텍스트가 없으면 MEDIUM
      - occurrence_count >= 100이지만 document_count < 5 → 동일 문서 반복 가능성
    """
    if not normalized_label:
        return _make_flag(
            reason_code="LABEL_CONTEXT_INSUFFICIENT",
            severity="HIGH",
            normalized_label=None,
            context={"missingLabel": True},
        )
    stripped = _PUNCT_RE.sub("", normalized_label)
    if len(stripped) < 2:
        return _make_flag(
            reason_code="LABEL_CONTEXT_INSUFFICIENT",
            severity="HIGH",
            normalized_label=normalized_label,
            context={"shortLabelLen": len(stripped)},
        )
    if not (neighbor_text and neighbor_text.strip()):
        return _make_flag(
            reason_code="LABEL_CONTEXT_INSUFFICIENT",
            severity="MEDIUM",
            normalized_label=normalized_label,
            context={"missingNeighborText": True},
        )
    if occurrence_count >= 100 and document_count and document_count < 5:
        return _make_flag(
            reason_code="LABEL_CONTEXT_INSUFFICIENT",
            severity="LOW",
            normalized_label=normalized_label,
            context={
                "occurrenceCount": occurrence_count,
                "documentCount": document_count,
                "reason": "high_occurrence_low_document_spread",
            },
        )
    return None


# ── 통합 진단 ────────────────────────────────────────────────────────────────


def diagnose_session(
    *,
    paragraph_xml_list: list[dict] | None = None,
    cell_xml_list: list[dict] | None = None,
    element_xml_list: list[dict] | None = None,
    readback_checks: list[dict] | None = None,
    label_checks: list[dict] | None = None,
    ambiguity_checks: list[dict] | None = None,
) -> list[dict]:
    """하나의 fill_review 세션에서 발생할 수 있는 모든 진단을 한꺼번에 수행.

    각 입력 항목은 dict: {"xml": "...", "target_key": "tk",
                              "normalized_label": "라벨"} 형태.
    return: flag dict 리스트.
    """
    flags: list[dict] = []
    for item in paragraph_xml_list or []:
        for fn in (analyze_run_boundary, analyze_style_resolution):
            f = fn(
                item["xml"],
                target_key=item.get("target_key"),
                normalized_label=item.get("normalized_label"),
            )
            if f:
                flags.append(f)
    for item in cell_xml_list or []:
        for fn in (analyze_cell_internal_paragraph, analyze_merged_cell_geometry):
            f = fn(
                item["xml"],
                target_key=item.get("target_key"),
                normalized_label=item.get("normalized_label"),
            )
            if f:
                flags.append(f)
    for item in element_xml_list or []:
        for fn in (analyze_checkbox_or_shape, analyze_object_anchor):
            f = fn(
                item["xml"],
                target_key=item.get("target_key"),
                normalized_label=item.get("normalized_label"),
            )
            if f:
                flags.append(f)
    for item in readback_checks or []:
        f = analyze_readback_mismatch(
            expected_hash=item.get("expected_hash"),
            actual_hash=item.get("actual_hash"),
            divergence_code=item.get("divergence_code"),
            target_key=item.get("target_key"),
            normalized_label=item.get("normalized_label"),
        )
        if f:
            flags.append(f)
    for item in ambiguity_checks or []:
        f = analyze_target_ambiguous(
            candidate_targets=item.get("candidate_targets") or [],
            normalized_label=item.get("normalized_label"),
        )
        if f:
            flags.append(f)
    for item in label_checks or []:
        f = analyze_label_context_sufficiency(
            normalized_label=item.get("normalized_label"),
            neighbor_text=item.get("neighbor_text"),
            occurrence_count=int(item.get("occurrence_count") or 0),
            document_count=int(item.get("document_count") or 0),
        )
        if f:
            flags.append(f)
    return flags


def to_backlog_records(
    flags: list[dict], *, session_id: str | None, document_id: str, created_at: str
) -> list[dict]:
    """diagnose_session()이 만든 flag dict들을 D동
    xml_deep_analyzer_need_flags 행 dict로 변환."""
    out: list[dict] = []
    for f in flags:
        out.append({
            "session_id": session_id,
            "document_id": document_id,
            "reason_code": f["reason_code"],
            "target_key": f.get("target_key"),
            "normalized_label": f.get("normalized_label"),
            "context_json": None,  # 호출자가 json.dumps할지 정함
            "severity": f["severity"],
            "created_at": created_at,
            "_context": f.get("context") or {},
        })
    return out


# ── 방화구획 검증 ────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCTION_PATHS_FOR_ANALYZER: tuple[Path, ...] = (
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_contract.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_ui_adapter.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/fill_review_live_pipeline.py",
    PROJECT_ROOT / "scripts/hwpx/fill_review/evidence_ingestion_contract.py",
)
FORBIDDEN_ANALYZER_IMPORTS: tuple[str, ...] = (
    "xml_deep_structure_analyzer",
    "analyze_run_boundary",
    "diagnose_session",
)


def audit_analyzer_isolation() -> dict:
    """production 모듈이 analyzer를 import하지 않는지 grep 검증."""
    violations: list[dict] = []
    checked: list[str] = []
    for path in PRODUCTION_PATHS_FOR_ANALYZER:
        if not path.is_file():
            continue
        checked.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in FORBIDDEN_ANALYZER_IMPORTS:
            if needle in text:
                violations.append({
                    "file": str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
                    "forbidden": needle,
                })
    return {"violations": violations, "ok": not violations, "filesChecked": checked}


def list_required_analyzers() -> tuple[str, ...]:
    return REQUIRED_ANALYZER_NAMES
