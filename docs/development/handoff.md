# Roadmap

What is still open. Read `README.md` and `CHANGELOG.md` for what the library does today and [Design principles](design-principles.md) for why.

## Smaller library items

| Item | Detail |
| --- | --- |
| `Profile.__post_init__` message ("unless this profile is only ever used as a parent via `inherits`") promises a case that later fails in `resolve_inherits` | Fix the wording, or add an `abstract` flag. |
| Every bundled profile is directly matchable, including future parents | `match_profile` iterates all profiles with a `match`. Harmless with one profile; needs an `abstract` concept before a second is added via `inherits`. |
| `CODEC_REGISTRY` is a plain mutable `dict` | Wrap in `types.MappingProxyType`. |
| `duration_days` type checking | The codec range-checks but does not type-check, so `1.5` raises `TypeError` instead of `ValidationError`, and `bool` is accepted as `0` or `1`. Neither reaches the wire. |
| `assert self._profile is not None` in the write path | In both write methods and in session and read helpers. Stripped under `python -O`; use an explicit `if ... raise`. |
| The link-opening step (`_open_link`) catches `ImportError` around the whole `establish_connection` call | Narrow the `try` to the `from bleak_retry_connector import ...` line. |
| `protocol.set_setpoint_request` and `set_mode_request` are public but unused by the client | Only tests use them (to build expected frames), `set_setpoint_request` has no ceiling check, and neither is re-exported at top level. Keep as documented low-level helpers or move out of the public surface. |
| `pyproject.toml` pins `bleak>=0.21` with no upper bound | Consider `bleak>=0.21,<4`. |

## Home Assistant integration

Needs a specification first: domain `aosmith_ble`, entity table, operation-mode mapping, config flow, coordinator, error and repair handling, diagnostics redaction. Not started. It belongs in its own repository (`ha-aosmith-ble`, via HACS). The diagnostics-only mode for unmatched devices can build on `async_diagnose()`.

## Lower priority

- **Stale days-remaining counters.** The Vacation counter keeps its last value after an early switch to another mode (hardware-observed), so `vacation_days_remaining` can read 5 in Hybrid. Decide whether the library should report 0 or hide a counter unless its mode is active.

- **Publish to PyPI.** The package builds, but nothing has been uploaded. Do it deliberately, when someone wants it installable from an index.
- **Fingerprint-based matching.** The third matching outcome: fingerprint matches but firmware differs, so inherit addressing and demote to read-only. Blocked on a block-length detection tool that does not exist yet. Do not start before the Home Assistant integration.
- **GUEST mode.** No profile may add mode 3 to `writable_modes` until an observed write exists ([Open questions](../research/open-questions.md)).
- **Current tank temperature and hot-water availability.** Open leads ([Hot water availability](../hardware/hot-water-availability.md)). The official app reads neither over BLE. The [panel experiment](../hardware/maintenance-display.md) could extend to tank temperature, otherwise a new empirical approach is needed.

See also [Open questions](../research/open-questions.md).
