"""
Tests for controller.py.

Invariant sections from tests/INVARIANTS.md covered here:
    A structural · F control policy

Fixtures available with no import (see conftest.py):
    env  loads  controller  battery  rfc  outpost
    nominal_history  outage_history  fine_history        <- READ-ONLY

Two rules, both learned the hard way in this project:
    - never retype a name; import it from conftest (COMMS_NAME, etc.)
    - never hardcode a config value; import the constant and assert the
      RELATIONSHIP, so the test survives a deliberate change to the number
"""
