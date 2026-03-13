# productroadmap_sheet/productroadmap_sheet_project/docs/appsripts/optimization_appscripst.md
// config.gs
// Central configuration for the Roadmap AI Apps Script UI.
// Backend handlers live in [app/services/action_runner.py](app/services/action_runner.py) for `pm.save_optimization`, `pm.populate_candidates`, `pm.optimize_run_selected_candidates`, `pm.optimize_run_all_candidates`, and `pm.explain_selection`. This doc keeps only the Apps Script UI code.

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

// menu.gs

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🧠 Roadmap AI")
    .addItem("Optimization: Populate Candidates", "uiOptPopulateCandidates")
    .addItem("Optimization: Run (Selected for Run)", "uiOptRunSelectedCandidates")
    .addItem("Optimization: Run (All Candidates)", "uiOptRunAllCandidates")
    .addSeparator()
    .addItem("Optimization: Explain Selection", "uiExplainSelection")
    .addItem("Optimization: Save current tab → DB", "uiOptSaveToDb")
    .addItem("Optimization: Save ALL tabs → DB", "uiOptSaveAllToDb")
    .addItem("Optimization: Refresh Instructions", "uiOptRefreshInstructions")
    .addItem("Optimization: Refresh THIS tab's instructions", "uiOptRefreshTabInstructions")
    .addToUi();
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

  // Allow configurable data start row via Settings!candidates_data_start_row, default 4
  const settings = getOptimizationSettings_();
  const dataStartRow = Math.max(2, parseInt(settings.candidates_data_start_row || "5", 10) || 5);

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < dataStartRow || lastCol < 1) return [];

  const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];

  const keyIdx = _findHeaderIndex_(headers, ["initiative_key", "initiative key"]);
  const selIdx = _findHeaderIndex_(headers, ["is_selected_for_run", "is selected for run", "selected_for_run"]);

  if (keyIdx === -1) throw new Error("Candidates tab missing initiative_key column.");
  if (selIdx === -1) throw new Error("Candidates tab missing is_selected_for_run column.");

  // Read data rows from row 4+
  const numRows = lastRow - (dataStartRow - 1);
  const values = sheet.getRange(dataStartRow, 1, numRows, lastCol).getValues();

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


// ui_optimization_save.gs
// UI handler for Optimization Center: pm.save_optimization
// Saves current tab edits → DB (no solver, no results write).
// Tab-aware: Scenario_Config → sync scenarios, Constraints/Targets → sync
// constraint sets, Candidates → sync PM-editable fields.
// With save_all option, syncs all three regardless of active tab.

/**
 * UI: Save Optimization Center edits → DB
 * Action: pm.save_optimization
 *
 * Tab-aware dispatch:
 *   Scenario_Config  → sync scenarios
 *   Constraints/Targets → sync constraint sets
 *   Candidates → sync PM-editable fields (eng_tokens, deadline, category, etc.)
 *   save_all=true → all of the above
 *
 * No solver, no results write — pure sheet→DB persistence.
 */
