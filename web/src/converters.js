// converters.js — power electronics. Port of converters.py.
//
// Multiply on the way out, DIVIDE on the way in. The same asymmetry as the
// battery round trip; reversed, a converter becomes a source of power.
import { CONVERTER_EFFICIENCY } from "./config.js";

export class Converter {
  constructor(name, efficiency = CONVERTER_EFFICIENCY, ratedW = 0.0) {
    if (!(efficiency > 0.0 && efficiency <= 1.0)) {
      throw new Error(`${name}: efficiency ${efficiency} outside (0, 1]`);
    }
    Object.assign(this, { name, efficiency, ratedW });
    Object.freeze(this);
  }
  /** Asset supplies this much; the bus receives less. */
  deliveredW(assetPowerW) { return assetPowerW * this.efficiency; }
  /** Asset needs this much; the bus must send more. */
  drawnW(assetPowerW) { return assetPowerW / this.efficiency; }
  lossSupplyingW(assetPowerW) { return assetPowerW - this.deliveredW(assetPowerW); }
  lossDrawingW(assetPowerW) { return this.drawnW(assetPowerW) - assetPowerW; }
}

/** One converter per asset, derived FROM the bus rather than a restated list,
 *  so an asset added to the outpost cannot end up without power electronics. */
export function buildConverters(bus, efficiency = CONVERTER_EFFICIENCY) {
  const converters = new Map();
  for (const a of [...bus.sources, ...bus.storage, ...bus.loads]) {
    converters.set(a.name, new Converter(a.name, efficiency));
  }
  return converters;
}
