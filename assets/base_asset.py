"""
@file    base_asset.py
@brief   Abstract interfaces for every microgrid asset.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-03

@details
Design intent: power_bus.py and controller.py depend ONLY on the interfaces
defined here (PowerSource, PowerStorage, Load) — never on a concrete class
like PVArray or BatteryBank directly. That's what lets us add a new
generation or storage type later (or swap the controller's strategy) without
touching the simulation engine.

This is the same idea as a hardware abstraction layer in embedded firmware:
the interface declares what a device promises, the concrete class supplies
how it delivers. Replacing the simulated environment with real sensors later
touches the implementations, never the engine.

Concrete implementations live in:
    assets/generation.py   -> PVArray, FissionSurfacePower
    assets/storage.py      -> BatteryBank, RegenerativeFuelCell
    assets/loads.py        -> ECLSS, ThermalControl, CommsArray, SciencePayload

@note Every power quantity in this project is in WATTS and every energy
    quantity in WATT-HOURS. Convert only at the visualization layer.


================================================================================
API
================================================================================

--------------------------------------------------------------------------------
class PowerSource(ABC)
--------------------------------------------------------------------------------
Anything that can inject power onto the bus: the PV array, the FSP reactor, or
an RFC operating in fuel-cell/discharge mode.

@var name  Human-readable identifier, used in logs and plot legends.

available_power(t_hours, environment) -> float
    Power this source COULD deliver at time t, before any dispatch decision.

    @param  t_hours      Simulation time [h] since t=0.
    @param  environment  LunarEnvironment supplying irradiance / day-night
                        state. Sources that do not depend on it (FSP) must
                        still accept it — the uniform signature is what lets
                        power_bus.py iterate over mixed source types with no
                        isinstance() checks.
    @return Available power [W], >= 0.

    @note This is the pre-dispatch ceiling, not the power actually taken.
        Implementations must be pure: compute and return, never cache on self,
        since the engine may query arbitrary t in any order.

--------------------------------------------------------------------------------
class PowerStorage(ABC)
--------------------------------------------------------------------------------
Anything that can absorb or release energy over time: batteries, or an RFC's
electrolyzer (charge) + fuel cell (discharge) pair. Unlike PowerSource,
implementations are STATEFUL — charge() and discharge() mutate stored energy,
so call order within a timestep matters.

@var name  Human-readable identifier, used in logs and plot legends.

state_of_charge -> float                                          [@property]
    Fractional fill level.

    @return Fill fraction in [0, 1].

    @note For the RFC this must be an energy-equivalent fill fraction derived
        from remaining H2/O2 mass, not a separate concept — the controller has
        to treat storage devices interchangeably.
    @note Declared as a @property, so callers write `dev.state_of_charge` with
        no parentheses. An implementation that omits the decorator returns a
        bound method: an ordering comparison against a float then raises
        TypeError, but a bare truthiness test passes silently and forever.

charge(power_w, dt_hours) -> float
    Attempt to absorb power for one timestep.

    @param  power_w   Power offered [W], >= 0.
    @param  dt_hours  Duration of the timestep [h].
    @return Power ACTUALLY absorbed [W], in [0, power_w].

    @warning The return value is the contract. A full or power-limited device
        cannot take everything offered, and power_bus.py relies on the
        difference to know how much surplus remains. Returning power_w
        unconditionally silently fabricates storage capacity.

discharge(power_w, dt_hours) -> float
    Attempt to deliver power for one timestep.

    @param  power_w   Power requested [W], >= 0.
    @param  dt_hours  Duration of the timestep [h].
    @return Power ACTUALLY delivered [W], in [0, power_w].

    @warning As with charge(), the shortfall between requested and delivered
        is what tells the engine a brownout occurred.

deliverable_energy_wh -> float                                    [@property]
    Energy this device can still put ON THE BUS [Wh].

    @return Bus-side energy remaining, >= 0. Zero at the SoC floor.

    @note BUS-SIDE, not device-side: the reserve floor is already subtracted
        and the discharge loss is already applied. state_of_charge answers
        "how full is the tank"; this answers "how many watt-hours will the
        outpost actually receive", which is the only question a power balance
        can use. For the RFC the two differ by a factor of 0.55.

deliverable_capacity_wh -> float                                  [@property]
    The same quantity with the device brim-full [Wh].

    @return Bus-side energy between the SoC floor and ceiling, > 0.

    @note This is a CONSTANT for a given device — it is the denominator of
        the fleet's aggregate state of charge, not a live reading. It exists
        so power_bus.py can compute

            aggregate_soc = sum(deliverable_energy_wh)
                        / sum(deliverable_capacity_wh)

        which weights each device by the energy it can actually contribute.
    @warning Do NOT let the engine average the devices' state_of_charge
        values instead. Measured on this outpost, the battery holds 180.5 kWh
        deliverable against the RFC's 2090 kWh — 7.9 % of the reserve. A mean
        of SoCs gives a nearly-empty battery the same vote as the tanks
        carrying the outpost through the night, so a full battery beside empty
        tanks reads as half charged. Capacity weighting is what the
        equivalent-SoC literature does, and it is why this property exists.

available_discharge_power_w(dt_hours) -> float                    [CONCRETE]
    Bus-side power ceiling this device can sustain for one whole timestep.

    @param  dt_hours  Duration of the timestep [h]; <= 0 returns 0.0.
    @return min(max_discharge_power_w, deliverable_energy_wh / dt_hours) [W].

    @note NOT abstract. Both operands are already interface members, so the
        expression is identical for every storage device that will ever
        exist — implemented once here rather than in each subclass, each free
        to get it wrong. Same reasoning as Load.effective_demand() below.
        Subclasses need only supply max_discharge_power_w (a nameplate value
        they all store anyway) and deliverable_energy_wh.
    @note A METHOD, not a property, because the answer depends on the step
        length: 100 Wh of reserve is 100 W over an hour and 1000 W over six
        minutes. A ceiling that ignored dt would report full nameplate power
        for a device with minutes of energy left — precisely the case this
        signal exists to catch.
    @note Both operands must be BUS-SIDE for the min() to be meaningful:
        max_discharge_power_w is the converter rating the bus sees, and
        deliverable_energy_wh is already post-efficiency. Mixing a
        device-side rating with bus-side energy here is the easy mistake.
    @note Summed across the fleet this gives the outpost's POWER headroom,
        which is a different failure mode from running out of energy and must
        be reported separately. Measured case: battery at its floor with the
        tanks at 95 % gives aggregate_soc = 0.872, which reads as healthy —
        but the fleet can then deliver only the RFC's 12 kW, so an FSP outage
        against a 19.5 kW night load leaves 7.5 kW unserved. Energy says fine;
        power says brownout. Both are correct, which is why the controller
        gets both.

--------------------------------------------------------------------------------
class Load(ABC)
--------------------------------------------------------------------------------
Anything that consumes power: ECLSS, thermal control, comms, science payloads.
Concrete subclasses only implement demand(); shed bookkeeping is handled in the
base so the controller has one consistent API across all load types.

@var name      Human-readable identifier, used in logs and plot legends.
@var priority  LoadPriority tier. Lower number = shed last, restored first.
@var shed      True when the controller has disconnected this load.

demand(t_hours) -> float
    Power this load WANTS to draw, ignoring shed state.

    @param  t_hours  Simulation time [h] since t=0.
    @return Demanded power [W], >= 0.

effective_demand(t_hours) -> float
    Power this load actually draws right now.

    @param  t_hours  Simulation time [h] since t=0.
    @return 0.0 if shed, otherwise demand(t_hours) [W].

    @note power_bus.py must always call this, never demand() directly, when
        computing the real load on the bus. Implemented once here rather than
        in four subclasses, each free to get it wrong.
"""

