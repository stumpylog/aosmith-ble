# Block 11: control

Block 11 (`0x0B`) is the primary control block. Every mode and setpoint change seen in the official app's captures used it. Parameters are 2-byte big-endian words, see [Blocks](blocks.md#addressing-parameters-are-2-byte-words).

## Parameters

Parameter names are the manufacturer's labels.

| Param | Name                           | Notes                                                            |
| ----- | ------------------------------ | ---------------------------------------------------------------- |
| 0     | `OPERATING_SETPOINT`           | `celsius * 256`, big-endian. Read and written.                   |
| 6     | `REMOTE_OPERATING_SETPOINT`    | 0 when unset                                                     |
| 15    | `OPERATION_MODE`               | `duration_days * 256 + mode_enum`. Read and written.             |
| 17    | `VACATION_MODE_REMAINING_DAYS` | holds the set days while Vacation is active, kept after a cancel |
| 18    | `GUEST_MODE_REMAINING_DAYS`    | countdown, not retested for Guest                                |
| 19    | `ELECTRIC_MODE_REMAINING_DAYS` | countdown, verified on hardware, see below                       |
| 20    | `HOT_WATER_PLUS_LEVEL`         | not returned on firmware 6.3 (the read wraps), see [Commands](commands.md#read-semantics) |

Params 17-19 are separate remaining-day counters. The official app never requests them (it reads only params 0-15); the `0x0000` readings come from 20-word reads made outside the app.

## Setpoint encoding

The setpoint is a 16-bit big-endian value holding Celsius times 256 (**verified on hardware**, confirmed by read-back after writes):

```text
word    = round(celsius * 256), as 2 bytes, big-endian
celsius = word / 256
celsius = (fahrenheit - 32) / 1.8
```

Example conversions:

| Fahrenheit | Celsius | High byte | Low byte | Hex     |
| ---------- | ------- | --------- | -------- | ------- |
| 114        | 45.56   | `0x2D`    | `0x8E`   | `2D 8E` |
| 120        | 48.89   | `0x30`    | `0xE4`   | `30 E4` |
| 124        | 51.11   | `0x33`    | `0x1C`   | `33 1C` |

Decoding is approximate at 1/256 resolution (`30 E4` decodes to 120.003 F), so round for display.

### Temperature limits

The handbook range and default are in [Operating limits](../hardware/operating-limits.md). The highest setpoint write in the official app captures is 126 F. `PRODUCT_MAX_TEMPERATURE` and `PRODUCT_MIN_TEMPERATURE` (Block 27 params 49 and 50) would give the device's own limits but are refused on this unit.

## Mode encoding

A mode write sends two data bytes for param 15: `[duration_days] [mode_enum]`. The read-back word is `(duration_days << 8) | mode_enum`, so writing `0F 01 01` (ELECTRIC, 1 day) reads back `0x0101` and `0F 00 04` (HYBRID, permanent) reads back `0x0004` (**verified on hardware** and against frames captured from the official app).

| Mode      | Enum | Duration byte        | Example command (with CRC)         |
| --------- | ---- | -------------------- | ---------------------------------- |
| ELECTRIC  | 1    | days, non-zero       | `BD 40 08 0B 0F 01 01 FE` (1 day)  |
| VACATION  | 2    | days, non-zero       | `BD 40 08 0B 0F 02 02 F4` (2 days) |
| GUEST     | 3    | days, non-zero       | not seen in captures               |
| HYBRID    | 4    | `0x00` (permanent)   | `BD 40 08 0B 0F 00 04 14`          |
| HEAT_PUMP | 5    | `0x00` (permanent)   | `BD 40 08 0B 0F 00 05 4A`          |

The duration is days. Other observed Electric frames: 2 days `BD 40 08 0B 0F 02 01 16`, 3 days `BD 40 08 0B 0F 03 01 84`, 5 days `BD 40 08 0B 0F 05 01 0A`. Frame layout and the write acknowledgement: [Commands](commands.md).

!!! warning "Timed-mode writes are stateful"
    ELECTRIC, VACATION and GUEST start a countdown that reverts the heater to the prior permanent mode. They change persistent device state.

## Status response layout

Reading Block 11 params 0 to 15 returns a 39-byte frame (indices are positions in the whole response):

```text
DB 02 27 0B 00 <setpoint hi> <setpoint lo> <const> <7 bytes> <20 bytes zero> <dur> <mode> 80 <crc>
```

| Index   | Size | Field                | Notes                                                              |
| ------- | ---- | -------------------- | ------------------------------------------------------------------ |
| 0-2     | 3    | header               | `DB 02 27`: header `DB`, type `02`, length `0x27` (39)             |
| 3       | 1    | block id             | `0x0B`                                                             |
| 4       | 1    | start parameter      | usually `0x00`                                                     |
| 5-6     | 2    | setpoint             | param 0, Celsius times 256, big-endian                             |
| 7       | 1    | unknown constant     | `0x05` in every capture                                            |
| 8-14    | 7    | undecoded "sensor"   | constant in every capture and live run, see below                  |
| 15-34   | 20   | zeros                | zero in captures; params 9 and 14 (offsets 23-24 and 33-34) read `0x0004` in some live runs, meaning unverified, see [open questions](../research/open-questions.md) |
| 35      | 1    | duration             | high byte of param 15, days, 0 = permanent                         |
| 36      | 1    | mode                 | low byte of param 15, enum 1-5                                     |
| 37      | 1    | status               | `0x80` = OK                                                        |
| 38      | 1    | CRC                  | CRC-8, see [CRC](crc.md)                                           |

The constant at `[7]` and the 7 bytes at `[8..14]` straddle word boundaries, so as word params they smear across params 1-4; split them into bytes to recover the raw layout. Param 1's high byte is `0x05`, matching `[7]` (**verified on hardware**).

## Timed-mode countdown

**Verified on hardware.** `ELECTRIC_MODE_REMAINING_DAYS` (p19) counts down over BLE on a fixed daily wall-clock tick, not from the moment of setting. When p19 reaches 0 the mode word flips to the prior permanent mode (HYBRID) in the same read. Use "the count reaches zero" as the revert signal. VACATION (p17) holds the set day count while Vacation is active (**verified on hardware**) and keeps that value after an early switch to another mode, so read it only while the mode matches; its decrement was not observed. GUEST (p18) was not retested. Run log and the handbook's 9-hour Vacation claim: [timed modes experiment](../research/timed-modes-experiment.md).

## Unnamed parameters 1-5 and 7-14

No meaning is known. Read as `/256` temperatures, params 1-4 look plausible but too low for a tank (**unverified**):

```text
param 1 = 0x058E (42 F)   param 2 = 0x02C7 (37 F)
param 3 = 0x08E4 (48 F)   param 4 = 0x01AB (35 F)
```

The raw bytes at response offsets `[7..14]` were `05 8E 02 C7 08 E4 01 AB` on every real sample in two long runs (**verified on hardware** as an observation, interpretation **unverified**):

- Run 1: 5527 samples over 2.6 days, spanning showers and appliance draws, almost entirely in ELECTRIC mode (compressor forced off, so inconclusive for heat-pump telemetry).
- Run 2: 2133 samples at 30 second intervals over about 19 hours in HYBRID mode with the compressor audibly running, setpoint 124 F. The bytes stayed byte-identical; the only anomalies were 38 empty rows from read dropouts.

They are probably not live coil, suction or discharge temperatures on this read path. Next step: correlate against compressor on/off times, or look in Blocks 8 and 28. See [open questions](../research/open-questions.md).
