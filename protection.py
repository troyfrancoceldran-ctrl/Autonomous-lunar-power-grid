"""
@file    protection.py
@brief   T04 — what happens in the microseconds after something shorts.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — spec, plumbing, tests, review
@date    2026-09-07

@details
T01 gave the outpost conductors and T02 made them cost something. Neither
asked what those conductors do when one of them touches the chassis. This
module does.

--------------------------------------------------------------------------------
WHY DC PROTECTION IS THE HARD KIND
--------------------------------------------------------------------------------
An AC fault current crosses zero twice per cycle, and a mechanical breaker
exploits that: it opens the contacts and the arc self-extinguishes at the next
zero. A DC fault current never crosses zero. The arc has no moment of weakness
and a mechanical contact will hold it until something melts.

So DC switchgear has to FORCE the current to zero by switching, and it has to
do it in microseconds before the semiconductors downstream cook. Spacecraft
practice is the Solid State Power Controller: the ISS distributes power through
RPCMs, and NASA's modern AMPS switchgear module does the same job at 0.5 kg
against the RPCM's 4.7 kg.

An SSPC protects on ENERGY, not merely on current. A circuit breaker trips when
current reaches a threshold; an SSPC integrates I^2 dt and trips when enough
energy has passed. That difference is the whole of method 2 below.

--------------------------------------------------------------------------------
THE NUMBERS THIS OUTPOST ACTUALLY PRODUCES
--------------------------------------------------------------------------------
Bolted fault at the far end of each feeder, sources treated as ideal, so these
are UPPER BOUNDS (see the declared simplification about source impedance):

    Battery Bank            36.81 mm^2    R 0.00327 ohm     36.6 kA
    PV Array               128.45 mm^2    R 0.00469 ohm     25.6 kA
    Regenerative Fuel Cell  36.81 mm^2    R 0.00655 ohm     18.3 kA
    ECLSS                    2.39 mm^2    R 0.02519 ohm      4.8 kA
    Science Payload         26.50 mm^2    R 0.02729 ohm      4.4 kA
    Thermal Control          4.05 mm^2    R 0.02977 ohm      4.0 kA
    Communications Array     5.52 mm^2    R 0.06549 ohm      1.8 kA
    FSP Reactor             10.60 mm^2    R 1.13700 ohm      0.9 kA

The battery bank is rated 417 A at 50 kW and 120 V. Its prospective fault is
36.6 kA — EIGHTY-EIGHT TIMES rated. There is no mechanical contact that opens
that on the Moon and is ever useful again.

Two things in that table are worth staring at.

  * THE REACTOR HAS THE LOWEST FAULT CURRENT, at the HIGHEST voltage. A
    kilometre of 10.6 mm^2 aluminium is a large series resistance, and it
    limits the fault as effectively as any device would. Distance protects.

  * THE TEMPERATURE FINDING INVERTS. T02 found the cable is worst in daylight,
    because heat raises resistance and burns power. Protection wants the
    opposite: a cold cable is a BETTER conductor, so the fault is worse.

        battery feeder at night  R 0.00327 ohm   36.6 kA
        battery feeder at ref    R 0.01440 ohm    8.3 kA
        battery feeder at day    R 0.02055 ohm    5.8 kA

    A 6.3x swing, and the worst case for protection is the exact condition
    that is best for efficiency. Anything sized on a daytime fault current is
    undersized by a factor of six at midnight. Protection must be designed
    against the COLD case; losses against the HOT one.

--------------------------------------------------------------------------------
WORK ORDER — T04 IS YOURS
--------------------------------------------------------------------------------
Same arrangement as T01: the engineering is yours, the plumbing and tests are
mine and already work. Four methods, marked >>> YOURS. Ask for syntax or
algorithm help whenever you want it.

`tests/test_protection.py` skips any test whose method still raises, so the
suite stays green and `pytest -rs` prints what is left.

1.  prospective_fault_current_a(feeder, temperature_k)          [module function]

        I_fault = V / R(T)

    A bolted fault — zero fault resistance — at the far end of the feeder,
    with the source treated as ideal. Use the feeder's own nominal voltage
    and its resistance at the given temperature.

    @note Ideal source means this is an UPPER bound. Real sources have
        internal impedance and converters have current limits, both of which
        reduce it. An upper bound is the right thing for sizing protection,
        but call it what it is.

2.  ProtectionDevice.trip_time_s(current_a)

    The SSPC curve, three regions, in this order:

        current <= rated                    -> math.inf     (never trips)
        current >= rated * inst_multiple    -> min_trip_time_s
        otherwise                           -> i2t_rating / current^2

    The middle region is the interesting one. Trip time falls as the SQUARE
    of current, so a 2x overload is tolerated four times as long as a 4x one.
    That is what "protects on energy" means: the device is integrating I^2 dt
    and firing at a fixed let-through.

    TRAP — check the ORDER of your branches. Written the other way round, a
    dead short lands in the I^2t region and computes a trip time faster than
    the hardware can physically act, which reads as excellent protection and
    is a lie. The instantaneous floor exists because silicon has a minimum
    switching time.

3.  ProtectionDevice.let_through_energy_a2s(current_a)

        E = current^2 * trip_time_s(current)

    The number that says whether the CABLE survives, as opposed to whether
    the device noticed. In the I^2t region this should come out flat at the
    device's rating — verify that, because it is the definition rather than a
    coincidence, and if it does not, method 2 is wrong.

    @note Returns math.inf for a current below the rating. That is correct
        and not a bug: a device that never trips lets through unbounded
        energy, which is precisely why the rating has to sit below what the
        cable can survive continuously.

4.  is_selective(upstream, downstream, current_a)               [module function]

    True when `downstream` clears far enough ahead of `upstream` that only
    the faulted zone goes dark:

        downstream.trip_time_s(I) + margin <= upstream.trip_time_s(I)

    NASA calls the goal "zonal protection" — the device nearest the fault
    trips and nothing else does. Failing selectivity is how a single shorted
    science instrument takes the habitat's life support with it.

    TRAP — both devices may be in their instantaneous region at a high enough
    fault current, and there both return the same floor. Selectivity by
    timing alone is then impossible. That is a real and well known limitation
    of solid-state protection, not a flaw in your implementation: notice it,
    and let the test say so.

--------------------------------------------------------------------------------
WHAT THIS DELIBERATELY DOES NOT MODEL
--------------------------------------------------------------------------------
  * Source impedance. Battery internal resistance and converter current limits
    both cut the real fault current well below these figures. Modelling them
    would need a cell-level battery model this project does not have, so the
    bound is left honest and explicit rather than guessed at.
  * Arc resistance. Every fault here is bolted. A real arcing fault draws less
    current and is HARDER to detect, which is the case that actually burns
    spacecraft.
  * Fault detection and location. Knowing a fault exists is assumed. In a real
    DC microgrid that is most of the problem.
  * Device mass and heat. An SSPC that interrupts 36 kA is not free in either.

@see NASA NTRS 20250000763 — zonal protection, algorithmic assignment of trip
    times and current limits, ISS RPCM 4.7 kg vs AMPS module 0.5 kg.
@see config.py for SSPC_* constants and their sources.
@see topology.py for the feeders these devices protect.


================================================================================
API
================================================================================

ProtectionDevice                                                    [dataclass]
    One solid-state power controller, guarding one feeder.

    @param  name                  Matches the feeder and the asset it serves.
    @param  rated_current_a       Continuous rating; below this it never trips.
    @param  i2t_rating_a2s        Let-through energy before it fires.
    @param  inst_multiple         Instantaneous threshold, as a multiple of
                                the rating.
    @param  min_trip_time_s       Physical floor on switching speed.

    trip_time_s(current_a) -> float
    let_through_energy_a2s(current_a) -> float
    instantaneous_threshold_a -> float                          [@property]

prospective_fault_current_a(feeder, temperature_k) -> float
    Bolted-fault current at the far end of a feeder, ideal source.

is_selective(upstream, downstream, current_a) -> bool
    Whether the downstream device clears first by the coordination margin.

feeder_rated_current_a(feeder, loss_fraction=MAX_FEEDER_LOSS_FRACTION) -> float
    The continuous current a conductor was sized to carry, by inverting the
    T01 sizing rule. Plumbing.

build_protection(buses) -> dict[str, ProtectionDevice]
    A device per feeder, rated from the feeder's own conductor. Plumbing.

coordination_failures(upstream, devices, feeder_currents) -> list[str]
    Feeders that do not clear ahead of the bus device. Plumbing.

fault_survey(buses, temperature_k=CABLE_TEMP_NIGHT_K) -> dict[str, float]
    Prospective fault current at every feeder; defaults to the COLD case,
    which is the worst one.
"""

