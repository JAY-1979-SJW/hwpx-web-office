/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-EXISTING-CHARPR-01.
 *
 * existing charPr 안에서 current attrs 의 bold/underline/italic 만
 * 토글한 완전 일치 id 를 찾는다. 모든 비교는 정확 동등(===) — 부분
 * 일치/근사 매칭은 허용하지 않는다. fontSize/color/fontName 변경 matching
 * 금지.
 *
 * 본 모듈은 신규 charPr 를 만들지 않는다. header.xml 을 수정하지 않는다.
 * backend writer / state factory 를 호출하지 않는다.
 */

export const MATCH_DIMENSIONS = ["bold", "underline", "italic"];

function _attrsEqual(a, b, ignoreKey) {
  // 비교 키: fontName, fontFace, fontSizePt, height, textColor + 토글
  // 외 두 가지 (bold/italic/underline 중 ignoreKey 제외).
  const keys = ["fontName", "fontFace", "fontSizePt", "height",
                          "textColor", "bold", "italic", "underline"];
  for (const k of keys) {
    if (k === ignoreKey) continue;
    if ((a?.[k] ?? null) !== (b?.[k] ?? null)) return false;
  }
  return true;
}

/* matchToggle(currentDef, defsDict, dimension)
 *
 * currentDef : { charPrId, fontName, fontSizePt, textColor, bold,
 *                italic, underline, ... }
 * defsDict   : Record<charPrId, def>  — payload.styles.charPrDefs.
 * dimension  : "bold" | "underline" | "italic".
 *
 * 동작:
 *   - currentDef[dimension] 만 반전한 target attrs 생성.
 *   - defsDict 의 모든 def 중 _attrsEqual(def, currentDef, dimension)
 *     이고 def[dimension] === !currentDef[dimension] 인 id 반환.
 *   - 없으면 null.
 *
 * 안전:
 *   - dimension 이 허용 enum 밖이면 null.
 *   - currentDef / defsDict 누락 시 null.
 *   - 자기 자신 (charPrId 동일) 은 후보에서 제외.
 */
export function matchToggle(currentDef, defsDict, dimension) {
  if (!currentDef || !defsDict) return null;
  if (!MATCH_DIMENSIONS.includes(dimension)) return null;
  const currentFlag = !!currentDef[dimension];
  const wantFlag = !currentFlag;
  const currentId = currentDef.charPrId
                                ?? currentDef.id ?? null;
  for (const [cid, def] of Object.entries(defsDict)) {
    if (cid === currentId) continue;
    if (!!def?.[dimension] !== wantFlag) continue;
    if (_attrsEqual(def, currentDef, dimension)) {
      return cid;
    }
  }
  return null;
}

/* 다중 dimension matching 결과 dict. UI 가 한 번 호출해 3 버튼 상태를
 * 동시에 결정할 수 있다. */
export function matchAllToggles(currentDef, defsDict) {
  const out = {};
  for (const dim of MATCH_DIMENSIONS) {
    out[dim] = matchToggle(currentDef, defsDict, dim);
  }
  return out;
}

/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-MATCHING-EXISTING-CHARPR-01.
 *
 * axis 한 개만 사용자가 지정한 newValue 로 변경한 target attrs 와
 * 정확 동등한 charPrId 를 찾는다. 1차 공정에서 axis 는 "fontSizePt" 만
 * 허용 — color/fontName 은 후속 공정.
 *
 * 안전:
 *   - axis ∉ MATCH_AXIS_CHANGE_DIMENSIONS → null
 *   - newValue == currentDef[axis] → 변경 없음 — null (NOOP)
 *   - fontSizePt 변경 시 height (=fontSizePt × 100) 정합도 함께 검증
 *   - 다른 모든 축 (fontName, fontFace, textColor, bold, italic,
 *     underline) 정확 동등(===)
 *   - 자기 자신 (charPrId) 제외
 */
// WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01:
// "fontName" 추가 (3차 axis).
export const MATCH_AXIS_CHANGE_DIMENSIONS = [
  "fontSizePt", "textColor", "fontName",
];

function _heightFromFontSizePt(pt) {
  if (pt === null || pt === undefined) return null;
  // header.xml 의 height 는 보통 pt × 100 (정수). 안전을 위해 round.
  return Math.round(pt * 100);
}

