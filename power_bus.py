"""
@file    power_bus.py
@brief   Per-tick energy balance: measure, decide, dispatch, report.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
The seam where every other module meets. Sources say what they COULD produce,
loads say what they WANT, storage says what it could absorb or deliver, and
the controller says what should be shed — but none of them know about each
other. This module is the only place that knows they all exist, and the only
place a watt is actually accounted for.

It depends exclusively on the interfaces in base_asset.py and controller.py.
There is no import of PVArray, BatteryBank or ECLSS anywhere below, and no
isinstance() check. Adding a second reactor or a flywheel means constructing
one and passing it in; this file does not change. That is the whole payoff of
Steps 1 through 7.

@note For the same reason there is NO factory here that builds the outpost
    from config.py. Wiring concrete assets together is main.py's job.
    A bus that knew how to build a PVArray would be a bus that could not be
    reused for a different outpost.

ORDER OF OPERATIONS — measure, decide, re-measure, dispatch, record

    1. MEASURE    aggregate_soc, the fleet's discharge ceiling, generation,
                and demand as the loads currently stand. From those,
                headroom_w = generation + ceiling - demand.
    2. DECIDE     controller.update(), which may shed or restore ONE load
    3. RE-MEASURE demand, because step 2 may have changed the shed state
    4. DISPATCH   surplus into storage, or deficit out of it, in merit order
    5. RECORD     one flat dict describing everything that happened

@warning The controller runs BEFORE dispatch. That is not an approximation to
    be tidied away later — it is what a sampled control loop actually does,
    and what the microcontroller will do. Letting the controller see this
    tick's dispatch result would be a forecast of the interval it is deciding
    about, which IEEE 2030.7 excludes from core control functions.

@note Everything the controller receives is measured at the START of this
    tick; nothing is carried over, so the bus holds no state of its own
    between ticks. An earlier design passed an unsigned shortfall remembered
    from the previous tick and the controller chattered: a successful shed
    zeroed that signal, the restore branch read the zero as permission, and
    the shed was undone one tick later. Measured beats remembered in a loop
    that decides before it acts. See DEFECT D-01 in controller.py.

MERIT ORDER
    Storage devices are used in the order they appear in the `storage` list,
    both charging and discharging. main.py passes the battery first, which is
    a deliberate policy rather than an accident of construction:

        battery round trip  0.9025      RFC round trip  0.385

    Cycling the efficient device first and keeping the lossy one for depth is
    the standard hybrid battery/hydrogen split — the battery absorbs short
    swings, hydrogen carries the long night. It costs a known thing: the
    battery spends most of the night at its floor, so the fleet's POWER
    ceiling falls to the RFC's 12 kW even while energy reserves read
    comfortable. That is exactly the blind spot headroom_w exists to expose,
    and it is a measurement to report in Step 10, not a bug to hide.

@see base_asset.py for the PowerSource / PowerStorage / Load contracts.
@see controller.py for the ControlStrategy this drives.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class PowerBus
--------------------------------------------------------------------------------
One tick of outpost operation, and the accounting that proves it balanced.

@var sources      PowerSource list; order is irrelevant, they are summed.
@var storage      PowerStorage list; order IS the merit order.
@var loads        Load list, shed or not.
@var controller   ControlStrategy; the only object permitted to shed a load.
@var environment  LunarEnvironment, passed through to every source.

@note The bus is STATELESS between ticks. All mutable state lives in the
    storage devices, the loads' shed flags and the controller's dwell memory.
    Every signal handed to the controller is measured fresh.

__init__(sources, storage, loads, controller, environment)
    Wire the outpost together.

    @note Nothing is copied. The bus holds references, so the caller can
        inspect the same device objects afterwards — which is how
        simulation_engine.py reads final states without the bus exposing them.

aggregate_soc -> float                                            [@property]
    Fleet reserve as one fraction in [0, 1].

    @return sum(deliverable_energy_wh) / sum(deliverable_capacity_wh),
            or 0.0 if the outpost has no storage at all.

    @note CAPACITY-WEIGHTED, never a mean of the devices' state_of_charge.
        The battery holds 180.5 kWh deliverable against the RFC's 2090 kWh —
        7.95 % of the reserve — so a plain average would give a nearly empty
        battery an equal vote with the tanks carrying the outpost through the
        night. Both terms are bus-side watt-hours, which is what makes them
        summable across devices that store energy in different forms.

storage_power_ceiling_w(dt_hours) -> float
    Power the whole fleet could deliver, sustained for one timestep.

    @param  dt_hours  Timestep duration [h].
    @return Sum of each device's available_discharge_power_w [W].

    @note The POWER signal's raw material, and independent of aggregate_soc.
        A fleet can read 0.872 on energy and still be unable to meet a 19.5 kW
        night load, because the only device with reserves left is rated at
        12 kW.

headroom_w(t_hours, dt_hours) -> float
    Signed power margin at the start of a tick.

    @param  t_hours   Simulation time [h].
    @param  dt_hours  Timestep duration [h].
    @return generation + storage discharge ceiling - current demand [W].

    @note SIGNED, and that is the whole point. Negative is the shortfall the
        controller sheds on; positive is the margin it must fit a load into
        before restoring one. An unsigned shortfall cannot answer the restore
        question, because a successful shed drives it to zero.
    @note Demand is measured BEFORE the controller acts — the loads as the
        previous tick left them. That is the situation being judged.

step(t_hours, dt_hours) -> dict
    Advance the outpost by one timestep.

    @param  t_hours   Simulation time [h] at the START of this tick.
    @param  dt_hours  Duration of the tick [h].
    @return A flat dict; keys listed under RECORD SCHEMA below.

    @warning NOT idempotent. Storage devices are mutated and load.shed may
        flip. Calling step() twice for the same t_hours double-charges the
        batteries. The engine must call it exactly once per tick, in
        increasing time order.

    @note Each storage device is charged or discharged AT MOST ONCE per tick,
        which is the precondition storage.py's charge()/discharge() state.

_dispatch_surplus(surplus_w, dt_hours) -> (absorbed_w, curtailed_w)  [internal]
    Push surplus into storage in merit order; whatever no device will take is
    curtailed.

    @note Curtailment is a real operation, not a modelling failure: a full
        battery and full tanks in bright sun means the array is regulated
        down. Recording it separately from generation is what lets Step 10
        show how much sunlight the outpost had to throw away.

_dispatch_deficit(deficit_w, dt_hours) -> (delivered_w, shortfall_w)  [internal]
    Draw a deficit out of storage in merit order; whatever no device can
    supply is unserved.

    @note The residue is shortfall_w — the outpost browning out. It is
        returned rather than raised, because a brownout is a result to be
        plotted, not an exception to be caught.


================================================================================
RECORD SCHEMA — the dict step() returns
================================================================================
Flat by design, so simulation_engine.py can accumulate a list of these and
hand it straight to a DataFrame with no reshaping.

    t_hours                  float   tick start time [h]
    is_daylight              bool    from the environment
    generation_w             float   total pre-dispatch source ceiling [W]
    demand_w                 float   total EFFECTIVE demand, post-shed [W]
    headroom_w               float   signed margin the controller saw [W]
    served_w                 float   demand_w - shortfall_w [W]
    net_w                    float   generation_w - demand_w; sign is the
                                    whole story of the tick
    charged_w                float   into storage, bus-side [W]
    discharged_w             float   out of storage, bus-side [W]
    curtailed_w              float   surplus nothing could absorb [W]
    shortfall_w              float   deficit nothing could supply [W]
    aggregate_soc            float   fleet reserve, sampled BEFORE dispatch
    storage_ceiling_w        float   fleet power headroom [W]
    action                   str|None  name of the load the controller
                                    touched, or None
    n_shed                   int     how many loads are currently shed
    gen:<source name>        float   per-source available power [W]
    soc:<storage name>       float   per-device state_of_charge AFTER dispatch

@note aggregate_soc is sampled before dispatch and the per-device soc: keys
    after it. That is deliberate and they will not agree within a row — the
    first is what the controller saw when it decided, the second is where the
    tick left the hardware. Conflating them would make the log unable to
    explain its own decisions.

CONSERVATION IDENTITY
    Every row satisfies, to floating-point tolerance:

        generation_w + discharged_w == served_w + charged_w + curtailed_w

    Both sides are bus-side watts. If this ever fails, a device has returned
    more than it moved and the energy accounting is fiction. Step 11 asserts
    it on every tick of the full run.
"""

