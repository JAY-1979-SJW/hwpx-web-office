const WRITE_SANDBOX_ENDPOINT = "/api/hwpx/form-autofill/write-sandbox";

const BLOCKED_APPROVAL_STATUSES = [
  "BLOCKED_NEEDS_REVIEW",
  "BLOCKED_MISSING_REQUIRED",
  "BLOCKED_ATTACHMENT_MISSING",
  "HOLD_BY_USER",
];

const RESULT_LABELS = {
  SUCCESS: {
    title: "작성 성공",
    readback: "readback 통과",
    source: "원본 변경 없음",
    download: "검토용 다운로드 가능",
    final: "최종 산출물 후보",
    className: "is-success",
  },
  FAILED_READBACK: {
    title: "readback 실패",
    readback: "readback 실패 표시",
    source: "원본 변경 없음",
    download: "다운로드 차단",
    final: "최종 산출물 차단",
    className: "is-failure",
  },
  FAILED_SOURCE_MUTATED: {
    title: "원본 변경 위험 실패",
    readback: "readback 보류",
    source: "원본 변경 위험 실패 표시",
    download: "다운로드 차단",
    final: "최종 산출물 차단",
    className: "is-failure",
  },
  FAILED_OUTPUT_BROKEN: {
    title: "출력 파일 손상",
    readback: "readback 보류",
    source: "원본 변경 없음",
    download: "다운로드 차단",
    final: "최종 산출물 차단",
    className: "is-failure",
  },
};

export function createSyntheticScenario(overrides = {}) {
  const base = {
    formId: "synthetic_form_08",
    displayName: "HWPX 자동작성 브라우저 시운전",
    mode: "SANDBOX_ONLY",
    approvalStatus: "READY_FOR_WRITER",
    writerEligible: true,
    approvedFields: [
      {
        fieldKey: "owner_name",
        label: "신청자",
        maskedValue: "김**",
        valueHash: "hash_owner_001",
        confidence: 0.96,
      },
      {
        fieldKey: "project_code",
        label: "사업 코드",
        maskedValue: "PRJ-****",
        valueHash: "hash_project_002",
        confidence: 0.92,
      },
    ],
    recommend: {
      formType: "공사 제출 서식",
      confidence: 0.94,
      displayName: "추천 서식 A",
    },
    parser: {
      paragraphCount: 18,
      tableCount: 4,
      fieldCandidateCount: 7,
    },
    needsReview: [],
    missingRequired: [],
    requiredAttachments: [],
    writerResult: {
      writerStatus: "SUCCESS",
      readbackFail: 0,
      sourceMutated: false,
      downloadEnabled: true,
      finalExportEnabled: true,
      outputFileId: "out_browser_smoke_08",
      finalExportId: "final_browser_smoke_08",
    },
  };
  return deepMerge(base, overrides);
}

export function computeWriterButtonState(scenario) {
  const approvedCount = Array.isArray(scenario.approvedFields)
    ? scenario.approvedFields.length
    : 0;
  const missingRequired = Array.isArray(scenario.missingRequired)
    ? scenario.missingRequired.length
    : 0;
  const needsReviewRemaining = Array.isArray(scenario.needsReview)
    ? scenario.needsReview.length
    : 0;
  const attachmentsMissing = Array.isArray(scenario.requiredAttachments)
    ? scenario.requiredAttachments.length
    : 0;

  const checks = [
    ["approvalStatus", scenario.approvalStatus === "READY_FOR_WRITER"],
    ["writerEligible", scenario.writerEligible === true],
    ["approvedFields", approvedCount >= 1],
    ["missingRequired", missingRequired === 0],
    ["needsReviewRemaining", needsReviewRemaining === 0],
    ["attachmentsMissing", attachmentsMissing === 0],
    ["mode", scenario.mode === "SANDBOX_ONLY"],
  ];
  const failed = checks.filter(([, ok]) => !ok).map(([name]) => name);
  return {
    enabled: failed.length === 0,
    reasons: failed,
    counts: {
      approvedFields: approvedCount,
      missingRequired,
      needsReviewRemaining,
      attachmentsMissing,
    },
  };
}

export function buildWriteSandboxPayload(scenario) {
  const approvedFields = (scenario.approvedFields || [])
    .filter((field) => field.writerEligible !== false)
    .map((field) => ({
      fieldKey: field.fieldKey,
      label: field.label,
      valueHash: field.valueHash,
      maskedValue: field.maskedValue,
      action: "CONFIRM_FIELD",
      writerEligible: true,
    }));

  return {
    formId: scenario.formId,
    mode: "SANDBOX_ONLY",
    sourceMutationAllowed: false,
    approvalResultDict: {
      approvalStatus: scenario.approvalStatus,
      approvedFields,
      summary: {
        approvedFields: approvedFields.length,
        missingRequired: scenario.missingRequired.length,
        undecidedCount: scenario.needsReview.length,
        attachmentsMissing: scenario.requiredAttachments.length,
      },
    },
  };
}

