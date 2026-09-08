// environment.js — the lunar day/night cycle. Port of environment.py.
import { LUNAR_CYCLE_HOURS, LUNAR_DAY_HOURS } from "./config.js";

/** Python's % returns a non-negative remainder for a positive divisor; JS's
 *  keeps the sign of the dividend. t is never negative here, but relying on
 *  that is exactly the kind of assumption that survives until it doesn't. */
export function mod(a, b) {
  return ((a % b) + b) % b;
}

export class LunarEnvironment {
  constructor(startPhaseHours = 0.0) {
    this.startPhaseHours = startPhaseHours;
  }

  /** Position within the current synodic cycle, in [0, 708.7). */
  phaseHours(tHours) {
    return mod(tHours + this.startPhaseHours, LUNAR_CYCLE_HOURS);
  }

  /** True while the outpost is in sunlight. Strict < at the terminator. */
  isDaylight(tHours) {
    return this.phaseHours(tHours) < LUNAR_DAY_HOURS;
  }

  /** Peak-flux fraction in [0, 1]; square wave — availability only. */
  solarIrradianceFraction(tHours) {
    return this.isDaylight(tHours) ? 1.0 : 0.0;
  }

  /** Sine of solar elevation in [0, 1]; 0.0 at night. */
  solarElevationFraction(tHours) {
    if (!this.isDaylight(tHours)) return 0.0;
    const phase = this.phaseHours(tHours);
    return Math.max(0.0, Math.sin((Math.PI * phase) / LUNAR_DAY_HOURS));
  }
}
