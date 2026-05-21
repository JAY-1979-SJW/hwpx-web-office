/* WebOfficeViewer — read-only viewer 진입 컴포넌트 (RO-VIEW).
 * 편집 입력 요소 금지. props.payload.editable === false 만 수용.
 */
import * as React from "react";
import { WebOfficeTableBlock } from "./WebOfficeTableBlock";
import { WebOfficeParagraphBlock } from "./WebOfficeParagraphBlock";
import { WebOfficePayloadSummary } from "./WebOfficePayloadSummary";

export type RenderCell = {
  cellId: string; navigationId: string;
  row: number; col: number; rowSpan: number; colSpan: number;
  isCoveredByMerge: boolean; isMergedOrigin: boolean;
  text: string; editable: false;
};
export type RenderTable = {
  tableId: string; blockId: string; sectionIndex: number;
  rowCount: number; colCount: number; visualColCount: number;
  hasMergedCells: boolean; cells: RenderCell[]; editable: false;
};
export type RenderParagraph = {
  paragraphId: string; text: string; parPrIDRef: string | null;
  runs: { runId: string; text: string; charPrIDRef: string | null }[];
  editable: false;
};
export type RenderBlock = {
  blockId: string; type: "paragraph" | "table" | "object";
  sectionIndex: number; blockIndex: number; ref: string | null;
  editable: false; paragraph?: RenderParagraph;
};
export type RenderPayload = {
  schemaVersion: string; engineVersion: string; payloadVersion: string;
  documentId: string; editable: false;
  sourceRef: { sha256: string; path: string };
  pages: { sectionIndex: number; sourceXmlPath: string | null;
                editable: false }[];
  blocks: RenderBlock[];
  tables: RenderTable[];
  objects: { objectId: string; kind: string; sectionIndex: number;
                    placeholder: boolean; editable: false }[];
  warnings: Record<string, unknown>[];
};

export interface WebOfficeViewerProps {
  payload: RenderPayload;
  title?: string;
}

export function WebOfficeViewer(props: WebOfficeViewerProps) {
  const { payload, title } = props;
  if (payload.editable !== false) {
    throw new Error("payload editable!=false — RO-VIEW only");
  }
  const tableMap = new Map<string, RenderTable>();
  for (const t of payload.tables) tableMap.set(t.tableId, t);

  return (
    <div className="web-office-viewer" data-editable="false"
              data-schema={payload.schemaVersion}
              data-engine={payload.engineVersion}
              data-payload={payload.payloadVersion}>
      <header className="wo-toolbar" data-editable="false">
        <div className="wo-toolbar-title">
          {title ?? `Document ${payload.documentId}`}
        </div>
        <div className="wo-toolbar-mode" data-mode="read-only">읽기 전용</div>
        <div className="wo-toolbar-zoom" data-zoom="100">100%</div>
      </header>
      <div className="wo-body">
        <aside className="wo-left-panel" data-editable="false">
          <h3>표 목록</h3>
          <ul className="wo-table-list">
            {payload.tables.map((t) => (
              <li key={t.tableId} data-table-id={t.tableId}>
                {t.tableId} ({t.rowCount}×{t.colCount})
              </li>
            ))}
          </ul>
        </aside>
        <main className="wo-center" data-editable="false">
          {payload.blocks.map((b) => {
            if (b.type === "table" && b.ref) {
              const tbl = tableMap.get(b.ref);
              if (tbl) return (
                <WebOfficeTableBlock key={b.blockId} table={tbl} />);
            }
            if (b.type === "paragraph" && b.paragraph) {
              return (
                <WebOfficeParagraphBlock
                  key={b.blockId}
                  paragraph={b.paragraph} />);
            }
            return (
              <div key={b.blockId} className="wo-block-other"
                        data-block-id={b.blockId}
                        data-type={b.type} data-editable="false" />);
          })}
        </main>
        <aside className="wo-right-panel" data-editable="false">
          <WebOfficePayloadSummary payload={payload} />
        </aside>
      </div>
    </div>
  );
}
