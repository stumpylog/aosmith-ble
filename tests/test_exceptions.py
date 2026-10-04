from aosmith_ble.exceptions import (
    AOSmithError,
    ConnectionSlotsExhaustedError,
    NotConnectedError,
    NotPairedError,
    ProtocolError,
    ReadRefusedError,
    SessionError,
    UnknownDeviceError,
    ValidationError,
)


def test_read_refused_is_a_protocol_error():
    assert issubclass(ReadRefusedError, ProtocolError)


def test_read_refused_is_distinct_from_session_error():
    assert not issubclass(ReadRefusedError, SessionError)
    assert not issubclass(SessionError, ReadRefusedError)


def test_new_exceptions_are_aosmith_errors():
    for exc in (
        UnknownDeviceError,
        ValidationError,
        ConnectionSlotsExhaustedError,
        NotConnectedError,
        NotPairedError,
    ):
        assert issubclass(exc, AOSmithError)


def test_exceptions_carry_a_message():
    assert str(ValidationError("setpoint 145.0 exceeds profile maximum 130.0")) == (
        "setpoint 145.0 exceeds profile maximum 130.0"
    )
