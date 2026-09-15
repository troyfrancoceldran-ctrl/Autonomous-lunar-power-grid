// controller.cpp — the policy. See controller.hpp for the order it runs in.
#include "controller.hpp"

namespace lunar {

bool Controller::dwell_elapsed(int index, double t_hours) const {
    const double last = last_change_h_[index];
    if (last == NO_CHANGE) return true;
    return t_hours - last >= min_dwell_hours_;
}

void Controller::reset() {
    for (int i = 0; i < MAX_LOADS; ++i) last_change_h_[i] = NO_CHANGE;
}

Action Controller::update(double t_hours, double aggregate_soc,
                          double headroom_w, const LoadView *loads, int count) {
    if (count > MAX_LOADS) count = MAX_LOADS;

    // 1. POWER emergency. Dwell is deliberately not consulted — the bus is
    //    already failing to serve what is connected to it.
    if (headroom_w < 0.0) {
        int target = -1;
        for (int i = 0; i < count; ++i) {
            if (loads[i].shed || loads[i].priority == PRIORITY_CRITICAL) continue;
            // Python's max() keeps the FIRST maximum on ties. Strict > here
            // reproduces that; >= would silently pick the last instead, and
            // the difference only shows up on a tie.
            if (target < 0 || loads[i].priority > loads[target].priority) target = i;
        }
        if (target < 0) return Action{};
        last_change_h_[target] = t_hours;
        return Action{target, true};
    }

    // 2. ENERGY low. Reserves draining, but supply still meets demand.
    if (aggregate_soc < shed_threshold_) {
        int target = -1;
        for (int i = 0; i < count; ++i) {
            if (loads[i].shed || loads[i].priority == PRIORITY_CRITICAL) continue;
            if (!dwell_elapsed(i, t_hours)) continue;
            if (target < 0 || loads[i].priority > loads[target].priority) target = i;
        }
        if (target < 0) return Action{};
        last_change_h_[target] = t_hours;
        return Action{target, true};
    }

    // 3. RECOVERY. A load returns only if it FITS in the measured margin —
    //    never merely because no shortfall is showing, which is precisely what
    //    a successful shed produces.
    if (aggregate_soc > restore_threshold_) {
        int target = -1;
        for (int i = 0; i < count; ++i) {
            if (!loads[i].shed) continue;
            if (!dwell_elapsed(i, t_hours)) continue;
            if (loads[i].demand_w > headroom_w) continue;
            // min() for restore: SMALLEST priority value is the MOST important
            // load, and it comes back first.
            if (target < 0 || loads[i].priority < loads[target].priority) target = i;
        }
        if (target < 0) return Action{};
        last_change_h_[target] = t_hours;
        return Action{target, false};
    }

    return Action{};    // inside the hysteresis dead band: deliberately idle
}

}  // namespace lunar
