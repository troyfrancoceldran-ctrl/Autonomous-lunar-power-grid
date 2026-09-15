"""
@file    web/tools/export_ekf_golden.py
@brief   Golden trace for the browser EKF, generated from the C++ filter.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-15

@details
web/src/ekf.js is a port of estimator/src/ekf.cpp so the page can show the
filter working tick by tick rather than replay a chart computed elsewhere. A
port nobody checks is a second source of truth, and the first time it drifts
the page starts lying about what the estimator does.

So this drives the REAL filter — the compiled C++, through ctypes — over a
deterministic input trace and records what it produced. The JS is then held to
that, exactly as the simulation port is held to its own goldens.

    .venv/bin/python web/tools/export_ekf_golden.py
    .venv/bin/python web/tools/run_conformance.py

@note The trace deliberately crosses the whole usable range and includes
    charge as well as discharge, because the OCV slope varies by an order of
    magnitude across it and a port can agree in the middle while diverging at
    the ends.
@note Inputs are computed in Python and stored, rather than regenerated in JS.
    A golden that asks the port to reproduce its own inputs is testing the
    random number generator, not the filter.
"""

import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import soc_estimator  # noqa: E402
from config import (BATTERY_CAPACITY_WH, BATTERY_R_INTERNAL_OHM,  # noqa: E402
                    CELLS_SERIES, VOLTAGE_SENSOR_NOISE_V)

STEPS = 600
DT_S = 60.0


def main():
    lib = soc_estimator.library()
    capacity_ah = lib.ekf_capacity_ah()

    # A trace that sweeps the range: discharge hard, rest, then recharge. The
    # sign flip matters — a port that has the predict step backwards agrees
    # perfectly until the current changes direction.
    inputs = []
    truth = 0.95
    for k in range(STEPS):
        if k < 300:
            current_a = 60.0
        elif k < 380:
            current_a = 0.0
        else:
            current_a = -45.0
        truth -= current_a * DT_S / (3600.0 * capacity_ah)
        truth = min(max(truth, 0.05), 1.0)
        # A deterministic wobble standing in for sensor noise. Reproducible in
        # both languages because it is stored, not regenerated.
        noise = VOLTAGE_SENSOR_NOISE_V * math.sin(k * 0.37)
        voltage_v = (lib.ekf_ocv_v(truth) - current_a * BATTERY_R_INTERNAL_OHM
                     + noise)
        inputs.append([current_a, voltage_v, DT_S])

    f = soc_estimator.Ekf(0.95, 1e-6, 1e-9, VOLTAGE_SENSOR_NOISE_V ** 2)
    ticks = []
    for current_a, voltage_v, dt_s in inputs:
        f.update(current_a, voltage_v, dt_s)
        ticks.append([f.soc, f.variance, f.gain])

    golden = {
        "source": "estimator/src/ekf.cpp via ctypes",
        "initial": {"soc": 0.95, "variance": 1e-6, "qProc": 1e-9,
                    "rMeas": VOLTAGE_SENSOR_NOISE_V ** 2},
        "constants": {
            "capacityAh": capacity_ah,
            "coulombicEfficiency": lib.ekf_coulombic_efficiency(),
            "rInternalOhm": lib.ekf_r_internal_ohm(),
            "cellsSeries": lib.ekf_cells_series(),
            "vNominal": BATTERY_CAPACITY_WH / capacity_ah,
        },
        "curve": [[z / 100.0, lib.ekf_ocv_v(z / 100.0),
                   lib.ekf_docv_dsoc(z / 100.0)] for z in range(5, 101)],
        "inputs": inputs,
        "ticks": ticks,
    }

    path = os.path.join(ROOT, "web", "golden", "ekf.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(golden, handle, separators=(",", ":"))
    size_kb = os.path.getsize(path) / 1024
    print(f"  wrote {os.path.relpath(path, ROOT)}")
    print(f"  {len(ticks)} ticks, {len(golden['curve'])} curve points, "
          f"{size_kb:.1f} KB")
    print(f"  final estimate {ticks[-1][0]:.6f}, "
          f"gain {ticks[-1][2]:.3e}")


if __name__ == "__main__":
    main()