import dataclasses
import math

from config import (CABLE_TEMP_NIGHT_K, CONDUCTOR_RESISTIVITY_OHM_M,
                    MAX_FEEDER_LOSS_FRACTION,
                    PROTECTION_COORDINATION_MARGIN_S,
                    SSPC_I2T_RATING_A2S, SSPC_INSTANTANEOUS_TRIP_MULTIPLE,
                    SSPC_MIN_TRIP_TIME_S)


@dataclasses.dataclass
class ProtectionDevice:
    """One solid-state power controller; see the API section."""

    name: str
    rated_current_a: float
    i2t_rating_a2s: float = SSPC_I2T_RATING_A2S
    inst_multiple: float = SSPC_INSTANTANEOUS_TRIP_MULTIPLE
    min_trip_time_s: float = SSPC_MIN_TRIP_TIME_S

    @property
    def instantaneous_threshold_a(self) -> float:
        """Current above which the device stops integrating and just fires."""
        return self.rated_current_a * self.inst_multiple

    # =========================================================================
    # START EDITING HERE — T04, method 2                            >>> YOURS
    # =========================================================================
    def trip_time_s(self, current_a: float) -> float:
        """Seconds before the device opens at this current.

        math.inf below the rating; min_trip_time_s at or above the
        instantaneous threshold; i2t_rating / current^2 in between.
        Mind the branch order — see TRAP in the module docstring.
        """
        
        raise NotImplementedError("T04 method 2")

    # ------------------------------------------------------------- 3 >>> YOURS
    def let_through_energy_a2s(self, current_a: float) -> float:
        """I^2 t actually let through before the device opens."""
        raise NotImplementedError("T04 method 3")


