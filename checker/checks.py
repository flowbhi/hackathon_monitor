import time, requests, json, os, re, datetime
from jsonpath_ng import parse as jp_parse

def expand_env(s: str) -> str:
    if not isinstance(s, str):
        return s
    for k,v in os.environ.items():
        s = s.replace("{"+k+"}", v)
    return s

def jsonpath_asserts(data, rules):
    for rule in (rules or []):
        val = [m.value for m in jp_parse(rule["path"]).find(data)]
        val = val[0] if val else None
        if "equals" in rule and val != rule["equals"]:
            return False, f"{rule['path']} != {rule['equals']} (got {val})"
        if "lt" in rule and not (val is not None and val < rule["lt"]):
            return False, f"{rule['path']} !< {rule['lt']} (got {val})"
        if "gt" in rule and not (val is not None and val > rule["gt"]):
            return False, f"{rule['path']} !> {rule['gt']} (got {val})"
    return True, "ok"

def http_check(cfg, _state=None):   # <- accept the 2nd arg, ignore it
    url = expand_env(cfg["url"])
    t0 = time.time()
    r = requests.get(url, timeout=5)
    latency_ms = int((time.time()-t0)*1000)
    if "expect_status" in cfg and r.status_code != cfg["expect_status"]:
        return False, latency_ms, {"status_code": r.status_code, "body": r.text[:200]}
    if "expect_jsonpath" in cfg:
        ok, msg = jsonpath_asserts(r.json(), cfg["expect_jsonpath"])
        if not ok:
            return False, latency_ms, {"error": msg}
    return True, latency_ms, {"status_code": r.status_code}

def job_check(cfg, state):
    import time, datetime, os, requests

    status_url_tpl = expand_env(cfg["status_url"])

    # Always try to refresh the latest job id from the helper file
    latest = None
    try:
        latest = open(".last_job_id", "r").read().strip()
    except FileNotFoundError:
        pass

    if latest and latest != state.get("_last_job_id"):
        state["_last_job_id"] = latest
        # (optional) remember when we saw it; useful for relative deadlines
        state["_job_seen_at"] = time.time()

    job_id = state.get("_last_job_id")
    if not job_id:
        return True, 0, {"info": "no job started yet"}

    url = status_url_tpl.replace("{job_id}", job_id)
    t0 = time.time()
    r = requests.get(url, timeout=5)
    latency_ms = int((time.time() - t0) * 1000)
    status = r.json().get("status", "unknown")

    # Absolute deadline (keep if configured)
    deadline = cfg.get("success_by")  # "HH:MM"
    if deadline and status != "succeeded":
        now = datetime.datetime.now().strftime("%H:%M")
        if now >= deadline:
            return False, latency_ms, {"status": status, "error": f"missed deadline {deadline}", "job_id": job_id}

    if status == "failed":
        return False, latency_ms, {"status": status, "job_id": job_id}

    return True, latency_ms, {"status": status, "job_id": job_id}


EXECUTORS = {
    "http": http_check,
    "job": job_check
}
