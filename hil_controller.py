"""
@file    hil_controller.py
@brief   Run the outpost's controller on a real ESP32, over a serial link.
@author  Troy Celdran
@author  JARVIS (Claude Opus 5) — co-author
@date    2026-09-15

@details
B03. The physics stays here; the DECISIONS move to hardware. Every tick this
sends the board what the controller would have been shown, and applies whatever
the board sends back.

    from hil_controller import HardwareController
    bus = build_outpost(env)
    bus.controller = HardwareController("/dev/cu.usbserial-0001")

The controller was written numpy-free at Step 7 precisely so it could port to a
microcontroller. This is that decision being cashed in.

WHAT IS AND IS NOT ON THE BOARD
    On it:  the policy — thresholds, priority ordering, dwell timers. The
            dwell state lives in the ESP32's RAM between ticks, which is what
            makes this a controller rather than a lookup.
    Not:    the physics, the assets, the topology. Those stay in Python, where
            they can be inspected.

API
    class HardwareController(ControlStrategy)
        update(t_hours, aggregate_soc, loads, headroom_w) -> Load | None
            Identical signature to AutonomousController.update, so the bus
            cannot tell the difference. That is the whole design.
        identify() -> str
        reset() -> None
        close() -> None

@note POSITIONAL PROTOCOL. The board has no heap and no strings, so loads are
    identified by their INDEX in the list the bus passes. The order must be
    stable within a run — it is, because PowerBus holds one list and never
    reorders it — and the index is meaningless across runs.
@note The board is the authority on WHICH load moves, but this side applies
    the change to the actual object. A reply naming an out-of-range index is
    a protocol failure and raises rather than being clamped: a clamped index
    would shed a load nobody chose.
"""

import time

try:
    import serial
except ImportError:                              # pragma: no cover
    serial = None

from controller import ControlStrategy

PROTOCOL_VERSION = 1
DEFAULT_PORT = "/dev/cu.usbserial-0001"
DEFAULT_BAUD = 115200


class LinkError(RuntimeError):
    """The board did not answer, or answered something unintelligible."""


class HardwareController(ControlStrategy):
    """The same policy as AutonomousController, executing on an ESP32."""

    def __init__(self, port: str = DEFAULT_PORT, baud: int = DEFAULT_BAUD,
                 name: str = "ESP32 Controller", timeout_s: float = 2.0,
                 settle_s: float = 2.0):
        """Open the link and confirm the board is the firmware we expect.

        @param settle_s  the ESP32 resets when the port opens — DTR toggles on
            most CP2102 boards — and spends about a second in its bootloader.
            Talking to it before then gets bootloader chatter, not answers.
        """
        if serial is None:
            raise LinkError("pyserial is not installed: pip install pyserial")
        self.name = name
        self.port_name = port
        # DTR and RTS must be LOW BEFORE the port opens. On a CP2102 board they
        # are wired to EN and IO0, so opening with them asserted resets the
        # ESP32 straight into its ROM bootloader — which talks at 74880 baud
        # and, read at 115200, produces an endless stream of plausible-looking
        # garbage. The firmware never runs at all.
        self._serial = serial.Serial()
        self._serial.port = port
        self._serial.baudrate = baud
        self._serial.timeout = timeout_s
        self._serial.dtr = False
        self._serial.rts = False
        self._serial.open()
        time.sleep(settle_s)
        self._serial.reset_input_buffer()

        banner = self._handshake(port)
        parts = banner.split()
        self.protocol = int(parts[2])
        self.max_loads = int(parts[3])
        if self.protocol != PROTOCOL_VERSION:
            raise LinkError(
                f"board speaks protocol {self.protocol}, host speaks "
                f"{PROTOCOL_VERSION}")
        self.ticks = 0
        self.actions = 0

    def _handshake(self, port: str, attempts: int = 3) -> str:
        """Ask who is there, tolerating one round of boot chatter.

        The first reply after a reset is often a fragment of the boot banner
        rather than an answer, so a single failure is not a verdict.
        """
        last = ""
        for _ in range(attempts):
            self._serial.reset_input_buffer()
            try:
                last = self.identify()
            except LinkError as exc:
                last = str(exc)
                continue
            if last.startswith("LUNAR B03"):
                return last
            time.sleep(0.4)
        raise LinkError(
            f"no B03 firmware answering on {port}. Last reply: "
            f"{last[:60]!r}{' ...' if len(last) > 60 else ''}")

    # --- the link ------------------------------------------------------------
    def _ask(self, line: str) -> str:
        """Send one line, read exactly one line back.

        The buffer is drained FIRST. This protocol is strict request/response,
        so anything already waiting when we send is by definition stale — a
        late reply to a request that timed out, or boot chatter. Left in place
        it offsets every subsequent exchange by one, and the symptom is a
        perfectly valid answer to the previous question, which is far harder to
        recognise than silence.
        """
        self._serial.reset_input_buffer()
        self._serial.write((line + "\n").encode("ascii"))
        self._serial.flush()
        reply = self._serial.readline().decode("ascii", "replace").strip()
        if not reply:
            raise LinkError(f"no reply to {line.split()[0]!r} within the timeout")
        return reply

    def identify(self) -> str:
        """The firmware banner, for checking what is actually on the board."""
        return self._ask("I")

    def reset(self) -> None:
        """Clear the board's dwell timers.

        Call this between scenarios. A board that has not been power-cycled
        carries its timers forward, and a stale timer looks exactly like a
        model bug from the host side.
        """
        reply = self._ask("R")
        if reply != "OK":
            raise LinkError(f"reset refused: {reply!r}")

    def close(self) -> None:
        """Release the port."""
        if getattr(self, "_serial", None) is not None:
            self._serial.close()
            self._serial = None

    # --- the ControlStrategy interface ---------------------------------------
    def update(self, t_hours: float, aggregate_soc: float, loads: list,
               headroom_w: float):
        """Ask the board what to do, then do it. Returns the Load, or None."""
        if len(loads) > self.max_loads:
            raise LinkError(
                f"{len(loads)} loads but the firmware holds {self.max_loads}")

        fields = [f"T {t_hours:.6f} {aggregate_soc:.9f} {headroom_w:.4f} "
                  f"{len(loads)}"]
        for load in loads:
            fields.append(f"{int(load.priority)} {1 if load.shed else 0} "
                          f"{load.demand(t_hours):.4f}")
        reply = self._ask(" ".join(fields))

        if not reply.startswith("A "):
            raise LinkError(f"expected an action, got {reply!r}")
        _, index_s, shed_s = reply.split()
        index, shed = int(index_s), bool(int(shed_s))

        self.ticks += 1
        if index < 0:
            return None
        if index >= len(loads):
            # Clamping would shed a load nobody chose. Fail instead.
            raise LinkError(f"board named load {index} of {len(loads)}")

        target = loads[index]
        target.shed = shed
        self.actions += 1
        return target

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
