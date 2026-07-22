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

// 6) 서식 조각(charPr) — 한 줄이 굵게/색 조각으로 분해되고 실서식 적용
const styled = renderCoordinateLayout({
  pageWidthPx: 400, pageHeightPx: 400, pages: 1,
  charPrDefs: {
    "1": { fontName: "함초롬돋움", fontSizePt: 14, bold: true },
    "2": { fontName: "함초롬바탕", fontSizePt: 10, textColor: "#ff0000" },
  },
  lines: [{
    text: "제목본문", x: 10, y: 10, w: 380, h: 24, cell: false,
    segments: [
      { text: "제목", charPr: "1" },
      { text: "본문", charPr: "2" },
    ],
  }],
  boxes: [],
});
// co-in 래퍼 1개 + 조각 2개 = span 3개
assert((styled.match(/<span/g) || []).length === 3, "co-in wrapper + 2 segment spans");
assert(styled.includes('class="co-in"'), "inline-block wrapper present (autoFit용)");
assert(/font-weight:700/.test(styled), "bold charPr applied");
assert(/font-size:14pt/.test(styled), "real fontSize applied (not h*0.72)");
assert(/color:#ff0000/.test(styled), "text color applied");
assert(styled.includes("제목") && styled.includes("본문"), "both texts present");
// charPr 없는 줄은 추정 폰트크기로 안전 폴백
const fallback = renderCoordinateLayout({
  pageWidthPx: 400, pageHeightPx: 400, pages: 1,
  lines: [{ text: "무서식", x: 0, y: 0, w: 100, h: 20 }], boxes: [],
});
assert(/font-size:14\.4px/.test(fallback), "fallback fontSize (h*0.72)");
assert(fallback.includes("무서식"), "fallback text present");
checks.formatSegments = true;

// 7) 세로 클리핑 방지 — line-height 는 반드시 박스 높이와 같아야 한다.
//    (더 크면 overflow:hidden 이 글자 위/아래를 잘라 문자가 깨짐 — 회귀 가드)
const bl = renderCoordinateLayout({
  pageWidthPx: 400, pageHeightPx: 400, pages: 1,
  lines: [{ text: "받침글자", x: 0, y: 0, w: 100, h: 20, baseline: 17 }],
  boxes: [],
});
assert(/height:20px;line-height:20px/.test(bl),
  "line-height == box height (글자 세로 클리핑 없음)");
assert(!/line-height:34/.test(bl), "no oversized line-height (clip regression)");
checks.noClip = true;

// 8) 문단 정렬(text-align) 반영 + Wingdings PUA 화살표 → 유니코드 정규화
const al = renderCoordinateLayout({
  pageWidthPx: 300, pageHeightPx: 300, pages: 1,
  lines: [
    { text: "제목", x: 0, y: 0, w: 300, h: 16, align: "center" },
    { text: "", x: 0, y: 20, w: 20, h: 12 },  // Wingdings 오른쪽 화살표
  ],
  boxes: [],
});
assert(/text-align:center/.test(al), "paragraph center align applied");
assert(al.includes("→") && !al.includes(""),
  "Wingdings PUA arrow normalized to unicode →");
checks.alignAndSymbol = true;

// 9) 편집 연결 — editable 시 셀 박스에 data-cell-id, getCellText 로 편집셀
//    원본 줄 숨기고 새 텍스트 렌더.
const ed = renderCoordinateLayout({
  pageWidthPx: 400, pageHeightPx: 400, pages: 1,
  boxes: [{ x: 0, y: 0, w: 100, h: 20, cellId: "cell_t_s0_000_r0_c0" }],
  lines: [{ text: "원본", x: 0, y: 0, w: 100, h: 20,
            cellId: "cell_t_s0_000_r0_c0",
            segments: [{ text: "원본", charPr: null }] }],
}, { editable: true,
     getCellText: (id) => (id === "cell_t_s0_000_r0_c0" ? "수정됨" : null) });
assert(ed.includes('data-cell-id="cell_t_s0_000_r0_c0"'),
  "editable 시 박스에 data-cell-id");
assert(ed.includes("수정됨") && !ed.includes("원본"),
  "편집셀 원본 숨기고 새 텍스트 렌더");
// editable 아니면 data-cell-id 없음(읽기 전용)
const ro = renderCoordinateLayout({
  pageWidthPx: 400, pageHeightPx: 400, pages: 1,
  boxes: [{ x: 0, y: 0, w: 100, h: 20, cellId: "cell_x" }], lines: [],
});
assert(!ro.includes("data-cell-id"), "non-editable 은 data-cell-id 없음");
checks.editableCells = true;

console.log(JSON.stringify({
  task: "HWPX-COORD-RENDERER-SELFTEST", checks, verdict: "PASS",
}));
