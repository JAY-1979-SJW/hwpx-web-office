"""
HWPX-FORM-AUTO-FILL-WRITER-SANDBOX-01

form_auto_fill_writer_sandbox.py — sandbox HWPX 복사본에만 자동입력.

입력:  ApprovalResult (approval_gate.py)  +  HWPX template path
출력:  SandboxWriteResult  — written / blocked / readback 결과 report

절대 금지:
    - 원본 HWPX 직접 수정 (output_path == source_path 거부)
    - writerEligible=false 필드 입력
    - HOLD / REQUEST_ATTACHMENT 필드 입력
    - AI API / OCR 호출
    - PII 원문 report 저장
    - raw path / raw filename report 저장
    - readback 검증 없이 PASS 처리
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

SCHEMA_VERSION = "form_auto_fill_writer_sandbox_v1"
TARGET_CONF_MIN = 0.80

# ── 차단 사유 상수 ────────────────────────────────────────────────────────────
BLOCKED_NOT_APPROVED = "BLOCKED_NOT_APPROVED"
BLOCKED_HOLD = "BLOCKED_HOLD"
BLOCKED_ATTACHMENT_REQUIRED = "BLOCKED_ATTACHMENT_REQUIRED"
BLOCKED_MISSING_REQUIRED = "BLOCKED_MISSING_REQUIRED"
BLOCKED_NO_VALUE = "BLOCKED_NO_VALUE"
BLOCKED_NO_TARGET_LOCATION = "BLOCKED_NO_TARGET_LOCATION"
BLOCKED_AMBIGUOUS_TARGET = "BLOCKED_AMBIGUOUS_TARGET"
BLOCKED_LOW_TARGET_CONFIDENCE = "BLOCKED_LOW_TARGET_CONFIDENCE"

_STATUS_WRITTEN = "WRITTEN"
_STATUS_DRY_RUN = "DRY_RUN"
_RB_PASS = "PASS"
_RB_FAIL = "FAIL"
_RB_SKIP = "SKIPPED"

_SECTION_RE = re.compile(r"Contents/section\d+\.xml", re.IGNORECASE)
_PII_RE = re.compile(r"\d{6}-\d{7}|\d{3}-\d{2}-\d{5}")


# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _val_hash(value: str) -> str:
    """값 hash (16자) — PII 대신 저장."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _norm(s: str) -> str:
    return s.strip().lower().replace(" ", "").replace(" ", "")


def _cell_text(cell: ET.Element) -> str:
    return "".join(t.text or "" for t in cell.iter(f"{{{NS_HP}}}t")).strip()


def _set_cell_text(cell: ET.Element, value: str) -> None:
    """셀 텍스트 교체. 기존 구조 최대한 보존."""
    t_elems = list(cell.iter(f"{{{NS_HP}}}t"))
    if t_elems:
        t_elems[0].text = value
        for t in t_elems[1:]:
            t.text = ""
    else:
        p = cell.find(f".//{{{NS_HP}}}p")
        if p is None:
            p = ET.SubElement(cell, f"{{{NS_HP}}}p")
        run = ET.SubElement(p, f"{{{NS_HP}}}run")
        t = ET.SubElement(run, f"{{{NS_HP}}}t")
        t.text = value


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────


@dataclass
class WriteTarget:
    section_name: str
    table_idx: int
    row_idx: int
    col_idx: int  # value 셀 (label 셀 오른쪽)
    label_text: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "table_cell",
            "sectionName": self.section_name,
            "tableIndex": self.table_idx,
            "row": self.row_idx,
            "col": self.col_idx,
        }


@dataclass
class SandboxWriteResult:
    schemaVersion: str = SCHEMA_VERSION
    sourceTemplateHash: str = ""
    outputHash: str = ""
    sourceMutated: bool = False
    outputPathMasked: str = ""
    writtenFields: list = field(default_factory=list)
    blockedFields: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def summary(self) -> dict[str, Any]:
        rb_pass = sum(1 for f in self.writtenFields if f.get("readbackStatus") == _RB_PASS)
        rb_fail = sum(1 for f in self.writtenFields if f.get("readbackStatus") == _RB_FAIL)
        return {
            "approvedFields": len(self.writtenFields) + len(self.blockedFields),
            "written": len(self.writtenFields),
            "blocked": len(self.blockedFields),
            "readbackPass": rb_pass,
            "readbackFail": rb_fail,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schemaVersion,
            "sourceTemplateHash": self.sourceTemplateHash,
            "outputHash": self.outputHash,
            "sourceMutated": self.sourceMutated,
            "outputPathMasked": self.outputPathMasked,
            "summary": self.summary,
            "writtenFields": self.writtenFields,
            "blockedFields": self.blockedFields,
            "warnings": self.warnings,
        }


