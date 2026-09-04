"""
@file    simulation_engine.py
@brief   Fixed-timestep time-marching loop and the run history it produces.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
The thinnest module in the project, and deliberately so. PowerBus.step()
already does everything that happens within a tick; this only decides WHEN
the ticks happen and keeps what they returned.

    for i in range(n_steps):
        history.append(bus.step(i * dt_hours, dt_hours))

Everything else here is export and convenience. If this file ever starts
making decisions about power, something has been put in the wrong place.

@note FIXED timestep, never adaptive. Every device's charge()/discharge()
    converts power to energy by multiplying by dt, and the controller's dwell
    timer counts in hours. A variable step would silently change the meaning
    of MIN_ACTION_DWELL_HOURS and make two runs incomparable. It is also what
    the flight controller would do: a real loop ticks on a timer interrupt.

@note t is computed as `i * dt_hours`, never accumulated as `t += dt`.
    Accumulating 1440 floats drifts; multiplying does not. At dt = 1.0 h this
    is invisible, but at dt = 0.05 h an accumulated clock ends the run about
    a microsecond off, and the duty-cycle loads compare against exact
    boundaries like `t % 24 < 8`.

SEPARATION OF CONCERNS
    engine     when ticks happen, and what was recorded
    bus        what happens within one tick
    metrics    what the recording MEANS         (Step 10)
    viz        what it looks like               (Step 10)

    The engine imports none of the concrete assets and never inspects a
    record's contents. It does not know what a watt is.

@see power_bus.py for the per-tick logic and the RECORD SCHEMA.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class SimulationEngine
--------------------------------------------------------------------------------
Marches a PowerBus through time and keeps every record it returns.

@var bus              The PowerBus being driven.
@var duration_hours   Total simulated time [h].
@var dt_hours         Fixed timestep [h].
@var history          THE OUTPUT — list of per-tick dicts, in time order.

__init__(bus, duration_hours=SIM_DURATION_HOURS, dt_hours=TIME_STEP_HOURS)
    Configure a run. Nothing is simulated until run() is called.

    @note The bus arrives already wired. This class never constructs an asset,
        which is what lets the same engine drive a contingency scenario, a
        sensitivity sweep, or a unit test with two toy devices.

n_steps -> int                                                    [@property]
    How many ticks the configured run will take.

    @return int(duration_hours / dt_hours).

    @note Truncating is deliberate. A duration that is not a whole number of
        steps runs the largest whole number that fits rather than a ragged
        final tick of a different length — which would break the fixed-step
        guarantee everything else relies on.

run() -> list[dict]
    March through the whole run and return the history.

    @return The accumulated per-tick records, oldest first.

    @warning NOT repeatable on the same engine. The bus's storage devices and
        the loads' shed flags carry state, so a second run() continues from
        wherever the first one stopped rather than starting over. Build a
        fresh bus for a fresh run — which is cheap, and is why there is no
        reset().
    @note Clears any previous history so the returned list always describes
        exactly the ticks this call performed.

to_csv(path) -> None
    Write the history as CSV, one row per tick.

    @param path  Destination file; parent directories are created.

    @note Uses the stdlib csv module rather than pandas. The engine has no
        business requiring a dataframe library to save a list of dicts, and
        this keeps the simulation core importable on a machine that has only
        the standard library. metrics.py may use pandas freely.
    @note Column order is taken from the first record, so it follows the
        RECORD SCHEMA order in power_bus.py rather than sorting alphabetically
        and scattering the related columns.

to_json(path) -> None
    Write the history as JSON, as one array of objects.

    @param path  Destination file; parent directories are created.

    @note This is the feed a browser-based visualization consumes — a single
        fetch, no parsing beyond JSON.parse. Keeping it here rather than in
        visualization.py means the simulation never imports a UI concern; it
        emits data, and whatever wants to draw it reads the file.
    @note Written COMPACT, with no indentation. It is a machine feed, and at
        1440 rows indentation costs about 15 % — 724 KB pretty-printed
        against 611 KB compact. Read it with json.load() or JSON.parse(),
        not with your eyes; the CSV is the human-readable export at
        222 KB.

summary() -> dict
    A handful of run-level totals, for a one-line console report.

    @return Keys: hours, steps, unserved_kwh, curtailed_kwh, generated_kwh,
            served_kwh, min_aggregate_soc, min_headroom_w, actions.

    @note NOT the metrics module. These are the few numbers needed to see at
        a glance whether a run did anything surprising. Uptime per load, shed
        event durations, reactant margin at dawn and the rest belong in
        metrics.py, which is free to be as thorough as it likes.
    @warning Energies are integrated as `sum(power) * dt`, which is a
        left-endpoint rectangle rule. Exact here because every quantity the
        bus reports is constant across its own timestep by construction — it
        is a rate held for the tick, not a sample of a continuous curve.
"""

import csv
import json
import os

from config import SIM_DURATION_HOURS, TIME_STEP_HOURS


class SimulationEngine:
    """Marches a PowerBus through time and keeps every record it returns."""

    def __init__(self, bus, duration_hours: float = SIM_DURATION_HOURS,
                dt_hours: float = TIME_STEP_HOURS):
        """Configure a run; nothing is simulated until run() is called."""
        self.bus = bus
        self.duration_hours = duration_hours
        self.dt_hours = dt_hours
        self.history = []

    @property
    def n_steps(self) -> int:
        """Whole ticks that fit in the configured duration."""
        return int(self.duration_hours / self.dt_hours)

    def run(self) -> list:
        """March the whole run; returns the per-tick history, oldest first."""
        self.history = []
        for i in range(self.n_steps):
            self.history.append(self.bus.step(i * self.dt_hours, self.dt_hours))
        return self.history

    def _ensure_parent(self, path: str) -> None:
        """Create the destination directory if it does not exist."""
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

    def to_csv(self, path: str) -> None:
        """Write the history as CSV, one row per tick."""
        if not self.history:
            raise RuntimeError("nothing to write — call run() first")
        self._ensure_parent(path)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.history[0]))
            writer.writeheader()
            writer.writerows(self.history)

    def to_json(self, path: str) -> None:
        """Write the history as one JSON array; the feed a UI would consume."""
        if not self.history:
            raise RuntimeError("nothing to write — call run() first")
        self._ensure_parent(path)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self.history, handle, separators=(",", ":"))

    def summary(self) -> dict:
        """Run-level totals for a one-line console report; not metrics.py."""
        if not self.history:
            raise RuntimeError("nothing to summarize — call run() first")
        dt = self.dt_hours
        return {
            "hours": self.duration_hours,
            "steps": len(self.history),
            "generated_kwh": sum(r["generation_w"] for r in self.history) * dt / 1000.0,
            "served_kwh": sum(r["served_w"] for r in self.history) * dt / 1000.0,
            "unserved_kwh": sum(r["shortfall_w"] for r in self.history) * dt / 1000.0,
            "curtailed_kwh": sum(r["curtailed_w"] for r in self.history) * dt / 1000.0,
            "min_aggregate_soc": min(r["aggregate_soc"] for r in self.history),
            "min_headroom_w": min(r["headroom_w"] for r in self.history),
            "actions": sum(1 for r in self.history if r["action"]),
        }
