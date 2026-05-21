/* WebOfficeParagraphBlock — read-only paragraph renderer. */
import * as React from "react";
import type { RenderParagraph } from "./WebOfficeViewer";

interface Props { paragraph: RenderParagraph; }

export function WebOfficeParagraphBlock({ paragraph }: Props) {
  return (
    <div className="wo-paragraph"
            data-paragraph-id={paragraph.paragraphId}
            data-editable="false">
      {paragraph.text}
    </div>);
}
