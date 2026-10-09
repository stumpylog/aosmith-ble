# Changelog

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
