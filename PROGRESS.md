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

## Next cycle — week of 2026-09-08
Two upgrades, taken together because the second is more useful once the first
exists. Both are in the README roadmap.
- [ ] **Electrical topology** — split into four work orders, spec in
      `topology.py`'s module docstring, constants in `config.py`.
      - [x] **T01** `topology.py` — SPLIT 2026-09-07. Plumbing done by Claude
            (dataclasses, conductor_mass_kg, DCBus aggregation,
            build_topology, 26 tests). Electrical core is the USER's:
            resistance_ohm, current_a, voltage_drop_v, loss_w,
            size_for_loss_budget. Tests for those SKIP until each method
            lands, so the suite stays green — `pytest -rs` prints the
            remaining work as a skip list. 12 pass, 14 skipped.
      - [x] **T02** `power_bus.py` — DONE 2026-09-07 (Claude). Feeders wired
            into the tick; identity extended to `generation + discharged ==
            served + charged + curtailed + losses` and still closes, worst
            residual 7.276e-12 W. Opt-in via `--topology`, so every result
            published before T02 stays reproducible.
            RESULT: the nominal run goes from 0.0 to 10.3 kWh unserved with
            NO outage — conductor loss alone (8.56 % of generation) is enough
            to make the outpost miss its load. Daylight 10.36 % vs night
            2.69 % as a fraction of generation. Eight feeders each sized to a
            5 % budget compose to 8.56 %, not 5 %.
            Two defects, both found only by running it: D-03 the reactor
            feeder was bound by a name build_outpost never used, so a 1 km
            link silently contributed 0.0 W while totals looked plausible;
            D-04 surplus dispatch offered devices power the bus could not
            deliver, and the clamp hid a 1.625e+03 W residual.
      - [x] **T03** `converters.py` — DONE 2026-09-07 (Claude). Opt-in behind
            `--converters`, separately from `--topology`, so the two losses
            can be attributed rather than lumped.
            RESULT: the silicon costs MORE than the copper. Converters alone
            lose 9.79 % of generation against conductors' 8.56 %, and cost 14x
            the unserved energy (142.1 vs 10.3 kWh). Together 18.10 %, and
            155.5 kWh unserved on a run with no outage.
            Also: adding converters LOWERS conductor loss (2587.9 -> 2518.1
            kWh) because a converter throttles what its feeder carries.
            Nothing was double-counted: PV_EFFICIENCY is a cell figure, the
            battery's 0.95 is electrochemical, the RFC's 0.55 is stack
            chemistry — none includes power electronics.
      - [x] **T04** `protection.py` — DONE 2026-09-08. Spec, plumbing, tests
            and maths PDF by Claude; the ENGINEERING BY THE USER (their
            choice, taken in preference to T03). 21 tests, none skipped.
            RESULTS: every feeder's fault is exactly 88x its rating, which
            is algebra rather than coincidence — V, A and L cancel, leaving
            (1/f)(rho_ref/rho_night). And only 2 of 8 feeders can be
            coordinated: the 100 us margin is twice the 50 us floor, so any
            fault clearing upstream in under 150 us has no room for one.
            The user's one defect was `t = self.trip_time_s` returning the
            BOUND METHOD — the fourth appearance of that family here.
            Grounded numbers already in the module docstring: the battery
            feeder's prospective fault is 36.6 kA, EIGHTY-EIGHT times its
            417 A rating. The reactor has the LOWEST fault current at the
            HIGHEST voltage — a kilometre of thin aluminium is its own
            protection. And the T02 temperature finding INVERTS: losses are
            worst hot, fault current worst COLD, a 6.3x swing either way.
      Architecture settled from NASA sources: a 120 VDC user bus (ISPSIS,
      100 m limit) carrying every asset EXCEPT the reactor, which must sit
      >= 1 km away for NUCLEAR reasons and therefore needs a boost/transmit/
      buck chain. The ceiling on transmission voltage is space-qualified
      SEMICONDUCTORS (160 V devices, 1.5 kV rad-hard cap), not insulation.
- [ ] **Client-side model** — port the simulation core to JavaScript so it runs
      in a browser instead of replaying an exported history. Most of the work
      is already done: the controller is plain arithmetic with no numpy because
      it was written to port to a microcontroller, and that same discipline
      makes it port to JS.
Further out, and dependent on both: an operable SLD, then a hardware render.
The successor is expected to be a NEW repo with its own name.

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
