"""apply_format_bridge — 서식(글꼴/크기/색상/굵게 등) 편집 요청 → charPr
해석(기존 매칭 또는 CLAUDE.md §4.1 append-only 신규 생성) → 기존
APPLY_FORMAT 저장 파이프라인(run_para_edit_e2e) 연결.

브라우저는 "무엇을 무엇으로 바꿔라"(overrides)만 보내고, 실제 charPr
id 해석(문서에 이미 있는지 찾기, 없으면 append)은 이 브리지가 서버
에서 담당한다 — 클라이언트가 임의 id 를 지정하게 하면 검증을 우회할
수 있다.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path
from typing import Any

_PR = Path(__file__).resolve().parents[3]
if str(_PR) not in sys.path:
    sys.path.insert(0, str(_PR))
_HX = _PR / "scripts" / "hwpx"
if str(_HX) not in sys.path:
    sys.path.insert(0, str(_HX))

from scripts.hwpx.parser.style_parser import parse_char_pr_defs  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.charpr_append import (  # ruff: ignore[module-import-not-at-top-of-file]
    append_char_pr_with_overrides,
    find_matching_char_pr,
)
from scripts.hwpx.web_office.para_edit_e2e_pipeline import SCENARIO_APPLY_FORMAT, run_para_edit_e2e  # ruff: ignore[module-import-not-at-top-of-file]
from scripts.hwpx.web_office.ro_view_importer import import_hwpx_as_ro_view  # ruff: ignore[module-import-not-at-top-of-file]


def _current_char_pr_id(doc, paragraph_id: str, range_anchor: int) -> str | None:
    """paragraph_id 문단에서 range_anchor 오프셋을 담고 있는 run 의
    charPrIDRef. 못 찾으면 문단 첫 run 의 charPrIDRef(있으면)."""
    for p in doc.paragraphs:
        if p.paragraphId != paragraph_id:
            continue
        pos = 0
        for r in p.runs:
            end = pos + len(r.text or "")
            if pos <= range_anchor < end or (range_anchor == pos == end):
                return r.charPrIDRef
            pos = end
        return p.runs[0].charPrIDRef if p.runs else None
    return None


def resolve_and_apply_format(  # ruff: ignore[too-many-arguments] (다른 파일에서 호출 — 시그니처 변경 보류)
    *,
    source_path: Path,
    output_path: Path,
    paragraph_id: str,
    range_anchor: int,
    range_focus: int,
    overrides: dict[str, Any],
    tmp_dir: Path,
) -> dict[str, Any]:
    """overrides 를 만족하는 charPr 를 해석(매칭/append)한 뒤
    APPLY_FORMAT 으로 저장까지 실행. output_path 에 결과 기록.

    Returns run_para_edit_e2e 의 결과 dict + resolvedCharPrIDRef +
    charPrCreated(bool).
    """
    doc = import_hwpx_as_ro_view(source_path)
    current_id = _current_char_pr_id(doc, paragraph_id, range_anchor)
    if current_id is None:
        return {
            "verdict": "FAIL",
            "reason": "CURRENT_CHARPR_NOT_FOUND",
            "paragraphId": paragraph_id,
        }

    with zipfile.ZipFile(source_path) as z:
        header_bytes = z.read("Contents/header.xml")
    char_pr_defs = parse_char_pr_defs(header_bytes)

    matched = find_matching_char_pr(char_pr_defs, current_id, overrides)
    apply_source = source_path
    char_pr_created = False
    if matched is not None:
        target_id = matched
    else:
        new_header, target_id = append_char_pr_with_overrides(header_bytes, current_id, overrides)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        patched = tmp_dir / f"__hdrpatch_{source_path.stem}.hwpx"
        with zipfile.ZipFile(source_path) as z_in, zipfile.ZipFile(patched, "w") as z_out:
            for name in z_in.namelist():
                info = z_in.getinfo(name)
                data = new_header if name == "Contents/header.xml" else z_in.read(name)
                z_out.writestr(info, data)
        apply_source = patched
        char_pr_created = True

    result = run_para_edit_e2e(
        source_path=apply_source,
        output_path=output_path,
        scenario=SCENARIO_APPLY_FORMAT,
        paragraph_id=paragraph_id,
        range_anchor=range_anchor,
        range_focus=range_focus,
        target_char_pr_id=target_id,
        allow_writer=True,
    )
    if char_pr_created and apply_source != source_path:
        try:
            apply_source.unlink()
        except OSError:
            pass
    result["resolvedCharPrIDRef"] = target_id
    result["charPrCreated"] = char_pr_created
    return result
