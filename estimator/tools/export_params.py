"""
@file    estimator/tools/export_params.py
@brief   Generate estimator/include/battery_params.hpp from config.py.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-14

@details
The filter has to predict a measurement, and to do that it needs the same
battery the simulation has — same OCV curve, same internal resistance, same
capacity. Hand-copying eight polynomial coefficients into a C++ header works
exactly once, and then someone refits the curve on one side only and the
filter quietly starts estimating a battery that does not exist.

So the header is GENERATED, exactly as web/src/config.js is:

    .venv/bin/python estimator/tools/export_params.py

@note ocv_v() is generated too, not just its coefficients. It is a direct port
    of BatteryBank.open_circuit_voltage_v — same Horner evaluation, same
    x = 2*soc - 1 mapping, same pack scaling — so the two languages cannot
    disagree about what the curve IS. What is deliberately NOT generated is
    its derivative: dOCV/dsoc is the measurement Jacobian, it is the heart of
    the filter, and writing it is B02's job.
@note constexpr throughout, so none of this costs a byte of RAM on the target.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import config as cfg  # noqa: E402

HEADER = '''// GENERATED FILE — do not edit.
//
// Produced by estimator/tools/export_params.py from config.py, so the filter
// and the simulation cannot disagree about the battery. Change config.py and
// re-run the generator.
//
// Portable C++17: no Arduino.h, no vendor SDK, no dynamic allocation. Every
// value is constexpr, so none of it costs RAM on the target.
#pragma once

namespace lunar {{
namespace params {{

// --- the pack ---------------------------------------------------------------

/// Cells in series. Pack volts = cells * cell volts.
constexpr int CELLS_SERIES = {cells};

/// Pack ohmic resistance. DERIVED from BATTERY_DISCHARGE_EFFICIENCY at the
/// rated operating point — R = OCV(1-eta)/I_rated — not chosen independently,
/// because the efficiency already accounts for the same loss.
constexpr double R_INTERNAL_OHM = {r_internal!r};

/// Usable charge, from BATTERY_CAPACITY_WH at nominal pack voltage.
/// {capacity_wh:.0f} Wh / ({cells} x {cell_nominal} V) = {capacity_ah:.1f} Ah.
constexpr double CAPACITY_AH = {capacity_ah!r};

/// Coulombic efficiency used by the predict step — amp-hours out per
/// amp-hour in. NOT BATTERY_DISCHARGE_EFFICIENCY, which counts watt-hours
/// and carries the ohmic losses the IR term already models. See config.py.
constexpr double COULOMBIC_EFFICIENCY = {coulombic!r};

/// Floor and ceiling. The filter's estimate is clamped to these: a state of
/// charge outside them is not merely unlikely, it is unphysical.
constexpr double SOC_MIN = {soc_min!r};
constexpr double SOC_MAX = {soc_max!r};

// --- the instruments --------------------------------------------------------
// Present so the tests can build a plant that matches the Python one. The
// filter itself should read R_MEAS from its own tuning, not from here — how
// noisy the sensor IS and how noisy the filter BELIEVES it to be are two
// different numbers, and conflating them is how a filter gets overconfident.

constexpr double CURRENT_SENSOR_NOISE_A = {i_noise!r};
constexpr double CURRENT_SENSOR_BIAS_A = {i_bias!r};
constexpr double VOLTAGE_SENSOR_NOISE_V = {v_noise!r};

// --- the curve --------------------------------------------------------------

/// Degree-{degree} least-squares fit of the NMC cell curve, in the mapped
/// variable x = 2*soc - 1. ASCENDING order: c[0] + c[1]x + c[2]x^2 + ...
/// Max fit error 6.3 mV per cell; monotonic on [0.05, 1.0], which is the
/// property the whole estimator rests on.
constexpr int OCV_POLY_N = {n_coeff};
constexpr double OCV_POLY[OCV_POLY_N] = {{
{coeffs}
}};

/// Pack open-circuit voltage at a state of charge.
///
/// A direct port of BatteryBank.open_circuit_voltage_v: Horner over the
/// ASCENDING coefficients, which is why the loop runs downward. Evaluating it
/// upward gives a different polynomial that still returns plausible voltages.
inline double ocv_v(double soc) {{
    const double x = 2.0 * soc - 1.0;
    double result = 0.0;
    for (int i = OCV_POLY_N - 1; i >= 0; --i) {{
        result = result * x + OCV_POLY[i];
    }}
    return result * static_cast<double>(CELLS_SERIES);
}}

}}  // namespace params
}}  // namespace lunar
'''


def main():
    cells = cfg.CELLS_SERIES
    cell_nominal = 3.70
    capacity_ah = cfg.BATTERY_CAPACITY_WH / (cell_nominal * cells)
    coeffs = "\n".join(
        f"    {v!r},{'' if i == len(cfg.OCV_POLY_NMC) - 1 else ''}   // x^{i}"
        for i, v in enumerate(cfg.OCV_POLY_NMC))

    text = HEADER.format(
        cells=cells,
        r_internal=cfg.BATTERY_R_INTERNAL_OHM,
        capacity_wh=cfg.BATTERY_CAPACITY_WH,
        cell_nominal=cell_nominal,
        capacity_ah=capacity_ah,
        coulombic=cfg.BATTERY_COULOMBIC_EFFICIENCY,
        soc_min=cfg.BATTERY_SOC_MIN,
        soc_max=cfg.BATTERY_SOC_MAX,
        i_noise=cfg.CURRENT_SENSOR_NOISE_A,
        i_bias=cfg.CURRENT_SENSOR_BIAS_A,
        v_noise=cfg.VOLTAGE_SENSOR_NOISE_V,
        degree=len(cfg.OCV_POLY_NMC) - 1,
        n_coeff=len(cfg.OCV_POLY_NMC),
        coeffs=coeffs,
    )

    path = os.path.join(ROOT, "estimator", "include", "battery_params.hpp")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    print(f"  wrote {os.path.relpath(path, ROOT)}")
    print(f"  {len(cfg.OCV_POLY_NMC)} coefficients, "
        f"{cells}S, {capacity_ah:.1f} Ah, "
          f"{cfg.BATTERY_R_INTERNAL_OHM * 1000:.1f} mohm")


if __name__ == "__main__":
    main()
