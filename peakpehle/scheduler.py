"""FR-05..FR-10: original vs rule-based vs CP-SAT optimized schedules, evaluated on the FULL day.

Slots are 15 minutes (96 per day). An activity = power (kW), duration (slots), allowed window
[earliest_start, latest_finish], original start, shiftable flag (False = protected, never moved).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ortools.sat.python import cp_model

SLOTS = 96
EVENING = (64, 80)        # 16:00-20:00


def hhmm(slot: int) -> str:
    return f"{slot // 4:02d}:{slot % 4 * 15:02d}"


def slot(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 4 + m // 15


@dataclass
class Activity:
    id: str
    power_kw: float
    duration: int             # slots
    earliest: int             # slot
    latest_finish: int        # slot (exclusive end)
    original_start: int
    shiftable: bool
    owner_approved: bool = True

    @property
    def movable(self) -> bool:
        # Unverified or protected activities default to non-shiftable (SRS section 8).
        return self.shiftable and self.owner_approved


def profile(acts, starts) -> np.ndarray:
    p = np.zeros(SLOTS)
    for a in acts:
        s = starts[a.id]
        p[s:s + a.duration] += a.power_kw
    return p


def metrics(residual: np.ndarray, acts, starts, original_starts) -> dict:
    total = residual + profile(acts, starts)
    ev = total[EVENING[0]:EVENING[1]]
    outside = np.concatenate([total[:EVENING[0]], total[EVENING[1]:]])
    moved = [a.id for a in acts if starts[a.id] != original_starts[a.id]]
    delays = [abs(starts[a.id] - original_starts[a.id]) * 15 for a in acts]
    return {
        "full_day_max_kw": round(float(total.max()), 1),
        "peak_time": hhmm(int(total.argmax())),
        "evening_max_kw": round(float(ev.max()), 1),
        "evening_avg_kw": round(float(ev.mean()), 1),
        "outside_evening_max_kw": round(float(outside.max()), 1),
        "energy_kwh": round(float(total.sum() * 0.25), 1),
        "shifted": moved,
        "max_shift_min": max(delays) if delays else 0,
        "violations": violations(acts, starts),
    }


def violations(acts, starts) -> list:
    v = []
    for a in acts:
        s = starts[a.id]
        if not a.movable and s != a.original_start:
            v.append(f"{a.id}: protected/unverified activity was moved")
        if a.movable and (s < a.earliest or s + a.duration > a.latest_finish):
            v.append(f"{a.id}: outside its allowed window or deadline")
    return v


def original(acts):
    return {a.id: a.original_start for a in acts}


def rule_based(acts):
    """Simple rule: move any movable activity that overlaps 16-20 to the EARLIEST feasible
    start that avoids the evening window (before 16:00 if possible, else after 20:00)."""
    starts = original(acts)
    for a in acts:
        s = a.original_start
        overlaps = s < EVENING[1] and s + a.duration > EVENING[0]
        if not (a.movable and overlaps):
            continue
        candidates = [t for t in range(a.earliest, a.latest_finish - a.duration + 1)
                      if t + a.duration <= EVENING[0] or t >= EVENING[1]]
        if candidates:
            starts[a.id] = candidates[0]
    return starts


def optimized(residual, acts, time_limit_s: float = 10.0):
    """CP-SAT: minimise full-day maximum demand; tie-break by fewest/smallest moves.
    Returns (starts, status_text). Never returns an invalid schedule."""
    m = cp_model.CpModel()
    scale = 10                                        # 0.1 kW integer resolution
    res = np.round(residual * scale).astype(int)
    x = {}
    for a in acts:
        if not a.movable:
            continue
        opts = range(a.earliest, a.latest_finish - a.duration + 1)
        if len(opts) == 0:
            return None, f"INFEASIBLE: {a.id} needs {a.duration * 15} min but its window " \
                         f"{hhmm(a.earliest)}-{hhmm(a.latest_finish)} is shorter"
        for s in opts:
            x[a.id, s] = m.NewBoolVar(f"{a.id}_{s}")
        m.AddExactlyOne(x[a.id, s] for s in opts)
    fixed = np.zeros(SLOTS)
    for a in acts:
        if not a.movable:
            fixed[a.original_start:a.original_start + a.duration] += a.power_kw
    fixed_i = np.round(fixed * scale).astype(int)
    peak = m.NewIntVar(0, int(res.max() + fixed_i.max() + sum(a.power_kw for a in acts) * scale + 1), "peak")
    for t in range(SLOTS):
        terms = [int(a.power_kw * scale) * x[a.id, s] for a in acts if a.movable
                 for s in range(max(a.earliest, t - a.duration + 1), min(t, a.latest_finish - a.duration) + 1)
                 if (a.id, s) in x]
        m.Add(int(res[t] + fixed_i[t]) + sum(terms) <= peak)
    move_cost = sum(abs(s - a.original_start) * x[a.id, s] for a in acts if a.movable
                    for s in range(a.earliest, a.latest_finish - a.duration + 1))
    m.Minimize(peak * 10000 + move_cost)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_workers = 4
    st = solver.Solve(m)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None, f"INFEASIBLE: solver status {solver.StatusName(st)}"
    starts = original(acts)
    for (aid, s), var in x.items():
        if solver.Value(var):
            starts[aid] = s
    return starts, solver.StatusName(st)


def judge(base: dict, cand: dict, energy_tol=0.01, rebound_tol=0.02) -> list:
    """FR-09 + acceptance: a scenario 'fails' on violations, rebound or material energy increase."""
    issues = []
    if cand["violations"]:
        issues.append("constraint violations")
    if cand["full_day_max_kw"] > base["full_day_max_kw"] * (1 + rebound_tol):
        issues.append(f"rebound: new full-day peak {cand['full_day_max_kw']} kW at {cand['peak_time']}")
    elif (cand["outside_evening_max_kw"] > base["outside_evening_max_kw"] * (1 + 5 * rebound_tol)
          and cand["outside_evening_max_kw"] >= cand["evening_max_kw"]):
        # SRS FR-09: peak merely moved to another time = failure, even if smaller than the original
        issues.append(f"rebound: new peak {cand['outside_evening_max_kw']} kW outside 4-8 PM at {cand['peak_time']} "
                      f"(was {base['outside_evening_max_kw']} kW there)")
    if cand["energy_kwh"] > base["energy_kwh"] * (1 + energy_tol):
        issues.append("material energy increase")
    return issues
