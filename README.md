# Lunar Microgrid Simulation

A time-series simulation of an autonomous power microgrid for a lunar outpost —
photovoltaic generation, battery + regenerative fuel cell (RFC) storage, and an
autonomous load-shedding controller, modeled hour-by-hour across the 14-day
lunar day / 14-day lunar night cycle.

This project doubles as a portfolio piece for the Power + AI systems track
(grid analytics / digital twin / battery management roles).

## Status

Build is happening incrementally, step by step. See `PROGRESS.md` for what's
done and what's next.

## Project layout

```
config.py                # Simulation constants: time step, lunar cycle length, thresholds
environment.py            # LunarEnvironment: solar flux / day-night phase over time
assets/
    base_asset.py         # Abstract PowerSource, PowerStorage, Load interfaces
    generation.py         # PVArray, FissionSurfacePower
    storage.py             # BatteryBank (SoC), RegenerativeFuelCell (H2/O2 mass)
    loads.py               # ECLSS, ThermalControl, CommsArray, SciencePayload
controller.py              # AutonomousController — priority-based load shedding + hysteresis
power_bus.py                # Energy balance each timestep; dispatches storage & controller
simulation_engine.py        # Fixed-timestep time-marching loop, history logging
metrics.py                  # KPIs: shed events, SoC excursions, reactant margin, uptime
visualization.py             # Plots
main.py                       # Entry point
tests/                         # pytest unit tests, one module per asset/controller
data/output_logs/               # Per-run time-series output (gitignored)
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running

Not runnable yet — `main.py` will wire everything together once the engine
exists (see PROGRESS.md).
