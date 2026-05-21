/* WebOfficeFormatPreview — WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-
 * PREVIEW-01.
 *
 * read-only 컴포넌트. payload.styles.charPrDefs + 현재 active paragraph
 * 의 run charPrIDRef 분포를 사람 친화적으로 표시한다.
 *
 * 본 컴포넌트는:
 *   - makeApplyFormatCommand 를 호출하지 않는다.
 *   - commandLog 를 변경하지 않는다.
 *   - 어떤 writer / save API 도 호출하지 않는다.
 *   - 클릭/적용 버튼이 없다 (정보 디스플레이 한정).
 *
 * 실험 플래그: 기본 비활성. window.__woFormatPreview === true 일 때만
 * 마운트되도록 호출자가 게이트한다.
 */
import * as React from "react";

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

export type ParaRunRef = {
  runId: string;
  text: string;
  charPrIDRef: string | null;
};

export interface WebOfficeFormatPreviewProps {
  /** payload.styles.charPrDefs — header.xml charPr 정의 dict. */
  charPrDefs: Record<string, CharPrDef>;
  /** 현재 active paragraph 의 runs (paragraphInventory 대용). */
  activeRuns: ParaRunRef[] | null;
  /** 현재 선택/캐럿이 가리키는 run 의 charPrIDRef (null 이면 미선택). */
  currentCharPrId: string | null;
  /** 문서 전체 charPr 후보까지 표시할지 (기본 false — paragraph 단위). */
  showDocumentScope?: boolean;
  /** WEB-OFFICE-PARA-EDIT-APPLYFORMAT-TOOLBAR-COMMAND-01: 명시적 opt-in.
   *  기본 false — abebab6 read-only preview 동작 그대로. true 일 때만
   *  charPr 후보가 클릭 가능해지고 onApplyCharPr 콜백이 호출된다. */
  enableApplyCommand?: boolean;
  /** charPr 후보 클릭 시 콜백. 상위 콜백이 applyFormatToSelection 을
   *  호출하도록 한다. 본 컴포넌트는 직접 state mutation 을 하지 않는다. */
  onApplyCharPr?: (charPrId: string) => void;
}

function _formatAttrs(def: CharPrDef | undefined): string {
  if (!def) return "(정의 없음)";
  const parts: string[] = [];
  if (def.fontName) parts.push(def.fontName);
  if (def.fontSizePt != null) parts.push(`${def.fontSizePt}pt`);
  if (def.textColor) parts.push(def.textColor);
  const flags: string[] = [];
  if (def.bold) flags.push("Bold");
  if (def.italic) flags.push("Italic");
  if (def.underline) flags.push("Underline");
  if (flags.length > 0) parts.push(flags.join(" "));
  return parts.join(" · ") || "(속성 없음)";
}

/* paragraph 단위 charPrId 사용 카운트 (JS 측 즉시 집계 — Python helper
 * 호출 0). */
function _paragraphInventory(
  runs: ParaRunRef[] | null,
): Array<{ charPrId: string | null; usageCount: number }> {
  if (!runs) return [];
  const counter = new Map<string | null, number>();
  for (const r of runs) {
    counter.set(r.charPrIDRef, (counter.get(r.charPrIDRef) ?? 0) + 1);
  }
  return Array.from(counter.entries())
    .map(([charPrId, usageCount]) => ({ charPrId, usageCount }))
    .sort((a, b) => b.usageCount - a.usageCount);
}

export function WebOfficeFormatPreview(
  props: WebOfficeFormatPreviewProps,
) {
  const {
    charPrDefs, activeRuns, currentCharPrId,
    showDocumentScope = false,
    enableApplyCommand = false,
    onApplyCharPr,
  } = props;

  const currentDef = currentCharPrId
    ? charPrDefs[currentCharPrId] ?? undefined
    : undefined;
  const paraEntries = _paragraphInventory(activeRuns);
  // 기본 read-only 모드 (abebab6 동작 유지). enableApplyCommand=true 시
  // 후보 항목이 클릭 가능 → onApplyCharPr 콜백 호출.
  const readOnlyMode = !enableApplyCommand;
  const dataReadOnly = readOnlyMode ? "true" : "false";
  const dataAppliesFormat = readOnlyMode ? "false" : "true";

  return (
    <div
      className="wo-format-preview"
      data-component="WebOfficeFormatPreview"
      data-read-only={dataReadOnly}
      data-applies-format={dataAppliesFormat}>
      <section className="wo-format-preview-current">
        <h4>현재 선택 charPr</h4>
        <dl>
          <dt>charPrId</dt>
          <dd data-current-char-pr={currentCharPrId ?? ""}>
            {currentCharPrId ?? "(선택 없음)"}
          </dd>
          <dt>속성</dt>
          <dd>{_formatAttrs(currentDef)}</dd>
        </dl>
      </section>

      <section className="wo-format-preview-paragraph">
        <h4>현재 문단의 charPr 후보</h4>
        {paraEntries.length === 0 ? (
          <p className="wo-empty">(active paragraph 없음)</p>
        ) : (
          <ul>
            {paraEntries.map((e) => {
              const def = e.charPrId
                ? charPrDefs[e.charPrId] ?? undefined
                : undefined;
              const isCurrent = e.charPrId === currentCharPrId;
              const clickable = (
                !readOnlyMode
                && !!onApplyCharPr
                && !!e.charPrId
                && !isCurrent);
              return (
                <li
                  key={`${e.charPrId ?? "null"}`}
                  data-char-pr={e.charPrId ?? ""}
                  data-usage-count={e.usageCount}
                  data-clickable={clickable ? "true" : "false"}
                  data-current={isCurrent ? "true" : "false"}>
                  {clickable ? (
                    <button
                      type="button"
                      className="wo-apply-charpr"
                      onClick={() => onApplyCharPr!(
                        e.charPrId as string)}>
                      <strong>#{e.charPrId}</strong>
                      {" — "}
                      {_formatAttrs(def)}
                      <span className="wo-usage">
                        {" "}
                        × {e.usageCount}
                      </span>
                    </button>
                  ) : (
                    <span
                      className={isCurrent
                                              ? "wo-current"
                                              : "wo-noclick"}>
                      <strong>#{e.charPrId ?? "(없음)"}</strong>
                      {" — "}
                      {_formatAttrs(def)}
                      <span className="wo-usage">
                        {" "}
                        × {e.usageCount}
                      </span>
                    </span>
                  )}
                </li>);
            })}
          </ul>
        )}
      </section>

      {showDocumentScope ? (
        <section className="wo-format-preview-document">
          <h4>문서 전체 charPr 정의</h4>
          <ul>
            {Object.values(charPrDefs).map((d) => (
              <li
                key={d.charPrId}
                data-char-pr={d.charPrId}>
                <strong>#{d.charPrId}</strong>
                {" — "}
                {_formatAttrs(d)}
              </li>))}
          </ul>
        </section>
      ) : null}

      <footer className="wo-format-preview-note">
        <small>
          read-only preview · ApplyFormat 명령 미발급 · writer 무호출
        </small>
      </footer>
    </div>);
}
