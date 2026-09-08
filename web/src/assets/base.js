// base.js — the concrete parts of base_asset.py.
//
// The Python ABCs are gone: JS has no abstract methods and duck typing does
// the same job. What DOES need porting is the two CONCRETE methods on those
// base classes, both of which exist because their operands are interface
// members and a per-device copy would be a chance to get one of them wrong.

export class PowerStorage {
  /** Bus-side power ceiling [W] sustainable for one whole timestep. */
  availableDischargePowerW(dtHours) {
    if (dtHours <= 0) return 0.0;
    return Math.min(this.maxDischargePowerW, this.deliverableEnergyWh / dtHours);
  }
}

export class Load {
  constructor() {
    this.shed = false;
  }

  /** What the bus actually sees: 0 W while shed. */
  effectiveDemand(tHours) {
    return this.shed ? 0.0 : this.demand(tHours);
  }
}
