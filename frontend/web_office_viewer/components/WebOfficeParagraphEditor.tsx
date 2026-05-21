/* WebOfficeParagraphEditor — PARA-EDIT BROWSER 컴포넌트 (Phase 3).
 *
 * 별도 entry — 기존 RO viewer 잠금에 영향 없음.
 * contenteditable 직접 저장은 금지 — 입력은 상태기계 → command 경로로만.
 * writer / save / output / apply 호출 일절 없음.
 */
import * as React from "react";

export type ParaRun = {
  runId: string; text: string; charPrIDRef: string | null;
};
export type Paragraph = {
  paragraphId: string; parPrIDRef: string | null;
  runs: ParaRun[];
};

export interface WebOfficeParagraphEditorProps {
  paragraph: Paragraph;
  active: boolean;
  caretOffset: number;
  rangeAnchor: number | null;
  rangeFocus: number | null;
  compositionActive: boolean;
  /* DOM keydown / composition 이벤트를 외부 상태기계로 위임. */
  onKeyDown: (ev: React.KeyboardEvent<HTMLDivElement>) => void;
  onCompositionStart: (
    ev: React.CompositionEvent<HTMLDivElement>) => void;
  onCompositionUpdate: (
    ev: React.CompositionEvent<HTMLDivElement>) => void;
  onCompositionEnd: (
    ev: React.CompositionEvent<HTMLDivElement>) => void;
  onClickRun: (runId: string, localOffset: number) => void;
}

export function WebOfficeParagraphEditor(
  props: WebOfficeParagraphEditorProps
) {
  const {
    paragraph, active, caretOffset, rangeAnchor, rangeFocus,
    compositionActive,
  } = props;

  // 의도적으로 contenteditable=false. 입력은 외부 상태기계 → command.
  return (
    <div
      className={"wo-paragraph-editor" +
                          (active ? " wo-active" : "")}
      data-paragraph-id={paragraph.paragraphId}
      data-paragraph-mode={
        compositionActive ? "COMPOSITION"
          : rangeAnchor !== null ? "TEXT_RANGE"
          : active ? "CARET" : "NONE"}
      data-caret-offset={caretOffset}
      data-range-anchor={rangeAnchor ?? ""}
      data-range-focus={rangeFocus ?? ""}
      data-contenteditable="false"
      tabIndex={0}
      onKeyDown={props.onKeyDown}
      onCompositionStart={props.onCompositionStart}
      onCompositionUpdate={props.onCompositionUpdate}
      onCompositionEnd={props.onCompositionEnd}>
      {paragraph.runs.map((r, i) => {
        let runStart = 0;
        for (let k = 0; k < i; k++) {
          runStart += paragraph.runs[k].text.length;
        }
        return (
          <span
            key={r.runId}
            className="wo-run"
            data-run-id={r.runId}
            data-char-pr={r.charPrIDRef ?? ""}
            data-run-start={runStart}
            onClick={(ev) => {
              // 클릭 위치로 caret 이동. localOffset 계산은 외부.
              props.onClickRun(r.runId, 0);
              ev.stopPropagation();
            }}>
            {r.text}
          </span>);
      })}
      {active && rangeAnchor === null
        ? <span className="wo-caret" data-caret-offset={caretOffset} />
        : null}
    </div>);
}
