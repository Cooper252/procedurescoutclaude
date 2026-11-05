"""Domain enums. Values must match the PostgreSQL enum types in migration 0001.

tests/test_enums_match_db.py fails if the two drift apart.
"""

from __future__ import annotations

from enum import StrEnum


class FacilityType(StrEnum):
    ACUTE_CARE_HOSPITAL = "acute_care_hospital"
    CRITICAL_ACCESS_HOSPITAL = "critical_access_hospital"
    CHILDRENS_HOSPITAL = "childrens_hospital"
    PSYCHIATRIC_HOSPITAL = "psychiatric_hospital"
    REHABILITATION_HOSPITAL = "rehabilitation_hospital"
    LONG_TERM_CARE_HOSPITAL = "long_term_care_hospital"
    AMBULATORY_SURGERY_CENTER = "ambulatory_surgery_center"
    OTHER = "other"


class FacilityStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    CLOSED = "closed"


class CodeSystem(StrEnum):
    """Exactly the CMS v3.0 code_information.type values."""

    CPT = "CPT"
    HCPCS = "HCPCS"
    ICD = "ICD"
    DRG = "DRG"
    MS_DRG = "MS-DRG"
    R_DRG = "R-DRG"
    S_DRG = "S-DRG"
    APS_DRG = "APS-DRG"
    AP_DRG = "AP-DRG"
    APR_DRG = "APR-DRG"
    TRIS_DRG = "TRIS-DRG"
    APC = "APC"
    NDC = "NDC"
    HIPPS = "HIPPS"
    LOCAL = "LOCAL"
    EAPG = "EAPG"
    CDT = "CDT"
    RC = "RC"
    CDM = "CDM"
    CMG = "CMG"
    MS_LTC_DRG = "MS-LTC-DRG"


class ServiceSetting(StrEnum):
    INPATIENT = "inpatient"
    OUTPATIENT = "outpatient"
    BOTH = "both"


class CodeRole(StrEnum):
    PRIMARY = "primary"
    VARIANT = "variant"
    RELATED = "related"


class ReviewState(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class SuggestionSource(StrEnum):
    HUMAN = "human"
    AI_SUGGESTED = "ai_suggested"
    IMPORT = "import"


class ProductType(StrEnum):
    HMO = "hmo"
    PPO = "ppo"
    EPO = "epo"
    POS = "pos"
    HDHP = "hdhp"
    INDEMNITY = "indemnity"
    OTHER = "other"
    UNKNOWN = "unknown"


class PlanSegment(StrEnum):
    COMMERCIAL = "commercial"
    EXCHANGE = "exchange"
    EMPLOYER_SELF_FUNDED = "employer_self_funded"
    UNION_TRUST = "union_trust"
    MEDICARE_ADVANTAGE = "medicare_advantage"
    MEDICAID_MANAGED_CARE = "medicaid_managed_care"
    TRICARE_VA = "tricare_va"
    WORKERS_COMP = "workers_comp"
    OTHER = "other"
    UNKNOWN = "unknown"


class MatchType(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    MANUAL = "manual"
    UNMAPPED = "unmapped"


class DiscoveryMethod(StrEnum):
    CMS_HPT_TXT = "cms_hpt_txt"
    SITE_CRAWL = "site_crawl"
    INDEX_FILE = "index_file"
    MANUAL = "manual"


class FileFormat(StrEnum):
    JSON = "json"
    CSV_TALL = "csv_tall"
    CSV_WIDE = "csv_wide"
    ZIP = "zip"
    UNKNOWN = "unknown"


class ValidationState(StrEnum):
    NOT_VALIDATED = "not_validated"
    VALID = "valid"
    VALID_WITH_WARNINGS = "valid_with_warnings"
    INVALID = "invalid"
    UNSUPPORTED_VERSION = "unsupported_version"


class ImportState(StrEnum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    VALIDATING = "validating"
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    LOADING = "loading"
    QUALITY_REVIEW = "quality_review"
    PUBLISHED = "published"
    FAILED = "failed"
    STALE = "stale"
    RETIRED = "retired"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class DatasetStatus(StrEnum):
    STAGED = "staged"
    PUBLISHED = "published"
    RETIRED = "retired"


class BillingClass(StrEnum):
    FACILITY = "facility"
    PROFESSIONAL = "professional"
    BOTH = "both"


class PriceType(StrEnum):
    GROSS = "gross"
    DISCOUNTED_CASH = "discounted_cash"
    NEGOTIATED = "negotiated"
    DEIDENTIFIED_MIN = "deidentified_min"
    DEIDENTIFIED_MAX = "deidentified_max"
    MEDIAN_ALLOWED = "median_allowed"
    P10_ALLOWED = "p10_allowed"
    P90_ALLOWED = "p90_allowed"
    ESTIMATED_ALLOWED = "estimated_allowed"  # CMS v2.0/v2.2 only; removed in v3.0


class Methodology(StrEnum):
    CASE_RATE = "case_rate"
    FEE_SCHEDULE = "fee_schedule"
    PERCENT_OF_TOTAL_BILLED_CHARGES = "percent_of_total_billed_charges"
    PER_DIEM = "per_diem"
    OTHER = "other"


# Enum name in PostgreSQL (schema.type) -> Python enum. Used by the drift test.
DB_ENUMS: dict[str, type[StrEnum]] = {
    "ref.facility_type": FacilityType,
    "ref.facility_status": FacilityStatus,
    "ref.code_system": CodeSystem,
    "ref.service_setting": ServiceSetting,
    "ref.code_role": CodeRole,
    "ref.review_state": ReviewState,
    "ref.suggestion_source": SuggestionSource,
    "ref.product_type": ProductType,
    "ref.plan_segment": PlanSegment,
    "ref.match_type": MatchType,
    "src.discovery_method": DiscoveryMethod,
    "src.file_format": FileFormat,
    "src.validation_state": ValidationState,
    "src.import_state": ImportState,
    "src.severity": Severity,
    "src.dataset_status": DatasetStatus,
    "price.billing_class": BillingClass,
    "price.price_type": PriceType,
    "price.methodology": Methodology,
}
