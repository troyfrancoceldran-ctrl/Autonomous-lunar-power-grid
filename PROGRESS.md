# Build Progress

Working agreement: hybrid pace. Boilerplate/plumbing steps are written by
Claude; physics- and algorithm-heavy steps (environment model, generation,
storage/SoC math, RFC mass balance, the controller) are written by the user
with Claude giving the spec/pseudocode first and reviewing the result after.

Documentation convention (applied on completion of every step, from Step 5 on):
each module carries a Doxygen-style header — `@file` / `@brief` / `@author` /
`@date` / `@details` — followed by an `API` section holding the full
`@param` / `@return` / `@note` detail for every class and method. The code
below carries only a single-phrase docstring per definition, so the
implementation stays readable without scrolling past its own documentation.
Authors are Troy Celdran with JARVIS (Claude Opus 5) as co-author.

- [x] Step 0 — Repo scaffold, config constants, `.gitignore`, `requirements.txt` (Claude)
- [x] Step 1 — `assets/base_asset.py` abstract interfaces (Claude)
- [x] Step 2 — `environment.py`: LunarEnvironment day/night + solar flux model (user)
- [x] Step 3 — `assets/generation.py`: PVArray, FissionSurfacePower (user)
- [x] Step 4 — `assets/storage.py`: BatteryBank SoC model (user, with Claude debugging)
- [x] Step 5 — `assets/storage.py`: RegenerativeFuelCell H2/O2 mass model (user)
- [x] Step 6 — `assets/loads.py`: ECLSS, ThermalControl, CommsArray, SciencePayload (user)
- [x] Step 7 — `controller.py`: AutonomousController (priority shed/restore + hysteresis) (user, ControlStrategy interface by Claude)
- [x] Compliance inspection of Steps 0–7 against NASA FSP / NASA Glenn RFC / IEEE 2030.7. Six findings; audit record in `docs/compliance_inspection.html`.
- [x] W01–W04 remediation — all six findings closed:
      - F-01/F-05/F-06 fixed in the inspection itself (708.7 h synodic period, 60-day run, declared simplifications)
      - F-02 `solar_elevation_fraction()` — fixed arrays follow the sine of solar elevation
      - F-04 PV dust derate and an explicit tracking flag
      - F-03 scripted reactor outage window
      - the two-signal control contract: capacity-weighted `aggregate_soc` + `shortfall_w`
