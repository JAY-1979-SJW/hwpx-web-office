#!/usr/bin/env python3
"""
감리 서료 3개 - 정확한 셀좌표(cellAddr/cellSpan) 기반 필드 기준서 생성

원칙:
- 빈 칸(text=='')이면서 같은 행에 왼쪽 라벨 셀이 있으면 → 입력 필드
- 행 전체가 통째로 비어있으면(라벨 없음) → spacer(여백 행)로 분류, 필드 제외
- 라벨이 없는 텍스트 셀(성명/주소 등)은 '라벨+필기공간 결합형' 셀로 별도 표기
"""

import json
import re
from pathlib import Path

PARSED_FILE = Path("data/cache/supervision_complete_guides_parsed.json")
SPEC_OUTPUT = Path("docs/specifications/supervision_forms_final.json")

FORMS_INFO = {
    "331": {"name": "공사 감리자 지정 신청서", "icon": "📋"},
    "99": {"name": "소방시설공사 완공검사신청서", "icon": "🔥"},
    "57": {"name": "특정ㆍ준특정옥외탱크저장소 구조안전점검시기 연장신청서", "icon": "🏭"},
}


def build_row_index(cells):
    rows = {}
    for c in cells:
        rows.setdefault(c["row"], []).append(c)
    for r in rows:
        rows[r].sort(key=lambda x: x["col_addr0"])
    return rows


def classify_role(label: str):
    """라벨 텍스트로 기관/서명/자동/사용자 역할 판정 (강제성 없음: required는 항상 False)"""
    if any(kw in label for kw in ["접수번호", "접수일자", "처리기간", "처리일자", "신고번호"]):
        return "agency", "🏛️ 기관에서 부여/처리하는 항목입니다 (신청 시 비워두세요)"
    if any(kw in label for kw in ["서명", "(인)", "(서명 또는 인)"]):
        return "signature", "✍️ 서명 또는 인감 (확인 표시로 대체 가능)"
    return "user", "✏️ 필요시 작성하세요"


INSTRUCTION_MARKERS = ("■", "※", "<개정")
BLANK_PLACEHOLDER_RE = re.compile(r"^\(\s*\)$")  # "(     )" 처럼 괄호만 있는 필기용 placeholder


def is_instruction_row(non_blank):
    """법령 인용/작성지침 줄(제목행) 판별 - 필드 후보에서 제외"""
    return any(any(m in c["text"] for m in INSTRUCTION_MARKERS) for c in non_blank)


def is_placeholder_text(text: str) -> bool:
    """ "(     )" 같은 괄호+공백뿐인 텍스트는 실질적으로 빈 칸(필기 대상)"""
    return bool(BLANK_PLACEHOLDER_RE.match(text.strip()))


def cell_end(c):
    return c["col_addr0"] + c["col_span"] - 1


def col_overlap(a, b) -> int:
    """두 셀의 열 구간이 겹치는 폭 (0이면 안 겹침)"""
    lo = max(a["col_addr0"], b["col_addr0"])
    hi = min(cell_end(a), cell_end(b))
    return max(0, hi - lo + 1)


STAMP_LABEL_RE = re.compile(r"^\(\s*서명\s*(또는)?\s*인\s*\)$")


def is_stamp_label(text: str) -> bool:
    """ "(서명 또는 인)" 같은 반복 도장 표시 - 다른 칸의 라벨로 재사용하면 안 됨"""
    return bool(STAMP_LABEL_RE.match(text.strip()))


