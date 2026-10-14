"""Generate SYNTHETIC demo data. Nothing here is MITS or any real campus's data.

Writes:
  data/synthetic_readings.csv   14 days x 15-min, meters MAIN (root) + SUB_ACAD + SUB_HOSTEL (children)
  data/meter_map.csv            parent/child hierarchy
  data/defective_readings.csv   same data with injected defects (for validation demo/tests)
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(11)
OUT = Path(__file__).parent
idx = pd.date_range("2026-05-04 00:00", periods=14 * 96, freq="15min")
h = np.asarray(idx.hour + idx.minute / 60)
weekday = np.asarray(idx.dayofweek < 5)
heat = 1 + 0.25 * np.clip(np.cos((h - 15) / 24 * 2 * np.pi), 0, None)

acad = (60 + 140 * ((h >= 9) & (h < 18) & weekday) * heat + rng.normal(0, 6, len(idx))).clip(20)
hostel = (50 + 90 * ((h >= 16) & (h < 23)) * heat + 30 * ((h >= 6) & (h < 8)) + rng.normal(0, 5, len(idx))).clip(20)
pumps = 60 * (((h >= 17) & (h < 19)) | ((h >= 17.5) & (h < 19)))          # current practice: evening pumping
other = 40 + 15 * (h >= 18) * (h < 22) + rng.normal(0, 3, len(idx))       # unmetered remainder
main = acad + hostel + pumps + other

rows = []
for mid, v in (("MAIN", main), ("SUB_ACAD", acad), ("SUB_HOSTEL", hostel)):
    rows.append(pd.DataFrame({"timestamp": idx, "meter_id": mid, "value": np.round(v, 1), "unit": "kW",
                              "source": "SYNTHETIC", "quality": "ok"}))
df = pd.concat(rows, ignore_index=True)
df.to_csv(OUT / "synthetic_readings.csv", index=False)

pd.DataFrame({"meter_id": ["MAIN", "SUB_ACAD", "SUB_HOSTEL"], "parent_id": [None, "MAIN", "MAIN"],
              "label": ["Campus incomer (synthetic)", "Academic block (synthetic)", "Hostels (synthetic)"]}
             ).to_csv(OUT / "meter_map.csv", index=False)

bad = df[df["meter_id"] == "MAIN"].copy()
bad = bad.drop(bad.index[200:260])                       # missing intervals
bad = pd.concat([bad, bad.iloc[[10, 11]]])               # duplicates
bad.loc[bad.index[300], "value"] = -50                   # invalid value
bad.to_csv(OUT / "defective_readings.csv", index=False)
print("synthetic data written")
