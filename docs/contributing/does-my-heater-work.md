# Does my heater work?

`connect()` refuses any heater without a verified profile, because the library writes to a real appliance and the firmware is not trusted to validate input. The one bundled profile is `hpts50-6.3` ([tested devices](../tested-devices.md)).

If your heater is refused, you can still help. `async_diagnose()` is a separate, explicit, read-only call that connects, probes and disconnects on its own, and produces a report you can paste into an issue.

## What it does and does not do

- It reads only, and never writes.
- It asks each block id from 0 to 40 for a single word starting at offset 0, with a short
  pause between reads, to record which blocks answer.
- It reads the identity block to record the model bytes and firmware.
- It disconnects when finished, whether or not anything matched.

## Run it

Press the Bluetooth button on the control panel once first, so the heater hands out the session value the library needs ([Handshake](../protocol/handshake.md#the-assetid)). Close the official app and any other client first, since only one can connect.

```python
import asyncio

from aosmith_ble import AOSmithBLEClient, async_discover, pairing_code_from_name


async def main() -> None:
    device = (await async_discover())[0]
    client = AOSmithBLEClient(device, pairing_code=pairing_code_from_name(device.name))
    report = await client.async_diagnose()
    print(report.to_markdown())  # redacted by default


asyncio.run(main())
```

`to_markdown()` redacts the session value, serial, Bluetooth address and any Wi-Fi name
by default. Do not pass `redact=False` when posting publicly.

## File a report

Open a "Device support request" issue and paste the report. Before you
post, check it contains none of these:

- your heater's Bluetooth address
- the 18-character session value (it starts `02iQk`)
- the full serial number from the rating plate or the advertised name's last digits

To contribute fixtures, use `report.to_fixture_entries()` (redacted frames shaped like `tests/fixtures/frames.json`), never raw captures. Why: [Test vectors](../development/test-vectors.md).

## What happens next

A maintainer compares your block presence and model bytes with the [block map](../protocol/blocks.md) and the evidence rules in [Research](../research/index.md). A report does not promise support for any model. A new profile starts read-only, and write support is added only after an observed write exists for that exact model and firmware.
