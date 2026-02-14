
// config.gs
// Central configuration for the Roadmap AI Apps Script UI.

function getRoadmapApiBaseUrl() {
  // Change this to your deployed backend base URL.
  // Example (local): "http://127.0.0.1:8000"
  // Example (prod): "https://your-domain.com"
  return "https://unclotted-johnnie-nonallegorically.ngrok-free.dev";
}

function getRoadmapApiSecret() {
  // For now we read from Script Properties (recommended).
  // We'll set this value in the next step.
  const props = PropertiesService.getScriptProperties();
  return props.getProperty("ROADMAP_AI_SECRET") || "";
}



// api.gs
// Low-level HTTP helpers to call the backend Action API.

// ---------- Helpers ----------

function _safeJsonParse_(text) {
  if (text == null) return { raw: "" };
  const t = String(text);
  const trimmed = t.trim();

  // HTML response (ngrok error page, gateway, etc.)
  if (
    trimmed.startsWith("<!DOCTYPE") ||
    trimmed.startsWith("<html") ||
    trimmed.startsWith("<HTML")
  ) {
    return { raw: t, _isHtml: true };
  }

  try {
    return JSON.parse(t);
  } catch (e) {
    return { raw: t, _parseError: String(e) };
  }
}

function _request_(method, path, bodyObj) {
  const baseUrl = getRoadmapApiBaseUrl();
  const secret = getRoadmapApiSecret();
  if (!secret) throw new Error("ROADMAP_AI_SECRET is missing in Script Properties.");

  const url = baseUrl.replace(/\/$/, "") + path;

  const options = {
    method: method,
    muteHttpExceptions: true,
    headers: {
      "X-ROADMAP-AI-SECRET": secret,
      // helps prevent ngrok browser-warning HTML pages
      "ngrok-skip-browser-warning": "true",
    },
  };

  if (bodyObj !== undefined) {
    options.contentType = "application/json";
    options.payload = JSON.stringify(bodyObj);
  }

  const res = UrlFetchApp.fetch(url, options);
  const statusCode = res.getResponseCode();
  const text = res.getContentText();
  const parsed = _safeJsonParse_(text);

  return { statusCode: statusCode, text: text, parsed: parsed, url: url };
}

function _formatHttpError_(ctx, hint) {
  const statusCode = ctx.statusCode;
  const parsed = ctx.parsed || {};
  const raw = (ctx.text || "").slice(0, 500);

  const msg =
    parsed.detail ||
    parsed.error ||
    (parsed._isHtml ? "Received HTML (ngrok/gateway page) instead of JSON." : null) ||
    raw ||
    "Unknown error";

  return new Error(
    (hint ? hint + " — " : "") +
      "HTTP " + statusCode + " from " + ctx.url + "\n" +
      msg
  );
}

// ---------- Public API ----------

function postActionRun(actionName, payload) {
  const body = {
    action: actionName,
    scope: payload.scope || {},
    sheet_context: payload.sheet_context || {},
    options: payload.options || {},
    requested_by: payload.requested_by || {},
  };

  const ctx = _request_("post", "/actions/run", body);

  if (ctx.statusCode >= 400) {
    throw _formatHttpError_(ctx, "Action API error");
  }

  // If proxy returned HTML even with 200, treat as hard error for POST.
  if (ctx.parsed && (ctx.parsed._isHtml || ctx.parsed._parseError)) {
    throw new Error(
      "Action API error — Non-JSON response from server\n" +
        (ctx.text || "").slice(0, 500)
    );
  }

  // Expected: { run_id: "...", status: "queued" }
  return ctx.parsed;
}

function getActionRun(runId) {
  const ctx = _request_("get", "/actions/run/" + encodeURIComponent(runId));

  if (ctx.statusCode >= 400) {
    throw _formatHttpError_(ctx, "Get run status failed");
  }

  // If it’s not valid JSON, treat as transient and keep polling.
  if (ctx.parsed && (ctx.parsed._isHtml || ctx.parsed._parseError)) {
    return {
      run_id: runId,
      status: "running", // transient proxy glitch; do NOT mark failed
      error: "Non-JSON response from server (transient)",
      raw: (ctx.text || "").slice(0, 200),
    };
  }

  return ctx.parsed;
}

function pollRunUntilDone(runId, tries = 60, sleepMs = 1000) {
  for (let i = 0; i < tries; i++) {
    let r;
    try {
      r = getActionRun(runId);
    } catch (e) {
      // transient network/proxy issues: wait and retry
      Utilities.sleep(sleepMs);
      continue;
    }

    const s = String(r && r.status ? r.status : "").toLowerCase();

    // Terminal states
    if (s === "success" || s === "failed") return r;

    Utilities.sleep(sleepMs);
  }

  return { run_id: runId, status: "timeout" };
}



