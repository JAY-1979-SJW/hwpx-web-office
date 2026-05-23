const PASS_VERDICT = "PASS_REAL_LIKE_SANDBOX_BATCH";
const SANDBOX_MODE = "SANDBOX_ONLY";
const API_ENDPOINTS = {
  health: "/api/hwpx/form-autofill/batch/health",
  run: "/api/hwpx/form-autofill/batch/real-like-sandbox",
  result: (batchId) => `/api/hwpx/form-autofill/batch/result/${encodeURIComponent(batchId)}`,
};

export function createBatchDashboardScenario(overrides = {}) {
  const base = {
    mode: SANDBOX_MODE,
    overallVerdict: PASS_VERDICT,
    warnings: [
      "WARN_REAL_LIKE_SANITIZED_SAMPLE_ONLY",
      "WARN_SANDBOX_ONLY",
      "WARN_REAL_USER_FILE_NOT_TESTED",
      "WARN_DEPLOY_NOT_PERFORMED",
      "WARN_EXISTING_DIRTY_BASELINE_DOCUMENTED",
    ],
    limitRuns: {
      limit1: {
        overallVerdict: PASS_VERDICT,
        summary: summary(1),
      },
      limit5: {
        overallVerdict: PASS_VERDICT,
        summary: summary(5),
      },
      limit10: {
        overallVerdict: PASS_VERDICT,
        summary: summary(10),
      },
    },
    summary: summary(10),
    selectedLimit: 10,
    apiState: {
      health: "idle",
      status: "idle",
      batchId: "",
      errorCode: "",
    },
    fileResults: [
      fileRow("sample_001"),
      fileRow("sample_002"),
      fileRow("sample_003"),
    ],
    blockedResults: [
      { sampleId: "blocked_001", status: "BLOCKED_PII_RISK", blockedReason: "BLOCKED_PII_RISK", writtenFields: 0 },
      { sampleId: "blocked_002", status: "BLOCKED_NO_TARGET_MAP", blockedReason: "BLOCKED_NO_TARGET_MAP", writtenFields: 0 },
    ],
    blockedBreakdown: {
      BLOCKED_PII_RISK: 1,
      BLOCKED_INVALID_HWPX: 1,
      BLOCKED_NO_TARGET_MAP: 1,
      BLOCKED_AMBIGUOUS_TARGET: 1,
      BLOCKED_LOW_TARGET_CONFIDENCE: 1,
    },
  };
  return deepMerge(base, overrides);
}

export function evaluateBatchUiState(batch) {
  const s = batch.summary || {};
  const security = batch.security || {};
  const failReasons = [];
  const errorCodes = (batch.errors || []).map((error) => error.code);
  const blockedCodes = ["BLOCKED_NON_SANDBOX_MODE", "BLOCKED_REAL_USER_FILE"];
  const failedCodes = ["FAILED_READBACK", "FAILED_SOURCE_MUTATION", "FAILED_UNEXPECTED_MUTATION", "FAILED_SECURITY_LEAK"];

  if (blockedCodes.some((code) => errorCodes.includes(code)) || batch.status === "BLOCKED") {
    return { state: "BLOCKED", reasons: errorCodes.length ? errorCodes : ["blocked"] };
  }
  if (failedCodes.some((code) => errorCodes.includes(code)) || batch.status === "FAILED") {
    return { state: "FAIL", reasons: errorCodes.length ? errorCodes : ["failed"] };
  }
  if (batch.mode !== SANDBOX_MODE) failReasons.push("mode");
  if (batch.sourceMutationAllowed !== undefined && batch.sourceMutationAllowed !== false) {
    failReasons.push("sourceMutationAllowed");
  }
  if ((s.readbackFail || 0) > 0) failReasons.push("readbackFail");
  if ((s.unexpectedMutation || 0) > 0) failReasons.push("unexpectedMutation");
  if ((s.sourceMutation || 0) > 0) failReasons.push("sourceMutation");
  if ((s.piiLeak || 0) > 0) failReasons.push("piiLeak");
  if ((s.rawPathLeak || 0) > 0) failReasons.push("rawPathLeak");
  if ((s.rawFilenameLeak || 0) > 0) failReasons.push("rawFilenameLeak");
  if ((security.piiLeak || 0) > 0) failReasons.push("security.piiLeak");
  if ((security.rawPathLeak || 0) > 0) failReasons.push("security.rawPathLeak");
  if ((security.rawFilenameLeak || 0) > 0) failReasons.push("security.rawFilenameLeak");

  if (failReasons.length) {
    return { state: "FAIL", reasons: failReasons };
  }
  if ((s.blockedFiles || 0) > 0 || (batch.blockedResults || []).length > 0) {
    return { state: "WARN", reasons: ["blockedFiles"] };
  }
  if (batch.overallVerdict === PASS_VERDICT && batch.mode === SANDBOX_MODE) {
    return { state: "PASS", reasons: [] };
  }
  return { state: "FAIL", reasons: ["overallVerdict"] };
}

