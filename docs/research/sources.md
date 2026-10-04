# Sources

Pointers only. Manuals are copyrighted and are not stored here. Search the A. O. Smith literature library or Google Patents by number.

## App

- The vendor's iCOMM Connectivity app (user-facing, used to generate captures of its Bluetooth traffic).

## Manuals

| Number | Document |
| --- | --- |
| `2000620230` | Service Handbook. Source for the maintenance display, operating limits, fault codes and mode behavior. |
| `100379659` | Installation Instructions and Use & Care Guide, Hybrid Electric Heat Pump Water Heater |
| `100392298` | Addendum to the installation instructions and Use & Care Guide (retires error code 044, the anode fault) |

The part number `100350404` and model `HPTS-50` identify the model tested.

## Patents

- US7346274, Water heater and method of controlling the same
- US7798107, Temperature control system for a water heater
- US8977791, Modular control system and method for a water heater

## Cloud API reference

- [py-aosmith](https://github.com/bdr99/py-aosmith) is an independent async client for the iCOMM cloud GraphQL API. It has no license file, so it is a reference only and no code is copied. We make no BLE support claim for the models its README lists.
- Cross-checks against the BLE findings (supporting evidence only, not hardware verification):
    - Its mode names match ours: ELECTRIC, GUEST, HEAT_PUMP, HYBRID, VACATION. STANDARD and EFFICIENCY appear for other families.
    - Each mode carries a controls hint, SELECT_DAYS or HOT_WATER_PLUS. This is consistent with timed modes taking a day count and with Hot Water Plus being an overlay.
    - The cloud reports `hotWaterStatus` (LOW, MEDIUM, HIGH or a number). This is consistent with availability being computed in the cloud, see [hot water availability](../hardware/hot-water-availability.md).
    - It also exposes `temperatureSetpointMaximum`, `temperatureSetpointPrevious` and pending flags. See the [open questions](open-questions.md).
