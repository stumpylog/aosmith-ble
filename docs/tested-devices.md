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

Setpoint writes: 95 to 130 F. Writable modes: HYBRID, HEAT_PUMP, ELECTRIC, VACATION.

Grades: `ok` was observed working on the heater, `partial` was observed but only checks itself, `unverified` is plausible but was never exercised, `-` is not supported.

What else is known:

- **Countdowns.** All three days-remaining reads work. The ELECTRIC countdown was observed decrementing. The VACATION counter was observed holding its set value while Vacation was active, and it keeps that value after an early cancel, so read it only while the mode matches. GUEST was never observed ([experiment](research/timed-modes-experiment.md)).
- **Setpoint.** The library caps writes at 130 F by default and never above 140 F. The handbook range is 95 to 150 F ([operating limits](hardware/operating-limits.md)).
- **GUEST mode.** No write has ever been observed, so it is not writable.
- **Faults.** The healthy response is verified. Non-zero codes have not been induced ([faults](protocol/faults.md)).
- **Not available over BLE.** Current tank temperature and hot water availability ([hot water availability](hardware/hot-water-availability.md)).
