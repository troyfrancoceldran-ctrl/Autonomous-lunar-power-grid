"""
@file    loads.py
@brief   Concrete Load implementations: ECLSS, ThermalControl, CommsArray,
         SciencePayload.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-04

@details
Everything on the outpost that consumes power, in four priority tiers:

    ECLSS            CRITICAL   6.5 kW flat, around the clock. Never shed.
    ThermalControl   HIGH       5.5 kW by day, 4.5 kW by night.
    CommsArray       MEDIUM     2.5 kW for 8 h of every 24, 0.5 kW between.
    SciencePayload   LOW        6.0 kW for 12 h of every 24, 0 W between.

Mean draw over the 56-day run is 15.67 kW, against 46.7 kW of daylight
generation and a 10 kW reactor at night. The resulting night deficit
consumes roughly three quarters of the outpost's stored energy, which is
what gives Step 7's controller something real to do.

After the stateful storage devices, these are a return to PURE FUNCTIONS:
demand() reads self and returns, writes nothing, and may be called at any t
in any order.

@note Subclasses implement demand() ONLY. Shed bookkeeping lives in
    Load.effective_demand() so all four behave identically — never override
    it. power_bus.py must always call effective_demand(), never demand().

@note `shed` is inherited as a class attribute defaulting to False. Writing
    load.shed = True creates an INSTANCE attribute that shadows it for that
    object alone, so no per-instance initialisation is needed. This is safe
    only because the default is immutable; a mutable class attribute would
    be shared across every instance.

@see base_asset.py for the Load contract.
@see config.py for LoadPriority and every power figure below.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class ECLSS(Load)
--------------------------------------------------------------------------------
Life support: atmosphere circulation, CO2 scrubbing, water recovery.

@var name      Identifier used in logs and plot legends.
@var power_w   Constant draw [W].
@var priority  LoadPriority.CRITICAL.

__init__(name="Environmental Control and Life Support System",
         power_w=ECLSS_POWER_W, priority=LoadPriority.CRITICAL)
    Construct the life-support load.

demand(t_hours) -> float
    Constant draw, indifferent to time.

    @param  t_hours  Simulation time [h]. DELIBERATELY UNUSED.
    @return power_w.

    @note CRITICAL declares that the controller must never shed this load.
        The class only states its tier; enforcing it is Step 7's job.

--------------------------------------------------------------------------------
class ThermalControl(Load)
--------------------------------------------------------------------------------
Habitat thermal control. The lunar surface swings from about +120 C in
daylight to -170 C at night, so this load never disappears — it only changes
job, from rejecting heat to adding it.

@var name            Identifier used in logs and plot legends.
@var environment     LunarEnvironment this load queries for day/night state.
@var day_power_w     Draw while the sun is up [W].
@var night_power_w   Draw during the lunar night [W].
@var priority        LoadPriority.HIGH.

__init__(environment, name="Thermal Control", day_power_w, night_power_w,
         priority=LoadPriority.HIGH)
    Construct the thermal load against a given environment.

    @param environment  Required, and deliberately FIRST with no default —
                        a ThermalControl without one is meaningless, so the
                        constructor refuses to build a half-configured object.

    @note This is dependency injection, and it is why LunarEnvironment was
        built stateless and queryable at arbitrary t. The load does not
        recompute the lunar cycle; it asks the object that owns that
        knowledge. Replace the environment with a real thermistor and this
        class is unchanged.

demand(t_hours) -> float
    Day or night power, according to the injected environment.

    @param  t_hours  Simulation time [h] since t=0.
    @return day_power_w in sunlight, night_power_w otherwise.

--------------------------------------------------------------------------------
class CommsArray(Load)
--------------------------------------------------------------------------------
High-gain Earth link: one transmit window per Earth day, standby between.

@var name              Identifier used in logs and plot legends.
@var active_power_w    Draw while transmitting [W].
@var standby_power_w   Draw between windows [W].
@var window_hours      Length of the transmit window [h].
@var period_hours      Repeat period [h].
@var priority          LoadPriority.MEDIUM.

__init__(name="Communications Array", active_power_w, standby_power_w,
         window_hours, period_hours, priority=LoadPriority.MEDIUM)
    Construct the comms load from its duty cycle.

demand(t_hours) -> float
    Active inside the window, standby outside it.

    @param  t_hours  Simulation time [h] since t=0.
    @return active_power_w or standby_power_w.

    @note Same technique as LunarEnvironment.is_daylight — modulo folds
        absolute time into one period, and the STRICT < places the boundary
        hour in the LATER state. Phase 8.0 is the first standby hour, not
        the last active one.

--------------------------------------------------------------------------------
class SciencePayload(Load)
--------------------------------------------------------------------------------
Science campaigns: drills, rovers, instruments. Fully interruptible.

@var name             Identifier used in logs and plot legends.
@var active_power_w   Draw during a campaign [W].
@var idle_power_w     Draw between campaigns [W], zero by default.
@var window_hours     Length of a campaign [h].
@var period_hours     Repeat period [h].
@var priority         LoadPriority.LOW.

__init__(name="Science Payload", active_power_w, idle_power_w, window_hours,
         period_hours, priority=LoadPriority.LOW)
    Construct the science load from its duty cycle.

demand(t_hours) -> float
    Active inside the campaign window, idle outside it.

    @param  t_hours  Simulation time [h] since t=0.
    @return active_power_w or idle_power_w.

    @note LOW means the controller sheds this first. Drills and rovers can
        wait; nobody dies. At 6 kW it is also the largest single saving
        available, which is what makes it worth shedding.
"""

