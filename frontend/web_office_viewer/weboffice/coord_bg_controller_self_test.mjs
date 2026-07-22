#!/usr/bin/env node
/* coord_bg_controller self-test — 배경 레이어 토글/캐시/폴백 불변식.
 *
 * 실 DOM/네트워크 없이 fake element + 주입 fetch 로 검증. 실패 시 비-0.
 */
import { createCoordBgController } from "./coord_bg_controller.mjs";

function assert(cond, msg) {
  if (!cond) { console.error("ASSERT FAIL:", msg); process.exit(1); }
}

function fakeEl() {
  return {
    hidden: false, innerHTML: "",
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
  };
}

const checks = {};

// 유효 레이아웃 응답을 반환하는 fetch (호출 횟수 집계)
function okFetch(counter) {
  return async () => {
    counter.n += 1;
    return {
      json: async () => ({
        status: "SUCCESS",
        data: {
          verdict: "PASS", pages: 1,
          pageWidthPx: 400, pageHeightPx: 600,
          lines: [{ text: "가", x: 0, y: 0, w: 10, h: 12,
                    segments: [{ text: "가", charPr: "1" }] }],
          boxes: [],
          charPrDefs: { "1": { fontName: "함초롬바탕", fontSizePt: 10 } },
        },
      }),
    };
  };
}

// 1) 토글 ON → fetch 1회, 레이어 표시 + 캔버스 wo-bg 부여
{
  const canvas = fakeEl(), layer = fakeEl();
  layer.hidden = true;
  const counter = { n: 0 };
  const c = createCoordBgController({
    canvas, layer, fetchImpl: okFetch(counter),
  });
  c.setSource("a.hwpx");
  await c.toggle(true);
  assert(counter.n === 1, "fetch called once on enable");
  assert(layer.hidden === false, "layer shown");
  assert(layer.innerHTML.includes("co-line"), "coord html rendered");
  assert(canvas.classList.contains("wo-bg"), "canvas got wo-bg");
  assert(c.isEnabled() === true, "enabled");
  checks.enable = true;

  // 2) 같은 source refresh → 캐시 사용(추가 fetch 없음)
  await c.refresh();
  assert(counter.n === 1, "cached, no extra fetch on same source");
  checks.cache = true;

  // 3) 토글 OFF → 레이어 숨김 + wo-bg 제거
  await c.toggle(false);
  assert(layer.hidden === true, "layer hidden on disable");
  assert(!canvas.classList.contains("wo-bg"), "wo-bg removed");
  checks.disable = true;

  // 4) source 변경 → 캐시 무효화, 다시 fetch
  c.setSource("b.hwpx");
  await c.toggle(true);
  assert(counter.n === 2, "new source triggers refetch");
  checks.sourceChange = true;
}

// 5) 레이아웃 실패 → 폴백(숨김·비활성·상태 fail), 예외 전파 안 함
{
  const canvas = fakeEl(), layer = fakeEl();
  let statusK = null;
  const c = createCoordBgController({
    canvas, layer,
    setStatus: (k) => { statusK = k; },
    fetchImpl: async () => ({
      json: async () => ({ status: "SUCCESS",
        data: { verdict: "REJECTED", reason: "NOT_HWPX" } }),
    }),
  });
  c.setSource("bad.hwpx");
  await c.toggle(true);
  assert(layer.hidden === true, "layer hidden on failure");
  assert(!canvas.classList.contains("wo-bg"), "no wo-bg on failure");
  assert(c.isEnabled() === false, "disabled on failure");
  assert(statusK === "fail", "status set to fail");
  checks.failFallback = true;
}

console.log(JSON.stringify({
  task: "HWPX-COORD-BG-CONTROLLER-SELFTEST", checks, verdict: "PASS",
}));
