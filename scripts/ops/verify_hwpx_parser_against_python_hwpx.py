"""HWPX-PARSER-CROSS-CHECK-PYTHON-HWPX-01.

자체 파서(scripts/hwpx/parser)의 문단/표 구조 인식 결과를, 외부 오픈소스
python-hwpx(Apache-2.0, https://github.com/airmang/python-hwpx)로 교차
검증한다. scripts/hwpx/openhwp_rust_probe.py와 같은 "비교 전용" 역할 —
python-hwpx를 production 파싱 경로에 넣지 않는다.

배경 (2026-09-29): HWPX는 표(hp:tbl)가 문단(hp:p) 안에 컨트롤로 중첩될
수 있는데, 자체 파서의 _para_text가 이를 재귀적으로 다 긁어 문서 제목
후보(titleCandidate)에 표 전체 내용이 섞이는 버그가 있었다. python-hwpx의
TextExtractor.iter_document_paragraphs(include_nested=True)가 각 문단이
표 안에 중첩됐는지(is_nested) 정확히 구분해준다는 걸 확인하고 이 버그를
잡았다. 이 스크립트는 그 교차검증 방법을 재사용 가능한 도구로 남긴다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _PROJECT_ROOT / "scripts"

# 이름 충돌 주의: pip 패키지 python-hwpx 도 최상위 모듈 이름이 `hwpx` 이고,
# 이 저장소의 내부 패키지도 scripts/hwpx 로 최상위 모듈 이름이 `hwpx` 다.
# 필요한 쪽을 쓸 때마다 sys.path 순서를 바꾸고 sys.modules 에서 `hwpx`로
# 시작하는 캐시를 지운 뒤 다시 import 해서 어느 쪽이 로드됐는지 확실히 한다.


def _purge_hwpx_modules() -> None:
    for name in [m for m in sys.modules if m == "hwpx" or m.startswith("hwpx.")]:
        del sys.modules[name]


def _our_parser_summary(path: Path) -> dict:
    _purge_hwpx_modules()
    if str(_SCRIPTS) in sys.path:
        sys.path.remove(str(_SCRIPTS))
    sys.path.insert(0, str(_SCRIPTS))

    from hwpx.parser.parser_engine import parse_hwpx_v2

    result = parse_hwpx_v2(path)
    return {
        "titleCandidate": result.document.titleCandidate,
        "topLevelParagraphTextLen": len(result.document.fullText or ""),
        "tableCount": len(result.tables),
        "cellCount": sum(len(t.cells) for t in result.tables),
    }


def _python_hwpx_summary(path: Path) -> dict:
    _purge_hwpx_modules()
    if str(_SCRIPTS) in sys.path:
        sys.path.remove(str(_SCRIPTS))

    from hwpx import ObjectFinder, TextExtractor

    extractor = TextExtractor(str(path))
    top_level_text_len = 0
    nested_count = 0
    top_count = 0
    for info in extractor.iter_document_paragraphs(include_nested=True):
        if info.is_nested:
            nested_count += 1
        else:
            top_count += 1
            top_level_text_len += len(info.text() or "")

    finder = ObjectFinder(str(path))
    cell_count = len(finder.find_all(tag="tc"))
    table_count = len(finder.find_all(tag="tbl"))
    return {
        "topLevelParagraphCount": top_count,
        "nestedParagraphCount": nested_count,
        "topLevelParagraphTextLen": top_level_text_len,
        "tableCount": table_count,
        "cellCount": cell_count,
    }


def verify_one(path: Path) -> dict:
    """단일 HWPX 파일에 대한 교차검증 결과. findings가 비어있으면 일치."""
    ours = _our_parser_summary(path)
    theirs = _python_hwpx_summary(path)
    findings: list[str] = []

    if ours["tableCount"] != theirs["tableCount"]:
        findings.append(
            f"tableCount 불일치: 자체={ours['tableCount']} python-hwpx={theirs['tableCount']}"
        )
    if ours["cellCount"] != theirs["cellCount"]:
        findings.append(
            f"cellCount 불일치: 자체={ours['cellCount']} python-hwpx={theirs['cellCount']}"
        )
    # 표가 문단 안에 중첩된 문서(nestedParagraphCount > 0)인데 자체 파서의
    # 표-밖-본문 텍스트 길이가 python-hwpx의 표-밖-본문 텍스트 길이보다
    # 훨씬 길면, 중첩 표 내용이 본문에 다시 섞여 들어가는 회귀다.
    if theirs["nestedParagraphCount"] > 0:
        their_len = theirs["topLevelParagraphTextLen"]
        our_len = ours["topLevelParagraphTextLen"]
        if our_len > their_len + 50:
            findings.append(
                f"본문 텍스트 길이 이상: 자체={our_len}자 python-hwpx(표 밖)={their_len}자 "
                "— 중첩 표 내용이 본문에 섞여 들어가는 회귀 의심"
            )

    return {
        "file": str(path),
        "ours": ours,
        "pythonHwpx": theirs,
        "findings": findings,
        "verdict": "PASS" if not findings else "MISMATCH",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="검증할 .hwpx 파일 경로(들)")
    parser.add_argument("--out-json", type=Path)
    args = parser.parse_args(argv)

    reports = [verify_one(p) for p in args.paths]
    overall_ok = all(r["verdict"] == "PASS" for r in reports)

    if args.out_json:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    for r in reports:
        print(f"[{r['verdict']}] {r['file']}")
        for f in r["findings"]:
            print(f"    - {f}")

    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
