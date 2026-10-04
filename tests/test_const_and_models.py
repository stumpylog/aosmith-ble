from aosmith_ble.const import (
    ASSET_ID_LEN,
    Block,
    Cmd,
    FAULT_CODES,
    HDR_REQUEST,
    HDR_RESPONSE,
    MAX_WORDS_PER_READ,
    Mode,
    STATUS_OK,
    STATUS_REFUSED,
)
from aosmith_ble.exceptions import (
    AOSmithError,
    NotConnectedError,
    NotPairedError,
    ProtocolError,
    SessionError,
)
from aosmith_ble.models import DeviceInfo, Fault


def test_framing_constants():
    assert HDR_REQUEST == 0xBD
    assert HDR_RESPONSE == 0xDB
    assert STATUS_OK == 0x80
    assert STATUS_REFUSED == 0x40
    assert MAX_WORDS_PER_READ == 20
    assert ASSET_ID_LEN == 18


def test_mode_enum_values():
    assert Mode.ELECTRIC == 1
    assert Mode.VACATION == 2
    assert Mode.GUEST == 3
    assert Mode.HYBRID == 4
    assert Mode.HEAT_PUMP == 5


def test_block_enum_values():
    assert Block.IDENTITY == 0
    assert Block.FAULTS == 2
    assert Block.CONTROL == 11
    assert Block.MODULE == 26


def test_command_byte_values():
    assert Cmd.WRITE_BLOCK == 0x40
    assert Cmd.READ_BLOCK == 0xA0
    assert Cmd.CHALLENGE_RESPONSE == 0xF1
    assert Cmd.INIT == 0xF2
    assert Cmd.CHALLENGE_REQUEST == 0xF4


def test_fault_code_table_spot_checks():
    assert FAULT_CODES[1] == "Dry Fire"
    assert FAULT_CODES[31] == "Water Leak"
    assert FAULT_CODES[44] == "Anode is Depleted"
    assert 44 in FAULT_CODES  # retracted by the manufacturer but kept for old units
    assert len(FAULT_CODES) == 26


def test_exception_hierarchy():
    for exc in (NotConnectedError, SessionError, NotPairedError, ProtocolError):
        assert issubclass(exc, AOSmithError)


def test_fault_model_reports_inactive_when_zero():
    fault = Fault(code=0)
    assert not fault.active
    assert fault.name == "None"
    assert not fault.restricts_changes


def test_fault_model_reports_active_known_code():
    fault = Fault(code=31)
    assert fault.active
    assert fault.name == "Water Leak"
    assert fault.restricts_changes


def test_fault_model_reports_active_unknown_code():
    fault = Fault(code=9999)
    assert fault.active
    assert fault.name == "Unknown fault 9999"


def test_device_info_defaults_to_unknown():
    info = DeviceInfo()
    assert info.model is None
    assert info.serial is None
    assert info.asset_id is None