from config import TIME_STEP_HOURS


class PowerBus:
    """One tick of outpost operation, and the accounting that proves it balanced."""

    def __init__(self, sources, storage, loads, controller, environment):
        """Hold references to every asset; order of `storage` is merit order."""
        self.sources = list(sources)
        self.storage = list(storage)
        self.loads = list(loads)
        self.controller = controller
        self.environment = environment

    @property
    def aggregate_soc(self) -> float:
        """Capacity-weighted fleet reserve in [0, 1]; bus-side watt-hours."""
        capacity_wh = sum(device.deliverable_capacity_wh for device in self.storage)
        if capacity_wh <= 0.0:
            return 0.0
        energy_wh = sum(device.deliverable_energy_wh for device in self.storage)
        return energy_wh / capacity_wh

    def storage_power_ceiling_w(self, dt_hours: float) -> float:
        """Power the fleet could sustain for one timestep [W]."""
        return sum(device.available_discharge_power_w(dt_hours)
                for device in self.storage)

    def headroom_w(self, t_hours: float, dt_hours: float) -> float:
        """Signed power margin [W]: generation + fleet ceiling - demand."""
        generation_w = sum(source.available_power(t_hours, self.environment)
                        for source in self.sources)
        demand_w = sum(load.effective_demand(t_hours) for load in self.loads)
        return generation_w + self.storage_power_ceiling_w(dt_hours) - demand_w

    def _dispatch_surplus(self, surplus_w: float, dt_hours: float):
        """Charge storage in merit order; returns (absorbed_w, curtailed_w)."""
        remaining_w = surplus_w
        absorbed_w = 0.0
        for device in self.storage:
            accepted_w = device.charge(remaining_w, dt_hours)
            absorbed_w += accepted_w
            remaining_w = max(0.0, remaining_w - accepted_w)
        return absorbed_w, remaining_w

    def _dispatch_deficit(self, deficit_w: float, dt_hours: float):
        """Discharge storage in merit order; returns (delivered_w, shortfall_w)."""
        remaining_w = deficit_w
        delivered_w = 0.0
        for device in self.storage:
            supplied_w = device.discharge(remaining_w, dt_hours)
            delivered_w += supplied_w
            remaining_w = max(0.0, remaining_w - supplied_w)
        return delivered_w, remaining_w

    def step(self, t_hours: float, dt_hours: float = TIME_STEP_HOURS) -> dict:
        """Advance one tick: measure, decide, re-measure, dispatch, record."""
        # 1. MEASURE — the tick as it stands, before any decision.
        soc = self.aggregate_soc
        ceiling_w = self.storage_power_ceiling_w(dt_hours)
        generation_w = sum(source.available_power(t_hours, self.environment)
                        for source in self.sources)
        connected_w = sum(load.effective_demand(t_hours) for load in self.loads)
        headroom_w = generation_w + ceiling_w - connected_w

        # 2. DECIDE — on signals measured a moment ago, never remembered.
        action = self.controller.update(t_hours, soc, self.loads, headroom_w)

        # 3. RE-MEASURE — the controller may have shed or restored a load.
        demand_w = sum(load.effective_demand(t_hours) for load in self.loads)
        net_w = generation_w - demand_w

        # 4. DISPATCH — at most one charge or discharge call per device.
        charged_w = discharged_w = curtailed_w = shortfall_w = 0.0
        if net_w > 0.0:
            charged_w, curtailed_w = self._dispatch_surplus(net_w, dt_hours)
        elif net_w < 0.0:
            discharged_w, shortfall_w = self._dispatch_deficit(-net_w, dt_hours)

        # 5. RECORD
        record = {
            "t_hours": t_hours,
            "is_daylight": self.environment.is_daylight(t_hours),
            "generation_w": generation_w,
            "demand_w": demand_w,
            "headroom_w": headroom_w,
            "served_w": demand_w - shortfall_w,
            "net_w": net_w,
            "charged_w": charged_w,
            "discharged_w": discharged_w,
            "curtailed_w": curtailed_w,
            "shortfall_w": shortfall_w,
            "aggregate_soc": soc,
            "storage_ceiling_w": ceiling_w,
            "action": None if action is None else action.name,
            "n_shed": sum(1 for load in self.loads if load.shed),
        }
        for source in self.sources:
            record[f"gen:{source.name}"] = source.available_power(
                t_hours, self.environment)
        for device in self.storage:
            record[f"soc:{device.name}"] = device.state_of_charge
        return record
