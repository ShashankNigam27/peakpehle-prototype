"""Acceptance tests mapped to SRS section 11. Run: python -m pytest -q"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from peakpehle import data_io, forecast, scheduler as sch

D = Path(__file__).resolve().parent.parent / "data"


# ---------- import + data quality (FR-01..03) ----------
def test_malformed_file_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("time,meter,reading\n2026-05-04 00:00,MAIN,10\n")
    with pytest.raises(data_io.ImportErrorPP, match="Missing required columns"):
        data_io.load_readings(p)


def test_column_mapping_and_unit_mismatch(tmp_path):
    p = tmp_path / "alt.csv"
    p.write_text("time,meter,reading,uom\n2026-05-04 00:00,MAIN,10,kWh\n")
    with pytest.raises(data_io.ImportErrorPP, match="not supported"):
        data_io.load_readings(p, mapping={"time": "timestamp", "meter": "meter_id", "reading": "value", "uom": "unit"})


def test_defects_are_reported():
    df = data_io.load_readings(D / "defective_readings.csv")
    kinds = {a["kind"] for a in data_io.check_quality(df).alerts}
    assert {"duplicate_timestamps", "missing_intervals", "invalid_values"} <= kinds


def test_meter_hierarchy_double_counting_blocked():
    df = data_io.load_readings(D / "synthetic_readings.csv")
    rep = data_io.check_quality(df, pd.read_csv(D / "meter_map.csv"))
    assert any(a["kind"] == "hierarchy_overlap" and a["severity"] == "block" for a in rep.alerts)


# ---------- scheduling (FR-05..10) ----------
def tiny():
    """Hand-calculated case: flat 100 kW residual; evening 16-20 gets +50 kW. One 40 kW, 1-hour pump at 17:00."""
    res = np.full(96, 100.0)
    res[64:80] += 50
    acts = [sch.Activity("PUMP", 40, 4, sch.slot("06:00"), sch.slot("20:00"), sch.slot("17:00"), True),
            sch.Activity("SERVER", 10, 96, 0, 96, 0, False)]
    return res, acts


def test_hand_calculated_metrics():
    res, acts = tiny()
    o = sch.original(acts)
    m = sch.metrics(res, acts, o, o)
    assert m["full_day_max_kw"] == 200.0          # 100 + 50 + 40 + 10
    assert m["energy_kwh"] == (100 * 96 + 50 * 16 + 40 * 4 + 10 * 96) * 0.25
    opt, _ = sch.optimized(res, acts)
    mo = sch.metrics(res, acts, opt, o)
    assert mo["full_day_max_kw"] == 160.0          # pump moved out of evening: max = 150 + 10
    assert mo["energy_kwh"] == m["energy_kwh"]     # shifting does not change energy


def test_protected_and_unapproved_never_move():
    res, acts = tiny()
    acts.append(sch.Activity("UNVERIFIED", 30, 4, 0, 96, sch.slot("17:00"), True, owner_approved=False))
    o = sch.original(acts)
    for starts in (sch.rule_based(acts), sch.optimized(res, acts)[0]):
        assert starts["SERVER"] == o["SERVER"] and starts["UNVERIFIED"] == o["UNVERIFIED"]


def test_windows_and_deadlines_respected():
    import run_demo
    acts = run_demo.load_activities(D / "activities_stress.csv")
    res = np.full(96, 300.0)
    for starts in (sch.rule_based(acts), sch.optimized(res, acts)[0]):
        assert sch.violations(acts, starts) == []


def test_infeasible_is_reported_not_faked():
    res = np.full(96, 100.0)
    acts = [sch.Activity("TOO_LONG", 20, 12, sch.slot("10:00"), sch.slot("11:00"), sch.slot("10:00"), True)]
    starts, status = sch.optimized(res, acts)
    assert starts is None and status.startswith("INFEASIBLE")


def test_rebound_is_flagged():
    res = np.full(96, 100.0)
    res[64:80] += 50
    # window 06:00-23:00: room to stagger all three outside 16-20, but the naive rule stacks them at 06:00
    acts = [sch.Activity(f"P{i}", 40, 8, sch.slot("06:00"), sch.slot("23:00"), sch.slot("17:00"), True) for i in range(3)]
    o = sch.original(acts)
    base = sch.metrics(res, acts, o, o)
    rule = sch.metrics(res, acts, sch.rule_based(acts), o)      # stacks all three at 12:00
    assert any("rebound" in i for i in sch.judge(base, rule))
    opt = sch.metrics(res, acts, sch.optimized(res, acts)[0], o)
    assert sch.judge(base, opt) == [] and opt["full_day_max_kw"] < min(base["full_day_max_kw"], rule["full_day_max_kw"])


# ---------- forecast ----------
def test_forecast_disabled_without_enough_history():
    s = pd.Series(np.ones(96 * 3))
    assert forecast.evaluate(s)["status"].startswith("disabled")


def test_no_control_interface_exists():
    import peakpehle
    names = " ".join(dir(peakpehle.scheduler) + dir(peakpehle.data_io)).lower()
    assert not any(w in names for w in ("switch", "actuate", "modbus", "bacnet", "plc"))
