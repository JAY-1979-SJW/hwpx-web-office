/* FormAutoFillWorkspace — HWPX 자동작성 파이프라인 UI 컴포넌트 (CONTRACT).
 *
 * HWPX-FORM-AUTO-FILL-WRITER-API-ROUTE-AND-FRONTEND-07
 *
 * 절대 금지:
 *   - 원본 HWPX 직접 수정
 *   - sourceMutationAllowed = true
 *   - mode != "SANDBOX_ONLY"
 *   - raw path / raw filename / PII 원문 화면 노출
 *   - AI API / OCR 직접 호출
 *
 * 버튼 활성화 조건:
 *   approvalStatus == "READY_FOR_WRITER"
 *   && approvedFields >= 1
 *   && missingRequired == 0
 *   && needsReviewRemaining == 0
 *   && attachmentsMissing == 0
 *   && mode == "SANDBOX_ONLY"
 */

import * as React from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type ApprovalStatus =
  | "READY_FOR_WRITER"
  | "BLOCKED_NEEDS_REVIEW"
  | "BLOCKED_MISSING_REQUIRED"
  | "BLOCKED_ATTACHMENT_MISSING"
  | "HOLD_BY_USER"
  | "BLOCKED_NO_ELIGIBLE_FIELDS";

export type WriterResultStatus =
  | "SUCCESS"
  | "FAILED_READBACK"
  | "FAILED_SOURCE_MUTATED"
  | "FAILED_OUTPUT_BROKEN"
  | "BLOCKED_NOT_READY";

export type ReviewAction =
  | "ACCEPT_OUTPUT"
  | "REJECT_OUTPUT"
  | "REQUEST_REWRITE"
  | "HOLD_REVIEW";

export interface AutoFillItem {
  fieldKey: string;
  label: string;
  valueHash: string;   // PII 보호: raw value 아님
  confidence: number;
}

export interface ReviewItem {
  fieldKey: string;
  label: string;
  reason: string;
}

export interface MissingItem {
  fieldKey: string;
  label: string;
  required: boolean;
}

export interface AttachmentItem {
  docType: string;
  neededFor: string[];
}

export interface FieldDecision {
  fieldKey: string;
  action: "CONFIRM_FIELD" | "EDIT_VALUE" | "HOLD" | "REQUEST_ATTACHMENT";
  editedValue?: string;
}

export interface WriterResult {
  writerStatus: WriterResultStatus;
  summary: {
    written: number;
    blocked: number;
    readbackPass: number;
    readbackFail: number;
    sourceMutated: boolean;
  };
  output: {
    outputFileId: string;
    outputHash: string;
    downloadEnabled: boolean;
  };
  /** 항상 false — 원본 HWPX 절대 수정 안 함 */
  sourceMutationAllowed: false;
  mode: "SANDBOX_ONLY";
}

export interface FormAutoFillWorkspaceProps {
  formId: string;
  formName: string;
  autoFillItems: AutoFillItem[];
  reviewItems: ReviewItem[];
  missingItems: MissingItem[];
  attachmentItems: AttachmentItem[];
  approvalStatus: ApprovalStatus;
  writerResult?: WriterResult;
  finalExportEnabled?: boolean;
  onDecisions: (decisions: FieldDecision[]) => void;
  onWriteSandbox: () => void;
  onDownloadReview: (action: ReviewAction) => void;
  mode: "SANDBOX_ONLY";
}

// ---------------------------------------------------------------------------
// Button state calculator
// ---------------------------------------------------------------------------

export function computeButtonEnabled(
  approvalStatus: ApprovalStatus,
  approvedFields: number,
  missingRequired: number,
  needsReviewRemaining: number,
  attachmentsMissing: number,
  mode: string,
): boolean {
  return (
    approvalStatus === "READY_FOR_WRITER" &&
    approvedFields >= 1 &&
    missingRequired === 0 &&
    needsReviewRemaining === 0 &&
    attachmentsMissing === 0 &&
    mode === "SANDBOX_ONLY"
  );
}

// ---------------------------------------------------------------------------
// Status label helper
// ---------------------------------------------------------------------------

