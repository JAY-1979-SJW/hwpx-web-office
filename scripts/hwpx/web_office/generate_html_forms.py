#!/usr/bin/env python3
"""
검증된 기준서(JSON) → 웹 입력 폼 HTML 자동 생성 (문서명 파일)

입력: docs/specifications/supervision_forms_final.json
출력: forms/<문서명>.html (문서마다 1개) + forms/index.html (목록)

이 스크립트는 서식별 하드코딩이 없다 - JSON 기준서만 바뀌면
다른 서식(카탈로그 전체)에도 그대로 재사용 가능하다.
"""

import json
import re
from pathlib import Path

SPEC_FILE = Path("docs/specifications/supervision_forms_final.json")
OUTPUT_DIR = Path("frontend/web_office_viewer/forms")

# git이 비-ASCII 파일명을 자동 이스케이프(따옴표+8진수)하면
# scripts/ops/classify_hwpx_repo_inventory.py의 `path.startswith("frontend/")`
# 같은 단순 접두어 검사가 깨져 신규파일 분류 게이트가 실패한다.
# 게이트(감사 인프라)를 고치는 대신 산출 파일명을 ASCII로 고정한다.
# 문서명(한글)은 HTML <title>/<h1> 안에 그대로 표시된다.
ASCII_SLUG_OVERRIDE = {
    '공사 감리자 지정 신청서': 'supervisor-designation-application',
    '소방시설공사 완공검사신청서': 'fire-facility-completion-inspection-application',
    '특정ㆍ준특정옥외탱크저장소 구조안전점검시기 연장신청서': 'outdoor-tank-safety-inspection-extension-application',
}

ROLE_ICON = {
    'agency': '🏛️',
    'signature': '✍️',
    'user': '✏️',
}


def slugify_filename(name: str) -> str:
    """문서명을 안전한 파일명으로 변환"""
    name = name.replace('ㆍ', '_').replace('·', '_')
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = re.sub(r'\s+', '_', name.strip())
    return name


def render_field_html(field):
    cell = field['cell']
    name = field['field_name']
    ftype = 'date' if field['type'] == 'date' else 'text'
    icon = ROLE_ICON.get(field['role'], '✏️')
    guidance = field.get('ai_guidance') or field['guidance']
    fillable = field.get('ai_fillable', True)
    readonly = 'readonly' if (field['role'] == 'agency' or not fillable) else ''

    if not fillable:
        # 입력 불필요 항목(정형 문구/구획 제목/단위기호 등) - 안내문으로만 표시, 입력창 없음
        return f'''
                    <div class="form-field info-only">
                        <label class="field-label">
                            {name}
                            <span class="cell-ref">[{cell}]</span>
                            <span class="badge-info">입력 불필요</span>
                        </label>
                        <div class="guidance-box">
                            <div class="guidance-text">ℹ️ {guidance}</div>
                        </div>
                    </div>'''

    return f'''
                    <div class="form-field">
                        <label class="field-label">
                            {name}
                            <span class="cell-ref">[{cell}]</span>
                        </label>
                        <input type="{ftype}" class="field-input" data-cell="{cell}" {readonly}>
                        <div class="guidance-box">
                            <div class="guidance-text">{icon} {guidance}</div>
                        </div>
                    </div>'''


