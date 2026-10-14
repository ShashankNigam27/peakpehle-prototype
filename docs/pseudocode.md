# PeakPehle pseudocode

```text
INPUT  readings(timestamp, meter_id, value, unit), meter_map(meter_id, parent_id),
       activities(id, power_kw, duration, earliest, latest_finish, original_start, shiftable, owner_approved)

# 1. Import
df <- read(file, column_mapping)
IF required columns missing OR unit not kW OR timestamps unparseable: STOP with error   # never guess

# 2. Validate
FOR each meter:
    flag duplicates, missing intervals (coverage), inconsistent intervals, negative/implausible values
IF parent and its sub-meters are both present: BLOCK aggregation -> use root meters only
IF any blocking alert affects the decision window: visibility-only mode, no optimisation

# 3. Explore
campus[t] <- sum of root meters at t ; report full-day max, 4-8 PM max/avg, coverage

# 4. Model
residual[t] <- campus[t] - sum(activity power at ORIGINAL times)
movable(a) <- a.shiftable AND a.owner_approved        # unverified defaults to fixed

# 5. Scenarios on identical inputs
original   <- original starts
rule_based <- for each movable a overlapping 16-20: earliest start in window that avoids 16-20
optimized  <- CP-SAT:
                 choose exactly one start s_a in [earliest_a, latest_finish_a - duration_a] for movable a
                 fixed activities stay at original start
                 demand[t] = residual[t] + sum(power of activities running at t) <= PEAK
                 minimise 10000*PEAK + total shift distance
              IF no solution: RETURN "INFEASIBLE" + blocking activity   # never an invalid schedule

# 6. Evaluate over the FULL day
FOR each scenario: full-day max, peak time, 4-8 PM max/avg, energy, shifted, max shift, violations
FAIL scenario IF violations OR full-day max rises OR peak just moved outside 4-8 PM (rebound)
                 OR energy rises materially
optimized counts as success ONLY IF it passes AND beats BOTH original and rule-based on full-day max

# 7. Human review + export
IF success: list proposed shifts with window, status = PENDING
ELSE: "no shifts recommended"
write report, CSV, audit log (with SYNTHETIC/measured label); no control commands exist
```
