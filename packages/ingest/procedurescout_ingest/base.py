"""Parser adapter interface. Concrete adapters (CMS JSON v2.x/v3.0,
CSV tall, CSV wide) arrive in Phase 2. Phase 0 defines only the contract."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from procedurescout_core.enums import (
    BillingClass,
    CodeSystem,
    FileFormat,
    Methodology,
    PriceType,
    ServiceSetting,
)


@dataclass(frozen=True, slots=True)
class ParsedPrice:
    """One amount from one source row, before normalization.

    Every raw value is kept as published; nothing here is canonical yet.
    """

    raw_row_ref: str  # line number or JSON path in the source file
    code_system: CodeSystem
    code: str
    price_type: PriceType
    amount: Decimal | None = None
    percentage: Decimal | None = None
    algorithm: str | None = None
    methodology: Methodology | None = None
    payer_name_raw: str | None = None
    plan_name_raw: str | None = None
    setting: ServiceSetting | None = None
    billing_class: BillingClass | None = None
    description_raw: str | None = None
    modifiers: tuple[str, ...] = field(default_factory=tuple)
    allowed_count_raw: str | None = None  # "0", "1 through 10", or digits >= 11
    additional_notes_raw: str | None = None


@dataclass(frozen=True, slots=True)
class RejectedRow:
    raw_row_ref: str
    rule: str
    message: str


class ParserAdapter(ABC):
    """Streams one file in bounded memory. One adapter per format + schema version."""

    #: e.g. "cms-json-2.x@1"; bumped whenever output can change.
    parser_version: str
    file_format: FileFormat
    supported_schema_versions: frozenset[str]

    @abstractmethod
    def detect(self, path: Path) -> bool:
        """Cheaply check whether this adapter can read the file."""

    @abstractmethod
    def parse(self, path: Path) -> Iterator[ParsedPrice | RejectedRow]:
        """Yield parsed amounts and rejected rows, never loading the whole file."""
