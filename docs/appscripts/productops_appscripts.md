# productroadmap_sheet_project/docs/appscripts/productops_appscripts.md


// config.gs
// Central configuration for the Roadmap AI Apps Script UI.

function getRoadmapApiBaseUrl() {
  // Change this to your deployed backend base URL.
  // Example (local): "http://127.0.0.1:8000"
  // Example (prod): "https://your-domain.com"
  return "https://510e-94-200-130-166.ngrok-free.app"
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

/// menu.gs

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🧠 Roadmap AI")
    .addItem("Score selected initiatives", "uiScoreSelected")
    .addItem("Switch scoring framework", "uiSwitchFramework")
    .addItem("Save selected rows", "uiSaveSelected")
    .addSeparator()
    .addItem("Sync intake → backlog", "uiBacklogSync")
    .addSeparator()
    .addItem("Suggest math model (LLM)", "uiSuggestMathModelLLM")
    .addItem("Seed math params", "uiSeedMathParams")
    .addSeparator()
    .addItem("Refresh THIS tab's instructions", "uiProdRefreshTabInstructions")
    .addToUi();
}

// ui_productops_refresh_sheet.gs
function uiProdRefreshInstructions() {
  const ss = SpreadsheetApp.getActive();
  const spreadsheetId = ss.getId();

  const payload = {
    sheet_context: { spreadsheet_id: spreadsheetId },
    options: { sheet_type: "product_ops" },
    requested_by: { ui: "apps_script", source: "product_ops" },
  };

  ss.toast("Refreshing Product Ops instructions...", "Roadmap AI", 5);

  try {
    const started = postActionRun("pm.refresh_sheet_instructions", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);
    const done = pollRunUntilDone(started.run_id, 60, 1000);
    showRunToast_(done, "Refresh Product Ops Instructions");
  } catch (e) {
    ss.toast("Failed to refresh instructions:\n" + (e?.message || e), "Roadmap AI ❌", 8);
  }
}

// ui_productops_refresh_tab.gs
function uiProdRefreshTabInstructions() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const payload = {
    sheet_context: { spreadsheet_id: spreadsheetId, tab: sheet.getName() },
    options: { sheet_type: "product_ops" },
    requested_by: { ui: "apps_script", source: "product_ops" },
  };

  ss.toast(`Refreshing instructions for ${sheet.getName()}...`, "Roadmap AI", 5);

  try {
    const started = postActionRun("pm.refresh_tab_instructions", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);
    const done = pollRunUntilDone(started.run_id, 60, 1000);
    showRunToast_(done, "Refresh Tab Instructions");
  } catch (e) {
    ss.toast("Failed to refresh tab instructions:\n" + (e?.message || e), "Roadmap AI ❌", 8);
  }
}

// Note: reuse showRunToast_ from the optimization Apps Script doc or copy it here unchanged.


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



// ui_scoring.gs
// UI handler for PM Job #2: pm.score_selected

function uiScoreSelected() {
  const keys = getSelectedInitiativeKeys();

  if (!keys.length) {
    SpreadsheetApp.getActiveSpreadsheet().toast("No initiative_key found in your selection.","Roadmap AI",5);
    return;
  }

  const spreadsheetId = SpreadsheetApp.getActive().getId();
  const tabName = SpreadsheetApp.getActiveSheet().getName();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: tabName,
    },
    scope: {
      type: "selection",
      initiative_keys: keys,
    },
    options: {
      // you can add commit_every here later if you want
    },
    requested_by: {
      ui: "apps_script",
      // (optional) you could put the PM email here later if you capture it
    },
  };

  // Call backend
  const result = postActionRun("pm.score_selected", payload);

  // Show quick feedback
  SpreadsheetApp.getActiveSpreadsheet().toast(
    "Scoring started.\nRun ID: " + result.run_id + "\nStatus: " + result.status + "\n\nCheck Status column in the sheet.", "Roadmap AI", 5
  );
}

// ui_framework.gs
// UI handler for PM Job #3: pm.switch_framework

function uiSwitchFramework() {
  const keys = getSelectedInitiativeKeys();

  if (!keys.length) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "No initiative_key found in your selection.",
      "Roadmap AI",
      5
    );
    return;
  }

  const spreadsheetId = SpreadsheetApp.getActive().getId();
  const tabName = SpreadsheetApp.getActiveSheet().getName();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: tabName,
    },
    scope: {
      type: "selection",
      initiative_keys: keys,
    },
    options: {
      // optional: commit_every: 100
      // optional: product_org: "core" (only relevant for backlog branch)
    },
    requested_by: {
      ui: "apps_script",
    },
  };

  try {
    const res = postActionRun("pm.switch_framework", payload);
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Switching framework started. Run ID: " + res.run_id,
      "Roadmap AI",
      8
    );

  } catch (e) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Failed to start: " + (e && e.message ? e.message : e),
      "Roadmap AI",
      8
    );
  }
}


