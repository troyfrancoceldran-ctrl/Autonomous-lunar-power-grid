"""
@file    main.py
@brief   Entry point: builds the outpost, runs a scenario, reports.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
The ONLY module that names concrete classes. PVArray, BatteryBank and ECLSS
appear here and nowhere else outside their own files — power_bus.py and
simulation_engine.py see nothing but the interfaces, which is what lets the
same engine run a different outpost without being edited.

That makes this file the outpost's parts list, and build_outpost() the place
to change the hardware.

    python main.py                     nominal 60-day run
    python main.py --outage 500        24 h reactor outage from hour 500
    python main.py --report            full KPI report instead of the summary
    python main.py --figures           render the four figures to data/figures/
    python main.py --export            write data/history_*.{csv,json}
    python main.py --outage 500 --report --figures --export      all of it

@note MERIT ORDER IS SET HERE, by the order of the storage list. Battery
    first, RFC second: cycle the efficient device (round trip 0.9025) and
    keep the lossy one (0.385) for depth. power_bus.py deliberately has no
    opinion about this — it uses the list as given, so changing the policy is
    a one-line edit here rather than a change to the engine.

@see power_bus.py for what happens inside a tick.
@see simulation_engine.py for the loop around it.


================================================================================
API
================================================================================

build_outpost(environment, outage_start_hours=None) -> PowerBus
    Assemble the standard outpost from config.py defaults.

    @param  environment          LunarEnvironment the assets will query.
    @param  outage_start_hours   Scripted FSP outage start [h], or None.
    @return A wired PowerBus, ready to step.

    @note ThermalControl is the one load that takes the environment: its
        setpoint differs between lunar day and night. Everything else derives
        its behaviour from t alone.

run_scenario(name, outage_start_hours=None, export=False) -> SimulationEngine
    Build, run and report one scenario.

    @param  name                Label for the console report.
    @param  outage_start_hours  Passed through to build_outpost().
    @param  export              Write data/history_<name>.{csv,json} as well.
    @param  report              Print the full metrics.py KPI report.
    @param  figures             Render the four figures into data/figures/.
    @return The engine, so a caller can reach .history for further analysis.

    @note visualization is imported INSIDE the branch, not at module level.
        It pulls in matplotlib, which costs seconds on a cold font cache, and
        a run that only wants numbers should not pay for a plotting library.

    @note Builds a FRESH outpost every time. Storage devices and shed flags
        are stateful, so reusing a bus across scenarios would carry the first
        run's ending state into the second one's start.
"""

import argparse

from config import FSP_OUTAGE_DURATION_HOURS
from controller import AutonomousController
from environment import LunarEnvironment
from power_bus import PowerBus
from simulation_engine import SimulationEngine
from topology import build_topology
from assets.generation import PVArray, FissionSurfacePower
from assets.loads import ECLSS, ThermalControl, CommsArray, SciencePayload
from assets.storage import BatteryBank, RegenerativeFuelCell


def build_outpost(environment, outage_start_hours=None,
                  topology: bool = False) -> PowerBus:
    """Assemble the standard outpost; storage order IS the merit order."""
    return PowerBus(
        sources=[
            PVArray(),
            FissionSurfacePower(outage_start_hours=outage_start_hours,
                                outage_duration_hours=FSP_OUTAGE_DURATION_HOURS),
        ],
        storage=[
            BatteryBank(),              # efficient and fast — cycled first
            RegenerativeFuelCell(),     # lossy and deep — held for the night
        ],
        loads=[
            ECLSS(),
            ThermalControl(environment),
            CommsArray(),
            SciencePayload(),
        ],
        controller=AutonomousController(),
        environment=environment,
        buses=build_topology(sized=True) if topology else None,
    )


def run_scenario(name: str, outage_start_hours=None, export: bool = False,
                report: bool = False, figures: bool = False,
                topology: bool = False):
    """Build a fresh outpost, run it, print a summary; returns the engine."""
    environment = LunarEnvironment()
    engine = SimulationEngine(
        build_outpost(environment, outage_start_hours, topology))
    engine.run()

    s = engine.summary()
    print(f"\n{name}")
    print(f"  {'duration':<20}{s['hours']:>12.0f} h over {s['steps']} steps")
    print(f"  {'generated':<20}{s['generated_kwh']:>12.1f} kWh")
    print(f"  {'served':<20}{s['served_kwh']:>12.1f} kWh")
    print(f"  {'unserved':<20}{s['unserved_kwh']:>12.1f} kWh")
    print(f"  {'curtailed':<20}{s['curtailed_kwh']:>12.1f} kWh")
    print(f"  {'min aggregate SoC':<20}{s['min_aggregate_soc']:>12.4f}")
    print(f"  {'min headroom':<20}{s['min_headroom_w'] / 1000:>12.2f} kW")
    print(f"  {'controller actions':<20}{s['actions']:>12}")
    if topology:
        loss_kwh = sum(r["losses_w"] for r in engine.history) / 1000.0
        print(f"  {'conductor loss':<20}{loss_kwh:>12.1f} kWh"
              f"  ({100 * loss_kwh / s['generated_kwh']:.2f} % of generation)")

    slug = "".join(ch if ch.isalnum() else "_" for ch in name.lower()).strip("_")

    if export:
        engine.to_csv(f"data/history_{slug}.csv")
        engine.to_json(f"data/history_{slug}.json")
        print(f"  {'exported':<20}  data/history_{slug}.csv and .json")

    if report:
        import metrics
        print()
        print(metrics.report(engine.history))

    if figures:
        import visualization           # imports matplotlib; deferred on purpose
        paths = visualization.make_all(engine.history, f"data/figures/{slug}")
        print(f"  {'figures':<20}  " + ", ".join(paths))

    return engine


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lunar outpost microgrid simulation")
    parser.add_argument("--outage", type=float, default=None, metavar="HOURS",
                        help="start a scripted FSP outage at this hour")
    parser.add_argument("--export", action="store_true",
                        help="write the run history to data/ as CSV and JSON")
    parser.add_argument("--report", action="store_true",
                        help="print the full KPI report from metrics.py")
    parser.add_argument("--topology", action="store_true",
                        help="model feeder resistance and conductor losses")
    parser.add_argument("--figures", action="store_true",
                        help="render the four figures into data/figures/")
    args = parser.parse_args()

    label = ("nominal" if args.outage is None
            else f"FSP outage at t={args.outage:.0f} h")
    run_scenario(label, outage_start_hours=args.outage, export=args.export,
                report=args.report, figures=args.figures,
                 topology=args.topology)