// selection.gs

function getSelectedInitiativeKeys() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();

  const lastCol = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0].map(h => String(h || '').trim().toLowerCase());

  // Find header with aliases
  let keyColIdx = headers.indexOf('initiative_key');
  if (keyColIdx === -1) keyColIdx = headers.indexOf('initiative key');
  if (keyColIdx === -1) return [];

  const keyCol = keyColIdx + 1; // 1-based
  const headerRow = 1;

  const rangeList = sheet.getActiveRangeList();
  const ranges = rangeList ? rangeList.getRanges() : (sheet.getActiveRange() ? [sheet.getActiveRange()] : []);
  if (!ranges.length) return [];

  const keys = [];
  for (const r of ranges) {
    const startRow = Math.max(r.getRow(), headerRow + 1); // skip header
    const endRow = r.getLastRow();
    const count = endRow - startRow + 1;
    if (count <= 0) continue;

    // Read the key column for only the selected rows in this block
    const colValues = sheet.getRange(startRow, keyCol, count, 1).getValues();
    for (let i = 0; i < count; i++) {
      const v = String(colValues[i][0] || '').trim();
      if (v) keys.push(v);
    }
  }

  return Array.from(new Set(keys));
}



// selection_optimization.gs

function _findHeaderIndex_(headers, aliases) {
  const lower = headers.map(h => String(h || "").trim().toLowerCase());
  for (const a of aliases) {
    const idx = lower.indexOf(String(a).toLowerCase());
    if (idx !== -1) return idx;
  }
  return -1;
}

/**
 * Reads the active sheet (expected Candidates tab) and returns initiative_keys
 * where is_selected_for_run is TRUE.
 *
 * Respects your sheet structure: row 1 headers, rows 2-3 metadata, row 4+ data.
 */
function getOptimizationSelectedCandidateKeys_() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 4 || lastCol < 1) return [];

  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  const keyIdx = _findHeaderIndex_(headers, ["initiative_key", "initiative key"]);
  const selIdx = _findHeaderIndex_(headers, ["is_selected_for_run", "is selected for run", "selected_for_run"]);

  if (keyIdx === -1) throw new Error("Candidates tab missing initiative_key column.");
  if (selIdx === -1) throw new Error("Candidates tab missing is_selected_for_run column.");

  // Read data rows from row 4+
  const numRows = lastRow - 3;
  const values = sheet.getRange(4, 1, numRows, lastCol).getValues();

  const keys = [];
  for (let i = 0; i < values.length; i++) {
    const row = values[i];
    const key = String(row[keyIdx] || "").trim();
    const flag = row[selIdx];

    // Google Sheets checkboxes often return true/false boolean
    const isTrue = (flag === true) || (String(flag || "").trim().toLowerCase() === "true");

    if (key && isTrue) keys.push(key);
  }

  return Array.from(new Set(keys));
}


// selection_optimization.gs

function _findHeaderIndex_(headers, aliases) {
  const lower = headers.map(h => String(h || "").trim().toLowerCase());
  for (const a of aliases) {
    const idx = lower.indexOf(String(a).toLowerCase());
    if (idx !== -1) return idx;
  }
  return -1;
}

/**
 * Reads the active sheet (expected Candidates tab) and returns initiative_keys
 * where is_selected_for_run is TRUE.
 *
 * Respects your sheet structure: row 1 headers, rows 2-3 metadata, row 4+ data.
 */
function getOptimizationSelectedCandidateKeys_() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 4 || lastCol < 1) return [];

  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  const keyIdx = _findHeaderIndex_(headers, ["initiative_key", "initiative key"]);
  const selIdx = _findHeaderIndex_(headers, ["is_selected_for_run", "is selected for run", "selected_for_run"]);

  if (keyIdx === -1) throw new Error("Candidates tab missing initiative_key column.");
  if (selIdx === -1) throw new Error("Candidates tab missing is_selected_for_run column.");

  // Read data rows from row 4+
  const numRows = lastRow - 3;
  const values = sheet.getRange(4, 1, numRows, lastCol).getValues();

  const keys = [];
  for (let i = 0; i < values.length; i++) {
    const row = values[i];
    const key = String(row[keyIdx] || "").trim();
    const flag = row[selIdx];

    // Google Sheets checkboxes often return true/false boolean
    const isTrue = (flag === true) || (String(flag || "").trim().toLowerCase() === "true");

    if (key && isTrue) keys.push(key);
  }

  return Array.from(new Set(keys));
}


/**
 * UI: Populate Optimization Candidates
 * Action: pm.populate_candidates
 */
