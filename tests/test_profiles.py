import copy
import pickle
from dataclasses import FrozenInstanceError

import pytest

from aosmith_ble.codecs import CODEC_REGISTRY
from aosmith_ble.exceptions import ValidationError
from aosmith_ble.profiles import (
    FieldName,
    FieldScope,
    FieldSpec,
    Match,
    Profile,
    Trust,
    resolve_inherits,
    trust_at_least,
)


def test_trust_at_least_same_grade_passes():
    assert trust_at_least(Trust.OK, Trust.OK)
    assert trust_at_least(Trust.UNSUPPORTED, Trust.UNSUPPORTED)


def test_trust_at_least_orders_ok_above_everything():
    assert trust_at_least(Trust.OK, Trust.PARTIAL)
    assert trust_at_least(Trust.OK, Trust.UNVERIFIED)
    assert trust_at_least(Trust.OK, Trust.UNSUPPORTED)


def test_trust_at_least_ranks_partial_above_unverified():
    # PARTIAL has been observed (if only self-validating); UNVERIFIED never has.
    assert trust_at_least(Trust.PARTIAL, Trust.UNVERIFIED)
    assert not trust_at_least(Trust.UNVERIFIED, Trust.PARTIAL)


def test_trust_at_least_unsupported_meets_nothing_above_it():
    assert not trust_at_least(Trust.UNSUPPORTED, Trust.UNVERIFIED)
    assert not trust_at_least(Trust.UNSUPPORTED, Trust.OK)


def _minimal_match() -> Match:
    return Match(model=b"HPTS-50", firmware=(6, 3))


def test_field_spec_rejects_unknown_codec():
    with pytest.raises(ValidationError, match="unknown codec"):
        FieldSpec(block=11, param=0, words=1, codec="not_a_real_codec", read=Trust.OK)


def test_field_spec_accepts_every_registered_codec_name():
    for name in CODEC_REGISTRY:
        FieldSpec(block=0, param=0, words=1, codec=name)  # must not raise


def test_field_spec_rejects_page_one_crossing_at_ok_trust():
    with pytest.raises(ValidationError, match="page one"):
        FieldSpec(block=0, param=36, words=5, codec="ascii_swapped", read=Trust.OK)


def test_field_spec_allows_page_one_crossing_at_partial_trust():
    # the documented carve-out: the block-0 serial, graded PARTIAL not OK.
    FieldSpec(block=0, param=36, words=5, codec="ascii_swapped", read=Trust.PARTIAL)


def test_field_spec_allows_page_one_crossing_at_lower_trust_levels():
    # The rule bites only at OK; every weaker grade may address a paged read.
    for trust in (Trust.UNVERIFIED, Trust.UNSUPPORTED):
        FieldSpec(block=11, param=20, words=1, codec="u16", read=trust)


def test_field_spec_allows_exactly_at_the_boundary():
    # param 16 + words 4 = 20 == MAX_WORDS_PER_READ, not a crossing.
    FieldSpec(block=0, param=16, words=4, codec="ascii_swapped", read=Trust.OK)


def test_field_spec_rejects_one_word_past_the_boundary():
    # param 20 is the first word the device will not serve on page one.
    with pytest.raises(ValidationError, match="page one"):
        FieldSpec(block=11, param=20, words=1, codec="u16", read=Trust.OK)


def test_field_spec_rejects_negative_addresses():
    # A negative param would slip under the page-one arithmetic entirely.
    with pytest.raises(ValidationError, match="param must be >= 0"):
        FieldSpec(block=11, param=-1, words=1, codec="u16", read=Trust.OK)
    with pytest.raises(ValidationError, match="block must be >= 0"):
        FieldSpec(block=-1, param=0, words=1, codec="u16", read=Trust.OK)


def test_field_spec_rejects_zero_words():
    with pytest.raises(ValidationError, match="words must be >= 1"):
        FieldSpec(block=11, param=0, words=0, codec="u16")


