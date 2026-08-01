"""AI 제안 검증 — 비창조·주소 해석을 기계 검사한다.

기준서: docs/design/hwpx_ai_doc_interpretation_fill_standard.md §3·§4

AI 출력은 신뢰하지 않는다. 두 가지를 기계로 대조한다:
  ① 비창조(NON_SOURCE_VALUE): 제안값이 소스 데이터 값에서 유래했는가.
     유래를 입증 못 하면 폐기 — 관공서 제출물에 지어낸 값은 허위 기재다.
  ② 주소 해석(ADDRESS_UNRESOLVED): 제안 대상 paragraphId 가 실파일에서
     form_direct_fill 과 동일한 규칙으로 해석되는가 — 낡은 스키마 방어
     (2026-08-01 전수 조사에서 스키마-실파일 불일치 3건이 유출을 냈다).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(_PR / "scripts/hwpx"))

_NORM_RE = re.compile(r"[\s\-–—.,()\[\]:：/]+")


def _norm(value: str) -> str:
    return _NORM_RE.sub("", str(value or "")).lower()


def value_from_source(value: str, source: dict) -> str | None:
    """제안값이 유래한 소스 키. 없으면 None(=지어낸 값).

    정규화(공백·구분기호 제거) 후 양방향 포함을 인정한다 —
    '010-1234-5678' ↔ '01012345678', '서울특별시 중구' ⊂ 전체 주소.
    """
    nv = _norm(value)
    if not nv:
        return None
    for k, sv in (source or {}).items():
        ns = _norm(sv)
        if not ns:
            continue
        if nv == ns or nv in ns or ns in nv:
            return str(k)
    return None


def validate_non_source(
    proposals: list[dict], source: dict,
) -> tuple[list[dict], list[dict]]:
    """(통과 제안, 폐기 제안). 통과분에는 sourceFieldVerified 를 단다."""
    accepted: list[dict] = []
    rejected: list[dict] = []
    for p in proposals:
        origin = value_from_source(p.get("value", ""), source)
        if origin is None:
            rejected.append({**p, "reason": "NON_SOURCE_VALUE"})
            continue
        accepted.append({**p, "sourceFieldVerified": origin})
    return accepted, rejected


def verify_addresses(
    source_rel: str, pids: list[str], *, project_root: Path = _PR,
) -> dict[str, str]:
    """{paragraphId: 실패사유}. 전부 해석되면 빈 dict.

    form_direct_fill 의 프로덕션 함수를 그대로 쓴다 — 재구현 금지.
    원본은 읽기만 한다.
    """
    from hwpx_package import HwpxPackage
    from hwpx_paragraph_ops import find_paragraph_in_cell, paragraph_runs
    from scripts.hwpx.web_office.form_direct_fill import (
        _direct, _section_entry_by_number, _tables_in_root,
        parse_paragraph_id)

    src = project_root / source_rel
    if not src.is_file():
        return {pid: "SOURCE_FILE_MISSING" for pid in pids}
    pkg = HwpxPackage(src)
    entry_by_sec = _section_entry_by_number(pkg)
    tables_by_sec: dict[int, list | None] = {}
    out: dict[str, str] = {}
    for pid in pids:
        coord = parse_paragraph_id(pid)
        if coord is None:
            out[pid] = "PID_UNPARSEABLE"
            continue
        sec, tbl_i, row, col, p_i = coord
        if sec not in tables_by_sec:
            entry = entry_by_sec.get(sec)
            tables_by_sec[sec] = (
                _tables_in_root(pkg.read_xml(entry)) if entry else None)
        tbls = tables_by_sec[sec]
        if tbls is None or not 0 <= tbl_i < len(tbls):
            out[pid] = "TABLE_NOT_FOUND"
            continue
        rows = _direct(tbls[tbl_i], "tr")
        if not 0 <= row < len(rows):
            out[pid] = "ROW_NOT_FOUND"
            continue
        cols = _direct(rows[row], "tc")
        if not 0 <= col < len(cols):
            out[pid] = "CELL_NOT_FOUND"
            continue
        para = find_paragraph_in_cell(cols[col], p_i)
        if para is None:
            out[pid] = "PARAGRAPH_NOT_FOUND"
            continue
        if not paragraph_runs(para):
            out[pid] = "NO_RUN"
    return out


def apply_address_results(
    accepted: list[dict], addr_failures: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """주소 검사 결과를 제안에 반영 — (통과, ADDRESS_UNRESOLVED 폐기)."""
    ok: list[dict] = []
    bad: list[dict] = []
    for p in accepted:
        reason = addr_failures.get(p.get("key", ""))
        if reason:
            bad.append({**p, "reason": "ADDRESS_UNRESOLVED",
                        "addressFailure": reason})
        else:
            ok.append(p)
    return ok, bad


def gate_verdict(
    accepted: list[dict], rejected: list[dict], held: list[dict],
) -> dict[str, Any]:
    """드라이 런 게이트(§4) — 위반이 '통과분'에 남아있으면 FAIL.

    폐기·보류가 있어도 통과분이 깨끗하면 PASS 다 — 게이트는 '나쁜 제안이
    걸러졌는가'를 재지, '나쁜 제안이 없었는가'를 재지 않는다.
    """
    bad_in_accepted = [
        p for p in accepted
        if p.get("reason") or not p.get("sourceFieldVerified")]
    return {
        "pass": not bad_in_accepted,
        "acceptedCount": len(accepted),
        "rejectedCount": len(rejected),
        "heldForThirdPartyCount": len(held),
        "sensitiveNeedsConfirmation": sum(
            1 for p in accepted if p.get("requiresConfirmation")),
    }
