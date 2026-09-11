"""가격 정책 검토의 과거 시점 컷오프. 저장소를 사용하지 않는 순수 함수 시험."""
import copy
import pytest
from scripts.plan_kit_price_basis import eligible_observation


def observation(oid="a", **changes):
    return {"observation_id": oid, "commodity_code": "NICKEL", "observed_at": "2023-06-30",
            "published_at": "2023-07-07", "vintage_date": "2023-07-07", **changes}


def choose(rows):
    return eligible_observation(rows, code="NICKEL", pricing_date="2023-07-07")


def test_boundary_date_included_without_mutation():
    rows = [observation()]
    before = copy.deepcopy(rows)
    assert choose(rows)["observation_id"] == "a"
    assert rows == before


@pytest.mark.parametrize("field", ["observed_at", "published_at", "vintage_date"])
def test_any_future_timestamp_excluded(field):
    assert choose([observation(**{field: "2023-07-08"})]) is None


def test_future_revision_does_not_replace_historical_observation():
    assert choose([observation(), observation("revised", vintage_date="2024-01-01")])["observation_id"] == "a"


def test_latest_eligible_not_last_input_row():
    earlier = observation("old", observed_at="2023-05-31", published_at="2023-06-07", vintage_date="2023-06-07")
    assert choose([observation(), earlier])["observation_id"] == "a"


def test_different_commodity_does_not_fill_missing_quote():
    assert choose([observation(commodity_code="COPPER")]) is None


def test_empty_history_is_not_zero_price():
    assert choose([]) is None


def test_duplicate_time_is_not_arbitrarily_selected():
    with pytest.raises(ValueError):
        choose([observation(), observation("duplicate")])


def test_invalid_date_rejected():
    with pytest.raises(ValueError):
        choose([observation(published_at="2023-02-30")])