def test_field_spec_defaults_to_state_scope():
    spec = FieldSpec(block=11, param=0, words=1, codec="c256", read=Trust.OK)
    assert spec.scope is FieldScope.STATE


def test_field_spec_accepts_identity_scope():
    spec = FieldSpec(
        block=0,
        param=36,
        words=5,
        codec="ascii_swapped",
        read=Trust.PARTIAL,
        scope=FieldScope.IDENTITY,
    )
    assert spec.scope is FieldScope.IDENTITY


def test_field_spec_with_identity_scope_is_still_frozen_and_slotted():
    spec = FieldSpec(
        block=0,
        param=36,
        words=5,
        codec="ascii_swapped",
        read=Trust.PARTIAL,
        scope=FieldScope.IDENTITY,
    )
    with pytest.raises(FrozenInstanceError):
        spec.scope = FieldScope.STATE


@pytest.mark.parametrize("cls", [FieldSpec, Match, Profile])
def test_profile_types_are_frozen_and_slotted(cls):
    assert hasattr(cls, "__slots__")


def test_field_spec_is_frozen_and_slotted():
    spec = FieldSpec(block=11, param=0, words=1, codec="c256", read=Trust.OK)
    # frozen: a trust grade cannot be raised after validation ran.
    with pytest.raises(FrozenInstanceError):
        spec.read = Trust.UNSUPPORTED
    # slotted: no instance __dict__, so a typo'd name cannot stick silently.
    assert not hasattr(spec, "__dict__")
    with pytest.raises((AttributeError, TypeError)):
        spec.raed = Trust.OK
    assert not hasattr(spec, "raed")


def test_profile_rejects_max_setpoint_above_130_without_extended_flag():
    with pytest.raises(ValidationError, match="130"):
        Profile(
            id="bad",
            match=_minimal_match(),
            min_setpoint_f=95,
            max_setpoint_f=135,
        )


def test_profile_allows_up_to_140_with_extended_flag():
    Profile(
        id="ok",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=140,
        allow_extended_max=True,
    )  # must not raise


def test_profile_rejects_above_140_even_with_extended_flag():
    with pytest.raises(ValidationError, match="140"):
        Profile(
            id="bad",
            match=_minimal_match(),
            min_setpoint_f=95,
            max_setpoint_f=150,
            allow_extended_max=True,
        )


def test_profile_rejects_min_above_max():
    with pytest.raises(ValidationError):
        Profile(id="bad", match=_minimal_match(), min_setpoint_f=130, max_setpoint_f=95)


def test_profile_rejects_duplicate_field_names():
    spec = FieldSpec(block=11, param=0, words=1, codec="c256", read=Trust.OK)
    with pytest.raises(ValidationError, match="duplicate"):
        Profile(
            id="bad",
            match=_minimal_match(),
            min_setpoint_f=95,
            max_setpoint_f=130,
            fields=(("setpoint", spec), ("setpoint", spec)),
        )


def test_profile_requires_match_unless_inherits_is_set():
    with pytest.raises(ValidationError, match="match is required"):
        Profile(id="bad", match=None, min_setpoint_f=95, max_setpoint_f=130)


def test_profile_field_map_view():
    spec = FieldSpec(block=11, param=0, words=1, codec="c256", read=Trust.OK)
    profile = Profile(
        id="p",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", spec),),
    )
    assert profile.field_map == {"setpoint": spec}


def test_profile_field_map_is_cached_and_read_only():
    spec = FieldSpec(block=11, param=0, words=1, codec="c256", read=Trust.OK)
    profile = Profile(
        id="p",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", spec),),
    )
    assert profile.field_map is profile.field_map
    with pytest.raises(TypeError):
        profile.field_map["setpoint"] = spec