# ── 타겟 위치 탐색 ────────────────────────────────────────────────────────────


def _label_match_confidence(txt: str, af, clf) -> float:
    if _norm(txt) == _norm(af.label):
        return 0.95
    if clf.semanticField and clf.semanticField == af.fieldKey:
        return 0.90
    if len(_norm(af.label)) >= 2 and (
        _norm(af.label) in _norm(txt) or _norm(txt) in _norm(af.label)
    ):
        return 0.70  # 부분 일치 (TARGET_CONF_MIN 미만)
    return 0.0


def _resolve_targets(template_path: Path, approved_fields: list) -> dict:
    """
    HWPX template에서 각 approved_field의 쓰기 위치를 탐색.

    Returns:
        dict[fieldKey, WriteTarget | (blocked_reason, detail)]
    """
    from hwpx.recognition_corpus.label_taxonomy import classify_label

    candidates: dict[str, list[WriteTarget]] = {}

    try:
        with zipfile.ZipFile(template_path) as z:
            sec_names = sorted(n for n in z.namelist() if _SECTION_RE.match(n))
            for sec_name in sec_names:
                try:
                    root = ET.fromstring(z.read(sec_name).decode("utf-8"))
                except (ET.ParseError, UnicodeDecodeError):
                    continue
                tables = root.findall(f".//{{{NS_HP}}}tbl")
                for ti, tbl in enumerate(tables):
                    for ri, row in enumerate(tbl.findall(f"{{{NS_HP}}}tr")):
                        cells = row.findall(f"{{{NS_HP}}}tc")
                        for ci in range(len(cells) - 1):
                            txt = _cell_text(cells[ci])
                            if not txt:
                                continue
                            clf = classify_label(txt)
                            for af in approved_fields:
                                conf = _label_match_confidence(txt, af, clf)
                                if conf > 0:
                                    candidates.setdefault(af.fieldKey, []).append(
                                        WriteTarget(sec_name, ti, ri, ci + 1, txt, conf)
                                    )
    except (zipfile.BadZipFile, OSError):
        pass

    return {
        af.fieldKey: _resolve_field_target(candidates.get(af.fieldKey, []))
        for af in approved_fields
    }


def _resolve_field_target(cands: list[WriteTarget]):
    if not cands:
        return (BLOCKED_NO_TARGET_LOCATION, "label not found in template")
    unique_locs = {(c.section_name, c.table_idx, c.row_idx, c.col_idx) for c in cands}
    if len(unique_locs) > 1:
        return (BLOCKED_AMBIGUOUS_TARGET, f"{len(unique_locs)} distinct locations")
    best = max(cands, key=lambda c: c.confidence)
    if best.confidence < TARGET_CONF_MIN:
        return (BLOCKED_LOW_TARGET_CONFIDENCE, f"conf={best.confidence:.2f} < {TARGET_CONF_MIN}")
    return best


# ── 쓰기 실행 ─────────────────────────────────────────────────────────────────


def _write_one_field(tables, mod: tuple, targets: dict) -> dict:
    ti, ri, ci, value, fk, lbl, action = mod
    try:
        rows = tables[ti].findall(f"{{{NS_HP}}}tr")
        cells = rows[ri].findall(f"{{{NS_HP}}}tc")
        _set_cell_text(cells[ci], value)
        return {
            "fieldKey": fk,
            "label": lbl,
            "decisionAction": action,
            "writeStatus": _STATUS_WRITTEN,
            "readbackStatus": _RB_SKIP,
            "targetLocation": targets[fk].to_dict(),
            "valueHash": _val_hash(value),
        }
    except (IndexError, AttributeError):
        return {
            "fieldKey": fk,
            "label": lbl,
            "decisionAction": action,
            "writeStatus": BLOCKED_NO_TARGET_LOCATION,
            "readbackStatus": _RB_SKIP,
            "targetLocation": {},
            "valueHash": "",
        }


