"""Database-level guarantees against misleading prices (docs/DATA_QUALITY_RULES.md)."""

from decimal import Decimal

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from procedurescout_core.money import parse_dollar
from tests.conftest import insert_price


def test_blank_amount_stays_null_never_zero(conn: Connection) -> None:
    gross = parse_dollar("")  # blank cell in a hospital file
    assert gross is None
    insert_price(
        conn,
        price_type="negotiated",
        amount=gross,
        percentage=Decimal("65"),
        methodology="percent_of_total_billed_charges",
        payer_name_raw="Example Health Plan",
        plan_name_raw="Example PPO",
    )
    stored = conn.execute(text("SELECT amount FROM price.price")).scalar_one()
    assert stored is None


def test_amount_column_has_no_default(conn: Connection) -> None:
    default = conn.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema='price' AND table_name='price' AND column_name='amount'"
        )
    ).scalar_one()
    assert default is None


def test_exact_decimal_round_trip(conn: Connection) -> None:
    insert_price(conn, amount=Decimal("0.0045"))
    assert conn.execute(text("SELECT amount FROM price.price")).scalar_one() == Decimal("0.0045")


def test_row_without_any_value_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_has_value"):
        insert_price(conn, amount=None)


def test_negative_amount_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        insert_price(conn, amount=Decimal("-1"))


def test_negotiated_without_payer_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_payer_required"):
        insert_price(conn, price_type="negotiated", amount=Decimal("100"), methodology="case_rate")


def test_cash_price_with_payer_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_payer_forbidden"):
        insert_price(
            conn,
            price_type="discounted_cash",
            amount=Decimal("100"),
            payer_name_raw="Aetna",
            plan_name_raw="Aetna PPO",
        )


def test_percentage_on_gross_rejected(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_formula_only_negotiated"):
        insert_price(conn, price_type="gross", percentage=Decimal("50"))


def test_negotiated_needs_methodology(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_negotiated_needs_methodology"):
        insert_price(
            conn,
            price_type="negotiated",
            amount=Decimal("100"),
            payer_name_raw="Aetna",
            plan_name_raw="Aetna PPO",
        )


def test_derived_dollar_must_document_rule(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_derivation_documented"):
        insert_price(
            conn,
            price_type="negotiated",
            amount=Decimal("650"),
            percentage=Decimal("65"),
            methodology="percent_of_total_billed_charges",
            payer_name_raw="Aetna",
            plan_name_raw="Aetna PPO",
            amount_derived=True,
        )


def test_derived_dollar_with_rule_accepted(conn: Connection) -> None:
    insert_price(
        conn,
        price_type="negotiated",
        amount=Decimal("650"),
        percentage=Decimal("65"),
        methodology="percent_of_total_billed_charges",
        payer_name_raw="Aetna",
        plan_name_raw="Aetna PPO",
        amount_derived=True,
        derivation_rule="65% x published gross charge $1000 (same file, same item)",
    )


def test_cpt_descriptor_requires_license(conn: Connection) -> None:
    with pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO ref.code (system, code, version, descriptor, descriptor_source) "
                "VALUES ('CPT', '45378', '2026', 'official text', 'AMA')"
            )
        )


def test_cpt_code_without_descriptor_allowed(conn: Connection) -> None:
    conn.execute(
        text("INSERT INTO ref.code (system, code, version) VALUES ('CPT', '45378', '2026')")
    )


def test_only_one_published_dataset_per_facility(conn: Connection) -> None:
    from tests.conftest import make_dataset_version, make_facility

    facility = make_facility(conn)
    make_dataset_version(conn, facility, status="published")
    with pytest.raises(IntegrityError, match="dataset_version_one_published"):
        make_dataset_version(conn, facility, status="published")


def _allowed_amount_row(count: str) -> dict[str, object]:
    return {
        "price_type": "median_allowed",
        "amount": Decimal("1200.00"),
        "payer_name_raw": "Aetna",
        "plan_name_raw": "Aetna PPO",
        "allowed_count_raw": count,
    }


@pytest.mark.parametrize("count", ["0", "1 through 10", "11", "2025"])
def test_cms_allowed_count_values_accepted(conn: Connection, count: str) -> None:
    insert_price(conn, **_allowed_amount_row(count))


@pytest.mark.parametrize("count", ["5", "10", "2,025", "1-10", "abc"])
def test_invalid_allowed_count_rejected(conn: Connection, count: str) -> None:
    with pytest.raises(IntegrityError):
        insert_price(conn, **_allowed_amount_row(count))


def test_allowed_count_only_on_allowed_amount_rows(conn: Connection) -> None:
    with pytest.raises(IntegrityError, match="price_allowed_count_scope"):
        insert_price(conn, amount=Decimal("10"), allowed_count_raw="11")


@pytest.mark.parametrize("code_type", ["APC", "HIPPS", "MS-LTC-DRG", "CDT", "EAPG"])
def test_all_cms_v3_code_types_accepted(conn: Connection, code_type: str) -> None:
    insert_price(conn, amount=Decimal("10"), code_system=code_type, code="X1")
