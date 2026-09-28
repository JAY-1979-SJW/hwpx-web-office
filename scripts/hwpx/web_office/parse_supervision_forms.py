#!/usr/bin/env python3
"""
감리 서류 파싱 및 메타데이터 추출 (셀주소 정확판)
- form_331: 공사 감리자 지정 신청서
- form_99:  소방시설공사 완공검사신청서
- form_57:  옥외탱크저장소 구조안전점검시기 연장신청서

핵심 수정: HWPX의 <hp:tc> 셀은 순서가 아니라 <hp:cellAddr colAddr rowAddr>
(0-based 실좌표)와 <hp:cellSpan colSpan rowSpan>(병합 정보)를 갖고 있다.
이전 스크립트는 이를 무시하고 셀 등장 순번으로 열 문자를 계산해서,
병합 셀이 있는 행에서는 실제 셀 주소가 전부 어긋났다.
"""

import json
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Any

NS_P = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'


def col_to_letter(col_idx0: int) -> str:
    """0-based 열 인덱스를 Excel 열 문자로 변환 (0->A, 1->B, ...)"""
    n = col_idx0 + 1
    address = ''
    while n > 0:
        n -= 1
        address = chr(ord('A') + n % 26) + address
        n //= 26
    return address


class HwpxParser:
    """HWPX 파일 파싱 클래스 (cellAddr/cellSpan 기반 정확 파싱)"""

    def __init__(self, hwpx_path: str):
        self.hwpx_path = Path(hwpx_path)
        self.cells = []       # 모든 셀 (텍스트 유무 무관)
        self.total_rows = 0

    def parse(self) -> Dict[str, Any]:
        if not self.hwpx_path.exists():
            raise FileNotFoundError(f"파일 없음: {self.hwpx_path}")

        try:
            with zipfile.ZipFile(self.hwpx_path, 'r') as z:
                xml_data = z.read('Contents/section0.xml')

            root = ET.fromstring(xml_data)

            tables = root.findall(f'.//{NS_P}tbl')
            if tables:
                self._parse_table(tables[0])

            non_empty = [c for c in self.cells if c['text']]

            return {
                'form_path': str(self.hwpx_path),
                'form_file': self.hwpx_path.name,
                'total_rows': self.total_rows,
                'total_cells': len(self.cells),
                'total_fields': len(non_empty),
                'cells': self.cells,       # 전체 맥락(빈 칸 포함) - 인접 라벨 조회용
                'fields': non_empty,       # 텍스트 있는 셀만
            }

        except Exception as e:  # noqa: BLE001 -- 이 단계만 기록 후 계속
            return {
                'error': str(e),
                'form_path': str(self.hwpx_path),
                'form_file': self.hwpx_path.name,
            }

    def _parse_table(self, table_elem):
        # 직계 자식 tr만 사용 - './/'(하위 전체 탐색)를 쓰면 셀 안에 중첩된
        # 하위 표(nested tbl)의 tr까지 섞여 들어와 cellAddr가 서로 다른 좌표계인데도
        # 뒤섞여 같은 주소(A1 등)가 중복되는 좌표 충돌이 발생한다.
        rows = table_elem.findall(f'{NS_P}tr')
        self.total_rows = len(rows)

        max_row0 = 0

        for tr in rows:
            tcs = tr.findall(f'{NS_P}tc')
            for tc in tcs:
                cell_addr = tc.find(f'{NS_P}cellAddr')
                cell_span = tc.find(f'{NS_P}cellSpan')

                if cell_addr is None:
                    continue  # cellAddr 없는 셀은 실제 데이터 셀이 아님(무시)

                col_addr0 = int(cell_addr.get('colAddr', '0'))
                row_addr0 = int(cell_addr.get('rowAddr', '0'))
                col_span = int(cell_span.get('colSpan', '1')) if cell_span is not None else 1
                row_span = int(cell_span.get('rowSpan', '1')) if cell_span is not None else 1

                max_row0 = max(max_row0, row_addr0)

                paragraphs = self._extract_cell_paragraphs(tc)
                text = ' '.join(p.strip() for p in paragraphs if p.strip())
                col_letter = col_to_letter(col_addr0)
                row_num = row_addr0 + 1  # 1-based로 표기 (엑셀 스타일)

                # 구조적 근거: 문단이 2개 이상이고, 첫 문단 이후에 공백 5칸 이상 연속된
                # 문단이 있으면 "라벨+필기공간 결합형" 셀로 판정 (추측이 아니라 XML 구조 근거)
                embedded = False
                if len(paragraphs) >= 2:
                    for p in paragraphs[1:]:
                        if '     ' in p:  # 5칸 이상 연속 공백
                            embedded = True
                            break

                self.cells.append({
                    'cell': f"{col_letter}{row_num}",
                    'row': row_num,
                    'col': col_addr0 + 1,       # 1-based 열 번호
                    'col_addr0': col_addr0,     # 0-based 원본 좌표(디버그용)
                    'row_addr0': row_addr0,
                    'col_span': col_span,
                    'row_span': row_span,
                    'text': text.strip(),
                    'para_count': len(paragraphs),
                    'embedded_write_space': embedded,
                    'paragraphs': [p.strip() for p in paragraphs],
                })

        # cellAddr 기준 row_addr0 최댓값+1이 실제 논리 행 수 (tr 개수와 다를 수 있음: 병합 때문)
        self.total_rows = max_row0 + 1

    def _extract_cell_paragraphs(self, cell_elem) -> List[str]:
        """셀 안의 문단들을 원문 그대로(공백 보존) 리스트로 반환"""
        paragraphs = cell_elem.findall(f'.//{NS_P}p')
        return [''.join(p.itertext()) for p in paragraphs]


