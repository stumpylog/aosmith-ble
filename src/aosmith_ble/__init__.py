"""Local Bluetooth LE client for A.O. Smith iCOMM heat pump water heaters.

No cloud account or vendor credentials required -- this connects directly
to the appliance over BLE, after matching it against a bundled device
profile that gates every read's and write's trust.
"""

from __future__ import annotations

from . import protocol
from .client import AOSmithBLEClient, async_discover, pairing_code_from_name
from .const import Mode
from .diagnostics import DiagnosticReport, probe_presence
from .exceptions import (
    AOSmithError,
    ConnectionSlotsExhaustedError,
    NotConnectedError,
    NotPairedError,
    ProtocolError,
    ReadRefusedError,
    SessionError,
    UnknownDeviceError,
    ValidationError,
)
from .models import DeviceInfo, Fault, Feature, FeatureSet
from .profiles import FieldName, FieldScope, Profile, Trust
from .profiles.bundled import match_profile

__version__ = "0.1.0"

__all__ = [
    "AOSmithBLEClient",
    "AOSmithError",
    "ConnectionSlotsExhaustedError",
    "DeviceInfo",
    "DiagnosticReport",
    "Fault",
    "Feature",
    "FeatureSet",
    "FieldName",
    "FieldScope",
    "Mode",
    "NotConnectedError",
    "NotPairedError",
    "Profile",
    "ProtocolError",
    "ReadRefusedError",
    "SessionError",
    "Trust",
    "UnknownDeviceError",
    "ValidationError",
    "async_discover",
    "match_profile",
    "pairing_code_from_name",
    "probe_presence",
    "protocol",
]
