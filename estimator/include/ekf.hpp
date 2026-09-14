// ekf.hpp — a one-state Extended Kalman Filter for state of charge.
//
// B01 gave the battery terminals. This infers the charge behind them.
//
//==============================================================================
// WHAT A KALMAN FILTER IS
//==============================================================================
// A weighted average between something you predicted and something you
// measured, where the weights come from how much you trust each. Everything
// else is bookkeeping for those weights.
//
// You are walking a corridor with your eyes shut, counting paces. Counting is
// smooth and precise over a few steps, but the error grows without bound — you
// will never notice you are drifting left. Occasionally you open your eyes and
// glimpse a doorway through fog: blurry, but it does not drift. Neither alone
// is good enough, and the filter is the rule for combining them.
//
//     counting paces      coulomb counting — smooth, drifts on sensor bias
//     glimpsing the door  terminal voltage — noisy, but anchored to reality
//
// ONE STATE, so there are no matrices. All six equations are scalar
// arithmetic, and every intermediate can be printed and watched.
//
//==============================================================================
// THE SIX LINES
//==============================================================================
//   PREDICT — where coulomb counting says you are, and how much less sure
//             you are for having guessed
//
//       z  <-  z - eta*I*dt / (3600*Q)
//       P  <-  P + Q_proc
//
//   CORRECT — what the voltmeter says, blended in proportion to trust
//
//       H  <-  dOCV/dz            evaluated at the PREDICTED z
//       V_pred <- OCV(z) - I*R
//       K  <-  P*H / (H*H*P + R_meas)
//       z  <-  z + K * (V_meas - V_pred)
//       P  <-  (1 - K*H) * P
//
// K is the only interesting quantity: near 0 means ignore the voltmeter, near
// 1 means trust it completely. Note where H sits — that is why the OCV slope
// has been the thread through all of this. A flat curve drives H to zero,
// which drives K to zero, and the filter stops listening to measurements
// however good the voltmeter is. Not a tuning problem: the chemistry.
//
// The "EXTENDED" part is only this: the measurement is a NONLINEAR function of
// the state (the OCV curve), so it is linearised at each step by taking its
// slope. H is the extension. That is the whole difference from a plain Kalman
// filter.
//
//==============================================================================
// WHAT TO IMPLEMENT                                                <- B02
//==============================================================================
// Two functions, both in src/ekf.cpp.
//
// 1.  docv_dsoc(soc) -> double
//
//     The measurement Jacobian: pack volts per unit state of charge. The
//     analytic derivative of params::ocv_v.
//
//     TRAP — THE CHAIN RULE. The polynomial is in x = 2*soc - 1, not in soc.
//     So differentiating the coefficients gives you dOCV/dx, and
//
//         dOCV/dsoc = dOCV/dx * dx/dsoc = dOCV/dx * 2
//
//     Forget the factor of 2 and every gain is half what it should be. The
//     filter still runs, still converges, just slower — which is exactly the
//     kind of wrong that survives a demo. test_jacobian_matches_numerical
//     catches it by comparing against a finite difference.
//
//     TRAP — PACK SCALE. ocv_v multiplies by CELLS_SERIES, so its derivative
//     must too, or H is 32x too small.
//
// 2.  Ekf::update(current_a, terminal_voltage_v, dt_s) -> double
//
//     The six lines above, in order. Returns the updated estimate.
//
//     TRAP — H AT THE PREDICTED STATE. Evaluate the Jacobian after the predict
//     step, not before. Linearising about the old state is a different filter,
//     and a worse one.
//
//     TRAP — SIGN. current_a is POSITIVE DISCHARGING, matching B01, so the
//     predict step SUBTRACTS. Get it backwards and the estimate climbs while
//     the pack empties.
//
//     TRAP — CLAMP AFTER, NOT BEFORE. A correction can push the estimate
//     outside [SOC_MIN, SOC_MAX], which is unphysical. Clamp z at the end.
//     Do not clamp P: it is a variance, and squeezing it lies to the filter
//     about its own confidence.
//
//     @note The bias is NOT in the state vector, so this filter cannot
//         estimate it and will NOT remove it. Expect a steady-state offset
//         where the voltage correction balances the coulomb drift. That is
//         the RESULT, not a bug: the filter converts UNBOUNDED drift into
//         BOUNDED error. Pure coulomb counting runs to 42 % across one lunar
//         night and keeps going; this should settle somewhere smaller and
//         stay. Measuring where is B04.
//
//==============================================================================
// TUNING
//==============================================================================
// Two knobs, and they are really a ratio — tuning a Kalman filter is mostly
// deciding which of your two liars lies less.
//
//   Q_proc   how much you distrust your own prediction. Larger leans on the
//            voltmeter. It stands in for everything the model omits: sensor
//            bias, an ageing capacity, a resistance that moves with
//            temperature. A filter with Q_proc = 0 believes its model
//            perfectly and will ignore evidence to the contrary forever.
//
//   R_meas   how much you distrust the sensor. Larger leans on counting.
//            A reasonable starting point is the measurement variance —
//            VOLTAGE_SENSOR_NOISE_V squared — but it is a BELIEF, not a
//            measurement. How noisy the sensor is and how noisy the filter
//            thinks it is are two different numbers, and setting them equal
//            assumes the model is otherwise perfect.
//
#pragma once

#include "battery_params.hpp"

namespace lunar {

/// The measurement Jacobian: d(pack OCV)/d(state of charge), volts per unit.
/// Free function so the tests can check it without constructing a filter.
double docv_dsoc(double soc);

class Ekf {
  public:
    /// @param initial_soc  the prior — what you believe before any evidence
    /// @param initial_var  how strongly. Large means "I am guessing", and the
    ///                     first measurement will move the estimate a long way.
    /// @param q_proc       process variance per step
    /// @param r_meas       measurement variance
    Ekf(double initial_soc, double initial_var, double q_proc, double r_meas)
        : soc_(initial_soc), variance_(initial_var),
          q_proc_(q_proc), r_meas_(r_meas) {}

    double soc() const { return soc_; }
    double variance() const { return variance_; }

    /// The gain from the last update. Exposed because it is the one number
    /// that says what the filter is actually doing: near zero means it has
    /// stopped believing the voltmeter.
    double gain() const { return gain_; }

    /// One predict/correct cycle.
    /// @param current_a            pack current [A], POSITIVE discharging
    /// @param terminal_voltage_v   what the voltmeter reported [V]
    /// @param dt_s                 seconds since the previous call
    /// @return the updated state-of-charge estimate
    double update(double current_a, double terminal_voltage_v, double dt_s);

  private:
    double soc_;
    double variance_;
    double q_proc_;
    double r_meas_;
    double gain_ = 0.0;
};

}  // namespace lunar
