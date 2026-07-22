/* editor_find — 찾기/바꾸기 순수 로직 모듈 (M1).
 *
 * 편집기 문단 모델(paragraphs = [{paragraphId, runs:[{text,charPrIDRef}]}])에서
 * 질의어를 찾아 위치 목록을 돌려주고, 바꾸기용 편집 계획을 생성한다.
 * 순수함수 — DOM/상태 비의존. 테스트 용이.
 *
 * 위치 표현: 문단별 평문(runs.text 이어붙임) 기준 offset.
 *   match = { paragraphId, start, end }  (end 미포함)
 */

/** 문단 하나의 평문(runs 이어붙임). */
export function paragraphText(p) {
  return (p.runs || []).map((r) => r.text || "").join("");
}

/** 전체 문단에서 query 출현 위치 목록. caseSensitive 기본 false. */
export function findMatches(paragraphs, query, opts = {}) {
  const matches = [];
  if (!query) return matches;
  const cs = !!opts.caseSensitive;
  const needle = cs ? query : query.toLowerCase();
  for (const p of paragraphs || []) {
    const raw = paragraphText(p);
    const hay = cs ? raw : raw.toLowerCase();
    let from = 0;
    while (true) {
      const idx = hay.indexOf(needle, from);
      if (idx < 0) break;
      matches.push({ paragraphId: p.paragraphId, start: idx, end: idx + query.length });
      from = idx + Math.max(1, query.length);
    }
  }
  return matches;
}

/** offset이 속한 run 인덱스와 run 내부 offset 반환. */
export function locateOffset(p, offset) {
  let acc = 0;
  const runs = p.runs || [];
  for (let i = 0; i < runs.length; i++) {
    const len = (runs[i].text || "").length;
    if (offset < acc + len) return { runIndex: i, inRun: offset - acc };
    acc += len;
  }
  return { runIndex: Math.max(0, runs.length - 1), inRun: (runs[runs.length - 1]?.text || "").length };
}

/** 첫 매치의 charPrIDRef(바꾸기 시 서식 계승용). 없으면 null. */
export function charPrAtMatch(p, match) {
  const loc = locateOffset(p, match.start);
  return (p.runs || [])[loc.runIndex]?.charPrIDRef ?? null;
}

/**
 * 바꾸기 계획: 각 매치를 (문단, 범위, 새 텍스트, 계승 charPr)로 표현.
 * 실제 편집은 편집기 계층이 setRange→deleteRange→typeTextAtCaret로 적용.
 * 매치는 문단별로 뒤에서 앞으로 정렬(offset 안정성 확보).
 */
export function buildReplacePlan(paragraphs, query, replacement, opts = {}) {
  const byPara = new Map();
  for (const m of findMatches(paragraphs, query, opts)) {
    if (!byPara.has(m.paragraphId)) byPara.set(m.paragraphId, []);
    byPara.get(m.paragraphId).push(m);
  }
  const plan = [];
  const pmap = new Map((paragraphs || []).map((p) => [p.paragraphId, p]));
  for (const [pid, ms] of byPara) {
    const p = pmap.get(pid);
    ms.sort((a, b) => b.start - a.start); // 뒤에서 앞으로
    for (const m of ms) {
      plan.push({
        paragraphId: pid,
        start: m.start,
        end: m.end,
        text: replacement,
        charPrIDRef: charPrAtMatch(p, m),
      });
    }
  }
  return plan;
}

/* ── 자체 검증(node에서 실행) ── */
export function _selfTest() {
  const paras = [
    { paragraphId: "p1", runs: [{ text: "신청서 ", charPrIDRef: "c1" }, { text: "제출", charPrIDRef: "c2" }] },
    { paragraphId: "p2", runs: [{ text: "재신청 신청 완료", charPrIDRef: "c3" }] },
  ];
  const out = [];
  const eq = (name, a, b) => out.push(`${JSON.stringify(a) === JSON.stringify(b) ? "PASS" : "FAIL"} ${name}`);

  eq("paragraphText join", paragraphText(paras[0]), "신청서 제출");
  eq("find '신청' 3건", findMatches(paras, "신청").length, 3);
  eq("find case pos p2", findMatches(paras, "신청").filter((m) => m.paragraphId === "p2").map((m) => m.start), [1, 4]);
  eq("locateOffset run boundary", locateOffset(paras[0], 4).runIndex, 1);
  eq("charPr 계승 p1@0", charPrAtMatch(paras[0], { start: 0, end: 2 }), "c1");
  const plan = buildReplacePlan(paras, "신청", "확인");
  eq("replace plan 3건", plan.length, 3);
  eq("plan p2 뒤에서앞으로", plan.filter((x) => x.paragraphId === "p2").map((x) => x.start), [4, 1]);
  return out;
}
