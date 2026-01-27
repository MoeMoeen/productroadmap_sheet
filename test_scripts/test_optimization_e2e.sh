#!/bin/bash
# End-to-end optimization API test

set -e

API_URL="${API_URL:-http://localhost:8000}"
SECRET="${ROADMAP_AI_SECRET:-super-secret-123}"

echo "======================================"
echo "Optimization End-to-End API Test"
echo "======================================"
echo ""

# Step 1: Check server health
echo "1. Checking API server health..."
HEALTH=$(curl -s "$API_URL/health" | head -1)
echo "   ✓ Server response: $HEALTH"
echo ""

# Step 2: Trigger optimization run (selected candidates only)
echo "2. Triggering optimization run..."
echo "   Action: pm.optimize_run_selected_candidates"
echo "   Scenario: 2026-Q1 Growth"
echo "   Constraint Set: Baseline"
echo ""

RESPONSE=$(curl -s -X POST "$API_URL/actions/run" \
  -H "Content-Type: application/json" \
  -H "X-ROADMAP-AI-SECRET: $SECRET" \
  -d '{
    "action": "pm.optimize_run_selected_candidates",
    "options": {
      "scenario_name": "2026-Q1 Growth",
      "constraint_set_name": "Baseline"
    }
  }')

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
echo ""

# Extract action_run_id for polling
ACTION_RUN_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('action_run_id') or data.get('run_id', ''))" 2>/dev/null || echo "")

if [ -z "$ACTION_RUN_ID" ]; then
  echo "❌ Failed to get run_id. Check response above."
  exit 1
fi

echo "   ✓ Action queued with run_id: $ACTION_RUN_ID"
echo ""

# Step 3: Poll for completion
echo "3. Polling for completion (max 2 minutes)..."
MAX_ATTEMPTS=24
ATTEMPT=0
STATUS=""

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
  ATTEMPT=$((ATTEMPT + 1))
  
  STATUS_RESPONSE=$(curl -s "$API_URL/actions/run/$ACTION_RUN_ID" \
    -H "X-ROADMAP-AI-SECRET: $SECRET")
  
  STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', ''))" 2>/dev/null || echo "")
  
  echo "   Attempt $ATTEMPT: Status = $STATUS"
  
  if [ "$STATUS" = "completed" ] || [ "$STATUS" = "success" ] || [ "$STATUS" = "failed" ]; then
    echo ""
    echo "Final Response:"
    echo "$STATUS_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$STATUS_RESPONSE"
    break
  fi
  
  sleep 5
done

echo ""
echo "======================================"
if [ "$STATUS" = "completed" ] || [ "$STATUS" = "success" ]; then
  echo "✓ TEST PASSED"
  echo "======================================"
  echo ""
  echo "Next steps:"
  echo "1. Check Optimization Center sheet:"
  echo "   https://docs.google.com/spreadsheets/d/1ctCxdh4awipo_mXf_gdMTL3aVf8QZVaKAukOwBhygfU"
  echo ""
  echo "2. Verify tabs:"
  echo "   - Runs tab: Should have 1 new row with run_id"
  echo "   - Results tab: Should have N rows (one per candidate)"
  echo "   - Gaps_and_Alerts tab: Should have M rows (one per target)"
  echo ""
  echo "3. Check row 4 onwards (rows 1-3 are header + metadata)"
  exit 0
else
  echo "❌ TEST FAILED OR TIMED OUT"
  echo "======================================"
  echo "Status: $STATUS"
  exit 1
fi
