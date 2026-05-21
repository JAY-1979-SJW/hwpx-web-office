"""para_edit_model 의 정규화/적용 함수 재노출 — 외부 호출 면.

- split_run / merge_runs / normalize_paragraph
- apply_command_to_paragraph
- 정합성 검증 함수
"""
from .para_edit_model import (  # noqa: F401
    Paragraph, ParaTextRun, ParagraphTarget,
    CaretPoint, TextRange, EditCommandV2,
    # constants
    CT_SET_CELL_TEXT, CT_TYPE_TEXT, CT_REPLACE_TEXT_RANGE,
    CT_DELETE_TEXT_RANGE, CT_SET_PARAGRAPH_TEXT_SAFE,
    CT_SPLIT_TEXT_RUN, CT_MERGE_TEXT_RUNS,
    POLICY_ANCHOR_CHARPR, POLICY_FOCUS_CHARPR,
    POLICY_REQUIRES_REVIEW,
    REASON_MERGE_CHARPR_MISMATCH,
    REASON_EXPECTED_BEFORE_MISMATCH,
    REASON_STALE_SESSION, REASON_UNSAFE_MULTI_STYLE_PARA,
    REASON_REQUIRES_REVIEW,
    # factories
    make_type_text_command, make_replace_text_range_command,
    make_delete_text_range_command,
    make_split_text_run_command, make_merge_text_runs_command,
    # apply / normalize
    apply_command_to_paragraph, normalize_paragraph,
    split_run, merge_runs, locate_offset, text_in_range,
    # validation
    validate_expected_before, validate_charpr_preserved,
    validate_parpr_preserved, validate_source_document_hash,
)
