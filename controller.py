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

update(t_hours, soc, loads) -> Load | None
    Decide shed/restore for this tick.

    @param  t_hours  Simulation time [h] since t=0.
    @param  soc      Overall storage reserve, a single fraction in [0, 1].
    @param  loads    Every Load on the bus, shed or not.
    @return The Load acted on, or None if nothing changed.

    @note The single soc float is deliberate. A strategy should not know
        whether the outpost has one battery, two, or a fuel cell — defining
        that aggregate is power_bus.py's job. That ignorance is what lets an
        RL policy drop in later, and what lets this run on a microcontroller
        reading one ADC channel.

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

update(t_hours, soc, loads) -> Load | None
    Shed or restore at most one load.

    @param  t_hours  Simulation time [h] since t=0.
    @param  soc      Overall storage reserve in [0, 1].
    @param  loads    Every Load on the bus.
    @return The Load acted on, or None.

    Below shed_threshold, picks the least important running load that is not
    CRITICAL and whose dwell has elapsed. Above restore_threshold, picks the
    most important shed load whose dwell has elapsed. Between the two, does
    nothing at all.

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
    def update(self, t_hours: float, soc: float, loads: list):
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

    def update(self, t_hours: float, soc: float, loads: list):
        """Shed or restore at most one load this tick; returns it, or None."""
        if soc < self.shed_threshold:
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

        if soc > self.restore_threshold:
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
