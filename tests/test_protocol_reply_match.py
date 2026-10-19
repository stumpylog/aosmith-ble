"""reply_matches: which notification answers which request.

Validation (CRC, length, status) is the parsers' job; these tests only pin
which frame is taken as the answer, so a late or unrelated reply is never
handed to the request in flight.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aosmith_ble import crc
from aosmith_ble import protocol as p

_FRAMES = {
    entry["id"]: bytes.fromhex(entry["hex"])
    for entry in json.loads(
        (Path(__file__).parent / "fixtures" / "frames.json").read_text()
    )
}

ASSET_ID = b"02iQk000000EXAMPLE"


def _stub(block: int, start: int, status: int) -> bytes:
    return crc.frame(bytes([0xDB, 0x02, 0x07, block, start, status]))


def _read_reply(block: int, start: int, words: int) -> bytes:
    body = bytearray([0xDB, 0x02, 0x00, block, start]) + bytes(2 * words) + b"\x80"
    body[2] = len(body) + 1
    return crc.frame(bytes(body))


def test_read_matches_its_own_reply():
    assert p.reply_matches(
        p.read_request(11, 0, 20), _FRAMES["block11_status_electric_2day"]
    )


def test_read_matches_a_short_reply():
    assert p.reply_matches(p.read_request(27, 20, 8), _read_reply(27, 20, 6))


def test_read_rejects_a_wider_reply_for_the_same_start():
    assert not p.reply_matches(
        p.read_request(11, 0, 1), _FRAMES["block11_status_electric_2day"]
    )


def test_read_rejects_another_blocks_reply():
    assert not p.reply_matches(p.read_request(11, 0, 20), _read_reply(27, 0, 20))


def test_read_rejects_another_start():
    assert not p.reply_matches(p.read_request(27, 20, 8), _read_reply(27, 0, 8))


@pytest.mark.parametrize(
    "reply",
    [
        _FRAMES["read_response_refused_generic"],
        _FRAMES["read_session_not_established_block11"],
        _stub(11, 0, 0x10),
    ],
    ids=["refused", "no-session echo", "expired"],
)
def test_read_matches_its_stubs(reply):
    assert p.reply_matches(p.read_request(11, 0, 26), reply)


def test_read_rejects_another_blocks_expiry_stub():
    assert not p.reply_matches(p.read_request(11, 0, 20), _stub(27, 6, 0x10))


def test_read_rejects_a_write_ack_for_the_same_param():
    assert not p.reply_matches(p.read_request(11, 0, 1), _FRAMES["write_ack_setpoint"])


@pytest.mark.parametrize(
    "reply", [_FRAMES["write_ack_setpoint"], _stub(11, 0, 0x40)], ids=["ack", "refused"]
)
def test_write_matches_its_ack_and_refusal(reply):
    assert p.reply_matches(p.set_setpoint_request(124.0), reply)


def test_write_matches_an_expiry_stub_from_any_block():
    assert p.reply_matches(p.set_setpoint_request(124.0), _stub(27, 6, 0x10))


def test_write_rejects_another_params_ack():
    assert not p.reply_matches(p.set_setpoint_request(124.0), _FRAMES["write_ack_mode"])


def test_write_rejects_a_read_reply():
    assert not p.reply_matches(
        p.set_setpoint_request(124.0), _FRAMES["block11_status_electric_2day"]
    )


def test_handshake_requests_match_their_reply_command():
    init = p.init_request()
    challenge = p.challenge_request()
    response = p.challenge_response(b"\x93\x12", ASSET_ID)
    init_reply = _FRAMES["init_response_slot_populated"]
    challenge_reply = _FRAMES["challenge_response_9312"]

    assert p.reply_matches(init, init_reply)
    assert p.reply_matches(challenge, challenge_reply)
    assert p.reply_matches(response, _FRAMES["f1_response_accepted"])
    assert p.reply_matches(response, _FRAMES["f1_response_rejected"])

    assert not p.reply_matches(init, challenge_reply)
    assert not p.reply_matches(challenge, _FRAMES["f1_response_accepted"])
    assert not p.reply_matches(response, init_reply)


@pytest.mark.parametrize(
    "reply",
    [b"", b"\xdb", bytes([0xBD]) + _FRAMES["write_ack_setpoint"][1:]],
    ids=["empty", "header only", "request header"],
)
def test_garbage_never_matches(reply):
    assert not p.reply_matches(p.read_request(11, 0, 1), reply)
    assert not p.reply_matches(p.set_setpoint_request(124.0), reply)


def test_an_unknown_request_matches_nothing():
    assert not p.reply_matches(b"\x11\x22", _FRAMES["write_ack_setpoint"])
    assert not p.reply_matches(b"\x11\x22", bytes.fromhex("aabbcc"))
