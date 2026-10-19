# Changelog

## 0.2.0

- New HPTS-50 fields, all read-only and all from one Block 27 read:
  - `FieldName.POWER_W` (27:6), graded OK: the power in watts the heater
    reports for the running component (356 W compressor, 4500 W element,
    0 idle). It is the heater's own figure, not a measurement.
  - `FieldName.ENERGY_WH` (27:7-9), graded OK: the running total of that
    power in watt-hours, or `None` when the heater reports no value.
  - `FieldName.HOT_WATER_AVAILABILITY` (27:23), graded PARTIAL so it is only
    returned with `min_trust=Trust.PARTIAL`: a `HotWaterAvailability` level
    (`LOW` 0, `MEDIUM` 5, `HIGH` 10), or the raw word for any other value.
    It has been seen rising during a reheat but not yet falling.
- New codecs `u48` and `availability`, and the `HotWaterAvailability` enum.
- The Block 27 read's span depends on the trust a caller reads at: params 6-9
  at the default, 6-23 with `Trust.PARTIAL`.
- The heater ends each session about 29.5 minutes after it was established,
  while the link stays up, and answers with status `0x10`. That reply now
  raises the new `SessionExpiredError`, a `SessionError` subclass, instead of
  a plain `ProtocolError`.
- `async_get_state()` recovers from an expired session on its own: it re-runs
  the session handshake on the open link, falls back to a full reconnect if
  that fails, and retries the read once.
- A write is never re-sent. Its pre-write state read is what recovers an
  expired session. A write acknowledged with `0x10` raises
  `SessionExpiredError`.

## 0.1.1

- New `ChallengeRejectedError`, a `SessionError` subclass, raised when the
  heater rejects the session challenge. The message now says to press the
  Bluetooth button instead of blaming the cached assetID.
- New `UnsupportedConfigurationError`, a `ValidationError` subclass with a
  `reason` (`ConfigurationIssue.UNITS` or `ConfigurationIssue.MTU`), raised for
  the Celsius-display check and the minimum-MTU check. Existing
  `except ValidationError` handlers still catch it.
- `UnknownDeviceError` now carries `model` and `firmware`, so a caller can say
  what was refused. `DeviceInfo` gains `firmware` (`(major, minor)`), set on a
  successful `connect()`.
- New `AOSmithBLEClient.async_close()`: waits for any read or write in flight,
  closes the link, and makes every later `connect()` and operation, including
  ones already queued, raise `NotConnectedError`. Idempotent. `disconnect()`
  is unchanged.
- Exceptions from bleak and bleak-retry-connector propagate unchanged and may
  contain the device address. The `__cause__` of `ConnectionSlotsExhaustedError`
  keeps the original text.
- Library exception text no longer embeds raw frame bytes (which can carry the
  assetID, the serial, or an HMAC of the assetID); it gives the frame length and
  header only. The connection name passed to `bleak-retry-connector` is a fixed
  `"iCOMM water heater"` instead of the advertised name, the address is gone
  from the device-not-found message, and `ConnectionSlotsExhaustedError` has a
  fixed message with the original error chained as its cause. The
  `ValueError` from `pairing_code_from_name` no longer echoes the name.

## 0.1.0

- `connect()` after a link lost under the client now closes the dead link
  before opening a new one. Without this the heater rejected the new session
  (hardware-observed), so a reused client could not reconnect after an
  unexpected drop.
- `AOSmithBLEClient` takes three optional keyword-only hooks for embedding in a
  long-running application: `client_class` (the bleak client class to connect
  with), `device_resolver` (a callback returning the freshest `BLEDevice`, used
  on every connect and every connection retry), and `on_disconnect` (a callback
  for unexpected link loss). All default to the previous behavior.
- `bleak-retry-connector` is now imported unconditionally; the unreachable
  fallback to a bare `BleakClient` is gone.
- `HeaterState` is removed. `AOSmithBLEClient.async_get_state()` now returns a
  `FeatureSet` (`Mapping[FieldName, Feature]`) -- a `Feature` per profile
  field graded at least `min_trust` (default `Trust.OK`), each carrying its
  own `value`, `trust`, and `writable`. A field graded below `min_trust` is
  absent from the mapping, never present with a placeholder.
- `FieldName` (a `StrEnum`) and `FieldScope` (`STATE`/`IDENTITY`) replace bare
  string field names and the implicit assumption that every field lives in
  Block 11.
- `DeviceInfo.serial` is now populated, once, at connect time.
- New `AOSmithBLEClient.async_diagnose()`: an independent connect/probe/
  disconnect sequence that works even for a device `connect()` would refuse
  outright, producing a `DiagnosticReport` with the existing `to_markdown()`
  plus a new `to_fixture_entries()` -- redacted, `tests/fixtures/frames.json`-
  shaped output suitable for a new-profile contribution PR.
- `Profile`/`FieldSpec`/`Match` device-profile system, with `__post_init__` structural
  validation and inheritance (write trust demoted unless re-asserted).
- One bundled profile (`hpts50-6.3`).
- The connecting, writing async client (`AOSmithBLEClient`): session establishment,
  profile matching, MTU and UNITS validation, state reads, and a single profile-gated
  write choke point with fault-active read-only gating and write-then-read-back
  verification.
- Release-on-demand and `BleakOutOfConnectionSlotsError` wrapping.
- Presence probing and the unknown-device diagnostic report.
- Distinguishes the two 7-byte short-response forms (`ReadRefusedError` vs.
  `SessionError`) that the 0.0.1 release's `parse_read` treated identically.

## 0.0.1 - Unreleased

- Initial protocol layer: frame construction/parsing, CRC-8, the session
  handshake (pairing-slot init, challenge/response), setpoint and mode
  codecs, fault code table.
- No Bluetooth I/O in this release; frame building and parsing only.
