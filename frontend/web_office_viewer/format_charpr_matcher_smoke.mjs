#!/usr/bin/env node
/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-EXISTING-CHARPR-01 smoke.
 * matchToggle 의 정확 일치 / 실패 / 자기 제외 / dimension enum 정합
 * 을 검증한다. */
import { matchToggle, matchAllToggles, MATCH_DIMENSIONS,
  matchAxisChange, extractAxisValues,
  MATCH_AXIS_CHANGE_DIMENSIONS }
  from "./format_charpr_matcher.mjs";

const out = { task: "WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-"
                                  + "EXISTING-CHARPR-01", checks: {} };
function rec(name, ok, extra) {
  out.checks[name] = { ok, ...(extra || {}) };
  if (!ok) {
    out.verdict = "FAIL"; out.failedAt = name;
    console.log(JSON.stringify(out)); process.exit(1);
  }
}

const def = (id, attrs) => ({
  charPrId: id, fontName: "굴림", fontFace: "0",
  fontSizePt: 11, height: 1100, textColor: "#000000",
  bold: false, italic: false, underline: false,
  ...attrs,
});
const defs = {
  "10": def("10", {}),
  "11": def("11", { bold: true }),
  "12": def("12", { underline: true }),
  "13": def("13", { italic: true }),
  // 다른 폰트 크기 — 매칭 후보가 아님
  "20": def("20", { fontSizePt: 12, bold: true }),
  // 같은 bold true 이지만 색이 다름
  "21": def("21", { textColor: "#0000FF", bold: true }),
};

// 1. bold toggle 성공 (10 → 11)
let r = matchToggle(defs["10"], defs, "bold");
rec("boldToggleSuccess", r === "11", { got: r });

// 2. underline toggle 성공 (10 → 12)
r = matchToggle(defs["10"], defs, "underline");
rec("underlineToggleSuccess", r === "12", { got: r });

// 3. italic toggle 성공 (10 → 13)
r = matchToggle(defs["10"], defs, "italic");
rec("italicToggleSuccess", r === "13", { got: r });

// 4. bold off (11) → bold on→off 매칭 (11 → 10)
r = matchToggle(defs["11"], defs, "bold");
rec("boldToggleOffSuccess", r === "10", { got: r });

// 5. 매칭 실패 — bold true 이미 있고 다른 색 fixture 만 있는 경우
const isolated = { "30": def("30", {}) };  // 자기 자신만
r = matchToggle(isolated["30"], isolated, "bold");
rec("noMatchReturnsNull", r === null);

// 6. fontSize 변경 matching 금지 — 다른 fontSize 의 bold 후보 무시
const sizeOnly = {
  "40": def("40", {}),
  "41": def("41", { fontSizePt: 14, bold: true }),
};
r = matchToggle(sizeOnly["40"], sizeOnly, "bold");
rec("differentSizeNotMatched", r === null);

// 7. color 변경 matching 금지
const colorOnly = {
  "50": def("50", {}),
  "51": def("51", { textColor: "#FF0000", bold: true }),
};
r = matchToggle(colorOnly["50"], colorOnly, "bold");
rec("differentColorNotMatched", r === null);

// 8. dimension enum 외 → null
r = matchToggle(defs["10"], defs, "color");
rec("invalidDimensionReturnsNull", r === null);

// 9. null inputs
rec("nullCurrentReturnsNull",
        matchToggle(null, defs, "bold") === null);
rec("nullDefsReturnsNull",
        matchToggle(defs["10"], null, "bold") === null);

// 10. 자기 자신 제외
const self = { "60": def("60", {}) };
rec("selfExcluded",
        matchToggle(self["60"], self, "bold") === null);

// 11. matchAllToggles 일괄 결과
const all = matchAllToggles(defs["10"], defs);
rec("matchAllBold", all.bold === "11");
rec("matchAllUnderline", all.underline === "12");
rec("matchAllItalic", all.italic === "13");
rec("matchAllKeysExact",
        Object.keys(all).sort().join(",")
        === MATCH_DIMENSIONS.slice().sort().join(","));

// 12. fuzzy 금지 — 일부 속성만 다른 경우 매칭 실패
const fuzzyDefs = {
  "70": def("70", {}),
  // bold true 이지만 italic 도 동시 변경 — 완전 일치 아님
  "71": def("71", { bold: true, italic: true }),
};
rec("fuzzyToggleNotMatched",
        matchToggle(fuzzyDefs["70"], fuzzyDefs, "bold") === null);

// ── WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-MATCHING-EXISTING-CHARPR-01

