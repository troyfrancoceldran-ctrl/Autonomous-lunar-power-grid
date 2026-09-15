// ekf_c_api.cpp — the flat C surface. See ekf_c_api.h for why it exists.
//
// Nothing here is filter logic. Every function forwards, and the arithmetic
// stays in ekf.cpp where the tests can reach it.
#include "ekf_c_api.h"

#include <new>

#include "ekf.hpp"

namespace {
/// A NULL handle must not crash a caller in another language, where a
/// segfault carries no traceback and no line number.
inline lunar::Ekf *as_filter(void *h) { return static_cast<lunar::Ekf *>(h); }
inline const lunar::Ekf *as_filter(const void *h) {
    return static_cast<const lunar::Ekf *>(h);
}
}  // namespace

extern "C" {

void *ekf_create(double initial_soc, double initial_var,
                double q_proc, double r_meas) {
    return new (std::nothrow) lunar::Ekf(initial_soc, initial_var,
                                        q_proc, r_meas);
}

void ekf_destroy(void *handle) { delete as_filter(handle); }

double ekf_update(void *handle, double current_a,
                double terminal_voltage_v, double dt_s) {
    if (handle == nullptr) return 0.0;
    return as_filter(handle)->update(current_a, terminal_voltage_v, dt_s);
}

double ekf_soc(const void *handle) {
    return handle ? as_filter(handle)->soc() : 0.0;
}
double ekf_variance(const void *handle) {
    return handle ? as_filter(handle)->variance() : 0.0;
}
double ekf_gain(const void *handle) {
    return handle ? as_filter(handle)->gain() : 0.0;
}

double ekf_ocv_v(double soc) { return lunar::params::ocv_v(soc); }
double ekf_docv_dsoc(double soc) { return lunar::docv_dsoc(soc); }

double ekf_capacity_ah(void) { return lunar::params::CAPACITY_AH; }
double ekf_coulombic_efficiency(void) {
    return lunar::params::COULOMBIC_EFFICIENCY;
}
double ekf_r_internal_ohm(void) { return lunar::params::R_INTERNAL_OHM; }
double ekf_soc_min(void) { return lunar::params::SOC_MIN; }
double ekf_soc_max(void) { return lunar::params::SOC_MAX; }
int ekf_cells_series(void) { return lunar::params::CELLS_SERIES; }

}  // extern "C"
