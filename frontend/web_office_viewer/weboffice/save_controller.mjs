/* save_controller — 검증(+readback) 후 원본 파일 직접 반영.
 *
 * save_apply_bridge(postCellSaveApply) 위. editInPlace 정책(2026-07-24,
 * 대표님 지시) — sandbox 산출물로 verify7 검증까지 마친 뒤 원본에
 * 덮어쓴다. writer 직접 호출 없음.
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
      // editInPlace 반영 후엔 sandbox 산출물이 삭제되므로(원본에 이미
      // 덮어씀) outputFileName 이 있어도 다운로드 대상이 아니다.
      lastOutput = d.editedInPlace ? null : (d.outputFileName || null);
      return { ok: true, output: lastOutput, editedInPlace: !!d.editedInPlace };
    },
    lastOutput: () => lastOutput,
    downloadUrl: () =>
      lastOutput
        ? "/api/web-office/download/" + encodeURIComponent(lastOutput)
        : null,
  };
}