def _do_write(
    source_path: Path,
    output_path: Path,
    targets: dict,
    writable_fields: list,
) -> list[dict]:
    """원본 → output 복사 후 writable_fields 입력. write_results 반환."""
    if source_path.resolve() == output_path.resolve():
        raise ValueError("output_path must differ from source_path")

    # 원본 전체 읽기
    file_bytes: dict[str, bytes] = {}
    with zipfile.ZipFile(source_path) as z:
        for name in z.namelist():
            file_bytes[name] = z.read(name)

    # 섹션별 수정 큐 구성
    write_queue: dict[str, list] = {}
    for af in writable_fields:
        target = targets.get(af.fieldKey)
        if isinstance(target, WriteTarget):
            write_queue.setdefault(target.section_name, []).append((
                target.table_idx,
                target.row_idx,
                target.col_idx,
                af.value,
                af.fieldKey,
                af.label,
                af.action,
            ))

    # XML 수정
    sec_roots: dict[str, ET.Element] = {}
    write_results: list[dict] = []

    for sec_name, mods in write_queue.items():
        if sec_name not in file_bytes:
            continue
        root = ET.fromstring(file_bytes[sec_name].decode("utf-8"))
        sec_roots[sec_name] = root
        tables = root.findall(f".//{{{NS_HP}}}tbl")

        write_results.extend(_write_one_field(tables, mod, targets) for mod in mods)

    # 수정된 섹션 재직렬화
    for sec_name, root in sec_roots.items():
        file_bytes[sec_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    # output ZIP 생성
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in file_bytes.items():
            z.writestr(name, content)

    return write_results


# ── readback 검증 ─────────────────────────────────────────────────────────────


def _verify_one_field(r: dict, targets: dict, sec_roots: dict, af_by_key: dict) -> None:
    fk = r["fieldKey"]
    target = targets.get(fk)
    if not isinstance(target, WriteTarget):
        r["readbackStatus"] = _RB_SKIP
        return

    root = sec_roots.get(target.section_name)
    if root is None:
        r["readbackStatus"] = _RB_FAIL
        return

    try:
        tables = root.findall(f".//{{{NS_HP}}}tbl")
        rows = tables[target.table_idx].findall(f"{{{NS_HP}}}tr")
        cells = rows[target.row_idx].findall(f"{{{NS_HP}}}tc")
        actual = _cell_text(cells[target.col_idx])
    except (IndexError, AttributeError):
        r["readbackStatus"] = _RB_FAIL
        return

    af = af_by_key.get(fk)
    r["readbackStatus"] = _RB_PASS if (af and actual == af.value) else _RB_FAIL


def _readback_verify(
    output_path: Path,
    targets: dict,
    approved_fields: list,
    write_results: list[dict],
) -> list[dict]:
    """output HWPX 재독 후 입력값 확인."""
    af_by_key = {af.fieldKey: af for af in approved_fields}

    try:
        with zipfile.ZipFile(output_path) as z:
            sec_roots: dict[str, ET.Element] = {}
            for name in z.namelist():
                if _SECTION_RE.match(name):
                    sec_roots[name] = ET.fromstring(z.read(name).decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError, UnicodeDecodeError, OSError):
        for r in write_results:
            if r.get("writeStatus") == _STATUS_WRITTEN:
                r["readbackStatus"] = _RB_FAIL
        return write_results

    for r in write_results:
        if r.get("writeStatus") != _STATUS_WRITTEN:
            continue
        _verify_one_field(r, targets, sec_roots, af_by_key)

    return write_results


# ── 메인 진입점 ───────────────────────────────────────────────────────────────


def _append_pre_write_blocked_fields(result, approval_result, action_hold) -> None:
    for af in approval_result.approvedFields:
        if not af.writerEligible:
            result.blockedFields.append({
                "fieldKey": af.fieldKey,
                "label": af.label,
                "blockedReason": BLOCKED_NOT_APPROVED,
                "decisionAction": af.action,
            })
        elif not af.value:
            result.blockedFields.append({
                "fieldKey": af.fieldKey,
                "label": af.label,
                "blockedReason": BLOCKED_NO_VALUE,
                "decisionAction": af.action,
            })
    for pf in approval_result.pendingFields:
        reason = BLOCKED_HOLD if pf.action == action_hold else BLOCKED_ATTACHMENT_REQUIRED
        result.blockedFields.append({
            "fieldKey": pf.fieldKey,
            "label": pf.label,
            "blockedReason": reason,
            "decisionAction": pf.action,
        })


def _split_writable_fields(approved: list, targets: dict, result) -> list:
    writable = []
    for af in approved:
        target = targets.get(af.fieldKey)
        if isinstance(target, WriteTarget):
            writable.append(af)
        else:
            reason, _detail = (
                target if isinstance(target, tuple) else (BLOCKED_NO_TARGET_LOCATION, "")
            )
            result.blockedFields.append({
                "fieldKey": af.fieldKey,
                "label": af.label,
                "blockedReason": reason,
                "decisionAction": af.action,
            })
    return writable


def run_sandbox_write(
    approval_result,
    template_path: Path,
    output_dir: Path,
    dry_run: bool = False,
) -> SandboxWriteResult:
    """
    ApprovalResult + HWPX template → sandbox copy에 자동입력.

    Args:
        approval_result: approval_gate.ApprovalResult
        template_path:   HWPX 템플릿 경로
        output_dir:      sandbox 출력 디렉터리
        dry_run:         True이면 output 파일 생성 없음

    Returns:
        SandboxWriteResult (sourceMutated 항상 검증됨)
    """
    from hwpx.pipeline.approval_gate import ACTION_ATTACHMENT, ACTION_HOLD

    template_path = Path(template_path)
    output_dir = Path(output_dir)
    result = SandboxWriteResult()

    src_hash = _sha256(template_path) if template_path.exists() else "file_not_found"
    result.sourceTemplateHash = src_hash

    # writerEligible=True && value 존재하는 필드만 대상
    approved = [
        af
        for af in approval_result.approvedFields
        if af.writerEligible and af.action not in (ACTION_HOLD, ACTION_ATTACHMENT) and af.value
    ]

    _append_pre_write_blocked_fields(result, approval_result, ACTION_HOLD)

    targets = _resolve_targets(template_path, approved)

    if dry_run:
        for af in approved:
            target = targets.get(af.fieldKey)
            if isinstance(target, WriteTarget):
                result.writtenFields.append({
                    "fieldKey": af.fieldKey,
                    "label": af.label,
                    "decisionAction": af.action,
                    "writeStatus": _STATUS_DRY_RUN,
                    "readbackStatus": _RB_SKIP,
                    "targetLocation": target.to_dict(),
                    "valueHash": _val_hash(af.value),
                })
            else:
                reason, detail = (
                    target if isinstance(target, tuple) else (BLOCKED_NO_TARGET_LOCATION, "")
                )
                result.blockedFields.append({
                    "fieldKey": af.fieldKey,
                    "label": af.label,
                    "blockedReason": reason,
                    "decisionAction": af.action,
                })
        result.warnings.append("WARN_DRY_RUN_NO_OUTPUT")
        result.warnings.append("WARN_SANDBOX_ONLY")
        return result

    # sandbox write
    output_path = output_dir / "output" / f"sandbox_{template_path.stem}.hwpx"

    if template_path.resolve() == output_path.resolve():
        result.warnings.append("FAIL_OUTPUT_EQUALS_SOURCE")
        return result

    # 타겟 있는 필드만 쓰기, 없는 필드는 차단
    writable = _split_writable_fields(approved, targets, result)

    write_results = _do_write(template_path, output_path, targets, writable)
    write_results = _readback_verify(output_path, targets, writable, write_results)

    # write_results 분리: WRITTEN → writtenFields, 나머지 → blockedFields
    for r in write_results:
        if r.get("writeStatus") == _STATUS_WRITTEN:
            result.writtenFields.append(r)
        else:
            result.blockedFields.append({
                "fieldKey": r["fieldKey"],
                "label": r["label"],
                "blockedReason": r["writeStatus"],
                "decisionAction": r["decisionAction"],
            })

    # 원본 불변 검증
    final_hash = _sha256(template_path)
    result.sourceMutated = final_hash != src_hash
    if result.sourceMutated:
        result.warnings.append("FAIL_SOURCE_HWPX_MUTATED")

    result.outputHash = _sha256(output_path) if output_path.exists() else ""
    result.outputPathMasked = (
        "sandbox_" + hashlib.sha256(template_path.stem.encode()).hexdigest()[:8] + ".hwpx"
    )

    rb_fails = sum(1 for f in result.writtenFields if f.get("readbackStatus") == _RB_FAIL)
    if rb_fails:
        result.warnings.append(f"FAIL_READBACK_MISMATCH: {rb_fails} fields")

    result.warnings.append("WARN_SANDBOX_ONLY")
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────


def _cli():
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="HWPX sandbox auto-fill writer")
    parser.add_argument("--approval-json", required=True)
    parser.add_argument("--template-hwpx", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sandbox-write", action="store_true")
    args = parser.parse_args()

    if not args.dry_run and not args.sandbox_write:
        parser.error("specify --dry-run or --sandbox-write")

    approval_data = json.loads(Path(args.approval_json).read_text("utf-8"))

    # approval_data → 간단한 namespace 객체로 복원
    from types import SimpleNamespace

    from hwpx.pipeline.approval_gate import ApprovedField, PendingField

    def _af(d):
        return ApprovedField(
            fieldKey=d["fieldKey"],
            label=d["label"],
            value=d["value"],
            originalValue=d.get("originalValue", ""),
            action=d["action"],
            sourceZone=d.get("sourceZone", ""),
            confidence=d.get("confidence", 0.0),
        )

    def _pf(d):
        return PendingField(
            fieldKey=d["fieldKey"],
            label=d["label"],
            action=d["action"],
            sourceZone=d.get("sourceZone", ""),
        )

    ar = SimpleNamespace(
        approvedFields=[_af(x) for x in approval_data.get("approvedFields", [])],
        pendingFields=[_pf(x) for x in approval_data.get("pendingFields", [])],
        writerEnabled=False,
    )

    result = run_sandbox_write(
        ar,
        Path(args.template_hwpx),
        Path(args.output_dir),
        dry_run=args.dry_run,
    )

    out_path = Path(args.output_dir) / "auto_fill_writer_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    _cli()
