# Step 11 — the invariant list

**Author: user. Spec: JARVIS.** This is the checklist the test suite should
enforce, not the suite itself.

## Why this list exists

Three separate times this project, a bug survived a passing test:

| Bug | What the value-comparison test said | What actually caught it |
|---|---|---|
| `is_daylight` returned a constant — the lunar night ceased to exist | 9/9 reference values PASS | asserting `is_daylight` **varies with t** |
| `PVArray` multiplied by the `sun_tracking` bool, producing 0 W at every hour | no test existed | asserting the array's **peak over a cycle** is non-zero |
| RFC properties written without `@property`, returning bound methods | abstract declaration satisfied | asserting `isinstance(type(d).x, property)` |

And three of the *checking harnesses themselves* were wrong: an expected
value computed at the wrong hour, a device chosen in the rating-limited
regime for a test of energy-limited scaling, and load names retyped as string
literals instead of read from the classes.

**The lesson: a test that fails for its own reasons is cheap; a test that
passes for its own reasons is expensive.** Value comparisons are necessary
and insufficient. The assertions below are the ones that would have caught
what value comparisons missed.

Two habits that follow directly:

- **Never retype a name.** Import `ECLSS()` and read `.name`; never write
  `"Comms Array"` in a test — the load is called `"Communications Array"`.
- **Never hardcode a config value.** Import it. A test asserting `354.35`
  breaks silently in the useful direction if the period is ever revised
  again; one asserting `LUNAR_DAY_HOURS` does not.

---

## A · Structural — the class is shaped as declared

These catch the whole `@property` family of faults, which the ABC cannot.

- [ ] `state_of_charge`, `deliverable_energy_wh`, `deliverable_capacity_wh`
      are each `isinstance(type(device).<name>, property)` on **both**
      storage classes
- [ ] `available_discharge_power_w` is **not** overridden — the concrete base
      implementation is the one that runs
- [ ] Every abstract member of `PowerSource`, `PowerStorage`, `Load` and
      `ControlStrategy` is implemented by every concrete subclass
      (instantiate each; a `TypeError` is the failure)
- [ ] Every reading is a `float`, never an `int` — `max(0, x)` and
      `max(0.0, x)` differ, and only one of them keeps the type
- [ ] No method mutates `self` when it is documented as pure: call
      `available_power` twice with the same `t` and get the same answer

## B · Behavioural variation — does it respond to its input at all?

The class that would have caught the two worst bugs of the project.

- [ ] `is_daylight` returns **both** `True` and `False` over one cycle, and
      the night is `LUNAR_NIGHT_HOURS ± 1 h` long
- [ ] `solar_elevation_fraction` is **> 0.99 somewhere** and **== 0.0
      somewhere**
- [ ] `PVArray.available_power` **peaks above zero** over a full cycle — in
      both `sun_tracking` modes. *A generator that never generates is a test
      failure, not a quiet result.*
- [ ] `FissionSurfacePower.available_power` **varies with t** when an outage
      is configured, and is **constant** when it is not
- [ ] Each duty-cycled load takes **both** its active and its standby value
      within one period
- [ ] The controller returns a **non-`None`** action for at least one input,
      and `None` inside the dead band

## C · Gate before guard — assert on the raw value, not the clamped one

The defensive clamp in `solar_elevation_fraction` absorbed a raw sine of
**−0.96** at midnight and reported a plausible `0.0`. The output was right
for the wrong reason.

- [ ] At a deep-night `t`, assert **both** that the output is `0.0` **and**
      that `is_daylight(t)` is `False`. The second is the real assertion
- [ ] `deliverable_energy_wh` is `0.0` at the floor **and** the device's
      `state_of_charge` is at `soc_min` — not just that the number is zero
- [ ] `FissionSurfacePower(outage_start_hours=0.0)` returns `0.0` at `t=0`.
      This is the `is not None` vs truthiness guard; it is the only test that
      distinguishes them

