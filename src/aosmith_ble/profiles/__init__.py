"""Device profiles: separates addressing (where a field lives, how it
decodes) from trust (what anyone has actually verified).

Profiles are authored as Python literals and validated in `__post_init__`,
so a malformed profile fails at import time, never mid-session against a
physical appliance.

Every type here is a frozen, slotted dataclass. Frozen because a profile is
shared process-wide and gates writes to hardware -- nothing should be able to
raise a trust grade or a setpoint ceiling after construction, which is when
the validation ran. Slotted because a mistyped attribute name on a profile
must raise `AttributeError` rather than silently creating an unread
attribute, which is exactly how an unsafe grade would go unnoticed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, StrEnum
from types import MappingProxyType

from ..codecs import CODEC_REGISTRY
from ..const import MAX_WORDS_PER_READ
from ..exceptions import ValidationError


class Trust(Enum):
    """How well a field's behaviour on a given device is actually known.

    `OK` means observed working on hardware; `PARTIAL` means observed but
    only self-validating or otherwise incompletely confirmed; `UNVERIFIED`
    means plausible but never exercised; `UNSUPPORTED` means known absent or
    known refused. Read and write are graded independently -- a field is
    routinely readable at `OK` while its write path has never been tried.
    """

    OK = "ok"
    UNVERIFIED = "unverified"
    PARTIAL = "partial"
    UNSUPPORTED = "unsupported"


_TRUST_RANK: dict[Trust, int] = {
    Trust.UNSUPPORTED: 0,
    Trust.UNVERIFIED: 1,
    Trust.PARTIAL: 2,
    Trust.OK: 3,
}


def trust_at_least(candidate: Trust, minimum: Trust) -> bool:
    """True if `candidate` is graded at least as trustworthy as `minimum`.

    `PARTIAL` outranks `UNVERIFIED`: a field graded `PARTIAL` has been
    observed working, if only in a self-validating or incomplete way, while
    `UNVERIFIED` has never been exercised at all -- see `Trust`'s own
    docstring. `UNSUPPORTED` ranks below both; nothing is "at least"
    `UNSUPPORTED` except `UNSUPPORTED` itself.
    """
    return _TRUST_RANK[candidate] >= _TRUST_RANK[minimum]


class FieldName(StrEnum):
    """Canonical identity for a field across `Profile.fields`, `FieldSpec`-
    addressed reads, and the `Feature`/`FeatureSet` model that reads produce.

    `StrEnum`, not `(str, Enum)`: `requires-python` already pins `>=3.11`,
    where `enum.StrEnum` is always available, and it makes `str(member)`
    return the plain value (`"setpoint"`) rather than `(str, Enum)`'s
    `"FieldName.SETPOINT"` -- which matters for log lines and the fixture/
    diagnostic output `DiagnosticReport` produces.
    """

    SETPOINT = "setpoint"
    MODE = "mode"
    FAULT = "fault"
    MODEL = "model"
    SERIAL = "serial"
    VACATION_DAYS_REMAINING = "vacation_days_remaining"
    GUEST_DAYS_REMAINING = "guest_days_remaining"
    ELECTRIC_DAYS_REMAINING = "electric_days_remaining"


class FieldScope(Enum):
    """When a field is fetched: every poll, or once per connection.

    `STATE` fields are read by every `async_get_state()` call. `IDENTITY`
    fields describe the device itself (model, serial) rather than its
    current state, do not change within a connection, and are read exactly
    once -- at connect time -- and cached on `DeviceInfo` instead of
    appearing in a `FeatureSet`.
    """

    STATE = "state"
    IDENTITY = "identity"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Where one named value lives in a device's block/parameter space, how
    to decode it, and how much its read and write paths are trusted."""

    block: int
    param: int
    words: int
    codec: str
    read: Trust = Trust.UNSUPPORTED
    write: Trust = Trust.UNSUPPORTED
    scope: FieldScope = FieldScope.STATE

    def __post_init__(self) -> None:
        if self.codec not in CODEC_REGISTRY:
            raise ValidationError(
                f"unknown codec {self.codec!r}; registered codecs are "
                f"{sorted(CODEC_REGISTRY)}"
            )
        if self.words < 1:
            raise ValidationError(f"words must be >= 1, got {self.words}")
        if self.block < 0:
            raise ValidationError(f"block must be >= 0, got {self.block}")
        if self.param < 0:
            raise ValidationError(f"param must be >= 0, got {self.param}")
        # `param` is a zero-based start offset and `words` a count, so the
        # last word touched is at index param + words - 1. A field ending
        # exactly on index MAX_WORDS_PER_READ - 1 still fits inside the
        # single response the device will serve without paging.
        crosses_page_one = (self.param + self.words) > MAX_WORDS_PER_READ
        if crosses_page_one and self.read is Trust.OK:
            raise ValidationError(
                f"field at block {self.block} param {self.param} (+{self.words} "
                f"words) crosses the {MAX_WORDS_PER_READ}-word page boundary; "
                "no value past page one may be graded read=Trust.OK "
                "(the one documented carve-out, the block-0 serial, is "
                "self-validating and graded PARTIAL, never OK)"
            )


@dataclass(frozen=True, slots=True)
class Match:
    """What a device must report for a profile to claim it."""

    model: bytes
    firmware: tuple[int, int]
    fingerprint: tuple[tuple[int, int], ...] | None = None


