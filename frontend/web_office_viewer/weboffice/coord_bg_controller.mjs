/* coord_bg_controller — 편집 앱의 "원본 배치" 배경 레이어.
 *
 * 편집 흐름(.wo-sheet) 뒤에 한컴 lineseg 좌표 기반 faithful 렌더를 ghost
 * 배경으로 깔아, 편집 중에도 원본 문자 위치·서식을 참조할 수 있게 한다.
 * read-only. 좌표 레이어는 pointer-events:none 이라 편집 클릭을 막지 않는다.
 *
 * 위치·서식은 coordinate_layout(백엔드) + coordinate_renderer(프론트) 를
 * 그대로 재사용한다 — 편집 로직/DOM 무접촉.
 */
import { renderCoordinateLayout } from "./coordinate_renderer.mjs";

const LAYOUT_ENDPOINT = "/api/web-office/hwpx-layout";

/* deps:
 *   canvas    : .wo-canvas (position:relative 컨테이너)
 *   layer     : .wo-coord  (배경 렌더 타깃, pointer-events:none)
 *   setStatus : (k, msg) => void  (상태줄; 선택)
 *   fetchImpl : fetch 주입(테스트용; 기본 globalThis.fetch)
 */
export function createCoordBgController(deps = {}) {
  const { canvas, layer, setStatus } = deps;
  const doFetch = deps.fetchImpl
    || ((...a) => globalThis.fetch(...a));

  let sourcePath = null;
  let enabled = false;
  let cacheKey = null;   // 렌더 캐시가 유효한 sourcePath
  let cacheHtml = null;

  async function fetchLayout(sp) {
    const res = await doFetch(LAYOUT_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sourcePath: sp }),
    });
    const env = await res.json();
    const d = (env && env.data) || env || {};
    if ((env && env.status && env.status !== "SUCCESS")
      || d.verdict === "REJECTED" || d.error) {
      throw new Error((env && env.errors && env.errors[0]
        && env.errors[0].code) || d.reason || d.error || "LAYOUT_FAILED");
    }
    return d;
  }

  function hide() {
    if (layer) layer.hidden = true;
    if (canvas) canvas.classList.remove("wo-bg");
  }

  async function render() {
    if (!enabled || !sourcePath) { hide(); return; }
    if (cacheKey !== sourcePath) {
      if (setStatus) setStatus("load", "원본 배치 배경 생성 중 …");
      try {
        const layout = await fetchLayout(sourcePath);
        cacheHtml = renderCoordinateLayout(layout);
        cacheKey = sourcePath;
        if (setStatus) setStatus("ok",
          `원본 배치 배경 · ${layout.pages}p · ${(layout.lines || []).length}줄`
          + " · 편집은 위 흐름에서");
      } catch (e) {
        enabled = false;
        hide();
        if (setStatus) setStatus("fail", "배경 생성 실패: " + e.message);
        return;
      }
    }
    if (layer) { layer.innerHTML = cacheHtml; layer.hidden = false; }
    if (canvas) canvas.classList.add("wo-bg");
  }

  return {
    /* 새 문서 로드 시 호출 — sourcePath 가 바뀌면 캐시 무효화. */
    setSource(sp) {
      if (sp !== sourcePath) {
        sourcePath = sp || null;
        cacheKey = null;
        cacheHtml = null;
      }
    },
    /* 토글 on/off. */
    async toggle(on) { enabled = !!on; await render(); },
    /* 로드 후 현재 상태로 재적용(토글 유지). */
    async refresh() { await render(); },
    isEnabled() { return enabled; },
  };
}