// axis enum 정합 (3차 공정 — fontSizePt + textColor + fontName)
rec("axisChangeDimensionsExact",
        MATCH_AXIS_CHANGE_DIMENSIONS.length === 3
        && MATCH_AXIS_CHANGE_DIMENSIONS.includes("fontSizePt")
        && MATCH_AXIS_CHANGE_DIMENSIONS.includes("textColor")
        && MATCH_AXIS_CHANGE_DIMENSIONS.includes("fontName"));

// fontSize matching 합성 dataset
const sizeDefs = {
  "100": { charPrId: "100", fontName: "굴림", fontFace: "0",
                  fontSizePt: 10, height: 1000, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  "101": { charPrId: "101", fontName: "굴림", fontFace: "0",
                  fontSizePt: 12, height: 1200, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  "102": { charPrId: "102", fontName: "굴림", fontFace: "0",
                  fontSizePt: 14, height: 1400, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  // 다른 fontName — fontSize matching 불가
  "110": { charPrId: "110", fontName: "바탕", fontFace: "1",
                  fontSizePt: 12, height: 1200, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  // 같은 fontSize 지만 color 다름
  "120": { charPrId: "120", fontName: "굴림", fontFace: "0",
                  fontSizePt: 12, height: 1200, textColor: "#FF0000",
                  bold: false, italic: false, underline: false },
};

// 2. fontSize 12 → 100→101 매칭
rec("fontSizeMatchingSuccess",
        matchAxisChange(sizeDefs["100"], sizeDefs, "fontSizePt", 12)
        === "101");

// 3. fontSize 99 → 매칭 없음
rec("fontSizeMatchingFailure",
        matchAxisChange(sizeDefs["100"], sizeDefs, "fontSizePt", 99)
        === null);

// 4. fontSize NOOP (10→10) → null
rec("fontSizeNoopReturnsNull",
        matchAxisChange(sizeDefs["100"], sizeDefs, "fontSizePt", 10)
        === null);

// 5. textColor axis 는 2차 공정에서 활성화되어 — null 일 수도 있지만,
// sizeDefs 에는 모두 #000000 만 있어 매칭 후보 없음 → null
rec("axisTextColorActivated2ndWave",
        matchAxisChange(sizeDefs["100"], sizeDefs, "textColor",
                                      "#0000FF") === null);

// 6. fontName 은 fontName-matching 공정에서 활성화됨. sizeDefs 에는
// 단일 폰트(굴림)만 있으므로 "바탕" 매칭 불가 → null
rec("axisFontNameRejected1stWave",
        matchAxisChange(sizeDefs["100"], sizeDefs, "fontName",
                                      "바탕") === null);

// 7. height 정합 — height 가 잘못 적힌 def 는 매칭 제외
const badHeightDefs = {
  "200": { charPrId: "200", fontName: "굴림", fontFace: "0",
                  fontSizePt: 10, height: 1000, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  // fontSizePt 는 12 인데 height 가 999 (1200 이어야 함) → 매칭 제외
  "201": { charPrId: "201", fontName: "굴림", fontFace: "0",
                  fontSizePt: 12, height: 999, textColor: "#000000",
                  bold: false, italic: false, underline: false },
};
rec("heightMismatchExcluded",
        matchAxisChange(badHeightDefs["200"], badHeightDefs,
                                      "fontSizePt", 12) === null);

// 8. 자기 자신 제외
const selfDefs = {
  "300": { charPrId: "300", fontName: "굴림", fontFace: "0",
                  fontSizePt: 10, height: 1000, textColor: "#000000",
                  bold: false, italic: false, underline: false },
};
rec("axisChangeSelfExcluded",
        matchAxisChange(selfDefs["300"], selfDefs, "fontSizePt", 12)
        === null);

// 9. null inputs
rec("axisChangeNullCurrent",
        matchAxisChange(null, sizeDefs, "fontSizePt", 12) === null);
rec("axisChangeNullDefs",
        matchAxisChange(sizeDefs["100"], null, "fontSizePt", 12)
        === null);
rec("axisChangeNullValue",
        matchAxisChange(sizeDefs["100"], sizeDefs, "fontSizePt", null)
        === null);

// 10. extractAxisValues — fontSize 후보 정렬 + matching 결과 동반
const values = extractAxisValues(sizeDefs, "fontSizePt",
                                                                sizeDefs["100"]);
rec("extractAxisValuesShape",
        Array.isArray(values) && values.length === 3);
rec("extractAxisValuesSorted",
        values.map((v) => v.value).join(",") === "10,12,14");
rec("extractAxisValuesCurrentMarked",
        values.find((v) => v.value === 10)?.current === true
        && values.find((v) => v.value === 10)?.enabled === false);
rec("extractAxisValuesMatch12",
        values.find((v) => v.value === 12)?.matchedCharPrId === "101");
rec("extractAxisValuesMatch14",
        values.find((v) => v.value === 14)?.matchedCharPrId === "102");
rec("extractAxisValuesEnabled12",
        values.find((v) => v.value === 12)?.enabled === true);

// 11. extractAxisValues axis 미허용 — 이제 모든 enum 활성화 후이므로
// 임의 미허용 axis ("bold") 로 검증
rec("extractAxisValuesRejectColor",
        Array.isArray(extractAxisValues(sizeDefs, "bold",
                                                                  sizeDefs["100"]))
        && extractAxisValues(sizeDefs, "bold", sizeDefs["100"])
              .length === 0);

// 12. extractAxisValues 중복 제거
const dupDefs = {
  "400": { charPrId: "400", fontName: "굴림", fontSizePt: 10,
                  height: 1000, textColor: "#000000", bold: false,
                  italic: false, underline: false, fontFace: "0" },
  "401": { charPrId: "401", fontName: "굴림", fontSizePt: 10,
                  height: 1000, textColor: "#000000", bold: false,
                  italic: false, underline: false, fontFace: "0" },
};
const dupValues = extractAxisValues(dupDefs, "fontSizePt",
                                                                      dupDefs["400"]);
rec("extractAxisValuesDedup",
        dupValues.filter((v) => v.value === 10).length === 1);

// ── WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-MATCHING-EXISTING-CHARPR-01

// axis enum 확장 정합 (color matching 공정 — 이후 fontName 추가됨)
rec("axisChangeDimensionsTwo",
        MATCH_AXIS_CHANGE_DIMENSIONS.length >= 2
        && MATCH_AXIS_CHANGE_DIMENSIONS.includes("fontSizePt")
        && MATCH_AXIS_CHANGE_DIMENSIONS.includes("textColor"));

// fontName 은 fontDefs 가 아닌 sizeDefs 에서는 동일 fontName(굴림) 만
// 있으므로 다른 폰트("바탕") 매칭 불가 → null
rec("fontNameStillRejected",
        matchAxisChange(sizeDefs["100"], sizeDefs, "fontName", "바탕")
        === null);

// color matching dataset
const colorDefs = {
  "500": { charPrId: "500", fontName: "굴림", fontFace: "0",
                  fontSizePt: 11, height: 1100, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  "501": { charPrId: "501", fontName: "굴림", fontFace: "0",
                  fontSizePt: 11, height: 1100, textColor: "#FF0000",
                  bold: false, italic: false, underline: false },
  "502": { charPrId: "502", fontName: "굴림", fontFace: "0",
                  fontSizePt: 11, height: 1100, textColor: "#0000FF",
                  bold: false, italic: false, underline: false },
  // 다른 fontSize — 매칭 불가
  "510": { charPrId: "510", fontName: "굴림", fontFace: "0",
                  fontSizePt: 12, height: 1200, textColor: "#00FF00",
                  bold: false, italic: false, underline: false },
  // 같은 색이지만 bold 다름
  "520": { charPrId: "520", fontName: "굴림", fontFace: "0",
                  fontSizePt: 11, height: 1100, textColor: "#FF0000",
                  bold: true, italic: false, underline: false },
};

// 검정 → 빨강 매칭
rec("colorMatchingBlackToRed",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#FF0000") === "501");
// 검정 → 파랑 매칭
rec("colorMatchingBlackToBlue",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#0000FF") === "502");
// 빨강 → 검정 매칭
rec("colorMatchingRedToBlack",
        matchAxisChange(colorDefs["501"], colorDefs, "textColor",
                                      "#000000") === "500");
// 없는 색
rec("colorMatchingNotFound",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#123456") === null);
// NOOP — 동일 색
rec("colorMatchingNoopReturnsNull",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#000000") === null);
// 다른 fontSize 의 같은 색은 매칭 안 됨 — 510 은 12pt 라서
rec("colorMatchingDifferentSizeRejected",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#00FF00") === null);
// bold 다름 + 같은 색은 매칭 안 됨
rec("colorMatchingDifferentBoldRejected",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#FF0000") !== "520");

// extractAxisValues("textColor")
const colorValues = extractAxisValues(colorDefs, "textColor",
                                                                    colorDefs["500"]);
rec("extractAxisValuesColorIsArray",
        Array.isArray(colorValues) && colorValues.length >= 4);
rec("extractAxisValuesColorDedup",
        colorValues.filter((v) => v.value === "#FF0000").length === 1);
rec("extractAxisValuesColorCurrent",
        colorValues.find((v) => v.value === "#000000")?.current
        === true);
rec("extractAxisValuesColorEnabled",
        colorValues.find((v) => v.value === "#FF0000")?.enabled
        === true);
rec("extractAxisValuesColorDisabledForOtherSize",
        // #00FF00 은 510 (fontSize 12) 에만 있어서 500 (11pt) 기준
        // 매칭 안 됨
        colorValues.find((v) => v.value === "#00FF00")?.enabled
        === false);

// fuzzy color 금지 확인 — Math.abs / hsv 등 사용 흔적은 matcher 모듈
// 자체 정적 grep 으로 audit 가 검증. smoke 에서는 동작 측면만:
rec("colorMatchingExactOnly",
        matchAxisChange(colorDefs["500"], colorDefs, "textColor",
                                      "#000001") === null);

// ── WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-CHARPR-01

// axis enum 3개 (fontSizePt, textColor, fontName)
rec("axisChangeDimensionsThree",
        MATCH_AXIS_CHANGE_DIMENSIONS.length === 3
        && MATCH_AXIS_CHANGE_DIMENSIONS.includes("fontName"));

// fontName matching dataset
const fontDefs = {
  "600": { charPrId: "600", fontName: "돋움", fontFace: "0",
                  fontSizePt: 11, height: 1100, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  "601": { charPrId: "601", fontName: "돋움체", fontFace: "0",
                  fontSizePt: 11, height: 1100, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  "602": { charPrId: "602", fontName: "바탕", fontFace: "1",
                  fontSizePt: 11, height: 1100, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  // 다른 fontSize — fontName 매칭 불가
  "610": { charPrId: "610", fontName: "한양신명조", fontFace: "2",
                  fontSizePt: 12, height: 1200, textColor: "#000000",
                  bold: false, italic: false, underline: false },
  // fontFace 다르지만 fontName 매칭은 OK 여야 함 (정합 면제)
  "620": { charPrId: "620", fontName: "굴림", fontFace: "5",
                  fontSizePt: 11, height: 1100, textColor: "#000000",
                  bold: false, italic: false, underline: false },
};

// 돋움 → 돋움체 매칭
rec("fontNameMatchingDotumToDotumChe",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "돋움체") === "601");

// 돋움 → 바탕 매칭
rec("fontNameMatchingDotumToBatang",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "바탕") === "602");

// fontFace 가 달라도 fontName + 6축 동일하면 매칭 OK — 굴림 (fontFace 5)
rec("fontNameMatchingFontFaceIgnored",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "굴림") === "620");

// 없는 폰트명
rec("fontNameMatchingNotFound",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "없는폰트") === null);

// NOOP — 동일 fontName
rec("fontNameMatchingNoopReturnsNull",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "돋움") === null);

// 다른 fontSize — 한양신명조 (12pt) 는 매칭 불가
rec("fontNameMatchingDifferentSizeRejected",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "한양신명조") === null);

// alias 미적용 — 돋움 vs Dotum 같은 alias 는 자동 매칭 안 됨
rec("fontNameAliasNotAutoMatched",
        matchAxisChange(fontDefs["600"], fontDefs, "fontName",
                                      "Dotum") === null);

// extractAxisValues("fontName") — 후보 추출
const fontValues = extractAxisValues(fontDefs, "fontName",
                                                                    fontDefs["600"]);
rec("extractAxisValuesFontNameArray",
        Array.isArray(fontValues) && fontValues.length >= 4);
rec("extractAxisValuesFontNameDedup",
        fontValues.filter((v) => v.value === "돋움").length === 1);
rec("extractAxisValuesFontNameCurrent",
        fontValues.find((v) => v.value === "돋움")?.current === true);
rec("extractAxisValuesFontNameEnabled",
        fontValues.find((v) => v.value === "돋움체")?.enabled === true);
rec("extractAxisValuesFontNameDisabledForOtherSize",
        // 한양신명조 는 다른 fontSize — 매칭 불가
        fontValues.find((v) => v.value === "한양신명조")?.enabled
        === false);
rec("extractAxisValuesFontNameFontFaceIgnored",
        // 굴림 은 fontFace 다르지만 매칭 가능
        fontValues.find((v) => v.value === "굴림")?.enabled === true);

out.verdict = "PASS";
console.log(JSON.stringify(out));