def test_profile_field_map_cache_does_not_affect_equality():
    spec = FieldSpec(block=11, param=0, words=1, codec="c256", read=Trust.OK)
    kwargs = dict(
        id="p",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", spec),),
    )
    warm, cold = Profile(**kwargs), Profile(**kwargs)
    warm.field_map  # populate the lazy cache on one of the two only
    assert warm == cold
    assert hash(warm) == hash(cold)


def _sample_profile() -> Profile:
    return Profile(
        id="p",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(
            (
                "setpoint",
                FieldSpec(
                    block=11,
                    param=0,
                    words=1,
                    codec="c256",
                    read=Trust.OK,
                    write=Trust.OK,
                ),
            ),
            (
                "mode",
                FieldSpec(
                    block=11, param=15, words=1, codec="mode_word", read=Trust.OK
                ),
            ),
        ),
    )


@pytest.mark.parametrize("warm", [False, True], ids=["cold", "warm"])
@pytest.mark.parametrize(
    "roundtrip",
    [copy.deepcopy, lambda p: pickle.loads(pickle.dumps(p))],
    ids=["deepcopy", "pickle"],
)
def test_profile_survives_copy_and_pickle_whether_or_not_the_cache_is_warm(
    warm, roundtrip
):
    profile = _sample_profile()
    if warm:
        profile.field_map  # a read-only view is not picklable; it must not be carried over
    clone = roundtrip(profile)
    assert clone == profile
    assert clone.field_map == profile.field_map
    assert clone.field_map["setpoint"].write is Trust.OK
    # The clone rebuilt its own view rather than sharing the original's.
    assert clone.field_map is not profile.field_map
    assert clone.field_map is clone.field_map  # and still caches


def test_profile_copy_starts_with_a_cold_cache():
    profile = _sample_profile()
    profile.field_map
    assert copy.deepcopy(profile)._field_map_cache is None
    assert pickle.loads(pickle.dumps(profile))._field_map_cache is None


def test_copied_profile_is_still_frozen_and_slotted():
    profile = _sample_profile()
    profile.field_map
    clone = pickle.loads(pickle.dumps(profile))
    assert not hasattr(clone, "__dict__")
    with pytest.raises(FrozenInstanceError):
        clone.max_setpoint_f = 140.0
    with pytest.raises(TypeError):
        clone.field_map["setpoint"] = None


def test_resolved_profile_survives_copy_and_pickle_when_warm():
    parent = _sample_profile()
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
    )
    resolved = resolve_inherits({"parent": parent, "child": child}, "child")
    resolved.field_map
    clone = pickle.loads(pickle.dumps(resolved))
    assert clone == resolved
    assert clone.field_map["setpoint"].write is Trust.UNVERIFIED  # demotion survives
    assert copy.deepcopy(resolved) == resolved


def test_resolve_inherits_demotes_write_trust_unless_redeclared():
    setpoint_ok_write = FieldSpec(
        block=11, param=0, words=1, codec="c256", read=Trust.OK, write=Trust.OK
    )
    mode_ok_write = FieldSpec(
        block=11, param=15, words=1, codec="mode_word", read=Trust.OK, write=Trust.OK
    )
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", setpoint_ok_write), ("mode", mode_ok_write)),
    )
    # Child redeclares "mode" with write=OK (re-asserted), leaves "setpoint" inherited.
    redeclared_mode = FieldSpec(
        block=11, param=15, words=1, codec="mode_word", read=Trust.OK, write=Trust.OK
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("mode", redeclared_mode),),
        inherits="parent",
    )
    registry = {"parent": parent, "child": child}
    resolved = resolve_inherits(registry, "child")

    assert (
        resolved.field_map["setpoint"].write is Trust.UNVERIFIED
    )  # demoted, not redeclared
    assert resolved.field_map["setpoint"].read is Trust.OK  # read trust NOT demoted
    assert resolved.field_map["mode"].write is Trust.OK  # redeclared, stays OK
    assert resolved.match == child.match  # match is the child's own, never inherited


