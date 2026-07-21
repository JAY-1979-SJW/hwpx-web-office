/* upload_controller — HWPX 업로드 / 샘플 로드 → 서버 파싱 응답 처리.
 *
 * 브라우저는 HWPX XML 을 직접 파싱하지 않는다(백엔드가 파싱). 여기서는
 * multipart 업로드 / sourcePath 로드만 담당한다.
 */
const UPLOAD_ENDPOINT = "/api/web-office/hwpx-upload";
const LOAD_ENDPOINT = "/api/web-office/hwpx-load";

export function createUploadController({ onLoaded, setStatus }) {
  function applyEnvelope(env) {
    const d = (env && env.data) || env || {};
    const failed = (env && env.status && env.status !== "SUCCESS")
      || d.verdict !== "PASS";
    if (failed) {
      const msg = (env.errors && env.errors[0] && env.errors[0].message)
        || d.reason || "UNKNOWN";
      setStatus("fail", "로드 실패: " + msg);
      return;
    }
    onLoaded(d);
  }
  return {
    async upload(file) {
      if (!file) return;
      if (!/\.hwpx$/i.test(file.name)) {
        setStatus("fail", "HWPX 파일만 가능합니다.");
        return;
      }
      setStatus("load", "업로드 중: " + file.name + " …");
      const fd = new FormData();
      fd.append("file", file);
      try {
        const res = await fetch(UPLOAD_ENDPOINT, { method: "POST", body: fd });
        applyEnvelope(await res.json());
      } catch (e) {
        setStatus("fail", "업로드 실패: " + e.message);
      }
    },
    async loadSample(sourcePath) {
      setStatus("load", "샘플 로드 중 …");
      try {
        const res = await fetch(LOAD_ENDPOINT, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            operation: "HWPX_EDITOR_LOAD", sourcePath,
          }),
        });
        applyEnvelope(await res.json());
      } catch (e) {
        setStatus("fail", "샘플 로드 실패: " + e.message);
      }
    },
  };
}
