# PeakPehle scenario report (SYNTHETIC DATA - not MITS performance)

Day: 2026-05-13 (synthetic). Monetary savings omitted: tariff not verified. All proposed shifts are advisory and PENDING human approval.

## A_as_observed

| scenario   |   full_day_max_kw | peak_time   |   evening_max_kw |   evening_avg_kw |   energy_kwh |   max_shift_min | shifted                      |   violations | verdict                                                                       |
|:-----------|------------------:|:------------|-----------------:|-----------------:|-------------:|----------------:|:-----------------------------|-------------:|:------------------------------------------------------------------------------|
| original   |               493 | 17:00       |              493 |            380.2 |       6045.5 |               0 |                              |            0 | baseline                                                                      |
| rule_based |               428 | 17:00       |              428 |            331.4 |       6045.5 |             690 | PUMP_1,PUMP_2,LAUNDRY,EV_CHG |            0 | passes checks                                                                 |
| optimized  |               428 | 17:00       |              428 |            377.7 |       6045.5 |              90 | PUMP_1,PUMP_2,LAUNDRY,EV_CHG |            0 | passes checks - but does NOT beat both baselines, so not described as success |

Proposed shifts:

- {'note': 'no shifts recommended: optimized schedule is not a validated improvement'}
- {'activity': 'WORKSHOP', 'note': 'not moved: owner approval missing (defaults to non-shiftable)'}

## B_stress_test

| scenario   |   full_day_max_kw | peak_time   |   evening_max_kw |   evening_avg_kw |   energy_kwh |   max_shift_min | shifted                      |   violations | verdict                                                                         |
|:-----------|------------------:|:------------|-----------------:|-----------------:|-------------:|----------------:|:-----------------------------|-------------:|:--------------------------------------------------------------------------------|
| original   |             672   | 17:30       |              672 |            477.7 |       6435.5 |               0 |                              |            0 | baseline                                                                        |
| rule_based |             613.8 | 13:00       |              428 |            331.4 |       6435.5 |             330 | PUMP_1,PUMP_2,LAUNDRY,EV_CHG |            0 | FAILED: rebound: new peak 613.8 kW outside 4-8 PM at 13:00 (was 340.2 kW there) |
| optimized  |             428   | 17:00       |              428 |            395.2 |       6435.5 |             300 | PUMP_1,PUMP_2,LAUNDRY,EV_CHG |            0 | passes checks                                                                   |

Proposed shifts:

- {'activity': 'PUMP_1', 'from': '17:00', 'to': '12:00', 'window': '12:00-20:00', 'approval': 'PENDING human review'}
- {'activity': 'PUMP_2', 'from': '17:30', 'to': '18:00', 'window': '12:00-20:00', 'approval': 'PENDING human review'}
- {'activity': 'LAUNDRY', 'from': '16:00', 'to': '14:00', 'window': '12:00-22:00', 'approval': 'PENDING human review'}
- {'activity': 'EV_CHG', 'from': '17:00', 'to': '18:00', 'window': '12:00-23:00', 'approval': 'PENDING human review'}
- {'activity': 'WORKSHOP', 'note': 'not moved: owner approval missing (defaults to non-shiftable)'}