def test_resolve_inherits_preserves_scope_on_a_demoted_identity_field():
    """The write-trust demotion builds a fresh FieldSpec; it must carry the
    parent's scope across rather than silently reverting an IDENTITY field
    to the STATE default (which would start polling it every state read)."""
    identity_ok_write = FieldSpec(
        block=0,
        param=16,
        words=4,
        codec="ascii_swapped",
        read=Trust.OK,
        write=Trust.OK,
        scope=FieldScope.IDENTITY,
    )
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=((FieldName.MODEL, identity_ok_write),),
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
    )

    resolved = resolve_inherits({"parent": parent, "child": child}, "child")

    spec = resolved.field_map[FieldName.MODEL]
    assert spec.write is Trust.UNVERIFIED  # the demotion path really ran
    assert spec.scope is FieldScope.IDENTITY


def test_resolve_inherits_leaves_the_parent_untouched():
    ok_write = FieldSpec(
        block=11, param=0, words=1, codec="c256", read=Trust.OK, write=Trust.OK
    )
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", ok_write),),
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
    )
    resolve_inherits({"parent": parent, "child": child}, "child")
    # Demotion produces a new spec; it must not have edited the parent's own.
    assert parent.field_map["setpoint"].write is Trust.OK


def test_resolve_inherits_demotes_only_write_ok_leaving_other_grades_alone():
    partial_write = FieldSpec(
        block=11,
        param=0,
        words=1,
        codec="c256",
        read=Trust.PARTIAL,
        write=Trust.PARTIAL,
    )
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", partial_write),),
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
    )
    resolved = resolve_inherits({"parent": parent, "child": child}, "child")
    # Demotion is not a blanket downgrade: a grade that was never OK is carried
    # through as-is, and is never silently promoted to UNVERIFIED either.
    assert resolved.field_map["setpoint"].write is Trust.PARTIAL
    assert resolved.field_map["setpoint"].read is Trust.PARTIAL


def test_resolve_inherits_child_may_redeclare_a_field_downward():
    ok_write = FieldSpec(
        block=11, param=15, words=1, codec="mode_word", read=Trust.OK, write=Trust.OK
    )
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("mode", ok_write),),
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
        fields=(
            (
                "mode",
                FieldSpec(
                    block=11,
                    param=15,
                    words=1,
                    codec="mode_word",
                    read=Trust.OK,
                    write=Trust.UNSUPPORTED,
                ),
            ),
        ),
    )
    resolved = resolve_inherits({"parent": parent, "child": child}, "child")
    assert resolved.field_map["mode"].write is Trust.UNSUPPORTED


def test_resolve_inherits_demotion_survives_a_multi_level_chain():
    ok_write = FieldSpec(
        block=11, param=0, words=1, codec="c256", read=Trust.OK, write=Trust.OK
    )
    grandparent = Profile(
        id="gp",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", ok_write),),
    )
    middle = Profile(
        id="mid",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="gp",
    )
    leaf = Profile(
        id="leaf",
        match=Match(model=b"HPTS-50", firmware=(6, 5)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="mid",
    )
    registry = {"gp": grandparent, "mid": middle, "leaf": leaf}
    # Demoted once at the middle hop and never restored further down the chain.
    assert (
        resolve_inherits(registry, "mid").field_map["setpoint"].write
        is Trust.UNVERIFIED
    )
    assert (
        resolve_inherits(registry, "leaf").field_map["setpoint"].write
        is Trust.UNVERIFIED
    )


def test_resolve_inherits_redeclaring_at_a_middle_hop_does_not_survive_to_the_leaf():
    ok_write = FieldSpec(
        block=11, param=0, words=1, codec="c256", read=Trust.OK, write=Trust.OK
    )
    grandparent = Profile(
        id="gp",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", ok_write),),
    )
    middle = Profile(
        id="mid",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="gp",
        fields=(("setpoint", ok_write),),  # re-asserted for this firmware only
    )
    leaf = Profile(
        id="leaf",
        match=Match(model=b"HPTS-50", firmware=(6, 5)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="mid",
    )
    registry = {"gp": grandparent, "mid": middle, "leaf": leaf}
    assert resolve_inherits(registry, "mid").field_map["setpoint"].write is Trust.OK
    # The leaf did not re-assert it, so the middle hop's OK does not carry down.
    assert (
        resolve_inherits(registry, "leaf").field_map["setpoint"].write
        is Trust.UNVERIFIED
    )


def test_resolve_inherits_respects_removes():
    spec = FieldSpec(block=2, param=7, words=1, codec="u16", read=Trust.OK)
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("fault", spec),),
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
        removes=frozenset({"fault"}),
    )
    registry = {"parent": parent, "child": child}
    resolved = resolve_inherits(registry, "child")
    assert "fault" not in resolved.field_map