export function matchAxisChange(currentDef, defsDict, axis, newValue) {
  if (!currentDef || !defsDict) return null;
  if (!MATCH_AXIS_CHANGE_DIMENSIONS.includes(axis)) return null;
  if (newValue === undefined || newValue === null) return null;
  // NOOP — 동일 값이면 매칭 결과 없음으로 본다.
  if ((currentDef[axis] ?? null) === newValue) return null;
  const currentId = currentDef.charPrId ?? currentDef.id ?? null;
  // axis === "fontSizePt" 전용 로직 (1차 공정 한정)
  if (axis === "fontSizePt") {
    const wantHeight = _heightFromFontSizePt(newValue);
    for (const [cid, def] of Object.entries(defsDict)) {
      if (cid === currentId) continue;
      if ((def?.fontSizePt ?? null) !== newValue) continue;
      // height 가 정의되어 있으면 정합 검증
      if (def?.height !== null && def?.height !== undefined
          && wantHeight !== null
          && def.height !== wantHeight) {
        continue;
      }
      // 다른 모든 축 정확 동등
      const otherKeys = ["fontName", "fontFace", "textColor",
                                      "bold", "italic", "underline"];
      let same = true;
      for (const k of otherKeys) {
        if ((def?.[k] ?? null) !== (currentDef?.[k] ?? null)) {
          same = false; break;
        }
      }
      if (same) return cid;
    }
    return null;
  }
  // WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01.
  // textColor 변경 매칭. #RRGGBB 문자열 완전 일치 (===) — 근사 매칭은 금지.
  if (axis === "textColor") {
    for (const [cid, def] of Object.entries(defsDict)) {
      if (cid === currentId) continue;
      if ((def?.textColor ?? null) !== newValue) continue;
      const otherKeys = ["fontName", "fontFace", "fontSizePt",
                                      "height", "bold", "italic", "underline"];
      let same = true;
      for (const k of otherKeys) {
        if ((def?.[k] ?? null) !== (currentDef?.[k] ?? null)) {
          same = false; break;
        }
      }
      if (same) return cid;
    }
    return null;
  }
  // WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01.
  // fontName 변경 매칭. 문자열 정확 동등(===) — 별칭/근사 매칭 미허용.
  // 정합성: corpus 실측 fontFace ↔ fontName 이 다대다 (HWPX 내부 슬롯
  // 인덱스) 이므로 fontFace 는 비교 identity 에서 **제외**한다.
  if (axis === "fontName") {
    for (const [cid, def] of Object.entries(defsDict)) {
      if (cid === currentId) continue;
      if ((def?.fontName ?? null) !== newValue) continue;
      // fontFace 는 비교하지 않음 (1차 정책).
      const otherKeys = ["fontSizePt", "height", "textColor",
                                      "bold", "italic", "underline"];
      let same = true;
      for (const k of otherKeys) {
        if ((def?.[k] ?? null) !== (currentDef?.[k] ?? null)) {
          same = false; break;
        }
      }
      if (same) return cid;
    }
    return null;
  }
  return null;
}

/* dropdown 후보 추출. axis="fontSizePt" 만 1차 공정 허용.
 *
 * returns: [{ value, matchedCharPrId, enabled }, ...]
 *   - value: 후보 값 (숫자, 오름차순, 중복 제거)
 *   - matchedCharPrId: currentDef 와 axis 만 다른 charPrId. 없으면 null
 *   - enabled: matchedCharPrId != null && value !== currentDef[axis]
 */
export function extractAxisValues(defsDict, axis, currentDef) {
  if (!defsDict) return [];
  if (!MATCH_AXIS_CHANGE_DIMENSIONS.includes(axis)) return [];
  // 후보 값 set
  const set = new Set();
  for (const d of Object.values(defsDict)) {
    const v = d?.[axis] ?? null;
    if (v !== null && v !== undefined) set.add(v);
  }
  const sorted = Array.from(set);
  if (axis === "fontSizePt") {
    sorted.sort((a, b) => a - b);
  } else {
    sorted.sort();
  }
  const currentValue = currentDef ? (currentDef[axis] ?? null) : null;
  return sorted.map((value) => {
    if (value === currentValue) {
      return { value, matchedCharPrId: null, enabled: false,
                      current: true };
    }
    const matched = currentDef
      ? matchAxisChange(currentDef, defsDict, axis, value)
      : null;
    return {
      value,
      matchedCharPrId: matched,
      enabled: matched !== null,
      current: false,
    };
  });
}
