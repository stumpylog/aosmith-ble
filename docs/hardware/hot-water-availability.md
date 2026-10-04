# Hot water availability

Hot water availability is not exposed over BLE, as far as any evidence shows:

1. The official app issues only two read commands over BLE in every capture: Block 11 params 0-15 and Block 2 param 7. It never reads a hot-water field.
2. No block dumped from the test unit contains a plausible level, percentage or gallons-remaining value.
3. No manual mentions available hot water, gallons remaining or a hot-water gauge.

`HOT_WATER_PLUS_LEVEL` is a mode overlay setting, not a gauge ([reference](../protocol/reference.md)). The app's "Hot Water Availability" screen is probably computed outside the heater, for example in the cloud (**unverified** inference from the three observations above). There is no HIGH/MEDIUM/LOW status field over BLE.

Related open leads are tracked in [open questions](../research/open-questions.md).