@dataclass(frozen=True, slots=True)
class Profile:
    """A device's addressing, limits and trust grades, as one immutable unit."""

    id: str
    match: Match | None
    min_setpoint_f: float
    max_setpoint_f: float
    allow_extended_max: bool = False
    writable_modes: tuple = field(default_factory=tuple)
    fields: tuple[tuple[FieldName, FieldSpec], ...] = field(default_factory=tuple)
    inherits: str | None = None
    removes: frozenset[str] = field(default_factory=frozenset)
    # Lazily built by `field_map`. Excluded from init, repr, equality and
    # therefore from the generated __hash__, so a cached lookup table never
    # changes how two profiles compare.
    _field_map_cache: Mapping[str, FieldSpec] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        hard_cap = 140.0 if self.allow_extended_max else 130.0
        if self.max_setpoint_f > hard_cap:
            raise ValidationError(
                f"profile {self.id!r}: max_setpoint_f {self.max_setpoint_f} exceeds "
                f"{hard_cap} ("
                f"{'140 absolute ceiling' if self.allow_extended_max else '130 default; set allow_extended_max=True for up to 140'}"
                ")"
            )
        if self.max_setpoint_f > 140.0:
            raise ValidationError(
                f"profile {self.id!r}: max_setpoint_f {self.max_setpoint_f} exceeds "
                "the absolute 140F ceiling, which allow_extended_max cannot raise"
            )
        if self.min_setpoint_f > self.max_setpoint_f:
            raise ValidationError(
                f"profile {self.id!r}: min_setpoint_f {self.min_setpoint_f} exceeds "
                f"max_setpoint_f {self.max_setpoint_f}"
            )
        names = [name for name, _spec in self.fields]
        if len(names) != len(set(names)):
            raise ValidationError(
                f"profile {self.id!r}: duplicate field name in fields"
            )
        if self.inherits is None and self.match is None:
            raise ValidationError(
                f"profile {self.id!r}: match is required unless this profile "
                "is only ever used as a parent via inherits"
            )

    @property
    def field_map(self) -> Mapping[FieldName, FieldSpec]:
        """Field name -> spec, built once and then reused.

        Returned as a read-only view: `Profile` is otherwise deeply
        immutable, and a shared mutable dict would be a way to edit a trust
        grade after validation. `functools.cached_property` cannot be used
        because a slotted instance has no `__dict__` for it to cache into.
        """
        cached = self._field_map_cache
        if cached is None:
            cached = MappingProxyType(dict(self.fields))
            object.__setattr__(self, "_field_map_cache", cached)
        return cached

    def __getstate__(self) -> dict[str, object]:
        """State for `copy` and `pickle`, with the lazy cache dropped.

        A slotted dataclass serializes every slot, and a `MappingProxyType`
        cannot be pickled -- so without this, whether a profile survives a
        copy would depend on whether anything had happened to read
        `field_map` first. Handing back `None` for the cache also means a
        copy never inherits another instance's view: it rebuilds its own on
        first access, from the `fields` tuple that came across with it.
        """
        state = {
            name: getattr(self, name)
            for cls in type(self).__mro__
            for name in getattr(cls, "__slots__", ())
        }
        state["_field_map_cache"] = None
        return state

    def __setstate__(self, state: dict[str, object]) -> None:
        # object.__setattr__ because the dataclass is frozen. Validation is
        # not re-run: the state being restored came from an instance that
        # already passed __post_init__ at construction.
        for name, value in state.items():
            object.__setattr__(self, name, value)


def resolve_inherits(
    profiles_by_id: dict[str, Profile],
    profile_id: str,
    _seen: frozenset[str] = frozenset(),
) -> Profile:
    """Return `profile_id` fully materialized.

    A profile with no `inherits` is returned unchanged. Otherwise its parent
    is resolved first (recursively, so a chain resolves correctly), then
    merged into the child:

    * `match` is never inherited -- it stays whatever the child declared.
    * A parent field is carried over unless the child declares a field of
      the same name or lists that name in `removes`.
    * A carried-over field whose parent `write` trust was `OK` is demoted to
      `UNVERIFIED`. Read trust is carried over untouched: a read that worked
      on the parent firmware very likely behaves the same on a close child
      firmware, whereas inheriting a write grade onto unverified firmware is
      a categorically bigger risk. To keep `write=Trust.OK` on a child, the
      child must redeclare that field itself, which is a deliberate act by
      the profile author.

    The result carries `inherits=None` and an empty `removes`, so resolving
    an already-resolved profile is a no-op.
    """
    try:
        profile = profiles_by_id[profile_id]
    except KeyError:
        raise ValidationError(f"unknown profile id {profile_id!r}") from None
    if profile.inherits is None:
        return profile
    if profile_id in _seen:
        raise ValidationError(
            f"cycle detected resolving inherits chain at {profile_id!r}"
        )
    parent = resolve_inherits(profiles_by_id, profile.inherits, _seen | {profile_id})

    child_field_names = {name for name, _spec in profile.fields}
    merged_fields: list[tuple[str, FieldSpec]] = list(profile.fields)
    for name, parent_spec in parent.fields:
        if name in profile.removes or name in child_field_names:
            continue
        demoted = parent_spec
        if parent_spec.write is Trust.OK:
            demoted = FieldSpec(
                block=parent_spec.block,
                param=parent_spec.param,
                words=parent_spec.words,
                codec=parent_spec.codec,
                read=parent_spec.read,
                write=Trust.UNVERIFIED,
                scope=parent_spec.scope,
            )
        merged_fields.append((name, demoted))

    return Profile(
        id=profile.id,
        match=profile.match,
        min_setpoint_f=profile.min_setpoint_f,
        max_setpoint_f=profile.max_setpoint_f,
        allow_extended_max=profile.allow_extended_max,
        writable_modes=profile.writable_modes,
        fields=tuple(merged_fields),
        inherits=None,
        removes=frozenset(),
    )


__all__ = [
    "FieldName",
    "FieldScope",
    "FieldSpec",
    "Match",
    "Profile",
    "Trust",
    "resolve_inherits",
    "trust_at_least",
]