function uiOptPopulateCandidates() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const resolved = resolveOptimizationScenarioAndCset_({
    allowPromptFallback: true
  });
  if (!resolved) return;

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: sheet.getName(),
    },
    options: {
      scenario_name: resolved.scenarioName,
      constraint_set_name: resolved.constraintSetName,
    },
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast(
    `Populating candidates\nScenario: ${resolved.scenarioName}\nConstraint set: ${resolved.constraintSetName}`,
    "Roadmap AI",
    5
  );

  try {
    const started = postActionRun("pm.populate_candidates", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 120, 1000);
    showRunToast_(done, "Populate Optimization Candidates");
  } catch (e) {
    ss.toast(
      "Failed to start populate candidates:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}

/**
 * UI: Run Optimization (Selected Candidates)
 * Action: pm.optimize_run_selected_candidates
 */
function uiOptRunSelectedCandidates() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const selectedKeys = getSelectedInitiativeKeys();
  if (!selectedKeys.length) {
    ss.toast("No initiative_key selected.", "Roadmap AI", 5);
    return;
  }

  const resolved = resolveOptimizationScenarioAndCset_({
    allowPromptFallback: true
  });
  if (!resolved) return;

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: sheet.getName(),
    },
    scope: {
      initiative_keys: selectedKeys,
    },
    options: {
      scenario_name: resolved.scenarioName,
      constraint_set_name: resolved.constraintSetName,
    },
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast(
    `Running optimization (SELECTED)\nCandidates: ${selectedKeys.length}`,
    "Roadmap AI",
    5
  );

  try {
    const started = postActionRun(
      "pm.optimize_run_selected_candidates",
      payload
    );
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 240, 1000);
    showRunToast_(done, "Optimization (Selected)");
  } catch (e) {
    ss.toast(
      "Failed to start optimization:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}


/**
 * UI: Run Optimization (All Candidates)
 * Action: pm.optimize_run_all_candidates
 */
function uiOptRunAllCandidates() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const resolved = resolveOptimizationScenarioAndCset_({
    allowPromptFallback: true
  });
  if (!resolved) return;

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: sheet.getName(),
    },
    options: {
      scenario_name: resolved.scenarioName,
      constraint_set_name: resolved.constraintSetName,
    },
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast(
    `Running optimization (ALL candidates)\nScenario: ${resolved.scenarioName}`,
    "Roadmap AI",
    5
  );

  try {
    const started = postActionRun(
      "pm.optimize_run_all_candidates",
      payload
    );
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 240, 1000);
    showRunToast_(done, "Optimization (All Candidates)");
  } catch (e) {
    ss.toast(
      "Failed to start optimization:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}


// settings_reader.gs
// Reads Optimization Center Settings tab and resolves scenario/constraint set,
// with UI prompt fallback.

function getOptimizationSettings_() {
  const ss = SpreadsheetApp.getActive();
  const sh = ss.getSheetByName("Settings");
  if (!sh) return {};

  const lastRow = sh.getLastRow();
  if (lastRow < 2) return {};

  // Read key/value pairs from A2:B
  const values = sh.getRange(2, 1, lastRow - 1, 2).getValues();
  const out = {};
  for (const row of values) {
    const k = String(row[0] || "").trim();
    const v = String(row[1] || "").trim();
    if (!k) continue;
    out[k] = v;
  }
  return out;
}

/**
 * Resolve scenario/constraint set for Optimization Center actions.
 * Priority:
 *  1) Settings tab values
 *  2) UI prompt fallback
 *
 * Returns:
 *  { scenarioName, constraintSetName, source }
 *  or null if user cancels / missing required values
 */
function resolveOptimizationScenarioAndCset_(opts) {
  opts = opts || {};
  const allowPromptFallback = opts.allowPromptFallback !== false;

  const cfg = getOptimizationSettings_();
  let scenarioName = String(cfg.current_scenario_name || "").trim();
  let constraintSetName = String(cfg.current_constraint_set_name || "").trim();

  if (scenarioName && constraintSetName) {
    return { scenarioName, constraintSetName, source: "settings" };
  }

  if (!allowPromptFallback) return null;

  // Prompt fallback
  const ui = SpreadsheetApp.getUi();
  const ss = SpreadsheetApp.getActive();

  if (!scenarioName) {
    const resp = ui.prompt(
      "Optimization: Scenario name",
      "Enter scenario_name (or set Settings!current_scenario_name).",
      ui.ButtonSet.OK_CANCEL
    );
    if (resp.getSelectedButton() !== ui.Button.OK) return null;
    scenarioName = String(resp.getResponseText() || "").trim();
  }

  if (!constraintSetName) {
    const resp2 = ui.prompt(
      "Optimization: Constraint set name",
      "Enter constraint_set_name (or set Settings!current_constraint_set_name).",
      ui.ButtonSet.OK_CANCEL
    );
    if (resp2.getSelectedButton() !== ui.Button.OK) return null;
    constraintSetName = String(resp2.getResponseText() || "").trim();
  }

  if (!scenarioName || !constraintSetName) {
    ss.toast("Scenario name and constraint set name are required.", "Roadmap AI", 6);
    return null;
  }

  return { scenarioName, constraintSetName, source: "prompt" };
}



/**
 * Small UX helper
 * Assumes backend returns status: queued/running/success/failed
 */
function showRunToast_(run, title) {
  const status = String(run?.status || "").toLowerCase();

  if (status === "success") {
    SpreadsheetApp.getActive().toast("Success ✅", title, 5);
    return;
  }
  if (status === "failed") {
  const err = run?.error || run?.error_message || run?.raw || "Unknown error";
  SpreadsheetApp.getActive().toast(String(err).slice(0, 120), title + " ❌", 10);
  return;
  }
  SpreadsheetApp.getActive().toast(`Status: ${status}`, title, 6);
}


// ui_optimization_explain.gs
// UI handler for Optimization Center: pm.explain_selection
// Depends on:
// - resolveOptimizationScenarioAndCset_(opts)
// - getSelectedInitiativeKeys()
// - postActionRun(actionName, payload)
// - pollRunUntilDone(runId, tries, sleepMs)
// - showRunToast_(run, title)

function uiExplainSelection() {
  const ss = SpreadsheetApp.getActive();
  const spreadsheetId = ss.getId();
  const ui = SpreadsheetApp.getUi();

  // 1) Resolve scenario + constraint set (Settings tab first, then prompt fallback)
  const cfg = resolveOptimizationScenarioAndCset_({ allowPromptFallback: true });
  if (!cfg) {
    ss.toast("Cancelled or missing scenario/constraint set.", "🧠 Explain selection", 6);
    return;
  }

  const scenarioName = String(cfg.scenarioName || "").trim();
  const constraintSetName = String(cfg.constraintSetName || "").trim();

  if (!scenarioName || !constraintSetName) {
    ss.toast("Scenario name and constraint set name are required.", "🧠 Explain selection", 6);
    return;
  }

  // 2) Toggle: sync_candidates_first
  const resp = ui.alert(
    "Explain selection — Sync candidates first?",
    "YES: sync Candidates editable fields to DB before explaining.\n" +
      "NO: do not sync candidates first (read-only explain).\n" +
      "CANCEL: abort.",
    ui.ButtonSet.YES_NO_CANCEL
  );
  if (resp === ui.Button.CANCEL) return;
  const syncCandidatesFirst = (resp === ui.Button.YES);

  // 3) Optional explicit key override from current selection
  const keys = getSelectedInitiativeKeys();
  const useExplicitKeys = Array.isArray(keys) && keys.length > 0;

  // 4) Build payload
  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      // Optional overrides (backend supports these per your latest action)
      candidates_tab: "Candidates",
      scenario_config_tab: "Scenario_Config",
      constraints_tab: "Constraints",
      targets_tab: "Targets",
    },
    options: {
      scenario_name: scenarioName,
      constraint_set_name: constraintSetName,
      sync_candidates_first: syncCandidatesFirst,
    },
    scope: useExplicitKeys
      ? { type: "selection", initiative_keys: keys }
      : { type: "selection" }, // backend reads is_selected_for_run from Candidates
    requested_by: { ui: "apps_script" },
  };

  // 5) Start action
  ss.toast(
    `Explaining selection...\nScenario: ${scenarioName}\nConstraint set: ${constraintSetName}`,
    "🧠 Explain selection",
    8
  );

  let started;
  try {
    started = postActionRun("pm.explain_selection", payload);
  } catch (e) {
    ss.toast(
      "Failed to start: " + (e && e.message ? e.message : e),
      "🧠 Explain selection",
      10
    );
    return;
  }

  ss.toast(`Queued: ${started.run_id}`, "🧠 Explain selection", 6);

  // 6) Poll
  const finalResult = pollRunUntilDone(started.run_id, 120, 1000);
  showRunToast_(finalResult, "🧠 Explain selection");

  // 7) Optional: show top violation in a dialog for faster UX
  // Tool response shape is usually { status, result_json: { raw, summary }, ... }
  try {
    if (String(finalResult?.status || "").toLowerCase() === "success") {
      const raw = finalResult?.result_json?.raw || {};
      const feasible = !!raw.is_feasible;
      const v0 = raw?.evaluation?.violations?.[0];

      if (!feasible && v0) {
        ui.alert(
          "Top violation",
          `${v0.code}\n\n${v0.message}`,
          ui.ButtonSet.OK
        );
      }
    }
  } catch (e) {
    // best-effort only
  }
}