"""Exceptions raised by the aosmith_ble library."""

from __future__ import annotations


class AOSmithError(Exception):
    """Base class for all library errors."""


class ProtocolError(AOSmithError):
    """A frame was malformed, failed CRC, or was refused by the device."""


class ReadRefusedError(ProtocolError):
    """The device declined to serve a read: the block is absent, or the
    requested offset is past the block's end.

    Distinct from ``SessionError``'s read-side use, which means "no session
    exists" rather than "this block genuinely isn't there" -- the two 7-byte
    short-response shapes on the wire look superficially similar but call
    for different recovery (retry after reconnecting vs. don't ask for this
    block on this device again).
    """


class NotConnectedError(AOSmithError):
    """An operation needed a live connection and there wasn't one."""


class SessionError(AOSmithError):
    """No valid session exists.

    Raised when the 0xF1 challenge response is explicitly rejected, and also
    when a read comes back in the shape the device uses when no session has
    been established at all (or one was lost) -- the response echoes the
    request's block, start and word count instead of a status byte, which is
    not the same wire shape as a genuine block-absent refusal
    (``ReadRefusedError``).
    """


class NotPairedError(AOSmithError):
    """No assetID is available.

    The device's pairing slot is empty and no assetID was cached, so the
    session challenge cannot be answered. Recovery is a physical action: press
    the Bluetooth button on the control panel once, which repopulates the slot
    so the assetID can be read and stored.
    """


class UnknownDeviceError(AOSmithError):
    """No bundled profile matches this device's model and firmware.

    The device is refused, not partially supported -- there is no observed
    evidence for how this firmware handles anything this library might send
    or expect to read. A diagnostics report is still produced so the
    allowlist can grow.
    """


class ValidationError(AOSmithError):
    """A matched profile failed structural validation against the live
    device, or a caller asked for something the matched profile does not
    support (an out-of-range setpoint, an unsupported mode, a write while a
    fault is active).
    """


class ConnectionSlotsExhaustedError(AOSmithError):
    """Wraps ``bleak_retry_connector``'s ``BleakOutOfConnectionSlotsError``.

    A Bluetooth proxy has a small, fixed number of concurrent connection
    slots (three by default on ESPHome), and holding one heater connection
    open for polling permanently consumes one of them.
    """
