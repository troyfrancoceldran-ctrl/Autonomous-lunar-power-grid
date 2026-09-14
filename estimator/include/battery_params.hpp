// GENERATED FILE — do not edit.
//
// Produced by estimator/tools/export_params.py from config.py, so the filter
// and the simulation cannot disagree about the battery. Change config.py and
// re-run the generator.
//
// Portable C++17: no Arduino.h, no vendor SDK, no dynamic allocation. Every
// value is constexpr, so none of it costs RAM on the target.
#pragma once

namespace lunar {
namespace params {

// --- the pack ---------------------------------------------------------------

/// Cells in series. Pack volts = cells * cell volts.
constexpr int CELLS_SERIES = 32;

/// Pack ohmic resistance. DERIVED from BATTERY_DISCHARGE_EFFICIENCY at the
/// rated operating point — R = OCV(1-eta)/I_rated — not chosen independently,
/// because the efficiency already accounts for the same loss.
constexpr double R_INTERNAL_OHM = 0.0143;

/// Usable charge, from BATTERY_CAPACITY_WH at nominal pack voltage.
/// 200000 Wh / (32 x 3.7 V) = 1689.2 Ah.
constexpr double CAPACITY_AH = 1689.1891891891892;

/// Coulombic efficiency used by the predict step.
constexpr double COULOMBIC_EFFICIENCY = 0.95;

/// Floor and ceiling. The filter's estimate is clamped to these: a state of
/// charge outside them is not merely unlikely, it is unphysical.
constexpr double SOC_MIN = 0.05;
constexpr double SOC_MAX = 1.0;

// --- the instruments --------------------------------------------------------
// Present so the tests can build a plant that matches the Python one. The
// filter itself should read R_MEAS from its own tuning, not from here — how
// noisy the sensor IS and how noisy the filter BELIEVES it to be are two
// different numbers, and conflating them is how a filter gets overconfident.

constexpr double CURRENT_SENSOR_NOISE_A = 0.5;
constexpr double CURRENT_SENSOR_BIAS_A = 2.0;
constexpr double VOLTAGE_SENSOR_NOISE_V = 0.0068;

// --- the curve --------------------------------------------------------------

/// Degree-7 least-squares fit of the NMC cell curve, in the mapped
/// variable x = 2*soc - 1. ASCENDING order: c[0] + c[1]x + c[2]x^2 + ...
/// Max fit error 6.3 mV per cell; monotonic on [0.05, 1.0], which is the
/// property the whole estimator rests on.
constexpr int OCV_POLY_N = 8;
constexpr double OCV_POLY[OCV_POLY_N] = {
    3.736277252,   // x^0
    0.282556708,   // x^1
    0.022414644,   // x^2
    0.393657303,   // x^3
    0.331825038,   // x^4
    -0.860396242,   // x^5
    -0.490196078,   // x^6
    0.784167834,   // x^7
};

/// Pack open-circuit voltage at a state of charge.
///
/// A direct port of BatteryBank.open_circuit_voltage_v: Horner over the
/// ASCENDING coefficients, which is why the loop runs downward. Evaluating it
/// upward gives a different polynomial that still returns plausible voltages.
inline double ocv_v(double soc) {
    const double x = 2.0 * soc - 1.0;
    double result = 0.0;
    for (int i = OCV_POLY_N - 1; i >= 0; --i) {
        result = result * x + OCV_POLY[i];
    }
    return result * static_cast<double>(CELLS_SERIES);
}

}  // namespace params
}  // namespace lunar
