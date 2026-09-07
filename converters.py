"""
@file    converters.py
@brief   T03 — power electronics, as a thing distinct from the device.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-07

@details
Every asset in this outpost is quietly assumed to hand the bus exactly what it
makes, and to receive exactly what it asks for. Nothing does. Between each
asset and the bus there is a converter, and it is neither free nor implied by
any efficiency already in the model.

--------------------------------------------------------------------------------
WHAT IS ALREADY COUNTED, AND WHAT IS NOT
--------------------------------------------------------------------------------
This is the whole difficulty of T03: some device efficiencies sound as though
they already include the electronics, and none of them do.

    PV_EFFICIENCY          0.30    CELL efficiency — photons to DC at the
                                panel terminals. An MPPT converter still
                                has to sit between that and the bus.
    BATTERY_*_EFFICIENCY   0.95    Round-trip ELECTROCHEMICAL loss. A real
                                pack is charged and discharged through a
                                bidirectional DC-DC unit that is not in it.
    ELECTROLYZER_EFFICIENCY 0.70   STACK efficiency, chemistry only.
    FUEL_CELL_EFFICIENCY   0.55    STACK efficiency, chemistry only. The fuel
                                cell's output is a low, unregulated,
                                load-dependent voltage — it needs the
                                biggest converter in the outpost, and the
                                0.385 round trip hides that completely.
    FSP_AVAILABILITY       1.0     Not an efficiency at all. The reactor's
                                Stirling convertors already produce AC
                                which is rectified to a 300-400 V DC link
                                before anything else happens.

So adding converters does not double-count: it counts something that was never
counted. NASA's UMIC rack targets > 95 % at 10 kW, which is where
CONVERTER_EFFICIENCY comes from.

--------------------------------------------------------------------------------
WHICH SIDE THE LOSS FALLS ON
--------------------------------------------------------------------------------
The asymmetry matters and is easy to get backwards. A converter of efficiency
eta between an asset and the bus:

    asset SUPPLIES P        the bus receives    P * eta
    asset DEMANDS  P        the bus must send   P / eta

Multiply on the way out, divide on the way in — the same rule as the battery's
round trip, and for the same reason. Getting it the wrong way round makes a
converter a source of power rather than a sink, and the conservation identity
will say so immediately.

The converter sits at the ASSET end, so the feeder carries the CONVERTED
power. That ordering is deliberate: a converter's job is to present the bus
voltage, so everything between it and the bus is at bus voltage by definition.

@note Opt-in behind `--converters`, separately from `--topology`. Two flags
    rather than one because the point of T03 is to attribute loss — with a
    single switch there would be no way to say how much of the damage is
    copper and how much is silicon.

@see config.py CONVERTER_EFFICIENCY, and its NASA UMIC source.
@see topology.py for the feeders these sit behind.
@see power_bus.py for how the two combine in a tick.


================================================================================
API
================================================================================

Converter                                                           [dataclass]
    One power-electronics stage between an asset and the bus.

    @param  name        Matches the asset. A mismatch is SILENT — see defect
                        D-03 in power_bus.py, which cost a 1 km reactor link.
    @param  efficiency  Fraction in (0, 1].
    @param  rated_w     Continuous rating; reported, not yet enforced.

    delivered_w(asset_power_w) -> float
        Power reaching the bus when the asset supplies this much.

    drawn_w(asset_power_w) -> float
        Power the bus must supply for the asset to receive this much.

    loss_supplying_w(asset_power_w) -> float
    loss_drawing_w(asset_power_w) -> float
        The loss in each direction, as a positive number.

build_converters(bus, efficiency=CONVERTER_EFFICIENCY) -> dict[str, Converter]
    One converter per asset on a PowerBus, rated from the asset's own peak.
"""

import dataclasses

from config import CONVERTER_EFFICIENCY


@dataclasses.dataclass(frozen=True)
class Converter:
    """One power-electronics stage; see the API section."""

    name: str
    efficiency: float = CONVERTER_EFFICIENCY
    rated_w: float = 0.0

    def __post_init__(self):
        if not 0.0 < self.efficiency <= 1.0:
            raise ValueError(
                f"{self.name}: efficiency {self.efficiency} outside (0, 1]")

    def delivered_w(self, asset_power_w: float) -> float:
        """Asset supplies this much; the bus receives less."""
        return asset_power_w * self.efficiency

    def drawn_w(self, asset_power_w: float) -> float:
        """Asset needs this much; the bus must send more."""
        return asset_power_w / self.efficiency

    def loss_supplying_w(self, asset_power_w: float) -> float:
        """Positive loss when power flows asset -> bus."""
        return asset_power_w - self.delivered_w(asset_power_w)

    def loss_drawing_w(self, asset_power_w: float) -> float:
        """Positive loss when power flows bus -> asset."""
        return self.drawn_w(asset_power_w) - asset_power_w


def build_converters(bus, efficiency: float = CONVERTER_EFFICIENCY) -> dict:
    """One converter per asset on a PowerBus, keyed by asset name.

    Built from the BUS rather than from a hardcoded list, so an asset added in
    main.build_outpost cannot end up without power electronics. That is the
    D-03 lesson applied before it can bite again: derive the set of names from
    the thing being modelled, never restate it.
    """
    converters = {}
    for source in bus.sources:
        converters[source.name] = Converter(source.name, efficiency)
    for device in bus.storage:
        converters[device.name] = Converter(device.name, efficiency)
    for load in bus.loads:
        converters[load.name] = Converter(load.name, efficiency)
    return converters
