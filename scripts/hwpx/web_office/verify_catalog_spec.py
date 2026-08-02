#!/usr/bin/env python3
"""
기준서(spec) 전수 검증 - 알려진 오류 패턴을 모든 문서에 대해 자동 스캔.

검증 항목:
  1. field_name이 placeholder("(     )")나 도장 표시("(서명 또는 인)")인 채로
     남아있는가 - 추출 단계 필터가 뚫린 경우
  2. label_cell 중복 사용 - 같은 셀이 여러 필드의 라벨로 쓰였는가(모순)
  3. label_only 비율이 지나치게 높은 문서 - 구조적 근거가 거의 없어
     저신뢰 취급해야 하는 문서
  4. 필드 0개인데 원본 셀은 많은 문서 - 추출 실패 의심
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

STAMP_RE = re.compile(r'^\(\s*서명\s*(또는)?\s*인\s*\)$')
PLACEHOLDER_RE = re.compile(r'^\(\s*\)$')


def verify_spec(spec_path: Path, parsed_path: Path):
    spec = json.loads(spec_path.read_text(encoding='utf-8'))
    parsed = json.loads(parsed_path.read_text(encoding='utf-8')) if parsed_path.exists() else {}

    issues = []
    stats = Counter()

    for doc_id, form in spec.items():
        fields = form['fields']
        stats['total_docs'] += 1

        if not fields:
            total_cells = parsed.get(doc_id, {}).get('total_cells', 0)
            if total_cells > 15:
                issues.append({
                    'doc_id': doc_id, 'form_name': form['form_name'],
                    'type': 'zero_fields_but_has_cells',
                    'detail': f"셀 {total_cells}개인데 필드 0개 - 추출 실패 의심",
                })
            continue

        stats['docs_with_fields'] += 1

        # 1) 도장/placeholder 텍스트가 "다른 칸"의 라벨로 빌려 쓰였는가
        #    (kind가 label_only면 자기 자신을 필드화한 것이라 정상 - 서명칸 자체는 필드가 맞음.
        #     blank_cell/embedded인데 label_cell != cell 이면 남의 도장/placeholder를 빌린 오류)
        for f in fields:
            name = f['field_name'].strip()
            borrowed = f['label_cell'] != f['cell']
            if borrowed and STAMP_RE.match(name):
                issues.append({
                    'doc_id': doc_id, 'form_name': form['form_name'],
                    'type': 'stamp_leaked_as_label', 'cell': f['cell'],
                    'detail': f"[{f['cell']}]가 다른 칸의 도장 표시를 라벨로 빌려씀: '{name}' (label_cell={f['label_cell']})",
                })
            if borrowed and PLACEHOLDER_RE.match(name):
                issues.append({
                    'doc_id': doc_id, 'form_name': form['form_name'],
                    'type': 'placeholder_leaked_as_label', 'cell': f['cell'],
                    'detail': f"[{f['cell']}]가 다른 칸의 빈 placeholder를 라벨로 빌려씀: '{name}' (label_cell={f['label_cell']})",
                })

        # 2) label_cell 중복 사용 검사
        label_cells = [f['label_cell'] for f in fields]
        dup = [c for c, n in Counter(label_cells).items() if n > 1]
        if dup:
            issues.append({
                'doc_id': doc_id, 'form_name': form['form_name'],
                'type': 'duplicate_label_cell',
                'detail': f"같은 셀이 여러 필드 라벨로 중복 사용: {dup}",
            })

        # 3) label_only 비율
        kind_counts = Counter(f.get('kind', '?') for f in fields)
        label_only_ratio = kind_counts.get('label_only', 0) / len(fields)
        if label_only_ratio >= 0.9 and len(fields) >= 5:
            issues.append({
                'doc_id': doc_id, 'form_name': form['form_name'],
                'type': 'low_confidence_document',
                'detail': f"label_only 비율 {label_only_ratio:.0%} ({len(fields)}개 중) - 구조적 근거 낮음",
            })

    return issues, stats


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else 'construction_full'
    spec_path = Path(f"docs/specifications/{prefix}_spec.json")
    parsed_path = Path(f"data/cache/{prefix}_parsed.json")

    print(f"🔍 검증 대상: {spec_path}\n")
    issues, stats = verify_spec(spec_path, parsed_path)

    by_type = Counter(i['type'] for i in issues)

    print("=" * 80)
    print("📊 전수 검증 결과")
    print("=" * 80)
    print(f"전체 문서: {stats['total_docs']}건 (필드 있음 {stats['docs_with_fields']}건)")
    print(f"이슈 총: {len(issues)}건\n")
    for t, c in by_type.most_common():
        print(f"  {t}: {c}건")

    out_path = Path(f"data/reports/{prefix}_verification_issues.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(issues, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n💾 상세 이슈 저장: {out_path}")

    print("\n📋 샘플 (유형별 최대 3건):")
    seen_type = Counter()
    for i in issues:
        if seen_type[i['type']] >= 3:
            continue
        seen_type[i['type']] += 1
        print(f"  [{i['type']}] {i['form_name'][:30]} ({i['doc_id'][:12]}) - {i['detail']}")


if __name__ == '__main__':
    main()
