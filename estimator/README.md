# The estimator

Project B, merged into Project A rather than kept beside it: an Extended Kalman
Filter in C++ that estimates battery state of charge from terminal measurements,
eventually running on an ESP32 with the physics on the host.

---

## Why this is not a bolt-on

`BatteryBank.state_of_charge` is `energy_wh / capacity_wh`. Exact. Noiseless.
Known instantly, every tick, for free.

**No real battery can tell you that.** There is no state-of-charge sensor. You
can measure terminal voltage and current, and from those you must *infer* the
charge — which is precisely why Kalman filters exist in battery management.

So the controller in this simulation has been acting on ground truth it could
never have had. That is a cheat, and it is the interesting kind: it does not
make the model wrong so much as make it *optimistic in a way nobody measured*.

Replacing truth with an estimate turns the merge into a question:

> **How much does outpost reliability degrade when the controller acts on an
> estimate rather than on truth?**

The project already reports unserved kWh, LOLP and failure mode, so the answer
is a table rather than an opinion. And it aims straight at the headline finding:
if the estimator lags during a fast discharge, the power-limited hours should get
**worse**, by an amount we can state.

---

## Toolchain, measured 2026-09-14

| | |
|---|---|
| `clang++` | ✅ Apple clang 21.0.0 |
| `g++`, `make`, `cmake` | ✅ present |
| PlatformIO / ESP-IDF / arduino-cli | ❌ none installed |
| ESP32 board attached | ❌ none (`/dev/cu.debug-console` is macOS's own) |
| `pyserial` | ❌ not installed |

**This sets the order of work, and the order is the right one anyway.**

The EKF gets written and proven **natively**, on the host, where a test can run
in milliseconds and a failure points at a line. Only then does it go near a
board. An estimator that is wrong on a laptop is wrong on an ESP32, and far
harder to see there.

That constraint also improves the code: the filter must be **portable C++ with
no framework dependencies** — no `Arduino.h`, no ESP-IDF headers, no dynamic
allocation. Which is what you want in an estimator regardless, and what makes it
flashable later without a rewrite.

---

## The sequence

### B01 — a battery the EKF can observe  ·  *user, physics*  ·  **blocks everything**

The filter needs something to measure. Today `BatteryBank` exposes state and no
terminals, so there is nothing to observe.

This adds an **open-circuit-voltage curve** and an **internal resistance**, so
the pack has a terminal voltage that depends on charge and on the current being
drawn:

```
V_terminal = OCV(soc) − I · R_internal
```

That single equation is what makes estimation possible *and* difficult: the
`I·R` term means a heavy discharge looks like a low state of charge, and
untangling the two is the filter's whole job.

Lives in the main simulation (`assets/storage.py`), not here — it is battery
physics, not estimator code.

### B02 — the EKF  ·  *user, algorithm*

`include/ekf.hpp` carries the interface and the spec; `src/ekf.cpp` is where it
goes. Native tests in `test/` run against profiles exported from the simulation.

### B03 — the HIL bridge  ·  *Claude, plumbing*

Controller on the ESP32, physics on the host, serial between them. The
controller was written numpy-free at Step 7 precisely so it could port to an
MCU; this is that decision being cashed in.

Needs hardware and a toolchain, so it comes last.

### B04 — the measurement  ·  *together*

Truth versus estimate across the scenarios. The deliverable is the table.

---

## Layout

```
estimator/
  include/ekf.hpp        the interface and the spec
  src/ekf.cpp            the filter                      [B02, user]
  test/
    harness.hpp          a tiny PASS/FAIL/SKIP reporter, no dependencies
    test_ekf.cpp         tests written FROM the spec
  tools/
    export_profile.py    dump (t, current, voltage, true SoC) from the sim
  data/                  exported profiles the tests read
  CMakeLists.txt         native build; no board required
```

## Building and testing

```bash
cmake -S estimator -B estimator/build
cmake --build estimator/build
./estimator/build/test_ekf
```

Tests whose method is not written yet report **SKIP** rather than fail, exactly
as the Python suite does — so the build stays green while the filter is being
written, and the skip list doubles as the to-do list.

---

## What this deliberately is not

- **Not a cell model.** One equivalent-circuit pack, not 100 series cells with
  individual balancing. The question is what the *controller* sees, not what a
  BMS engineer would need.
- **Not thermally coupled.** Real internal resistance is strongly temperature
  dependent, and the lunar swing is severe. Declared, not modelled — yet.
- **Not an ageing model.** Capacity fade and resistance growth are the other
  half of a real BMS and are out of scope here.
