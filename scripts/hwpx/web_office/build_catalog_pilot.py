#!/usr/bin/env python3
"""
카탈로그 시범 파이프라인 (100건)
- 기존 3단계 스크립트(HwpxParser / extract_fields / render_form_html)를
  그대로 재사용해서 카탈로그 파일 N건에 일괄 적용한다.
- 서식별 하드코딩 없음: 파일 목록만 바뀌면 그대로 재사용 가능.
- 입력 필드 0개인 '죽은 서식'도 목차/폼에 전부 포함 (필드 없음 안내 표시).

출력:
  data/cache/catalog_pilot_parsed.json         (파싱 원본 - 좌표/문단)
  docs/specifications/catalog_pilot_spec.json  (검증된 필드 기준서)
  forms_catalog/<문서명>.html                   (문서별 웹 폼)
  forms_catalog/index.html                      (전체 목차)
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from parse_supervision_forms import HwpxParser  # noqa: E402
from generate_forms_specification import extract_fields  # noqa: E402
from generate_html_forms import render_form_html, render_index_html, slugify_filename  # noqa: E402

import os

SAMPLE_SIZE = int(os.environ.get("PILOT_SAMPLE_SIZE", "100"))
KEYWORDS = [k for k in os.environ.get("PILOT_KEYWORDS", "").split(",") if k]
FILE_LIST = os.environ.get("PILOT_FILE_LIST", "")
FORM_LIBRARY = Path("data/drafts/form_library")
OUT_PREFIX = os.environ.get("PILOT_OUT_PREFIX", "catalog_pilot")
PARSED_CACHE = Path(f"data/cache/{OUT_PREFIX}_parsed.json")
SPEC_OUTPUT = Path(f"docs/specifications/{OUT_PREFIX}_spec.json")
FORMS_DIR = Path(os.environ.get("PILOT_FORMS_DIR", "forms_catalog"))


def derive_form_name(filename_stem: str) -> str:
    """파일명에서 사람이 읽을 문서명 추출: 해시프리픽스/번호코드 제거"""
    # "0393790f0e_16b6afa1e14849fc_02910_045_[별지_제22호의3서식]_공사_감리자_지정_신청서"
    # -> 대괄호 [..] 뒤부터가 실제 서식명인 경우가 많음
    m = re.search(r'\[[^\]]+\]_(.+)$', filename_stem)
    if m:
        name = m.group(1)
    else:
        # 대괄호 없으면 마지막 해시/숫자 코드 이후 부분 사용, 없으면 전체
        parts = filename_stem.split('_')
        name = '_'.join(p for p in parts if not re.fullmatch(r'[0-9a-f]{8,}|\d{3,5}|\d{3}', p))
        name = name or filename_stem

    name = name.replace('__A', '').replace('__filled', '')
    name = re.sub(r'_+', ' ', name).strip()
    return name or filename_stem


def main():
    if FILE_LIST:
        lines = Path(FILE_LIST).read_text(encoding='utf-8').splitlines()
        all_files = [Path(line.strip()) for line in lines if line.strip()]
    else:
        all_files = sorted(FORM_LIBRARY.glob("*.hwpx"))
        if KEYWORDS:
            all_files = [f for f in all_files if any(kw in f.name for kw in KEYWORDS)]
    files = all_files[:SAMPLE_SIZE]
    print(f"🏗️  카탈로그 시범 파이프라인: {len(files)}건 처리 시작 (목록: {FILE_LIST or KEYWORDS or '없음'})\n")

    parsed_all = {}
    spec_all = {}
    index_entries = []

    zero_field_count = 0

    for i, file_path in enumerate(files, 1):
        doc_id = file_path.stem
        form_name = derive_form_name(doc_id)

        parser = HwpxParser(str(file_path))
        parsed = parser.parse()

        if 'error' in parsed:
            print(f"[{i:3d}/{len(files)}] ❌ {form_name[:40]:40s} 파싱오류: {parsed['error']}")
            continue

        parsed_all[doc_id] = {
            'form_name': form_name,
            'file': file_path.name,
            'total_rows': parsed['total_rows'],
            'total_cells': parsed['total_cells'],
            'cells': parsed['cells'],
        }

        fields = extract_fields(doc_id, {'cells': parsed['cells']})

        form_spec = {
            'form_id': doc_id,
            'form_name': form_name,
            'icon': '📄',
            'total_fields': len(fields),
            'fields': fields,
        }
        spec_all[doc_id] = form_spec

        if len(fields) == 0:
            zero_field_count += 1

        filename = slugify_filename(form_name) + f"_{doc_id[:8]}.html"
        storage_key = f"catalog_{doc_id[:8]}_data"
        html = render_form_html(doc_id, form_spec, storage_key)
        FORMS_DIR.mkdir(exist_ok=True)
        (FORMS_DIR / filename).write_text(html, encoding='utf-8')

        index_entries.append({
            'file': filename,
            'name': form_name,
            'icon': '📄' if fields else '⚪',
            'count': len(fields),
        })

        status = f"필드 {len(fields)}개" if fields else "필드 없음"
        print(f"[{i:3d}/{len(files)}] ✓ {form_name[:40]:40s} {status}")

    PARSED_CACHE.parent.mkdir(parents=True, exist_ok=True)
    PARSED_CACHE.write_text(json.dumps(parsed_all, ensure_ascii=False, indent=2), encoding='utf-8')

    SPEC_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    SPEC_OUTPUT.write_text(json.dumps(spec_all, ensure_ascii=False, indent=2), encoding='utf-8')

    (FORMS_DIR / 'index.html').write_text(render_index_html(index_entries), encoding='utf-8')

    print("\n" + "=" * 70)
    print(f"✅ 완료: {len(index_entries)}건 처리 (필드 있음 {len(index_entries)-zero_field_count}건 / 필드 없음 {zero_field_count}건)")
    print(f"   파싱 캐시: {PARSED_CACHE}")
    print(f"   기준서:    {SPEC_OUTPUT}")
    print(f"   웹 폼:     {FORMS_DIR}/ ({len(index_entries)}개 파일 + index.html)")


if __name__ == '__main__':
    main()
