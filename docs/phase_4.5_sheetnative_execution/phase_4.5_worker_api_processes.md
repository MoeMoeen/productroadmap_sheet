
## 1) Two processes in parallel: is your mental model correct?

**Yes. Exactly.**

### Process A: FastAPI “web” process

* Receives HTTP requests from Apps Script / curl
* For `POST /actions/run` it **creates an ActionRun row** in the DB with `status="queued"`
* It does **not execute** the action

### Process B: Worker process

* Runs in a loop
* Looks in DB for `status="queued"`
* Claims one
* Executes it
* Updates DB to `running → success/failed`

### Do they talk to each other directly?

**No, not directly.**
They communicate **indirectly through the database**.

So the DB is the “bridge” / shared state.

That’s why this pattern is sometimes called:

* DB-backed job queue
* “outbox pattern” flavor
* async job execution via a ledger

---

## 2) About the curl test and `run_id`

### A) The first curl

Correct: it sends a POST request and the API returns something like:

```json
{"run_id":"run_20251222T101500Z_ab12cd34","status":"queued"}
```

That `run_id` is the unique identifier for that specific job.

### B) The second curl (`GET /actions/run/{run_id}`)

Yes — **`{run_id}` is a placeholder**.

You must replace it with the real value returned by the POST response.

Example:

```bash
curl -H "X-ROADMAP-AI-SECRET: dev-secret" \
  "http://localhost:8000/actions/run/run_20251222T101500Z_ab12cd34"
```

So:

* The POST gives you `run_id`
* Then you use that exact `run_id` to query status

---

## 3) What does “poll” mean here?

“Poll” simply means:

> **keep checking repeatedly** until the status changes.

There are two kinds of polling in our system:

### A) Worker polling the DB

The worker “polls” the DB by repeatedly doing:

* “is there any queued job?”
* if yes → run it
* if no → sleep → try again

That’s DB polling.

### B) Client polling the API (Apps Script / curl)

The client (Apps Script) “polls” the API by repeatedly calling:

* `GET /actions/run/{run_id}`

until it sees:

* `status = success` or `failed`

That’s API polling.

So yes, you caught the nuance perfectly:

* **Worker polls DB**
* **Client polls API**

Same word, different target.

---

## 4) Typical timeline (to make it crystal clear)

1. PM clicks “Sync backlog”
2. Apps Script sends `POST /actions/run`
3. API stores ActionRun:

   * queued
4. Worker sees queued run (by polling DB):

   * marks running
   * executes
   * marks success/failed
5. Apps Script polls `GET /actions/run/{run_id}`
6. It eventually sees:

   * success/failed and displays results

---

# Both processes auto-load ROADMAP_AI_SECRET from .env
uv run uvicorn app.main:app --port 8000 --env-file .env
uv run python -m app.workers.action_worker