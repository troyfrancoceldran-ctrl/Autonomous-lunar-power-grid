#include "ekf.hpp"

#include <stdexcept>

namespace lunar {

double Ekf::update(double current_a, double terminal_voltage_v, double dt_s) {
    (void)current_a;
    (void)terminal_voltage_v;
    (void)dt_s;
    // B02. Waiting on B01 to pin the measurement model — see ekf.hpp.
    throw std::logic_error("B02: Ekf::update not implemented");
}

}  // namespace lunar
