import json
from pathlib import Path

import pytest

from aosmith_ble.exceptions import ProtocolError
from aosmith_ble.protocol import (
    challenge_accepted,
    challenge_request,
    challenge_response,
    init_request,
    parse_challenge,
    parse_init,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


ASSET_ID = b"02iQk000000EXAMPLE"

# HMAC-SHA1(key=challenge, message=assetID) vectors for the placeholder assetID above.
#
# NOTE: these are SYNTHETIC. They were computed with hmac/hashlib from the placeholder
# assetID, which is the same construction the code under test uses, so they catch
# regressions but cannot catch a wrong construction. The construction was originally
# verified against five real app captures (see docs/protocol/handshake.md). Those real
# values are not published because they are tied to a real device's assetID.
#
# To restore a real, independent check (for example from a contributor's capture):
#   1. From an HCI snoop or sniffer capture of the official app, take the 18-char ASCII
#      assetID from the 0xF2 response (DB 2F 18 01 <assetID> 80 <crc>).
#   2. For several sessions of that same device, take the 2-byte nonce from the 0xF4
#      response (DB 4F 07 <nonce> 80 <crc>) and the 20-byte payload from the following
#      0xF1 write (BD F1 19 01 <payload> <crc>). All must be from the same assetID.
#   3. Replace ASSET_ID and CHALLENGE_RESPONSE_PAIRS here with those values, and keep
#      the captured values out of the repo if they identify a device (or redact them
#      and keep the vectors private, running them locally only).
#   4. Other tests and tests/fixtures/frames.json reuse the placeholder: if you change
#      it everywhere, recompute the CRC of init_response_slot_populated in frames.json.
CHALLENGE_RESPONSE_PAIRS = [
    (bytes.fromhex("9312"), bytes.fromhex("c93e625fc3978881f78abcadcc1c7e5d2c6e3625")),
    (bytes.fromhex("eb59"), bytes.fromhex("ec2c360d71d5cd5b4701c04cd910ecfa611bf751")),
    (bytes.fromhex("8a9a"), bytes.fromhex("d49c8b0cbe2dbbb40571df8d03cd8fc5edc76c17")),
    (bytes.fromhex("8875"), bytes.fromhex("c1f774a472f4002a5fb24ec1080693c2548428bb")),
    (bytes.fromhex("b748"), bytes.fromhex("a22aa27287e2d07bd1054cf92fb2ddb13cb1321f")),
]


def test_init_request_matches_capture():
    assert init_request(1) == _fixture("init_request_slot1")


def test_challenge_request_matches_capture():
    assert challenge_request() == _fixture("challenge_request")


def test_challenge_response_matches_every_known_pair():
    for challenge, expected_digest in CHALLENGE_RESPONSE_PAIRS:
        built = challenge_response(challenge, ASSET_ID)
        # digest occupies bytes [4:24] of the frame body (after header/cmd/len/0x01).
        assert built[4:24] == expected_digest


def test_challenge_response_rejects_wrong_challenge_length():
    with pytest.raises(ProtocolError):
        challenge_response(b"\x93", ASSET_ID)


def test_challenge_response_rejects_wrong_asset_id_length():
    with pytest.raises(ProtocolError):
        challenge_response(bytes.fromhex("9312"), b"too short")


def test_parse_init_slot_populated():
    status, asset_id = parse_init(_fixture("init_response_slot_populated"))
    assert status == 0x01
    assert asset_id == ASSET_ID


def test_parse_init_slot_empty():
    status, asset_id = parse_init(_fixture("init_response_slot_empty"))
    assert status == 0x00
    assert asset_id == bytes(18)


def test_parse_challenge_returns_nonce_bytes():
    assert parse_challenge(_fixture("challenge_response_9312")) == bytes.fromhex("9312")


def test_challenge_accepted_true_and_false():
    assert challenge_accepted(_fixture("f1_response_accepted")) is True
    assert challenge_accepted(_fixture("f1_response_rejected")) is False


def test_validate_rejects_bad_header():
    corrupted = bytearray(_fixture("f1_response_accepted"))
    corrupted[0] = 0x00
    with pytest.raises(ProtocolError):
        challenge_accepted(bytes(corrupted))
