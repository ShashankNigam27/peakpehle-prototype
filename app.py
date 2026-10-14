"""Streamlit prototype UI (also serves as the working wireframe). Run: streamlit run app.py
Advisory only - there is no equipment-control code anywhere in this repository."""
import json

import numpy as np
import pandas as pd
import streamlit as st

import run_demo
from peakpehle import data_io, forecast, scheduler as sch

st.set_page_config(page_title="PeakPehle", layout="wide")
st.title("PeakPehle - peak investigation & scheduling (prototype)")
st.warning("SYNTHETIC DEMO DATA. Results show method behaviour only, not MITS performance or savings. "
           "No equipment is controlled; every recommendation needs human approval.")

st.header("1. Import and validate")
up = st.file_uploader("Meter export (CSV: timestamp, meter_id, value, unit)", type=["csv", "xlsx"])
src = up if up is not None else run_demo.ROOT / "data" / "synthetic_readings.csv"
try:
    readings = data_io.load_readings(src)
except data_io.ImportErrorPP as e:
    st.error(str(e))
    st.stop()
meter_map = pd.read_csv(run_demo.ROOT / "data" / "meter_map.csv")
rep = data_io.check_quality(readings, meter_map)
st.dataframe(pd.DataFrame(rep.alerts) if rep.alerts else pd.DataFrame([{"status": "no alerts"}]))
st.caption("Hierarchy overlap is resolved by aggregating root meters only.")

st.header("2. Explore the peak")
days = sorted(readings["timestamp"].dt.strftime("%Y-%m-%d").unique())
day = st.selectbox("Day", days, index=days.index(run_demo.DAY) if run_demo.DAY in days else 0)
campus = data_io.campus_series(readings, meter_map, day)
st.line_chart(campus)
st.json(forecast.evaluate(readings[readings.meter_id == "MAIN"].set_index("timestamp")["value"]))

st.header("3. Compare schedules")
act_file = st.radio("Activity set", ["activities.csv", "activities_stress.csv"], horizontal=True)
acts = run_demo.load_activities(run_demo.ROOT / "data" / act_file)
st.dataframe(pd.read_csv(run_demo.ROOT / "data" / act_file))
base = run_demo.load_activities()
residual = np.clip(campus.to_numpy() - sch.profile(base, sch.original(base)), 0, None)
log = []
table, rec, res = run_demo.compare(residual, acts, log, act_file)
st.dataframe(table)
chart = pd.DataFrame({k: residual + sch.profile(acts, s) for k, s in
                      {"original": sch.original(acts), "rule_based": sch.rule_based(acts),
                       **({"optimized": sch.optimized(residual, acts)[0]} if sch.optimized(residual, acts)[0] else {})}.items()})
chart.index = [sch.hhmm(i) for i in range(96)]
st.line_chart(chart)

st.header("4. Human review")
for r in rec:
    if "activity" in r and "to" in r:
        c1, c2 = st.columns([3, 1])
        c1.write(f"**{r['activity']}**: {r['from']} -> {r['to']} (window {r['window']})")
        c2.selectbox("Decision", ["Pending", "Approve", "Reject"], key=r["activity"] + act_file)
    else:
        st.info(r.get("note", str(r)))
st.download_button("Export report (JSON)", json.dumps({"results": res, "recommendations": rec}, default=str),
                   file_name="peakpehle_report.json")
