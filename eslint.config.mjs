import { defineConfig } from "eslint/config";
import globals from "globals";
import js from "@eslint/js";

// 이 프로젝트의 .mjs 파일은 두 갈래로 실행된다(2026-09-29 실측 확인):
// - 브라우저 런타임: HTML의 <script type="module">로 로드됨 → globals.browser
// - node 실행 스모크/셀프테스트: tests/*.py, scripts/ops/*.py 가 subprocess.run(["node", ...])로 직접 실행
//   → globals.node (여기서 쓰는 process.argv/process.exit 는 진짜 Node 전역이라 오탐 방지용)
const NODE_RUN_FILES = [
  "frontend/web_office_viewer/cell_edit_self_test.mjs",
  "frontend/web_office_viewer/form_question_panel_self_test.mjs",
  "frontend/web_office_viewer/format_charpr_matcher_smoke.mjs",
  "frontend/web_office_viewer/para_edit_apply_format_smoke.mjs",
  "frontend/web_office_viewer/para_edit_browser_self_test.mjs",
  "frontend/web_office_viewer/para_edit_ime_live_smoke.mjs",
  "frontend/web_office_viewer/para_edit_self_test.mjs",
  "frontend/web_office_viewer/para_edit_structure_smoke.mjs",
  "frontend/web_office_viewer/render_smoke.mjs",
  "frontend/web_office_viewer/runtime_smoke.mjs",
  "frontend/web_office_viewer/real_file_load_save_bridge_self_test.mjs",
  "frontend/web_office_viewer/weboffice/coord_bg_controller_self_test.mjs",
  "frontend/web_office_viewer/weboffice/coordinate_renderer_selftest.mjs",
];

// 이 코드베이스는 "의도적으로 안 쓰는 매개변수"를 _ev/_e 처럼 밑줄 접두어로
// 표시하는 관례를 이미 쓰고 있다(2026-09-29 확인: para_edit_runtime.mjs의
// onCompositionStart(state, _ev), weboffice/app.mjs의 여러 이벤트 핸들러 등).
// 개별 호출부를 rename하는 대신 그 관례를 규칙에 반영한다.
const NO_UNUSED_VARS_RULE = ["error", { argsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" }];

export default defineConfig([
  {
    files: ["frontend/web_office_viewer/**/*.mjs", "frontend/web_office_viewer/**/*.js"],
    ignores: NODE_RUN_FILES,
    languageOptions: { globals: globals.browser },
    plugins: { js },
    extends: ["js/recommended"],
    rules: { "no-unused-vars": NO_UNUSED_VARS_RULE },
  },
  {
    files: NODE_RUN_FILES,
    languageOptions: { globals: globals.node },
    plugins: { js },
    extends: ["js/recommended"],
    rules: { "no-unused-vars": NO_UNUSED_VARS_RULE },
  },
]);
