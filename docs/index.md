# aosmith-ble

Protocol documentation for A.O. Smith iCOMM heat pump water heaters over Bluetooth LE. No cloud account, no vendor credentials, no internet connection involved.

!!! warning "Legal and safety notice"
    This project is **independent and unofficial**, and is **NOT affiliated with, endorsed by, or supported by A. O. Smith Corporation** or any of its subsidiaries.

    **Use at your own risk**

    - This project is **experimental** and **community-maintained**
    - May void your device warranty
    - Could cause device malfunction, damage, or unexpected behavior
    - Authors assume **NO LIABILITY** for any damages, injuries, or losses
    - You are responsible for ensuring your use complies with local laws and regulations

    **Trademark notice**

    - "AO Smith" and "iCOMM" are trademarks of A. O. Smith Corporation
    - Used solely for descriptive and compatibility identification purposes
    - No affiliation, endorsement, or sponsorship implied

    **For official support**: contact A. O. Smith Corporation directly. This project provides **community support only** through GitHub issues.

## Status

The full handshake is solved, reads and verified writes work, and no cloud is involved.

## Reading order

1. [Connection](protocol/connection.md): services, characteristics, MTU and framing.
2. [Handshake](protocol/handshake.md): init, challenge and response.
3. [Commands](protocol/commands.md): command types, reads and verified writes.
4. [Blocks](protocol/blocks.md): addressing and the block map.
5. [Block 11](protocol/block-11.md): status, setpoint, modes and timed countdowns.

[Tested devices](tested-devices.md) lists what the library supports. Then [Faults](protocol/faults.md), [CRC](protocol/crc.md) and the [reference](protocol/reference.md). The [Hardware](hardware/operating-limits.md) pages cover limits and the panel, the [Research](research/index.md) section is the evidence record, and [Development](development/index.md) covers what is still open.