from assets.base_asset import Load
from config import (LoadPriority,
                    ECLSS_POWER_W,
                    THERMAL_DAY_POWER_W,
                    THERMAL_NIGHT_POWER_W,
                    COMMS_ACTIVE_POWER_W,
                    COMMS_STANDBY_POWER_W,
                    COMMS_WINDOW_HOURS,
                    COMMS_PERIOD_HOURS,
                    SCIENCE_ACTIVE_POWER_W,
                    SCIENCE_IDLE_POWER_W,
                    SCIENCE_WINDOW_HOURS,
                    SCIENCE_PERIOD_HOURS)


class ECLSS(Load):
    """Life support; constant draw, never shed."""

    def __init__(self, name="Environmental Control and Life Support System"
                , power_w=ECLSS_POWER_W
                , priority=LoadPriority.CRITICAL):
        """Store the load's nameplate specification."""
        self.name = name
        self.power_w = power_w
        self.priority = priority

    def demand(self, t_hours: float) -> float:
        """Constant draw; t_hours deliberately unused."""
        return self.power_w


class ThermalControl(Load):
    """Habitat thermal control; follows the injected environment."""

    def __init__(self, environment, name="Thermal Control"
                , day_power_w=THERMAL_DAY_POWER_W
                , night_power_w=THERMAL_NIGHT_POWER_W
                , priority=LoadPriority.HIGH):
        """Store the nameplate spec and the environment to query."""
        self.name = name
        self.day_power_w = day_power_w
        self.night_power_w = night_power_w
        self.priority = priority
        self.environment = environment

    def demand(self, t_hours: float) -> float:
        """Heat rejection by day, survival heating by night."""
        if self.environment.is_daylight(t_hours):
            return self.day_power_w
        return self.night_power_w


class CommsArray(Load):
    """Earth link; one transmit window per period, standby between."""

    def __init__(self, name="Communications Array"
                , active_power_w=COMMS_ACTIVE_POWER_W
                , standby_power_w=COMMS_STANDBY_POWER_W
                , window_hours=COMMS_WINDOW_HOURS
                , period_hours=COMMS_PERIOD_HOURS
                , priority=LoadPriority.MEDIUM):
        """Store the load's nameplate specification and duty cycle."""
        self.name = name
        self.active_power_w = active_power_w
        self.standby_power_w = standby_power_w
        self.window_hours = window_hours
        self.period_hours = period_hours
        self.priority = priority

    def demand(self, t_hours: float) -> float:
        """Active inside the window; strict < puts the boundary in standby."""
        phase_hours = t_hours % self.period_hours
        if phase_hours < self.window_hours:
            return self.active_power_w
        return self.standby_power_w


class SciencePayload(Load):
    """Science campaigns; fully interruptible, shed first."""

    def __init__(self, name="Science Payload"
                , active_power_w=SCIENCE_ACTIVE_POWER_W
                , idle_power_w=SCIENCE_IDLE_POWER_W
                , window_hours=SCIENCE_WINDOW_HOURS
                , period_hours=SCIENCE_PERIOD_HOURS
                , priority=LoadPriority.LOW):
        """Store the load's nameplate specification and duty cycle."""
        self.name = name
        self.active_power_w = active_power_w
        self.idle_power_w = idle_power_w
        self.window_hours = window_hours
        self.period_hours = period_hours
        self.priority = priority

    def demand(self, t_hours: float) -> float:
        """Active inside the campaign window, idle outside it."""
        phase_hours = t_hours % self.period_hours
        if phase_hours < self.window_hours:
            return self.active_power_w
        return self.idle_power_w
