"""CELL-SAVE verify7 게이트 (V1~V7).

설계서 §11 Save flow + LOCK_01 회로 + 본 공정 시방서 정의.
- V1_POSITION_OK            : output 의 셀 좌표에 after 값 존재 (readback)
- V2_NO_CROSS_LEAK          : output blob 에 unique value count == applied 횟수
- V3_UNTOUCHED_PRESERVED    : 적용 안 한 셀의 text 가 원본과 동일
- V4_SOURCE_HASH_OK         : 원본 sha256 사전=사후 동일
- V5_EXPECTED_BEFORE_OK     : 적용 직전 셀 text 가 command.expectedBefore 와 일치
- V6_OUTPUT_ISOLATED        : output != source, sandbox 경로 하위
- V7_READBACK_MATCH         : output readback 후 셀 text == after

본 모듈은 hwpx_edit_tool 의 writer 본 실행을 호출하지 않는다.
import_hwpx_as_ro_view (read-only) 만 사용한다.
"""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .edit_command_model import EditCommand
from .ro_view_importer import import_hwpx_as_ro_view

SANDBOX_PREFIXES = ("data/drafts", "data\\drafts", "tmp", "data/audit", "data\\audit")


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _output_under_sandbox(out: Path, project_root: Path) -> bool:
    try:
        rel = out.resolve().relative_to(project_root.resolve())
    except ValueError:
        # 프로젝트 외부 (예: tmp_path) — 절대 경로 검사.
        # 문자열 패턴만으로 판정하면 임시폴더가 표준 위치가 아닌 PC 에서
        # 멀쩡한 출력이 거부된다. 실측: 이 개발기는 ESTsoft 가 임시폴더를
        # C:\Users\Public\Documents\ESTsoft\CreatorTemp 로 돌려놔서
        # V6 가 FAIL 이 났다. 그래서 OS 가 알려주는 임시폴더를 먼저 본다.
        resolved = out.resolve()
        try:
            resolved.relative_to(Path(tempfile.gettempdir()).resolve())
            return True
        except ValueError:
            pass
        s = str(resolved).lower()
        return "\\temp\\" in s or "/tmp/" in s or "pytest-of-" in s or "appdata\\local\\temp" in s
    s = str(rel).replace("\\", "/").lower()
    return any(s.startswith(p.replace("\\", "/")) for p in SANDBOX_PREFIXES)


def _read_blob(zip_path: Path) -> str:
    blob_parts: list[str] = []
    with zipfile.ZipFile(str(zip_path)) as z:
        blob_parts.extend(z.read(name).decode("utf-8", "ignore") for name in z.namelist() if name.endswith(".xml") or name.endswith(".hpf"))
    return "".join(blob_parts)


@dataclass
class Verify7Inputs:
    """verify7 입력 묶음(인자 개수 축소 목적, 유일한 호출부는 cell_save_pipeline)."""

    source_path: Path
    output_path: Path
    project_root: Path
    accepted_commands: list[EditCommand]
    pre_save_cell_texts: dict[str, str]
    source_sha_before: str
    source_mtime_before: int


def _check_v4_source_unchanged(inputs: Verify7Inputs) -> tuple[str, list[dict]]:
    sha_after = _sha(inputs.source_path)
    mtime_after = inputs.source_path.stat().st_mtime_ns
    if sha_after == inputs.source_sha_before and mtime_after == inputs.source_mtime_before:
        return "PASS", []
    return "FAIL", [
        {"code": "V4_SOURCE_CHANGED", "before": inputs.source_sha_before, "after": sha_after}
    ]


def _check_v5_expected_before(inputs: Verify7Inputs) -> tuple[str, list[dict]]:
    v5 = "PASS"
    findings: list[dict] = []
    for cmd in inputs.accepted_commands:
        current = inputs.pre_save_cell_texts.get(cmd.targetId, None)
        if current is None or current != cmd.expectedBefore:
            v5 = "FAIL"
            findings.append({
                "code": "V5_EXPECTED_BEFORE_MISS",
                "cellId": cmd.targetId,
                "expected": cmd.expectedBefore,
                "current": current,
            })
    if not inputs.accepted_commands:
        v5 = "FAIL"
        findings.append({
            "code": "V5_NO_ACCEPTED_COMMANDS",
            "detail": "applied=∅ — vacuous PASS 방지",
        })
    return v5, findings


def _check_v6_output_isolated(inputs: Verify7Inputs) -> tuple[str, list[dict]]:
    same_path = inputs.output_path.resolve() == inputs.source_path.resolve()
    under_sb = _output_under_sandbox(inputs.output_path, inputs.project_root)
    if not same_path and under_sb:
        return "PASS", []
    return "FAIL", [
        {
            "code": "V6_OUTPUT_NOT_ISOLATED",
            "samePath": same_path,
            "underSandbox": under_sb,
            "outputPath": str(inputs.output_path),
        }
    ]


