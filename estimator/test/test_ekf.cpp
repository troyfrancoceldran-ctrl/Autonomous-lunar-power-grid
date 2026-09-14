// test_ekf.cpp — the filter's tests, and the harness's own.
//
// Written from the spec before the filter, as T01 and T04 were: a test that
// disagrees with an implementation is then a real argument about which is
// wrong, rather than a restatement of whatever the code happens to do.
//
// Nothing here asserts a number copied out of an implementation. Every
// expectation is either derived independently in the test, or is a property
// that holds whatever the constants are.
#include "harness.hpp"
#include "ekf.hpp"
#include "battery_params.hpp"

#include <cmath>
#include <stdexcept>

using harness::check;
using harness::close;
namespace P = lunar::params;

// --- the harness itself, checked before anything trusts it ------------------

TEST(harness_close_accepts_exact_equality) { close(1.0, 1.0, 1e-9, "identical"); }

TEST(harness_close_rejects_outside_tolerance) {
    bool threw = false;
    try { close(1.0, 1.1, 1e-9, "should fail"); }
    catch (const harness::Failure&) { threw = true; }
    check(threw, "close() must reject a 10% difference");
}

TEST(harness_close_treats_near_zero_absolutely) { close(0.0, 1e-18, 1e-9, "zero"); }

// --- the generated curve: works now -----------------------------------------

TEST(ocv_is_monotonic_across_the_usable_range) {
    // The property the whole estimator rests on. Where dOCV/dz <= 0, one
    // voltage means two charges and state of charge stops being observable.
    double previous = P::ocv_v(P::SOC_MIN);
    for (int i = 1; i <= 2000; ++i) {
        const double z = P::SOC_MIN + (P::SOC_MAX - P::SOC_MIN) * i / 2000.0;
        const double v = P::ocv_v(z);
        check(v > previous, "OCV must increase with state of charge");
        previous = v;
    }
}

TEST(ocv_returns_pack_volts_not_cell_volts) {
    // 32 cells at ~3.74 V is ~120 V, which is what the bus expects. A cell-
    // scale return would be a factor-of-32 error surfacing elsewhere.
    const double v = P::ocv_v(0.5);
    check(v > 100.0 && v < 140.0, "pack OCV at 50% should be ~120 V");
}

// --- function 1: the Jacobian ------------------------------------------------

TEST(jacobian_matches_a_numerical_derivative) {
    // THE chain-rule test. The polynomial is in x = 2*soc - 1, so an analytic
    // derivative that forgets dx/dsoc = 2 comes out exactly half. A finite
    // difference knows nothing about the mapping and cannot make that mistake.
    const double h = 1e-6;
    for (double z : {0.10, 0.25, 0.50, 0.75, 0.95}) {
        double analytic;
        try { analytic = lunar::docv_dsoc(z); }
        catch (const std::logic_error& e) { throw harness::NotImplemented(e.what()); }
        const double numerical = (P::ocv_v(z + h) - P::ocv_v(z - h)) / (2.0 * h);
        close(analytic, numerical, 1e-5, "dOCV/dsoc against finite difference");
    }
}

TEST(jacobian_is_positive_everywhere_usable) {
    double first;
    try { first = lunar::docv_dsoc(P::SOC_MIN); }
    catch (const std::logic_error& e) { throw harness::NotImplemented(e.what()); }
    check(first > 0.0, "slope must be positive at the floor");
    for (int i = 0; i <= 1000; ++i) {
        const double z = P::SOC_MIN + (P::SOC_MAX - P::SOC_MIN) * i / 1000.0;
        check(lunar::docv_dsoc(z) > 0.0, "slope must be positive everywhere");
    }
}

// --- function 2: the filter --------------------------------------------------

static double try_update(lunar::Ekf& f, double i, double v, double dt) {
    try { return f.update(i, v, dt); }
    catch (const std::logic_error& e) { throw harness::NotImplemented(e.what()); }
}

TEST(discharging_lowers_the_estimate) {
    // Sign check. Positive current discharges, so the predict step subtracts.
    lunar::Ekf f(0.8, 1e-6, 1e-12, 1e6);   // huge R_meas: ignore the voltmeter
    const double before = f.soc();
    try_update(f, 400.0, P::ocv_v(0.8), 3600.0);
    check(f.soc() < before, "a discharge must reduce the estimate");
}

