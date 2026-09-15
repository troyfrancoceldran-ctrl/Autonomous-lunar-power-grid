// controller.hpp — the outpost controller, framework-free.
//
// A port of AutonomousController.update in controller.py. It is the SAME
// decision logic, and B03's whole claim is that it stays the same when it
// moves onto a microcontroller.
//
//==============================================================================
// WHY THIS COMPILES ON THE HOST TOO
//==============================================================================
// No Arduino.h, no ESP-IDF headers, no dynamic allocation, no <string>. The
// board's main.cpp owns the serial link and calls into this; this owns the
// policy and knows nothing about how it was asked.
//
// That split is not tidiness. It is what lets the controller be tested
// against a 1440-tick golden trace from the Python original on a laptop,
// where a failure names a line, BEFORE anything is flashed. A controller that
// is wrong on the host is wrong on the ESP32 and far harder to see there.
//
//==============================================================================
// THE POLICY, IN THE ORDER IT IS EVALUATED
//==============================================================================
//   1. POWER emergency   headroom < 0     shed the least important connected
//                                         load. Dwell is deliberately NOT
//                                         consulted: the bus is already
//                                         failing to serve what is on it.
//   2. ENERGY low        soc < shed       same, but dwell applies.
//   3. RECOVERY          soc > restore    restore the most important shed load
//                                         that FITS in the measured headroom.
//   4. otherwise                          idle, inside the hysteresis band.
//
// Priority is an ordinal: LOWER number means MORE important. So shedding takes
// the MAXIMUM priority value and restoring takes the MINIMUM. Getting that
// backwards sheds life support first and still looks like it works.
#pragma once

#include <cstdint>

namespace lunar {

/// Hard ceiling on loads. Static storage only — no allocation on the target.
constexpr int MAX_LOADS = 16;

/// CRITICAL is never shed. Mirrors config.LoadPriority.
constexpr int PRIORITY_CRITICAL = 0;

/// What the host reports about one load at the start of a tick.
struct LoadView {
    int priority;        ///< lower = more important; 0 is CRITICAL
    bool shed;           ///< true if currently disconnected
    double demand_w;     ///< what it would draw if connected
};

/// What the controller decided. index < 0 means it chose to do nothing.
struct Action {
    int index = -1;
    bool shed = false;   ///< true = shed this load, false = restore it
};

class Controller {
  public:
    Controller(double shed_threshold, double restore_threshold,
              double min_dwell_hours)
        : shed_threshold_(shed_threshold),
          restore_threshold_(restore_threshold),
          min_dwell_hours_(min_dwell_hours) {
        for (int i = 0; i < MAX_LOADS; ++i) last_change_h_[i] = NO_CHANGE;
    }

    /// Decide shed/restore for this tick. At most ONE load is acted on.
    /// @param t_hours       simulation time
    /// @param aggregate_soc fleet reserve in [0, 1]
    /// @param headroom_w    signed; negative means the bus cannot meet demand
    /// @param loads         the current view, in the host's own order
    /// @param count         how many entries of `loads` are valid
    Action update(double t_hours, double aggregate_soc, double headroom_w,
                  const LoadView *loads, int count);

    /// Forget every dwell timer. The host calls this between scenarios so a
    /// board that has not been power-cycled does not carry state across runs —
    /// a stale timer is exactly the kind of fault that looks like a model bug.
    void reset();

  private:
    /// Sentinel for "this load has never changed state". A real timestamp can
    /// legitimately be 0.0 (the first tick), so a sentinel is needed rather
    /// than a zero test.
    static constexpr double NO_CHANGE = -1.0e30;

    bool dwell_elapsed(int index, double t_hours) const;

    double shed_threshold_;
    double restore_threshold_;
    double min_dwell_hours_;
    double last_change_h_[MAX_LOADS];
};

}  // namespace lunar
