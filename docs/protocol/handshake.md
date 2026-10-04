# Handshake

The session handshake: how a client gets the heater to accept reads and writes.

Placeholders throughout: assetID `02iQk000000EXAMPLE`, pairing code `XXXXXX`.

## Step 1: serial number authentication

The phone sends the last 6 digits of the advertised device name as ASCII:

```text
Write 0x0010: 58 58 58 58 58 58
              ^-- ASCII: "XXXXXX" (last 6 digits of the advertised name, e.g. iCOMM-AC000W037XXXXXX)
```

This write gets only the ATT write response, no notification. The official app uses write-with-response for commands. Pause briefly before the next command (**unverified**: the needed length is not measured).

Order relative to enabling notifications: see [Connection](connection.md#connection-overview).

## Step 2: initialize

```text
Write 0x0010: BD F2 05 01 D8
              |  |  |  |  +-- CRC
              |  |  |  +---- Data: 0x01 (pairing-slot index)
              |  |  +------- Length: 5
              |  +---------- Type: 0xF2 (INIT)
              +------------- Header: 0xBD
```

## Step 3: init response (cloud ID)

Synthetic frame for the example assetID (see [the worked example](#worked-example-synthetic-vector)):

```text
Notification: DB 2F 18 01 30 32 69 51 6B 30 30 30 30 30 30 45 58 41 4D 50 4C 45 80 DE
              |  |  |  |  |                                                 |  +- CRC
              |  |  |  |  +-------------------------------------------------+--- Status (0x80)
              |  |  |  |         Salesforce cloud ID / assetID (18 chars ASCII)
              |  |  |  +- Pairing slot status: 0x01 = populated, 0x00 = empty
              |  |  +---- Length: 0x18 (24 bytes)
              |  +------- Type: 0x2F (INIT_RESPONSE)
              +---------- Header: 0xDB

Decoded cloud ID: "02iQk000000EXAMPLE"
```

The `01` in the `BD F2 05 01` request is a pairing-slot index, not a constant. Byte `[3]` of the response reports that slot's state:

| `[3]`  | Meaning        | assetID field    |
| ------ | -------------- | ---------------- |
| `0x01` | Slot populated | 18-char ASCII ID |
| `0x00` | Slot empty     | all zeros        |

**Verified on hardware:** an empty slot (`0x00`) does not block reads. With the assetID cached from a prior session the challenge is still accepted. Save the assetID, it is the HMAC message in step 5.

## Step 4: session challenge request (0xF4)

```text
Write 0x0010: BD F4 04 12
              |  |  |  +-- CRC
              |  |  +----- Length: 4
              |  +-------- Type: 0xF4 (CHALLENGE REQUEST)
              +----------- Header: 0xBD

Notification: DB 4F 07 93 12 80 F4
              |  |  |  |  |  |  +- CRC
              |  |  |  |  |  +---- Status (0x80)
              |  |  |  +--+------- Challenge: 2 bytes, NEW EVERY SESSION
              |  |  +------------- Length: 7
              |  +---------------- Type: 0x4F
              +------------------- Header: 0xDB
```

The two bytes are a per-session nonce, different on every connection. The example nonce `9312` is reused in the vector below.

## Session challenge response (0xF1)

Step 5 of the handshake:

```text
Write 0x0010: BD F1 19 01 <20-byte HMAC> <CRC>

Notification: DB 1F 05 80 D2     <- 0x80 = ACCEPTED
              DB 1F 05 01 6A     <- 0x01 = REJECTED
```

The 20-byte payload is:

```text
payload = HMAC-SHA1(key     = the 2 challenge bytes from step 4,
                    message = the 18-char ASCII assetID from step 3)
```

The **nonce is the key** and the **assetID is the message**, not the reverse.

All 20 digest bytes are sent. Verified against five challenge/response pairs captured from the official app (**verified on hardware**). The real pairs are not published because they depend on the unit's assetID; see [Test vectors](../development/test-vectors.md).

**There is no secret.** The device supplies both the assetID and the nonce, so any client that can connect can compute the answer. This is obfuscation, not authentication.

**This step is mandatory.** Until the device answers `0x80`, data reads return 7-byte echo stubs rather than real records.

### Worked example (synthetic vector)

Example values for the placeholder assetID, not a capture, computed with the [CRC](crc.md) and the HMAC construction above, nonce `9312`:

```text
asset hex:  303269516b3030303030304558414d504c45
hmac:       c93e625fc3978881f78abcadcc1c7e5d2c6e3625
f1 frame:   bdf11901c93e625fc3978881f78abcadcc1c7e5d2c6e3625ec
init resp:  db2f1801303269516b3030303030304558414d504c4580de
```

- `f1 frame` is the full `0xF1` write: `BD F1 19 01`, the 20 HMAC bytes, then the CRC `EC`.
- `init resp` is the `0xF2` response for a populated slot: `DB 2F 18 01`, the 18 assetID bytes, status `80`, then the CRC `DE`.

It checks an implementation against this description, not against the device ([Test vectors](../development/test-vectors.md)).

### Stub versus real record

With the challenge not yet accepted, a read returns a 7-byte stub. After `0x80` it returns the real record:

```text
TX  BD A0 07 0B 00 10 F4
RX  DB 02 07 0B 00 10 2E      <- stub, 7 bytes (challenge not accepted)
RX  DB 02 27 0B 00 33 1C ...  <- real record, 39 bytes (after 0x80)
```

## The assetID

The `0xF1` response needs the 18-character assetID (for example `02iQk000000EXAMPLE`). Where it comes from:

- **Not on the rating plate** (**verified on hardware**). The plate carries the model (`HPTS-50 200`), a `<plate serial>` and the part number `100350404`. The assetID is a Salesforce-style cloud record ID.
- **Not in any readable block** (**verified on hardware**). Blocks 0, 1, 2, 8, 11, 13, 26 and 27 were probed. The model and part of the serial are present (word-swapped, see [Blocks](blocks.md)), but the assetID is not.
- **From the `0xF2` init response**, only while pairing slot 1 is populated (`status=0x01`). An empty slot returns zeros (**verified on hardware**).
- **One Bluetooth button press repopulates the slot** (**verified on hardware**). The installation guide says one press activates the Bluetooth signal for 10 minutes and holding for 3 seconds turns it off (**from the handbook**), so do not hold the button.

Once captured, the assetID can be cached indefinitely. A cached value authenticates even when the slot later reads empty (**verified on hardware**). Bootstrap: press the button once, read the assetID, store it. No cloud account or A.O. Smith credentials are needed, and the button is not needed for reads once the assetID is known.

### Re-pairing

When the official app finds no known ID in the slot, it sends `BD F3 05 01` (delete slot 1) followed by `BD F0 16 <assetID as 18 bytes>` to write its own PairKey. That path writes persistent state to the heater and can evict another client's entry. A client does not need it and should not use it.

## Complete connection sequence

In order:

1. Connect, and answer the heater's MTU request ([Client requirements](connection.md#client-requirements)).
2. Subscribe to notifications on the RX characteristic (`69400002-...`).
3. Write the 6-digit pairing code from the advertised name to the TX characteristic, then settle briefly.
4. Send `BD F2 05 01 D8` and parse the init response for the assetID (cache it if the slot is populated, reuse the cache if it is empty).
5. Send `BD F4 04 12` and read the 2-byte nonce.
6. Compute the HMAC and send the `0xF1` frame. Proceed only on `DB 1F 05 80 D2`.
7. Issue reads and verified writes ([Commands](commands.md)).
