# Blocks and parameters

The heater's state lives in numbered blocks. A client reads a block with a read command (see [Commands](commands.md)) and decodes the 2-byte words. Block 11 has its own page: [Block 11](block-11.md).

Parameter names are the manufacturer's labels. An index with no name here has no known name; it is not nonexistent.

## Addressing: parameters are 2-byte words

A block payload is a sequence of 2-byte words, and every parameter index indexes that word array (**verified on hardware**, matches captures):

```text
parameter N  =  payload[2N], payload[2N+1]      (big-endian uint16)
payload      =  response[5 .. len-3]            (after the 5-byte header, before status+CRC)
```

In a Block 11 response `DB 02 <len> 0B 00 <payload...> <status> <crc>`:

```text
param 0  = bytes [5..6]     OPERATING_SETPOINT
param 15 = bytes [35..36]   OPERATION_MODE
```

Temperatures are `word / 256` degrees Celsius (**verified on hardware** for the Block 11 setpoint, [Block 11](block-11.md#setpoint-encoding)).

## Strings are word-swapped

ASCII inside a block is byte-swapped within each 16-bit word. Swap each pair before decoding. For example the model string `HPTS-50` followed by a NUL arrives as the byte pairs `PH ST 5- NUL0`, which swaps back to `HP TS -5 0NUL`.

Block 0 holds the identity strings (**verified on hardware**, against a live Block 0 read after a button-pressed pairing):

```text
Block 0, params 16-19   -> deswaps to "HPTS-50\x00"   (model, matches the rating plate)
Block 0, params 20+     -> deswaps to "<9-digit serial suffix>100350404", then repeats
                           (the first 9 digits are the last 9 digits of the plate serial,
                            "100350404" is the plate item/part number, exact match)
```

So the model, part number and part of the serial are readable over BLE; the assetID is not ([The assetID](handshake.md#the-assetid)).

## Block map

Enumerated by reading `start=0, count=1` for every block ID 0 to 40 and fully paging each block that answered (**verified on hardware**, one unit, reads only, nothing written):

| Block           | Present | Content                                                                                       |
| --------------- | ------- | --------------------------------------------------------------------------------------------- |
| 0               | yes     | Model, serial suffix and part number as byte-swapped ASCII (`HPTS-50`, serial suffix, `100350404`) |
| 1               | yes     | Identity strings, mostly ASCII digits; contains a setpoint copy                               |
| 2               | yes     | Fault code at param 7; setpoint copies at params 2, 3, 16, 17                                 |
| 3               | yes     | Nameplate. No parameter names known, see below                                                 |
| 11              | yes     | Control block: setpoint, mode, durations. See [Block 11](block-11.md)                         |
| 21-26           | yes     | All zeros. The Wi-Fi module was never provisioned and no CTA-2045 module is installed, see [Faults](faults.md#no-cta-2045-module) |
| 27              | yes     | 26 words, sparse; the SSID range (words 28 and up) is refused on this unit                    |
| 28              | yes     | 112 words; ASCII part/model code                                                              |
| all others 0-40 | no      | `0x40` refusal stub                                                                           |

## Block 3 is the nameplate

Cross-checked against the unit's rating plate (**verified on hardware**):

| Param | Value           | Rating plate                    |
| ----- | --------------- | ------------------------------- |
| 1, 7  | `0x0032` = 50   | TANK NOMINAL CAPACITY 50 US GAL |
| 3     | `0x1194` = 4500 | ELEMENT WATTS 4500              |
| 6     | `0x00F0` = 240  | VOLTS AC 208/240                |

## Two traps when reading blocks

**Reads cap at 20 words and pages wrap.** Blocks 2 and 11 repeat with period 20, so a read at param 20 returns the setpoint again ([Commands](commands.md#read-semantics)).

**Values that look like temperatures are often ASCII.** `0x30` to `0x36` are the digits `0` to `6`. Block 1's `0x3431 0x3335 0x3630 0x3633` is not `125.9F 124.2F 129.5F 129.6F` but the characters `"41" "35" "60" "63"` from the serial number. Check the ASCII reading first.

## Parameter tables

Blocks 0 and 3 hold identity and nameplate data with no known parameter names (see above). Block 11 is on [Block 11](block-11.md).

### Block 1

| Param | Name           |
| ----- | -------------- |
| 43    | `MAX_SETPOINT` |

(**Unverified**.) The block is mostly ASCII identity digits on this unit, so decode with care.

### Block 2

| Param | Name                       |
| ----- | -------------------------- |
| 7     | `CURRENT_FAULT_ERROR_CODE` |

Read and healthy response: [Faults](faults.md#where-the-code-lives). `0x0000` means no active fault.

### Block 8

| Param | Name                    |
| ----- | ----------------------- |
| 2     | `CONTROLLING_SET_POINT` |

**Unverified**, not decoded on hardware.

### Block 13

| Param | Name              |
| ----- | ----------------- |
| 0     | `ONLINE`          |
| 2     | `REMOTE_SETPOINT` |
| 3     | `REMOTE_MODE`     |
| 4     | `MAX_SETPOINT`    |
| 9     | `REMOTE_ENABLE`   |
| 11    | `FAULT_FLAGS`     |

**Unverified.** Block 13 is refused on the test unit (no CTA-2045 module), see [Faults](faults.md#no-cta-2045-module).

### Block 26

| Param | Name                                         |
| ----- | -------------------------------------------- |
| 0     | `MODE`                                       |
| 1     | `SETPOINT`                                   |
| 2     | `UNITS`                                      |
| 3     | `REAL_TIME_LW`                               |
| 4     | `REAL_TIME_HW`                               |
| 5     | `BLUETOOTH_CONNECTION_STATUS`                |
| 6     | `WIFI_CONNECTION_STATUS`                     |
| 13    | `OADR_OVERRIDE_STATUS`                       |
| 17-19 | `OADR_ELECTRIC_POWER_USAGE_CUMULATIVE_2/1/0` |
| 31    | `WIFI_CONNECTION_DETAILS`                    |
| 32    | `WIFI_RSSI_BARS`                             |
| 35    | `SET_WATER_SENSOR`                           |
| 36    | `WATER_SENSOR_STATUS`                        |
| 37    | `WATER_AVAILABLE`                            |
| 38    | `MODULE_FAULT_FLAGS`                         |

**Unverified.** `REAL_TIME_LW` and `REAL_TIME_HW` are the low and high words of the clock value. The three `OADR_ELECTRIC_POWER_USAGE_CUMULATIVE_*` words are the cumulative power counter.

Field notes:

- `UNITS`: 0 = Fahrenheit, 1 = Celsius (**unverified**, since every word reads zero on this unit).
- `SET_WATER_SENSOR` is the leak detection enable, and `WATER_SENSOR_STATUS` is the leak sensor status (**unverified**).
- Bit 0 of `MODULE_FAULT_FLAGS` indicates a leak (**unverified**, not seen on hardware since every word reads zero).

### Block 27

| Param | Name                                                        |
| ----- | ----------------------------------------------------------- |
| 0     | `SOFTWARE_VERSION_HOST_MCU`                                 |
| 3     | `OADR_OVERRIDE_STATUS`                                      |
| 7-9   | `OADR_ELECTRIC_POWER_USAGE_2/1/0`                           |
| 10-12 | `OADR_GRID_PRESENT_ENERGY_LEVEL_2/1/0`                      |
| 13-15 | `OADR_GRID_TOTAL_ENERGY_LEVEL_2/1/0`                        |
| 23    | `WATER_AVAILABLE`                                           |
| 25    | `CTA_UCM_PRESENT`                                           |
| 28-47 | `SSID` (words 28 to 47, ASCII)                              |
| 49    | `PRODUCT_MAX_TEMPERATURE`                                   |
| 50    | `PRODUCT_MIN_TEMPERATURE`                                   |
| 51    | `SET_ADVANCED_LOAD_UP_ENABLE`                               |
| 113   | `SET_TOU_USER_PREFERENCE`                                   |
| 114   | `PRICE_RATIO_LOWER_THRESHOLD`                               |
| 115   | `PRICE_RATIO_HIGHER_THRESHOLD`                              |
| 116   | `LOAD_UP_HOUR_BEFORE_SHED`                                  |
| 147   | `UTILITY_ENROLLMENT`                                        |

**Unverified**, except the firmware string `6.3` at param 0 (**verified on hardware**). Words 28 and up are refused on this unit, so `PRODUCT_MAX_TEMPERATURE` and `PRODUCT_MIN_TEMPERATURE` are unread.

### Block 28

| Param | Name                          |
| ----- | ----------------------------- |
| 13    | `SET_ADVANCED_LOAD_UP_ENABLE` |
| 109   | `UTILITY_ENROLLMENT`          |

**Unverified.** The block is 112 words and holds an ASCII part/model code on the test unit (**verified on hardware**).