from abc import ABC, abstractmethod

from config import LoadPriority


class PowerSource(ABC):
    """Anything that can inject power onto the bus."""

    name: str

    @abstractmethod
    def available_power(self, t_hours: float, environment) -> float:
        """Pre-dispatch power ceiling [W] at time t."""
        raise NotImplementedError


class PowerStorage(ABC):
    """Anything that can absorb or release energy over time. Stateful."""

    name: str

    @property
    @abstractmethod
    def state_of_charge(self) -> float:
        """Fractional fill level in [0, 1]."""
        raise NotImplementedError

    @abstractmethod
    def charge(self, power_w: float, dt_hours: float) -> float:
        """Absorb power for one timestep; returns power ACTUALLY absorbed [W]."""
        raise NotImplementedError

    @abstractmethod
    def discharge(self, power_w: float, dt_hours: float) -> float:
        """Deliver power for one timestep; returns power ACTUALLY delivered [W]."""
        raise NotImplementedError

    @property
    @abstractmethod
    def deliverable_energy_wh(self) -> float:
        """Bus-side energy still available [Wh], after floor and losses."""
        raise NotImplementedError

    @property
    @abstractmethod
    def deliverable_capacity_wh(self) -> float:
        """Bus-side energy when full [Wh]; the aggregate-SoC denominator."""
        raise NotImplementedError

    def available_discharge_power_w(self, dt_hours: float) -> float:
        """Bus-side power ceiling [W] sustainable for one whole timestep."""
        if dt_hours <= 0:
            return 0.0
        return min(self.max_discharge_power_w,
                self.deliverable_energy_wh / dt_hours)


class Load(ABC):
    """Anything that consumes power."""

    name: str
    priority: LoadPriority
    shed: bool = False

    @abstractmethod
    def demand(self, t_hours: float) -> float:
        """Power wanted [W] at time t, ignoring shed state."""
        raise NotImplementedError

    def effective_demand(self, t_hours: float) -> float:
        """Power actually drawn [W]; zero while shed."""
        return 0.0 if self.shed else self.demand(t_hours)