export function writerStatusLabel(status: WriterResultStatus): string {
  switch (status) {
    case "SUCCESS":               return "작성 완료";
    case "FAILED_READBACK":       return "검증 실패 — readback 불일치";
    case "FAILED_SOURCE_MUTATED": return "위험: 원본 파일 변경 감지";
    case "FAILED_OUTPUT_BROKEN":  return "출력 파일 손상";
    case "BLOCKED_NOT_READY":     return "승인 필요";
    default:                      return "알 수 없음";
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function FormAutoFillWorkspace(props: FormAutoFillWorkspaceProps) {
  const {
    formId, formName,
    autoFillItems, reviewItems, missingItems, attachmentItems,
    approvalStatus, writerResult, finalExportEnabled,
    onDecisions, onWriteSandbox, onDownloadReview,
    mode,
  } = props;

  const approvedCount = autoFillItems.length;
  const missingRequired = missingItems.filter(m => m.required).length;
  const reviewRemaining = reviewItems.length;
  const attachMissing = attachmentItems.length;

  const buttonEnabled = computeButtonEnabled(
    approvalStatus, approvedCount, missingRequired, reviewRemaining, attachMissing, mode,
  );

  // raw path / filename 노출 방지: fileId만 표시
  const outputFileId = writerResult?.output?.outputFileId ?? "";
  const outputHash   = writerResult?.output?.outputHash   ?? "";

  return React.createElement(
    "div",
    { "data-testid": "form-autofill-workspace", "data-form-id": formId },

    // 서식명
    React.createElement("h2", { "data-testid": "form-title" }, formName),

    // SANDBOX 경고
    React.createElement(
      "p",
      { "data-testid": "sandbox-warning", style: { color: "#b45309" } },
      "원본 HWPX는 수정하지 않고 sandbox 복사본에만 작성합니다.",
    ),

    // 자동입력 가능 구역
    React.createElement(
      "section",
      { "data-testid": "auto-fill-ready", "data-count": approvedCount },
      React.createElement("h3", null, `자동입력 가능 (${approvedCount})`),
      ...autoFillItems.map(item =>
        React.createElement(
          "div",
          { key: item.fieldKey, "data-testid": `auto-fill-item-${item.fieldKey}` },
          `${item.label} — confidence: ${item.confidence.toFixed(2)}`,
          // valueHash만 표시 (raw value 아님)
          React.createElement("span", { "data-value-hash": item.valueHash }),
        ),
      ),
    ),

    // 확인 필요 구역
    React.createElement(
      "section",
      { "data-testid": "needs-review", "data-count": reviewRemaining },
      React.createElement("h3", null, `확인 필요 (${reviewRemaining})`),
    ),

    // 누락 필수값 구역
    React.createElement(
      "section",
      { "data-testid": "missing-required", "data-count": missingRequired },
      React.createElement("h3", null, `누락 필수값 (${missingRequired})`),
    ),

    // 필요 첨부서류 구역
    React.createElement(
      "section",
      { "data-testid": "attachment-items", "data-count": attachMissing },
      React.createElement("h3", null, `필요 첨부서류 (${attachMissing})`),
    ),

    // 승인 후 작성 버튼
    React.createElement(
      "button",
      {
        "data-testid": "write-sandbox-button",
        disabled: !buttonEnabled,
        onClick: buttonEnabled ? onWriteSandbox : undefined,
        "data-approval-status": approvalStatus,
        "data-mode": mode,
        "data-source-mutation-allowed": "false",
      },
      "승인 후 작성",
    ),

    // writer 결과 구역
    writerResult && React.createElement(
      "section",
      { "data-testid": "writer-result" },
      React.createElement("h3", null, "작성 결과"),
      React.createElement(
        "p",
        { "data-testid": "writer-status" },
        writerStatusLabel(writerResult.writerStatus),
      ),
      React.createElement(
        "p",
        { "data-testid": "readback-summary" },
        `readback: ${writerResult.summary.readbackPass} PASS / ${writerResult.summary.readbackFail} FAIL`,
      ),
      // output 정보 — fileId/hash만, raw path 없음
      writerResult.output.downloadEnabled && React.createElement(
        "div",
        { "data-testid": "download-info" },
        React.createElement(
          "span",
          { "data-output-file-id": outputFileId, "data-output-hash": outputHash },
          "다운로드 가능",
        ),
      ),
      // 다운로드 검토 버튼
      writerResult.output.downloadEnabled && React.createElement(
        "div",
        { "data-testid": "review-actions" },
        (["ACCEPT_OUTPUT", "REJECT_OUTPUT", "REQUEST_REWRITE", "HOLD_REVIEW"] as ReviewAction[])
          .map(action =>
            React.createElement(
              "button",
              {
                key: action,
                "data-testid": `review-action-${action}`,
                onClick: () => onDownloadReview(action),
              },
              action,
            ),
          ),
      ),
    ),

    // final export 상태
    finalExportEnabled !== undefined && React.createElement(
      "section",
      { "data-testid": "final-export-status" },
      React.createElement(
        "p",
        { "data-testid": "final-export-enabled", "data-value": String(finalExportEnabled) },
        finalExportEnabled ? "최종 산출물 등록 가능" : "최종 산출물 등록 불가",
      ),
    ),
  );
}
