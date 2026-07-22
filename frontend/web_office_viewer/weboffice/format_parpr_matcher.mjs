/* format_parpr_matcher — 문단서식(paraPr) 축 변경을 "기존 paraPr 매칭"으로만 해결.
 *
 * charPr 매처(format_charpr_matcher)와 동형 설계:
 *   신규 paraPr 정의를 만들지 않는다. 원하는 축 값을 가진 기존 paraPr 이
 *   없으면 null 을 돌려 편집을 거부한다(§4 정신 유지).
 *
 * 다루는 축:
 *   align       문단 정렬  (align.horizontal: LEFT/CENTER/RIGHT/JUSTIFY)
 *   lineSpacing 줄간격     (lineSpacing.value, PERCENT 기준)
 *   indentLeft  왼쪽 들여쓰기 (margin.left.value, HWPUNIT)
 *
 * 매칭 규칙: 대상 축만 원하는 값이고 "나머지 축들"은 현재와 동일한 paraPr 을 찾는다.
 */

export const PARA_AXES = {
  align: (d) => d?.align?.horizontal ?? null,
  lineSpacing: (d) => {
    const v = d?.lineSpacing?.value;
    return v === undefined || v === null || v === "" ? null : Number(v);
  },
  indentLeft: (d) => {
    const v = d?.margin?.left?.value;
    return v === undefined || v === null || v === "" ? null : Number(v);
  },
};

/** 대상 축을 제외한 나머지 축들의 서명(같으면 "그 축만 다른" 후보). */
function signatureExcept(def, exclude) {
  return Object.keys(PARA_AXES)
    .filter((k) => k !== exclude)
    .map((k) => `${k}=${PARA_AXES[k](def)}`)
    .join("|");
}

/** 현재 paraPr 의 축 값. */
export function paraAxisValue(def, axis) {
  const fn = PARA_AXES[axis];
  return fn ? fn(def) : null;
}

/**
 * curDef 에서 axis 만 value 로 바꾼 기존 paraPr 의 id. 없으면 null(=거부).
 * defs: { paraPrId: def } 형태.
 */
export function matchParaAxisChange(curDef, defs, axis, value) {
  if (!curDef || !PARA_AXES[axis] || !defs) return null;
  const want = String(value);
  const base = signatureExcept(curDef, axis);
  // 현재와 같은 값이면 변경 불필요
  if (String(paraAxisValue(curDef, axis)) === want) return null;
  for (const [id, def] of Object.entries(defs)) {
    if (String(paraAxisValue(def, axis)) !== want) continue;
    if (signatureExcept(def, axis) === base) return id;
  }
  return null;
}

/**
 * 툴바용: 해당 축에서 고를 수 있는 값 목록.
 * [{ value, current, enabled, paraPrId }] — enabled=false 면 매칭 paraPr 부재(선택 불가).
 */
export function extractParaAxisValues(defs, axis, curDef) {
  if (!PARA_AXES[axis] || !defs) return [];
  const cur = paraAxisValue(curDef, axis);
  const seen = new Map();
  for (const def of Object.values(defs)) {
    const v = paraAxisValue(def, axis);
    if (v === null || seen.has(String(v))) continue;
    seen.set(String(v), v);
  }
  const out = [];
  for (const [key, v] of seen) {
    const isCur = String(cur) === key;
    out.push({
      value: v,
      current: isCur,
      enabled: isCur || matchParaAxisChange(curDef, defs, axis, v) !== null,
      paraPrId: isCur ? null : matchParaAxisChange(curDef, defs, axis, v),
    });
  }
  return out;
}

/* ── 자체 검증 ── */
export function _selfTest() {
  const mk = (align, ls, left) => ({
    align: { horizontal: align, vertical: "BASELINE" },
    lineSpacing: { type: "PERCENT", value: String(ls) },
    margin: { left: { value: String(left) }, intent: { value: "0" } },
  });
  // 0: LEFT/160/0   1: CENTER/160/0   2: RIGHT/160/0   3: LEFT/130/0   4: LEFT/160/7000
  const defs = { 0: mk("LEFT",160,0), 1: mk("CENTER",160,0), 2: mk("RIGHT",160,0),
                 3: mk("LEFT",130,0), 4: mk("LEFT",160,7000) };
  const cur = defs[0];
  const out = [];
  const eq = (n,a,b)=>out.push(`${JSON.stringify(a)===JSON.stringify(b)?"PASS":"FAIL"} ${n} (${JSON.stringify(a)})`);

  eq("축 읽기 align", paraAxisValue(cur,"align"), "LEFT");
  eq("align→CENTER = paraPr 1", matchParaAxisChange(cur,defs,"align","CENTER"), "1");
  eq("align→RIGHT = paraPr 2", matchParaAxisChange(cur,defs,"align","RIGHT"), "2");
  eq("align→JUSTIFY 없음 = 거부", matchParaAxisChange(cur,defs,"align","JUSTIFY"), null);
  eq("현재값 재선택 = null", matchParaAxisChange(cur,defs,"align","LEFT"), null);
  eq("줄간격→130 = paraPr 3", matchParaAxisChange(cur,defs,"lineSpacing",130), "3");
  eq("들여쓰기→7000 = paraPr 4", matchParaAxisChange(cur,defs,"indentLeft",7000), "4");
  // 다른 축이 섞이면 매칭 안 됨: CENTER 기준에서 줄간격 130 은 (CENTER,130) 없음
  eq("CENTER 기준 줄간격130 = 거부", matchParaAxisChange(defs[1],defs,"lineSpacing",130), null);
  const vals = extractParaAxisValues(defs,"align",cur);
  eq("align 후보 3종(LEFT/CENTER/RIGHT)", vals.length, 3);
  eq("JUSTIFY 후보 없음(비활성 아님·목록 미포함)", vals.map(v=>v.value).sort(), ["CENTER","LEFT","RIGHT"].sort());
  return out;
}
