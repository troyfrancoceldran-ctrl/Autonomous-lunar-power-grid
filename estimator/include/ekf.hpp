// ekf.hpp — the state-of-charge estimator.
//
// PLACEHOLDER INTERFACE. The shape below is safe for any EKF on this problem;
// what it deliberately does NOT yet fix is the state vector, because that is
// pinned by B01. A filter tracking only SoC is one state; one that also tracks
// a polarisation voltage across an RC pair is two, and which is right depends
// on the battery model the simulation is about to grow. Specifying it before
// B01 exists would be guessing, and the measurement model has to match the
// plant exactly or the filter is estimating a battery that is not there.
//
// Portable C++17. No Arduino.h, no ESP-IDF, no dynamic allocation, no
// exceptions on the hot path — this has to cross-compile for a microcontroller
// without a rewrite.
#pragma once

namespace lunar {

/// Battery parameters the filter needs in order to predict a measurement.
/// Populated from the simulation's own constants, never re-typed by hand —
/// the same discipline that generates web/src/config.js from config.py.
struct BatteryParams {
    double capacity_ah = 0.0;      ///< usable charge
    double r_internal_ohm = 0.0;   ///< ohmic drop, V = OCV(soc) - I*R
};

class Ekf {
  public:
    explicit Ekf(const BatteryParams& params) : params_(params) {}

    /// Best current estimate of state of charge, in [0, 1].
    double soc() const { return soc_; }

    /// Estimator confidence — the state variance. Worth exposing because a
    /// controller that acts on an estimate should be able to ask how much the
    /// estimate is worth, and B04 will want it.
    double variance() const { return variance_; }

    /// One predict/correct cycle from a terminal measurement.
    /// @param current_a            positive discharging, negative charging
    /// @param terminal_voltage_v   what a voltmeter across the pack reads
    /// @param dt_s                 seconds since the previous call
    /// @return the updated state-of-charge estimate
    double update(double current_a, double terminal_voltage_v, double dt_s);

  private:
    BatteryParams params_;
    double soc_ = 1.0;
    double variance_ = 0.0;
};

}  // namespace lunar
