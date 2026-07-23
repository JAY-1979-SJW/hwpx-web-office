"""서식 직접 채움 — 원본을 사본에 복사해 한 번만 파싱하고 기입 후 저장.

왜 (2026-07-24, 대표님 지시)
---------------------------
브라우저용 증분 편집 경로(para_save_apply_bridge)는 클라이언트를 믿지 않아
저장 때마다 원본을 여러 번 다시 읽는다. 게다가 그 로드는 AI 필드 인식을
포함해 대형 서식 1건에 167초가 걸린다. 종합소득세 신고서(531칸) 전량 기입에
저장만 1,100초가 걸린 실측이 있다:

    로드(AI인식) 167s → writer dry-run 재파싱 → 본실행 재파싱 → verify7 재파싱

**배치·에이전트 채움에는 좌표가 이미 스키마에 있다.** paragraphId 가
위치(`par_t_s{섹션}_{표}_r{행}_c{열}_p{문단}`)를 그대로 담으므로, 저장 때
AI 인식을 다시 돌릴 이유가 없다. 이 모듈은:

    원본 → 사본 복사 → 사본 1회 파싱 → 트리에 기입 → 1회 저장

§4 준수:
- **원본은 열지도 않는다** — 사본만 변경한다. 사본의 sha 를 원본과 대조해
  무변경을 사후 확인한다(원리상 당연하지만 게이트로 못박는다).
- 신규 charPr 생성 없음 — 기존 run 의 charPrIDRef 를 그대로 쓴다.
- header.xml 불변 · 표 구조 불변(셀 텍스트 내용만 기입).
- 이미 값이 있는 칸은 덮지 않는다(빈 칸만 채운다).

좌표 규칙이 읽기/쓰기와 같은 근거:
  parse_tables_from_section 은 root.iter() 로 표를 세고(중첩 포함, 섹션별
  증가), 셀은 직속 tr/tc 순번을 쓴다 — hwpx_table_ops.table_elements 및
  오늘 대칭을 맞춘 find_paragraph_in_cell 과 동일하다.

정확성은 좌표 추론에 기대지 않는다: 저장 후 결과 파일을 다시 열어 각
paragraphId 가 값을 담는지, 다른 칸으로 새지 않았는지 확인하는 것이 최종
게이트다(verify_output).
"""
from __future__ import annotations

import hashlib
import re
import shutil
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR / "scripts/hwpx") not in sys.path:
    sys.path.insert(0, str(_PR / "scripts/hwpx"))

from hwpx_package import HwpxPackage, local_name  # noqa: E402
from hwpx_paragraph_ops import (  # noqa: E402
    STATUS_OK,
    apply_text_range_edit,
    find_paragraph_in_cell,
    paragraph_runs,
    paragraph_text,
)

# par_t_s{섹션}_{표:03d}_r{행}_c{열}_p{문단}
_PID_RE = re.compile(r"^par_t_s(\d+)_(\d+)_r(\d+)_c(\d+)_p(\d+)$")


def parse_paragraph_id(pid: str) -> tuple[int, int, int, int, int] | None:
    """paragraphId → (섹션, 표순번, 행, 열, 문단). 형식이 다르면 None."""
    m = _PID_RE.match(pid or "")
    if not m:
        return None
    return tuple(int(g) for g in m.groups())  # type: ignore[return-value]


def _section_entry_by_number(package: HwpxPackage) -> dict[int, str]:
    """섹션 번호(파일명 sectionN.xml 의 N) → entry.

    섹션이 비연속일 수 있다(section3 이 없는 실사례). 위치가 아니라 파일명
    번호로 건다 — paragraphId 의 섹션 번호가 파일명 번호와 일치한다.
    """
    out: dict[int, str] = {}
    for entry in package.section_entries():
        m = re.search(r"section(\d+)\.xml$", entry.replace("\\", "/").lower())
        if m:
            out[int(m.group(1))] = entry
    return out


def _tables_in_root(root: ET.Element) -> list[ET.Element]:
    """섹션 root 안의 표를 문서 순서로(중첩 포함) — 파서와 같은 규칙."""
    return [e for e in root.iter() if local_name(e.tag).lower() == "tbl"]


def _direct(elem: ET.Element, name: str) -> list[ET.Element]:
    return [c for c in elem if local_name(c.tag).lower() == name]


