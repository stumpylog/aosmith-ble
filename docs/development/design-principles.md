# Design principles

1. **Audience.** Published for the community, aware of multiple models and firmware versions.
2. **No speculative writes, ever.** Confidence comes from read-side validation, limits from the verified profile, and frames from range-checked values. No public raw-write API, no blind write retries.
3. **Strict validation.** An unrecognized device is refused outright, and the refusal produces a complete diagnostic report suitable for pasting into an issue.
4. **One connection.** Hold a single connection open and poll. Surface the sleep timeout as a repair ("press the Bluetooth button") in the Home Assistant integration.
5. **Writes.** Setpoint, mode, and timed modes.
6. **Two packages.** `aosmith-ble` is the library. A separate Home Assistant integration (`ha-aosmith-ble`, distributed through HACS) builds on it.

## Compatibility table

Compatibility table: contributors run `async_diagnose()` on an unknown device, and `DiagnosticReport.to_fixture_entries()` plus `draft_profile_stanza` become the pull request artifact for a new bundled profile.

Frame formats: [Commands](../protocol/commands.md). Low-level frame builders exist for testing and cannot transmit; the [roadmap](handoff.md) tracks whether they stay public. None is a supported write API.
