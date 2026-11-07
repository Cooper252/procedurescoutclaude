from decimal import Decimal

import pytest

from procedurescout_core.money import MoneyParseError, parse_dollar, parse_percentage


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$1,234.50", Decimal("1234.50")),
        ("1234.5", Decimal("1234.5")),
        ("  42 ", Decimal("42")),
        ("0", Decimal("0")),
        ("0.0045", Decimal("0.0045")),  # per-unit drug prices can be sub-cent
        (".75", Decimal(".75")),
        (1500, Decimal("1500")),
        (Decimal("88.10"), Decimal("88.10")),
    ],
)
def test_dollar_parses_exactly(raw: object, expected: Decimal) -> None:
    result = parse_dollar(raw)
    assert result == expected
    assert isinstance(result, Decimal)


@pytest.mark.parametrize("raw", [None, "", "   ", "N/A", "na", "NaN", "null", "-", Decimal("NaN")])
def test_blank_dollar_is_none_never_zero(raw: object) -> None:
    assert parse_dollar(raw) is None


@pytest.mark.parametrize("raw", ["65%", "65 %", "100%"])
def test_percentage_rejected_by_dollar_parser(raw: str) -> None:
    with pytest.raises(MoneyParseError, match="percentage"):
        parse_dollar(raw)


@pytest.mark.parametrize("raw", ["-5", "(12.00)", "$-1"])
def test_negative_dollar_rejected(raw: str) -> None:
    with pytest.raises(MoneyParseError):
        parse_dollar(raw)


@pytest.mark.parametrize("raw", ["abc", "12.3.4", "1e5", "12 34", True])
def test_garbage_rejected(raw: object) -> None:
    with pytest.raises(MoneyParseError):
        parse_dollar(raw)


def test_float_rejected() -> None:
    with pytest.raises(MoneyParseError, match="float"):
        parse_dollar(12.5)


def test_sub_cent_values_kept_exactly() -> None:
    assert parse_dollar("2669.73225") == Decimal("2669.73225")
    assert parse_dollar("460.370000000001") == Decimal("460.370000000001")
    assert str(parse_dollar("2781.00000")) == "2781.00000"  # as published


def test_too_many_places_refused_not_rounded() -> None:
    with pytest.raises(MoneyParseError, match="refusing to round"):
        parse_dollar("1.1234567890123456")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("65", Decimal("65")), ("65%", Decimal("65")), (" 65.5 % ", Decimal("65.5")), (0, Decimal(0))],
)
def test_percentage_parses(raw: object, expected: Decimal) -> None:
    assert parse_percentage(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "N/A"])
def test_blank_percentage_is_none(raw: object) -> None:
    assert parse_percentage(raw) is None


@pytest.mark.parametrize("raw", ["1000.01", "$50", "-1", 0.65])
def test_bad_percentage_rejected(raw: object) -> None:
    with pytest.raises(MoneyParseError):
        parse_percentage(raw)