## D · Conservation — the accounting is not fiction

- [ ] `generation_w + discharged_w == served_w + charged_w + curtailed_w`
      on **every tick** of a full run, to `< 1e-9 W`
- [ ] Per-load `load:` columns sum to `demand_w` on every tick
- [ ] Signed `flow:` columns sum to `charged_w − discharged_w` on every tick
- [ ] A device never charges and discharges in the same tick
- [ ] `charge()`/`discharge()` never return more than requested, and never
      move more energy than the device had headroom or reserve for
- [ ] Round trip: charge X, discharge it back, and the delivered energy is
      `X × round_trip` to tolerance — `0.9025` battery, `0.385` RFC

## E · Boundaries — the operators that were argued over

- [ ] Terminator is **strict `<`**: `phase = LUNAR_DAY_HOURS` is night
- [ ] Outage window is **half-open**: inclusive start, exclusive end
- [ ] Duty cycle is **strict `<`**: `t % period == window` is standby
- [ ] `dt_hours <= 0` returns `0.0` from `available_discharge_power_w`
      rather than dividing by zero
- [ ] Negative `t_hours` folds correctly through the modulo

## F · Control policy — the rules that carry safety weight

- [ ] **ECLSS is never shed**, under any combination of `aggregate_soc` and
      `headroom_w`, including a long run of emergency ticks at `soc = 0.05`
- [ ] Shed order is strictly least-important-first; restore is
      most-important-first
- [ ] Inside the dead band with non-negative headroom, the controller returns
      `None`
- [ ] The power branch **outranks** both the dead band and the energy branch
- [ ] The power branch **bypasses dwell**; the other two **respect** it
- [ ] `MIN_ACTION_DWELL_HOURS > TIME_STEP_HOURS` — assert the relationship,
      not the values. This was vacuous for five steps and nothing noticed
- [ ] **D-01 regression:** shed on negative headroom, then present
      `headroom_w = 0.0` on the next tick with a healthy `aggregate_soc`.
      The controller must **not** restore. This is the exact sequence that
      chattered
- [ ] A load is restored only when `load.demand(t) <= headroom_w` — pick a
      `t` where the load is **active**, or the test proves nothing (a
      duty-cycled load drawing 0 W fits trivially)

## G · Engine and export

- [ ] `to_csv`/`to_json`/`summary` raise rather than write an empty file
      before `run()`
- [ ] `n_steps` truncates: 5 h at `dt = 7 h` gives **0** steps, not a ragged
      tick
- [ ] No clock drift — `t_hours` equals `i * dt` exactly at every index
- [ ] JSON round-trips to an object equal to `history`
- [ ] CSV column order matches the record schema
- [ ] Conservation still holds at `dt = 0.25 h`

## H · Scenario-level regressions

Pin the headline numbers so a refactor that changes physics is loud. Recompute
and update deliberately when a model changes — never to make a test pass.

- [ ] Nominal 60-day run: **0 kWh unserved**
- [ ] Nominal: fleet capacity `2 270 500 Wh`, battery share `7.95 %`
- [ ] Outage at `t = 500 h`: exactly **1 shortfall event**, `1.5 kWh` unserved
- [ ] Outage at `t = 500 h`: **100 % of shortfall hours are power-limited**,
      at `aggregate_soc = 0.6159`. *This is the project's central claim; if a
      change breaks it, the claim needs re-earning.*

---

## Suggested layout

```
tests/
    conftest.py            fixtures: a fresh outpost, a short run, a full run
    test_environment.py    A, B, C, E
    test_generation.py     A, B, C, E
    test_storage.py        A, C, D, E
    test_loads.py          B, E
    test_controller.py     A, F
    test_power_bus.py      D
    test_engine.py         G
    test_scenarios.py      H
```

Build the full 1440-tick run **once** as a session-scoped fixture. It takes
well under a second, but rebuilding it per test makes the suite slow enough
that it stops being run.
