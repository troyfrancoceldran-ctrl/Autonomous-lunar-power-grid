#include "ekf.hpp"

#include <stdexcept>

namespace lunar {

// ============================ START EDITING HERE ============================
// Two functions. The spec, the six equations and the four traps are all in
// ekf.hpp; docs/ekf_formulas.pdf is the same material typeset, with charts.
// If the C++ rather than the filter is the unfamiliar part: CPP_NOTES.md.
//
// Order of work: docv_dsoc first — jacobian_matches_a_numerical_derivative
// checks it against a finite difference in isolation, so you can have it
// PROVEN right before update() is allowed to depend on it.
//
//   cmake --build estimator/build && ./estimator/build/test_ekf
//
// 9 tests are SKIPPING. They are the specification, and they go green in the
// order you write.
// ============================================================================

double docv_dsoc(double soc) {
    const double x = 2.0 * soc - 1.0;
    double result = 0.0;
    for (int i = params::OCV_POLY_N - 1; i >= 1; --i){
         result = result * x + static_cast<double>(i) * params::OCV_POLY[i];
    }
    return result * static_cast<double>(params::CELLS_SERIES) * 2;
}


double Ekf::update(double current_a, double terminal_voltage_v, double dt_s) {
    (void)current_a;
    (void)terminal_voltage_v;
    (void)dt_s;

    (void)q_proc_;
    (void)r_meas_;

    // B02 function 2. The six lines, in order. See ekf.hpp.
    //
    // Scratch kept for reference — commented out so the suite reports SKIP
    // rather than FAIL. The skip mechanism keys off the logic_error below:
    // a placeholder that RETURNS makes seven tests fail, which buries the
    // one signal that matters while function 2 is being written.
    //
    // const double x = 2.0 - 1.0;
    // double result = 0.0;
    // for (int i = params::OCV_POLY_N - 1; i >= 0; --i){
    //      result = result * x + static_cast<double>(i) * params::OCV_POLY[i];
    // }
    // return result * static_cast<double>(params::CELLS_SERIES) * 2;

    
    throw std::logic_error("B02: Ekf::update not implemented");
}

}  // namespace lunar
