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
"""

from abc import ABC, abstractmethod

from config import LoadPriority


class PowerSource(ABC):
    """
    @brief Anything that can inject power onto the bus.

    @details
    Covers the PV array, the FSP reactor, or an RFC operating in
    fuel-cell/discharge mode.

    @var name  Human-readable identifier, used in logs and plot legends.
    """

    name: str

    @abstractmethod
    def available_power(self, t_hours: float, environment) -> float:
        """
        @brief Power this source COULD deliver at time t, before dispatch.

        @param t_hours      Simulation time [h] since t=0.
        @param environment  LunarEnvironment supplying irradiance/day-night
                            state. Sources that do not depend on it (FSP)
                            must still accept it — the uniform signature is
                            what lets power_bus.py iterate over mixed source
                            types without type checks.
        @return Available power [W], >= 0.

        @note This is the pre-dispatch ceiling, not the power actually taken.
              Implementations must be pure: compute and return, never cache
              on self, since the engine may query arbitrary t in any order.
        """
        raise NotImplementedError


class PowerStorage(ABC):
    """
    @brief Anything that can absorb or release energy over time.

    @details
    Batteries, or an RFC's electrolyzer (charge) + fuel cell (discharge) pair.
    Unlike PowerSource, implementations are STATEFUL: charge() and discharge()
    mutate stored energy, so call order within a timestep matters.

    @var name  Human-readable identifier, used in logs and plot legends.
    """

    name: str

    @property
    @abstractmethod
    def state_of_charge(self) -> float:
        """
        @brief Fractional fill level.

        @return Fill fraction in [0, 1].

        @note For the RFC this must be an energy-equivalent fill fraction
              derived from remaining H2/O2 mass, not a separate concept — the
              controller has to treat storage devices interchangeably.
        """
        raise NotImplementedError

    @abstractmethod
    def charge(self, power_w: float, dt_hours: float) -> float:
        """
        @brief Attempt to absorb power for one timestep.

        @param power_w   Power offered [W], >= 0.
        @param dt_hours  Duration of the timestep [h].
        @return Power ACTUALLY absorbed [W], in [0, power_w].

        @warning The return value is the contract. A full or power-limited
                 device cannot take everything offered, and power_bus.py
                 relies on the difference to know how much surplus remains.
                 Returning power_w unconditionally silently fabricates
                 storage capacity.
        """
        raise NotImplementedError

    @abstractmethod
    def discharge(self, power_w: float, dt_hours: float) -> float:
        """
        @brief Attempt to deliver power for one timestep.

        @param power_w   Power requested [W], >= 0.
        @param dt_hours  Duration of the timestep [h].
        @return Power ACTUALLY delivered [W], in [0, power_w].

        @warning As with charge(), the shortfall between requested and
                 delivered is what tells the engine a brownout occurred.
        """
        raise NotImplementedError


class Load(ABC):
    """
    @brief Anything that consumes power.

    @details
    ECLSS, thermal control, comms, science payloads. Concrete subclasses only
    implement demand(); shed bookkeeping is handled here so the controller has
    one consistent API across all load types.

    @var name      Human-readable identifier, used in logs and plot legends.
    @var priority  LoadPriority tier. Lower number = shed last, restored first.
    @var shed      True when the controller has disconnected this load.
    """

    name: str
    priority: LoadPriority
    shed: bool = False

    @abstractmethod
    def demand(self, t_hours: float) -> float:
        """
        @brief Power this load WANTS to draw, ignoring shed state.

        @param t_hours  Simulation time [h] since t=0.
        @return Demanded power [W], >= 0.
        """
        raise NotImplementedError

    def effective_demand(self, t_hours: float) -> float:
        """
        @brief Power this load actually draws right now.

        @param t_hours  Simulation time [h] since t=0.
        @return 0.0 if shed, otherwise demand(t_hours) [W].

        @note power_bus.py must always call this, never demand() directly,
              when computing the real load on the bus. Implemented once here
              rather than in four subclasses, each free to get it wrong.
        """
        return 0.0 if self.shed else self.demand(t_hours)