// ui_save.gs
// UI handler for PM Job #4: pm.save_selected

function uiSaveSelected() {
  const keys = getSelectedInitiativeKeys();

  if (!keys.length) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "No initiative_key found in your selection.",
      "Roadmap AI",
      5
    );
    return;
  }

  const spreadsheetId = SpreadsheetApp.getActive().getId();
  const tabName = SpreadsheetApp.getActiveSheet().getName();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: tabName,
    },
    scope: {
      type: "selection",
      initiative_keys: keys,
    },
    options: {
      // optional: commit_every: 100
      // optional: product_org: "core" (only relevant if you're saving from backlog)
    },
    requested_by: {
      ui: "apps_script",
    },
  };

  try {
    const res = postActionRun("pm.save_selected", payload);

    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Save started. Run ID: " + res.run_id + "\nCheck Status column.",
      "Roadmap AI",
      8
    );
  } catch (e) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Failed to start: " + (e && e.message ? e.message : e),
      "Roadmap AI",
      8
    );
  }
}


// ui_populate_initiatives.gs
// UI handler for PM Job: pm.populate_initiatives
// Tab: Scoring_Inputs

/**
 * PM Job: Populate Scoring_Inputs with optimization candidate initiatives from DB
 * Tab: Scoring_Inputs
 * Action: pm.populate_initiatives
 *
 * Workflow:
 * 1) PM marks initiatives as optimization candidates in Central Backlog
 * 2) PM goes to Scoring_Inputs tab and runs "Populate Initiatives"
 * 3) Backend queries DB for is_optimization_candidate=True initiatives
 * 4) Backend appends new initiative keys to Scoring_Inputs (doesn't overwrite existing)
 * 5) PM can then edit framework parameters and run "Score Selected"
 *
 * This action doesn't require a selection - it operates on all optimization candidates.
 */
function uiPopulateInitiatives() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const tabName = sheet.getName();
  const spreadsheetId = ss.getId();

  // Confirm with user
  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert(
    "Populate Initiatives",
    "This will add all optimization candidate initiatives from the database to this sheet.\n\n" +
      "Only new initiatives will be added - existing ones won't be duplicated.\n\n" +
      "Continue?",
    ui.ButtonSet.YES_NO
  );
  
  if (resp !== ui.Button.YES) return;

  ss.toast("Fetching optimization candidates from database...", "Roadmap AI", -1);

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: tabName,
    },
    scope: {},  // No scope needed - operates on all is_optimization_candidate=True
    options: {},
    requested_by: {
      ui: "apps_script",
    },
  };

  try {
    const started = postActionRun("pm.populate_initiatives", payload);
    ss.toast(`Queued: ${started.run_id}`, "Roadmap AI", 5);
    
    const done = pollRunUntilDone(started.run_id, 60, 1000);
    
    // Show detailed result
    if (String(done?.status || "").toLowerCase() === "success") {
      const result = done.result || {};
      const total = result.total_candidates || 0;
      const existing = result.existing_in_sheet || 0;
      const added = result.newly_added || 0;
      
      ss.toast(
        `✅ Population complete!\n\n` +
        `Total candidates: ${total}\n` +
        `Already in sheet: ${existing}\n` +
        `Newly added: ${added}`,
        "Roadmap AI",
        8
      );
    } else {
      showRunToast_(done, "Populate Initiatives");
    }
  } catch (e) {
    ss.toast(
      "Failed to populate initiatives:\n" + (e && e.message ? e.message : e),
      "Roadmap AI ❌",
      8
    );
  }
}


/**
 * ui_mathmodels.gs
 * UI handlers for MathModels tab:
 * - pm.suggest_math_model_llm
 * - pm.seed_math_params
 *
 * Depends on api.gs helpers:
 * - postActionRun(actionName, payload)
 * - pollRunUntilDone(runId, tries, sleepMs)
 *
 * Depends on selection.gs helper:
 * - getSelectedInitiativeKeys()
 */

/**
 * PM Job: Suggest math model via LLM
 * Tab: MathModels
 * Action: pm.suggest_math_model_llm
 *
 * Flow reminder:
 * 1) Suggest math model (LLM) -> writes to LLM-owned columns
 * 2) PM reviews/edits formula_text + assumptions_text + model fields
 * 3) PM sets approved_by_user = TRUE
 * 4) Seed math params (pm.seed_math_params)
 * 5) PM fills parameter values in Params tab
 * 6) PM runs Save Selected on Params tab (pm.save_selected)
 * 7) PM runs Score Selected (pm.score_selected)
 */
