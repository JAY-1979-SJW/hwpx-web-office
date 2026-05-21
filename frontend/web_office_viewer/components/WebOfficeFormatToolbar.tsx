/* WebOfficeFormatToolbar — WEB-OFFICE-PARA-EDIT-APPLYFORMAT-MATCHING-
 * EXISTING-CHARPR-01.
 *
 * Bold / Underline / Italic 토글 버튼. existing charPrIDRef 만 적용
 * 가능 — matching 결과가 null 이면 disabled. 본 컴포넌트는 직접
 * makeApplyFormatCommand 를 호출하지 않으며, backend writer / save 도
 * 호출하지 않는다. 콜백 onApplyCharPr 로 위임한다.
 *
 * 실험 플래그: 기본 비활성 (enableApplyCommand=false 시 버튼 미노출).
 */
import * as React from "react";
import { matchToggle, MATCH_DIMENSIONS,
  extractAxisValues } from "../format_charpr_matcher.mjs";

export type CharPrDef = {
  charPrId: string;
  fontName: string | null;
  fontFace: string | null;
  fontSizePt: number | null;
  height: number | null;
  textColor: string | null;
  bold: boolean;
  italic: boolean;
  underline: boolean;
};

export interface WebOfficeFormatToolbarProps {
  charPrDefs: Record<string, CharPrDef>;
  currentCharPrId: string | null;
  /** 명시적 opt-in. 기본 false → 버튼 미노출. */
  enableApplyCommand?: boolean;
  /** 클릭 시 matching 된 charPrId 로 콜백. 상위에서
   *  applyFormatToSelection 을 호출한다. */
  onApplyCharPr?: (charPrId: string) => void;
}

const DIM_LABEL: Record<string, string> = {
  bold: "Bold",
  underline: "Underline",
  italic: "Italic",
};

export function WebOfficeFormatToolbar(
  props: WebOfficeFormatToolbarProps,
) {
  const {
    charPrDefs, currentCharPrId,
    enableApplyCommand = false,
    onApplyCharPr,
  } = props;
  // enableApplyCommand=false → 컴포넌트 자체를 렌더하지 않는다.
  if (!enableApplyCommand) {
    return (
      <div
        className="wo-format-toolbar"
        data-component="WebOfficeFormatToolbar"
        data-enabled="false"
        data-applies-format="false" />);
  }
  const currentDef: CharPrDef | undefined = currentCharPrId
    ? charPrDefs[currentCharPrId] ?? undefined
    : undefined;
  // matching 결과를 모든 dimension 에 대해 한 번에 계산.
  const matched: Record<string, string | null> = {};
  for (const dim of MATCH_DIMENSIONS) {
    matched[dim] = currentDef
      ? matchToggle(currentDef, charPrDefs, dim)
      : null;
  }
  const click = (matchedId: string | null) => {
    if (!matchedId || !onApplyCharPr) return;
    onApplyCharPr(matchedId);
  };
  return (
    <div
      className="wo-format-toolbar"
      data-component="WebOfficeFormatToolbar"
      data-enabled="true"
      data-applies-format="true">
      {MATCH_DIMENSIONS.map((dim) => {
        const mId = matched[dim];
        const disabled = !mId || !currentDef || !onApplyCharPr;
        const active = !!currentDef?.[
          dim as "bold" | "italic" | "underline"];
        return (
          <button
            key={dim}
            type="button"
            className={"wo-format-btn wo-fmt-" + dim
                                + (active ? " wo-active" : "")}
            data-dim={dim}
            data-matched-char-pr={mId ?? ""}
            data-disabled={disabled ? "true" : "false"}
            data-active={active ? "true" : "false"}
            disabled={disabled}
            title={disabled
              ? "현재 문서에 매칭되는 기존 스타일이 없습니다."
              : `${DIM_LABEL[dim]} 토글 → charPr #${mId}`}
            onClick={() => click(mId)}>
            {DIM_LABEL[dim]}
          </button>);
      })}
      {/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTSIZE-MATCHING-EXISTING-
        * CHARPR-01: fontSize dropdown. matching 가능한 fontSize 만
        * enabled. 1차 공정 — color/fontName dropdown 미포함. */}
      <FontSizeDropdown
        charPrDefs={charPrDefs}
        currentDef={currentDef}
        onApplyCharPr={onApplyCharPr} />
      {/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-COLOR-MATCHING-EXISTING-
        * CHARPR-01: ColorPalette swatch UI. existing charPr 매칭 가능
        * color 만 enabled. HTML color input / 외부 color picker 라이브러리
        * 모두 미사용. */}
      <ColorPalette
        charPrDefs={charPrDefs}
        currentDef={currentDef}
        onApplyCharPr={onApplyCharPr} />
      {/* WEB-OFFICE-PARA-EDIT-APPLYFORMAT-FONTNAME-MATCHING-EXISTING-
        * CHARPR-01: FontNameDropdown. fontName 만 변경. fontFace 정합
        * 면제 (corpus 실측 fontFace ↔ fontName 다대다). alias/근사
        * 매칭 미적용. 외부 font picker / 시스템 font list 미사용. */}
      <FontNameDropdown
        charPrDefs={charPrDefs}
        currentDef={currentDef}
        onApplyCharPr={onApplyCharPr} />
      <span
        className="wo-format-toolbar-note"
        data-current-char-pr={currentCharPrId ?? ""}>
        <small>existing charPr 매칭 한정 · 신규 style 생성 미지원</small>
      </span>
    </div>);
}


