# Regular / Morning Checks – Monitoring Dashboard

A small **ops monitoring system** you can run locally. It simulates a production stack, runs automated health checks, shows a **live dashboard**, and **alerts** you (email/console) with optional **auto-remediation**.

---

## Table of contents

* [What you get](#what-you-get)
* [Architecture](#architecture)
* [How the system works (end-to-end flow)](#how-the-system-works-end-to-end-flow)
* [Module details](#module-details)

  * [1) MockApp (FastAPI)](#1-mockapp-fastapi)
  * [2) Checker (APScheduler)](#2-checker-apscheduler)
  * [3) Dashboard (Streamlit)](#3-dashboard-streamlit)
* [Setup & Run](#setup--run)
* [Configuration: `checks.yaml` reference](#configuration-checksyaml-reference)
* [Controls & Demo script](#controls--demo-script)
* [Customize & extend](#customize--extend)
* [Troubleshooting](#troubleshooting)
* [Folder layout](#folder-layout)
* [Security notes](#security-notes)

---

## What you get

* **Mock application** with a web **Control Panel** to toggle failures (“API Down”, “DB Slow”, “Queue Stuck”, “Job Fail”) and to **Run Job**.
* **Checker service** that runs checks every 30 seconds from a simple **YAML config**, writes results, sends **email alerts** (or prints to console), and can **auto-fix** common issues.
* **Dashboard** that shows a GREEN/RED status board and a “Last 24h Results” table (timestamps in **IST**).

---

## Architecture

```
┌───────────┐    health JSON      ┌───────────────┐     read JSON files      ┌─────────────┐
│  MockApp  │ <────────────────── │    Checker    │ ───────────────────────► │  Dashboard  │
│ (FastAPI) │  /api/db/queue/job  │ (APScheduler) │     state.json           │ (Streamlit) │
│  + Panel  │ ──────────────────► │ + Notifier    │     results.json        └─────────────┘
└───────────┘  auto-fix endpoints └───────────────┘
     ▲  │
     │  └─ Run Job / Fault toggles
```

**Data store (default):** simple files `state.json` (current status) and `results.json` (append-only history).
*(Optional alternative: SQLite via `checker/state.py`.)*

---

## How the system works (end-to-end flow)

1. **MockApp** exposes health endpoints:

   * `/api/ping`, `/db/health`, `/queue/health`, `/jobs/{id}/status`
   * Admin/control: `/` (Control Panel), `/admin/faults`, `/admin/reset`, `/jobs/run`
2. **Checker** (every 30s):

   * Reads `checks.yaml` and runs each check (HTTP/JSONPath or Job status).
   * On **failure**:

     * Retries (per `global.retries`), updates **state machine** (OK→FAIL), writes to files,
     * Sends **alerts** (email/console) according to `notify_on`,
     * Runs **auto-actions** (e.g., POST `/admin/reset`).
   * On **recovery**: marks FAIL→OK and notifies if configured.
3. **Dashboard** reads `state.json` and `results.json`, shows:

   * **Status cards** (GREEN = OK, RED = FAIL),
   * **Last 24h Results** table with IST timestamps.

---

## Module details

### 1) MockApp (FastAPI)

* **Purpose:** Simulate a production app with health metrics and a UI to inject faults.
* **Key endpoints**

  * `GET /` → Control Panel (toggle faults, run job, view live state)
  * `GET /api/ping` → `{"status":"ok"}` (or 503 if “API Down”)
  * `GET /db/health` → `{"ok": true/false, "latency_ms": ...}`
  * `GET /queue/health` → `{"depth": N, "oldest_age_s": M}`
  * `POST /jobs/run` → starts a dummy job; finishes \~20s (succeeds unless “Job Fail” is ON); writes a helper file `.last_job_id`
  * `GET /jobs/{job_id}/status` → `running|succeeded|failed`
  * `POST /admin/faults` → set `{ api_down, db_slow, queue_stuck, job_fail }`
  * `POST /admin/reset` → clear faults & normalize queue

> You can drive your entire demo from `/` (no curl needed).

---

### 2) Checker (APScheduler)

* **Purpose:** Execute checks on a schedule, persist results, alert, auto-remediate.
* **Schedule:** runs all checks every 30 seconds by default (edit in `checker/main.py`).
* **State machine per check**

  * `OK → FAIL` → send `first_fail` alert, optional auto-actions, track `consecutive_failures`
  * `FAIL → OK` → send `recovered` alert
  * `FAIL → FAIL` → throttled reminders (optional to add)
* **Storage (default)**: `checker/state_file.py` writing:

  * `state.json` → latest status/metadata by check
  * `results.jsonl` → append-only history (one JSON line per event)
* **Alerts:** SMTP via `.env`. If SMTP isn’t set, emails print to console.

---

### 3) Dashboard (Streamlit)

* **Purpose:** Visual status board and 24h event log.
* **Features:**

  * Cards per check: current **Status**, **Consecutive failures**.
  * Results table (IST timezone).
  * Auto-refresh via Streamlit’s rerun + light caching.

---

## Setup & Run

### Prereqs

* Python 3.10+
* pip

### Environment variables

Create a file **`.env`** in the **repo root** (same folder where you run the commands):

```env
# SMTP is optional; if not set, emails print to console
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
MAIL_FROM=monitor@demo.local
MAIL_TO=your_email@gmail.com

# MockApp base URL
MOCKAPP_BASE=http://127.0.0.1:8000
```

> Gmail requires an **app password** (not your login password).

### Install

```bash
python -m venv .venv

# Windows:
.venv/Scripts/activate
# macOS/Linux:
source .venv/bin/activate

pip install --upgrade pip (optional)
pip install -r requirements.txt
```

### Run (three terminals)

**A) MockApp**

```bash
uvicorn mockapp.app:app --reload --port 8000
# open http://127.0.0.1:8000/
```

**B) Checker**

```bash
python -m checker.main
```

**C) Dashboard**

```bash
streamlit run dashboard/app.py
# open the URL it prints (e.g., http://localhost:8501)
```

---

## Configuration: `checks.yaml` reference

Example:

```yaml
global:
  retries: 2               # retry a failing check N times
  retry_backoff_s: 5       # wait between retries (seconds)
  thresholds:
    api_warn_ms: 1000
    api_crit_ms: 3000

checks:
  - name: api-availability
    type: http
    url: "{MOCKAPP_BASE}/api/ping"  # env vars are expanded from .env
    expect_status: 200
    severity: P1
    on_fail:
      actions:
        - type: http_post
          url: "{MOCKAPP_BASE}/admin/reset"
      notify: ["first_fail"]
    notify_on: ["first_fail","recovered"]

  - name: db-health
    type: http
    url: "{MOCKAPP_BASE}/db/health"
    expect_jsonpath:
      - path: "$.ok"           # JSONPath: $ is the root of the JSON
        equals: true
      - path: "$.latency_ms"
        lt: 100
    severity: P2
    notify_on: ["first_fail","recovered"]

  - name: queue-depth
    type: http
    url: "{MOCKAPP_BASE}/queue/health"
    expect_jsonpath:
      - path: "$.depth"
        lt: 50
      - path: "$.oldest_age_s"
        lt: 300
    severity: P2
    notify_on: ["first_fail","recovered"]

  - name: job            # you can rename from 'nightly-job' to 'job'
    type: job
    status_url: "{MOCKAPP_BASE}/jobs/{job_id}/status"
    # success_by: "23:59"             # absolute deadline (optional)
    # minutes_after_start: 30         # relative deadline (optional)
    severity: P1
    notify_on: ["deadline_miss","recovered"]
```

**Key fields**

* `type: http`

  * `url`: endpoint to GET
  * `expect_status`: required HTTP status
  * `expect_jsonpath`: list of rules evaluated on JSON response

    * `path`: JSONPath (e.g., `$.ok`, `$.latency_ms`)
    * predicates: `equals`, `lt`, `gt`
* `type: job`

  * `status_url`: template with `{job_id}`
  * Job id discovery: the checker reads `.last_job_id` (written by MockApp on `/jobs/run`) **each cycle** and follows the latest.
  * Deadlines (optional):

    * `success_by: "HH:MM"` absolute clock deadline
    * `minutes_after_start: N` relative deadline

**Notifications**

* `notify_on`: subset of `["first_fail","recovered","deadline_miss"]`
* `on_fail.actions`: auto-remediation steps; built-ins:

  * `http_post` with `url` and optional `payload`

---

## Controls & Demo script

### Control Panel (`/`)

* **API Down / DB Slow / Queue Stuck / Job Fail**: toggle **ON** → click **Apply**.
* **Reset**: clear all faults.
* **Run Job**: starts a job; completes \~20s later (fails if **Job Fail** is ON).
* **Live Status**: current MockApp state JSON.

### 3-minute demo

1. Show all **GREEN** tiles on the dashboard.
2. In the panel, toggle **API Down** → **Apply**.

   * Within ≤30s, **api-availability** turns **RED**; email/console alert appears; auto-action may call `/admin/reset`.
3. Click **Reset** → next cycle the tile goes **GREEN**; **RECOVERED** email appears.
4. Click **Run Job** → job shows `running` then `succeeded`; **job** tile remains green.

---

## Customize & extend

* **Add a new HTTP check:** copy one of the existing blocks in `checks.yaml`, change `name`, `url`, and `expect_jsonpath`.
* **Change schedule cadence:** in `checker/main.py`, edit the `IntervalTrigger(seconds=30)`.
* **Add a Slack/Teams notifier:** extend `checker/notify.py` with a webhook sender and call it from `notify_event`.
* **Persist with SQLite instead of files:** swap imports in `checker/main.py` to use `state.py` instead of `state_file.py`.
* **Timezone:** dashboard already shows IST. Adjust in `dashboard/app.py` if you need a different tz.

---

## Troubleshooting

| Symptom                                                     | Probable cause                             | Fix                                                                                            |
| ----------------------------------------------------------- | ------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| `Invalid URL '{MOCKAPP_BASE}/...'`                          | `.env` not found or `MOCKAPP_BASE` missing | Create `.env` in repo root; set `MOCKAPP_BASE=http://127.0.0.1:8000`; restart checker          |
| `http_check() takes 1 positional argument but 2 were given` | Old function signature                     | In `checker/checks.py`, ensure `def http_check(cfg, _state=None):`                             |
| `KeyError: 0` in checker                                    | Using file-backed state but tuple indexing | In `checker/main.py`, build `prev_states` as `{r["name"]: r["status"] for r in read_states()}` |
| Job tile stays RED with `missed deadline`                   | Deadline passed & last job not `succeeded` | Run a job, or set `success_by: "23:59"`, or remove the deadline                                |
| Dashboard shows old job id                                  | Checker cached first id                    | We refresh `.last_job_id` each cycle; ensure you have the updated `job_check` version          |
| Emails not received                                         | SMTP not configured                        | Leave SMTP blank to print to console, or set `SMTP_*` in `.env` (Gmail app password)           |
| Want a clean slate                                          | Old results                                | Stop checker, delete `state.json` and `results.jsonl`, restart                                 |

---

## Folder layout

```
hackathon_monitor/
├─ .env                      # your environment variables (repo root)
├─ requirements.txt
├─ checks.yaml
├─ mockapp/
│  └─ app.py                 # FastAPI + Control Panel
├─ checker/
│  ├─ main.py                # scheduler + runner
│  ├─ checks.py              # http/job executors
│  ├─ actions.py             # http_post, etc.
│  ├─ notify.py              # email (console fallback if SMTP missing)
│  ├─ state_file.py          # default file-backed store (state.json, results.jsonl)
│  └─ state.py               # optional SQLite store
└─ dashboard/
   └─ app.py                 # Streamlit UI (IST)
```

---

## Security notes

* Keep SMTP creds in `.env` (never commit them).
* Use **read-only** credentials for real DB checks.
* Rate-limit auto-remediation (e.g., max N restarts/hour) if you extend beyond demo.
* The mock endpoints are **local only**; do not expose publicly.

---

