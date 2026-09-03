# Build Progress

Working agreement: hybrid pace. Boilerplate/plumbing steps are written by
Claude; physics- and algorithm-heavy steps (environment model, generation,
storage/SoC math, RFC mass balance, the controller) are written by the user
with Claude giving the spec/pseudocode first and reviewing the result after.

- [x] Step 0 — Repo scaffold, config constants, `.gitignore`, `requirements.txt` (Claude)
- [x] Step 1 — `assets/base_asset.py` abstract interfaces (Claude)
- [x] Step 2 — `environment.py`: LunarEnvironment day/night + solar flux model (user)
- [x] Step 3 — `assets/generation.py`: PVArray, FissionSurfacePower (user)
- [x] Step 4 — `assets/storage.py`: BatteryBank SoC model (user, with Claude debugging)
- [ ] Step 5 — `assets/storage.py`: RegenerativeFuelCell H2/O2 mass model
- [ ] Step 6 — `assets/loads.py`: ECLSS, ThermalControl, CommsArray, SciencePayload
- [ ] Step 7 — `controller.py`: AutonomousController (priority shed/restore + hysteresis)
- [ ] Step 8 — `power_bus.py`: wire generation + loads + storage + controller together per tick
- [ ] Step 9 — `simulation_engine.py`: 56-day time-marching loop + history log
- [ ] Step 10 — `metrics.py` + `visualization.py`: KPIs and plots
- [ ] Step 11 — `tests/`: pytest coverage per module
- [ ] Step 12 — polish: docstrings, README run instructions, push to GitHub

Each step should be its own git commit, so the repo history itself tells
the build story — useful when this becomes a portfolio piece.
