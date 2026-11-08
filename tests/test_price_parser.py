"""Phase 2 step 2b: reading prices from CMS files (synthetic files only)."""

import io
from collections import Counter
from decimal import Decimal
from pathlib import Path

from procedurescout_core.enums import CodeSystem, FileFormat, Methodology, PriceType
from procedurescout_ingest.base import ParsedPrice, RejectedRow
from procedurescout_ingest.price_parser import code_system, parse

FIX = Path(__file__).resolve().parent / "fixtures" / "price_files"


def run(name_or_bytes: str | bytes, fmt: FileFormat) -> tuple[list[ParsedPrice], list[RejectedRow]]:
    data = (FIX / name_or_bytes).read_bytes() if isinstance(name_or_bytes, str) else name_or_bytes
    out = list(parse(io.BytesIO(data), fmt))
    return (
        [r for r in out if isinstance(r, ParsedPrice)],
        [r for r in out if isinstance(r, RejectedRow)],
    )


def kinds(prices: list[ParsedPrice]) -> Counter[str]:
    return Counter(p.price_type.value for p in prices)


def test_json_prices() -> None:
    prices, rejects = run("synthetic_standardcharges.json", FileFormat.JSON)
    assert rejects == []
    assert kinds(prices) == {"gross": 2, "discounted_cash": 1, "negotiated": 3}
    a = [p for p in prices if p.code == "99999"]
    assert all(p.code_system is CodeSystem.CPT and p.other_codes == ("RC:0450",) for p in a)
    gross = next(p for p in a if p.price_type is PriceType.GROSS)
    assert gross.amount == Decimal("100.10") and gross.setting is not None
    pct = next(p for p in a if p.payer_name_raw == "Synthetic Payer Two")
    assert (pct.amount, pct.percentage, pct.methodology) == (
        None,
        Decimal("60"),
        Methodology.PERCENT_OF_TOTAL_BILLED_CHARGES,
    )
    drg = next(p for p in prices if p.code_system is CodeSystem.MS_DRG and p.payer_name_raw)
    assert (drg.amount, drg.methodology, drg.plan_name_raw) == (
        Decimal("20000"),
        Methodology.CASE_RATE,
        "PPO",
    )
    assert gross.raw_row_ref == "standard_charge_information[0].standard_charges[0]"


def test_csv_tall_prices_and_no_repeated_gross() -> None:
    prices, rejects = run("synthetic_standardcharges_tall.csv", FileFormat.CSV_TALL)
    assert rejects == []
    # item A's gross/cash/min/max appear on both payer rows but are stored once
    assert kinds(prices) == {
        "gross": 2,
        "discounted_cash": 1,
        "deidentified_min": 2,
        "deidentified_max": 2,
        "negotiated": 3,
    }
    assert {p.raw_row_ref for p in prices if p.price_type is PriceType.GROSS} == {
        "line 4",
        "line 6",
    }


def test_csv_wide_prices() -> None:
    prices, rejects = run("synthetic_standardcharges_wide.csv", FileFormat.CSV_WIDE)
    assert rejects == []
    negotiated = [p for p in prices if p.price_type is PriceType.NEGOTIATED]
    assert sorted((p.payer_name_raw or "", p.plan_name_raw or "") for p in negotiated) == [
        ("Synthetic Payer One", "PPO"),
        ("Synthetic Payer One", "PPO"),
        ("Synthetic Payer Two", "HMO"),
    ]
    assert kinds(prices)["gross"] == 2


HEAD = (
    b"hospital_name,last_updated_on,version\n"
    b"Synthetic Hospital,2026-01-01,2.2.0\n"
    b"description,code|1,code|1|type,code|2,code|2|type,setting,drug_unit_of_measurement,"
    b"drug_type_of_measurement,standard_charge|gross,standard_charge|discounted_cash,"
    b"payer_name,plan_name,standard_charge|negotiated_dollar,"
    b"standard_charge|negotiated_percentage,standard_charge|negotiated_algorithm,"
    b"estimated_amount,standard_charge|methodology,median_amount,count\n"
)


def test_refusals_are_explicit() -> None:
    body = (
        b"NO METHOD,11111,CPT,,,outpatient,,,10,,Synthetic Payer,PPO,9,,,,,,\n"
        b"NO PLAN,11112,CPT,,,outpatient,,,10,,Synthetic Payer,,9,,,,fee schedule,,\n"
        b"ODD METHOD,11113,CPT,,,outpatient,,,10,,Synthetic Payer,PPO,9,,,,magic,,\n"
        b"BAD CODE TYPE,11114,XYZ,,,outpatient,,,10,,,,,,,,,,\n"
        b"NO CODE,,,,,outpatient,,,10,,,,,,,,,,\n"
        b"NEGATIVE,11115,CPT,,,outpatient,,,-5,,,,,,,,,,\n"
        b"ROUNDING,11116,CPT,,,outpatient,,,1.1234567890123456,,,,,,,,,,\n"
    )
    prices, rejects = run(HEAD + body, FileFormat.CSV_TALL)
    rules = Counter(r.rule for r in rejects)
    assert rules == {
        "missing_methodology": 1,
        "missing_payer_or_plan": 1,
        "unknown_methodology": 1,
        "unknown_code_type": 1,
        "no_code": 1,
        "bad_amount": 2,
    }
    # the gross charges on the first three rows are still kept
    assert kinds(prices) == {"gross": 3}


