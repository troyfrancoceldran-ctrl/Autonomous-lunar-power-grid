"""
Abstract interfaces for every microgrid asset.

Design intent: power_bus.py and controller.py depend ONLY on the interfaces
defined here (PowerSource, PowerStorage, Load) — never on a concrete class
like PVArray or BatteryBank directly. That's what lets us add a new
generation or storage type later (or swap the controller's strategy) without
touching the simulation engine.

Concrete implementations live in:
    assets/generation.py   -> PVArray, FissionSurfacePower
    assets/storage.py       -> BatteryBank, RegenerativeFuelCell
    assets/loads.py          -> ECLSS, ThermalControl, CommsArray, SciencePayload
"""

from abc import ABC, abstractmethod

from config import LoadPriority


class PowerSource(ABC):
    """Anything that can inject power onto the bus (PV array, FSP reactor,
    or an RFC operating in fuel-cell/discharge mode)."""

    name: str

    @abstractmethod
    def available_power(self, t_hours: float, environment) -> float:
        """Power [W] this source COULD deliver at time t, before any dispatch
        decision is made. For PV this depends on `environment` (day/night
        phase, irradiance); for FSP it's roughly constant.
        """
        raise NotImplementedError


class PowerStorage(ABC):
    """Anything that can absorb or release energy over time: batteries, or
    an RFC's electrolyzer (charge) + fuel cell (discharge) pair."""

    name: str

    @property
    @abstractmethod
    def state_of_charge(self) -> float:
        """Fractional fill level in [0, 1]. For RFC, this should be an
        energy-equivalent fill fraction derived from remaining H2/O2 mass,
        not a separate concept — the controller should be able to treat
        storage devices interchangeably."""
        raise NotImplementedError

    @abstractmethod
    def charge(self, power_w: float, dt_hours: float) -> float:
        """Attempt to absorb `power_w` for `dt_hours`. Must return the power
        ACTUALLY absorbed (<= power_w), since a full or power-limited device
        can't take everything offered. power_bus.py relies on this return
        value to know how much surplus is left over."""
        raise NotImplementedError

    @abstractmethod
    def discharge(self, power_w: float, dt_hours: float) -> float:
        """Attempt to deliver `power_w` for `dt_hours`. Must return the power
        ACTUALLY delivered (<= power_w), since an empty or power-limited
        device can't always meet the request."""
        raise NotImplementedError


class Load(ABC):
    """Anything that consumes power: ECLSS, thermal control, comms, science
    payloads. Concrete subclasses only need to implement `demand()`; shed
    bookkeeping is handled here so the controller has one consistent API
    across all load types."""

    name: str
    priority: LoadPriority
    shed: bool = False

    @abstractmethod
    def demand(self, t_hours: float) -> float:
        """Power [W] this load WANTS to draw at time t, ignoring shed state."""
        raise NotImplementedError

    def effective_demand(self, t_hours: float) -> float:
        """Power [W] this load actually draws right now, accounting for
        whether the controller has shed it. power_bus.py should always call
        this, never `demand()` directly, when computing the real load on
        the bus."""
        return 0.0 if self.shed else self.demand(t_hours)
