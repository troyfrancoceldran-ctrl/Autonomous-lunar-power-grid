"""
@file    firmware/tools/export_controller_golden.py
@brief   Record every decision the Python controller makes, for the C++ port.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-15

@details
B03 moves the controller onto an ESP32. The claim being made is that it is the
SAME controller — so the port has to be held to the original's decisions,
tick for tick, before it goes anywhere near a board.

This runs the real simulation and records, at every tick, exactly what the
controller was shown and exactly what it did. firmware/test/test_controller.cpp
replays that through the C++ port and requires an identical answer.

    .venv/bin/python firmware/tools/export_controller_golden.py

@note Recorded by WRAPPING controller.update rather than by reconstructing its
    inputs afterwards. A reconstruction is a second implementation of the thing
    under test, and it would agree with the port for the same wrong reasons.
@note The action is recorded as an INDEX into the loads list, not a name. The
    board has no strings and no heap; the protocol is positional, and the
    golden has to test the protocol that will actually run.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from environment import LunarEnvironment          # noqa: E402
from simulation_engine import SimulationEngine    # noqa: E402
import main                                       # noqa: E402
from config import (SOC_SHED_THRESHOLD, SOC_RESTORE_THRESHOLD,  # noqa: E402
                    MIN_ACTION_DWELL_HOURS)


def main_():
    ticks = []
    bus = main.build_outpost(LunarEnvironment(), topology=True, converters=True)
    real_update = bus.controller.update

    def recording_update(t_hours, aggregate_soc, loads, headroom_w):
        # Snapshot BEFORE the call: the controller mutates load.shed, and a
        # view taken afterwards would show the answer as part of the question.
        view = [[int(load.priority), bool(load.shed),
                 float(load.demand(t_hours))] for load in loads]
        action = real_update(t_hours, aggregate_soc, loads, headroom_w)
        if action is None:
            index, shed = -1, False
        else:
            index = [load.name for load in loads].index(action.name)
            shed = bool(action.shed)
        ticks.append({"t": t_hours, "soc": aggregate_soc,
                      "headroom": headroom_w, "loads": view,
                      "index": index, "shed": shed})
        return action

    bus.controller.update = recording_update
    SimulationEngine(bus).run()

    acted = sum(1 for t in ticks if t["index"] >= 0)
    golden = {
        "source": "controller.AutonomousController via the full simulation",
        "policy": {"shed": SOC_SHED_THRESHOLD,
                   "restore": SOC_RESTORE_THRESHOLD,
                   "dwell": MIN_ACTION_DWELL_HOURS},
        "ticks": ticks,
    }
    path = os.path.join(ROOT, "firmware", "test", "controller_golden.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(golden, handle, separators=(",", ":"))
    print(f"  wrote {os.path.relpath(path, ROOT)}")
    print(f"  {len(ticks)} ticks, {acted} of them an action, "
          f"{os.path.getsize(path) / 1024:.0f} KB")


if __name__ == "__main__":
    main_()
