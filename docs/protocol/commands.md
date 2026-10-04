# Commands and responses

Command and response formats, read semantics and the verified write path. Commands use the [framing](connection.md#message-framing) and none is accepted until the [handshake](handshake.md) completes.

## Command format

```text
BD [CMD] [LEN] [BLOCK] [PARAM] [DATA...] [CRC]
```

### Command types

Names are descriptive labels.

| Hex  | Name          | Purpose                         |
| ---- | ------------- | ------------------------------- |
| 0x40 | WRITE_BLOCK   | Write parameter value           |
| 0xA0 | READ_BLOCK    | Read parameter words            |
| 0xF0 | PAIR_KEY      | Write assetID into pairing slot |
| 0xF1 | CHALLENGE_RESPONSE | Session challenge response |
| 0xF2 | INIT          | Initialize / read pairing slot  |
| 0xF3 | SLOT_DELETE   | Delete a pairing slot           |
| 0xF4 | CHALLENGE_REQUEST | Request the session nonce    |

`0xF0` and `0xF3` write persistent state and are not needed by a client (see [Handshake](handshake.md#re-pairing)).

## Read semantics

Reads take a start offset and a word count (verified on hardware):

```text
BD A0 07 <block> <start_param> <word_count> <crc>
```

Byte `[4]` is the first parameter index and byte `[5]` the word count (2-byte words). `BD A0 07 02 07 01 66` reads Block 2 from param 7 for one word.

A single response is capped at **20 words** (asking for more still returns 20). Reach later words by paging with the start offset:

```text
BD A0 07 0B 00 14 ..   Block 11, params 0-19
BD A0 07 0B 14 01 ..   Block 11, param 20 (HOT_WATER_PLUS_LEVEL)
```

The param 20 frame and `HOT_WATER_PLUS_LEVEL` at that index are **unverified**. On firmware 6.3, Blocks 2 and 11 repeat with period 20 over BLE, so a read at param 20 returns the setpoint again (`p20 == p0`) and `HOT_WATER_PLUS_LEVEL` is not returned. No `0x0000 = NORMAL_OPERATION` reading is claimed.

A read the device will not serve returns a 7-byte stub carrying `0x40` where a successful response carries `0x80`:

```text
BD A0 07 1B 1C 14 ..  ->  DB 02 07 1B 1C 40 50    (Block 27 words 28+ unavailable on this unit)
```

## Writing parameters (verified)

Writes (**verified on hardware**):

```text
BD 40 <len> <block> <param> <value bytes...> <crc>      len = valueBytes + 6
```

Success is acknowledged with:

```text
DB 02 07 <block> <param> 80 <crc>       0x80 = accepted
```

Block 11 value encodings (**verified on hardware**):

```text
OPERATING_SETPOINT  value = round((degF - 32) / 1.8 * 256)   as 2 bytes, big-endian
OPERATION_MODE      value = <duration_days> <mode_enum>      duration 0 = permanent
```

See [Block 11](block-11.md) for the encodings in detail.

**Verified end to end on hardware**, both a no-op and a real round trip:

```text
no-op mode write   BD 40 08 0B 0F 00 04 14 -> DB 02 07 0B 0F 80 FA, state unchanged
setpoint 124->123  BD 40 08 0B 00 32 8E 56 -> ack, read-back 0x328E (123.0 F)
setpoint 123->124  BD 40 08 0B 00 33 1C 06 -> ack, read-back 0x331C (124.0 F)
```

The no-op check rewrites `OPERATION_MODE` with the value just read back, exercising the write path without changing state. A written value shows in the next Block 11 read, so writes can be confirmed. These encodings also reproduce every `0x40` write in the official app captures byte for byte:

```text
124F -> bd40080b00331c06      126F -> bd40080b0034390c
114F -> bd40080b002d8ece      120F -> bd40080b0030e46e
HYBRID/perm  -> bd40080b0f000414    ELECTRIC/1d  -> bd40080b0f0101fe
VACATION/3d  -> bd40080b0f030266    HEAT_PUMP/perm -> bd40080b0f00054a
```

!!! warning "Writes are stateful"
    Mode writes with a non-zero duration are stateful: losing the link mid-test leaves the unit in that mode until it expires. The setpoint is a single scalar and can be put straight back, but do not raise it casually (scald risk). See [Operating limits](../hardware/operating-limits.md).

## Example frames

**Set temperature to 120F (Block 11, param 0):**

```text
BD 40 08 0B 00 30 E4 6E
|  |  |  |  |  |  |  +-- CRC
|  |  |  |  |  +--+---- Temperature: 0x30E4 (120F / 48.89C)
|  |  |  |  +---------- Parameter: 0 (SETPOINT)
|  |  |  +------------- Block: 0x0B (11)
|  |  +---------------- Length: 8
|  +------------------- Command: WRITE (0x40)
+---------------------- Header: 0xBD
```

**Set mode to HEAT_PUMP (Block 11, param 15):**

```text
BD 40 08 0B 0F 00 05 4A
|  |  |  |  |  |  |  +-- CRC
|  |  |  |  |  +--+---- Mode data: duration=0 (permanent), mode=5 (HEAT_PUMP)
|  |  |  |  +---------- Parameter: 15 (MODE)
|  |  |  +------------- Block: 0x0B (11)
|  |  +---------------- Length: 8
|  +------------------- Command: WRITE (0x40)
+---------------------- Header: 0xBD
```

**Read Block 11 status (params 0-15):**

```text
BD A0 07 0B 00 10 F4
|  |  |  |  |  |  +-- CRC
|  |  |  |  |  +------ Word count: 0x10 (16 words)
|  |  |  |  +--------- Start parameter: 0
|  |  |  +------------ Block: 0x0B (11)
|  |  +--------------- Length: 7
|  +------------------ Command: READ (0xA0)
+--------------------- Header: 0xBD
```

## Response types

| Type | Name          | Length   | Purpose                    |
| ---- | ------------- | -------- | -------------------------- |
| 0x02 | BLOCK_STATUS  | Variable | Parameter value response   |
| 0x2F | INIT_RESPONSE | 24       | Cloud ID (after handshake) |
| 0x4F | QUICK_STATUS  | 7        | Session nonce / brief ack  |

### Quick status response (0x4F)

Received after the `0xF4` challenge request:

```text
DB 4F 07 [2 nonce bytes] [status 0x80] [CRC]
```

In the handshake, the two data bytes are the per-session nonce (verified on hardware). Whether `0x4F` carries anything else in other contexts is unverified.
