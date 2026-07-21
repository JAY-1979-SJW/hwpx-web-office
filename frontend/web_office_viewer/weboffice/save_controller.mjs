/* save_controller — sandbox 저장(+readback) 및 편집본 다운로드.
 *
 * save_apply_bridge(postCellSaveApply) 위. 원본 무수정, output 은 sandbox
 * 사본. writer 직접 호출 없음.
 */
import { postCellSaveApply } from "../save_apply_bridge.mjs";

export function createSaveController({ getState, getSourcePath }) {
  let lastOutput = null;
  return {
    async save() {
      const r = await postCellSaveApply({
        state: getState(),
        sourcePath: getSourcePath(),
        requestId: "wo-" + Date.now(),
      });
      if (r && r.status === "FAILED") {
        return {
          ok: false,
          code: (r.errors && r.errors[0] && r.errors[0].code) || "FAIL",
        };
      }
      const d = (r && r.data) || r || {};
      lastOutput = d.outputFileName || null;
      return { ok: true, output: lastOutput };
    },
    lastOutput: () => lastOutput,
    downloadUrl: () =>
      lastOutput
        ? "/api/web-office/download/" + encodeURIComponent(lastOutput)
        : null,
  };
}
