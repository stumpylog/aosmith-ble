# Methodology

## How the protocol was studied

- **Captures of the official app's Bluetooth traffic.** Android HCI snoop logs show what the phone did; an nRF52840 sniffer shows what goes over the air ([captures](captures.md)).
- **Reads from the heater itself.** Read-only requests against a real unit, used to map blocks, parameters and fault codes.
- **The manufacturer's manuals and patents**, listed by number in [sources](sources.md).
- **Checking constructions against captured sessions.** Frames and responses are compared byte for byte with the official app's. The `0xF1` response was checked against five captured sessions (**verified on hardware**, [handshake](../protocol/handshake.md)).