TEST(coulomb_counting_alone_tracks_the_true_charge) {
    // With the voltmeter distrusted into irrelevance the filter is pure
    // integration, so it must reproduce the coulomb count exactly.
    lunar::Ekf f(0.9, 1e-9, 0.0, 1e12);
    const double amps = 200.0, dt = 60.0, steps = 10;
    for (int i = 0; i < steps; ++i) try_update(f, amps, P::ocv_v(0.9), dt);
    const double expected = 0.9 - P::COULOMBIC_EFFICIENCY * amps * dt * steps
                                  / (3600.0 * P::CAPACITY_AH);
    close(f.soc(), expected, 1e-6, "pure coulomb counting");
}

TEST(a_trusted_measurement_pulls_the_estimate_toward_truth) {
    // Start the filter badly wrong, hand it a clean measurement of a pack that
    // is really at 0.60, and it must move most of the way in one step.
    lunar::Ekf f(0.90, 1.0, 1e-9, 1e-8);   // unsure of itself, trusts the meter
    const double truth = 0.60;
    try_update(f, 0.0, P::ocv_v(truth), 1.0);
    check(std::fabs(f.soc() - truth) < std::fabs(0.90 - truth),
        "the estimate must move toward the measurement");
}

TEST(the_estimate_stays_inside_physical_bounds) {
    lunar::Ekf f(P::SOC_MIN + 0.01, 1e-6, 1e-12, 1e6);
    for (int i = 0; i < 50; ++i) try_update(f, 450.0, P::ocv_v(0.05), 3600.0);
    check(f.soc() >= P::SOC_MIN - 1e-12, "estimate must not fall below SOC_MIN");
    check(f.soc() <= P::SOC_MAX + 1e-12, "estimate must not rise above SOC_MAX");
}

TEST(a_correction_reduces_variance) {
    // Confidence decays on predict and recovers on correct. If variance only
    // ever grows, the gain collapses and the filter goes deaf.
    lunar::Ekf f(0.7, 1.0, 1e-9, 1e-6);
    const double before = f.variance();
    try_update(f, 0.0, P::ocv_v(0.7), 1.0);
    check(f.variance() < before, "a measurement must increase confidence");
}

TEST(gain_falls_when_the_sensor_is_distrusted) {
    // K = PH/(H^2 P + R). Raising R must lower K — the one relationship that
    // says the filter is weighing evidence rather than following it.
    lunar::Ekf trusting(0.7, 1e-4, 1e-9, 1e-8);
    lunar::Ekf doubting(0.7, 1e-4, 1e-9, 1e+2);
    try_update(trusting, 0.0, P::ocv_v(0.7), 1.0);
    try_update(doubting, 0.0, P::ocv_v(0.7), 1.0);
    check(doubting.gain() < trusting.gain(),
        "a distrusted sensor must produce a smaller gain");
}

TEST(a_biased_current_sensor_produces_BOUNDED_error) {
    // THE POINT OF THE WHOLE EXERCISE.
    //
    // A plant discharging steadily, and a current sensor reading high by a
    // fixed amount. Pure coulomb counting drifts without limit — 42 % across
    // one lunar night. The filter cannot REMOVE the bias (it is not in the
    // state vector) but it must BOUND the error, settling where the voltage
    // correction balances the coulomb drift.
    //
    // Bounded, not zero. A test demanding zero would be demanding a filter
    // this one is not.
    const double amps = 150.0, dt = 60.0;
    double truth = 0.90;
    lunar::Ekf f(0.90, 1e-6, 1e-9, P::VOLTAGE_SENSOR_NOISE_V * P::VOLTAGE_SENSOR_NOISE_V);

    double worst_late = 0.0;
    for (int k = 0; k < 600; ++k) {
        truth -= P::COULOMBIC_EFFICIENCY * amps * dt / (3600.0 * P::CAPACITY_AH);
        const double v_true = P::ocv_v(truth) - amps * P::R_INTERNAL_OHM;
        try_update(f, amps + P::CURRENT_SENSOR_BIAS_A, v_true, dt);
        if (k > 300) worst_late = std::fmax(worst_late, std::fabs(f.soc() - truth));
    }
    check(worst_late < 0.10,
        "error must settle below 10 % SoC despite an uncorrected bias");
}