export function renderRealLikeBatchDashboard(root, batch) {
  root.replaceChildren();
  const ui = evaluateBatchUiState(batch);
  const s = batch.summary;

  root.append(
    el("header", { class: "topbar" },
      el("div", {},
        el("h1", { "data-testid": "page-title" }, "Real-like sandbox batch"),
        el("p", { "data-testid": "sandbox-warning", class: "sandbox-warning" },
          "SANDBOX_ONLY: 원본 HWPX는 수정하지 않고 sandbox 결과만 표시합니다."),
      ),
      el("strong", { "data-testid": "overall-state", class: `state state-${ui.state.toLowerCase()}` }, ui.state),
    ),
    el("main", { class: "dashboard", "data-testid": "browser-batch-dashboard" },
      panel("batch-summary", "Batch summary",
        kv("api status", batch.apiState?.status || batch.status || "static"),
        kv("batchId", batch.apiState?.batchId || batch.batchId || "none"),
        kv("verdict", batch.overallVerdict),
        kv("mode", batch.mode),
        kv("sourceMutationAllowed", String(batch.sourceMutationAllowed === undefined ? false : batch.sourceMutationAllowed)),
        kv("processed", String(s.processed)),
        kv("written", String(s.writtenFiles)),
        kv("blocked", String(s.blockedFiles)),
        kv("failed", String(s.failedFiles || 0)),
      ),
      limitPanel("limit-1-result", "limit=1", batch.limitRuns.limit1),
      limitPanel("limit-5-result", "limit=5", batch.limitRuns.limit5),
      limitPanel("limit-10-result", "limit=10", batch.limitRuns.limit10),
      panel("api-e2e-controls", "API browser E2E",
        el("div", { class: "button-row", "data-testid": "api-limit-controls" },
          limitButton(1, batch.selectedLimit),
          limitButton(5, batch.selectedLimit),
          limitButton(10, batch.selectedLimit),
          el("button", { type: "button", "data-testid": "api-run-batch" }, "Run batch"),
        ),
        kv("selected limit", String(batch.selectedLimit || 10)),
        kv("health", batch.apiState?.health || "idle"),
        kv("batchId", batch.apiState?.batchId || batch.batchId || "none"),
        kv("result", batch.apiState?.status || batch.status || "idle"),
        kv("error", batch.apiState?.errorCode || firstErrorCode(batch) || "none"),
      ),
      panel("file-results", "File results",
        ...batch.fileResults.map((row) =>
          el("div", { class: "row", "data-testid": `file-result-${row.sampleId}` },
            el("span", {}, row.sampleId),
            el("strong", { class: row.status === "SANDBOX_WRITE_PASS" ? "ok" : "bad" }, row.status),
          ),
        ),
      ),
      panel("blocked-results", "Blocked results",
        ...batch.blockedResults.map((row) =>
          el("div", { class: "row warn", "data-testid": `blocked-result-${row.sampleId}` },
            el("span", {}, row.sampleId),
            el("strong", {}, row.blockedReason),
          ),
        ),
      ),
      panel("blocked-breakdown", "Blocked breakdown",
        ...Object.entries(batch.blockedBreakdown).map(([key, value]) => kv(key, String(value))),
      ),
      panel("readback-summary", "Readback result",
        kv("readbackPass", String(total(batch.fileResults, "readbackPass"))),
        kv("readbackFail", String(s.readbackFail)),
        kv("unexpectedMutation", String(s.unexpectedMutation)),
      ),
      panel("source-immutability", "Source immutability",
        kv("sourceMutation", String(s.sourceMutation)),
        kv("sha256 changed", String(any(batch.fileResults, "sourceHashChanged"))),
        kv("mtime changed", String(any(batch.fileResults, "sourceMtimeChanged"))),
      ),
      panel("security-summary", "Security summary",
        kv("piiLeak", String(s.piiLeak)),
        kv("rawPathLeak", String(s.rawPathLeak)),
        kv("rawFilenameLeak", String(s.rawFilenameLeak)),
        kv("aiApi", "0"),
        kv("scanApi", "0"),
        kv("externalEditorRequired", "false"),
      ),
      panel("warnings-panel", "Warnings",
        ...batch.warnings.map((warning) => el("p", { class: "muted" }, warning)),
      ),
      panel("ui-state-matrix", "UI state matrix",
        kv("state", ui.state),
        kv("apiE2E", ui.state),
        kv("reason", ui.reasons.join(", ") || "none"),
      ),
    ),
  );
}

