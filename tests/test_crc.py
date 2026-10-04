import json
from pathlib import Path

from aosmith_ble.crc import check, crc8, frame

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


def test_every_fixture_has_a_valid_trailing_crc():
    for entry in FIXTURES:
        data = bytes.fromhex(entry["hex"])
        assert check(data), f"fixture {entry['id']!r} has a bad trailing CRC"


def test_crc8_matches_known_value():
    # write_setpoint_124f body without its trailing CRC byte.
    body = bytes.fromhex("bd40080b00331c")
    assert crc8(body) == 0x06


def test_frame_appends_the_correct_crc():
    body = bytes.fromhex("bd40080b00331c")
    assert frame(body) == _fixture("write_setpoint_124f")


def test_check_detects_a_corrupted_byte():
    good = _fixture("write_setpoint_124f")
    corrupted = bytearray(good)
    corrupted[4] ^= 0xFF  # flip a byte in the middle of the body
    assert not check(bytes(corrupted))


def test_check_rejects_too_short_input():
    assert not check(b"\x00")
