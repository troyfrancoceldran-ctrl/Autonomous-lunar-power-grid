"""
Canonical asset names, read from the classes themselves.

Import these; never write a load name as a literal in a test. Typing
"Comms Array" for "Communications Array" cost a full test run during Step 8,
and a test asserting against a name that does not exist fails for a reason
that has nothing to do with the code under test.

Kept out of conftest.py deliberately: pytest loads conftest under its own
module name, so importing it again would execute it a second time and build
a second set of load objects. A plain module has no such subtlety.
"""

from environment import LunarEnvironment
from assets.loads import ECLSS, CommsArray, SciencePayload, ThermalControl
from assets.storage import BatteryBank, RegenerativeFuelCell

ECLSS_NAME = ECLSS().name
THERMAL_NAME = ThermalControl(LunarEnvironment()).name
COMMS_NAME = CommsArray().name
SCIENCE_NAME = SciencePayload().name

BATTERY_NAME = BatteryBank().name
RFC_NAME = RegenerativeFuelCell().name
