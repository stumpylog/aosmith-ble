import json
from pathlib import Path

from aosmith_ble.const import Mode
from aosmith_ble.protocol import set_mode_request, set_setpoint_request, write_request

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "frames.json").read_text())


def _fixture(fixture_id: str) -> bytes:
    for entry in FIXTURES:
        if entry["id"] == fixture_id:
            return bytes.fromhex(entry["hex"])
    raise KeyError(fixture_id)


def test_write_request_builds_generic_frame():
    assert write_request(0x0B, 0x00, bytes([0x33, 0x1C])) == _fixture(
        "write_setpoint_124f"
    )


def test_set_setpoint_request_matches_captured_writes():
    assert set_setpoint_request(124.0) == _fixture("write_setpoint_124f")
    assert set_setpoint_request(126.0) == _fixture("write_setpoint_126f")
    assert set_setpoint_request(114.0) == _fixture("write_setpoint_114f")
    assert set_setpoint_request(120.0) == _fixture("write_setpoint_120f")


def test_set_mode_request_matches_captured_writes():
    assert set_mode_request(Mode.HYBRID, 0) == _fixture("write_mode_hybrid_permanent")
    assert set_mode_request(Mode.ELECTRIC, 1) == _fixture("write_mode_electric_1day")
    assert set_mode_request(Mode.VACATION, 3) == _fixture("write_mode_vacation_3day")
    assert set_mode_request(Mode.HEAT_PUMP, 0) == _fixture(
        "write_mode_heatpump_permanent"
    )


def test_set_mode_request_accepts_plain_int_mode():
    assert set_mode_request(4, 0) == _fixture("write_mode_hybrid_permanent")
