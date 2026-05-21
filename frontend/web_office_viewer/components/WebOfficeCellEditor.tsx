/* WebOfficeCellEditor — CELL-EDIT MVP-A 셀 편집 UI.
 *
 * 이 컴포넌트는 RO-VIEW 잠금 대상이 아니다 (별도 entry point 에서만 사용).
 * 편집 모드(MODE_CELL_EDIT)일 때만 텍스트 입력이 활성화된다.
 *
 * 본 컴포넌트는 writer / apply 호출을 일절 하지 않는다. 모든 변경은
 * commitCellText 를 통해 EditCommand 로 환원되어 undoStack 에 적재된다.
 */
import * as React from "react";

export interface CellEditorProps {
  cellId: string;
  initialText: string;
  mode: "READ_ONLY" | "CELL_SELECT" | "CELL_EDIT";
  onCommit: (next: string) => void;   // commitCellText 호출자
  onCancel: () => void;
}

export function WebOfficeCellEditor(props: CellEditorProps) {
  const { cellId, initialText, mode, onCommit, onCancel } = props;
  const [draft, setDraft] = React.useState(initialText);

  React.useEffect(() => { setDraft(initialText); }, [initialText, mode]);

  if (mode !== "CELL_EDIT") {
    return (
      <span className="wo-cell-text"
                  data-cell-id={cellId}
                  data-editor-mode={mode}>
        {initialText}
      </span>);
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") { e.preventDefault(); onCommit(draft); }
    else if (e.key === "Escape") { e.preventDefault(); onCancel(); }
  };

  return (
    <input
      className="wo-cell-editor-input"
      data-cell-id={cellId}
      data-editor-mode="CELL_EDIT"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={handleKeyDown}
      onBlur={() => onCommit(draft)}
      autoFocus />);
}
