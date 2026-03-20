# productroadmap_sheet_project/docs/appscripts/central_backlog_appscripts.md

# Central Backlog Sheet - Google Apps Script

This Apps Script is bound to the **Central Backlog** Google Sheet.
It provides PM actions for syncing initiatives between the sheet and database.

## Data Flow Summary

| Menu Item | Action | Direction | Description |
|-----------|--------|-----------|-------------|
| Sync intake → backlog | `pm.backlog_sync` | DB → Sheet | Pulls all initiatives from DB, overwrites all columns |
| Save selected rows | `pm.save_selected` | Sheet → DB | Syncs CENTRAL_EDITABLE_FIELDS to DB |
| Switch scoring framework | `pm.switch_framework` | DB → Sheet | Activates per-framework scores |

**IMPORTANT**: Run "Save selected rows" before "Sync intake → backlog" to persist PM edits,
otherwise pm.backlog_sync will overwrite unsaved changes.

---

## Files to Create in Apps Script Editor

### config.gs

```javascript
// config.gs
// Central configuration for the Roadmap AI Apps Script UI.

function getRoadmapApiBaseUrl() {
  // Change this to your deployed backend base URL.
  // Example (local): "http://127.0.0.1:8000"
  // Example (prod): "https://your-domain.com"
  return "https://your-ngrok-or-domain.ngrok-free.app";
}

function getRoadmapApiSecret() {
  // Read from Script Properties (recommended).
  // Set via: Extensions > Apps Script > Project Settings > Script Properties
  const props = PropertiesService.getScriptProperties();
  return props.getProperty("ROADMAP_AI_SECRET") || "";
}
```

### api.gs

```javascript
// api.gs
// Low-level HTTP helpers to call the backend Action API.

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

  if (ctx.parsed && (ctx.parsed._isHtml || ctx.parsed._parseError)) {
    throw new Error(
      "Action API error — Non-JSON response from server\n" +
        (ctx.text || "").slice(0, 500)
    );
  }

  return ctx.parsed;
}

function getActionRun(runId) {
  const ctx = _request_("get", "/actions/run/" + encodeURIComponent(runId));

  if (ctx.statusCode >= 400) {
    throw _formatHttpError_(ctx, "Get run status failed");
  }

  if (ctx.parsed && (ctx.parsed._isHtml || ctx.parsed._parseError)) {
    return {
      run_id: runId,
      status: "running",
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
      Utilities.sleep(sleepMs);
      continue;
    }

    const s = String(r && r.status ? r.status : "").toLowerCase();

    if (s === "success" || s === "failed") return r;

    Utilities.sleep(sleepMs);
  }

  return { run_id: runId, status: "timeout" };
}
```

### menu.gs

```javascript
// menu.gs
// Menu registration for Central Backlog sheet

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("🧠 Roadmap AI")
    .addItem("Sync intake → backlog", "uiBacklogSync")
    .addItem("Save selected rows", "uiSaveSelected")
    .addItem("Switch scoring framework", "uiSwitchFramework")
    .addSeparator()
    .addItem("Refresh tab instructions", "uiRefreshTabInstructions")
    .addToUi();
}
```

### selection.gs

```javascript
// selection.gs
// Extract selected initiative_keys from the current selection.

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

    const colValues = sheet.getRange(startRow, keyCol, count, 1).getValues();
    for (let i = 0; i < count; i++) {
      const v = String(colValues[i][0] || '').trim();
      if (v) keys.push(v);
    }
  }

  return Array.from(new Set(keys));
}
```

### ui_backlog_sync.gs

```javascript
// ui_backlog_sync.gs
// PM Job #1: pm.backlog_sync (DB → Sheet)
//
// This syncs ALL initiatives from DB to the Central Backlog sheet.
// WARNING: Overwrites ALL columns - run "Save selected rows" first to preserve PM edits!

function uiBacklogSync() {
  const ss = SpreadsheetApp.getActive();
  const spreadsheetId = ss.getId();

  const ui = SpreadsheetApp.getUi();
  const resp = ui.alert(
    "Sync intake → backlog",
    "This will:\n" +
      "1. Sync all intake sheets to DB\n" +
      "2. Regenerate this entire backlog from DB\n\n" +
      "⚠️ WARNING: Any unsaved edits will be OVERWRITTEN.\n" +
      "Run 'Save selected rows' first if you have unsaved changes.\n\n" +
      "Continue?",
    ui.ButtonSet.YES_NO
  );
  if (resp !== ui.Button.YES) return;

  ss.toast("Starting backlog sync...", "🧠 Roadmap AI", -1);

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
    },
    scope: {
      type: "all",  // No selection - syncs all
    },
    options: {},
    requested_by: {
      ui: "apps_script",
      source: "central_backlog",
    },
  };

  try {
    const started = postActionRun("pm.backlog_sync", payload);
    ss.toast(`Queued: ${started.run_id}`, "🧠 Roadmap AI", 5);

    const finalResult = pollRunUntilDone(started.run_id, 120, 1000);
    showRunToast_(finalResult, "Sync intake → backlog");

    if (String(finalResult?.status || "").toLowerCase() === "success") {
      const summary = finalResult?.result?.summary || {};
      const msg = `Updated: ${summary.updated_count || 0} initiatives, ${summary.cells_updated || 0} cells`;
      ss.toast(msg, "🧠 Roadmap AI ✅", 8);
    }
  } catch (e) {
    ss.toast("Failed: " + (e?.message || e), "🧠 Roadmap AI ❌", 10);
  }
}
```

