"""
@file    controller.py
@brief   Priority-based load shedding and restoration with hysteresis.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
The first code in this project that makes a DECISION rather than reporting a
fact. Every other module describes a thing — how much power it makes, how
much energy it holds, how much it draws. This one encodes policy: what the
outpost should do when its reserves run low.

Built as a Strategy. power_bus.py holds a ControlStrategy, never a concrete
class, so a later RL-based policy can be swapped in without the engine
changing a line. It is also the piece intended to run on real hardware
eventually, so it stays plain arithmetic, comparisons and loops — no numpy,
no pandas, nothing that will not port to an MCU.

TWO INDEPENDENT GUARDS against chatter:

Hysteresis   Shed below 0.30, restore above 0.45, and DO NOTHING between.
            Were both thresholds 0.30, the outpost would shed at 0.2999,
            recover to 0.3001, restore, drop again, and oscillate every
            hour for the rest of the night. Contactors have finite
            switching lifetimes; a chattering controller destroys them.
            The dead band is not an oversight — it is the mechanism.
            The same idea appears as Schmitt-trigger input thresholds and
            as the deadband in a thermostat.

Dwell time   A given load may not change state more than once per
            MIN_ACTION_DWELL_HOURS, independently of SoC. Hysteresis
            stops oscillation around a threshold; dwell stops rapid
            successive action on one device.

@note One action per call, never a bulk shed. If the deficit persists, SoC
    keeps falling and the next tick sheds the next load — a staircase rather
    than a cliff, and the outpost sheds only as much as it actually needs.

@warning A strategy may mutate `load.shed` and NOTHING else. It must never
    touch generation or storage: dispatch is the bus's job, policy is the
    controller's. Blurring that boundary is what makes an engine
    unswappable.

@see base_asset.py for the Load contract this operates on.
@see config.py for LoadPriority and the two thresholds.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class ControlStrategy(ABC)
--------------------------------------------------------------------------------
A dispatch policy. The interface power_bus.py depends on.

@var name  Human-readable identifier, used in logs.

update(t_hours, aggregate_soc, loads, headroom_w) -> Load | None
    Decide shed/restore for this tick.

    @param  t_hours        Simulation time [h] since t=0.
    @param  aggregate_soc  Fleet reserve as a single fraction in [0, 1].
    @param  loads          Every Load on the bus, shed or not.
    @param  headroom_w     Signed power margin this tick [W]: generation plus
                        the fleet's discharge ceiling, less current demand.
                        Negative means the bus is already failing to serve
                        what is connected.
    @return The Load acted on, or None if nothing changed.

    @note Two scalars, not one, because energy and power fail differently.
        aggregate_soc is the ENERGY signal — bus-side deliverable energy over
        bus-side deliverable capacity, so a device counts for what it can
        actually contribute. headroom_w is the POWER signal — how many watts
        of margin the bus has right now, whatever its reserves.

        Neither subsumes the other. Measured on this outpost: battery at its
        floor with the tanks at 95 % gives aggregate_soc = 0.872, which reads
        as comfortable, while the fleet can supply only the RFC's 12 kW — so
        an FSP outage against a 19.5 kW night load leaves 7.5 kW unserved. A
        controller watching energy alone sleeps through that. One watching
        power alone cannot see the tanks draining, and sheds only once the
        outpost is already failing.

        This is defence in depth, chosen deliberately over a single elegant
        signal, because the two failure modes are different events.

    @note They are still SCALARS. A strategy must not know whether the outpost
        has one battery, two, or a fuel cell — computing both aggregates is
        power_bus.py's job. That ignorance is what lets an RL policy drop in
        later, and what lets this run on a microcontroller reading two ADC
        channels instead of one.
    @note headroom_w has NO default. Adding one would let a stale three-
        argument call site keep compiling while silently reporting "infinite
        margin" — the safety signal quietly disabled. Better a loud
        TypeError at the first call.
    @note It is SIGNED, and measured at the START of the tick being decided.
        An earlier design passed an unsigned shortfall carried from the
        previous tick; because the controller decides before dispatch, a
        successful shed zeroed that signal and the restore branch undid the
        shed on the very next tick. See DEFECT D-01 below.

--------------------------------------------------------------------------------
class AutonomousController(ControlStrategy)
--------------------------------------------------------------------------------
Priority-ordered shed/restore with hysteresis and a per-load dwell timer.

@var name               Identifier used in logs.
@var shed_threshold     Shed below this SoC, 0.30 [-].
@var restore_threshold  Restore above this SoC, 0.45 [-].
@var min_dwell_hours    Minimum interval between actions on one load [h].
@var _last_change_h     THE STATE — {load name: time it last changed} [h].

__init__(name="Autonomous Controller", shed_threshold, restore_threshold,
        min_dwell_hours)
    Construct a controller from its policy thresholds.

    @note _last_change_h is a new kind of state: not an accumulating
        quantity like the battery's energy_wh, but a memory of WHEN
        something happened.

_dwell_elapsed(load, t_hours) -> bool                              [internal]
    Whether this load is free to change state again.

    @param  load     The Load being considered.
    @param  t_hours  Current simulation time [h].
    @return True if the load has never been acted on, or if min_dwell_hours
            has passed since it last changed.

    @note dict.get() returns None for a missing key rather than raising,
        which is exactly the question being asked: have I touched this load
        before?

update(t_hours, aggregate_soc, loads, headroom_w) -> Load | None
    Shed or restore at most one load.

    @param  t_hours        Simulation time [h] since t=0.
    @param  aggregate_soc  Fleet reserve in [0, 1].
    @param  loads          Every Load on the bus.
    @param  headroom_w     Signed power margin this tick [W]; negative means
                        the bus is already failing to serve what is on it.
    @return The Load acted on, or None.

    THREE branches, tried in this order:

        1. POWER EMERGENCY   headroom_w < 0
        2. ENERGY LOW        aggregate_soc < shed_threshold
        3. RECOVERY          aggregate_soc > restore_threshold
                            AND the load FITS: demand(t) <= headroom_w

    Power comes first because it is the acute failure: the outpost is already
    not serving its loads. Energy is the slow one — reserves draining while
    supply still meets demand. Between the thresholds, with no shortfall,
    the controller does nothing at all.

    @warning Branch 1 bypasses the dwell timer, and it is the only place in
        this file that does. Dwell exists to stop chatter around a threshold;
        an unserved-power event is not chatter, and an uncontrolled brownout
        drops loads in whatever order physics chooses. Shedding deliberately
        in priority order beats waiting an hour to be tidy. Terrestrial grids
        make the same trade in under-frequency load shedding.

    @warning Branch 3's fit test is NOT optional, and merely checking that no
        shortfall is showing is NOT sufficient — that was defect D-01 below. A
        shed removes the shortfall by working, so "no shortfall" one tick
        after a shed says nothing about whether the load can come back.
        Asking whether the load FITS in the present margin is a question with
        a real answer.

    @note CRITICAL is excluded in branch 1 as in branch 2. ECLSS never sheds,
        even in a brownout: losing life support to save the bus is not a trade
        this controller may make. If the deficit outlives every sheddable
        load, the correct behaviour is to report unserved power and let the
        record show it.

    @note KNOWN LIMIT of the fit test: it asks what the load draws NOW, so a
        duty-cycled load can be restored during its idle window — costing 0 W
        and fitting trivially — and then bite when it switches on. Comms and
        Science are both 24 h cycles, so this is reachable. It is accepted
        deliberately. Testing the load's PEAK instead would be safer but
        would need the Load interface to publish a nameplate maximum, and
        testing what it will draw next hour would be a forecast, which IEEE
        2030.7 keeps out of core control functions. The cost of the accepted
        version is bounded: the power branch sheds it again on the next tick,
        so the exposure is one timestep. Measured over the 60-day run this
        costs nothing at all, and 1.5 kWh across a 24 h reactor outage.

    @note headroom_w is never computed here. power_bus.py measures it as
        generation + the fleet discharge ceiling - current demand, at the
        start of the tick, and passes it in exactly as it does aggregate_soc.
        A strategy reacts to the bus; it does not model it.

    @note LoadPriority is an IntEnum where LOWER number = MORE important
        (CRITICAL 0, HIGH 1, MEDIUM 2, LOW 3). The selection therefore
        inverts: shedding takes max() of the priority value, restoring takes
        min(). That inversion is the easiest thing here to get backwards.

    @note The CRITICAL exclusion appears only in the shed branch. It is
        unnecessary in restore — a load that can never be shed can never be
        a restore candidate.

    @note Verified staircase, thresholds 0.30/0.45: nothing at 0.35, shed
        Science at 0.29, Comms at 0.25, Thermal at 0.20, nothing further.
        On recovery, nothing at 0.40 (dead band), then Thermal, Comms,
        Science in that order. ECLSS never sheds.


================================================================================
DEFECT D-01 and its fix — signed headroom replaces the shortfall scalar
================================================================================
W04 first gave update() a `shortfall_w` argument: watts the bus failed to
serve, measured at the END of the previous tick because the controller runs
BEFORE dispatch. Step 8 drove the outpost through a 24 h reactor outage and
the controller chattered — shedding Comms, restoring it, shedding it again,
twelve actions in twenty-four hours.

TWO CAUSES

D-01a  The restore guard read a STALE signal.

            tick N    shortfall 1500 -> shed Comms -> shortfall becomes 0
            tick N+1  shortfall 0, soc 0.60 > 0.45 -> RESTORE Comms
            tick N+2  shortfall 1500 again

        The guard `and shortfall_w <= 0` was meant to prevent exactly this
        and could not: a successful shed ZEROES the very signal the guard
        tests. The cure was being read as the absence of the disease. No
        amount of hysteresis on the ENERGY signal helps, because the energy
        signal was reading a comfortable 0.60 throughout.

D-01b  MIN_ACTION_DWELL_HOURS equalled TIME_STEP_HOURS, so the guard
        `t - last >= min_dwell` was 1.0 >= 1.0 — true on the very next tick.
        The dwell timer had been a no-op since Step 7; nothing noticed until
        a branch bypassed hysteresis and left dwell as the only brake.

THE FIX
    `shortfall_w` becomes a SIGNED `headroom_w`, measured at the start of the
    current tick rather than carried from the last:

        headroom_w = generation_w + storage_ceiling_w - demand_w

    Negative headroom IS the shortfall, and it is now current. Positive
    headroom is the margin, which is what makes the restore question
    answerable: bring a load back only if it FITS.

        restore requires  load.demand(t_hours) <= headroom_w

    A controller can no longer restore something the bus demonstrably cannot
    carry, so the shed/restore cycle has no way to start.

    @note Still not a forecast. Every term is measured at the start of the
        interval being decided — generation from the sources, ceiling from
        the devices, demand from the loads as they currently stand. IEEE
        2030.7 excludes forecasting from core control functions, not
        arithmetic on present measurements.
    @note One number now carries both signals, and power_bus.py holds no
        state between ticks. Measured rather than remembered is the stronger
        property: a remembered scalar is stale by construction in a loop that
        decides before it acts.

WHY NOT JUST LENGTHEN THE DWELL
    Measured over the same outage, sweeping min_dwell_hours:

        dwell h   actions in outage   unserved kWh
            1                  12           19.0
            2                  12           26.0
            3                  10           20.5
            6                   6           14.0
            12                   4            9.0
            24                   2            9.0

    Chatter falls but never stops, unserved energy does not fall
    monotonically, and at 2 h it is WORSE than at 1 h because the restore
    lands at a less forgiving moment. Lengthening the dwell hides a
    mechanism it cannot remove. D-01b is still fixed in config.py, but on its
    own merits, not as a remedy for D-01a.
"""

