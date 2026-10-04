"""Protocol constants for the A.O. Smith iCOMM BLE interface.

Names for blocks, parameters and fault codes follow the vendor app's naming
where one exists.
"""

from __future__ import annotations

from enum import IntEnum

# -- GATT ----------------------------------------------------------------

SERVICE_UUID = "69400001-b5a3-f393-e0a9-e50e24dcca99"
CHAR_TX_UUID = "69400003-b5a3-f393-e0a9-e50e24dcca99"  # we write commands here
CHAR_RX_UUID = "69400002-b5a3-f393-e0a9-e50e24dcca99"  # notifications arrive here

# Advertised name is "iCOMM-<model><serial>", e.g. iCOMM-AC000W037123456.
NAME_PREFIX = "iCOMM-"

# -- Framing -------------------------------------------------------------

HDR_REQUEST = 0xBD  # client -> device
HDR_RESPONSE = 0xDB  # device -> client

STATUS_OK = 0x80  # trailing status byte on a successful response
STATUS_REFUSED = 0x40  # returned instead of 0x80 for a read the device won't serve


class Cmd(IntEnum):
    """Command byte (frame[1]) for requests."""

    WRITE_BLOCK = 0x40
    READ_BLOCK = 0xA0
    PAIR_KEY = 0xF0  # write assetID into a pairing slot (not used by this library)
    CHALLENGE_RESPONSE = 0xF1
    INIT = 0xF2
    SLOT_DELETE = 0xF3  # delete a pairing slot (not used by this library)
    CHALLENGE_REQUEST = 0xF4


# The device caps a single read response at this many 2-byte parameter words.
# Longer blocks are read by paging with the start-parameter offset.
MAX_WORDS_PER_READ = 20

# assetID length in the 0xF2 init response, and the HMAC message length.
ASSET_ID_LEN = 18


class Block(IntEnum):
    IDENTITY = 0  # model + serial, ASCII, byte-swapped within each word
    LIMITS = 1
    FAULTS = 2
    SETPOINT = 8
    CONTROL = 11  # setpoint, mode, mode durations
    REMOTE = 13
    MODULE = 26  # wifi / leak / power counters
    CONFIG = 27


class Block11(IntEnum):
    """Parameter (word) indices within block 11."""

    OPERATING_SETPOINT = 0
    REMOTE_OPERATING_SETPOINT = 6
    OPERATION_MODE = 15  # (duration_days << 8) | mode
    VACATION_MODE_REMAINING_DAYS = 17
    GUEST_MODE_REMAINING_DAYS = 18
    ELECTRIC_MODE_REMAINING_DAYS = 19
    HOT_WATER_PLUS_LEVEL = 20  # beyond MAX_WORDS_PER_READ; needs a paged read


BLOCK2_CURRENT_FAULT_ERROR_CODE = 7


class Mode(IntEnum):
    ELECTRIC = 1
    VACATION = 2
    GUEST = 3
    HYBRID = 4
    HEAT_PUMP = 5


class HotWaterPlus(IntEnum):
    NORMAL_OPERATION = 0
    MORE_HOT_WATER = 1
    MORE_SAVINGS = 2
    MOST_SAVINGS = 3


# Union of the vendor app's fault table and the Service Handbook
# diagnostic code chart, which disagree in both directions:
#   - handbook only: 29, 47, 48
#   - app only:      2, 101, 102 (absent from every manual; likely BLE-internal)
#   - 44 was formally retracted by addendum 100392298
# The vendor app disables user controls while any of its listed faults is active.
FAULT_CODES: dict[int, str] = {
    1: "Dry Fire",
    2: "High Water Temperature",
    3: "Upper Thermistor Sensor Failure",
    4: "Lower Thermistor Sensor Failure",
    6: "Internal Processor Error",
    9: "Power Supply Voltage Error",
    21: "Upper Element Circuit Failure",
    22: "Lower Element Circuit Failure",
    25: "Coil Temperature Sensor Failure",
    26: "Suction Temperature Sensor Failure",
    27: "Discharge Temperature Sensor Failure",
    28: "Ambient Temperature Sensor Failure",
    29: "Outlet Temperature Sensor Failure",  # handbook only; MAX/Premium/120V
    31: "Water Leak",
    44: "Anode is Depleted",  # retracted by addendum 100392298; kept for old units
    46: "Water Shut-off Valve Error",
    47: "Smart Valve Failure",  # handbook only; MAX/Premium/120V
    48: "Battery Low (BR2032)",  # handbook only; all models
    80: "Air Filter is Dirty",
    81: "Condensate Management Error",
    83: "Compressor Low Pressure",
    84: "Compressor Error",
    85: "High Discharge Temperature",
    86: "Fan Error",
    101: "Upper Thermostat Error",
    102: "Lower Thermostat Error",
}
