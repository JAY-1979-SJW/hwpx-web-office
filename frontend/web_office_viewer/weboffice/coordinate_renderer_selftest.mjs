#!/usr/bin/env node
/* coordinate_renderer self-test — 절대배치 렌더 불변식 검증. 실패 시 비-0. */
import { renderCoordinateLayout } from "./coordinate_renderer.mjs";

function assert(cond, msg) {
  if (!cond) { console.error("ASSERT FAIL:", msg); process.exit(1); }
}

const checks = {};

// 합성 레이아웃: 2페이지, 줄 3개(2페이지째 1개), 박스 2개(테두리 유/무)
const H = 1000;
const layout = {
  pageWidthPx: 800, pageHeightPx: H, pages: 2,
  lines: [
    { text: "가나 다라", x: 50, y: 60, w: 700, h: 20, cell: false },
    { text: "셀줄", x: 60, y: 120, w: 200, h: 16, cell: true },
    { text: "2페이지줄", x: 50, y: H + 60, w: 700, h: 20, cell: false },
  ],
  boxes: [
    { x: 55, y: 100, w: 210, h: 40,
      border: { l: "1.00px solid #000", r: "none",
                t: "1.00px solid #000", b: "none" } },
    { x: 55, y: H + 40, w: 210, h: 40 },  // border 없음(안내선)
  ],
};

const html = renderCoordinateLayout(layout);

// 1) 페이지 2개
assert((html.match(/class="co-page"/g) || []).length === 2, "2 pages");
checks.pages = true;

// 2) 줄 3개, 절대배치 top 이 페이지 상대로 환산됨(2페이지 줄 top≈60)
assert((html.match(/class="co-line"/g) || []).length === 3, "3 lines");
assert(html.includes("가나 다라"), "line text present");
assert(/top:60(\.0)?px/.test(html), "page1 line top=60");
assert(/top:60(\.0)?px/.test(html.split('class="co-page"')[2] || ""),
  "page2 line converted to page-relative top≈60");
checks.linesPositioned = true;

// 3) HTML escape
const esc = renderCoordinateLayout({
  pageWidthPx: 100, pageHeightPx: 100, pages: 1,
  lines: [{ text: "<b>&x", x: 0, y: 0, w: 10, h: 10 }], boxes: [],
});
assert(esc.includes("&lt;b&gt;&amp;x") && !esc.includes("<b>&x"),
  "html escaped");
checks.escape = true;

// 4) 박스 테두리: 지정 변은 solid, none 변은 옅은 안내선으로 치환
assert(html.includes("border-left:1.00px solid #000"), "box left border");
assert(html.includes("border-right:0.6px solid #e2e6ea"), "none→guide");
assert(html.includes("border:0.6px solid #e2e6ea"), "no-border box guide");
checks.borders = true;

// 5) 빈 레이아웃
assert(renderCoordinateLayout(null).includes("co-empty"), "null layout");
checks.empty = true;

console.log(JSON.stringify({
  task: "HWPX-COORD-RENDERER-SELFTEST", checks, verdict: "PASS",
}));
