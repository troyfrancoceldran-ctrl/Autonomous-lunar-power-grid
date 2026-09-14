#include "ekf.hpp"

#include <stdexcept>

namespace lunar {

double docv_dsoc(double soc) {
    (void)soc;
    // B02 function 1. Analytic derivative of params::ocv_v.
    // Mind the chain rule: the polynomial is in x = 2*soc - 1.
    throw std::logic_error("B02: docv_dsoc not implemented");
}

double Ekf::update(double current_a, double terminal_voltage_v, double dt_s) {
    (void)current_a;
    (void)terminal_voltage_v;
    (void)dt_s;
    // -Wunused-private-field is an error here, and a stub that never touches
    // its own tuning would trip it. Delete these two lines when the six lines
    // of the filter start using them for real.
    (void)q_proc_;
    (void)r_meas_;
    // B02 function 2. The six lines, in order. See ekf.hpp.
    throw std::logic_error("B02: Ekf::update not implemented");
}

}  // namespace lunar