def test_v2_estimates_drugs_cp1252_and_counts() -> None:
    body = (
        b"SYNTHETIC DRUG \x96 10MG,J9999,HCPCS,0636,RC,outpatient,2.5,ML,40,,"
        b"Synthetic Payer,PPO,30,,,28.50,fee schedule,,\n"
        b"SYNTHETIC ODD UNIT,J9998,HCPCS,,,outpatient,0,XX,40,,,,,,,,,,\n"
        b"SYNTHETIC ZERO,J9997,HCPCS,,,outpatient,,,0,,Synthetic Payer,PPO,,,,,,15,7\n"
    )
    prices, rejects = run(HEAD + body, FileFormat.CSV_TALL)
    assert rejects == []
    drug = next(p for p in prices if p.code == "J9999" and p.price_type is PriceType.GROSS)
    assert drug.description_raw == "SYNTHETIC DRUG \u2013 10MG"  # Windows-1252 dash
    assert "text_decoded_cp1252" in drug.quality_flags
    assert (drug.drug_unit, drug.drug_unit_type, drug.other_codes) == (
        Decimal("2.5"),
        "ML",
        ("RC:0636",),
    )
    est = next(p for p in prices if p.price_type is PriceType.ESTIMATED_ALLOWED)
    assert (est.amount, est.payer_name_raw) == (Decimal("28.50"), "Synthetic Payer")
    odd = next(p for p in prices if p.code == "J9998")
    assert odd.drug_unit is None and "drug_unit_amount_unreadable" in odd.quality_flags
    zero = next(p for p in prices if p.code == "J9997" and p.price_type is PriceType.GROSS)
    assert zero.amount == Decimal("0") and "zero_amount" in zero.quality_flags
    median = next(p for p in prices if p.price_type is PriceType.MEDIAN_ALLOWED)
    assert median.allowed_count_raw is None and "allowed_count_unreadable" in median.quality_flags


def test_code_type_spellings() -> None:
    assert code_system("ms-drg") is CodeSystem.MS_DRG
    assert code_system("MS DRG") is CodeSystem.MS_DRG
    assert code_system("apr_drg") is CodeSystem.APR_DRG
    assert code_system("cpt ") is CodeSystem.CPT
    assert code_system("CPT4") is None  # not a CMS code type: refused, not guessed


def test_spaced_column_names_and_payer_labels_in_different_case() -> None:
    # Seen in real Nevada files (run #12): "code |1" with a space, and a payer's
    # dollar column spelled differently from its methodology column.
    data = (
        b"hospital_name,last_updated_on,version\n"
        b"Synthetic Hospital,2026-01-01,2.0.0\n"
        b"description ,code |1,code|1|type,setting,standard_charge|gross,"
        b"standard_charge|Synthetic Health Plan NV | All|negotiated_dollar,"
        b"standard_charge|synthetic health plan nv|all|methodology,"
        b"standard_charge| Synthetic Blue  |All|negotiated_dollar,"
        b"standard_charge|synthetic blue|all|methodology\n"
        b"SYNTHETIC ROOM,101,RC,inpatient,1184,1065.60,per diem,1124.8,per diem\n"
    )
    prices, rejects = run(data, FileFormat.CSV_WIDE)
    assert rejects == []
    negotiated = sorted(
        (p.payer_name_raw or "", p.plan_name_raw or "", str(p.amount), str(p.methodology))
        for p in prices
        if p.price_type is PriceType.NEGOTIATED
    )
    assert negotiated == [
        ("Synthetic Blue", "All", "1124.8", "per_diem"),
        ("Synthetic Health Plan NV", "All", "1065.60", "per_diem"),
    ]
    gross = next(p for p in prices if p.price_type is PriceType.GROSS)
    assert (gross.code_system, gross.code, gross.description_raw) == (
        CodeSystem.RC,
        "101",
        "SYNTHETIC ROOM",
    )


def test_sub_cent_amounts_kept_and_flagged() -> None:
    body = b"SUB CENT,11117,CPT,,,outpatient,,,2669.73225,2781.00000,,,,,,,,,\n"
    prices, rejects = run(HEAD + body, FileFormat.CSV_TALL)
    assert rejects == []
    by = {p.price_type: p for p in prices}
    assert by[PriceType.GROSS].amount == Decimal("2669.73225")
    assert "more_than_4_decimals" in by[PriceType.GROSS].quality_flags
    assert "more_than_4_decimals" not in by[PriceType.DISCOUNTED_CASH].quality_flags


def test_likely_file_errors_are_flagged_not_dropped() -> None:
    body = (
        b"PENNY SURGERY,11118,CPT,,,outpatient,,,0.01,,,,,,,,,,\n"
        b"HUGE,11119,CPT,,,outpatient,,,12000000,,,,,,,,,,\n"
    )
    prices, rejects = run(HEAD + body, FileFormat.CSV_TALL)
    assert rejects == []
    flags = {p.code: p.quality_flags for p in prices}
    assert "under_one_dollar" in flags["11118"] and "over_ten_million" in flags["11119"]
