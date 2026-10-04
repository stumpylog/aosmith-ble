"""Value types returned by the client."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .const import FAULT_CODES
from .profiles import FieldName, Trust


@dataclass(frozen=True, slots=True)
class Fault:
    code: int

    @property
    def active(self) -> bool:
        return self.code != 0

    @property
    def name(self) -> str:
        if not self.active:
            return "None"
        return FAULT_CODES.get(self.code, f"Unknown fault {self.code}")

    @property
    def restricts_changes(self) -> bool:
        """The app disables user controls while any known fault is active."""
        return self.active


@dataclass(frozen=True, slots=True)
class Feature:
    """One profile field's current, decoded value, graded by how much this
    library has actually verified about reading it.

    Absent entirely from a `FeatureSet` if its read trust falls below the
    threshold the caller asked for (see `AOSmithBLEClient.async_get_state`)
    -- there is no "present but untrustworthy" state to represent here, by
    design: a caller that iterates a `FeatureSet` sees only what it asked to
    trust.
    """

    id: FieldName
    value: object
    trust: Trust
    writable: bool


FeatureSet = Mapping[FieldName, Feature]


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    """Identity read from block 0, plus the assetID learned from 0xF2.

    All three fields are populated once, at connect time, and never change
    for the lifetime of a connection -- unlike a `FeatureSet`, which is
    re-read on every `async_get_state()` call.
    """

    model: str | None = None
    serial: str | None = None
    asset_id: str | None = None
