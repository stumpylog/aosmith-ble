# Open questions

## Protocol

- **Block 11 params 1-5 and 7-14.** Meaning unknown; naming them needs empirical correlation (for example the [panel experiment](../hardware/maintenance-display.md)). Params 1-4 and the byte at offset 7 never changed in long runs ([Block 11](../protocol/block-11.md)).
- **Block 11 param 20 on firmware 6.3.** `HOT_WATER_PLUS_LEVEL` would be param 20, but a read there returns the setpoint. The buffer echo would explain that ([Commands](../protocol/commands.md#unbacked-words-echo-the-previous-read)); a start-20 read right after a read of another block would tell whether param 20 exists at all.
- **Block 27 contents.** Params 6, 7-9 and 23 are identified ([Blocks](../protocol/blocks.md#block-27)). Param 2 and the energy-level words 10-15 change with heating and mode, but their meanings are unconfirmed. Words 28 and up, including `SSID`, are refused on this unit.
- **Block 26.** Whether any firmware populates it (every word reads 0 on the test unit). Params 3 and 4 are believed to be the low and high words of the `REAL_TIME` clock (**unverified**), so the timestamp format is unknown.
- **Maximum setpoint from the cloud.** The cloud API's `temperatureSetpointMaximum` (see [sources](sources.md#cloud-api-reference)) is a lead for the device's own maximum, since Block 27 params 49 and 50 (`PRODUCT_MAX_TEMPERATURE` and `PRODUCT_MIN_TEMPERATURE`) are refused on this unit. **Unverified.**
- **Pairing slots.** Whether `BD F2 05 <n>` enumerates additional pairing slots for n > 1.
- **Re-pairing.** Whether the `F3`/`F0` re-pairing path is ever required for a fresh client. It writes persistent state and is deliberately not implemented.
- **Block 11 params 9 and 14.** Explained by the buffer echo for param 9 (**verified on hardware**) and very likely for param 14 ([Commands](../protocol/commands.md#unbacked-words-echo-the-previous-read)). The original observation: Both read `0x0000` throughout a 336-sample, 3-hour logger run, then `0x0004` afterwards, coinciding with exploratory reads at non-zero start offsets (causation unproven, possibly ordinary internal state). While ELECTRIC mode was active both also read `0x0004`, the HYBRID mode value. A health check right after showed setpoint 124.0F, HYBRID permanent and fault code 0, so no sign of harm. The hypothesis that they hold the revert target (the mode active before the timed mode) is **unverified**: the [timed-modes experiment](timed-modes-experiment.md) saw the revert to HYBRID but did not record these params.

## Device behavior

- **Hot water availability.** Block 27 param 23 rises during a reheat; whether it falls with draws, and the meaning of its values, is not yet confirmed. See [hot water availability](../hardware/hot-water-availability.md).
- **Tank temperature.** No known BLE field; the official app reads none. Leads: the [panel experiment](../hardware/maintenance-display.md) (planned, not run) and a fresh empirical approach.
- **GUEST mode.** Mode 3 has never been observed written by anything. It is not writable until an observed write exists.
- **VACATION countdown.** p17 holds the set days during Vacation (verified), but its decrement tick and the handbook's 9-hour revert were not observed.
- **Temperature control accuracy.** Not validated.
- **Suggested captures still of value:** Block 26 writes by the official app on different firmware, and the full Block 27 response from an app connection.
- **Low priority, not investigated:** OpenADR demand response parameters, utility program enrollment, load shedding, price signals, time-of-use configuration, leak detection sensor control, WiFi configuration over BLE, module fault flag decoding, and protocol differences across models.

## Project

Library, Home Assistant and publishing work: [roadmap](../development/handoff.md).
