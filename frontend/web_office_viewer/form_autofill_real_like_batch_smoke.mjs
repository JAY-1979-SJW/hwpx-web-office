const PASS_VERDICT = "PASS_REAL_LIKE_SANDBOX_BATCH";
const SANDBOX_MODE = "SANDBOX_ONLY";

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
  const failReasons = [];
  if (batch.mode !== SANDBOX_MODE) failReasons.push("mode");
  if ((s.readbackFail || 0) > 0) failReasons.push("readbackFail");
  if ((s.unexpectedMutation || 0) > 0) failReasons.push("unexpectedMutation");
  if ((s.sourceMutation || 0) > 0) failReasons.push("sourceMutation");
  if ((s.piiLeak || 0) > 0) failReasons.push("piiLeak");
  if ((s.rawPathLeak || 0) > 0) failReasons.push("rawPathLeak");
  if ((s.rawFilenameLeak || 0) > 0) failReasons.push("rawFilenameLeak");

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
        kv("verdict", batch.overallVerdict),
        kv("mode", batch.mode),
        kv("processed", String(s.processed)),
        kv("written", String(s.writtenFiles)),
        kv("blocked", String(s.blockedFiles)),
        kv("failed", String(s.failedFiles || 0)),
      ),
      limitPanel("limit-1-result", "limit=1", batch.limitRuns.limit1),
      limitPanel("limit-5-result", "limit=5", batch.limitRuns.limit5),
      limitPanel("limit-10-result", "limit=10", batch.limitRuns.limit10),
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
        kv("reason", ui.reasons.join(", ") || "none"),
      ),
    ),
  );
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

