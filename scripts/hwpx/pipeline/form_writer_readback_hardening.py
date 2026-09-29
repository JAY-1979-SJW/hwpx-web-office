"""
HWPX-FORM-AUTO-FILL-WRITER-READBACK-HARDENING-02

form_writer_readback_hardening.py — sandbox writer 결과 readback 정밀 검증.

입력:  source HWPX path  +  output HWPX path
       approved_fields list  +  SandboxWriteResult.to_dict()
출력:  ReadbackHardeningResult

검증 항목:
    - 필드별: PASS / WARN_NORMALIZED / FAIL_MISMATCH / FAIL_EMPTY / FAIL_TRUNCATED /
              FAIL_MISSING_TARGET / FAIL_DUPLICATE_TARGET / FAIL_OUTPUT_XML_BROKEN
    - 구조: ZIP valid / section XML valid / table·cell count / 비대상 셀 mutation / style 변경

절대 금지:
    - 원본 HWPX 수정 금지
    - AI API / OCR 호출 금지
    - raw value / PII 원문 report 저장 금지
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
ET.register_namespace("hp", NS_HP)

SCHEMA_VERSION = "form_writer_readback_hardening_v1"

# ── 필드별 readback 상태 ──────────────────────────────────────────────────────
READBACK_PASS = "READBACK_PASS"
READBACK_WARN_NORMALIZED_MATCH = "READBACK_WARN_NORMALIZED_MATCH"
READBACK_FAIL_MISSING_TARGET = "READBACK_FAIL_MISSING_TARGET"
READBACK_FAIL_VALUE_MISMATCH = "READBACK_FAIL_VALUE_MISMATCH"
READBACK_FAIL_EMPTY_VALUE = "READBACK_FAIL_EMPTY_VALUE"
READBACK_FAIL_TRUNCATED_VALUE = "READBACK_FAIL_TRUNCATED_VALUE"
READBACK_FAIL_DUPLICATE_TARGET = "READBACK_FAIL_DUPLICATE_TARGET"
READBACK_FAIL_UNEXPECTED_MUTATION = "READBACK_FAIL_UNEXPECTED_TARGET_MUTATION"
READBACK_FAIL_OUTPUT_XML_BROKEN = "READBACK_FAIL_OUTPUT_XML_BROKEN"

# ── 전체 verdict ──────────────────────────────────────────────────────────────
VERDICT_PASS = "PASS_READBACK_HARDENED"
VERDICT_WARN_NORMALIZED = "WARN_READBACK_NORMALIZED_MATCH_ONLY"
VERDICT_WARN_BLOCKED = "WARN_SOME_FIELDS_BLOCKED"
VERDICT_FAIL_MISMATCH = "FAIL_READBACK_MISMATCH"
VERDICT_FAIL_BROKEN = "FAIL_OUTPUT_HWPX_BROKEN"
VERDICT_FAIL_MUTATED = "FAIL_SOURCE_MUTATED"
VERDICT_FAIL_XML_MUTATION = "FAIL_UNEXPECTED_XML_MUTATION"

_SECTION_RE = re.compile(r"Contents/section\d+\.xml", re.IGNORECASE)


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _val_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _cell_text(cell: ET.Element) -> str:
    return "".join(t.text or "" for t in cell.iter(f"{{{NS_HP}}}t")).strip()


def _load_sections(hwpx_path: Path) -> dict[str, ET.Element | None]:
    """ZIP에서 section XML 파싱. 실패 시 None."""
    result: dict[str, ET.Element | None] = {}
    try:
        with zipfile.ZipFile(hwpx_path) as z:
            for name in sorted(n for n in z.namelist() if _SECTION_RE.match(n)):
                try:
                    result[name] = ET.fromstring(z.read(name).decode("utf-8"))
                except Exception:  # ruff: ignore[blind-except] - 파싱 실패 필드별 None 기록, 호출부가 sectionXmlValid로 감지
                    result[name] = None
    except (zipfile.BadZipFile, OSError):
        pass
    return result


def _count_structure(sections: dict) -> dict[str, int]:
    """섹션 구조 요소 집계."""
    tbl = para = cell = charpr = 0
    for root in sections.values():
        if root is None:
            continue
        tbl += len(root.findall(f".//{{{NS_HP}}}tbl"))
        para += len(root.findall(f".//{{{NS_HP}}}p"))
        charpr += len(root.findall(f".//{{{NS_HP}}}charPr"))
        for t in root.findall(f".//{{{NS_HP}}}tbl"):
            for row in t.findall(f"{{{NS_HP}}}tr"):
                cell += len(row.findall(f"{{{NS_HP}}}tc"))
    return {"tableCount": tbl, "cellCount": cell, "paraCount": para, "charPrCount": charpr}


def _non_target_cell_texts(
    sections: dict,
    exclude: set[tuple],  # {(sec_name, table_idx, row_idx, col_idx)}
) -> dict[tuple, str]:
    texts = {}
    for sec_name, root in sections.items():
        if root is None:
            continue
        for ti, tbl in enumerate(root.findall(f".//{{{NS_HP}}}tbl")):
            for ri, row in enumerate(tbl.findall(f"{{{NS_HP}}}tr")):
                for ci, cell in enumerate(row.findall(f"{{{NS_HP}}}tc")):
                    k = (sec_name, ti, ri, ci)
                    if k not in exclude:
                        texts[k] = _cell_text(cell)
    return texts


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────


@dataclass
class StructureCheckResult:
    zipValid: bool = True
    sectionXmlValid: bool = True
    tableCountChanged: bool = False
    cellCountChanged: bool = False
    paraCountChanged: bool = False
    unexpectedCellMutationCount: int = 0
    styleMutationDetected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "zipValid": self.zipValid,
            "sectionXmlValid": self.sectionXmlValid,
            "tableCountChanged": self.tableCountChanged,
            "cellCountChanged": self.cellCountChanged,
            "paraCountChanged": self.paraCountChanged,
            "unexpectedCellMutationCount": self.unexpectedCellMutationCount,
            "styleMutationDetected": self.styleMutationDetected,
        }


@dataclass
class ReadbackHardeningResult:
    schemaVersion: str = SCHEMA_VERSION
    sourceTemplateHash: str = ""
    outputHash: str = ""
    sourceMutated: bool = False
    overallVerdict: str = VERDICT_PASS
    fieldResults: list[dict] = field(default_factory=list)
    structureCheck: StructureCheckResult = field(default_factory=StructureCheckResult)
    warnings: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, Any]:
        exact = sum(1 for f in self.fieldResults if f.get("readbackStatus") == READBACK_PASS)
        norm = sum(
            1
            for f in self.fieldResults
            if f.get("readbackStatus") == READBACK_WARN_NORMALIZED_MATCH
        )
        fails = sum(
            1 for f in self.fieldResults if f.get("readbackStatus", "").startswith("READBACK_FAIL")
        )
        return {
            "writtenFields": len(self.fieldResults),
            "readbackPass": exact,
            "normalizedMatch": norm,
            "readbackFail": fails,
            "unexpectedMutation": self.structureCheck.unexpectedCellMutationCount,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "sourceTemplateHash": self.sourceTemplateHash,
            "outputHash": self.outputHash,
            "sourceMutated": self.sourceMutated,
            "overallVerdict": self.overallVerdict,
            "summary": self.summary,
            "fieldResults": self.fieldResults,
            "structureCheck": self.structureCheck.to_dict(),
            "warnings": self.warnings,
        }


# ── 필드별 readback 상태 결정 ─────────────────────────────────────────────────


def _field_readback_status(actual: str, expected: str) -> str:
    if not actual and expected:
        return READBACK_FAIL_EMPTY_VALUE
    if actual == expected:
        return READBACK_PASS
    if actual.strip() == expected.strip():
        return READBACK_WARN_NORMALIZED_MATCH
    if (
        expected
        and len(actual) < len(expected)
        and expected.startswith(actual)
        and len(actual) >= 1
    ):
        return READBACK_FAIL_TRUNCATED_VALUE
    return READBACK_FAIL_VALUE_MISMATCH


# ── 메인 검증 함수 ────────────────────────────────────────────────────────────


def _detect_duplicate_target_fields(written_fields: list[dict]) -> tuple[set[tuple], set[str]]:
    """table_cell 타겟 위치가 겹치는 필드들을 찾는다. (target_locs, dup_keys) 반환."""
    seen_locs: dict[tuple, str] = {}
    dup_keys: set[str] = set()
    for wf in written_fields:
        loc = wf.get("targetLocation", {})
        if loc.get("type") == "table_cell":
            k = (
                loc.get("sectionName", ""),
                loc.get("tableIndex", -1),
                loc.get("row", -1),
                loc.get("col", -1),
            )
            if k in seen_locs:
                dup_keys.add(wf["fieldKey"])
                dup_keys.add(seen_locs[k])
            else:
                seen_locs[k] = wf["fieldKey"]
    return set(seen_locs.keys()), dup_keys


def _broken_output_field_results(written_fields: list[dict]) -> list[dict]:
    return [
        {
            "fieldKey": wf["fieldKey"],
            "targetLocation": wf.get("targetLocation", {}),
            "expectedValueHash": wf.get("valueHash", ""),
            "actualValueHash": "",
            "readbackStatus": READBACK_FAIL_OUTPUT_XML_BROKEN,
            "valueStoredInReport": False,
        }
        for wf in written_fields
    ]


def _check_structure_and_mutations(
    sc: StructureCheckResult,
    out_sections: dict,
    src_sections: dict,
    target_locs: set[tuple],
) -> list[str]:
    """sc를 채우고(in-place), 추가할 경고 문자열 목록을 반환한다."""
    warnings: list[str] = []
    sc.sectionXmlValid = all(v is not None for v in out_sections.values())
    if not sc.sectionXmlValid:
        warnings.append("FAIL_OUTPUT_HWPX_BROKEN")

    src_struct = _count_structure(src_sections)
    out_struct = _count_structure(out_sections)
    sc.tableCountChanged = src_struct["tableCount"] != out_struct["tableCount"]
    sc.cellCountChanged = src_struct["cellCount"] != out_struct["cellCount"]
    sc.paraCountChanged = src_struct["paraCount"] != out_struct["paraCount"]
    sc.styleMutationDetected = src_struct["charPrCount"] != out_struct["charPrCount"]

    if sc.tableCountChanged or sc.cellCountChanged:
        warnings.append("FAIL_UNEXPECTED_XML_MUTATION: table/cell count changed")

    src_cells = _non_target_cell_texts(src_sections, target_locs)
    out_cells = _non_target_cell_texts(out_sections, target_locs)
    mutations = sum(1 for k, v in src_cells.items() if out_cells.get(k, v) != v)
    sc.unexpectedCellMutationCount = mutations
    if mutations > 0:
        warnings.append(f"FAIL_UNEXPECTED_XML_MUTATION: {mutations} non-target cells changed")

    return warnings


def _verify_one_field(wf: dict, dup_keys: set[str], af_by_key: dict, out_sections: dict) -> dict:
    fk = wf["fieldKey"]
    loc = wf.get("targetLocation", {})
    expected_hash = wf.get("valueHash", "")
    base = {"fieldKey": fk, "targetLocation": loc, "expectedValueHash": expected_hash}

    if fk in dup_keys:
        return {
            **base,
            "actualValueHash": "",
            "readbackStatus": READBACK_FAIL_DUPLICATE_TARGET,
            "valueStoredInReport": False,
        }

    if loc.get("type") != "table_cell":
        return {
            **base,
            "actualValueHash": "",
            "readbackStatus": READBACK_FAIL_MISSING_TARGET,
            "valueStoredInReport": False,
        }

    sec_name = loc.get("sectionName", "")
    ti = loc.get("tableIndex", -1)
    ri = loc.get("row", -1)
    ci = loc.get("col", -1)

    root = out_sections.get(sec_name)
    if root is None:
        return {
            **base,
            "actualValueHash": "",
            "readbackStatus": READBACK_FAIL_MISSING_TARGET,
            "valueStoredInReport": False,
        }

    try:
        tables = root.findall(f".//{{{NS_HP}}}tbl")
        rows = tables[ti].findall(f"{{{NS_HP}}}tr")
        cells = rows[ri].findall(f"{{{NS_HP}}}tc")
        actual = _cell_text(cells[ci])
    except (IndexError, AttributeError):
        return {
            **base,
            "actualValueHash": "",
            "readbackStatus": READBACK_FAIL_MISSING_TARGET,
            "valueStoredInReport": False,
        }

    af = af_by_key.get(fk)
    expected_value = af.value if af else ""
    actual_hash = _val_hash(actual)
    status = _field_readback_status(actual, expected_value)

    return {
        **base,
        "actualValueHash": actual_hash,
        "readbackStatus": status,
        "valueStoredInReport": False,
    }


def _determine_overall_verdict(field_results: list[dict], sc: StructureCheckResult) -> str:
    statuses = [f.get("readbackStatus", "") for f in field_results]
    has_fail = any(s.startswith("READBACK_FAIL") for s in statuses)
    has_norm = any(s == READBACK_WARN_NORMALIZED_MATCH for s in statuses)
    xml_broken = not sc.zipValid or not sc.sectionXmlValid
    xml_mutated = sc.tableCountChanged or sc.cellCountChanged or sc.unexpectedCellMutationCount > 0

    if xml_broken:
        return VERDICT_FAIL_BROKEN
    if xml_mutated:
        return VERDICT_FAIL_XML_MUTATION
    if has_fail:
        return VERDICT_FAIL_MISMATCH
    if has_norm:
        return VERDICT_WARN_NORMALIZED
    return VERDICT_PASS


def verify_readback(
    source_path: Path,
    output_path: Path,
    approved_fields: list,  # ApprovedField (fieldKey, value 접근)
    writer_result_dict: dict,  # SandboxWriteResult.to_dict()
) -> ReadbackHardeningResult:
    """
    Sandbox writer output HWPX에 대한 정밀 readback 검증.

    Args:
        source_path:        원본 HWPX 템플릿
        output_path:        sandbox 출력 HWPX
        approved_fields:    approval gate ApprovedField 목록
        writer_result_dict: SandboxWriteResult.to_dict() 결과

    Returns:
        ReadbackHardeningResult
    """
    source_path = Path(source_path)
    output_path = Path(output_path)
    result = ReadbackHardeningResult()

    # 원본 해시 기록
    result.sourceTemplateHash = _sha256(source_path) if source_path.exists() else ""
    result.outputHash = _sha256(output_path) if output_path.exists() else ""

    af_by_key = {af.fieldKey: af for af in approved_fields}
    written_fields = writer_result_dict.get("writtenFields", [])

    target_locs, dup_keys = _detect_duplicate_target_fields(written_fields)

    # ── ZIP / XML 유효성 ─────────────────────────────────────────────────────
    zip_valid = output_path.exists() and zipfile.is_zipfile(output_path)
    sc = StructureCheckResult(zipValid=zip_valid)

    if not zip_valid:
        result.overallVerdict = VERDICT_FAIL_BROKEN
        result.warnings.append("FAIL_OUTPUT_HWPX_BROKEN")
        result.fieldResults = _broken_output_field_results(written_fields)
        result.structureCheck = sc
        return result

    out_sections = _load_sections(output_path)
    src_sections = _load_sections(source_path) if source_path.exists() else {}
    result.warnings.extend(
        _check_structure_and_mutations(sc, out_sections, src_sections, target_locs)
    )
    result.structureCheck = sc

    # ── 필드별 readback ───────────────────────────────────────────────────────
    for wf in written_fields:
        result.fieldResults.append(_verify_one_field(wf, dup_keys, af_by_key, out_sections))

    result.overallVerdict = _determine_overall_verdict(result.fieldResults, sc)
    result.warnings.append("WARN_SANDBOX_ONLY")
    return result


# ── 편의 함수 ─────────────────────────────────────────────────────────────────


def run_hardening(
    approval_result,
    template_path: Path,
    output_dir: Path,
) -> ReadbackHardeningResult:
    """
    sandbox write + readback hardening 일괄 실행.

    Args:
        approval_result: ApprovalResult
        template_path:   HWPX 템플릿
        output_dir:      sandbox 출력 디렉터리
    """
    from hwpx.pipeline.form_auto_fill_writer_sandbox import run_sandbox_write

    writer_result = run_sandbox_write(approval_result, template_path, output_dir)
    output_path = Path(output_dir) / "output" / f"sandbox_{Path(template_path).stem}.hwpx"

    return verify_readback(
        source_path=Path(template_path),
        output_path=output_path,
        approved_fields=approval_result.approvedFields,
        writer_result_dict=writer_result.to_dict(),
    )
