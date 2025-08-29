from fastapi import FastAPI, Body
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import time

app = FastAPI(title="MockApp + Control Panel")

class Faults(BaseModel):
    api_down: bool = False
    db_slow: bool = False
    queue_stuck: bool = False
    job_fail: bool = False

STATE = {
    "faults": Faults().model_dump(),
    "queue": {"depth": 7, "oldest_age_s": 22},
    "jobs": {},  # job_id -> {"status": "queued|running|succeeded|failed", "start": ts}
    "version": "1.0.3",
    "start_time": time.time()
}

# ---- Health-ish endpoints for the checker ----
@app.get("/health")
def health():
    return {"ok": True, "version": STATE["version"], "uptime_s": int(time.time() - STATE["start_time"])}

@app.get("/api/ping")
def api_ping():
    if STATE["faults"]["api_down"]:
        return JSONResponse({"status": "down", "detail": "simulated outage"}, status_code=503)
    return {"status": "ok"}

@app.get("/db/health")
def db_health():
    base = 12
    latency = base + (250 if STATE["faults"]["db_slow"] else 0)
    ok = not STATE["faults"]["db_slow"]
    return {"ok": ok, "latency_ms": latency}

@app.get("/queue/health")
def queue_health():
    q = STATE["queue"].copy()
    if STATE["faults"]["queue_stuck"]:
        q["depth"] = max(q["depth"], 200)
        q["oldest_age_s"] = max(q["oldest_age_s"], 1200)
    return q

@app.post("/jobs/run")
def run_job():
    job_id = f"job_{int(time.time())}"
    STATE["jobs"][job_id] = {"status": "running", "start": time.time()}
    # also save to a helper file so the checker can discover the latest job id
    open(".last_job_id", "w").write(job_id)
    return {"job_id": job_id}

@app.get("/jobs/{job_id}/status")
def job_status(job_id: str):
    job = STATE["jobs"].get(job_id)
    if not job:
        return {"status": "unknown"}
    # simulate finish after 20s
    elapsed = time.time() - job["start"]
    if elapsed > 20 and job["status"] == "running":
        job["status"] = "failed" if STATE["faults"]["job_fail"] else "succeeded"
    return {"status": job["status"]}

# ---- Admin API (used by the Control Panel & the checker auto-actions) ----
@app.post("/admin/faults")
def set_faults(faults: Faults = Body(...)):
    STATE["faults"] = faults.model_dump()
    return {"ok": True, "faults": STATE["faults"]}

@app.post("/admin/reset")
def reset_faults():
    STATE["faults"] = Faults().model_dump()
    STATE["queue"] = {"depth": 5, "oldest_age_s": 10}
    return {"ok": True, "faults": STATE["faults"]}

@app.get("/admin/state")
def read_state():
    return STATE

# ---- Simple HTML Control Panel ----
CONTROL_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>MockApp Control Panel</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; }
    h1 { margin-bottom: 8px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    .card { border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
    .row { display:flex; align-items:center; justify-content:space-between; margin: 8px 0; }
    .switch { position: relative; display: inline-block; width: 44px; height: 24px; }
    .switch input { display:none; }
    .slider { position:absolute; cursor:pointer; top:0; left:0; right:0; bottom:0; background:#ccc; transition:.2s; border-radius: 12px; }
    .slider:before { position:absolute; content:""; height:18px; width:18px; left:3px; bottom:3px; background:white; transition:.2s; border-radius:50%; }
    input:checked + .slider { background:#dc2626; }
    input:checked + .slider:before { transform: translateX(20px); }
    button { padding:8px 12px; border-radius:8px; border:1px solid #e5e7eb; background:#111827; color:white; cursor:pointer; }
    button.secondary { background:white; color:#111827; }
    .ok { color:#16a34a; font-weight:600; }
    .bad { color:#dc2626; font-weight:600; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  </style>
</head>
<body>
  <h1>MockApp Control Panel</h1>
  <p class="mono">Use this page to inject faults and drive your demo.</p>

  <div class="grid">
    <div class="card">
      <h3>Fault Toggles</h3>
      <div class="row"><span>API Down</span><label class="switch"><input id="api_down" type="checkbox"><span class="slider"></span></label></div>
      <div class="row"><span>DB Slow</span><label class="switch"><input id="db_slow" type="checkbox"><span class="slider"></span></label></div>
      <div class="row"><span>Queue Stuck</span><label class="switch"><input id="queue_stuck" type="checkbox"><span class="slider"></span></label></div>
      <div class="row"><span>Job Fail</span><label class="switch"><input id="job_fail" type="checkbox"><span class="slider"></span></label></div>
      <div class="row"><button onclick="applyFaults()">Apply</button><button class="secondary" style="margin-left:8px" onclick="resetFaults()">Reset</button></div>
      <div id="faultStatus" class="mono"></div>
    </div>

    <div class="card">
      <h3>Batch Job</h3>
      <p>Start a job (finishes ~20s later; succeeds unless <em>Job Fail</em> is ON).</p>
      <div class="row"><button onclick="runJob()">Run Job</button></div>
      <div id="jobInfo" class="mono"></div>
    </div>

    <div class="card">
      <h3>Live Status (read-only)</h3>
      <p>Shows a snapshot used by your checker.</p>
      <pre id="live" class="mono" style="white-space: pre-wrap; font-size: 12px; background:#f9fafb; padding:8px; border-radius:8px; max-height:280px; overflow:auto;"></pre>
      <div class="row"><button class="secondary" onclick="refresh()">Refresh</button></div>
    </div>
  </div>

<script>
async function getState() {
  const r = await fetch('/admin/state');
  return await r.json();
}
async function refresh() {
  const s = await getState();
  document.getElementById('live').textContent = JSON.stringify(s, null, 2);
  const f = s.faults || {};
  ['api_down','db_slow','queue_stuck','job_fail'].forEach(k=>{
    const el = document.getElementById(k);
    if (el) el.checked = !!f[k];
  });
}
async function applyFaults() {
  const payload = {
    api_down: document.getElementById('api_down').checked,
    db_slow: document.getElementById('db_slow').checked,
    queue_stuck: document.getElementById('queue_stuck').checked,
    job_fail: document.getElementById('job_fail').checked,
  };
  const r = await fetch('/admin/faults', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
  const j = await r.json();
  document.getElementById('faultStatus').textContent = 'Applied: ' + JSON.stringify(j.faults);
  refresh();
}
async function resetFaults() {
  const r = await fetch('/admin/reset', { method:'POST' });
  const j = await r.json();
  document.getElementById('faultStatus').textContent = 'Reset: ' + JSON.stringify(j.faults);
  refresh();
}
async function runJob() {
  const r = await fetch('/jobs/run', { method:'POST' });
  const j = await r.json();
  document.getElementById('jobInfo').textContent = 'Started job: ' + j.job_id;
  refresh();
}
refresh();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def control_panel():
    return HTMLResponse(content=CONTROL_HTML)
