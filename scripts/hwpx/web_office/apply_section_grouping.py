#!/usr/bin/env python3
"""
API 호출 없이(§4.8) 구획(장) 헤더를 구조적으로 찾아 필드를 그룹핑한다.

패턴 근거: 검증된 3건에서 "① 건축주", "② 설계자", "③ 공사개요"(form_331),
"신 청 인", "시공장소", "책임시공 및 기술관리 소방기술자"(form_99) 같은
구획 헤더는 실측으로 다음 두 형태 중 하나였다:
  A) 원문자 번호(①~⑩)로 시작하는 셀 - 명확한 구획 표시
  B) row_span >= 2 인 좁은 셀(표 너비 대비) - 여러 행에 걸친 구획 라벨

각 필드에 'section' 태그를 붙이고(가장 가까운 앞쪽 구획 헤더),
구획 헤더 셀 자신은 ai_fillable=false로 표시한다(이미 다른 로직으로
false가 아닌 경우에만 - 세션이 직접 판단한 3건은 건드리지 않음).

대상: docs/specifications/{prefix}_spec.json + data/cache/{prefix}_parsed.json
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

CIRCLED_NUM_RE = re.compile(r'^[①-⑳]')  # ①~⑳


def find_section_headers(cells, total_cols):
    """구획 헤더로 볼 수 있는 셀들을 (row, text) 리스트로 반환 (행 순서대로)"""
    headers = []
    for c in cells:
        text = c['text'].strip()
        if not text:
            continue
        is_circled = bool(CIRCLED_NUM_RE.match(text))
        is_narrow_tall = c.get('row_span', 1) >= 2 and c['col_span'] <= max(3, total_cols * 0.15)
        if is_circled or is_narrow_tall:
            headers.append({'row': c['row'], 'text': text, 'cell': c['cell'], 'circled': is_circled})
    headers.sort(key=lambda h: h['row'])
    return headers


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else 'construction_clean'
    spec_path = Path(f"docs/specifications/{prefix}_spec.json")
    parsed_path = Path(f"data/cache/{prefix}_parsed.json")

    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    parsed = json.loads(parsed_path.read_text(encoding='utf-8'))

    stats = Counter()
    section_marked_false = 0

    for doc_id, form in spec.items():
        pdata = parsed.get(doc_id)
        if not pdata:
            continue
        cells = pdata['cells']
        total_cols = max((c['col_addr0'] + c['col_span'] for c in cells), default=1)
        headers = find_section_headers(cells, total_cols)
        header_cells = {h['cell'] for h in headers}

        for field in form['fields']:
            # 이 필드보다 엄격히 앞쪽 행에 있는 가장 가까운 구획 헤더 찾기
            # (같은 행 <= 비교는 같은 행의 다른 헤더를 잘못 끌어오는 오류가 있어 < 로 제한)
            candidates = [h for h in headers if h['row'] < field['row']]
            if candidates:
                section = candidates[-1]['text']
                field['section'] = section
                stats['tagged'] += 1
            else:
                stats['no_section'] += 1

            # 구획 헤더 셀 자신은 입력 대상이 아님 (이미 세션이 판단한 필드는 건드리지 않음)
            if field['cell'] in header_cells and 'ai_fillable' not in field:
                field['ai_fillable'] = False
                field['ai_guidance'] = 'ℹ️ 구획 제목입니다. 같은 구획 안의 다른 칸에 실제 정보를 입력하세요.'
                field['pattern_reason'] = 'section_header'
                section_marked_false += 1

    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

    print("=" * 70)
    print("구획(장) 그룹핑 - 패턴 기반, API 미호출")
    print("=" * 70)
    print(f"구획 태그 부여: {stats['tagged']}개 필드")
    print(f"구획 없음: {stats['no_section']}개 필드")
    print(f"구획 헤더 자체를 입력불필요로 판정: {section_marked_false}개")
    print(f"\n💾 저장: {spec_path}")


if __name__ == '__main__':
    main()
