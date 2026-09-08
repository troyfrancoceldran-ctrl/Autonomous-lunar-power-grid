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

@note CONSERVATION, extended by T02. The identity was

        generation + discharged == served + charged + curtailed

    and is now

        generation + discharged == served + charged + curtailed + losses

    Losses do not excuse the books from balancing; a watt burned in a
    conductor is simply another destination. Measured worst residual over
    1440 ticks: 0.000e+00 W with no topology, 7.276e-12 W with it.

    Generation is measured at the SOURCE TERMINALS and demand at the LOAD
    TERMINALS, while the controller sees bus-side figures — generation minus
    its feeder cut, demand plus its own. Handing the controller terminal
    numbers would let it promise power that never arrives.

@note TWO DEFECTS T02 shipped, both invisible until a full run was measured:

    D-03  The reactor's feeder was named 'Fission Surface Power' while
        build_outpost calls the asset 'FSP Reactor'. Binding by name fails
        SILENTLY — the asset simply has no feeder and reports 0.0 W, so a
        1 km transmission run contributed nothing while every total still
        looked plausible. The layout test did not catch it because it
        compared build_topology's literals against literals of my own
        writing. test_every_asset_is_bound_to_a_feeder now compares against
        the assembled outpost.

    D-04  _dispatch_surplus offered a device the whole remaining surplus
        when the bus could only deliver that minus the feeder cut, so the
        device accepted power that did not exist. The accounting clamped at
        zero to hide it and the conservation residual reached 1.625e+03 W.
        The device is now offered only what survives the feeder.

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

_dispatch_surplus(surplus_w, dt_hours) -> (absorbed_w, curtailed_w, flows)
                                                                    [internal]
    Push surplus into storage in merit order; whatever no device will take is
    curtailed. `flows` maps device name -> power absorbed [W].

    @note Curtailment is a real operation, not a modelling failure: a full
        battery and full tanks in bright sun means the array is regulated
        down. Recording it separately from generation is what lets Step 10
        show how much sunlight the outpost had to throw away.

_dispatch_deficit(deficit_w, dt_hours) -> (delivered_w, shortfall_w, flows)
                                                                    [internal]
    Draw a deficit out of storage in merit order; whatever no device can
    supply is unserved. `flows` maps device name -> power delivered [W].

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
    flow:<storage name>      float   SIGNED per-device power [W]: positive
                                    charging, negative discharging, 0 idle
    load:<load name>         float   per-load EFFECTIVE demand [W], 0 if shed
    shed:<load name>         bool    whether that load is currently shed

@note The per-load and per-device columns exist so the history is
    self-describing: every question metrics.py or a visualization can ask is
    answerable from the file alone, with no need to re-run the simulation or
    reach back into the live objects. That is what makes to_json() a complete
    feed rather than a summary.
@note flow: is SIGNED on one axis rather than split into two columns, because
    a device is never charging and discharging in the same tick — the sign is
    free information, and one column plots directly as a single trace through
    zero.

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
from topology import cable_temperature_k