- [x] Step 8 — `power_bus.py`: per-tick measure/decide/dispatch/record (Claude). Exposed defect D-01 in the W04 control contract — the shortfall signal was stale by construction; replaced with a signed `headroom_w` measured at the start of each tick. `MIN_ACTION_DWELL_HOURS` 1.0 -> 3.0, which had been a no-op since Step 7.
- [x] Step 9 — `simulation_engine.py`: fixed-timestep loop + CSV/JSON history export; `main.py` now runnable (Claude)
- [x] Step 10 — `metrics.py` + `visualization.py`: KPIs and plots (Claude). Headline result: on the t=500 h outage, **100 % of shortfall hours were power-limited at aggregate_soc 0.6159** — the two-signal design measured rather than asserted. Also: 27.3 % of generation curtailed, battery at its floor for 554 of 708 night hours.
- [x] Step 11 — `tests/`: 188 tests in 0.4 s, organised by failure mode rather than by module (Claude — reassigned mid-session at the user's request). Plus `tests/mutation_check.py`, which reintroduces nine shipped bugs and confirms 8 are caught; the 9th is a verified equivalent mutant. Seven measurement errors were made writing it, against zero code defects found.
- [x] Step 12 (part 1) — README rewritten around the result, `--report`/`--figures` flags wired into `main.py`, MIT LICENSE, figures committed to `docs/figures/`, pre-publication audit run (Claude)
- [x] Step 12 (part 2) — published. Public repo `Autonomous-lunar-power-grid`
      at github.com/troyfrancoceldran-ctrl, 40 commits, MIT. All commits
      rewritten to a GitHub noreply author before the first push, so the
      university address never left the machine. Roadmap added in `1c82dbf`.

- [x] Dual-theme figures + defect D-02 (Claude, 2026-09-07). The palette that
      shipped through Step 12 called itself "validated" and was not: amber at
      2.11:1 and green at 2.74:1 against the surface (floor 3.0), orange vs
      amber ΔE 9.6 under deuteranopia and red vs orange ΔE 10.6 under
      tritanopia (floor 18). Root cause was HUE CHOICE — three warm hues
      collapse onto one axis under deuteranopia, so no tuning fixes it.
      `tests/palette_check.py` now measures both themes; it is itself verified
      against the CIEDE2000 standard's published test data. The palette needs
      only THREE slots: no figure identified more than three series by colour.
      218 tests.

## Week of 2026-09-08 — DONE
All four topology work orders, the client-side model and the operable SLD.
The repo is also a live website now: GitHub Pages serves the landing page, the
diagram and the conformance check at
https://troyfrancoceldran-ctrl.github.io/Autonomous-lunar-power-grid/
The conformance page only became runnable once it was served over HTTPS —
file:// blocks the fetch it needs — so "run it yourself" is now literal.

## Next cycle — PROJECT B, and the merge into this one
From the user's career roadmap: **Project B — Real-Time HIL Battery Management
State Estimator**, an Extended Kalman Filter written from scratch in Modern
C++, flashed onto an ESP32, tracking Li-ion state of charge under noisy
high-stress current profiles. The user intends to merge it into this project
(Project A) rather than keep them separate.

WHY IT IS NOT A BOLT-ON. `BatteryBank.state_of_charge` is `energy_wh /
capacity_wh` — exact, noiseless, known instantly. No real system can measure
SoC at all; that is precisely why an EKF exists. So the controller currently
acts on ground truth it could never have. Swapping that input for an ESTIMATE
turns the merge into a measurable question:

    How much does outpost reliability degrade when the controller acts on an
    estimate rather than on truth?

The project already measures unserved kWh, LOLP and failure mode, so the answer
is a table. It attacks the headline finding directly: if the estimator lags
during a fast discharge, the power-limited hours should get WORSE, and by a
number we can state.

- [ ] **B01** A battery terminal model the EKF can observe — OCV curve plus
      internal resistance, so there is a voltage to measure rather than a
      state to read. (USER — physics)
- [ ] **B02** The EKF itself, C++ on the ESP32. (USER)
- [ ] **B03** The HIL bridge: controller on the ESP32, physics on the host,
      serial between them. This is what "hardware" should mean here — the
      controller was written numpy-free at Step 7 precisely so it could port
      to an MCU. (Claude — plumbing)
- [ ] **B04** Measure truth-vs-estimate across the scenarios. (together)

NOTE ON THE "HARDWARE RENDER". It was a placeholder and the user was never
sure of it either (said so 2026-09-08). Hardware-in-the-loop supersedes it: a
render produces a picture, HIL produces a measurement, and this project has
consistently preferred measurements.

## Agreed sequence from here (2026-09-04)
1. **User** writes Step 11 against `tests/INVARIANTS.md`.
2. **Together** — full test run and review before anything is published.
3. **Claude** does Step 12: README with the figures and the headline result,
   docstring consistency sweep, LICENSE, `.gitignore` check for anything that
   should not be public.
4. **Push to a NEW public GitHub repo.** Outward-facing, so it needs explicit
   go-ahead at the time, not this note. Two things to settle first: the repo
   name, and the git author identity (see tasks.md — currently the repo-local
   "TroyJan_ EE").
5. **LinkedIn post** — Claude can draft it; posting is the user's to do.

Each step should be its own git commit, so the repo history itself tells
the build story — useful when this becomes a portfolio piece.
