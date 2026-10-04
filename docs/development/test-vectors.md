# Test vectors

The test vectors for the `0xF1` challenge response and the init response are synthetic. The HMAC vectors in `tests/test_protocol_session.py` and the `init_response_slot_populated` frame in `tests/fixtures/frames.json` are computed from a placeholder assetID (`02iQk000000EXAMPLE`, 18 characters like a real one). Tests use a dummy pairing code (`123456`).

## What that means

A real capture is an independent check: the official app produced those bytes, so a match proves the code builds the same response. A synthetic vector is computed with `hmac` and `hashlib` using the same construction as the code under test, so it catches regressions but not a wrong construction.

The construction is in [Handshake](../protocol/handshake.md).

## Supplying real vectors privately

For example from a capture of the official app, all from one device:

1. Take the 18-character ASCII assetID from the `0xF2` init response (`DB 2F 18 01 <assetID> 80 <crc>`).
2. For several sessions of that same device, take the 2-byte nonce from each `0xF4` response (`DB 4F 07 <nonce> 80 <crc>`) and the 20-byte payload from the `0xF1` write that follows it (`BD F1 19 01 <payload> <crc>`).
3. In `tests/test_protocol_session.py`, replace `ASSET_ID` and `CHALLENGE_RESPONSE_PAIRS` with those values.
4. Other tests and `tests/fixtures/frames.json` reuse the placeholder. If you change it everywhere, recompute the CRC of `init_response_slot_populated` in `frames.json`. See [CRC](../protocol/crc.md).
5. Redact device-identifying values, or keep real vectors private and run them locally.
