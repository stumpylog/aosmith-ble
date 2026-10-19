# Hot water availability

Block 27 param 23 behaves like a hot water availability level (**partly verified on hardware**):

- It read 5 after morning showers and rose to 10 partway through the reheat, while the compressor was still running. It stayed 10 when the compressor stopped.
- It stayed 10 through a hot tap draw big enough to start the compressor, so it changes in coarse steps.
- It has not been observed falling.

A third-party report names the values 0, 5 and 10 Low, Medium and High (**from a third-party report**). See [Blocks](../protocol/blocks.md#block-27).

The official app issues only two read commands over BLE in every capture: Block 11 params 0-15 and Block 2 param 7. It never reads this field, so the app's own hot water availability screen probably comes from somewhere else, for example the cloud (**unverified**).

`HOT_WATER_PLUS_LEVEL` is a mode overlay setting, not a gauge ([reference](../protocol/reference.md)).

Tank temperature is not exposed over BLE, as far as any evidence shows: no block dumped from the test unit holds a plausible tank temperature, and no manual mentions one being reported. Related open leads are tracked in [open questions](../research/open-questions.md).