export function createApiBatchPayload(limit) {
  return {
    limit: Number(limit),
    mode: SANDBOX_MODE,
    sourceMutationAllowed: false,
  };
}

export function normalizeApiBatchResponse(response, selectedLimit = 10) {
  const summaryValue = response.summary || {};
  const securityValue = response.security || {};
  const limit = Number(summaryValue.limit || selectedLimit || 10);
  const normalizedSummary = {
    totalCandidates: Number(summaryValue.totalCandidates || summaryValue.processed || limit),
    processed: Number(summaryValue.processed || 0),
    ready: Number(summaryValue.ready || 0),
    writtenFiles: Number(summaryValue.writtenFiles || 0),
    blockedFiles: Number(summaryValue.blockedFiles || 0),
    failedFiles: Number(summaryValue.failedFiles || 0),
    readbackFail: Number(summaryValue.readbackFail || 0),
    unexpectedMutation: Number(summaryValue.unexpectedMutation || 0),
    sourceMutation: Number(summaryValue.sourceMutation || 0),
    piiLeak: Number(securityValue.piiLeak || summaryValue.piiLeak || 0),
    rawPathLeak: Number(securityValue.rawPathLeak || summaryValue.rawPathLeak || 0),
    rawFilenameLeak: Number(securityValue.rawFilenameLeak || summaryValue.rawFilenameLeak || 0),
  };
  const verdict = response.status === "SUCCESS" ? PASS_VERDICT : response.status || "FAILED";
  const scenario = createBatchDashboardScenario({
    mode: response.mode || SANDBOX_MODE,
    sourceMutationAllowed: response.sourceMutationAllowed === undefined ? false : response.sourceMutationAllowed,
    overallVerdict: verdict,
    selectedLimit: limit,
    status: response.status || "FAILED",
    batchId: response.batchId || "",
    summary: normalizedSummary,
    security: securityValue,
    fileResults: response.fileResults || [],
    blockedResults: response.blockedResults || [],
    warnings: response.warnings || [],
    errors: response.errors || [],
    apiState: {
      health: "ok",
      status: response.status || "FAILED",
      batchId: response.batchId || "",
      errorCode: firstErrorCode(response),
    },
  });
  scenario.limitRuns[`limit${limit}`] = {
    overallVerdict: verdict,
    summary: normalizedSummary,
  };
  return scenario;
}