function uiSuggestMathModelLLM() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const tabName = sheet.getName();

  if (tabName !== "MathModels") {
    SpreadsheetApp.getUi().alert(
      "Wrong tab",
      'Go to the "MathModels" tab, select one or more initiative rows, then run this again.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }

  // ✅ reuse existing selection logic
  const keys = getSelectedInitiativeKeys();
  if (!keys.length) {
    SpreadsheetApp.getUi().alert(
      "No selection",
      "Select one or more rows that contain initiative_key.",
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }

  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert(
    "Suggest math model (LLM)",
    `This will request LLM suggestions for ${keys.length} initiative(s).\n\n` +
      `It writes into LLM-owned columns (llm_suggested_formula_text, llm_notes, suggested_by_llm).\n` +
      `It does NOT set approved_by_user.\n\nContinue?`,
    ui.ButtonSet.YES_NO
  );
  if (resp !== ui.Button.YES) return;

  SpreadsheetApp.getActive().toast("Requesting LLM suggestions...", "🧠 Roadmap AI", -1);

  const payload = {
    sheet_context: { spreadsheet_id: ss.getId(), tab: "MathModels" },

    // Keep your current shape (type is optional; backend mainly needs initiative_keys)
    scope: { type: "selection", initiative_keys: keys },

    options: { max_llm_calls: 10 },

    requested_by: { ui: "apps_script" }
  };

  const started = postActionRun("pm.suggest_math_model_llm", payload);
  SpreadsheetApp.getActive().toast(`Queued: ${started.run_id}`, "🧠 Roadmap AI", 5);

  const finalResult = pollRunUntilDone(started.run_id, 90, 1000);
  showRunToast_(finalResult, "Suggest math model (LLM)");

  // Optional: if failed, show error quickly
  if (String(finalResult?.status || "").toLowerCase() === "failed") {
    const err = finalResult?.error_text || finalResult?.error || finalResult?.detail || "Check ActionRuns";
    SpreadsheetApp.getUi().alert("Job failed", String(err).slice(0, 800), SpreadsheetApp.getUi().ButtonSet.OK);
  }
}

/**
 * PM Job: Seed math params from approved formulas
 * Tab: MathModels
 * Action: pm.seed_math_params
 *
 * IMPORTANT:
 * - Only seeds for rows where approved_by_user = TRUE
 * - Appends new rows to Params tab with EMPTY values (PM fills)
 */
function uiSeedMathParams() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const tabName = sheet.getName();

  if (tabName !== "MathModels") {
    SpreadsheetApp.getUi().alert(
      "Wrong tab",
      'Go to the "MathModels" tab, select one or more initiative rows, then run this again.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }

  // ✅ reuse existing selection logic
  const keys = getSelectedInitiativeKeys();
  if (!keys.length) {
    SpreadsheetApp.getUi().alert(
      "No selection",
      "Select one or more rows that contain initiative_key.",
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }

  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert(
    "Seed math params",
    `This will seed missing params ONLY for selected rows where approved_by_user = TRUE.\n\n` +
      `After seeding:\n` +
      `1) Go to Params tab and fill param values\n` +
      `2) Select those param rows and run "Save selected rows"\n` +
      `3) Go to Scoring_Inputs and run "Score selected initiatives"\n\nContinue?`,
    ui.ButtonSet.YES_NO
  );
  if (resp !== ui.Button.YES) return;

  SpreadsheetApp.getActive().toast("Seeding params...", "🧠 Roadmap AI", -1);

  const payload = {
    sheet_context: { spreadsheet_id: ss.getId(), tab: "MathModels" },
    scope: { type: "selection", initiative_keys: keys },
    options: { max_llm_calls: 10 },
    requested_by: { ui: "apps_script" }
  };

  const started = postActionRun("pm.seed_math_params", payload);
  SpreadsheetApp.getActive().toast(`Queued: ${started.run_id}`, "🧠 Roadmap AI", 5);

  const finalResult = pollRunUntilDone(started.run_id, 90, 1000);
  showRunToast_(finalResult, "Seed math params");

  if (String(finalResult?.status || "").toLowerCase() === "failed") {
    const err = finalResult?.error_text || finalResult?.error || finalResult?.detail || "Check ActionRuns";
    SpreadsheetApp.getUi().alert("Job failed", String(err).slice(0, 800), SpreadsheetApp.getUi().ButtonSet.OK);
  }
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


