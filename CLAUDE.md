# CLAUDE.md

Guidance for working in this repository.

## What this is

`aosmith-ble` is a Python library plus a documentation site for local Bluetooth LE
control of A.O. Smith iCOMM heat pump water heaters (no cloud). The library is in
`src/aosmith_ble/` (client, protocol, profiles, codecs, diagnostics). The protocol
knowledge and research record are in `docs/`, built with Zensical. Python only.

## Commands

```bash
uv sync
uv run pytest -q                  # the test suite, no hardware needed
uvx zensical serve                # live docs preview
uvx zensical build --clean --strict   # must pass with zero warnings
```

Use `uv`/`uvx` for all Python work, `rg` for searching, `fd` for finding files.

## Layout

- `src/aosmith_ble/protocol.py`, `crc.py`: frame building and parsing, CRC-8.
- `src/aosmith_ble/profiles/`: per-model field maps and trust grades.
- `src/aosmith_ble/client.py`: the connecting client. All writes go through one profile-gated path.
- `tests/`: unit tests with fixtures in `tests/fixtures/frames.json`.
- `docs/protocol/`, `docs/hardware/`, `docs/research/`, `docs/development/`: the site.
  The nav lives in `zensical.toml`; every page must be listed there.
- `docs/superpowers/`: working plans and specs, if present. Excluded from the published
  site by the exclude plugin in `zensical.toml`, so never link to it as a site page.

## Safety rules

- Research is read-only. Never send a write whose encoding is not proven (byte-for-byte match with a captured frame, or a verified round trip).
- No speculative writes, no raw-write API, no blind write retries.
- Never raise the setpoint casually. Writes are capped at 140F absolute and 130F by default; the handbook range is 95-150F.
- Timed-mode writes are stateful: the device counts days down and reverts at zero. The setpoint is a scalar, not per-mode.
- GUEST mode has never been observed written; do not add it to any profile's `writable_modes` until a write is observed.
- Exploratory reads at non-zero start offsets coincided with a change in Block 11 params 9 and 14 (causation unproven). Keep reads to what the app does.

## Hardware facts that cost time

- Only one central can connect at a time. Stop other clients first.
- A stale BlueZ connection blocks discovery (the heater stops advertising while connected): `bluetoothctl disconnect <mac>`.
- After about 10 minutes with no traffic the heater sleeps and needs a Bluetooth button
  press to wake.
- The central must answer the heater's ATT MTU request or no notifications arrive.
- The proprietary service UUID is not advertised. Discovery matches on the `iCOMM-*`
  local name.

## Docs rules

- Tag every protocol claim as verified on hardware, from the handbook, or unverified. Never upgrade confidence while moving text.
- Never put a real MAC, serial, assetID, pairing code or advertised name in docs,
  fixtures or tests. Use `AA:BB:CC:DD:EE:FF`, `iCOMM-AC000W037XXXXXX`,
  `02iQk000000EXAMPLE`, `XXXXXX`, `<plate serial>`. Part number `100350404` and model
  `HPTS-50` are model-level and fine.
- Test vectors are synthetic. See `docs/development/test-vectors.md` before changing
  `ASSET_ID` or `frames.json`.
- docs/research and docs/hardware are language-neutral: no code snippets or library
  references. State current facts only; no revision history or dates.
- Use `!!! warning` admonitions, not GitHub-style alerts, and relative links only.
