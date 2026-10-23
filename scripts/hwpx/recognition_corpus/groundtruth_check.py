"""정답표 대조 — 분석기가 찾은 값칸이 사람이 확인한 칸 주소표와 얼마나 맞는가.

정답표: <dir>/<id>.json (fields[].table/row/col 과 sign_cells[]) + <id>.hwpx.
지표: 정답 칸 재현율(recall), 정답에 없는 칸 수(extra), 서명칸 오입력 수(sign_hit).
읽기 전용 — 서식을 고치지 않는다.

사용: python groundtruth_check.py <정답표 폴더> [id ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[2]
for _p in (str(_SCRIPTS), str(_SCRIPTS / "hwpx")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

def check(gt_dir: Path, form_id: str) -> dict:
    from hwpx.parser import parse_hwpx_v2
    from hwpx.pipeline.form_recognizer import recognize_form

    gt = json.loads((gt_dir / f"{form_id}.json").read_text(encoding="utf-8"))
    want = {(f["table"], f["row"], f["col"]) for f in gt.get("fields", [])}
    sign = {(f["table"], f["row"], f["col"]) for f in gt.get("sign_cells", [])}
    form = recognize_form(parse_hwpx_v2(gt_dir / f"{form_id}.hwpx"))
    got = {(s.tableOrdinal, s.visualRow, s.visualCol) for s in form.enhancedSlots}
    return {
        "id": form_id,
        "gt_fields": len(want),
        "slots": len(got),
        "found": len(want & got),
        "recall": round(len(want & got) / len(want), 3) if want else None,
        "extra": len(got - want - sign),
        "sign_hit": len(got & sign),
        "missing": sorted(want - got)[:10],
    }


def main(argv: list[str]) -> int:
    gt_dir = Path(argv[1])
    ids = argv[2:] or sorted(p.stem for p in gt_dir.glob("*.json"))
    for fid in ids:
        print(json.dumps(check(gt_dir, fid), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
