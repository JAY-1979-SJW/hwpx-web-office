#!/usr/bin/env python3
"""
API 호출 없이(§4.8) 순수 텍스트 패턴만으로 "입력 불필요" 항목을 판정한다.

검증된 3건(supervision_forms_final.json)에서 Claude Code 세션이 직접
읽고 판단한 134개 필드 중 ai_fillable=false 사례들을 관찰해서 뽑아낸
안전한 구문 패턴만 사용한다. 애매한 경우(구획 제목 vs 데이터)는
추측하지 않고 그대로 둔다 - "근거 없으면 제외" 원칙과 동일하게,
여기서는 "근거 없으면 판정 보류(기존 유지)".

대상: docs/specifications/{prefix}_spec.json (기본: construction_clean)
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

# ── 안전한 패턴 (오탐 위험 낮음) ──────────────────────────────────────
BOILERPLATE_RE = re.compile(
    r'(신청합니다|통보합니다|제출합니다|신고합니다|따라\s*위와\s*같이|포함합니다\)?$)'
)
RECIPIENT_RE = re.compile(
    r'(귀하$|장\s*귀하|본부장|소방서장|시장·|시장ㆍ|구청장|한국\S{0,10}(원장|기술원))'
)
PAPER_SIZE_RE = re.compile(r'\d+\s*[㎜mm]+\s*[×xX]\s*\d+\s*[㎜mm]+')
FEE_NOTICE_RE = re.compile(r'수수료\s*없\s*음')
UNIT_ONLY_RE = re.compile(r'^[㎡ℓ㎜@%℃]+$')  # 단위기호 단독 (설명 텍스트 없음)


def classify_pattern(text: str):
    """(is_false, reason) - False 판정 사유가 없으면 (None, None) = 판단 보류"""
    t = text.strip()
    if not t:
        return None, None
    if BOILERPLATE_RE.search(t):
        return True, 'boilerplate_sentence'
    if RECIPIENT_RE.search(t):
        return True, 'recipient_line'
    if PAPER_SIZE_RE.search(t):
        return True, 'paper_size_notice'
    if FEE_NOTICE_RE.search(t):
        return True, 'fee_notice'
    if UNIT_ONLY_RE.match(t):
        return True, 'unit_symbol_only'
    return None, None


REASON_TEXT = {
    'boilerplate_sentence': 'ℹ️ 법령 근거를 밝히는 정형 신청 문구입니다. 수정하지 않습니다.',
    'recipient_line': 'ℹ️ 제출받을 기관(수신처) 표시입니다. 편집 대상이 아닙니다.',
    'paper_size_notice': 'ℹ️ 제출용 용지 규격 안내입니다. 편집 대상이 아닙니다.',
    'fee_notice': 'ℹ️ 수수료 안내 문구입니다. 편집 대상이 아닙니다.',
    'unit_symbol_only': 'ℹ️ 단위 기호입니다. 옆/앞 칸에 입력한 값의 단위 표시로, 별도 입력 대상이 아닙니다.',
}


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else 'construction_clean'
    spec_path = Path(f"docs/specifications/{prefix}_spec.json")

    spec = json.loads(spec_path.read_text(encoding='utf-8'))

    total_fields = 0
    flagged = Counter()

    for form in spec.values():
        for field in form['fields']:
            total_fields += 1
            if 'ai_fillable' in field:
                continue  # 이미 세션이 직접 판단한 필드(검증된 3건)는 건드리지 않음

            is_false, reason = classify_pattern(field['field_name'])
            if is_false:
                field['ai_fillable'] = False
                field['ai_guidance'] = REASON_TEXT[reason]
                field['pattern_reason'] = reason
                flagged[reason] += 1
            # 판단 보류: ai_fillable 필드를 아예 추가하지 않음(기존 guidance 유지)

    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')

    print("=" * 70)
    print(f"패턴 기반 '입력 불필요' 판정 (API 미호출, 토큰 0)")
    print("=" * 70)
    print(f"전체 필드: {total_fields}개")
    print(f"판정됨(입력 불필요): {sum(flagged.values())}개")
    for reason, count in flagged.most_common():
        print(f"  - {reason}: {count}개")
    print(f"판단 보류(기존 유지): {total_fields - sum(flagged.values())}개")
    print(f"\n💾 저장: {spec_path}")


if __name__ == '__main__':
    main()