interface FontNameDropdownProps {
  charPrDefs: Record<string, CharPrDef>;
  currentDef: CharPrDef | undefined;
  onApplyCharPr?: (charPrId: string) => void;
}

function FontNameDropdown(props: FontNameDropdownProps) {
  const { charPrDefs, currentDef, onApplyCharPr } = props;
  const candidates = currentDef
    ? extractAxisValues(charPrDefs, "fontName", currentDef)
    : [];
  const currentValue = currentDef?.fontName ?? null;
  const handleChange = (ev: React.ChangeEvent<HTMLSelectElement>) => {
    const v = ev.target.value;
    const cand = candidates.find((c) => String(c.value) === v);
    if (cand && cand.matchedCharPrId && onApplyCharPr) {
      onApplyCharPr(cand.matchedCharPrId);
    }
  };
  return (
    <span
      className="wo-format-fontname"
      data-component="FontNameDropdown"
      data-applies-format="true"
      data-current-fontname={currentValue ?? ""}
      data-candidate-count={candidates.length}>
      <label className="wo-fn-label" htmlFor="wo-fn-select">
        FontName
      </label>
      <select
        id="wo-fn-select"
        className="wo-fontname-select"
        value={currentValue ?? ""}
        onChange={handleChange}
        disabled={!currentDef || !onApplyCharPr
                              || candidates.length === 0}>
        {candidates.length === 0 ? (
          <option value="" disabled>
            (후보 없음)
          </option>
        ) : (
          candidates.map((c) => {
            const name = String(c.value);
            return (
              <option
                key={`fn-${name}`}
                value={name}
                disabled={!c.enabled}
                data-matched-char-pr={c.matchedCharPrId ?? ""}
                data-current={c.current ? "true" : "false"}
                title={c.enabled
                  ? `fontName ${name} → charPr #${c.matchedCharPrId}`
                  : (c.current
                      ? `${name} (현재 선택)`
                      : "현재 문서에 같은 속성 조합의 기존 폰트 스타일이 없습니다.")}>
                {name}
                {c.current ? " (current)" : ""}
                {!c.enabled && !c.current ? " (no match)" : ""}
              </option>);
          })
        )}
      </select>
      {candidates.length === 0 ? (
        <small className="wo-fn-empty">
          현재 문단의 스타일에 대해 변경 가능한 폰트가 없습니다 —
          후속 공정에서 신규 style 생성을 지원합니다.
        </small>
      ) : null}
    </span>);
}


interface ColorPaletteProps {
  charPrDefs: Record<string, CharPrDef>;
  currentDef: CharPrDef | undefined;
  onApplyCharPr?: (charPrId: string) => void;
}

