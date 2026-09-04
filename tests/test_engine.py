"""
Tests for simulation_engine.py.

Invariant sections from tests/INVARIANTS.md covered here:
    G engine and export
"""

import csv
import json
import os

import pytest

from config import SIM_DURATION_HOURS, TIME_STEP_HOURS
from environment import LunarEnvironment
from main import build_outpost
from simulation_engine import SimulationEngine


def fresh_engine(**kwargs):
    return SimulationEngine(build_outpost(LunarEnvironment()), **kwargs)


# =============================================================================
# G — CONTRACT.  Refuse rather than write an empty file.
# =============================================================================

def test_history_is_empty_before_run(outpost):
    assert SimulationEngine(outpost).history == []


@pytest.mark.parametrize("call", [
    lambda e, p: e.to_csv(p),
    lambda e, p: e.to_json(p),
    lambda e, p: e.summary(),
])
def test_export_before_run_raises(outpost, tmp_path, call):
    """Silently writing a header-only CSV would be worse than failing."""
    engine = SimulationEngine(outpost)
    with pytest.raises(RuntimeError):
        call(engine, str(tmp_path / "nope"))


# =============================================================================
# G — THE CLOCK.  Computed, never accumulated.
# =============================================================================

def test_no_clock_drift(nominal_history):
    """t = i * dt exactly. Accumulating t += dt drifts into the duty-cycle
    boundaries, which compare against exact values like t % 24 < 8."""
    for i, record in enumerate(nominal_history):
        assert record["t_hours"] == i * TIME_STEP_HOURS


def test_run_length_matches_config(nominal_history):
    assert len(nominal_history) == int(SIM_DURATION_HOURS / TIME_STEP_HOURS)


@pytest.mark.parametrize("duration, dt, expected", [
    (1440.0, 1.0, 1440),
    (100.0, 3.0, 33),        # truncates rather than running a ragged tick
    (10.0, 0.25, 40),
    (5.0, 7.0, 0),           # a step longer than the run yields no steps
])
def test_n_steps_truncates(duration, dt, expected):
    engine = fresh_engine(duration_hours=duration, dt_hours=dt)
    assert engine.n_steps == expected


def test_conservation_survives_a_finer_timestep(fine_history):
    """dt = 0.25 h. If the identity depended on dt, the physics would be wrong."""
    for record in fine_history:
        supplied = record["generation_w"] + record["discharged_w"]
        absorbed = (record["served_w"] + record["charged_w"]
                    + record["curtailed_w"])
        assert supplied == pytest.approx(absorbed, abs=1e-9)


def test_run_replaces_history_and_carries_device_state():
    """Documented: run() is NOT repeatable — build a fresh bus instead.

    Sampled at 500 h, which ends mid-night. At 200 h the outpost sits in
    daylight with storage brim-full, so the carried state is identical to the
    initial state and this test would pass while proving nothing.
    """
    engine = fresh_engine(duration_hours=500.0)
    first = engine.run()[0]["aggregate_soc"]
    second_run = engine.run()
    assert second_run[0]["aggregate_soc"] != first
    assert len(engine.history) == engine.n_steps, "history appended, not replaced"


# =============================================================================
# G — EXPORT.  Round trips and column order.
# =============================================================================

def test_json_round_trips_exactly(tmp_path, outpost):
    engine = SimulationEngine(outpost, duration_hours=48.0)
    engine.run()
    path = str(tmp_path / "nested" / "history.json")
    engine.to_json(path)
    assert json.load(open(path)) == engine.history


def test_csv_column_order_follows_the_record_schema(tmp_path, outpost):
    """Alphabetising would scatter gen:, soc: and load: away from each other."""
    engine = SimulationEngine(outpost, duration_hours=48.0)
    engine.run()
    path = str(tmp_path / "history.csv")
    engine.to_csv(path)
    with open(path) as handle:
        rows = list(csv.DictReader(handle))
    assert list(rows[0]) == list(engine.history[0])
    assert len(rows) == len(engine.history)


def test_export_creates_missing_parent_directories(tmp_path, outpost):
    engine = SimulationEngine(outpost, duration_hours=24.0)
    engine.run()
    path = str(tmp_path / "a" / "b" / "c" / "history.csv")
    engine.to_csv(path)
    assert os.path.exists(path)


# =============================================================================
# G — SUMMARY.  Totals that must agree with the history they came from.
# =============================================================================

def test_summary_energies_agree_with_the_history(nominal_history, outpost):
    engine = SimulationEngine(outpost)
    engine.history = nominal_history
    summary = engine.summary()
    demand_kwh = (sum(r["demand_w"] for r in nominal_history)
                  * TIME_STEP_HOURS / 1000.0)
    assert (summary["served_kwh"] + summary["unserved_kwh"]) == pytest.approx(
        demand_kwh, abs=1e-9)
    assert summary["steps"] == len(nominal_history)


def test_summary_extremes_match_the_history(nominal_history, outpost):
    engine = SimulationEngine(outpost)
    engine.history = nominal_history
    summary = engine.summary()
    assert summary["min_aggregate_soc"] == min(
        r["aggregate_soc"] for r in nominal_history)
    assert summary["min_headroom_w"] == min(
        r["headroom_w"] for r in nominal_history)
    assert summary["actions"] == sum(1 for r in nominal_history if r["action"])
