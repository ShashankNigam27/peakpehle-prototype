"""FR-01/02: import interval readings with explicit column mapping; FR-03: data-quality checks."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

REQUIRED = ["timestamp", "meter_id", "value", "unit"]
ALLOWED_UNITS = {"kW"}            # demand only in V1; kWh must be converted explicitly, never guessed


class ImportErrorPP(ValueError):
    """Raised when a file cannot be imported safely (stop, don't guess)."""


def load_readings(path, mapping: dict | None = None, interval_min: int = 15) -> pd.DataFrame:
    """Read a CSV/Excel meter export. `mapping` renames source columns to REQUIRED names."""
    try:
        df = pd.read_excel(path) if str(path).endswith((".xlsx", ".xls")) else pd.read_csv(path)
    except Exception as e:  # noqa: BLE001
        raise ImportErrorPP(f"Unsupported or malformed file: {e}") from e
    if mapping:
        df = df.rename(columns=mapping)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ImportErrorPP(f"Missing required columns {missing}. Provide a column mapping.")
    bad_units = sorted(set(df["unit"].astype(str)) - ALLOWED_UNITS)
    if bad_units:
        raise ImportErrorPP(f"Unit(s) {bad_units} not supported for demand analysis; convert to kW first.")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if df["timestamp"].isna().any():
        raise ImportErrorPP(f"{int(df['timestamp'].isna().sum())} timestamp(s) could not be parsed.")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df.attrs["interval_min"] = interval_min
    return df


@dataclass
class QualityReport:
    alerts: list = field(default_factory=list)
    coverage: dict = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return any(a["severity"] == "block" for a in self.alerts)

    def add(self, severity, meter, kind, detail):
        self.alerts.append({"severity": severity, "meter": meter, "kind": kind, "detail": detail})


def check_quality(df: pd.DataFrame, meter_map: pd.DataFrame | None = None,
                  max_kw: float = 5000, gap_block_frac: float = 0.05) -> QualityReport:
    rep = QualityReport()
    step = pd.Timedelta(minutes=df.attrs.get("interval_min", 15))
    for mid, g in df.groupby("meter_id"):
        dups = int(g.duplicated("timestamp").sum())
        if dups:
            rep.add("warn", mid, "duplicate_timestamps", f"{dups} duplicate rows")
        g = g.drop_duplicates("timestamp").sort_values("timestamp")
        expected = pd.date_range(g["timestamp"].min(), g["timestamp"].max(), freq=step)
        missing = len(expected) - len(g)
        frac = missing / max(len(expected), 1)
        rep.coverage[mid] = round(1 - frac, 4)
        if missing:
            rep.add("block" if frac > gap_block_frac else "warn", mid, "missing_intervals",
                    f"{missing} missing ({frac:.1%})")
        diffs = g["timestamp"].diff().dropna()
        odd = int((diffs != step).sum()) - missing
        if odd > 0:
            rep.add("warn", mid, "inconsistent_interval", f"{odd} gaps not equal to {step}")
        bad = int(((g["value"] < 0) | (g["value"] > max_kw) | g["value"].isna()).sum())
        if bad:
            rep.add("block", mid, "invalid_values", f"{bad} negative, missing or > {max_kw} kW")
    if meter_map is not None:
        parents = set(meter_map["parent_id"].dropna())
        present = set(df["meter_id"])
        for p in parents & present:
            kids = set(meter_map.loc[meter_map["parent_id"] == p, "meter_id"]) & present
            if kids:
                rep.add("block", p, "hierarchy_overlap",
                        f"parent and sub-meters {sorted(kids)} both present: aggregate only the parent "
                        f"(or only children) to avoid double-counting")
    return rep


def campus_series(df: pd.DataFrame, meter_map: pd.DataFrame, day: str) -> pd.Series:
    """Campus demand for one day using ROOT meters only (resolves the hierarchy overlap)."""
    roots = set(meter_map.loc[meter_map["parent_id"].isna(), "meter_id"])
    d = df[df["meter_id"].isin(roots)].drop_duplicates(["meter_id", "timestamp"])
    d = d[d["timestamp"].dt.strftime("%Y-%m-%d") == day]
    return d.groupby("timestamp")["value"].sum().sort_index()
