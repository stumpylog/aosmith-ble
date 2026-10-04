# aosmith-ble

Local Bluetooth LE control of A.O. Smith iCOMM heat pump water heaters -- no cloud
account, no vendor credentials, no internet connection involved. This project is
independent and unaffiliated with A.O. Smith.

Documentation: see the `docs/` folder or the project site.

Looking for the cloud API instead? See [py-aosmith](https://github.com/bdr99/py-aosmith).

## What this is

An async client that connects directly to a water heater's BLE interface, matches it against a bundled device profile, and reads or writes only what that profile has verified. An unrecognized device is refused outright. To help add support for a new device, call `AOSmithBLEClient.async_diagnose()`. It connects, probes and disconnects on its own (so it works even where `connect()` refuses) and returns a `DiagnosticReport`: `to_markdown()` gives a human-readable report and `to_fixture_entries()` gives redacted, fixture-shaped captures for a profile-contribution PR.

## Install

    pip install git+https://github.com/stumpylog/aosmith-ble

## Quickstart

```python
import asyncio
from aosmith_ble import AOSmithBLEClient, FieldName, Mode, async_discover, pairing_code_from_name

async def main():
    devices = await async_discover()
    device = devices[0]
    code = pairing_code_from_name(device.name)
    async with AOSmithBLEClient(device, pairing_code=code) as client:
        features = await client.async_get_state()
        setpoint = features[FieldName.SETPOINT].value
        mode = features[FieldName.MODE].value
        fault = features[FieldName.FAULT].value
        print(f"{setpoint}F, mode={Mode(mode.mode).name}, fault={fault.name}")
        await client.async_set_setpoint(124.0)

asyncio.run(main())
```

## Pairing

Press the Bluetooth button on the control panel once before first use. The device hands out the "assetID" it authenticates sessions against only while its pairing slot is populated. Cache `AOSmithBLEClient.asset_id` (for example with the device address) and pass it back as `asset_id=` so the button press is a one-time step.

## Safety model

Every write goes through one profile-gated path: setpoint and mode are checked against the profile's verified limits (never above 140F, 130F by default), a fault-active device is read-only, and every write is read back and compared before the call succeeds. The public API cannot write an arbitrary block or parameter.

## What this doesn't do (yet)

No current-tank-temperature reading (the manufacturer's app never reads it either). No Home Assistant integration; that is a separate, HACS-distributed package. No support for devices other than the bundled profile: `connect()` refuses an unmatched device. Diagnostics are an explicit, separate call, never part of the automatic connection flow.

## License

MIT. See `LICENSE`.