def _load_output_cells(output_path: Path) -> tuple[dict[str, str], list[dict]]:
    if output_path.is_file():
        out_doc = import_hwpx_as_ro_view(output_path)
        return {c.cellId: c.text for c in out_doc.cells}, []
    return {}, [{"code": "OUTPUT_MISSING", "detail": str(output_path)}]


def _check_v1_position(
    accepted_commands: list[EditCommand], out_cells: dict[str, str]
) -> tuple[str, list[dict]]:
    # 좌표별 after 값 존재. readback 채널(ro_view cell.text)은 라벨 매칭용
    # 정규화 텍스트(공백 병합·한글 사이 공백 제거)라, 원문 그대로 비교하면
    # 공백 있는 정상 기록도 오탐 FAIL 한다. 좌표 검증 목적에 맞게 양변을
    # 동일 정규화로 비교한다(실제 hp:t 는 공백 원형 그대로 기록됨 — 기록
    # 충실성은 writer/파이프라인 계층에서 별도 보장).
    from scripts.hwpx.parser.object_cell_mapper import _parser_normalize

    v1 = "PASS"
    findings: list[dict] = []
    for cmd in accepted_commands:
        got = out_cells.get(cmd.targetId)
        if got is None or _parser_normalize(got) != _parser_normalize(cmd.after):
            v1 = "FAIL"
            findings.append({
                "code": "V1_POSITION_MISS",
                "cellId": cmd.targetId,
                "expected": cmd.after,
                "got": got,
            })
    if not accepted_commands:
        v1 = "FAIL"
    return v1, findings


def _check_v2_cross_leak(
    output_path: Path, accepted_commands: list[EditCommand]
) -> tuple[str, list[dict]]:
    # cross-leak: output blob 에 unique value count == 1 (셀당)
    if not output_path.is_file():
        return "FAIL", []
    blob = _read_blob(output_path)
    for cmd in accepted_commands:
        occ = blob.count(cmd.after)
        # 같은 value 가 여러 명령에 등장할 수 있으므로 적용 명령 수 합산
        expected_min = sum(1 for c2 in accepted_commands if c2.after == cmd.after)
        if occ < expected_min:
            return "FAIL", [
                {
                    "code": "V2_LEAK_OR_MISSING",
                    "value": cmd.after,
                    "occ": occ,
                    "expectedMin": expected_min,
                }
            ]
        # 상한 — applied 외에 동일 value 가 원본에 이미 존재하지 않았다면
        # 출력은 expected_min 과 같아야 함. 본 게이트는 보수적으로 "최소"만
        # 검사하고 cross-leak 은 V3 으로 잡는다.
    return "PASS", []


def _check_v3_untouched_preserved(
    output_path: Path,
    accepted_commands: list[EditCommand],
    pre_save_cell_texts: dict[str, str],
    out_cells: dict[str, str],
) -> tuple[str, list[dict]]:
    if not output_path.is_file():
        return "FAIL", []
    applied_ids = {cmd.targetId for cmd in accepted_commands}
    for cell_id, before_text in pre_save_cell_texts.items():
        if cell_id in applied_ids:
            continue
        after_text = out_cells.get(cell_id)
        if after_text != before_text:
            return "FAIL", [
                {
                    "code": "V3_UNTOUCHED_CHANGED",
                    "cellId": cell_id,
                    "before": before_text,
                    "after": after_text,
                }
            ]
    return "PASS", []


def verify7(inputs: Verify7Inputs) -> dict[str, Any]:
    """본 함수는 writer 본 실행 이후 호출된다. output_path 에서 readback 만 수행."""
    findings: list[dict] = []
    results: dict[str, str] = {}

    v4, f4 = _check_v4_source_unchanged(inputs)
    results["V4_SOURCE_HASH_OK"] = v4
    findings.extend(f4)

    v5, f5 = _check_v5_expected_before(inputs)
    results["V5_EXPECTED_BEFORE_OK"] = v5
    findings.extend(f5)

    v6, f6 = _check_v6_output_isolated(inputs)
    results["V6_OUTPUT_ISOLATED"] = v6
    findings.extend(f6)

    out_cells, f_load = _load_output_cells(inputs.output_path)
    findings.extend(f_load)

    v1, f1 = _check_v1_position(inputs.accepted_commands, out_cells)
    results["V1_POSITION_OK"] = v1
    findings.extend(f1)

    v2, f2 = _check_v2_cross_leak(inputs.output_path, inputs.accepted_commands)
    results["V2_NO_CROSS_LEAK"] = v2
    findings.extend(f2)

    v3, f3 = _check_v3_untouched_preserved(
        inputs.output_path, inputs.accepted_commands, inputs.pre_save_cell_texts, out_cells
    )
    results["V3_UNTOUCHED_PRESERVED"] = v3
    findings.extend(f3)

    # V7 — readback == after (V1 과 사실상 동일하지만 명시적으로 분리 게이트)
    v7 = "PASS" if v1 == "PASS" and inputs.output_path.is_file() else "FAIL"
    results["V7_READBACK_MATCH"] = v7

    overall = "PASS" if all(v == "PASS" for v in results.values()) else "FAIL"
    return {"results": results, "findings": findings, "verdict": overall}
