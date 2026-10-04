# CRC-8

Every frame ends with a one-byte CRC-8. It is **verified on hardware**.

## Definition

| Property   | Value                                                      |
| ---------- | ---------------------------------------------------------- |
| Width      | 8 bits                                                     |
| Polynomial | `0x5E`                                                     |
| Init       | `0x00`                                                     |
| Bit order  | MSB-first, no reflection, no final XOR                     |
| Input      | The whole message, header through data, excluding the CRC  |

The CRC was checked against every captured frame in both directions, including frames the device rejects, so CRC is not the cause of any rejection (**verified on hardware**).

## Algorithm

Start with a running value of `0x00`. For each byte of the message in order: XOR the byte into the running value, then repeat 8 times: if the top bit of the running value is set, shift it left one bit and XOR with `0x5E`, otherwise just shift it left one bit (keeping 8 bits). The final running value is the CRC.

To build a frame, append the CRC of the frame so far. To validate a received frame, compute the CRC over every byte except the last and compare it with the last byte.

## Verification examples

The algorithm above reproduces each of these:

| Message            | Hex                    | CRC  |
| ------------------ | ---------------------- | ---- |
| Init command       | `BD F2 05 01`          | 0xD8 |
| Challenge request  | `BD F4 04`             | 0x12 |
| Set temp 120F      | `BD 40 08 0B 00 30 E4` | 0x6E |
| Set mode HEAT_PUMP | `BD 40 08 0B 0F 00 05` | 0x4A |

Worked example with an HMAC frame: [Handshake](handshake.md#worked-example-synthetic-vector).
