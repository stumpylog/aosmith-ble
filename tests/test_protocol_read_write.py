import json
from pathlib import Path

import pytest

from aosmith_ble.exceptions import ProtocolError, ReadRefusedError
from aosmith_ble.protocol import (
    fault_read_request,
    param,
    parse_read,
    read_request,
    word_count,
    word_to_fahrenheit,
    write_accepted,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


def test_read_request_matches_captures():
    assert read_request(0x0B, 0x00, 0x1A) == _fixture("read_block11_full")
    assert read_request(0x02, 0x07, 0x01) == _fixture("read_block2_fault")


def test_fault_read_request_matches_capture():
    assert fault_read_request() == _fixture("read_block2_fault")


def test_write_accepted_true_for_matching_block_and_param():
    assert write_accepted(_fixture("write_ack_mode"), 0x0B, 0x0F) is True


def test_write_accepted_false_for_mismatched_param():
    assert write_accepted(_fixture("write_ack_mode"), 0x0B, 0x00) is False


def test_parse_read_returns_payload_on_success():
    payload = parse_read(
        _fixture("read_response_block2_fault_healthy"),
        request_block=0x02,
        request_start=0x07,
        request_words=0x01,
    )
    assert payload == bytes.fromhex("0000")
    assert param(payload, 0) == 0


def test_parse_read_raises_on_mismatched_echoed_block_or_start():
    """A successful-status response that echoes a different block/start than
    what was requested is a stale or misdelivered reply, not a valid answer
    -- it must raise rather than be decoded as if it matched."""
    stale = _fixture("read_response_block2_fault_healthy")  # echoes block=2, start=7
    with pytest.raises(ProtocolError, match="echoed"):
        parse_read(
            stale,
            request_block=0x0B,
            request_start=0x00,
            request_words=0x01,
        )


def test_parse_read_raises_on_refusal_stub():
    with pytest.raises(ReadRefusedError, match="refused"):
        parse_read(
            _fixture("read_response_refused_generic"),
            request_block=0x0B,
            request_start=0x00,
            request_words=0x40,
        )


def test_param_out_of_range_raises():
    payload = bytes.fromhex("0000")
    with pytest.raises(ProtocolError):
        param(payload, 5)


def test_word_count():
    assert word_count(bytes.fromhex("0000")) == 1
    assert word_count(bytes.fromhex("00000000")) == 2


def test_parse_read_decodes_block11_status_electric_2day():
    payload = parse_read(
        _fixture("block11_status_electric_2day"),
        request_block=0x0B,
        request_start=0x00,
        request_words=0x1A,
    )
    assert word_count(payload) == 16

    setpoint_word = param(payload, 0)
    assert setpoint_word == 0x331C
    assert round(word_to_fahrenheit(setpoint_word), 1) == 124.0

    mode_word = param(payload, 15)
    assert mode_word == 0x0201
    assert (mode_word >> 8) == 2
    assert (mode_word & 0xFF) == 1