def parse_supervision_forms():
    """3개 감리 문서 파싱"""

    form_library = Path(__file__).parent.parent.parent.parent / "data" / "drafts" / "form_library"

    forms = {
        '331': {
            'name': '공사 감리자 지정 신청서',
            'file': '0393790f0e_16b6afa1e14849fc_02910_045_[별지_제22호의3서식]_공사_감리자_지정_신청서.hwpx'
        },
        '99': {
            'name': '소방시설공사 완공검사신청서',
            'file': '022e3f35e6_6ff3fe63f13a8199_01076_035_[별지_제17호서식]_소방시설공사_완공검사신청서__A.hwpx'
        },
        '57': {
            'name': '특정ㆍ준특정옥외탱크저장소 구조안전점검시기 연장신청서',
            'file': '035e67fa92_7e0e56c15d7fecd8_01315_072_[별지_제41호서식]_특정ㆍ준특정옥외탱크저장소의_구조안전점검시기_연장신청서(위험물의_저장관리_등의_상황).hwpx'
        }
    }

    results = {}

    for form_id, form_info in forms.items():
        file_path = form_library / form_info['file']

        print(f"\n📄 파싱 중: form_{form_id} ({form_info['name']})")
        print(f"   파일: {file_path.name}")

        if not file_path.exists():
            print("   ❌ 파일 없음")
            results[form_id] = {'error': 'File not found'}
            continue

        parser = HwpxParser(str(file_path))
        result = parser.parse()

        if 'error' in result:
            print(f"   ❌ 파싱 오류: {result['error']}")
            results[form_id] = result
            continue

        results[form_id] = {
            'form_id': int(form_id),
            'form_name': form_info['name'],
            'total_rows': result['total_rows'],
            'total_cells': result['total_cells'],
            'total_fields': result['total_fields'],
            'cells': result['cells'],
            'fields': result['fields'],
            'note': 'cellAddr/cellSpan 기반 정확 파싱 (병합 셀 반영)',
        }

        print(f"   ✓ 전체 셀: {result['total_cells']}개, 텍스트 있는 셀: {result['total_fields']}개, 논리 행: {result['total_rows']}행")

    return results


def save_metadata(data: Dict, output_path: str):
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with Path(output).open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 메타데이터 저장: {output}")


if __name__ == '__main__':
    print("=" * 60)
    print("🏗️  감리 서류 파싱 (cellAddr/cellSpan 기반 정확판)")
    print("=" * 60)

    metadata = parse_supervision_forms()

    cache_dir = Path(__file__).parent.parent.parent.parent / "data" / "cache"
    output_path = cache_dir / "supervision_complete_guides_parsed.json"
    save_metadata(metadata, str(output_path))

    print("\n" + "=" * 60)
    print("📊 파싱 결과 요약")
    print("=" * 60)
    for form_id, data in metadata.items():
        if 'error' not in data:
            print(f"form_{form_id}: 셀 {data['total_cells']}개 (텍스트 {data['total_fields']}개), 행 {data['total_rows']}행")
        else:
            print(f"form_{form_id}: ❌ {data['error']}")
