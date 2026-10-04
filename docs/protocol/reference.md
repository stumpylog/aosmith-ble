# Quick reference

Lookup tables; details are on the linked pages.

## Operating modes

| Value | Mode      | Notes                                                       |
| ----- | --------- | ----------------------------------------------------------- |
| 1     | ELECTRIC  | resistance elements only; timed, needs a non-zero duration in days |
| 2     | VACATION  | energy-saving away mode; timed, needs a non-zero duration in days |
| 3     | GUEST     | high-demand mode; timed, days; never observed written       |
| 4     | HYBRID    | heat pump with element backup; permanent, duration 0        |
| 5     | HEAT_PUMP | heat pump only; permanent, duration 0                       |

The one-line descriptions are **unverified**. GUEST has never been observed written.

The mode word (Block 11 param 15) is `(duration_days << 8) | mode`. See [Block 11](block-11.md#mode-encoding).

## Hot Water Plus

| Value | Name             |
| ----- | ---------------- |
| 0     | NORMAL_OPERATION |
| 1     | MORE_HOT_WATER   |
| 2     | MORE_SAVINGS     |
| 3     | MOST_SAVINGS     |

The values are **unverified**. It overlays Hybrid, Heat Pump or Electric and is read from Block 11 param 20, which firmware 6.3 does not return ([Commands](commands.md#read-semantics)). It is not a hot water gauge ([Hot water availability](../hardware/hot-water-availability.md)).

## Temperature encoding

Block 11 temperatures are 16-bit big-endian words holding Celsius times 256:

```text
word    = round(celsius * 256), as 2 bytes, big-endian
celsius = word / 256
example: 120 F = 48.89 C -> word 0x30E4
```

More examples: [Block 11](block-11.md#setpoint-encoding).

## Command quick reference

All frames start with `0xBD` and end with a CRC-8 byte, see [Commands](commands.md) and [CRC](crc.md).

| Action                | Command hex               |
| --------------------- | ------------------------- |
| Init                  | `BD F2 05 01 D8`          |
| Query (challenge)     | `BD F4 04 12`             |
| Read Block 11         | `BD A0 07 0B 00 10 F4`    |
| Set 120 F             | `BD 40 08 0B 00 30 E4 6E` |
| Mode ELECTRIC (1 day) | `BD 40 08 0B 0F 01 01 FE` |
| Mode HYBRID           | `BD 40 08 0B 0F 00 04 14` |
| Mode HEAT_PUMP        | `BD 40 08 0B 0F 00 05 4A` |

The session must be authenticated first ([Handshake](handshake.md)).