from abc import ABC, abstractmethod

from config import (SOC_SHED_THRESHOLD,
                    SOC_RESTORE_THRESHOLD,
                    MIN_ACTION_DWELL_HOURS,
                    LoadPriority)


class ControlStrategy(ABC):
    """A dispatch policy. power_bus.py holds one of these, never a concrete one."""

    name: str

    @abstractmethod
    def update(self, t_hours: float, aggregate_soc: float, loads: list,
            headroom_w: float):
        """Decide shed/restore for this tick; returns the Load acted on, or None."""
        raise NotImplementedError


class AutonomousController(ControlStrategy):
    """Priority-ordered shed/restore with hysteresis and per-load dwell."""

    def __init__(self, name="Autonomous Controller"
                , shed_threshold=SOC_SHED_THRESHOLD
                , restore_threshold=SOC_RESTORE_THRESHOLD
                , min_dwell_hours=MIN_ACTION_DWELL_HOURS):
        """Store the policy thresholds; start with no action history."""
        self.name = name
        self.shed_threshold = shed_threshold
        self.restore_threshold = restore_threshold
        self.min_dwell_hours = min_dwell_hours

        self._last_change_h = {}

    def _dwell_elapsed(self, load, t_hours: float) -> bool:
        """True if this load is free to change state again."""
        last_h = self._last_change_h.get(load.name)
        if last_h is None:
            return True
        return t_hours - last_h >= self.min_dwell_hours

    def update(self, t_hours: float, aggregate_soc: float, loads: list,
            headroom_w: float):
        """Shed or restore at most one load this tick; returns it, or None."""
        # POWER emergency. The bus is already failing to serve what is
        # connected, so act now — dwell is deliberately not consulted.
        if headroom_w < 0.0:
            candidates = [load for load in loads
                        if not load.shed
                        and load.priority is not LoadPriority.CRITICAL]
            if not candidates:
                return None
            target = max(candidates, key=lambda load: load.priority)
            target.shed = True
            self._last_change_h[target.name] = t_hours
            return target

        # ENERGY low. Reserves are draining but supply still meets demand.
        if aggregate_soc < self.shed_threshold:
            candidates = [load for load in loads
                        if not load.shed
                        and load.priority is not LoadPriority.CRITICAL
                        and self._dwell_elapsed(load, t_hours)]
            if not candidates:
                return None
            # Largest priority VALUE = least important load, so shed it first.
            target = max(candidates, key=lambda load: load.priority)
            target.shed = True
            self._last_change_h[target.name] = t_hours
            return target

        # RECOVERY. A load comes back only if it FITS in the measured margin —
        # never merely because no shortfall is showing, which is what a
        # successful shed produces.
        if aggregate_soc > self.restore_threshold:
            candidates = [load for load in loads
                        if load.shed
                        and self._dwell_elapsed(load, t_hours)
                        and load.demand(t_hours) <= headroom_w]
            if not candidates:
                return None
            # Smallest priority VALUE = most important load, so restore it first.
            target = min(candidates, key=lambda load: load.priority)
            target.shed = False
            self._last_change_h[target.name] = t_hours
            return target

        return None     # inside the hysteresis dead band: deliberately idle