export function renderFormAutoFillBrowserSmoke(root, scenario) {
  root.replaceChildren();

  const state = computeWriterButtonState(scenario);
  const result = scenario.writerResult;
  const resultLabel = RESULT_LABELS[result.writerStatus] || RESULT_LABELS.FAILED_OUTPUT_BROKEN;

  root.append(
    el("header", { class: "topbar" },
      el("div", { class: "title-group" },
        el("h1", { "data-testid": "form-title" }, scenario.displayName),
        el("p", { "data-testid": "sandbox-warning", class: "sandbox-warning" },
          "원본 HWPX는 수정하지 않고 sandbox 복사본에만 작성합니다."),
      ),
      el("span", { "data-testid": "mode-badge", class: "mode-badge" }, scenario.mode),
    ),
    el("main", { class: "workspace", "data-testid": "form-autofill-workspace" },
      section("recommend-section", "서식 추천 결과",
        row("추천 서식", scenario.recommend.displayName),
        row("분류", scenario.recommend.formType),
        row("신뢰도", scenario.recommend.confidence.toFixed(2)),
      ),
      section("parser-section", "업로드 문서 파싱 결과",
        row("문단", String(scenario.parser.paragraphCount)),
        row("표", String(scenario.parser.tableCount)),
        row("필드 후보", String(scenario.parser.fieldCandidateCount)),
      ),
      section("auto-fill-ready", "자동입력 가능 섹션",
        ...scenario.approvedFields.map((field) =>
          el("div", { class: "field-row", "data-testid": `approved-field-${field.fieldKey}` },
            el("span", {}, field.label),
            el("strong", { "data-value-hash": field.valueHash }, field.maskedValue),
          ),
        ),
      ),
      section("needs-review", "확인 필요 섹션",
        emptyOrList(scenario.needsReview, "확인 필요 항목 없음", "reason"),
      ),
      section("missing-required", "누락 필수값 섹션",
        emptyOrList(scenario.missingRequired, "누락 필수값 없음", "label"),
      ),
      section("required-attachments", "필요 첨부서류 섹션",
        emptyOrList(scenario.requiredAttachments, "누락 첨부서류 없음", "docType"),
      ),
      section("approval-panel", "사람 승인 상태",
        row("상태", scenario.approvalStatus),
        row("승인 필드", String(state.counts.approvedFields)),
        row("확인 필요", String(state.counts.needsReviewRemaining)),
      ),
      el("section", { class: "panel action-panel", "data-testid": "writer-action-panel" },
        el("h2", {}, "승인 후 작성"),
        el("button", {
          type: "button",
          "data-testid": "write-sandbox-button",
          "data-endpoint": WRITE_SANDBOX_ENDPOINT,
          "data-source-mutation-allowed": "false",
          disabled: state.enabled ? undefined : "",
        }, "승인 후 작성"),
        el("p", {
          "data-testid": "button-disabled-reason",
          class: state.enabled ? "muted" : "blocked",
        }, state.enabled ? "READY_FOR_WRITER 조건 충족" : `비활성화 사유: ${state.reasons.join(", ")}`),
      ),
      section("readback-result", "readback 결과",
        el("p", { "data-testid": "writer-status", class: resultLabel.className }, resultLabel.title),
        el("p", { "data-testid": "readback-status" }, resultLabel.readback),
        el("p", { "data-testid": "source-mutation-status" }, resultLabel.source),
      ),
      section("download-review-status", "다운로드 검토 상태",
        el("p", {
          "data-testid": "download-status",
          "data-output-file-id": result.downloadEnabled ? result.outputFileId : "",
        }, result.downloadEnabled ? resultLabel.download : "다운로드 차단"),
      ),
      section("final-export-status", "final export 상태",
        el("p", {
          "data-testid": "final-export-enabled",
          "data-final-export-id": result.finalExportEnabled ? result.finalExportId : "",
        }, result.finalExportEnabled ? resultLabel.final : "최종 산출물 차단"),
      ),
    ),
  );

  const button = root.querySelector('[data-testid="write-sandbox-button"]');
  button.addEventListener("click", async () => {
    if (!computeWriterButtonState(scenario).enabled) {
      return;
    }
    const payload = buildWriteSandboxPayload(scenario);
    const response = await fetch(WRITE_SANDBOX_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    root.dispatchEvent(new CustomEvent("write-sandbox-complete", { detail: body }));
    root.querySelector('[data-testid="writer-status"]').textContent =
      body.status === "SUCCESS" ? "작성 성공" : "작성 실패";
  });
}

function section(testId, title, ...children) {
  return el("section", { class: "panel", "data-testid": testId },
    el("h2", {}, title),
    ...children,
  );
}

function row(label, value) {
  return el("div", { class: "kv" },
    el("span", {}, label),
    el("strong", {}, value),
  );
}

function emptyOrList(items, emptyText, key) {
  if (!items.length) {
    return el("p", { class: "muted" }, emptyText);
  }
  return el("ul", {}, ...items.map((item) => el("li", {}, String(item[key] || item.label || item.docType))));
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value === undefined || value === null) {
      continue;
    }
    if (name === "class") {
      node.className = value;
    } else if (name === "disabled") {
      node.disabled = true;
    } else {
      node.setAttribute(name, value);
    }
  }
  for (const child of children) {
    if (Array.isArray(child)) {
      node.append(...child);
    } else if (child instanceof Node) {
      node.append(child);
    } else if (child !== undefined && child !== null) {
      node.append(document.createTextNode(String(child)));
    }
  }
  return node;
}

function deepMerge(target, source) {
  const output = Array.isArray(target) ? [...target] : { ...target };
  for (const [key, value] of Object.entries(source)) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      output[key] = deepMerge(output[key] || {}, value);
    } else {
      output[key] = value;
    }
  }
  return output;
}
