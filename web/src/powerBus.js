// powerBus.js — one tick, and the accounting that proves it balanced.
// Port of power_bus.py.
//
// The identity this must preserve, every tick:
//   generation + discharged == served + charged + curtailed + losses
import { TIME_STEP_HOURS } from "./config.js";
import { cableTemperatureK } from "./topology.js";

export class PowerBus {
  constructor({ sources, storage, loads, controller, environment,
                buses = null, converters = null }) {
    Object.assign(this, { sources, storage, loads, controller, environment });
    this.buses = buses ?? [];
    this.feedersByName = new Map();
    for (const bus of this.buses) {
      for (const f of bus.feeders) this.feedersByName.set(f.name, f);
    }
    this.converters = converters ?? new Map();
  }

  /** Loss in the feeder serving `name`; 0.0 with no topology wired. */
  feederLossW(name, powerW, temperatureK) {
    const feeder = this.feedersByName.get(name);
    if (!feeder || powerW <= 0.0) return 0.0;
    return feeder.lossW(powerW, feeder.nominalVoltageV, temperatureK);
  }

  /** Asset supplies; what reaches the bus. Converter first, feeder second. */
  supplyToBus(name, assetPowerW, temperatureK) {
    const converter = this.converters.get(name);
    const afterConverterW = converter ? converter.deliveredW(assetPowerW) : assetPowerW;
    const converterLossW = assetPowerW - afterConverterW;
    const feederLossW = this.feederLossW(name, afterConverterW, temperatureK);
    return [afterConverterW - feederLossW, converterLossW, feederLossW];
  }

  /** Asset needs; what the bus must send. Multiply out, DIVIDE in. */
  drawFromBus(name, assetPowerW, temperatureK) {
    const converter = this.converters.get(name);
    const beforeConverterW = converter ? converter.drawnW(assetPowerW) : assetPowerW;
    const converterLossW = beforeConverterW - assetPowerW;
    const feederLossW = this.feederLossW(name, beforeConverterW, temperatureK);
    return [beforeConverterW + feederLossW, converterLossW, feederLossW];
  }

  /** Capacity-weighted, never a mean of the devices' state_of_charge. */
  get aggregateSoc() {
    const capacityWh = this.storage.reduce((s, d) => s + d.deliverableCapacityWh, 0.0);
    if (capacityWh <= 0.0) return 0.0;
    const energyWh = this.storage.reduce((s, d) => s + d.deliverableEnergyWh, 0.0);
    return energyWh / capacityWh;
  }

  storagePowerCeilingW(dtHours) {
    return this.storage.reduce((s, d) => s + d.availableDischargePowerW(dtHours), 0.0);
  }

  dispatchSurplus(surplusW, dtHours, temperatureK) {
    let remainingW = surplusW;
    let absorbedW = 0.0, converterLossW = 0.0, feederLossW = 0.0;
    const flows = {};
    for (const device of this.storage) {
      // Offer only what SURVIVES the trip. Offering the raw remainder lets a
      // device accept power the bus cannot deliver — defect D-04, which the
      // clamp then hid as a 1.6 kW conservation residual.
      const converter = this.converters.get(device.name);
      const eta = converter ? converter.efficiency : 1.0;
      const roughW = remainingW * eta;
      const [, , trialFeederW] = this.drawFromBus(device.name, roughW, temperatureK);
      const offerW = Math.max(0.0, (remainingW - trialFeederW) * eta);

      const acceptedW = device.charge(offerW, dtHours);
      const [costW, convLoss, feedLoss] =
        this.drawFromBus(device.name, acceptedW, temperatureK);

      flows[device.name] = acceptedW;
      absorbedW += acceptedW;
      converterLossW += convLoss;
      feederLossW += feedLoss;
      remainingW -= costW;
    }
    return [absorbedW, remainingW, flows, converterLossW, feederLossW];
  }

  dispatchDeficit(deficitW, dtHours, temperatureK) {
    let remainingW = deficitW;
    let deliveredW = 0.0, converterLossW = 0.0, feederLossW = 0.0;
    const flows = {};
    for (const device of this.storage) {
      const suppliedW = device.discharge(remainingW, dtHours);
      const [arrivedW, convLoss, feedLoss] =
        this.supplyToBus(device.name, suppliedW, temperatureK);
      flows[device.name] = -suppliedW;        // signed: out of the device
      deliveredW += suppliedW;
      converterLossW += convLoss;
      feederLossW += feedLoss;
      remainingW = Math.max(0.0, remainingW - arrivedW);
    }
    return [deliveredW, remainingW, flows, converterLossW, feederLossW];
  }

