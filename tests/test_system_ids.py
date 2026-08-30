"""사용자가 내부 ID를 정하지 않는 중앙 채번 계약."""
import re

import pytest

from core.system_ids import OBJECT_PREFIXES, allocate, is_system_id


@pytest.mark.parametrize("kind,prefix", sorted(OBJECT_PREFIXES.items()))
def test_object_type_has_one_opaque_prefix(kind, prefix):
    values = allocate(kind, 3)
    assert len(values) == len(set(values)) == 3
    assert all(re.fullmatch(fr"{prefix}_[0-9a-f]{{20}}", value) for value in values)
    assert all(is_system_id(value, kind) for value in values)


def test_allocator_rejects_unknown_type_and_bulk_abuse():
    with pytest.raises(ValueError):
        allocate("user_supplied_kind")
    for count in (0, 21):
        with pytest.raises(ValueError):
            allocate("agent", count)


def test_different_object_types_never_share_prefix():
    prefixes = list(OBJECT_PREFIXES.values())
    assert len(prefixes) == len(set(prefixes))
    assert not is_system_id(allocate("agent")[0], "workflow")
