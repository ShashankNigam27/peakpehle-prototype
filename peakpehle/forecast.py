"""Optional forecast (SRS section 7): weekly seasonal-naive vs daily-naive on a chronological holdout."""
from __future__ import annotations

import numpy as np
import pandas as pd


def evaluate(series: pd.Series, holdout_days: int = 3, per_day: int = 96) -> dict:
    """series: campus kW at 15-min, chronological. Train = everything before the last `holdout_days`."""
    y = series.to_numpy()
    n_hold = holdout_days * per_day
    if len(y) < 7 * per_day + n_hold:
        return {"status": "disabled: need at least 1 week + holdout of data"}
    test = y[-n_hold:]
    weekly = y[-n_hold - 7 * per_day:-7 * per_day]          # same slot, previous week
    daily = y[-n_hold - per_day:-per_day]                   # same slot, previous day
    ev = np.zeros(n_hold, bool)
    for d in range(holdout_days):
        ev[d * per_day + 64:d * per_day + 80] = True

    def m(pred):
        e = pred - test
        return {"MAE": round(float(np.abs(e).mean()), 1), "RMSE": round(float(np.sqrt((e ** 2).mean())), 1),
                "evening_MAE": round(float(np.abs(e[ev]).mean()), 1)}

    out = {"weekly_seasonal_naive": m(weekly), "daily_naive": m(daily)}
    best = min(out, key=lambda k: out[k]["MAE"])
    out["decision"] = f"keep '{best}' as baseline; add a complex model only if it beats this"
    return out