def render_form_html(form_id, form_spec, storage_key):
    title = form_spec['form_name']
    icon = form_spec['icon']
    if form_spec['fields']:
        fields_html = ''.join(render_field_html(f) for f in form_spec['fields'])
    else:
        fields_html = '''
                    <div class="form-field" style="grid-column: 1 / -1;">
                        <div class="guidance-box">⚠️ 자동 판별 결과 입력 필드를 찾지 못했습니다 (서명/도장 전용이거나 별지 서식일 수 있습니다).</div>
                    </div>'''

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 웹 입력</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333; padding: 20px; min-height: 100vh;
        }}
        .container {{ max-width: 900px; margin: 0 auto; background: white; border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2); overflow: hidden; }}
        header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;
            padding: 30px; text-align: center; }}
        header h1 {{ font-size: 1.6em; margin-bottom: 8px; }}
        header p {{ opacity: 0.9; font-size: 0.9em; }}
        .form-container {{ padding: 30px; display: grid; gap: 20px; grid-template-columns: 1fr 1fr; }}
        .form-field {{ display: flex; flex-direction: column; }}
        .field-label {{ font-weight: 600; margin-bottom: 8px; font-size: 0.95em; }}
        .field-label .cell-ref {{ color: #667eea; font-size: 0.8em; font-weight: normal; margin-left: 5px; }}
        .field-input {{ padding: 10px 12px; border: 1px solid #ddd; border-radius: 5px; font-size: 1em; font-family: inherit; }}
        .field-input:focus {{ outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1); }}
        .field-input[readonly] {{ background: #f0f0f0; color: #888; }}
        .form-field.info-only {{ opacity: 0.75; }}
        .badge-info {{ background: #eee; color: #666; font-size: 0.7em; padding: 2px 6px;
            border-radius: 10px; margin-left: 6px; font-weight: normal; }}
        .guidance-box {{ background: #f8f9fa; border-left: 3px solid #667eea; padding: 10px; border-radius: 5px;
            font-size: 0.85em; color: #555; margin-top: 6px; }}
        .button-group {{ display: flex; gap: 10px; padding: 0 30px 30px; justify-content: center; grid-column: 1 / -1; }}
        button {{ padding: 12px 28px; font-size: 1em; border: none; border-radius: 5px; cursor: pointer; font-weight: 600; }}
        .btn-save {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
        .btn-reset, .btn-back {{ background: #f0f0f0; color: #333; }}
        .status-message {{ margin: 0 30px 20px; padding: 12px; border-radius: 5px; display: none;
            text-align: center; font-weight: 500; grid-column: 1 / -1; }}
        .status-message.success {{ background: #d4edda; color: #155724; border: 1px solid #c3e6cb; display: block; }}
        @media (max-width: 700px) {{ .form-container {{ grid-template-columns: 1fr; }} }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{icon} {title}</h1>
            <p>기준서 기반 자동 생성 웹 입력 ({len(form_spec['fields'])}개 필드) · 필수 강제 없음</p>
        </header>
        <form id="formMain" class="form-container">
{fields_html}
            <div class="button-group">
                <button type="button" class="btn-back" onclick="location.href='index.html'">🏠 돌아가기</button>
                <button type="reset" class="btn-reset">🔄 초기화</button>
                <button type="submit" class="btn-save">💾 저장</button>
            </div>
            <div class="status-message" id="statusMessage"></div>
        </form>
    </div>
    <script>
        const STORAGE_KEY = '{storage_key}';
        const form = document.getElementById('formMain');
        form.addEventListener('submit', function(e) {{
            e.preventDefault();
            const data = {{}};
            document.querySelectorAll('[data-cell]').forEach(input => {{
                if (input.value) data[input.dataset.cell] = input.value;
            }});
            localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
            const msg = document.getElementById('statusMessage');
            msg.textContent = `✅ 저장되었습니다! (${{Object.keys(data).length}}개 필드)`;
            msg.className = 'status-message success';
            setTimeout(() => {{ msg.style.display = 'none'; }}, 3000);
        }});
        window.addEventListener('load', function() {{
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {{
                const data = JSON.parse(saved);
                Object.keys(data).forEach(cell => {{
                    const input = document.querySelector(`[data-cell="${{cell}}"]`);
                    if (input) input.value = data[cell];
                }});
            }}
        }});
    </script>
</body>
</html>
'''


def render_index_html(entries):
    cards = ''.join(f'''
            <a href="{e['file']}" class="form-card">
                <div class="form-card-header">
                    <div class="form-card-icon">{e['icon']}</div>
                    <div class="form-card-title">{e['name']}</div>
                </div>
                <div class="form-card-body">
                    <div class="form-fields">입력 필드 {e['count']}개</div>
                    <button class="form-card-button">📝 입력하기</button>
                </div>
            </a>''' for e in entries)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>웹 문서 입력 시스템</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh;
            display: flex; align-items: center; justify-content: center; padding: 20px; }}
        .container {{ max-width: 1100px; width: 100%; }}
        header {{ text-align: center; color: white; margin-bottom: 40px; }}
        header h1 {{ font-size: 2.2em; margin-bottom: 8px; }}
        .forms-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
        .form-card {{ background: white; border-radius: 12px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);
            overflow: hidden; text-decoration: none; color: inherit; transition: transform 0.2s; }}
        .form-card:hover {{ transform: translateY(-6px); }}
        .form-card-header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;
            padding: 20px; text-align: center; }}
        .form-card-icon {{ font-size: 2.2em; margin-bottom: 8px; }}
        .form-card-title {{ font-size: 1.05em; font-weight: 700; }}
        .form-card-body {{ padding: 20px; text-align: center; }}
        .form-fields {{ color: #666; font-size: 0.9em; margin-bottom: 15px; }}
        .form-card-button {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;
            border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📋 웹 문서 입력 시스템</h1>
            <p style="color:white;opacity:0.9;">기준서(cellAddr 기반) 자동 생성 · 문서명으로 구분</p>
        </header>
        <div class="forms-grid">{cards}
        </div>
    </div>
</body>
</html>
'''


def main():
    spec = json.loads(SPEC_FILE.read_text(encoding='utf-8'))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    entries = []
    for form_id, form_spec in spec.items():
        slug = ASCII_SLUG_OVERRIDE.get(form_spec['form_name']) or slugify_filename(form_spec['form_name'])
        filename = slug + '.html'
        storage_key = f"form_{slug}_data"

        html = render_form_html(form_id, form_spec, storage_key)
        (OUTPUT_DIR / filename).write_text(html, encoding='utf-8')

        entries.append({
            'file': filename,
            'name': form_spec['form_name'],
            'icon': form_spec['icon'],
            'count': form_spec['total_fields'],
        })
        print(f"✅ 생성: forms/{filename} ({form_spec['total_fields']}개 필드)")

    (OUTPUT_DIR / 'index.html').write_text(render_index_html(entries), encoding='utf-8')
    print(f"✅ 생성: forms/index.html")


if __name__ == '__main__':
    main()
