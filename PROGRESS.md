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
- [ ] Step 11 — `tests/`: pytest coverage per module (USER — assigned 2026-09-04, a deliberate swap from the usual split. Tests would normally be plumbing, but this session produced three passing-for-the-wrong-reason harnesses, so writing the assertions is the exercise. Claude supplies the invariant list; the user writes the suite.)
- [ ] Step 12 — polish: README, docstring sweep, LICENSE, push to a new public GitHub repo (Claude)

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