class PowerBus:
    """One tick of outpost operation, and the accounting that proves it balanced."""

    def __init__(self, sources, storage, loads, controller, environment,
                 buses=None, converters=None):
        """Hold references to every asset; order of `storage` is merit order.

        @param buses  Optional iterable of topology.DCBus. Omit it and every
            feeder loss is zero, which is the model as it stood before T02 —
            so the pre-topology results remain reproducible rather than being
            overwritten by a change of physics.
        """
        self.sources = list(sources)
        self.storage = list(storage)
        self.loads = list(loads)
        self.controller = controller
        self.environment = environment
        self.buses = list(buses) if buses else []
        self._feeders = {f.name: f for bus in self.buses for f in bus.feeders}
        self.converters = dict(converters) if converters else {}

    def _supply_to_bus(self, name: str, asset_power_w: float,
                       temperature_k: float):
        """Asset supplies asset_power_w; what reaches the bus, and the losses.

        @return (bus_power_w, converter_loss_w, feeder_loss_w)
        @note Converter first, feeder second. The converter sits at the asset
            end and presents bus voltage, so the feeder carries CONVERTED
            power — sizing the feeder for the raw asset output would size it
            for a voltage that exists nowhere.
        """
        converter = self.converters.get(name)
        after_converter_w = (converter.delivered_w(asset_power_w)
                            if converter else asset_power_w)
        converter_loss_w = asset_power_w - after_converter_w
        feeder_loss_w = self._feeder_loss_w(name, after_converter_w,
                                            temperature_k)
        return after_converter_w - feeder_loss_w, converter_loss_w, feeder_loss_w

    def _draw_from_bus(self, name: str, asset_power_w: float,
                       temperature_k: float):
        """Asset needs asset_power_w; what the bus must send, and the losses.

        @return (bus_power_w, converter_loss_w, feeder_loss_w)
        @note Multiply on the way out, DIVIDE on the way in. The same
            asymmetry as the battery round trip, and getting it backwards
            turns a converter into a source of power.
        """
        converter = self.converters.get(name)
        before_converter_w = (converter.drawn_w(asset_power_w)
                            if converter else asset_power_w)
        converter_loss_w = before_converter_w - asset_power_w
        feeder_loss_w = self._feeder_loss_w(name, before_converter_w,
                                            temperature_k)
        return before_converter_w + feeder_loss_w, converter_loss_w, feeder_loss_w

    def _feeder_loss_w(self, name: str, power_w: float,
                    temperature_k: float) -> float:
        """Loss in the feeder serving `name`; 0.0 with no topology wired.

        An asset with no feeder is treated as sitting on the bus itself,
        which is the honest reading of a topology that does not mention it.
        """
        feeder = self._feeders.get(name)
        if feeder is None or power_w <= 0.0:
            return 0.0
        return feeder.loss_w(power_w, feeder.nominal_voltage_v, temperature_k)

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

    def _dispatch_surplus(self, surplus_w: float, dt_hours: float,
                          temperature_k: float):
        """Charge in merit order.

        @return (absorbed_w, curtailed_w, flows, converter_loss_w, feeder_loss_w)

        `absorbed_w` is ASSET-side: what the devices actually stored. The bus
        spent that plus both losses, which is why the device may only be
        offered what survives the trip.
        """
        remaining_w = surplus_w
        absorbed_w = 0.0
        converter_loss_w = feeder_loss_w = 0.0
        flows = {}
        for device in self.storage:
            # What could reach this device if the bus spent everything left?
            # One correction pass: estimate on the converter alone, then knock
            # off the feeder loss that estimate implies. Offering the raw
            # remainder would let the device accept power that does not exist
            # — defect D-04.
            converter = self.converters.get(device.name)
            eta = converter.efficiency if converter else 1.0
            rough_w = remaining_w * eta
            trial_cost_w, _, trial_feeder_w = self._draw_from_bus(
                device.name, rough_w, temperature_k)
            offer_w = max(0.0, (remaining_w - trial_feeder_w) * eta)

            accepted_w = device.charge(offer_w, dt_hours)
            cost_w, conv_loss, feed_loss = self._draw_from_bus(
                device.name, accepted_w, temperature_k)

            flows[device.name] = accepted_w
            absorbed_w += accepted_w
            converter_loss_w += conv_loss
            feeder_loss_w += feed_loss
            remaining_w = remaining_w - cost_w
        return (absorbed_w, remaining_w, flows,
                converter_loss_w, feeder_loss_w)

    def _dispatch_deficit(self, deficit_w: float, dt_hours: float,
                          temperature_k: float):
        """Discharge in merit order.

        @return (delivered_w, shortfall_w, flows, converter_loss_w, feeder_loss_w)

        `delivered_w` is ASSET-side: what the devices gave up. Less than that
        reaches the bus, so the deficit falls by the arriving figure and the
        difference survives as shortfall. No iteration needed — losses simply
        make a discharge less effective.
        """
        remaining_w = deficit_w
        delivered_w = 0.0
        converter_loss_w = feeder_loss_w = 0.0
        flows = {}
        for device in self.storage:
            supplied_w = device.discharge(remaining_w, dt_hours)
            arrived_w, conv_loss, feed_loss = self._supply_to_bus(
                device.name, supplied_w, temperature_k)

            flows[device.name] = -supplied_w        # signed: out of the device
            delivered_w += supplied_w
            converter_loss_w += conv_loss
            feeder_loss_w += feed_loss
            remaining_w = max(0.0, remaining_w - arrived_w)
        return (delivered_w, remaining_w, flows,
                converter_loss_w, feeder_loss_w)

    def step(self, t_hours: float, dt_hours: float = TIME_STEP_HOURS) -> dict:
        """Advance one tick: measure, decide, re-measure, dispatch, record."""
        is_daylight = self.environment.is_daylight(t_hours)
        cable_k = cable_temperature_k(is_daylight)

        # 1. MEASURE — at the BUS. A source's nameplate is measured at ITS
        #    terminals; what the bus can spend is that minus the converter and
        #    the feeder. Handing the controller terminal figures would let it
        #    promise power that never arrives.
        soc = self.aggregate_soc
        ceiling_w = self.storage_power_ceiling_w(dt_hours)

        gen_by_source = {source.name: source.available_power(t_hours,
                                                            self.environment)
                        for source in self.sources}
        generation_w = sum(gen_by_source.values())
        generation_bus_w = gen_conv_loss_w = gen_feed_loss_w = 0.0
        for name, power_w in gen_by_source.items():
            bus_w, conv_w, feed_w = self._supply_to_bus(name, power_w, cable_k)
            generation_bus_w += bus_w
            gen_conv_loss_w += conv_w
            gen_feed_loss_w += feed_w

        def demand_at_bus():
            """(bus_w, converter_loss, feeder_loss) for the loads as they stand."""
            total = conv = feed = 0.0
            for load in self.loads:
                bus_w, c, f = self._draw_from_bus(
                    load.name, load.effective_demand(t_hours), cable_k)
                total += bus_w
                conv += c
                feed += f
            return total, conv, feed

        connected_bus_w, _, _ = demand_at_bus()
        headroom_w = generation_bus_w + ceiling_w - connected_bus_w

        # 2. DECIDE — on signals measured a moment ago, never remembered.
        action = self.controller.update(t_hours, soc, self.loads, headroom_w)

        # 3. RE-MEASURE — the controller may have shed or restored a load. A
        #    load costs the bus its demand PLUS both losses, so shedding one
        #    saves slightly more than its nameplate.
        demand_w = sum(load.effective_demand(t_hours) for load in self.loads)
        demand_bus_w, load_conv_loss_w, load_feed_loss_w = demand_at_bus()
        net_w = generation_bus_w - demand_bus_w

        # 4. DISPATCH — at most one charge or discharge call per device.
        charged_w = discharged_w = curtailed_w = shortfall_w = 0.0
        store_conv_loss_w = store_feed_loss_w = 0.0
        flows = {device.name: 0.0 for device in self.storage}
        if net_w > 0.0:
            (charged_w, curtailed_w, flows,
            store_conv_loss_w, store_feed_loss_w) = self._dispatch_surplus(
                net_w, dt_hours, cable_k)
        elif net_w < 0.0:
            (discharged_w, shortfall_w, flows,
            store_conv_loss_w, store_feed_loss_w) = self._dispatch_deficit(
                -net_w, dt_hours, cable_k)
            # NOTE: shortfall is measured at the BUS, not at the load
            # terminals. Converting it to a load-side figure means dividing by
            # a converter and a feeder that the missing power never passed
            # through, and the arithmetic is only approximate — a first
            # attempt scaled it by demand_w / demand_bus_w and broke the
            # conservation identity by 60.9 W. An exact bus-side number that
            # slightly overstates what the loads lost is worth more than an
            # approximate load-side one that stops the books balancing.

        converter_loss_w = (gen_conv_loss_w + load_conv_loss_w
                            + store_conv_loss_w)
        feeder_loss_w = (gen_feed_loss_w + load_feed_loss_w
                        + store_feed_loss_w)
        losses_w = converter_loss_w + feeder_loss_w

        # 5. RECORD
        record = {
            "t_hours": t_hours,
            "is_daylight": is_daylight,
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
            # --- electrical layer. All zero when nothing is wired, which
            #     keeps every earlier result reproducible rather than revised.
            "cable_temperature_k": cable_k,
            "generation_bus_w": generation_bus_w,
            "demand_bus_w": demand_bus_w,
            "gen_loss_w": gen_feed_loss_w,
            "load_loss_w": load_feed_loss_w,
            "storage_loss_w": store_feed_loss_w,
            "feeder_loss_w": feeder_loss_w,
            "converter_loss_w": converter_loss_w,
            "losses_w": losses_w,
        }
        for source in self.sources:
            record[f"gen:{source.name}"] = gen_by_source[source.name]
            record[f"floss:{source.name}"] = self._feeder_loss_w(
                source.name, gen_by_source[source.name], cable_k)
        for device in self.storage:
            record[f"soc:{device.name}"] = device.state_of_charge
            record[f"flow:{device.name}"] = flows[device.name]
            record[f"floss:{device.name}"] = self._feeder_loss_w(
                device.name, abs(flows[device.name]), cable_k)
        for load in self.loads:
            record[f"load:{load.name}"] = load.effective_demand(t_hours)
            record[f"shed:{load.name}"] = load.shed
            record[f"floss:{load.name}"] = self._feeder_loss_w(
                load.name, load.effective_demand(t_hours), cable_k)
        return record
