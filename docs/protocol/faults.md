# Fault codes

## Where the code lives

The current fault code is Block 2, parameter 7 (`CURRENT_FAULT_ERROR_CODE`), a 2-byte word. `0x0000` means no active fault. Codes are decimal, not hex.

```text
TX  BD A0 07 02 07 01 66
RX  DB 02 09 02 07 00 00 80 9C     -> code 0x0000, healthy
```

The read and healthy response are **verified on hardware**. Non-zero codes are **from the handbook** or **unverified**: no fault has been induced.

## Code table

Codes and titles are the manufacturer's (**unverified**).

| Code | Fault (manufacturer's title)       |
| ---- | ---------------------------------- |
| 1    | Dry Fire                           |
| 2    | High Water Temperature             |
| 3    | Upper Thermistor Sensor Failure    |
| 4    | Lower Thermistor Sensor Failure    |
| 6    | Internal Processor Error           |
| 9    | Power Supply Voltage Error         |
| 21   | Upper Element Circuit Failure      |
| 22   | Lower Element Circuit Failure      |
| 25   | Heat Pump Sensor Error             |
| 26   | Heat Pump Sensor Error             |
| 27   | Heat Pump Sensor Error             |
| 28   | Ambient Temperature Sensor Failure |
| 31   | Water Leak                         |
| 44   | Anode is Depleted                  |
| 46   | Water Shut-off Valve Error         |
| 80   | Air Filter is Dirty                |
| 81   | Condensate Management Error        |
| 83   | Compressor Low Pressure            |
| 84   | Compressor Error                   |
| 85   | High Discharge Temperature         |
| 86   | Fan Error                          |
| 101  | Upper Thermostat Error             |
| 102  | Lower Thermostat Error             |

Codes 25, 26 and 27 share the title "Heat Pump Sensor Error" in the table above. The Service Handbook names them individually (**from the handbook**): 25 is the coil temperature sensor, 26 the suction temperature sensor, 27 the discharge temperature sensor.

## Reconciliation with the handbook

The code table and the manuals disagree:

| Code        | Source        | Note                                                                                                      |
| ----------- | ------------- | --------------------------------------------------------------------------------------------------------- |
| 29          | handbook only | Outlet temperature sensor (MAX, Premium and 120V models)                                                  |
| 47          | handbook only | Smart Valve failure (MAX, Premium and 120V models)                                                        |
| 48          | handbook only | Battery low (BR2032), applies to all models                                                               |
| 2, 101, 102 | table only    | Absent from every manual; likely BLE or internal only (**unverified**)                                    |
| 44          | retracted     | Addendum `100392298` states that error 044 (SAC anode depleted) "is no longer applicable to this water heater" |

The handbook also maps faults to limp modes (**from the handbook**): 3 and 21 -> Limp Mode 1, 4 and 22 -> Limp Mode 2, and 9, 25, 26, 27, 28, 81, 83, 84, 85, 86 -> Limp Mode 3 (elements only).

## Undecoded fault fields

Two other fault-related fields exist and are not decoded: `FAULT_FLAGS` (Block 13 param 11) and `MODULE_FAULT_FLAGS` (Block 26 param 38). Both look like bitfields, not enumerated codes (**unverified**).

## No CTA-2045 module

**Verified on hardware.** On the test unit a Block 13 read is refused every cycle with the 7-byte `0x40` stub, at any start offset tried, including words 4 to 11, so it is not a wrong-offset problem. A Block 26 read is accepted but every word reads back zero with no change over several hours, including through hot water draws, for both a full dump and words 35 to 38.

**Verified on hardware (physical inspection):** the unit has a CTA-2045 port and it is not populated. Block 13 (remote control) and the populated part of Block 26 (SSID, `WIFI_RSSI_BARS`, `CTA_UCM_PRESENT`, the OADR power counters) are believed to serve that optional module (**unverified**, none installed to test). Without one, Block 13 is refused and Block 26's leak and module fields read a permanent zero (**verified on hardware**).
