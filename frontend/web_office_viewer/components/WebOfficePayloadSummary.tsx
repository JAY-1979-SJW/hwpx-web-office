/* WebOfficePayloadSummary — read-only payload summary panel. */
import * as React from "react";
import type { RenderPayload } from "./WebOfficeViewer";

interface Props { payload: RenderPayload; }

export function WebOfficePayloadSummary({ payload }: Props) {
  const warningsCount = (payload.warnings ?? []).length;
  return (
    <div className="wo-payload-summary" data-editable="false">
      <h3>payload summary</h3>
      <dl>
        <dt>documentId</dt><dd>{payload.documentId}</dd>
        <dt>sha256</dt><dd>{payload.sourceRef?.sha256}</dd>
        <dt>blocks</dt><dd>{payload.blocks.length}</dd>
        <dt>tables</dt><dd>{payload.tables.length}</dd>
        <dt>objects</dt><dd>{payload.objects.length}</dd>
      </dl>
      <h3>warnings</h3>
      {warningsCount === 0
        ? <div className="wo-warnings-empty">warnings: 0</div>
        : <ul className="wo-warnings">
            {(payload.warnings ?? []).map((w, i) => (
              <li key={i}>{JSON.stringify(w)}</li>))}
          </ul>}
    </div>);
}
