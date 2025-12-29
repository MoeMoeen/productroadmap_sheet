
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


-----------------------------------------------------------------------------------

# EDUCATIONAL

Totally fair question. The confusion comes from the word “async” being used for two different problems.

1) FastAPI async def solves “don’t block while waiting”

FastAPI async is about concurrency inside one web server process:

If your handler does I/O (DB query, HTTP call) and uses await, the server can work on other requests while it’s waiting.

It’s great for lots of short requests and I/O-heavy tasks.


But it’s still the same request/response lifecycle:

client calls endpoint

server runs the work

server returns response

if the server restarts mid-way, the work is gone


So async def helps with performance, not durable background jobs.


---

2) ActionRun + Worker solves “do long work reliably and track it”

Your worker architecture solves different requirements:

✅ Durability

The job is stored in DB (ActionRun). If the API server restarts, the job is still there.

✅ Long-running tasks

Apps Script / browsers time out. A worker can run for minutes.

✅ Progress & audit trail

You can poll GET /actions/run/{run_id} and see queued/running/success/failed, plus results/errors.

✅ Separation of concerns

Web API stays responsive. Heavy work happens elsewhere.

So this is not “async vs sync”. It’s:

> request concurrency vs background job orchestration




---

3) Why not just use FastAPI BackgroundTasks?

FastAPI has BackgroundTasks, but:

it runs in the same process as the web server

if the process restarts, background tasks die

no built-in job history, retries, locking, etc.


It’s okay for “send an email after response”, not for “recompute scores + write to sheets + update backlog”.


---

4) Where Kafka / RabbitMQ / Celery fit

Those are professional queue systems for when you need:

higher throughput

multiple worker machines

delayed/retry policies

dead-letter queues

event streams (Kafka especially)

guaranteed delivery semantics


RabbitMQ (message broker)

good for “job queues”

pairs often with Celery


Kafka (event streaming)

good for “events over time”

multiple consumers

replayable logs


Celery/RQ (job frameworks)

the “worker runner” part

often uses Redis/RabbitMQ as backend


What you built is basically:

a minimal job queue using Postgres as the queue

plus a worker loop

with row locking (FOR UPDATE SKIP LOCKED) to avoid double execution


That’s why it feels like “mini RabbitMQ”: conceptually similar, but implemented with DB rows.


---

5) How they work together in real systems

A common production setup looks like:

FastAPI endpoints (often async def)

validate request

enqueue job (Celery/RQ/Kafka/RabbitMQ or DB queue)

return run_id


Workers

pull jobs from queue

do heavy work

store result/status



So async FastAPI and queues are complementary, not competing.


---

Rule of thumb (simple)

Use FastAPI async when:

work is short

mostly waiting on I/O

you can return response quickly


Use a job queue/worker when:

work may take long (seconds → minutes)

you need durability (survive restarts)

you need status tracking/polling

you want to protect the web server from heavy tasks


That’s exactly your case (Sheets writes, scoring batches, LLM calls, full sync).


---
