"""Phase 2, step 2b: read the prices in a CMS hospital price file.

Supports the three CMS layouts (JSON, CSV "tall", CSV "wide") for template
versions 2.x and 3.x. Every published amount becomes one ParsedPrice; anything
that cannot be read exactly becomes a RejectedRow with a reason. Nothing is
guessed:

- amounts and percentages go through procedurescout_core.money (Decimal,
  never rounded, blanks stay None, negative or malformed values are refused);
- a negotiated rate needs a payer, a plan and a methodology, as CMS requires;
  otherwise it is refused, not filled in;
- the code type must be one of the CMS code types; the item is stored under
  its most specific code (CODE_PRIORITY) and the other codes are kept as
  published in other_codes;
- payer and plan names are kept exactly as published (matching to canonical
  payers happens later, only through approved aliases);
- a CSV cell that is not valid UTF-8 is decoded as Windows-1252 and the price
  is flagged (`text_decoded_cp1252`).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator, Sequence
from decimal import Decimal, InvalidOperation
from typing import IO, Any, cast

import ijson  # type: ignore[import-untyped]

from procedurescout_core.enums import (
    BillingClass,
    CodeSystem,
    FileFormat,
    Methodology,
    PriceType,
    ServiceSetting,
)
from procedurescout_core.money import MoneyParseError, parse_dollar, parse_percentage

from .base import ParsedPrice, RejectedRow

PARSER_VERSION = "cms-mrf@1"

# Most specific first. An item with CPT 70450 + RC 0350 + CDM 12345 is stored
# under CPT; the others go to other_codes.
CODE_PRIORITY: tuple[CodeSystem, ...] = (
    CodeSystem.MS_DRG,
    CodeSystem.APR_DRG,
    CodeSystem.MS_LTC_DRG,
    CodeSystem.DRG,
    CodeSystem.R_DRG,
    CodeSystem.S_DRG,
    CodeSystem.APS_DRG,
    CodeSystem.AP_DRG,
    CodeSystem.TRIS_DRG,
    CodeSystem.CPT,
    CodeSystem.HCPCS,
    CodeSystem.CDT,
    CodeSystem.NDC,
    CodeSystem.HIPPS,
    CodeSystem.APC,
    CodeSystem.EAPG,
    CodeSystem.CMG,
    CodeSystem.ICD,
    CodeSystem.RC,
    CodeSystem.LOCAL,
    CodeSystem.CDM,
)
_CODE_SYSTEMS = {c.value: c for c in CodeSystem}
_METHODOLOGY = {
    "case rate": Methodology.CASE_RATE,
    "fee schedule": Methodology.FEE_SCHEDULE,
    "percent of total billed charges": Methodology.PERCENT_OF_TOTAL_BILLED_CHARGES,
    "per diem": Methodology.PER_DIEM,
    "other": Methodology.OTHER,
}
_SETTING = {s.value: s for s in ServiceSetting}
_BILLING = {b.value: b for b in BillingClass}
DRUG_UNIT_TYPES = frozenset({"GR", "ML", "ME", "UN", "F2", "GM", "EA"})
MAX_EXAMPLES = 5


def _text(value: object) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _word(value: object) -> str | None:
    s = _text(value)
    return " ".join(s.replace("_", " ").split()).casefold() if s else None


def code_system(raw: object) -> CodeSystem | None:
    s = _text(raw)
    if s is None:
        return None
    return _CODE_SYSTEMS.get(re.sub(r"[\s_]+", "-", s.upper()))


def _count(raw: object) -> str | None:
    s = _text(raw)
    if s is None:
        return None
    if s in ("0", "1 through 10"):
        return s
    if s.isdigit() and int(s) >= 11:
        return str(int(s))
    raise ValueError(f"count {s!r} is not '0', '1 through 10' or a number >= 11")


class _Item:
    """What a charge item shares across its prices."""

    def __init__(
        self,
        ref: str,
        codes: Sequence[tuple[object, object]],
        description: object,
        drug_unit: object,
        drug_type: object,
        flags: tuple[str, ...] = (),
    ) -> None:
        self.ref = ref
        self.problem: str | None = None
        self.flags = list(flags)
        found: list[tuple[CodeSystem, str]] = []
        unknown: list[str] = []
        for ctype, code in codes:
            c = _text(code)
            if c is None:
                continue
            system = code_system(ctype)
            if system is None:
                unknown.append(f"{_text(ctype)}:{c}")
            else:
                found.append((system, c))
        if not found:
            self.problem = "no_code" if not unknown else "unknown_code_type"
            self.unknown = unknown
            return
        found.sort(key=lambda sc: CODE_PRIORITY.index(sc[0]))
        self.system, self.code = found[0]
        self.other = tuple(f"{s.value}:{c}" for s, c in found[1:]) + tuple(unknown)
        self.description = _text(description)
        self.drug_unit: Decimal | None = None
        self.drug_type: str | None = None
        unit, dtype = _text(drug_unit), _text(drug_type)
        if unit or dtype:
            # kept only when both parts are usable; the flag says which part was not
            try:
                value: Decimal | None = Decimal(unit or "")
                if value is not None and (not value.is_finite() or value <= 0):
                    value = None
            except InvalidOperation:
                value = None
            dtype_ok = (dtype or "").upper() in DRUG_UNIT_TYPES
            if value is None:
                self.flags.append("drug_unit_amount_unreadable")
            elif not dtype_ok:
                self.flags.append("drug_unit_type_unknown")
            else:
                self.drug_unit, self.drug_type = value, (dtype or "").upper()

    def price(self, ref: str, ptype: PriceType, **kw: Any) -> ParsedPrice:
        flags = tuple(self.flags) + tuple(kw.pop("flags", ()))
        return ParsedPrice(
            raw_row_ref=ref,
            code_system=self.system,
            code=self.code,
            price_type=ptype,
            description_raw=self.description,
            drug_unit=self.drug_unit,
            drug_unit_type=self.drug_type,
            other_codes=self.other,
            quality_flags=flags,
            **kw,
        )


_CENT_HUNDREDTH = Decimal("0.0001")


def _amount_flags(amount: Decimal | None) -> tuple[str, ...]:
    if amount is None:
        return ()
    flags = []
    if amount == 0:
        flags.append("zero_amount")
    if amount != amount.quantize(_CENT_HUNDREDTH, rounding="ROUND_DOWN"):
        flags.append("more_than_4_decimals")  # stored exactly; shown rounded
    return tuple(flags)


def _column(name: str) -> str:
    """Column names compared without case or spaces around '|' ('code |1' = 'code|1')."""
    return re.sub(r"\s*\|\s*", "|", name.strip()).casefold()


def _label(name: str) -> str:
    """A payer or plan label inside one file's column names, compared without
    case or extra spaces. Only used to group one file's own columns (dollar,
    percentage, methodology...) for the same payer and plan; the name stored is
    the label as first published."""
    return " ".join(name.split()).casefold()


def _amount_prices(
    item: _Item,
    ref: str,
    common: dict[str, Any],
    values: Sequence[tuple[PriceType, object]],
) -> Iterator[ParsedPrice | RejectedRow]:
    for ptype, raw in values:
        try:
            amount = parse_dollar(raw)
        except MoneyParseError as exc:
            yield RejectedRow(ref, "bad_amount", f"{ptype.value}: {exc}")
            continue
        if amount is None:
            continue
        flags = _amount_flags(amount)
        yield item.price(ref, ptype, amount=amount, flags=flags, **common)


def _payer_prices(
    item: _Item,
    ref: str,
    common: dict[str, Any],
    payer: object,
    plan: object,
    fields: dict[str, object],
) -> Iterator[ParsedPrice | RejectedRow]:
    """One payer/plan's numbers for one item. `fields` keys: dollar, percentage,
    algorithm, methodology, notes, estimated, median, p10, p90, count."""
    payer_name, plan_name = _text(payer), _text(plan)
    notes = _text(fields.get("notes"))
    try:
        dollar = parse_dollar(fields.get("dollar"))
        pct = parse_percentage(fields.get("percentage"))
    except MoneyParseError as exc:
        yield RejectedRow(ref, "bad_amount", f"negotiated: {exc}")
        dollar = pct = None
        fields = {**fields, "algorithm": None}
    algorithm = _text(fields.get("algorithm"))
    has_negotiated = dollar is not None or pct is not None or algorithm is not None
    allowed = [
        (PriceType.ESTIMATED_ALLOWED, fields.get("estimated")),
        (PriceType.MEDIAN_ALLOWED, fields.get("median")),
        (PriceType.P10_ALLOWED, fields.get("p10")),
        (PriceType.P90_ALLOWED, fields.get("p90")),
    ]
    has_allowed = any(_text(v) is not None for _, v in allowed)
    if not has_negotiated and not has_allowed:
        return
    if payer_name is None or plan_name is None:
        yield RejectedRow(ref, "missing_payer_or_plan", f"payer {payer_name!r}, plan {plan_name!r}")
        return
    who = {"payer_name_raw": payer_name, "plan_name_raw": plan_name}
    if has_negotiated:
        method_raw = _word(fields.get("methodology"))
        methodology = _METHODOLOGY.get(method_raw or "")
        if methodology is None:
            rule = "missing_methodology" if method_raw is None else "unknown_methodology"
            yield RejectedRow(ref, rule, f"negotiated rate with methodology {method_raw!r}")
        else:
            flags = _amount_flags(dollar)
            yield item.price(
                ref,
                PriceType.NEGOTIATED,
                amount=dollar,
                percentage=pct,
                algorithm=algorithm,
                methodology=methodology,
                additional_notes_raw=notes,
                flags=flags,
                **who,
                **common,
            )
    count: str | None = None
    count_flag: tuple[str, ...] = ()
    try:
        count = _count(fields.get("count"))
    except ValueError:
        count_flag = ("allowed_count_unreadable",)
    for ptype, raw in allowed:
        try:
            amount = parse_dollar(raw)
        except MoneyParseError as exc:
            yield RejectedRow(ref, "bad_amount", f"{ptype.value}: {exc}")
            continue
        if amount is None:
            continue
        is_pct = ptype in (PriceType.MEDIAN_ALLOWED, PriceType.P10_ALLOWED, PriceType.P90_ALLOWED)
        yield item.price(
            ref,
            ptype,
            amount=amount,
            allowed_count_raw=count if is_pct else None,
            additional_notes_raw=notes,
            flags=count_flag if is_pct else (),
            **who,
            **common,
        )


# ------------------------------------------------------------------ JSON
def parse_json(stream: IO[bytes]) -> Iterator[ParsedPrice | RejectedRow]:
    items = ijson.items(stream, "standard_charge_information.item", use_float=False)
    for i, raw in enumerate(items):
        ref = f"standard_charge_information[{i}]"
        if not isinstance(raw, dict):
            yield RejectedRow(ref, "not_an_object", "charge item is not a JSON object")
            continue
        codes = [
            (c.get("type"), c.get("code"))
            for c in raw.get("code_information") or []
            if isinstance(c, dict)
        ]
        drug = raw.get("drug_information") or {}
        if not isinstance(drug, dict):
            drug = {}
        item = _Item(ref, codes, raw.get("description"), drug.get("unit"), drug.get("type"))
        if item.problem:
            yield RejectedRow(ref, item.problem, f"codes: {getattr(item, 'unknown', [])}")
            continue
        for j, sc in enumerate(raw.get("standard_charges") or []):
            if not isinstance(sc, dict):
                continue
            sref = f"{ref}.standard_charges[{j}]"
            common = _common(sc.get("setting"), sc.get("billing_class"), sc.get("modifiers"))
            notes = _text(sc.get("additional_generic_notes"))
            yield from _amount_prices(
                item,
                sref,
                {**common, "additional_notes_raw": notes},
                [
                    (PriceType.GROSS, sc.get("gross_charge")),
                    (PriceType.DISCOUNTED_CASH, sc.get("discounted_cash")),
                    (PriceType.DEIDENTIFIED_MIN, sc.get("minimum")),
                    (PriceType.DEIDENTIFIED_MAX, sc.get("maximum")),
                ],
            )
            for k, p in enumerate(sc.get("payers_information") or []):
                if not isinstance(p, dict):
                    continue
                yield from _payer_prices(
                    item,
                    f"{sref}.payers_information[{k}]",
                    common,
                    p.get("payer_name"),
                    p.get("plan_name"),
                    {
                        "dollar": p.get("standard_charge_dollar"),
                        "percentage": p.get("standard_charge_percentage"),
                        "algorithm": p.get("standard_charge_algorithm"),
                        "methodology": p.get("methodology"),
                        "notes": p.get("additional_payer_notes"),
                        "estimated": p.get("estimated_amount"),
                        "median": p.get("median_amount"),
                        "p10": p.get("10th_percentile"),
                        "p90": p.get("90th_percentile"),
                        "count": p.get("count"),
                    },
                )


def _common(setting: object, billing: object, modifiers: object) -> dict[str, Any]:
    mods: tuple[str, ...] = ()
    if isinstance(modifiers, list):
        mods = tuple(m for m in (_text(x) for x in modifiers) if m)
    elif _text(modifiers):
        mods = tuple(m.strip() for m in str(modifiers).split("|") if m.strip())
    return {
        "setting": _SETTING.get(_word(setting) or ""),
        "billing_class": _BILLING.get(_word(billing) or ""),
        "modifiers": mods,
    }


# ------------------------------------------------------------------ CSV
def _fix_cell(cell: str) -> tuple[str, bool]:
    """Cells were decoded as UTF-8 with surrogateescape; re-decode any cell
    with stray bytes as Windows-1252."""
    try:
        cell.encode("utf-8")
        return cell, False
    except UnicodeEncodeError:
        raw = cell.encode("utf-8", "surrogateescape")
        return raw.decode("cp1252", errors="replace"), True


def _csv_rows(stream: IO[bytes]) -> Iterator[tuple[list[str], bool]]:
    wrapper = io.TextIOWrapper(
        cast(io.BufferedReader, stream),
        encoding="utf-8-sig",
        errors="surrogateescape",
        newline="",
    )
    for row in csv.reader(wrapper):
        fixed = False
        out = []
        for cell in row:
            value, changed = _fix_cell(cell)
            fixed = fixed or changed
            out.append(value)
        yield out, fixed


_ALLOWED_PREFIX = {
    "estimated_amount": "estimated",
    "median_amount": "median",
    "10th_percentile": "p10",
    "90th_percentile": "p90",
    "count": "count",
    "additional_payer_notes": "notes",
}
_NEGOTIATED_FIELD = {
    "negotiated_dollar": "dollar",
    "negotiated_percentage": "percentage",
    "negotiated_algorithm": "algorithm",
    "methodology": "methodology",
}


def parse_csv(stream: IO[bytes]) -> Iterator[ParsedPrice | RejectedRow]:
    rows = _csv_rows(stream)
    try:
        next(rows)  # header labels
        next(rows)  # header values
        columns, _ = next(rows)
    except StopIteration:
        yield RejectedRow("row 3", "not_cms_csv", "fewer than three rows")
        return
    cols = [_column(c) for c in columns]
    idx: dict[str, int] = {}
    for i, c in enumerate(cols):
        idx.setdefault(c, i)
    code_cols = []
    n = 1
    while f"code|{n}" in idx:
        code_cols.append((idx.get(f"code|{n}|type"), idx[f"code|{n}"]))
        n += 1
    tall = "payer_name" in idx
    groups: dict[tuple[str, str], dict[str, int]] = {}
    names: dict[tuple[str, str], tuple[str, str]] = {}
    if not tall:
        for i, col in enumerate(columns):
            parts = [p.strip() for p in col.split("|")]
            head = parts[0].casefold()
            field = None
            if head == "standard_charge" and len(parts) == 4:
                field = _NEGOTIATED_FIELD.get(parts[3].casefold())
            elif head in _ALLOWED_PREFIX and len(parts) == 3:
                field = _ALLOWED_PREFIX[head]
            if field and parts[1] and parts[2]:
                gkey = (_label(parts[1]), _label(parts[2]))
                names.setdefault(gkey, (parts[1], parts[2]))
                groups.setdefault(gkey, {})[field] = i
        if not groups and not any(c.startswith("standard_charge|gross") for c in cols):
            yield RejectedRow("row 3", "not_cms_csv", "no CMS price columns")
            return

    def cell(row: list[str], name: str) -> str | None:
        i = idx.get(name)
        return row[i] if i is not None and i < len(row) else None

    seen_items: set[int] = set()
    for line, (row, fixed) in enumerate(rows, start=4):
        if not any(c.strip() for c in row):
            continue
        ref = f"line {line}"
        codes = [
            (row[t] if t is not None and t < len(row) else None, row[c] if c < len(row) else None)
            for t, c in code_cols
        ]
        item = _Item(
            ref,
            codes,
            cell(row, "description"),
            cell(row, "drug_unit_of_measurement"),
            cell(row, "drug_type_of_measurement"),
            ("text_decoded_cp1252",) if fixed else (),
        )
        if item.problem:
            yield RejectedRow(ref, item.problem, f"codes: {getattr(item, 'unknown', [])}")
            continue
        common = _common(cell(row, "setting"), cell(row, "billing_class"), cell(row, "modifiers"))
        generic = [
            (PriceType.GROSS, cell(row, "standard_charge|gross")),
            (PriceType.DISCOUNTED_CASH, cell(row, "standard_charge|discounted_cash")),
            (PriceType.DEIDENTIFIED_MIN, cell(row, "standard_charge|min")),
            (PriceType.DEIDENTIFIED_MAX, cell(row, "standard_charge|max")),
        ]
        notes = _text(cell(row, "additional_generic_notes"))
        if tall:
            # gross/cash/min/max repeat on every payer row of the same item
            item_key = hash(
                (
                    item.system,
                    item.code,
                    item.other,
                    item.description,
                    common["setting"],
                    common["modifiers"],
                    tuple(v for _, v in generic),
                )
            )
            if item_key not in seen_items:
                seen_items.add(item_key)
                yield from _amount_prices(
                    item, ref, {**common, "additional_notes_raw": notes}, generic
                )
            yield from _payer_prices(
                item,
                ref,
                common,
                cell(row, "payer_name"),
                cell(row, "plan_name"),
                {
                    "dollar": cell(row, "standard_charge|negotiated_dollar"),
                    "percentage": cell(row, "standard_charge|negotiated_percentage"),
                    "algorithm": cell(row, "standard_charge|negotiated_algorithm"),
                    "methodology": cell(row, "standard_charge|methodology"),
                    "notes": cell(row, "additional_payer_notes"),
                    "estimated": cell(row, "estimated_amount"),
                    "median": cell(row, "median_amount"),
                    "p10": cell(row, "10th_percentile"),
                    "p90": cell(row, "90th_percentile"),
                    "count": cell(row, "count"),
                },
            )
        else:
            yield from _amount_prices(item, ref, {**common, "additional_notes_raw": notes}, generic)
            for gkey, where in groups.items():
                payer, plan = names[gkey]
                yield from _payer_prices(
                    item,
                    ref,
                    common,
                    payer,
                    plan,
                    {k: (row[i] if i < len(row) else None) for k, i in where.items()},
                )


def parse(stream: IO[bytes], file_format: FileFormat) -> Iterator[ParsedPrice | RejectedRow]:
    if file_format is FileFormat.JSON:
        return parse_json(stream)
    if file_format in (FileFormat.CSV_TALL, FileFormat.CSV_WIDE):
        return parse_csv(stream)
    raise ValueError(f"no price reader for format {file_format.value}")
