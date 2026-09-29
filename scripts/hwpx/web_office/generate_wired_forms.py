#!/usr/bin/env python3
"""
검증된 3건을 '진짜 저장 API'(cell-save-apply)와 실제로 연결된 웹 폼으로
생성한다.

이전 시도(generate_html_forms.py)는 제가 만든 cellAddr 파서의 좌표
("B4" 식)로 필드를 만들었는데, 실제 저장 백엔드(editor_file_bridge)는
자체 recognizedFields(cellId="cell_t_s0_000_r3_c1" 식)를 이미 갖고
있고 좌표 체계가 다르다(검증 완료 - 같은 문서에서 직접 비교). 그래서
이 스크립트는:
  1) 실제 백엔드를 불러(hwpx-load) recognizedFields를 가져오고
  2) 손수 작성한 AI 해설(supervision_forms_final.json)을 라벨 텍스트로
     매칭해 설명을 붙이고
  3) 저장 버튼이 실제 /api/web-office/cell-save-apply 를 호출하는
     HTML을 만든다.
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from hwpx.web_office.editor_file_bridge import load_hwpx_for_editor  # ruff: ignore[module-import-not-at-top-of-file]

SPEC_PATH = PROJECT_ROOT / "docs" / "specifications" / "supervision_forms_final.json"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "web_office_viewer" / "forms"
API_BASE = "http://127.0.0.1:8811"

DOCS = {
    "331": {
        "source": "data/drafts/form_library/0393790f0e_16b6afa1e14849fc_02910_045_[별지_제22호의3서식]_공사_감리자_지정_신청서.hwpx",
        "slug": "supervisor-designation-application-live",
        "icon": "📋",
    },
    "99": {
        "source": "data/drafts/form_library/022e3f35e6_6ff3fe63f13a8199_01076_035_[별지_제17호서식]_소방시설공사_완공검사신청서__A.hwpx",
        "slug": "fire-facility-completion-inspection-application-live",
        "icon": "🔥",
    },
    "57": {
        "source": "data/drafts/form_library/035e67fa92_7e0e56c15d7fecd8_01315_072_[별지_제41호서식]_특정ㆍ준특정옥외탱크저장소의_구조안전점검시기_연장신청서(위험물의_저장관리_등의_상황).hwpx",
        "slug": "outdoor-tank-safety-inspection-extension-application-live",
        "icon": "🏭",
    },
}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def build_guidance_index(fields: list) -> dict:
    idx = {}
    for f in fields:
        idx[norm(f["field_name"])] = f
        idx[norm(f.get("label_cell", ""))] = f  # 보조키(거의 안 씀)
    return idx


def render_field(f, guidance_field):
    label = f["label"]
    cell_id = f["cellId"]
    ftype = (
        "date" if f["fieldType"] == "date" else ("number" if f["fieldType"] == "number" else "text")
    )
    guidance = (guidance_field or {}).get("ai_guidance") or f.get("prompt", "")
    role = (guidance_field or {}).get("role", "user")
    icon = {"agency": "🏛️", "signature": "✍️", "user": "✏️"}.get(role, "✏️")
    readonly = "readonly" if role == "agency" else ""

    input_id = f"field-{cell_id}"
    return f'''
                <div class="form-field">
                    <label class="field-label" for="{input_id}">{label}
                        <span class="cell-ref">[{cell_id}]</span>
                    </label>
                    <input id="{input_id}" type="{ftype}" class="field-input" data-cell-id="{cell_id}" {readonly}>
                    <div class="guidance-box">{icon} {guidance}</div>
                </div>'''


def render_page(form_id, info, recognized_fields, guidance_idx, form_name):
    fields_html = ""
    matched = 0
    for f in recognized_fields:
        g = guidance_idx.get(norm(f["label"]))
        if g:
            matched += 1
        fields_html += render_field(f, g)

    return f'''<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{form_name} - 실시간 저장 연동</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
    background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); padding:20px; min-height:100vh; }}
.container {{ max-width:900px; margin:0 auto; background:white; border-radius:10px;
    box-shadow:0 10px 40px rgba(0,0,0,0.2); overflow:hidden; }}
header {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); color:white; padding:25px; text-align:center; }}
header h1 {{ font-size:1.5em; }}
.status-bar {{ padding:10px 20px; background:#fff3cd; color:#856404; font-size:0.85em; text-align:center; }}
.status-bar.ok {{ background:#d4edda; color:#155724; }}
.form-container {{ padding:25px; display:grid; gap:18px; grid-template-columns:1fr 1fr; }}
.form-field {{ display:flex; flex-direction:column; }}
.field-label {{ font-weight:600; margin-bottom:6px; font-size:0.92em; }}
.cell-ref {{ color:#999; font-size:0.7em; font-weight:normal; margin-left:5px; }}
.field-input {{ padding:9px 11px; border:1px solid #ddd; border-radius:5px; font-size:1em; }}
.field-input[readonly] {{ background:#f0f0f0; color:#888; }}
.guidance-box {{ background:#f8f9fa; border-left:3px solid #667eea; padding:8px 10px;
    border-radius:4px; font-size:0.82em; color:#555; margin-top:6px; }}
.button-group {{ grid-column:1/-1; display:flex; gap:10px; justify-content:center; padding-top:10px; }}
button {{ padding:11px 26px; border:none; border-radius:5px; cursor:pointer; font-weight:600; }}
.btn-save {{ background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); color:white; }}
.btn-back {{ background:#f0f0f0; }}
.result-box {{ grid-column:1/-1; padding:12px; border-radius:5px; display:none; font-size:0.9em; }}
.result-box.show {{ display:block; }}
.result-box.success {{ background:#d4edda; color:#155724; }}
.result-box.error {{ background:#f8d7da; color:#721c24; }}
@media (max-width:700px) {{ .form-container {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="container">
    <header><h1>{info["icon"]} {form_name}</h1><p style="opacity:0.9;font-size:0.85em;">실제 저장 API 연동 ({len(recognized_fields)}개 필드, 매칭 {matched}개)</p></header>
    <div class="status-bar" id="statusBar">🔌 문서 불러오는 중...</div>
    <form class="form-container" id="formMain">
{fields_html}
        <div class="button-group">
            <button type="button" class="btn-back" onclick="location.href='index.html'">🏠 돌아가기</button>
            <button type="submit" class="btn-save">💾 실제 문서에 저장</button>
        </div>
        <div class="result-box" id="resultBox"></div>
    </form>
</div>
<script>
const API_BASE = "{API_BASE}";
const SOURCE_PATH = {json.dumps(info["source"], ensure_ascii=False)};
let sourceDocumentHash = null;
let tableIndexById = {{}};

async function loadDoc() {{
    const res = await fetch(`${{API_BASE}}/api/web-office/hwpx-load`, {{
        method: 'POST', headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{operation:'HWPX_EDITOR_LOAD', sourcePath: SOURCE_PATH}})
    }});
    const env = await res.json();
    const statusBar = document.getElementById('statusBar');
    if (env.status !== 'SUCCESS') {{
        statusBar.textContent = '❌ 문서 로드 실패: ' + JSON.stringify(env.errors);
        return;
    }}
    const dm = env.data.documentModel;
    sourceDocumentHash = dm.sourceDocumentHash;
    dm.tables.forEach((t, i) => {{ tableIndexById[t.tableId] = i; }});
    // 현재 값으로 입력창 미리 채우기
    const cellById = {{}};
    dm.cells.forEach(c => {{ cellById[c.cellId] = c; }});
    document.querySelectorAll('[data-cell-id]').forEach(input => {{
        const c = cellById[input.dataset.cellId];
        if (c && c.text) input.value = c.text;
    }});
    statusBar.textContent = '✅ 문서 로드 완료 - 실제 저장 API에 연결됨';
    statusBar.classList.add('ok');
}}

function tableIdFromCellId(cellId) {{
    const m = cellId.match(/^cell_(.+)_r(\\d+)_c(\\d+)$/);
    if (!m) throw new Error('invalid cellId: ' + cellId);
    return {{ tableId: m[1], row: parseInt(m[2]), col: parseInt(m[3]) }};
}}

function uuid() {{
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {{
        const r = Math.random()*16|0, v = c==='x'?r:(r&0x3|0x8);
        return v.toString(16);
    }});
}}

document.getElementById('formMain').addEventListener('submit', async function(e) {{
    e.preventDefault();
    const resultBox = document.getElementById('resultBox');
    if (!sourceDocumentHash) {{
        resultBox.className = 'result-box show error';
        resultBox.textContent = '문서가 아직 로드되지 않았습니다.';
        return;
    }}
    const commands = [];
    document.querySelectorAll('[data-cell-id]:not([readonly])').forEach(input => {{
        const value = input.value.trim();
        if (!value) return;
        const {{tableId, row, col}} = tableIdFromCellId(input.dataset.cellId);
        const tableIndex = tableIndexById[tableId] ?? 0;
        const now = new Date().toISOString();
        commands.push({{
            commandId: uuid(), commandType: 'SET_CELL_TEXT',
            targetId: input.dataset.cellId, targetKind: 'cell',
            before: '', after: value, expectedBefore: '',
            forward: {{set_cells: [{{table: tableIndex, row, col, value}}]}},
            inverse: {{set_cells: [{{table: tableIndex, row, col, value: ''}}]}},
            createdAt: now, sourceDocumentHash, status: 'PENDING'
        }});
    }});
    if (!commands.length) {{
        resultBox.className = 'result-box show error';
        resultBox.textContent = '입력된 값이 없습니다.';
        return;
    }}
    const res = await fetch(`${{API_BASE}}/api/web-office/cell-save-apply`, {{
        method: 'POST', headers: {{'Content-Type':'application/json'}},
        body: JSON.stringify({{
            operation: 'CELL_SAVE_APPLY', sourcePath: SOURCE_PATH,
            sourceDocumentHash, commandLog: commands, dryRunOnly: false,
            editInPlace: false
        }})
    }});
    const env = await res.json();
    resultBox.classList.add('show');
    if (env.status === 'SUCCESS') {{
        resultBox.className = 'result-box show success';
        resultBox.textContent = `✅ 저장 완료! ${{commands.length}}개 필드 반영 (검증본: ${{env.data.outputFileName}})`;
    }} else {{
        resultBox.className = 'result-box show error';
        resultBox.textContent = '❌ 저장 실패: ' + JSON.stringify(env.errors);
    }}
}});

loadDoc();
</script>
</body>
</html>
'''


def main():
    spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
    entries = []

    for form_id, info in DOCS.items():
        result = load_hwpx_for_editor(
            {"operation": "HWPX_EDITOR_LOAD", "sourcePath": info["source"]},
            project_root=PROJECT_ROOT,
        )
        if result.get("verdict") != "PASS":
            print(f"❌ {form_id} 로드 실패: {result}")
            continue
        recognized = result["documentModel"]["recognizedFields"]
        guidance_idx = build_guidance_index(spec[form_id]["fields"])
        form_name = spec[form_id]["form_name"]

        html = render_page(form_id, info, recognized, guidance_idx, form_name)
        out_file = OUTPUT_DIR / f"{info['slug']}.html"
        out_file.write_text(html, encoding="utf-8")

        matched = sum(1 for f in recognized if norm(f["label"]) in guidance_idx)
        print(
            f"✅ {form_name}: recognizedFields {len(recognized)}개, AI해설 매칭 {matched}개 -> {out_file.name}"
        )
        entries.append({
            "slug": info["slug"],
            "name": form_name,
            "icon": info["icon"],
            "count": len(recognized),
        })

    return entries


if __name__ == "__main__":
    main()
