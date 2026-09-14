// test_ekf.cpp — the filter's tests, and the harness's own.
//
// Written before the filter, as T01 and T04 were: a test that disagrees with
// an implementation is then a real argument about which is wrong, rather than
// a restatement of whatever the code happens to do.
#include "harness.hpp"
#include "ekf.hpp"

#include <stdexcept>

using harness::check;
using harness::close;

// --- the harness itself, checked before anything trusts it ------------------
// The Sharma vectors did this job for CIEDE2000: verify the measuring device
// before you measure with it.

TEST(harness_close_accepts_exact_equality) {
    close(1.0, 1.0, 1e-9, "identical values");
}

TEST(harness_close_accepts_within_tolerance) {
    close(1.0, 1.0 + 1e-12, 1e-9, "inside tolerance");
}

TEST(harness_close_rejects_outside_tolerance) {
    bool threw = false;
    try {
        close(1.0, 1.1, 1e-9, "should fail");
    } catch (const harness::Failure&) {
        threw = true;
    }
    check(threw, "close() must reject a 10% difference");
}

TEST(harness_close_treats_near_zero_absolutely) {
    // A value that should be 0.0 arriving as 1e-18 is agreement, not a 100%
    // relative error. Without this floor every zero-valued field fails.
    close(0.0, 1e-18, 1e-9, "near zero");
}

// --- the filter: skips until B02 lands --------------------------------------

TEST(ekf_starts_at_a_known_state) {
    lunar::BatteryParams p;
    p.capacity_ah = 100.0;
    p.r_internal_ohm = 0.01;
    lunar::Ekf f(p);
    check(f.soc() == 1.0, "a fresh filter should start from its prior");
}

TEST(ekf_update_is_implemented) {
    lunar::BatteryParams p;
    p.capacity_ah = 100.0;
    p.r_internal_ohm = 0.01;
    lunar::Ekf f(p);
    try {
        f.update(10.0, 3.9, 1.0);
    } catch (const std::logic_error& e) {
        throw harness::NotImplemented(e.what());
    }
}