def test_resolve_inherits_detects_cycles():
    a = Profile(id="a", match=None, min_setpoint_f=95, max_setpoint_f=130, inherits="b")
    b = Profile(id="b", match=None, min_setpoint_f=95, max_setpoint_f=130, inherits="a")
    registry = {"a": a, "b": b}
    with pytest.raises(ValidationError, match="cycle"):
        resolve_inherits(registry, "a")


def test_resolve_inherits_detects_a_self_cycle():
    a = Profile(id="a", match=None, min_setpoint_f=95, max_setpoint_f=130, inherits="a")
    with pytest.raises(ValidationError, match="cycle"):
        resolve_inherits({"a": a}, "a")


def test_resolve_inherits_rejects_an_unknown_parent_id():
    child = Profile(
        id="child",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="nope",
    )
    with pytest.raises(ValidationError, match="unknown profile id"):
        resolve_inherits({"child": child}, "child")


def test_resolve_inherits_requires_the_child_to_declare_its_own_match():
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
    )
    child = Profile(
        id="child", match=None, min_setpoint_f=95, max_setpoint_f=130, inherits="parent"
    )
    with pytest.raises(ValidationError, match="match is required"):
        resolve_inherits({"parent": parent, "child": child}, "child")


def test_resolve_inherits_no_op_when_no_parent():
    profile = Profile(
        id="solo", match=_minimal_match(), min_setpoint_f=95, max_setpoint_f=130
    )
    assert resolve_inherits({"solo": profile}, "solo") is profile


def test_resolve_inherits_is_idempotent():
    ok_write = FieldSpec(
        block=11, param=0, words=1, codec="c256", read=Trust.OK, write=Trust.OK
    )
    parent = Profile(
        id="parent",
        match=_minimal_match(),
        min_setpoint_f=95,
        max_setpoint_f=130,
        fields=(("setpoint", ok_write),),
    )
    child = Profile(
        id="child",
        match=Match(model=b"HPTS-50", firmware=(6, 4)),
        min_setpoint_f=95,
        max_setpoint_f=130,
        inherits="parent",
    )
    resolved = resolve_inherits({"parent": parent, "child": child}, "child")
    # Re-resolving must not demote a second time or otherwise drift.
    again = resolve_inherits({"child": resolved}, "child")
    assert again is resolved
    assert again.inherits is None
    assert again.removes == frozenset()


def test_field_name_members_equal_their_plain_string_value():
    assert FieldName.SETPOINT == "setpoint"
    assert hash(FieldName.SETPOINT) == hash("setpoint")


def test_field_name_is_usable_as_a_plain_string_dict_key():
    # A dict keyed by the enum must still be reachable by the bare string --
    # this is the property that keeps the migration in bundled.py (Task 4)
    # from breaking every existing string-keyed field_map lookup at once.
    d = {FieldName.MODE: "x"}
    assert d["mode"] == "x"


def test_field_name_has_one_member_per_bundled_field():
    expected = {
        "setpoint",
        "mode",
        "fault",
        "model",
        "serial",
        "vacation_days_remaining",
        "guest_days_remaining",
        "electric_days_remaining",
    }
    assert {member.value for member in FieldName} == expected