### ui_save.gs

```javascript
// ui_save.gs
// PM Job #4: pm.save_selected (Sheet → DB)
//
// Syncs PM-editable fields from selected rows to DB.
// Fields synced: Title, Hypothesis, Problem Statement, Department, Country,
// Product Area, Lifecycle Status, Active Scoring Framework, Use Math Model,
// Dependencies, Strategic Priority Coefficient, Is Optimization Candidate, etc.

function uiSaveSelected() {
  const keys = getSelectedInitiativeKeys();

  if (!keys.length) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "No initiative_key found in your selection.",
      "🧠 Roadmap AI",
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
    options: {},
    requested_by: {
      ui: "apps_script",
      source: "central_backlog",
    },
  };

  try {
    const res = postActionRun("pm.save_selected", payload);

    SpreadsheetApp.getActiveSpreadsheet().toast(
      `Saving ${keys.length} row(s)...\nRun ID: ${res.run_id}`,
      "🧠 Roadmap AI",
      5
    );

    const finalResult = pollRunUntilDone(res.run_id, 60, 1000);
    showRunToast_(finalResult, "Save selected rows");

  } catch (e) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Failed: " + (e?.message || e),
      "🧠 Roadmap AI ❌",
      8
    );
  }
}
```

### ui_framework.gs

```javascript
// ui_framework.gs
// PM Job #3: pm.switch_framework
//
// Activates a different scoring framework's scores for selected rows.
// Does NOT recompute scores - just copies already-computed per-framework scores to active fields.

function uiSwitchFramework() {
  const keys = getSelectedInitiativeKeys();

  if (!keys.length) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "No initiative_key found in your selection.",
      "🧠 Roadmap AI",
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
    options: {},
    requested_by: {
      ui: "apps_script",
      source: "central_backlog",
    },
  };

  try {
    const res = postActionRun("pm.switch_framework", payload);
    SpreadsheetApp.getActiveSpreadsheet().toast(
      `Switching framework for ${keys.length} row(s)...\nRun ID: ${res.run_id}`,
      "🧠 Roadmap AI",
      5
    );

    const finalResult = pollRunUntilDone(res.run_id, 60, 1000);
    showRunToast_(finalResult, "Switch scoring framework");

  } catch (e) {
    SpreadsheetApp.getActiveSpreadsheet().toast(
      "Failed: " + (e?.message || e),
      "🧠 Roadmap AI ❌",
      8
    );
  }
}
```

### ui_refresh.gs

```javascript
// ui_refresh.gs
// Refresh tab instructions (writes system instructions to row 2)

function uiRefreshTabInstructions() {
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getActiveSheet();
  const spreadsheetId = ss.getId();

  const payload = {
    sheet_context: {
      spreadsheet_id: spreadsheetId,
      tab: sheet.getName(),
    },
    options: {
      sheet_type: "central_backlog",
    },
    requested_by: {
      ui: "apps_script",
      source: "central_backlog",
    },
  };

  ss.toast(`Refreshing instructions for ${sheet.getName()}...`, "🧠 Roadmap AI", 5);

  try {
    const started = postActionRun("pm.refresh_tab_instructions", payload);
    ss.toast(`Queued: ${started.run_id}`, "🧠 Roadmap AI", 5);
    const done = pollRunUntilDone(started.run_id, 60, 1000);
    showRunToast_(done, "Refresh Tab Instructions");
  } catch (e) {
    ss.toast("Failed: " + (e?.message || e), "🧠 Roadmap AI ❌", 8);
  }
}
```

### helpers.gs

```javascript
// helpers.gs
// Shared UI helper functions

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
```

---

## Setup Instructions

1. Open your Central Backlog Google Sheet
2. Go to **Extensions > Apps Script**
3. Create files for each section above (config.gs, api.gs, menu.gs, etc.)
4. Copy the code into each file
5. Set the API secret:
   - Go to **Project Settings** (gear icon)
   - Under **Script Properties**, add:
     - Property: `ROADMAP_AI_SECRET`
     - Value: (your shared secret)
6. Update `getRoadmapApiBaseUrl()` in config.gs with your backend URL
7. Save all files
8. Reload the Google Sheet - the "🧠 Roadmap AI" menu should appear

---

## PM Workflow

### Typical Edit Flow

1. **View data**: Open Central Backlog sheet
2. **Edit PM fields**: Modify Title, Hypothesis, Problem Statement, etc.
3. **Save edits**: Select edited rows → Roadmap AI → "Save selected rows"
4. **Sync latest**: Roadmap AI → "Sync intake → backlog" (pulls DB → Sheet)

### Warning: Unsaved Edits

The "Sync intake → backlog" action **overwrites all columns** from DB.
Always run "Save selected rows" first if you have unsaved PM edits!

### Fields Synced by "Save selected rows"

These CENTRAL_EDITABLE_FIELDS flow Sheet → DB:

- Title
- Department, Requesting Team, Requester Name, Requester Email
- Country, Product Area, Lifecycle Status
- Customer Segment, Initiative Type
- Hypothesis, Problem Statement
- Active Scoring Framework, Use Math Model
- Dependencies Initiatives, Dependencies Others
- LLM Summary
- Strategic Priority Coefficient
- Is Optimization Candidate, Candidate Period Key
