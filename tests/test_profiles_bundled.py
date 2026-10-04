from aosmith_ble.const import Mode
from aosmith_ble.profiles import FieldName, FieldScope, Trust
from aosmith_ble.profiles.bundled import (
    BUNDLED_PROFILES,
    HPTS50_MODEL_BYTES,
    match_profile,
)


def test_hpts50_profile_constructs_without_raising():
    assert "hpts50-6.3" in BUNDLED_PROFILES


def test_hpts50_profile_field_trust_grades():
    profile = BUNDLED_PROFILES["hpts50-6.3"]
    assert profile.field_map["setpoint"].read is Trust.OK
    assert profile.field_map["setpoint"].write is Trust.OK
    assert profile.field_map["mode"].write is Trust.OK
    assert (
        profile.field_map["fault"].write is Trust.UNSUPPORTED
    )  # never declared writable
    assert profile.field_map["serial"].read is Trust.PARTIAL
    assert profile.field_map["guest_days_remaining"].read is Trust.UNVERIFIED
    assert profile.field_map["electric_days_remaining"].read is Trust.OK


def test_hpts50_profile_guest_is_never_writable():
    profile = BUNDLED_PROFILES["hpts50-6.3"]
    assert Mode.GUEST not in profile.writable_modes


def test_hpts50_profile_setpoint_limits():
    profile = BUNDLED_PROFILES["hpts50-6.3"]
    assert profile.min_setpoint_f == 95
    assert profile.max_setpoint_f == 130
    assert profile.allow_extended_max is False


def test_match_profile_exact_match():
    profile = match_profile(HPTS50_MODEL_BYTES, (6, 3))
    assert profile is not None
    assert profile.id == "hpts50-6.3"


def test_match_profile_no_match_on_different_firmware():
    assert match_profile(HPTS50_MODEL_BYTES, (6, 4)) is None


def test_match_profile_no_match_on_different_model():
    assert match_profile(b"some other raw wire bytes entirely", (6, 3)) is None


def test_every_field_spec_codec_is_registered():
    # Redundant with FieldSpec.__post_init__ (which would already have
    # raised at import time), but exercised explicitly per profile: every
    # bundled profile must reference only registered codecs.
    from aosmith_ble.codecs import CODEC_REGISTRY

    for profile in BUNDLED_PROFILES.values():
        for _name, spec in profile.fields:
            assert spec.codec in CODEC_REGISTRY


def test_no_bundled_profile_field_crosses_page_one_at_ok_trust():
    from aosmith_ble.const import MAX_WORDS_PER_READ

    for profile in BUNDLED_PROFILES.values():
        for name, spec in profile.fields:
            if spec.param + spec.words > MAX_WORDS_PER_READ:
                assert spec.read is not Trust.OK, (
                    f"{profile.id}.{name} crosses page one but is graded OK"
                )


def test_hpts50_identity_fields_are_model_and_serial_only():
    profile = BUNDLED_PROFILES["hpts50-6.3"]
    identity = {
        name for name, spec in profile.fields if spec.scope is FieldScope.IDENTITY
    }
    assert identity == {FieldName.MODEL, FieldName.SERIAL}


def test_hpts50_state_fields_exclude_model_and_serial():
    profile = BUNDLED_PROFILES["hpts50-6.3"]
    state = {name for name, spec in profile.fields if spec.scope is FieldScope.STATE}
    assert state == {
        FieldName.SETPOINT,
        FieldName.MODE,
        FieldName.FAULT,
        FieldName.VACATION_DAYS_REMAINING,
        FieldName.GUEST_DAYS_REMAINING,
        FieldName.ELECTRIC_DAYS_REMAINING,
    }


def test_hpts50_field_map_is_reachable_by_field_name_members():
    profile = BUNDLED_PROFILES["hpts50-6.3"]
    assert profile.field_map[FieldName.SETPOINT].read is Trust.OK
    assert profile.field_map[FieldName.SERIAL].read is Trust.PARTIAL