export function installRealLikeBatchApiE2E(root, options = {}) {
  const endpoints = options.endpoints || API_ENDPOINTS;
  const fetcher = options.fetcher || window.fetch.bind(window);
  const state = {
    selectedLimit: 10,
    health: "idle",
    lastBatch: createBatchDashboardScenario(),
  };

  async function runBatch(limit = state.selectedLimit) {
    state.selectedLimit = Number(limit);
    state.health = "checking";
    paint();
    const healthResponse = await fetcher(endpoints.health, { method: "GET" });
    await safeJson(healthResponse);
    state.health = "ok";

    const payload = createApiBatchPayload(state.selectedLimit);
    const runResponse = await fetcher(endpoints.run, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    const runData = await safeJson(runResponse);
    let finalData = runData;
    if (runData.batchId) {
      const resultResponse = await fetcher(endpoints.result(runData.batchId), { method: "GET" });
      finalData = await safeJson(resultResponse);
    }
    const rendered = normalizeApiBatchResponse(finalData, state.selectedLimit);
    rendered.apiState.health = state.health;
    state.lastBatch = rendered;
    paint();
    return { payload, runData, finalData };
  }

  function paint() {
    const batch = deepMerge(state.lastBatch, {
      selectedLimit: state.selectedLimit,
      apiState: { ...(state.lastBatch.apiState || {}), health: state.health },
    });
    renderRealLikeBatchDashboard(root, batch);
    bindControls();
  }

  function bindControls() {
    for (const limit of [1, 5, 10]) {
      root.querySelector(`[data-testid="api-limit-${limit}"]`)?.addEventListener("click", () => {
        state.selectedLimit = limit;
        paint();
      });
    }
    root.querySelector('[data-testid="api-run-batch"]')?.addEventListener("click", () => {
      runBatch(state.selectedLimit).catch((error) => {
        state.lastBatch = createBatchDashboardScenario({
          status: "FAILED",
          overallVerdict: "FAILED",
          selectedLimit: state.selectedLimit,
          errors: [{ code: "FAILED_BROWSER_API_E2E", message: String(error.message || error) }],
          apiState: {
            health: state.health,
            status: "FAILED",
            batchId: "",
            errorCode: "FAILED_BROWSER_API_E2E",
          },
        });
        paint();
      });
    });
  }

  paint();
  return { runBatch, setLimit: (limit) => { state.selectedLimit = Number(limit); paint(); } };
}

function summary(count) {
  return {
    totalCandidates: count,
    processed: count,
    ready: count,
    writtenFiles: count,
    blockedFiles: 0,
    failedFiles: 0,
    readbackFail: 0,
    unexpectedMutation: 0,
    sourceMutation: 0,
    piiLeak: 0,
    rawPathLeak: 0,
    rawFilenameLeak: 0,
  };
}

function fileRow(sampleId) {
  return {
    sampleId,
    status: "SANDBOX_WRITE_PASS",
    sourceHashChanged: false,
    sourceMtimeChanged: false,
    writtenFields: 3,
    readbackPass: 3,
    readbackFail: 0,
    unexpectedMutation: 0,
    finalExportEnabled: true,
  };
}

function limitPanel(testId, title, value) {
  const s = value.summary;
  return panel(testId, title,
    kv("verdict", value.overallVerdict),
    kv("processed", String(s.processed)),
    kv("written", String(s.writtenFiles)),
    kv("readbackFail", String(s.readbackFail)),
  );
}

function limitButton(limit, selectedLimit) {
  return el("button", {
    type: "button",
    "data-testid": `api-limit-${limit}`,
    "aria-pressed": String(Number(selectedLimit || 10) === limit),
  }, `limit=${limit}`);
}

function firstErrorCode(batch) {
  return (batch.errors || [])[0]?.code || "";
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function panel(testId, title, ...children) {
  return el("section", { class: "panel", "data-testid": testId },
    el("h2", {}, title),
    ...children,
  );
}

function kv(label, value) {
  return el("div", { class: "kv" }, el("span", {}, label), el("strong", {}, value));
}

function total(rows, key) {
  return rows.reduce((sum, row) => sum + Number(row[key] || 0), 0);
}

function any(rows, key) {
  return rows.some((row) => Boolean(row[key]));
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name === "class") {
      node.className = value;
    } else if (value !== undefined && value !== null) {
      node.setAttribute(name, value);
    }
  }
  for (const child of children) {
    if (child instanceof Node) {
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
