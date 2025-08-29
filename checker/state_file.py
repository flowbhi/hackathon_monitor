import json, os, time, threading
from typing import Dict, Any, List

STATE_PATH = os.environ.get("STATE_PATH", "./state.json")
RESULTS_PATH = os.environ.get("RESULTS_PATH", "./results.json")
_lock = threading.Lock()

_state: Dict[str, Any] = {}  # name -> {status, first_failed_at, last_changed_at, consecutive_failures, last_notification_at}

def init_store():
    global _state
    if os.path.exists(STATE_PATH):
        try:
            _state = json.load(open(STATE_PATH, "r"))
        except Exception:
            _state = {}
    else:
        _state = {}
    # ensure files exist
    if not os.path.exists(RESULTS_PATH):
        open(RESULTS_PATH, "a").close()

def _flush_state():
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(_state, f)
    os.replace(tmp, STATE_PATH)

def upsert_state(name: str, status: str, now: float = None, fail: bool = False):
    now = now or time.time()
    with _lock:
        cur = _state.get(name)
        if not cur:
            cur = {
                "status": status,
                "first_failed_at": now if fail else None,
                "last_changed_at": now,
                "consecutive_failures": 1 if fail else 0,
                "last_notification_at": None
            }
        else:
            prev_status = cur["status"]
            prev_cf = cur.get("consecutive_failures", 0)
            cur["status"] = status
            if fail:
                if prev_status != "FAIL":
                    cur["first_failed_at"] = cur["first_failed_at"] or now
                cur["consecutive_failures"] = prev_cf + 1
            else:
                cur["consecutive_failures"] = 0
            if prev_status != status:
                cur["last_changed_at"] = now
        _state[name] = cur
        _flush_state()

def record_result(name: str, status: str, latency_ms: float, details: dict):
    rec = {
        "ts": time.time(),
        "name": name,
        "status": status,
        "latency_ms": latency_ms,
        "details": details
    }
    line = json.dumps(rec, ensure_ascii=False)
    with _lock, open(RESULTS_PATH, "a") as f:
        f.write(line + "\n")

def read_states() -> List[dict]:
    with _lock:
        return [{ "name": k, **v } for k,v in _state.items()]

def update_last_notification(name: str):
    with _lock:
        if name in _state:
            _state[name]["last_notification_at"] = time.time()
            _flush_state()