# ------------------------------------------------------------- 1 >>> YOURS ---
def prospective_fault_current_a(feeder, temperature_k: float) -> float:
    """Bolted-fault current at the far end of a feeder, ideal source.

    I = feeder.nominal_voltage_v / feeder.resistance_ohm(temperature_k)
    """
    raise NotImplementedError("T04 method 1")


# ------------------------------------------------------------- 4 >>> YOURS ---
def is_selective(upstream, downstream, current_a: float) -> bool:
    """True when the downstream device clears first by the margin.

    downstream.trip_time_s(I) + PROTECTION_COORDINATION_MARGIN_S
        <= upstream.trip_time_s(I)
    """
    raise NotImplementedError("T04 method 4")


# =============================================================================
# Plumbing — mine, and working.
# =============================================================================

def build_protection(buses) -> dict:
    """A device per feeder, rated from what that feeder is sized to carry.

    The rating comes from the feeder's own conductor: a device rated above
    what its cable can carry protects the device and lets the cable burn,
    which is the wrong way round. Sizing both from the same area keeps them
    consistent by construction rather than by remembering to.

    @note Keyed by feeder name, so a device is bound to its feeder the same
        way a feeder is bound to its asset — and with the same hazard. See
        defect D-03 in power_bus.py: a name mismatch is silent.
    """
    devices = {}
    for bus in buses:
        for feeder in bus.feeders:
            devices[feeder.name] = ProtectionDevice(
                name=feeder.name,
                rated_current_a=feeder_rated_current_a(feeder),
            )
    return devices


def feeder_rated_current_a(feeder,
                        loss_fraction: float = MAX_FEEDER_LOSS_FRACTION
                        ) -> float:
    """The continuous current this conductor was sized to carry.

    Inverting the T01 sizing rule. Sizing gave

        A = P * rho * L_c / (f * V^2)

    so the power that area was chosen for is P = A * f * V^2 / (rho * L_c),
    and the current is that over V:

        I_rated = A * f * V / (rho * L_c)

    Deriving it rather than storing it means the device rating cannot drift
    away from the cable it protects. A device rated above its conductor
    protects itself and lets the cable burn, which is the wrong way round.
    """
    return (feeder.area_m2 * loss_fraction * feeder.nominal_voltage_v
            / (CONDUCTOR_RESISTIVITY_OHM_M * feeder.conductor_length_m))


def coordination_failures(upstream, devices, feeder_currents) -> list:
    """Feeders whose device does not clear ahead of `upstream`, as strings.

    Reports rather than asserts, the same way over_span_limit does — a
    coordination study produces a list of problems to fix, not an exception.

    @param upstream  The device guarding the bus itself, which must be the
        LAST thing to open. Everything below it should clear first.
    """
    problems = []
    for name, current_a in sorted(feeder_currents.items()):
        downstream = devices.get(name)
        if downstream is None:
            problems.append(f"{name}: no protection device")
            continue
        if not is_selective(upstream, downstream, current_a):
            problems.append(
                f"{name}: downstream {downstream.trip_time_s(current_a):.2e} s "
                f"vs upstream {upstream.trip_time_s(current_a):.2e} s "
                f"at {current_a:.0f} A")
    return problems


def fault_survey(buses, temperature_k=CABLE_TEMP_NIGHT_K) -> dict:
    """Prospective fault current at every feeder, worst case by default.

    Defaults to the NIGHT temperature deliberately: a cold conductor is a
    better one, so the coldest case is the worst case for fault current —
    the exact inverse of the loss picture in T02.
    """
    return {feeder.name: prospective_fault_current_a(feeder, temperature_k)
            for bus in buses for feeder in bus.feeders}
