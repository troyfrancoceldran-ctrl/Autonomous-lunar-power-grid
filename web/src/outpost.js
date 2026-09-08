// outpost.js — the parts list. Port of main.build_outpost.
//
// The ONLY module that names a concrete class, exactly as in Python. Everything
// else sees interfaces, which is what lets the same engine run a different
// outpost without being edited.
import { PowerBus } from "./powerBus.js";
import { AutonomousController } from "./controller.js";
import { PVArray, FissionSurfacePower } from "./assets/generation.js";
import { BatteryBank, RegenerativeFuelCell } from "./assets/storage.js";
import { ECLSS, ThermalControl, CommsArray, SciencePayload } from "./assets/loads.js";
import { buildTopology } from "./topology.js";
import { buildConverters } from "./converters.js";
import { FSP_OUTAGE_DURATION_HOURS } from "./config.js";

/** Assemble the standard outpost; storage ORDER is the merit order. */
export function buildOutpost(environment, outageStartHours = null,
                            topology = false, converters = false) {
  const bus = new PowerBus({
    sources: [
      new PVArray(),
      new FissionSurfacePower({
        outageStartHours,
        outageDurationHours: FSP_OUTAGE_DURATION_HOURS,
      }),
    ],
    storage: [
      new BatteryBank(),            // efficient and fast — cycled first
      new RegenerativeFuelCell(),   // lossy and deep — held for the night
    ],
    loads: [
      new ECLSS(),
      new ThermalControl(environment),
      new CommsArray(),
      new SciencePayload(),
    ],
    controller: new AutonomousController(),
    environment,
    buses: topology ? buildTopology(true) : null,
  });
  if (converters) {
    // Built FROM the assembled bus, never a restated list — defect D-03.
    bus.converters = buildConverters(bus);
  }
  return bus;
}
