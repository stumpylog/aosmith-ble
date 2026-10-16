"""Tests for the typed errors the client raises: the failure kinds a host
needs to tell apart without parsing message text."""

from __future__ import annotations

import pytest
from test_client_session import (
    _block0_page_one_hpts50_fw63,
    _fixture,
    _full_happy_path_responder,
    _make_client,
    _response,
    _units_response,
)

from aosmith_ble import (
    ChallengeRejectedError,
    ConfigurationIssue,
    SessionError,
    UnknownDeviceError,
    UnsupportedConfigurationError,
    ValidationError,
)
from aosmith_ble import protocol as p


def _rejecting_responder():
    base = _full_happy_path_responder()

    def responder(cmd: bytes) -> list[bytes]:
        if cmd[:4] == bytes([0xBD, 0xF1, 0x19, 0x01]):
            return [_fixture("f1_response_rejected")]
        return base(cmd)

    return responder


def test_challenge_rejected_is_a_session_error():
    assert issubclass(ChallengeRejectedError, SessionError)


async def test_rejected_challenge_raises_challenge_rejected_error():
    client, _fake = await _make_client(_rejecting_responder())

    with pytest.raises(ChallengeRejectedError) as excinfo:
        await client._establish_session()

    assert "press the Bluetooth button" in str(excinfo.value)
    assert "probably wrong" not in str(excinfo.value)
    assert client._session_ok is False


def test_unsupported_configuration_is_a_validation_error():
    assert issubclass(UnsupportedConfigurationError, ValidationError)


def test_configuration_issue_values():
    assert ConfigurationIssue.UNITS == "units"
    assert ConfigurationIssue.MTU == "mtu"


async def test_celsius_display_raises_unsupported_configuration_units():
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(0, 0, 20):
            return [_block0_page_one_hpts50_fw63()]
        if cmd == p.read_request(26, 2, 1):
            return [_units_response(1)]
        return []

    client, _fake = await _make_client(responder)

    with pytest.raises(UnsupportedConfigurationError, match="UNITS") as excinfo:
        await client._match_and_validate_profile()

    assert excinfo.value.reason is ConfigurationIssue.UNITS
    assert client.profile is None


async def test_small_mtu_raises_unsupported_configuration_mtu():
    client, _fake = await _make_client(_full_happy_path_responder(), mtu_size=23)

    with pytest.raises(UnsupportedConfigurationError, match="MTU") as excinfo:
        await client._match_and_validate_profile()

    assert excinfo.value.reason is ConfigurationIssue.MTU
    assert client.profile is None


def _unknown_model_responder_fw(model_bytes: bytes, firmware: tuple[int, int]):
    def responder(cmd: bytes) -> list[bytes]:
        if cmd == p.read_request(0, 0, 20):
            payload = bytes(firmware) + bytes(2 * 15) + model_bytes
            return [_response(payload, block=0, start=0)]
        return []

    return responder


async def test_unknown_device_error_carries_model_and_firmware():
    model_bytes = b"NOTHPTS!"
    client, _fake = await _make_client(_unknown_model_responder_fw(model_bytes, (6, 4)))

    with pytest.raises(UnknownDeviceError) as excinfo:
        await client._match_and_validate_profile()

    assert excinfo.value.model == p.deswap_ascii(model_bytes)
    assert excinfo.value.firmware == (6, 4)


async def test_unknown_device_error_with_non_ascii_model_still_raises_it():
    client, _fake = await _make_client(
        _unknown_model_responder_fw(
            bytes([0xFF, 0x00, 0x80, 0x01, 0x02, 0x03, 0x04, 0x05]), (1, 2)
        )
    )

    with pytest.raises(UnknownDeviceError) as excinfo:
        await client._match_and_validate_profile()

    # Non-printable bytes are dropped by deswap_ascii; the model may be
    # short or empty but is always a str, and firmware is still reported.
    assert excinfo.value.model == p.deswap_ascii(
        bytes([0xFF, 0x00, 0x80, 0x01, 0x02, 0x03, 0x04, 0x05])
    )
    assert excinfo.value.firmware == (1, 2)


async def test_device_info_firmware_is_set_on_a_successful_match():
    client, _fake = await _make_client(_full_happy_path_responder())
    assert client.device_info.firmware is None

    await client._establish_session()
    await client._match_and_validate_profile()

    assert client.device_info.firmware == (6, 3)
    assert client.device_info.model == "HPTS-50"


async def test_disconnect_clears_device_info_firmware():
    client, _fake = await _make_client(_full_happy_path_responder())
    await client._establish_session()
    await client._match_and_validate_profile()

    await client.disconnect()

    assert client.device_info.firmware is None


def test_unsupported_configuration_reason_is_keyword_only():
    with pytest.raises(TypeError):
        UnsupportedConfigurationError("msg", ConfigurationIssue.MTU)  # type: ignore[misc]
    err = UnsupportedConfigurationError("msg", reason=ConfigurationIssue.MTU)
    assert err.reason is ConfigurationIssue.MTU
