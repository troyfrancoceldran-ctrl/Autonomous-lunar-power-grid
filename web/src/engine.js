// engine.js — the loop around a tick. Port of simulation_engine.py.
import { SIM_DURATION_HOURS, TIME_STEP_HOURS } from "./config.js";

export class SimulationEngine {
  constructor(bus, durationHours = SIM_DURATION_HOURS, dtHours = TIME_STEP_HOURS) {
    Object.assign(this, { bus, durationHours, dtHours });
    this.history = [];
  }

  get nSteps() { return Math.trunc(this.durationHours / this.dtHours); }

  /** t is i*dt, NEVER an accumulator. Adding dt 1440 times drifts; multiplying
   *  does not, and a clock that drifts puts the terminator in the wrong place. */
  run() {
    this.history = [];
    for (let i = 0; i < this.nSteps; i++) {
      this.history.push(this.bus.step(i * this.dtHours, this.dtHours));
    }
    return this.history;
  }

  summary() {
    if (!this.history.length) throw new Error("nothing to summarize — call run() first");
    const dt = this.dtHours;
    const sum = (key) => this.history.reduce((s, r) => s + r[key], 0.0);
    return {
      hours: this.durationHours,
      steps: this.history.length,
      generated_kwh: (sum("generation_w") * dt) / 1000.0,
      served_kwh: (sum("served_w") * dt) / 1000.0,
      unserved_kwh: (sum("shortfall_w") * dt) / 1000.0,
      curtailed_kwh: (sum("curtailed_w") * dt) / 1000.0,
      min_aggregate_soc: Math.min(...this.history.map((r) => r.aggregate_soc)),
      min_headroom_w: Math.min(...this.history.map((r) => r.headroom_w)),
      actions: this.history.filter((r) => r.action).length,
    };
  }
}
