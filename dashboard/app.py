import json, time, pandas as pd, streamlit as st, os
import pytz
from datetime import datetime, timezone, timedelta

STATE_PATH = os.environ.get("STATE_PATH", "./state.json")
RESULTS_PATH = os.environ.get("RESULTS_PATH", "./results.json")

@st.cache_data(ttl=3)
def load_states():
    if not os.path.exists(STATE_PATH):
        return pd.DataFrame(columns=["name","status","first_failed_at","last_changed_at","consecutive_failures","last_notification_at"])
    data = json.load(open(STATE_PATH))
    rows = [{ "name": k, **v } for k,v in data.items()]
    return pd.DataFrame(rows)

@st.cache_data(ttl=3)
def load_recent_results(max_lines=2000):
    if not os.path.exists(RESULTS_PATH):
        return pd.DataFrame(columns=["ts","name","status","latency_ms","details"])
    lines = []
    with open(RESULTS_PATH, "r") as f:
        for i, line in enumerate(f):
            if not line.strip(): continue
            lines.append(json.loads(line))
    lines = lines[-max_lines:]
    return pd.DataFrame(lines)

st.set_page_config(page_title="Morning Checks", layout="wide")
st.title("Regular / Morning Checks – Live Dashboard")

col1, col2 = st.columns([1,2])

with col1:
    st.subheader("Current Status")
    states = load_states()
    if states.empty:
        st.info("No checks yet. Wait ~30s after starting the checker.")
    else:
        for _, row in states.sort_values("name").iterrows():
            color = "#16a34a" if row.status=="OK" else "#dc2626"
            st.markdown(f"""
<div style="border:1px solid #e5e7eb;border-radius:12px;padding:10px;margin-bottom:8px;background:{'#ecfdf5' if row.status=='OK' else '#fef2f2'}">
<b>{row['name']}</b><br>
Status: <span style="color:{color};font-weight:bold">{row['status']}</span><br>
Consecutive failures: {int(row.get('consecutive_failures') or 0)}
</div>
""", unsafe_allow_html=True)

with col2:
    st.subheader("Last 24h Results")
    df = load_recent_results()
    if not df.empty:
        
        IST = pytz.timezone("Asia/Kolkata")
        df["time"] = pd.to_datetime(df["ts"], unit="s", utc=True).dt.tz_convert(IST)
        st.dataframe(df[["time","name","status","latency_ms","details"]], use_container_width=True, height=420)
    else:
        st.info("No results yet.")

st.caption("Tip: use MockApp /admin/faults to inject failures; /admin/reset to recover.")
