// ekf_c_api.h — a flat C surface over the filter, for callers that are not C++.
//
// WHY THIS EXISTS
// ---------------
// B04 asks what the outpost costs when its controller acts on an ESTIMATE
// rather than on truth. The simulation is Python; the filter is C++. The
// measurement is only worth having if it exercises THE filter rather than a
// second implementation that resembles it — a Python port would have to be
// kept in step by hand, and the first time it drifted the table would be
// quietly wrong.
//
// So Python calls this, through ctypes, which is in the standard library.
// No pybind11, no build-time dependency, nothing to install.
//
// It is also the shape B03 needs. A serial bridge to an ESP32 marshals scalars
// across a boundary exactly like this one; doing it in-process first means the
// hard part is debugged before a cable is involved.
//
// @note HOST ONLY. These wrappers allocate, and the filter is deliberately
//     allocation-free so it can flash to a microcontroller. ekf.cpp is what
//     goes on the target; this file does not.
#ifdef __cplusplus
extern "C" {
#endif

/// Construct a filter. Returns an opaque handle, or NULL on failure.
/// @param initial_soc  the prior — what you believe before any evidence
/// @param initial_var  how strongly. Large means "I am guessing".
/// @param q_proc       process variance per step
/// @param r_meas       measurement variance
void *ekf_create(double initial_soc, double initial_var,
                double q_proc, double r_meas);

/// Release a handle from ekf_create. Safe to call with NULL.
void ekf_destroy(void *handle);

/// One predict/correct cycle. @return the updated state-of-charge estimate.
double ekf_update(void *handle, double current_a,
                double terminal_voltage_v, double dt_s);

double ekf_soc(const void *handle);
double ekf_variance(const void *handle);
double ekf_gain(const void *handle);

/// Free functions, exposed so a caller can check the curve it is estimating
/// against without constructing a filter.
double ekf_ocv_v(double soc);
double ekf_docv_dsoc(double soc);

/// Compile-time constants, so a Python caller never hard-codes a second copy
/// of the battery. Every one of these is generated from config.py.
double ekf_capacity_ah(void);
double ekf_coulombic_efficiency(void);
double ekf_r_internal_ohm(void);
double ekf_soc_min(void);
double ekf_soc_max(void);
int    ekf_cells_series(void);

#ifdef __cplusplus
}  // extern "C"
#endif
