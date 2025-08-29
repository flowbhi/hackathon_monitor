import os, time, yaml, traceback
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

#from .state import init_db, upsert_state, record_result, read_states
from .state_file import init_store as init_db
from .state_file import upsert_state, record_result, read_states

from .checks import EXECUTORS
from .notify import notify_event
from .actions import ACTIONS

load_dotenv()
init_db()

# Load config
with open("checks.yaml","r") as f:
    CFG = yaml.safe_load(f)

GLOBAL = CFG.get("global", {})
RETRIES = int(GLOBAL.get("retries", 0))
BACKOFF = int(GLOBAL.get("retry_backoff_s", 5))

STATE_CACHE = {}  # per-check runtime memory

def run_check(item):
    name = item["name"]
    typ  = item["type"]
    severity = item.get("severity","P3")
    notify_on = set(item.get("notify_on", []))
    on_fail = item.get("on_fail", {})
    exec_fn = EXECUTORS[typ]

    ok, latency_ms, details = False, 0, {}
    tries = 0
    last_err = None
    while tries <= RETRIES:
        try:
            ok, latency_ms, details = exec_fn(item, STATE_CACHE.setdefault(name, {}))
            break
        except Exception as e:
            last_err = str(e)
            tries += 1
            time.sleep(BACKOFF)
    if not ok and last_err:
        details = {"error": last_err}

    status = "OK" if ok else "FAIL"
    record_result(name, status, latency_ms, details)
    states = read_states()  # list of dicts: {"name":..., "status":...}
    prev_states = {r["name"]: r["status"] for r in states}
    prev = prev_states.get(name, None)
    fail_transition = (prev != "FAIL" and status == "FAIL")
    recover_transition = (prev == "FAIL" and status == "OK")

    upsert_state(name, status, fail=(status=="FAIL"))

    # Notify?
    if fail_transition and ("first_fail" in notify_on):
        notify_event(name, severity, "first_fail", details)
    if recover_transition and ("recovered" in notify_on):
        notify_event(name, severity, "recovered", details)
    # Deadline miss special event for job checks
    if (not ok) and details.get("error","").startswith("missed deadline") and ("deadline_miss" in notify_on):
        notify_event(name, severity, "deadline_miss", details)

    # Auto-actions on fail
    if (status=="FAIL") and on_fail:
        for action in on_fail.get("actions", []):
            act = action["type"]
            fn = ACTIONS.get(act)
            if fn:
                try:
                    res = fn(action["url"], action.get("payload"))
                    # also log as a result line
                    record_result(name, "ACTION", 0, {"action": act, "result": res})
                except Exception:
                    record_result(name, "ACTION_FAIL", 0, {"action": act, "error": traceback.format_exc()[:500]})

def schedule_all():
    sched = BackgroundScheduler()
    # Every 30s run all checks (simple & effective for demo)
    sched.add_job(lambda: [run_check(ch) for ch in CFG["checks"]],
                  trigger=IntervalTrigger(seconds=30), id="batch_checks", max_instances=1)
    sched.start()
    print("Checker running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sched.shutdown()

if __name__ == "__main__":
    schedule_all()
