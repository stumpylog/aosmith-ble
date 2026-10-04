import json
from pathlib import Path

import pytest

from aosmith_ble.exceptions import ReadRefusedError, SessionError
from aosmith_ble.protocol import parse_read

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


def test_refusal_form_raises_read_refused():
    with pytest.raises(ReadRefusedError):
        parse_read(
            _fixture("read_response_refused_generic"),
            request_block=0x0B,
            request_start=0x00,
            request_words=0x1A,
        )


def test_session_not_established_form_raises_session_error_block11():
    with pytest.raises(SessionError, match="session challenge has not been accepted"):
        parse_read(
            _fixture("read_session_not_established_block11"),
            request_block=0x0B,
            request_start=0x00,
            request_words=0x1A,
        )


def test_session_not_established_form_raises_session_error_block2():
    with pytest.raises(SessionError):
        parse_read(
            _fixture("read_session_not_established_block2_fault"),
            request_block=0x02,
            request_start=0x07,
            request_words=0x01,
        )


def test_session_not_established_form_is_only_recognized_against_its_own_request():
    """The echo form must be compared against the ACTUAL request, not treated
    as globally recognizable -- the same bytes, read against a request they
    don't match, are just an unrecognized short form (generic ProtocolError),
    not silently accepted as either known case."""
    from aosmith_ble.exceptions import ProtocolError

    with pytest.raises(ProtocolError) as exc_info:
        parse_read(
            _fixture("read_session_not_established_block11"),
            request_block=0x02,  # doesn't match the fixture's echoed block (0x0B)
            request_start=0x07,
            request_words=0x01,
        )
    assert not isinstance(exc_info.value, (ReadRefusedError, SessionError))