function uiOptSaveToDb() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();
  const tabName = sheet.getName();

  // Optional: if on Candidates tab, send selected keys for scoped save
  const tabLc = tabName.trim().toLowerCase();
  let initiativeKeys = [];
  if (tabLc.indexOf("candidate") !== -1) {
    initiativeKeys = getSelectedInitiativeKeys();
    if (!initiativeKeys.length) {
      const ui = SpreadsheetApp.getUi();
      const resp = ui.alert(
        "Save ALL candidates?",
        "No rows selected in Candidates. Save ALL candidates to DB?",
        ui.ButtonSet.YES_NO
      );
      if (resp !== ui.Button.YES) {
        ss.toast("Save cancelled.", "Roadmap AI", 5);
        return;
      }
    }
  }

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: tabName,
    },
    scope: initiativeKeys.length > 0
      ? { initiative_keys: initiativeKeys }
      : {},
    options: {},
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast(
    `Saving ${tabName} → DB...`,
    "Roadmap AI",
    5
  );

  try {
    const started = postActionRun("pm.save_optimization", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 120, 1000);
    showRunToast_(done, "Save Optimization → DB");
  } catch (e) {
    ss.toast(
      "Failed to save:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}

/**
 * UI: Save ALL Optimization Center tabs → DB
 * Action: pm.save_optimization (with save_all=true)
 *
 * Syncs scenarios + constraint sets + candidates in one call.
 */
function uiOptSaveAllToDb() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: sheet.getName(),
    },
    scope: {},
    options: {
      save_all: true,
    },
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast("Saving ALL optimization tabs → DB...", "Roadmap AI", 5);

  try {
    const started = postActionRun("pm.save_optimization", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 180, 1000);
    showRunToast_(done, "Save All → DB");
  } catch (e) {
    ss.toast(
      "Failed to save:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}

// ui_optimization_refresh_instructions.gs
/**
 * UI: Refresh instructions rows for Optimization Center tabs
 * Action: pm.refresh_sheet_instructions
 */
function uiOptRefreshInstructions() {
  const ss = SpreadsheetApp.getActive();
  const spreadsheetId = ss.getId();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
    },
    options: {
      sheet_type: "optimization_center",
    },
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast("Refreshing instructions...", "Roadmap AI", 5);

  try {
    const started = postActionRun("pm.refresh_sheet_instructions", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 60, 1000);
    showRunToast_(done, "Refresh Instructions");
  } catch (e) {
    ss.toast(
      "Failed to refresh instructions:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}

/**
 * UI: Refresh instructions row for the active tab only
 * Action: pm.refresh_tab_instructions
 */
function uiOptRefreshTabInstructions() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: sheet.getName(),
    },
    options: {
      sheet_type: "optimization_center",
    },
    requested_by: {
      ui: "apps_script",
      source: "optimization_center",
    },
  };

  ss.toast(`Refreshing instructions for ${sheet.getName()}...`, "Roadmap AI", 5);

  try {
    const started = postActionRun("pm.refresh_tab_instructions", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);

    const done = pollRunUntilDone(started.run_id, 60, 1000);
    showRunToast_(done, "Refresh Tab Instructions");
  } catch (e) {
    ss.toast(
      "Failed to refresh tab instructions:\n" + (e?.message || e),
      "Roadmap AI ❌",
      8
    );
  }
}

// ui_optimization_populatecandidates
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

  const selectedKeys = getOptimizationSelectedCandidateKeys_();
  if (!selectedKeys.length) {
    ss.toast("No candidates marked is_selected_for_run.", "Roadmap AI", 5);
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
    `Running optimization (is_selected_for_run)\nCandidates: ${selectedKeys.length}`,
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


// explain_output.gs
// Writes explain selection results to a dedicated sheet for PM review.

function _getOrCreateSheet_(name) {
  const ss = SpreadsheetApp.getActive();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
  }
  return sh;
}

function _writeExplainOutput_(result, context) {
  const scenarioName = context?.scenarioName || "";
  const constraintSetName = context?.constraintSetName || "";

  const status = String(result?.status || "").toLowerCase();

  // Support both shapes: { result_json: { raw, summary } } OR { raw: ... }
  const raw =
    (result && result.result_json && result.result_json.raw) ||
    (result && result.raw) ||
    {};

  const evalObj = raw.evaluation || {};
  const rp = raw.repair_plan || {};
  const violations = Array.isArray(evalObj.violations) ? evalObj.violations : [];
  const steps = Array.isArray(rp.steps) ? rp.steps : [];

  const sh = _getOrCreateSheet_("Explain_Output");
  // Clear prior content but preserve formatting/styling
  sh.clearContents();

  const summaryRows = [
    ["run_id", String(result?.run_id || "")],
    ["status", status],
    ["scenario", scenarioName],
    ["constraint_set", constraintSetName],
    ["is_feasible", evalObj.is_feasible === true ? "TRUE" : "FALSE"],
    ["selected_keys", (evalObj.selected_keys || []).join(", ")],
    ["violations_count", String(violations.length)],
    ["repair_steps_count", String(steps.length)],
  ];

  sh.getRange(1, 1, summaryRows.length, 2).setValues(summaryRows);

  let row = summaryRows.length + 2;

  // If job didn't succeed, stop here (still gives useful header info)
  if (status !== "success") {
    sh.getRange(row, 1).setValue("Run did not complete successfully. See ActionRuns for details.");
    sh.getRange(1, 1, sh.getLastRow(), 2).setWrap(true);
    sh.autoResizeColumns(1, 2);
    return;
  }

  // Violations table
  sh.getRange(row, 1, 1, 4).setValues([["violations", "code", "message", "severity"]]);
  row += 1;
  if (violations.length) {
    const vRows = violations.map(v => ["", v.code || "", v.message || "", v.severity || ""]);
    sh.getRange(row, 1, vRows.length, 4).setValues(vRows);
    row += vRows.length + 1;
  } else {
    sh.getRange(row, 1).setValue("(none)");
    row += 2;
  }

  // Repair steps table
  sh.getRange(row, 1, 1, 5).setValues([["repair_steps", "action", "initiative_key", "reason", "impact"]]);
  row += 1;
  if (steps.length) {
    const sRows = steps.map(s => [
      "",
      s.action || "",
      s.initiative_key || "",
      s.reason || "",
      s.impact ? JSON.stringify(s.impact) : "",
    ]);
    sh.getRange(row, 1, sRows.length, 5).setValues(sRows);
  } else {
    sh.getRange(row, 1).setValue("(none)");
  }

  // UX polish
  sh.getRange(1, 1, sh.getLastRow(), sh.getLastColumn()).setWrap(true);
  sh.autoResizeColumns(1, 5);
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

  // 3) Selection: prefer explicit UI selection; otherwise fall back to checkbox is_selected_for_run
  const explicitKeys = getSelectedInitiativeKeys();
  let keys = explicitKeys;
  if (!Array.isArray(keys) || !keys.length) {
    keys = getOptimizationSelectedCandidateKeys_();
  }

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
    requested_by: { ui: "apps_script" },
  };

  if (keys && keys.length) {
    payload.scope = { type: "selection", initiative_keys: keys };
  }

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

  // 6b) Write detailed output to Explain_Output tab for PMs
  try {
    _writeExplainOutput_(finalResult, { scenarioName, constraintSetName });
  } catch (e) {
    ss.toast("Explain output write failed: " + (e && e.message ? e.message : e), "🧠 Explain selection", 8);
  }

  // 7) Optional: show top violation in a dialog for faster UX
  // Tool response shape is usually { status, result_json: { raw, summary }, ... }
  try {
    if (String(finalResult?.status || "").toLowerCase() === "success") {
      const raw = finalResult?.result_json?.raw || finalResult?.raw || {};
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