"""Exceptions raised by the aosmith_ble library."""

from __future__ import annotations

from enum import StrEnum


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

    Raised for a lost or never-established session: a read comes back in the
    shape the device uses when no session has been established (or one was
    lost), where the response echoes the request's block, start and word
    count instead of a status byte. That is not the same wire shape as a
    genuine block-absent refusal (``ReadRefusedError``). A rejected challenge
    response raises the subclass ``ChallengeRejectedError``.
    """


class ChallengeRejectedError(SessionError):
    """The heater rejected the session challenge response.

    A subclass of ``SessionError`` so existing handlers still catch it. It is
    its own type because the recovery differs from a lost session: the
    assetID used was not accepted, so a fresh one has to be read from the
    pairing slot (a Bluetooth button press), and a single rejection has had
    non-auth causes before (a stale link), so a caller usually retries once
    on a fresh link before treating it as an authentication failure.
    """


class SessionExpiredError(SessionError):
    """The heater ended the session; the BLE link may still be up.

    Raised for a status 0x10 reply. The heater ends each session about 29.5
    minutes after it was established. A subclass of ``SessionError`` so
    existing handlers still catch it. Reads recover from it on their own by
    re-running the session handshake; a write that gets it is not re-sent,
    since whether it was applied is unknown.
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

    ``model`` (deswapped, as in ``DeviceInfo.model``) and ``firmware``
    ``(major, minor)`` say what was refused. The client always sets both.
    """

    def __init__(
        self,
        message: str,
        *,
        model: str | None = None,
        firmware: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.model = model
        self.firmware = firmware


class ValidationError(AOSmithError):
    """A matched profile failed structural validation against the live
    device, or a caller asked for something the matched profile does not
    support (an out-of-range setpoint, an unsupported mode, a write while a
    fault is active).
    """


class ConfigurationIssue(StrEnum):
    """Why a device or its link was refused as unsupported."""

    UNITS = "units"
    MTU = "mtu"


class UnsupportedConfigurationError(ValidationError):
    """The device or link is in a configuration this library cannot work
    with, and the user can change it: the display units are not Fahrenheit
    (``UNITS``) or the negotiated ATT MTU is too small for a full response
    (``MTU``).

    A subclass of ``ValidationError``, so existing handlers still catch it.
    ``reason`` lets a caller choose the right instruction without parsing
    the message.
    """

    def __init__(self, message: str, *, reason: ConfigurationIssue) -> None:
        super().__init__(message)
        self.reason = reason


class ConnectionSlotsExhaustedError(AOSmithError):
    """Wraps ``bleak_retry_connector``'s ``BleakOutOfConnectionSlotsError``.

    A Bluetooth proxy has a small, fixed number of concurrent connection
    slots (three by default on ESPHome), and holding one heater connection
    open for polling permanently consumes one of them.
    """
