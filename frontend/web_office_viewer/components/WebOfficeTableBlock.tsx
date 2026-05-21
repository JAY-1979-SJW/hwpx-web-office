/* WebOfficeTableBlock — read-only table renderer.
 * 셀에 editable 입력 요소는 절대 부착하지 않는다.
 */
import * as React from "react";
import type { RenderTable, RenderCell } from "./WebOfficeViewer";

interface Props { table: RenderTable; }

export function WebOfficeTableBlock({ table }: Props) {
  const byRow = new Map<number, RenderCell[]>();
  for (const c of table.cells) {
    if (c.isCoveredByMerge) continue;
    if (!byRow.has(c.row)) byRow.set(c.row, []);
    byRow.get(c.row)!.push(c);
  }
  const rows = [...byRow.keys()].sort((a, b) => a - b);
  return (
    <table className="wo-table"
              data-table-id={table.tableId}
              data-row-count={table.rowCount}
              data-col-count={table.colCount}
              data-editable="false"
              data-has-merged={table.hasMergedCells ? "true" : "false"}>
      <tbody>
        {rows.map((r) => {
          const cells = byRow.get(r)!.slice().sort((a, b) => a.col - b.col);
          return (
            <tr key={r} className="wo-row" data-row={r}>
              {cells.map((c) => (
                <td key={c.cellId}
                        className={
                          "wo-cell" +
                          (c.isMergedOrigin ? " wo-cell-merged-origin" : "")}
                        data-cell-id={c.cellId}
                        data-navigation-id={c.navigationId}
                        data-row={c.row} data-col={c.col}
                        data-editable="false"
                        rowSpan={c.rowSpan > 1 ? c.rowSpan : undefined}
                        colSpan={c.colSpan > 1 ? c.colSpan : undefined}>
                  {c.text}
                </td>
              ))}
            </tr>);
        })}
      </tbody>
    </table>);
}
