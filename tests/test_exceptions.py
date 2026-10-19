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
    WriteUnconfirmedError,
)


def test_read_refused_is_a_protocol_error():
    assert issubclass(ReadRefusedError, ProtocolError)


def test_write_unconfirmed_is_a_protocol_error():
    assert issubclass(WriteUnconfirmedError, ProtocolError)


def test_write_unconfirmed_carries_what_was_written_and_read():
    err = WriteUnconfirmedError("x", block=11, param=0, expected=(1,), actual=None)
    assert (err.block, err.param, err.expected, err.actual) == (11, 0, (1,), None)


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


def test_unknown_device_error_defaults_identity_to_none():
    exc = UnknownDeviceError("no profile")
    assert exc.model is None
    assert exc.firmware is None
    assert str(exc) == "no profile"
