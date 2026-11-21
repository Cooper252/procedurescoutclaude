"""Why a place in the results shows no price (Cooper, 2026-11-20)."""

from procedurescout_core.search import _reason


def test_each_place_without_a_price_says_why() -> None:
    assert _reason(True, None, None, None) == "prices"
    # posts a price list, but not this procedure (a psychiatric hospital and an MRI)
    assert _reason(False, "2026-11-01", None, "psychiatric_hospital") == "not_listed"
    # CMS's ownership for VA, military and Indian Health Service hospitals
    for owner in (
        "Veterans Health Administration",
        "Government - Federal",
        "Department of Defense",
        "Tribal",
    ):
        assert _reason(False, None, owner, "acute_care_hospital") == "federal"
    # a state or private hospital we don't have a price list for yet
    assert _reason(False, None, "Government - State", "psychiatric_hospital") == "no_file"
    assert _reason(False, None, "Voluntary non-profit - Private", None) == "no_file"