def fill_document_direct(
    source_rel: str,
    fills: list[dict[str, Any]],
    *,
    output_dir: Path,
    project_root: Path = _PR,
    overwrite_nonempty: bool = False,
) -> dict[str, Any]:
    """빈 칸들에 값을 기입해 새 파일로 저장한다.

    fills: [{"paragraphId": str, "value": str}, ...]
    Returns: {verdict, filled, skipped, rejected, outputPath, outputName,
              sourceUnchanged, ...}
    """
    src = project_root / source_rel
    if not src.is_file():
        return {"verdict": "REJECTED", "reason": "SOURCE_FILE_MISSING"}
    if not fills:
        return {"verdict": "NOOP", "reason": "NO_FILLS"}

    sha_before = hashlib.sha256(src.read_bytes()).hexdigest()

    # ── 원본 → 사본. 이후 사본만 다룬다. ──────────────────────────
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"direct_fill_{uuid.uuid4().hex[:12]}.hwpx"
    shutil.copy2(src, out_path)

    pkg = HwpxPackage(out_path)
    entry_by_sec = _section_entry_by_number(pkg)

    # 섹션 root 는 한 번만 파싱해 캐시 — 칸마다 재파싱하면 O(칸수 × 문서)가
    # 되어 처음 겪은 그 느림이 재발한다.
    roots: dict[str, ET.Element] = {}
    tables_by_sec: dict[int, list[ET.Element]] = {}

    def _section_tables(sec: int) -> list[ET.Element] | None:
        if sec in tables_by_sec:
            return tables_by_sec[sec]
        entry = entry_by_sec.get(sec)
        if entry is None:
            return None
        root = roots.get(entry)
        if root is None:
            root = pkg.read_xml(entry)
            roots[entry] = root
        tbls = _tables_in_root(root)
        tables_by_sec[sec] = tbls
        return tbls

    filled: list[dict] = []
    skipped: list[dict] = []
    rejected: list[dict] = []
    touched_entries: set[str] = set()

    for f in fills:
        pid = f.get("paragraphId") or ""
        val = f.get("value")
        if not isinstance(val, str) or val == "":
            rejected.append({"paragraphId": pid, "reason": "EMPTY_VALUE"})
            continue
        coord = parse_paragraph_id(pid)
        if coord is None:
            rejected.append({"paragraphId": pid, "reason": "PID_UNPARSEABLE"})
            continue
        sec, tbl_i, row, col, p_i = coord
        tbls = _section_tables(sec)
        if tbls is None or not 0 <= tbl_i < len(tbls):
            rejected.append({"paragraphId": pid, "reason": "TABLE_NOT_FOUND"})
            continue
        rows = _direct(tbls[tbl_i], "tr")
        if not 0 <= row < len(rows):
            rejected.append({"paragraphId": pid, "reason": "ROW_NOT_FOUND"})
            continue
        cols = _direct(rows[row], "tc")
        if not 0 <= col < len(cols):
            rejected.append({"paragraphId": pid, "reason": "CELL_NOT_FOUND"})
            continue
        para = find_paragraph_in_cell(cols[col], p_i)
        if para is None:
            rejected.append({"paragraphId": pid, "reason": "PARAGRAPH_NOT_FOUND"})
            continue
        if paragraph_text(para).strip() and not overwrite_nonempty:
            skipped.append({"paragraphId": pid, "reason": "CELL_NOT_EMPTY"})
            continue
        runs = paragraph_runs(para)
        if not runs:
            rejected.append({"paragraphId": pid, "reason": "NO_RUN"})
            continue
        res = apply_text_range_edit(para, runs[0], 0, 0, val, expected_before="")
        if res.get("status") != STATUS_OK:
            rejected.append({"paragraphId": pid, "reason": res.get("status")})
            continue
        filled.append({"paragraphId": pid, "value": val,
                       "charPrIDRef": res.get("charPrIDRef")})
        touched_entries.add(entry_by_sec[sec])

    if not filled:
        out_path.unlink(missing_ok=True)
        # 반환 형태를 본 경로와 맞춘다 — skipped/rejected 는 개수, *Items 는
        # 목록. 호출자가 분기마다 다른 키를 다루지 않게 한다.
        return {"verdict": "NOOP" if not rejected else "FAIL",
                "filled": 0,
                "skipped": len(skipped), "rejectedCount": len(rejected),
                "skippedItems": skipped, "rejected": rejected,
                "sourceUnchanged": True}

    for entry in touched_entries:
        pkg.write_xml(entry, roots[entry])
    pkg.write_package(out_path)

    sha_after = hashlib.sha256(src.read_bytes()).hexdigest()
    source_unchanged = sha_after == sha_before

    verdict = "PASS"
    if rejected:
        verdict = "PARTIAL"
    if not source_unchanged:
        verdict = "FAIL"          # 절대 일어나선 안 된다 — 사본만 만졌다

    return {
        "verdict": verdict,
        "filled": len(filled),
        "skipped": len(skipped),
        "rejectedCount": len(rejected),
        "rejected": rejected,
        "skippedItems": skipped,
        "sourceUnchanged": source_unchanged,
        "outputName": out_path.name,
        "outputPath": str(out_path),
        "touchedSections": sorted(touched_entries),
    }


def verify_output(
    output_rel: str,
    expected: dict[str, str],
    *,
    project_root: Path = _PR,
) -> dict[str, Any]:
    """저장본을 로더로 다시 열어 값이 제자리에 있고 새지 않았는지 확인.

    좌표 추론을 믿지 않는다 — 이것이 최종 게이트다. expected 는
    {paragraphId: value}.
    """
    from scripts.hwpx.web_office.editor_file_bridge import load_hwpx_for_editor

    res = load_hwpx_for_editor(
        {"operation": "HWPX_EDITOR_LOAD", "sourcePath": output_rel},
        project_root=project_root)
    if res.get("verdict") != "PASS":
        return {"ok": False, "reason": "OUTPUT_LOAD_FAILED"}
    texts = {p["paragraphId"]:
             "".join(r.get("text", "") for r in p.get("runs", []))
             for p in res["documentModel"]["paragraphs"]}
    in_place = bad = 0
    mismatches = []
    for pid, val in expected.items():
        got = texts.get(pid, "")
        if got.strip() == val:
            in_place += 1
        else:
            bad += 1
            if len(mismatches) < 8:
                mismatches.append({"paragraphId": pid, "expected": val,
                                   "got": got[:24]})
    want_pids = set(expected)
    values = set(expected.values())
    leaks = []
    for pid, t in texts.items():
        if pid in want_pids:
            continue
        for v in values:
            if v in t:
                leaks.append({"paragraphId": pid, "value": v})
                break
    return {"ok": bad == 0 and not leaks,
            "inPlace": in_place, "mismatch": bad, "leaks": len(leaks),
            "mismatches": mismatches, "leakSamples": leaks[:8]}
