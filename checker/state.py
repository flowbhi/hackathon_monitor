import sqlite3, json, os, time
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_URL", "sqlite:///./monitor.db").replace("sqlite:///","")

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks_state(
  name TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  first_failed_at REAL,
  last_changed_at REAL,
  consecutive_failures INTEGER DEFAULT 0,
  last_notification_at REAL
);
CREATE TABLE IF NOT EXISTS results(
  ts REAL NOT NULL,
  name TEXT NOT NULL,
  status TEXT NOT NULL,
  latency_ms REAL,
  details_json TEXT
);
"""

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()

def init_db():
    with _conn() as c:
        for stmt in SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                c.execute(s)
        c.commit()

def upsert_state(name, status, now=None, fail=False):
    now = now or time.time()
    with _conn() as c:
        cur = c.cursor()
        cur.execute("SELECT status, consecutive_failures FROM checks_state WHERE name=?", (name,))
        row = cur.fetchone()
        if not row:
            cur.execute(
              "INSERT INTO checks_state(name,status,first_failed_at,last_changed_at,consecutive_failures,last_notification_at) VALUES(?,?,?,?,?,?)",
              (name, status, now if fail else None, now, 1 if fail else 0, None))
        else:
            prev_status, prev_cf = row
            cf = (prev_cf + 1) if fail else 0
            set_first_fail = "first_failed_at=COALESCE(first_failed_at, ?)," if fail and prev_cf == 0 else ""
            args = []
            if fail and prev_cf == 0:
                args.append(now)
            sql = f"UPDATE checks_state SET status=?, {set_first_fail} last_changed_at=?, consecutive_failures=? WHERE name=?"
            args = [status] + args + [now, cf, name]
            cur.execute(sql, tuple(args))
        c.commit()

def record_result(name, status, latency_ms, details):
    with _conn() as c:
        c.execute(
          "INSERT INTO results(ts,name,status,latency_ms,details_json) VALUES(?,?,?,?,?)",
          (time.time(), name, status, latency_ms, json.dumps(details)[:2000]))
        c.commit()

def read_states():
    with _conn() as c:
        cur = c.cursor()
        cur.execute("SELECT name,status,first_failed_at,last_changed_at,consecutive_failures,last_notification_at FROM checks_state")
        rows = cur.fetchall()
        return rows

def update_last_notification(name):
    with _conn() as c:
        c.execute("UPDATE checks_state SET last_notification_at=? WHERE name=?", (time.time(), name))
        c.commit()
