from aosmith_ble.protocol import deswap_ascii, is_at_command


def test_deswap_ascii_round_trips_a_known_model_string():
    target = "HPTS-50 "  # even length; the codec has no notion of padding

    def swap(data: bytes) -> bytes:
        out = bytearray()
        for i in range(0, len(data) - 1, 2):
            out += bytes([data[i + 1], data[i]])
        return bytes(out)

    wire_bytes = swap(target.encode("ascii"))
    assert deswap_ascii(wire_bytes) == target


def test_deswap_ascii_drops_non_printable_bytes():
    # A trailing odd byte and a null byte should not appear in the result.
    wire_bytes = bytes([0x00, 0x41, 0x00])  # swaps to 0x41 0x00, one leftover byte
    assert deswap_ascii(wire_bytes) == "A"


def test_is_at_command_detects_at_reset():
    assert is_at_command(b"AT+RESET=1") is True


def test_is_at_command_rejects_protocol_frames():
    assert is_at_command(bytes.fromhex("db02070b0f80fa")) is False


def test_is_at_command_rejects_short_data():
    assert is_at_command(b"AT") is False