def find_label_for_blank(blank, non_blank, rows, row_num, total_cols):
    """
    우선순위:
      1) 같은 행에서 '붙어있는'(간격 1) 왼쪽 라벨 - "라벨: ___" 인라인 패턴
         (단, "(서명 또는 인)" 같은 반복 도장 표시는 라벨 후보에서 제외)
      2) 같은 행에서 가장 가까운 좌/우 라벨 (도장 표시 제외)
      3) 위 1,2에서 유효한 같은 행 라벨을 못 찾았을 때만: 바로 위 행의 '좁은'
         (표 너비 40% 이하) 열-정렬 헤더 - 반복표(헤더 위/데이터 아래) 패턴.
         같은 행에 이미 유효한 라벨이 있으면 이 단계는 절대 쓰지 않는다
         (너비 넓은 무관 텍스트가 우연히 겹쳐 검증된 필드를 오염시키는 회귀 방지).
    """
    labelable = [c for c in non_blank if not is_stamp_label(c["text"])]
    left_labels = [c for c in labelable if cell_end(c) < blank["col_addr0"]]
    right_labels = [c for c in labelable if c["col_addr0"] > cell_end(blank)]
    left_label = max(left_labels, key=lambda x: cell_end(x)) if left_labels else None
    right_label = min(right_labels, key=lambda x: x["col_addr0"]) if right_labels else None

    # 1) 붙어있는 왼쪽 라벨 (간격 1칸)
    if left_label and blank["col_addr0"] - cell_end(left_label) == 1:
        return left_label, "inline_left"

    # 2) 같은 행 폴백: 가장 가까운 좌/우
    if left_label or right_label:
        left_dist = blank["col_addr0"] - cell_end(left_label) if left_label else None
        right_dist = right_label["col_addr0"] - cell_end(blank) if right_label else None
        if left_label and (not right_label or left_dist <= right_dist):
            return left_label, "nearest_left"
        return right_label, "nearest_right"

    # 3) 같은 행에 쓸 라벨이 전혀 없을 때만: 바로 위 행의 좁은 열-정렬 헤더 (반복표 폴백)
    if row_num - 1 > 3:
        above_row = rows.get(row_num - 1, [])
        above_candidates = [
            c
            for c in above_row
            if c["text"]
            and not is_stamp_label(c["text"])
            and not is_placeholder_text(c["text"])
            and col_overlap(c, blank) > 0
            and c["col_span"] <= max(3, total_cols * 0.4)
        ]
        if above_candidates:
            best = max(above_candidates, key=lambda c: col_overlap(c, blank))
            return best, "column_header_above_fallback"

    return None, None


def _blank_cell_fields(blanks, non_blank, rows, row_num, total_cols, used_as_label):
    fields = []
    for blank in blanks:
        label_cell, reason = find_label_for_blank(blank, non_blank, rows, row_num, total_cols)
        if not label_cell:
            continue  # 근거(인접 라벨) 없으면 제외 - 추측 금지

        label = label_cell["text"].strip()
        used_as_label.add(label_cell["cell"])
        role, guidance = classify_role(label)
        fields.append({
            "cell": blank["cell"],
            "row": blank["row"],
            "field_name": label,
            "label_cell": label_cell["cell"],
            "type": "date" if ("일자" in label or "연월일" in label) else "text",
            "role": role,
            "required": False,
            "guidance": guidance,
            "kind": "blank_cell",
            "match_reason": reason,
        })
    return fields


def _embedded_write_space_fields(non_blank, used_as_label):
    # 임베디드 필드: 문단 2개+ & 뒤쪽 문단에 공백 5칸+ (구조적 근거) → 라벨+필기공간 결합 셀
    fields = []
    for c in non_blank:
        if not c.get("embedded_write_space") or c["cell"] in used_as_label:
            continue
        paras = c.get("paragraphs", [])
        label = paras[0].strip() if paras else c["text"]
        if not label:
            continue
        suffix = " ".join(p.strip() for p in paras[1:] if p.strip())
        used_as_label.add(c["cell"])
        role, guidance = classify_role(label)
        fields.append({
            "cell": c["cell"],
            "row": c["row"],
            "field_name": label,
            "label_cell": c["cell"],
            "type": "date" if ("일자" in label or "연월일" in label) else "text",
            "role": role,
            "required": False,
            "guidance": guidance + (f' (칸 안에 "{suffix}" 표기 포함)' if suffix else ""),
            "kind": "embedded_write_space",
        })
    return fields


