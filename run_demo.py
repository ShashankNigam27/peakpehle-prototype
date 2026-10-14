"""End-to-end demo following the SRS workflow: import -> validate -> explore -> model -> compare
-> evaluate -> human approval (pending) -> export. All data SYNTHETIC.

python data/make_synthetic.py && python run_demo.py
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from peakpehle import data_io, forecast, scheduler as sch

ROOT = Path(__file__).parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
DAY = "2026-05-13"                        # a synthetic weekday


def load_activities(path=ROOT / "data" / "activities.csv"):
    a = pd.read_csv(path)
    acts = []
    for r in a.itertuples():
        end = 96 if r.latest_finish == "24:00" else sch.slot(r.latest_finish)
        acts.append(sch.Activity(r.id, float(r.power_kw), int(r.duration_min) // 15, sch.slot(r.earliest), end,
                                 sch.slot(r.original_start), bool(r.shiftable), bool(r.owner_approved)))
    return acts


def main():
    log = []
    # 1-2. Import + validate
    meter_map = pd.read_csv(ROOT / "data" / "meter_map.csv")
    readings = data_io.load_readings(ROOT / "data" / "synthetic_readings.csv")
    q = data_io.check_quality(readings, meter_map)
    log.append({"step": "validate", "alerts": q.alerts, "coverage": q.coverage})
    print("Data-quality alerts:", *[f"  [{a['severity']}] {a['meter']}: {a['kind']} - {a['detail']}" for a in q.alerts], sep="\n")
    print("-> hierarchy overlap resolved by aggregating ROOT meter (MAIN) only; children used for drill-down.\n")

    # 3. Explore
    campus = data_io.campus_series(readings, meter_map, DAY).to_numpy()
    print(f"Observed {DAY}: full-day max {campus.max():.0f} kW at {sch.hhmm(int(campus.argmax()))}; "
          f"4-8 PM max {campus[64:80].max():.0f} kW\n")

    # Optional forecast
    full = readings[readings.meter_id == "MAIN"].set_index("timestamp")["value"]
    fc = forecast.evaluate(full)
    log.append({"step": "forecast", **fc})
    print("Forecast check (chronological holdout):", json.dumps(fc, indent=1), "\n")

    # 4. Model: residual = observed minus activities at their ORIGINAL times
    base_acts = load_activities()
    residual = np.clip(campus - sch.profile(base_acts, sch.original(base_acts)), 0, None)
    all_tables = []
    for scen_name, file in (("A_as_observed", "activities.csv"), ("B_stress_test", "activities_stress.csv")):
        print(f"===== Scenario set {scen_name} ({file}) =====")
        table, rec, res = compare(residual, load_activities(ROOT / "data" / file), log, scen_name)
        table.insert(0, "scenario_set", scen_name)
        all_tables.append((table, rec))
    export(all_tables, log)
    print("\nNo equipment is controlled. Outputs written to outputs/.")


def compare(residual, acts, log, scen_name):
    orig = sch.original(acts)

    # 5-6. Compare + evaluate
    scen = {"original": orig, "rule_based": sch.rule_based(acts)}
    opt, status = sch.optimized(residual, acts)
    print("Optimizer status:", status)
    if opt is not None:
        scen["optimized"] = opt
    res = {k: sch.metrics(residual, acts, s, orig) for k, s in scen.items()}
    for k in res:
        res[k]["verdict"] = "baseline" if k == "original" else (
            "FAILED: " + "; ".join(sch.judge(res["original"], res[k])) if sch.judge(res["original"], res[k]) else "passes checks")
    if "optimized" in res and res["optimized"]["full_day_max_kw"] >= min(res["original"]["full_day_max_kw"],
                                                                        res["rule_based"]["full_day_max_kw"]):
        res["optimized"]["verdict"] += " - but does NOT beat both baselines, so not described as success"

    rows = []
    for k, m in res.items():
        rows.append({"scenario": k, **{c: m[c] for c in ("full_day_max_kw", "peak_time", "evening_max_kw",
                     "evening_avg_kw", "energy_kwh", "max_shift_min")}, "shifted": ",".join(m["shifted"]),
                     "violations": len(m["violations"]), "verdict": m["verdict"]})
    table = pd.DataFrame(rows)
    print(table.to_string(index=False), "\n")

    # 7. Recommendation (pending human approval)
    rec = []
    success = "optimized" in res and not res["optimized"]["verdict"].startswith("FAILED") \
        and "does NOT beat" not in res["optimized"]["verdict"]
    if not success:
        rec.append({"note": "no shifts recommended: optimized schedule is not a validated improvement"})
        scen = {k: v for k, v in scen.items() if k != "optimized"}
    if "optimized" in scen:
        for a in acts:
            if scen["optimized"][a.id] != orig[a.id]:
                s = scen["optimized"][a.id]
                rec.append({"activity": a.id, "from": sch.hhmm(orig[a.id]), "to": sch.hhmm(s),
                            "window": f"{sch.hhmm(a.earliest)}-{sch.hhmm(a.latest_finish)}",
                            "approval": "PENDING human review"})
    for a in acts:
        if a.shiftable and not a.owner_approved:
            rec.append({"activity": a.id, "note": "not moved: owner approval missing (defaults to non-shiftable)"})
    log.append({"step": f"compare_{scen_name}", "results": res, "recommendations": rec,
                "ts": datetime.now().isoformat(timespec="seconds"), "data_label": "SYNTHETIC"})
    for r in rec:
        print(r)
    print()
    return table, rec, res


def export(all_tables, log):
    pd.concat([t for t, _ in all_tables]).to_csv(OUT / "scenario_comparison.csv", index=False)
    (OUT / "recommendations.json").write_text(json.dumps({t["scenario_set"].iloc[0]: r for t, r in all_tables}, indent=2))
    (OUT / "audit_log.json").write_text(json.dumps(log, indent=2, default=str))
    md = ["# PeakPehle scenario report (SYNTHETIC DATA - not MITS performance)", "",
          f"Day: {DAY} (synthetic). Monetary savings omitted: tariff not verified. "
          "All proposed shifts are advisory and PENDING human approval.", ""]
    for t, r in all_tables:
        md += [f"## {t['scenario_set'].iloc[0]}", "", t.drop(columns="scenario_set").to_markdown(index=False), "",
               "Proposed shifts:", ""] + [f"- {x}" for x in r] + [""]
    (OUT / "report.md").write_text("\n".join(md))


if __name__ == "__main__":
    main()