function ColorPalette(props: ColorPaletteProps) {
  const { charPrDefs, currentDef, onApplyCharPr } = props;
  const candidates = currentDef
    ? extractAxisValues(charPrDefs, "textColor", currentDef)
    : [];
  const handleClick = (matchedId: string | null) => {
    if (matchedId && onApplyCharPr) onApplyCharPr(matchedId);
  };
  return (
    <span
      className="wo-format-color"
      data-component="ColorPalette"
      data-applies-format="true"
      data-candidate-count={candidates.length}>
      <span className="wo-color-label">Color</span>
      {candidates.length === 0 ? (
        <small className="wo-color-empty">
          현재 문단의 스타일에 대해 변경 가능한 색이 없습니다 —
          후속 공정에서 신규 style 생성을 지원합니다
        </small>
      ) : (
        candidates.map((c) => {
          const colorValue = String(c.value);
          const disabled = !c.enabled
                                          || !onApplyCharPr
                                          || c.current;
          const title = c.current
            ? "현재 선택된 색상"
            : (c.enabled
                ? `color ${colorValue} → charPr #${c.matchedCharPrId}`
                : "현재 문서에 같은 속성 조합의 기존 색상 스타일이 없습니다.");
          return (
            <button
              key={`color-${colorValue}`}
              type="button"
              className={"wo-color-swatch"
                                  + (c.current ? " wo-current" : "")
                                  + (c.enabled ? " wo-enabled" : " wo-disabled")}
              data-color={colorValue}
              data-matched-char-pr={c.matchedCharPrId ?? ""}
              data-disabled={disabled ? "true" : "false"}
              data-current={c.current ? "true" : "false"}
              disabled={disabled}
              title={title}
              aria-label={`color ${colorValue}`}
              style={{
                backgroundColor: colorValue,
                width: "16px", height: "16px",
                border: "1px solid #ccc",
                display: "inline-block",
                margin: "0 2px",
              }}
              onClick={() => handleClick(c.matchedCharPrId)} />);
        })
      )}
    </span>);
}


interface FontSizeDropdownProps {
  charPrDefs: Record<string, CharPrDef>;
  currentDef: CharPrDef | undefined;
  onApplyCharPr?: (charPrId: string) => void;
}

function FontSizeDropdown(props: FontSizeDropdownProps) {
  const { charPrDefs, currentDef, onApplyCharPr } = props;
  const candidates = currentDef
    ? extractAxisValues(charPrDefs, "fontSizePt", currentDef)
    : [];
  const currentValue = currentDef?.fontSizePt ?? null;
  const handleChange = (ev: React.ChangeEvent<HTMLSelectElement>) => {
    const v = parseFloat(ev.target.value);
    const cand = candidates.find((c) => c.value === v);
    if (cand && cand.matchedCharPrId && onApplyCharPr) {
      onApplyCharPr(cand.matchedCharPrId);
    }
  };
  return (
    <span
      className="wo-format-fontsize"
      data-component="FontSizeDropdown"
      data-current-fontsize={currentValue ?? ""}
      data-candidate-count={candidates.length}>
      <label className="wo-fs-label" htmlFor="wo-fs-select">
        FontSize
      </label>
      <select
        id="wo-fs-select"
        className="wo-fontsize-select"
        data-applies-format="true"
        value={currentValue ?? ""}
        onChange={handleChange}
        disabled={!currentDef || !onApplyCharPr
                              || candidates.length === 0}>
        {candidates.length === 0 ? (
          <option value="" disabled>
            (후보 없음)
          </option>
        ) : (
          candidates.map((c) => (
            <option
              key={`fs-${c.value}`}
              value={c.value}
              disabled={!c.enabled}
              data-matched-char-pr={c.matchedCharPrId ?? ""}
              data-current={c.current ? "true" : "false"}
              title={c.enabled
                ? `${c.value}pt → charPr #${c.matchedCharPrId}`
                : (c.current
                    ? `${c.value}pt (현재 선택)`
                    : "현재 문서에 같은 속성 조합의 기존 스타일이 없습니다.")}>
              {c.value}pt
              {c.current ? " (current)" : ""}
              {!c.enabled && !c.current ? " (no match)" : ""}
            </option>))
        )}
      </select>
    </span>);
}