def _label_only_fields(rows, used_as_label):
    # 3차 패스: 구조적 근거(빈칸/임베디드) 없이 라벨 한 줄만 있는 셀도
    # 낮은 신뢰도로 필드화 (사용자 요청: 문서 반영만 되면 됨).
    # 조건: row<=2 제외, 법령/지침 줄 제외, 다른 필드의 라벨로 이미 쓰인 셀 제외,
    #       row_span>=3인 큰 구역제목(① 건축주 처럼 여러 행에 걸친 섹션 타이틀) 제외
    fields = []
    for row_num in sorted(rows.keys()):
        if row_num <= 3:
            continue
        row_cells = rows[row_num]
        non_blank = [c for c in row_cells if c["text"] and not is_placeholder_text(c["text"])]
        if not non_blank or is_instruction_row(non_blank):
            continue
        for c in non_blank:
            if c["cell"] in used_as_label:
                continue
            if c.get("row_span", 1) >= 3:
                continue  # 섹션 타이틀 등 큰 병합 블록 제외
            label = c["text"].strip()
            role, guidance = classify_role(label)
            fields.append({
                "cell": c["cell"],
                "row": c["row"],
                "field_name": label,
                "label_cell": c["cell"],
                "type": "date" if ("일자" in label or "연월일" in label) else "text",
                "role": role,
                "required": False,
                "guidance": guidance + " (⚠️ 구조적 근거 낮음: 라벨 셀 자체에 입력)",
                "kind": "label_only",
            })
    return fields


def extract_fields(form_id, form_data):
    cells = form_data["cells"]
    rows = build_row_index(cells)
    total_cols = max((cell_end(c) for c in cells), default=0) + 1

    fields = []
    used_as_label = set()  # 전역: 이미 다른 필드의 라벨로 쓰인 셀(순수 라벨, 필드 아님)

    for row_num in sorted(rows.keys()):
        # row 1~3은 서식마다 표현이 달라도(■/※/·) 항상 법령인용/제목/작성지침 구간
        # (검증된 4개 문서에서 공통 확인) → 구조적으로 필드 후보에서 제외
        if row_num <= 3:
            continue

        row_cells = rows[row_num]
        non_blank = [c for c in row_cells if c["text"] and not is_placeholder_text(c["text"])]
        blanks = [c for c in row_cells if not c["text"] or is_placeholder_text(c["text"])]

        if not non_blank:
            continue  # 행 전체가 빈칸(라벨 없음) → spacer, 건너뜀
        if is_instruction_row(non_blank):
            continue  # 법령 인용/작성지침 줄(■/※/<개정 마커) → 제외

        fields.extend(
            _blank_cell_fields(blanks, non_blank, rows, row_num, total_cols, used_as_label)
        )
        fields.extend(_embedded_write_space_fields(non_blank, used_as_label))

    fields.extend(_label_only_fields(rows, used_as_label))

    for fid, f in enumerate(fields, start=1):
        f["id"] = fid
    return fields


def main():
    parsed = json.loads(PARSED_FILE.read_text(encoding="utf-8"))
    result = {}

    print("=" * 90)
    print("✅ 정확한 셀좌표 기반 필드 기준서 생성 (cellAddr/cellSpan)")
    print("=" * 90)

    for form_id, info in FORMS_INFO.items():
        form_data = parsed[form_id]
        fields = extract_fields(form_id, form_data)

        result[form_id] = {
            "form_id": int(form_id),
            "form_name": info["name"],
            "icon": info["icon"],
            "total_fields": len(fields),
            "fields": fields,
        }

        print(
            f"\n{info['icon']} {info['name']} — 입력 필드 {len(fields)}개 (근거: 왼쪽 라벨 확인된 빈칸만)"
        )
        for f in fields:
            print(f"   [{f['cell']}] {f['field_name']}  ({f['role']})")

    SPEC_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SPEC_OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 저장: {SPEC_OUTPUT}")


if __name__ == "__main__":
    main()
