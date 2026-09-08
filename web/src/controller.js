// controller.js — the shed/restore policy. Port of controller.py.
import { SOC_SHED_THRESHOLD, SOC_RESTORE_THRESHOLD, MIN_ACTION_DWELL_HOURS,
        LoadPriority } from "./config.js";

/** Python's max(seq, key=f) returns the FIRST maximum; min the first minimum.
 *  A reduce written with >= or <= returns the LAST, which silently changes
 *  which load is chosen whenever two share a priority. Strict comparison
 *  keeps the first, matching Python. */
function firstBy(items, key, better) {
  let best = null;
  for (const item of items) {
    if (best === null || better(key(item), key(best))) best = item;
  }
  return best;
}
const lowestPriorityFirst = (items) =>
  firstBy(items, (l) => l.priority, (a, b) => a > b);   // max()
const highestPriorityFirst = (items) =>
  firstBy(items, (l) => l.priority, (a, b) => a < b);   // min()

export class AutonomousController {
  constructor({ name = "Autonomous Controller",
                shedThreshold = SOC_SHED_THRESHOLD,
                restoreThreshold = SOC_RESTORE_THRESHOLD,
                minDwellHours = MIN_ACTION_DWELL_HOURS } = {}) {
    Object.assign(this, { name, shedThreshold, restoreThreshold, minDwellHours });
    this.lastChangeH = new Map();
  }

  /** Has this load been left alone long enough to act on again? Per-load. */
  dwellElapsed(load, tHours) {
    if (!this.lastChangeH.has(load.name)) return true;
    return tHours - this.lastChangeH.get(load.name) >= this.minDwellHours;
  }

  /** At most ONE action per tick: a staircase, not a cliff. */
  update(tHours, aggregateSoc, loads, headroomW) {
    // 1. POWER emergency. Dwell is BYPASSED: the bus is already failing, and
    //    an uncontrolled brownout drops loads in whatever order physics picks.
    if (headroomW < 0.0) {
      const candidates = loads.filter(
        (l) => !l.shed && l.priority !== LoadPriority.CRITICAL);
      if (!candidates.length) return null;
      const target = lowestPriorityFirst(candidates);
      target.shed = true;
      this.lastChangeH.set(target.name, tHours);
      return target;
    }

    // 2. ENERGY low. Supply still meets demand, so dwell is enforced.
    if (aggregateSoc < this.shedThreshold) {
      const candidates = loads.filter(
        (l) => !l.shed && l.priority !== LoadPriority.CRITICAL
              && this.dwellElapsed(l, tHours));
      if (!candidates.length) return null;
      const target = lowestPriorityFirst(candidates);
      target.shed = true;
      this.lastChangeH.set(target.name, tHours);
      return target;
    }

    // 3. RECOVERY. BOTH signals must agree: reserves above the restore
    //    threshold AND the load actually fits in the measured headroom.
    if (aggregateSoc > this.restoreThreshold) {
      const candidates = loads.filter(
        (l) => l.shed && this.dwellElapsed(l, tHours)
              && l.demand(tHours) <= headroomW);
      if (!candidates.length) return null;
      const target = highestPriorityFirst(candidates);
      target.shed = false;
      this.lastChangeH.set(target.name, tHours);
      return target;
    }

    return null;   // inside the hysteresis dead band: deliberately idle
  }
}
