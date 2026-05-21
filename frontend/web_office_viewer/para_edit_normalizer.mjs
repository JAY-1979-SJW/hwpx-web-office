/* para_edit_command 의 정규화/적용 함수 재노출 */
export {
  splitRun, mergeRuns, normalizeParagraph,
  applyCommandToParagraph,
  makeTypeTextCommand, makeReplaceTextRangeCommand,
  makeDeleteTextRangeCommand,
  validateExpectedBefore, validateCharPrPreserved,
  validateParPrPreserved,
  CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE, CT_DELETE_TEXT_RANGE,
  CT_SPLIT_TEXT_RUN, CT_MERGE_TEXT_RUNS,
  POLICY_ANCHOR_CHARPR, POLICY_FOCUS_CHARPR, POLICY_REQUIRES_REVIEW,
  REASON_MERGE_CHARPR_MISMATCH, REASON_REQUIRES_REVIEW,
} from "./para_edit_command.mjs";
