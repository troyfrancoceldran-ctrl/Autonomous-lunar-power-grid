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

update(t_hours, aggregate_soc, loads, shortfall_w) -> Load | None
    Decide shed/restore for this tick.

    @param  t_hours        Simulation time [h] since t=0.
    @param  aggregate_soc  Fleet reserve as a single fraction in [0, 1].
    @param  loads          Every Load on the bus, shed or not.
    @param  shortfall_w    Power the bus could NOT serve this tick [W], >= 0.
    @return The Load acted on, or None if nothing changed.

    @note Two scalars, not one, because energy and power fail differently.
        aggregate_soc is the ENERGY signal — bus-side deliverable energy over
        bus-side deliverable capacity, so a device counts for what it can
        actually contribute. shortfall_w is the POWER signal — what the fleet
        could not deliver right now, whatever its reserves.

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
    @note shortfall_w has NO default. Adding one would let a stale three-
        argument call site keep compiling while silently reporting "no
        brownout, ever" — the safety signal quietly disabled. Better a loud
        TypeError at the first call.

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

update(t_hours, aggregate_soc, loads, shortfall_w) -> Load | None
    Shed or restore at most one load.

    @param  t_hours        Simulation time [h] since t=0.
    @param  aggregate_soc  Fleet reserve in [0, 1].
    @param  loads          Every Load on the bus.
    @param  shortfall_w    Power the bus could not serve this tick [W].
    @return The Load acted on, or None.

    THREE branches, tried in this order:

        1. POWER EMERGENCY   shortfall_w > 0
        2. ENERGY LOW        aggregate_soc < shed_threshold
        3. RECOVERY          aggregate_soc > restore_threshold
                            AND shortfall_w <= 0

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

    @warning Branch 3's second condition is NOT optional. Without it the
        controller sheds on the power signal, restores on the energy signal,
        and oscillates every tick — and the trap is subtle, because reserves
        can read healthy precisely BECAUSE the shed loads are not drawing
        from them. Restoring is what brings the shortfall back.

    @note CRITICAL is excluded in branch 1 as in branch 2. ECLSS never sheds,
        even in a brownout: losing life support to save the bus is not a trade
        this controller may make. If the deficit outlives every sheddable
        load, the correct behaviour is to report unserved power and let the
        record show it.

    @note shortfall_w is never computed here. power_bus.py measures it as
        max(0, demand - what generation and storage could actually deliver)
        and passes it in, exactly as it does aggregate_soc. A strategy
        reacts to the bus; it does not model it.

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
SPEC — W04, controller half.  Author: user.  Reviewer: JARVIS.
================================================================================
AutonomousController.update() takes the new power signal and gains a branch
above the existing two. The ControlStrategy interface above is already
changed; this brings the implementation into line with it.

RENAME
    The `soc` parameter becomes `aggregate_soc` throughout. It is no longer
    "the battery's state of charge" — it is a capacity-weighted fleet
    aggregate, and the old name invites a reader to assume otherwise.

NEW PRECEDENCE — three branches, in this order

    1.  POWER EMERGENCY   shortfall_w > 0
            Shed the least important non-CRITICAL running load, IGNORING the
            dwell timer.
    2.  ENERGY LOW        aggregate_soc < shed_threshold
            Exactly the existing shed branch, dwell still enforced.
    3.  RECOVERY          aggregate_soc > restore_threshold
                        AND shortfall_w <= 0
            The existing restore branch, with the new second condition.
    otherwise             return None

    PSEUDOCODE
        if shortfall_w > 0:
            candidates = running, non-CRITICAL          # no dwell filter
            if not candidates: return None
            target = max(candidates, key=priority); target.shed = True
            record the change time; return target

        if aggregate_soc < self.shed_threshold:
            ... unchanged ...

        if aggregate_soc > self.restore_threshold and shortfall_w <= 0:
            ... unchanged ...

        return None

    @warning Branch 3's `and shortfall_w <= 0` is NOT optional. Without it the
        controller can restore a load while the bus is still failing to serve
        the loads it already has — reserves may look full precisely because
        the shed loads are not drawing from them. It would shed on the power
        signal, restore on the energy signal, and oscillate every tick. The
        two signals must agree before anything comes back.

    @note Branch 1 bypasses dwell DELIBERATELY, and it is the one place in
        this file that does. The dwell timer exists to stop chatter around a
        threshold. An unserved-power event is not chatter — it is the outpost
        already failing to meet demand, and an uncontrolled brownout drops
        loads in whatever order physics chooses. Shedding deliberately, in
        priority order, one per tick, is strictly better than waiting an hour
        to be tidy. This is what under-frequency load shedding does on a
        terrestrial grid, and for the same reason.
    @note Still ONE action per call, in all three branches. If the shortfall
        persists the next tick sheds the next load — the staircase again.
    @note CRITICAL is excluded in branch 1 as in branch 2. ECLSS never sheds,
        even in a brownout: the outpost losing life support to save the bus is
        not a trade this controller is permitted to make. If the deficit
        outlives every sheddable load, the correct behaviour is to report
        unserved power and let the record show it.

VERIFICATION
    Construct four loads and drive update() directly.

    a. shortfall_w = 0.0, aggregate_soc = 0.50   -> None (dead band, no
                                                emergency)
    b. shortfall_w = 7500.0, aggregate_soc = 0.90 -> sheds Science Payload,
                                                despite a healthy reserve.
                                                THIS is the case the whole
                                                work order exists for.
    c. immediately after (b), same tick time, shortfall still positive
                                                -> sheds Comms Array, proving
                                                dwell was bypassed
    d. shortfall_w = 0.0, aggregate_soc = 0.90, dwell elapsed
                                                -> restores Comms Array
    e. shortfall_w = 500.0, aggregate_soc = 0.90 -> must NOT restore; must
                                                shed instead
    f. aggregate_soc = 0.29, shortfall_w = 0.0   -> unchanged staircase
                                                behaviour from Step 7
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
            shortfall_w: float):
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
            shortfall_w: float):
        """Shed or restore at most one load this tick; returns it, or None."""
        # POWER emergency. The bus is already failing to serve what is
        # connected, so act now — dwell is deliberately not consulted.
        if shortfall_w > 0:
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

        # RECOVERY. Both signals must agree before anything comes back: the
        # reserve may look healthy precisely because the shed loads are not
        # drawing from it.
        if aggregate_soc > self.restore_threshold and shortfall_w <= 0:
            candidates = [load for load in loads
                        if load.shed
                        and self._dwell_elapsed(load, t_hours)]
            if not candidates:
                return None
            # Smallest priority VALUE = most important load, so restore it first.
            target = min(candidates, key=lambda load: load.priority)
            target.shed = False
            self._last_change_h[target.name] = t_hours
            return target

        return None     # inside the hysteresis dead band: deliberately idle