  /** Advance one tick: measure, decide, re-measure, dispatch, record. */
  step(tHours, dtHours = TIME_STEP_HOURS) {
    const isDaylight = this.environment.isDaylight(tHours);
    const cableK = cableTemperatureK(isDaylight);

    // 1. MEASURE — at the BUS, which is where the controller lives.
    const soc = this.aggregateSoc;
    const ceilingW = this.storagePowerCeilingW(dtHours);

    const genBySource = new Map();
    for (const source of this.sources) {
      genBySource.set(source.name, source.availablePower(tHours, this.environment));
    }
    let generationW = 0.0;
    for (const v of genBySource.values()) generationW += v;

    let generationBusW = 0.0, genConvLossW = 0.0, genFeedLossW = 0.0;
    for (const [name, powerW] of genBySource) {
      const [busW, convW, feedW] = this.supplyToBus(name, powerW, cableK);
      generationBusW += busW;
      genConvLossW += convW;
      genFeedLossW += feedW;
    }

    const demandAtBus = () => {
      let total = 0.0, conv = 0.0, feed = 0.0;
      for (const load of this.loads) {
        const [busW, c, f] =
          this.drawFromBus(load.name, load.effectiveDemand(tHours), cableK);
        total += busW; conv += c; feed += f;
      }
      return [total, conv, feed];
    };

    const [connectedBusW] = demandAtBus();
    const headroomW = generationBusW + ceilingW - connectedBusW;

    // 2. DECIDE — on signals measured a moment ago, never remembered.
    const action = this.controller.update(tHours, soc, this.loads, headroomW);

    // 3. RE-MEASURE — the controller may have shed or restored a load.
    let demandW = 0.0;
    for (const load of this.loads) demandW += load.effectiveDemand(tHours);
    const [demandBusW, loadConvLossW, loadFeedLossW] = demandAtBus();
    const netW = generationBusW - demandBusW;

    // 4. DISPATCH — at most one charge or discharge call per device.
    let chargedW = 0.0, dischargedW = 0.0, curtailedW = 0.0, shortfallW = 0.0;
    let storeConvLossW = 0.0, storeFeedLossW = 0.0;
    let flows = {};
    for (const d of this.storage) flows[d.name] = 0.0;

    if (netW > 0.0) {
      [chargedW, curtailedW, flows, storeConvLossW, storeFeedLossW] =
        this.dispatchSurplus(netW, dtHours, cableK);
    } else if (netW < 0.0) {
      [dischargedW, shortfallW, flows, storeConvLossW, storeFeedLossW] =
        this.dispatchDeficit(-netW, dtHours, cableK);
    }

    const converterLossW = genConvLossW + loadConvLossW + storeConvLossW;
    const feederLossW = genFeedLossW + loadFeedLossW + storeFeedLossW;
    const lossesW = converterLossW + feederLossW;

    // 5. RECORD
    const record = {
      t_hours: tHours,
      is_daylight: isDaylight,
      generation_w: generationW,
      demand_w: demandW,
      headroom_w: headroomW,
      served_w: demandW - shortfallW,
      net_w: netW,
      charged_w: chargedW,
      discharged_w: dischargedW,
      curtailed_w: curtailedW,
      shortfall_w: shortfallW,
      aggregate_soc: soc,
      storage_ceiling_w: ceilingW,
      action: action === null ? null : action.name,
      n_shed: this.loads.filter((l) => l.shed).length,
      cable_temperature_k: cableK,
      generation_bus_w: generationBusW,
      demand_bus_w: demandBusW,
      gen_loss_w: genFeedLossW,
      load_loss_w: loadFeedLossW,
      storage_loss_w: storeFeedLossW,
      feeder_loss_w: feederLossW,
      converter_loss_w: converterLossW,
      losses_w: lossesW,
    };
    for (const source of this.sources) {
      record[`gen:${source.name}`] = genBySource.get(source.name);
      record[`floss:${source.name}`] =
        this.feederLossW(source.name, genBySource.get(source.name), cableK);
    }
    for (const device of this.storage) {
      record[`soc:${device.name}`] = device.stateOfCharge;
      record[`flow:${device.name}`] = flows[device.name];
      record[`floss:${device.name}`] =
        this.feederLossW(device.name, Math.abs(flows[device.name]), cableK);
    }
    for (const load of this.loads) {
      record[`load:${load.name}`] = load.effectiveDemand(tHours);
      record[`shed:${load.name}`] = load.shed;
      record[`floss:${load.name}`] =
        this.feederLossW(load.name, load.effectiveDemand(tHours), cableK);
    }
    return record;
  }
}
