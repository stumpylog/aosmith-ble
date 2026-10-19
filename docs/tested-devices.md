# Tested devices

The library only talks to a device it has a verified profile for. A device that does not match is refused, and [diagnostics](contributing/does-my-heater-work.md) can help add it. One profile is bundled.

## HPTS-50, firmware 6.3 (`hpts50-6.3`)

Tested on one unit. Matched on the model field in Block 0 and firmware 6.3.

| Field | Location | Read | Write |
| --- | --- | --- | --- |
| `setpoint` | block 11, param 0 | ok | ok |
| `mode` | block 11, param 15 | ok | ok |
| `fault` | block 2, param 7 | ok | - |
| `model` | block 0, param 16 | ok | - |
| `serial` | block 0, param 36 | partial | - |
| `vacation_days_remaining` | block 11, param 17 | ok | - |
| `guest_days_remaining` | block 11, param 18 | unverified | - |
| `electric_days_remaining` | block 11, param 19 | ok | - |
| `power_w` | block 27, param 6 | ok | - |
| `energy_wh` | block 27, param 7 | ok | - |
| `hot_water_availability` | block 27, param 23 | partial | - |

Setpoint writes: 95 to 130 F. Writable modes: HYBRID, HEAT_PUMP, ELECTRIC, VACATION.

Grades: `ok` was observed working on the heater, `partial` was observed but only checks itself, `unverified` is plausible but was never exercised, `-` is not supported.

What else is known:

- **Countdowns.** All three days-remaining reads work. The ELECTRIC countdown was observed decrementing. The VACATION counter was observed holding its set value while Vacation was active, and it keeps that value after an early cancel, so read it only while the mode matches. GUEST was never observed ([experiment](research/timed-modes-experiment.md)).
- **Setpoint.** The library caps writes at 130 F by default and never above 140 F. The handbook range is 95 to 150 F ([operating limits](hardware/operating-limits.md)).
- **GUEST mode.** No write has ever been observed, so it is not writable.
- **Faults.** The healthy response is verified. Non-zero codes have not been induced ([faults](protocol/faults.md)).
- **Power and energy.** Power read 356 W while the compressor ran and 0 within 30 seconds of it stopping. Energy rose 6 Wh a minute while it ran, which matches 356 W, and stopped with it. Neither has been checked against an external meter.
- **Hot water availability.** Graded `partial`: it rose from 5 to 10 partway through a reheat, but has not been observed falling during a draw. The Low, Medium and High names for 0, 5 and 10 come from a third-party report ([hot water availability](hardware/hot-water-availability.md)).
- **Not available over BLE.** Current tank temperature.
