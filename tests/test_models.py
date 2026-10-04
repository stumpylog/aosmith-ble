from dataclasses import FrozenInstanceError

import pytest

from aosmith_ble.models import Feature
from aosmith_ble.profiles import FieldName, Trust


def test_feature_is_frozen_and_slotted():
    feature = Feature(id=FieldName.SETPOINT, value=124.0, trust=Trust.OK, writable=True)
    assert feature.value == 124.0
    assert feature.writable is True
    with pytest.raises(FrozenInstanceError):
        feature.value = 100.0
    assert not hasattr(feature, "__dict__")


def test_feature_carries_its_own_trust_grade():
    feature = Feature(
        id=FieldName.GUEST_DAYS_REMAINING,
        value=0,
        trust=Trust.UNVERIFIED,
        writable=False,
    )
    assert feature.trust is Trust.UNVERIFIED


def test_heater_state_no_longer_exists():
    import aosmith_ble.models as models_mod

    assert not hasattr(models_mod, "HeaterState")
