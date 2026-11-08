# ruff: noqa: E501, RUF001  (one-off review script: long data tables copied from hospital files)
"""Draft plan-name proposals from the workflow export payer-plan-names.csv.

Every row is a PROPOSAL for Cooper to review (CLAUDE.md rules 9 and 10):
nothing here is approved. Output: proposals.csv (one row per hospital spelling).
"""

import csv
import re
import sys

src, out = sys.argv[1], sys.argv[2]

# hospital payer spelling (normalized) -> (insurer as on cards, kind, note)
# kind: insurer | network | employer | union | government | provider_group | exclude
P = {}


def add(names, insurer, kind="insurer", note=""):
    for n in names:
        P[n] = (insurer, kind, note)


add(["AETNA", "AETNA-ALL PLANS", "[PAYER_AETNA]"], "Aetna")
add(["AETNA MEDICARE", "[PAYER_AETNA MEDICARE]"], "Aetna", note="Medicare plans")
add(["STRATEGIC RESOURCE COMPANY (SRC)/AETNA STUDENT HEALTH"], "Aetna Student Health")
add(
    [
        "ANTHEM",
        "ANTHEM_BLUE_CROSS_BLUE_SHIELD",
        "ANTHEM BLUE CROSS BLUE SHIELD",
        "ANTHEM BCBS",
        "ANTHEM_BCBS",
        "ANTHEM_PATHWAY",
        "ANTHEM BCBS-ALL OTHER PLANS",
        "ANTHEM BCBS MCR ADV",
        "ANTHEM BCBS MCAID",
        "ANTHEM MEDICAID",
        "ELEVANCE (ANTHEM BCBS)",
        "BCBS - ANTHEM",
        "BLUE CROSS BLUE SHIELD OF NEVADA",
        "BLUE CROSS BLUE SHIELD OF NV ANTHEM",
        "BCBS OF NV",
        "ANTHEM BLUE CROSS BLUE SHIELD PATHWAY X",
        "ANTHEM BLUE CROSS BLUE SHIELD INDEMINITY",
        "[PAYER_BLUE CROSS OF NV]",
        "[PAYER_BLUE CROSS OF NV HMO]",
    ],
    "Anthem Blue Cross Blue Shield (Nevada)",
)
add(
    ["BLUE CROSS BLUE SHIELD MEDICARE"],
    "Anthem Blue Cross Blue Shield (Nevada)",
    note="says Blue Cross Blue Shield, not which state: check",
)
add(
    ["BCBS", "BLUE CROSS"],
    "Blue Cross Blue Shield (state not stated)",
    "exclude",
    "state not given; out-of-state Blues are different payers (rule 9)",
)
add(
    ["ANTHEM BLUE CROSS BLUE SHIELD COLORADO"],
    "Anthem Blue Cross Blue Shield (Colorado)",
    "exclude",
    "out-of-state Blue plan; not the Nevada plan",
)
add(["[PAYER_BCBS FEDERAL EMPLOYEE]"], "Blue Cross Blue Shield Federal Employee Program")
add(
    [
        "CIGNA",
        "CIGNA-ALL PLANS",
        "[PAYER_CIGNA]",
        "CIGNA_GREATWEST",
        "GREAT WEST HEALTHCARE",
        "GREAT WEST HEALTHCARE (MEDIVERSAL)",
        "EVERNORTH",
    ],
    "Cigna",
)
add(
    ["CIGNA HEALTHCARE & LIFE INSURANCE COMPANY – WY"],
    "Cigna (Wyoming company)",
    "exclude",
    "a Wyoming Cigna company; check before using for Nevada",
)
add(
    [
        "HUMANA",
        "HUMANAHCP",
        "HUMANA-MEDICARE ADVANTAGE",
        "HUMANA-COMMERICAL",
        "[PAYER_HUMANA MEDICARE]",
        "[PAYER_HUMANA GOLD]",
    ],
    "Humana",
)
add(
    [
        "UNITED",
        "UNITED HEALTHCARE",
        "UNITED_HEALTH_CARE",
        "UNITED_HEALTHCARE",
        "UHC",
        "UHC COMM-ALL OTHER PLANS",
        "UHC ADHOC",
        "UHC MCAID",
        "[PAYER_UHC MEDICARE]",
        "[PAYER_UHC MEDICARE SOLUTIONS]",
        "PACIFICARE OF NEVADA INC",
        "SENIOR DIMENSIONS",
    ],
    "UnitedHealthcare",
)
add(["SUREST"], "Surest (UnitedHealthcare)")
add(
    ["UMR", "[PAYER_UMR PPO]", "[PAYER_HR NEVADA UMR]", "[PAYER_UMR VENETIAN]"],
    "UMR (UnitedHealthcare)",
    note="UMR administers employer plans",
)
add(["GEHA-UHC"], "GEHA (UnitedHealthcare network)")
add(["GEHA"], "GEHA")
add(
    [
        "SIERRA_HEALTH_PLAN_OF_NEVADA",
        "HEALTH PLAN OF NV",
        "HEALTH PLAN NEVADA",
        "HEALTHPLAN NEVADA",
        "HEALTH PLAN OF NEVADA",
        "SIERRA HPN",
        "SIERRA/HPN",
        "SIERRA HEALTH PLAN NV",
        "HPN MEDICAID",
        "SIERRA (HPN) MEDICAID",
        "[PAYER_HPN MEDICAID]",
        "[PAYER_HPN COMMERCIAL]",
        "SMART_CHOICE",
        "SIERRA_SMART_CHOICE",
        "VHS_EMPLOYEES_HPN",
        "SR_CARE_PLUS",
    ],
    "Health Plan of Nevada (HPN)",
)
add(
    ["SIERRA_HEALTH_OPTIONS", "SIERRA HEALTH OPTIONS", "SIERRA HEALTHCARE OPTIONS"],
    "Sierra Health Options",
)
add(
    ["SIERRA HEALTH AND LIFE", "NEVADA_SIERRA_HEALTH_&_LIFE", "[PAYER_SIERRA HEALTH & LIFE]"],
    "Sierra Health and Life",
)
add(
    ["SIERRA", "SIERRA-ALL PLANS", "SIERRA HEALTH"],
    "Sierra Health (company not stated)",
    note="could be HPN, Sierra Health and Life or Sierra Health Options",
)
add(
    ["PROMINENCE", "PROMINENCE HEALTH PLAN", "[PAYER_PROMINENCE HEALTH PLAN]"],
    "Prominence Health Plan",
)
add(
    [
        "PROMINENCE HEALTHFIRST",
        "PROMINENCE HEALTH FIRST",
        "PROMINENCE HEALTHFIRST (FKA NV PREFERRED HEALTHCARE PROVIDERS)",
        "NEVADA_PREFERRED_PROVIDERS",
        "NV PREFERRED",
    ],
    "Prominence HealthFirst (formerly Nevada Preferred)",
    "network",
    "a provider network; your card may show its logo",
)
add(
    [
        "HOMETOWN HEALTH",
        "HOMETOWN HEALTH PLAN OF NEVADA",
        "HOMETOWN HEALTH PLAN NEVADA",
        "HOMETOWN HEALTH PLAN NV",
        "HOMETOWN HEALTH PLAN",
        "HOMETOWN HEALTH PROVIDERS",
        "HOMETOWN HEALTH MCR",
        "[PAYER_HOMETOWN HEALTH]",
    ],
    "Hometown Health",
)
add(["HOME TOWN TEST"], "test entry", "exclude", "a test row in the hospital file")
add(
    [
        "SILVER SUMMIT",
        "SILVER_SUMMIT",
        "SILVERSUMMIT",
        "SILVERSUMMITHEALTHPLAN",
        "SILVERSUMMIT HEALTHPLAN",
        "SILVER SUMMIT HEALTH PLAN (CENTENE)",
        "SILVERSUMMIT MEDICARE",
        "[PAYER_SILVERSUMMIT HEALTHPLAN]",
        "AMBETTER",
        "[PAYER_AMBETTER SILVERSUMMIT]",
        "ALLWELL",
        "[PAYER_ALLWELL SILVERSUMMIT]",
        "CENTENE",
        "WELLCARE",
    ],
    "SilverSummit Healthplan (Centene)",
    note="Ambetter and Allwell are SilverSummit products",
)
add(
    [
        "MOLINA",
        "MOLINA HEALTHCARE",
        "MOLINA HEALTHCARE OF NV",
        "MOLINA MEDICAID",
        "MOLINA NV",
        "[PAYER_MOLINA MEDICAID NV]",
    ],
    "Molina Healthcare",
)
add(["CARESOURCE", "CARE SOURCE", "CARESOURCE MEDICAID"], "CareSource")
add(
    [
        "SELECT HEALTH",
        "SELECTHEALTH",
        "SELECT_HEALTH",
        "SELECTHEALTH MCARE-ALL PLANS",
        "[PAYER_SELECT HEALTH]",
        "[PAYER_SELECT HEALTH IHC]",
        "INTERMOUNTAIN",
        "INTERMOUNTAIN HEALTHCARE (HCP)",
    ],
    "Select Health (Intermountain)",
)
add(["KAISER"], "Kaiser Permanente")
add(["OSCAR"], "Oscar Health")
add(["HEALTH NET"], "Health Net")
add(["IMPERIAL INSURANCE COMPANY", "IMPERIAL INSURANCE COMPANIES"], "Imperial Insurance Companies")
add(["SAINT MARY HEALTH PLAN", "SAINT MARY'S HEALTH PLAN"], "Saint Mary's Health Plan")
add(
    [
        "ALIGNMENT",
        "ALIGNMENT HEALTH",
        "ALIGNMENT HEALTH PLAN",
        "ALIGNMENT_HEALTH",
        "ALIGNMENT MEDICARE",
    ],
    "Alignment Health",
)
add(["SCAN", "[PAYER_SCAN HEALTH PLAN]"], "SCAN Health Plan")
add(["CAREMORE", "CAREMORE_HEALTH", "[PAYER_CAREMORE]"], "CareMore Health")
add(["ADVANTRA FREEDOM"], "Advantra (Coventry Medicare)")
add(["MAIL HANDLERS BENEFIT PLAN"], "Mail Handlers Benefit Plan")
add(["AMERICAN POSTAL WORKERS HEALTH PLAN"], "APWU Health Plan")
add(["[PAYER_GOLDEN RULE]"], "Golden Rule (UnitedHealthcare)")
add(["[PAYER_MERITAIN HEALTH]"], "Meritain Health", note="administers employer plans")
add(
    ["HEALTHSCOPE", "[PAYER_HEALTHSCOPE-CLARK COUNTY]", "[PAYER_PEBP HEALTHSCOPE]"],
    "HealthSCOPE Benefits",
    note="administers employer plans (e.g. Clark County, Nevada PEBP)",
)
add(
    ["CULINARY HEALTH FUND", "CULINARY WORKERS HWF", "[PAYER_CULINARY HEALTH PLAN]"],
    "Culinary Health Fund",
    "union",
    "",
)
add(
    [
        "HEALTH_SERVICES_COALITION",
        "HEALTH SERVICES COALITION",
        "HEALTHSERVICESCOALITION",
        "COALITION",
        "BUSINESS_COALITION",
        "LAUGHLIN COALITION",
    ],
    "Health Services Coalition",
    "network",
    "Las Vegas employers' and unions' purchasing coalition; your card may show it",
)
add(["TRADITIONAL MEDICARE", "[PAYER_MEDICARE]"], "Original Medicare", "government")
add(["TRADITIONAL MEDICAID", "[PAYER_MEDICAID]"], "Nevada Medicaid (fee for service)", "government")
add(
    [
        "TRICARE",
        "[PAYER_TRICARE]",
        "TRIWEST",
        "TRIWEST HEALTHCARE ALLIANCE",
        "HEALTH NET FEDERAL SERVICES TRICARE",
    ],
    "TRICARE",
    "government",
    "TriWest runs TRICARE West",
)
add(
    ["TRIWEST HEALTHCARE ALLIANCE CORP - VA CCN", "VA PC3 (VA CHOICE)"],
    "VA Community Care",
    "government",
)
add(["[PAYER_CHAMPVA]"], "CHAMPVA", "government")
for n in [
    "MULTIPLAN",
    "MULTIPLAN COMPLEMENTARY NETWORK",
    "MULTIPLAN PRIMARY NETWORK-ALL OTHER PLANS",
]:
    P[n] = (
        "MultiPlan",
        "network",
        "a network many employer plans rent; your card may show its logo",
    )
add(["PHCS"], "PHCS (MultiPlan)", "network", "a MultiPlan network; your card may show its logo")
add(["BEECH STREET", "BEECHSTREET"], "Beech Street", "network", "a rental network")
add(
    ["FIRST HEALTH", "FIRST_HEALTH_NETWORK"],
    "First Health (Aetna)",
    "network",
    "an Aetna-owned rental network",
)
add(["COVENTRY"], "Coventry (Aetna)", "network", "Aetna-owned network")
add(["THREE RIVERS PROVIDER NETWORK", "THREE RIVERS"], "Three Rivers Provider Network", "network")
add(
    [
        "UNIVERSAL HEALTH NETWORK (UHN)",
        "UNIVERSAL HEALTH NETOWRK",
        "UHN-UNIVERSAL HEALTH NETWORK",
        "UNIVERSAL HEALTHCARE",
    ],
    "Universal Health Network",
    "network",
)
add(["NEVADA PREFERRED PROFESSIONALS"], "Nevada Preferred Professionals", "network")
add(
    [
        "CMN GLOBAL",
        "OLYMPUS MEDSAVE USA",
        "MEDCARE INTERNATIONAL",
        "SIX DEGREES HEALTH",
        "6 DEGREES",
        "6 DEGREES HEALTH",
        "ACCESS TO HEALTHCARE NETWORK",
        "HEALTH DIRECT PARTNERS",
        "EMPLOYER DIRECT",
        "EMPLOYER DIRECT HEALTHCARE",
        "ASSERTA HEALTH",
        "FIRST CHOICE",
        "CORVEL",
        "NATIONAL HEALTHCARE SOLUTIONS, INC",
        "OCCUNET",
        "AFFILIATED",
        "PROVIDER SELECT",
        "KEENAN",
        "NORTHERN NV HEALTH NTWRK",
        "BARINET",
        "EMERGING THERAPY SOLUTIONS",
        "COMMUNITY CARE HEALTH",
        "[PAYER_COMMUNITY CARE HEALTH PLA]",
    ],
    None,
    "network",
    "a network or repricing company, not something most people see on a card",
)
add(
    [
        "P3 HEALTH PARTNERS",
        "P3 HEALTH PARTNERS NEVADA",
        "P3",
        "[PAYER_P3 HEALTH PARTNERS]",
        "[PAYER_P3 HEALTH PARTNERS IHC]",
        "OPTUMCARE",
        "OPTUM",
        "OPTUM MEDICARE",
        "OPTUM HEALTH",
        "HEALTHCARE PARTNERS OF NEVADA",
        "HEALTHCARE PARTNERS OF NV",
        "NEVADA HEALTH PARTNERS",
        "DIGNITY HEALTH",
        "BANNER HEALTH",
    ],
    None,
    "provider_group",
    "a doctor group or health system that manages care for an insurer's plans; match through the insurer instead",
)
add(
    [
        "OPTUM TRANSPLANTS",
        "OPTUM TRANSPLANTS OON",
        "HUMANA NATIONAL TRANSPLANT",
        "RENAL PAYOR SOLUTION MEDICARE",
        "RENAL PAYOR SOLUTIONS",
        "HUMANA BEHAVIORAL HEALTH",
        "OPTUM-US BEHAV HLTH",
        "CIGNA_BEHAVIORAL HEALTH",
        "MAGELLAN",
        "[PAYER_MAGELLAN]",
        "UNITED BH",
        "UNITED BEHAVIORAL HEALTH",
        "[PAYER_UNITED BEHAVIORAL HEALTH]",
        "[PAYER_BEACON HEALTH OPTIONS]",
        "[PAYER_GEHA UBH]",
        "[PAYER_UMR BHO]",
        "MHN",
        "[PAYER_MANAGED HEALTH NETWORK]",
        "[PAYER_MINES & ASSOCIATES]",
        "PROVIDENCE HLTH",
        "HMC",
    ],
    None,
    "exclude",
    "specialty-only contract (transplant, kidney or behavioral health), not a general plan",
)
add(
    [
        "WORKER COMPENSATION",
        "WORKER COMP",
        "ANTHEM BCBSNV WORKER COMP",
        "ANTHEM BCBS WORKERS COMPENSATION",
    ],
    None,
    "exclude",
    "workers' compensation, not health insurance people choose",
)
add(
    [
        "CARSON CITY JAIL",
        "CLARK COUNTY DETENTION CENTER",
        "NAPHCARE",
        "[PAYER_LAS VEGAS JUSTICE COURT]",
        "[PAYER_DCFS]",
        "[PAYER_DPBH RAWSON NEAL]",
        "INDIAN HEALTH SERVICES",
        "VETERANS EVALUATION SERVICE VES",
        "[PAYER_ALTEA RESEARCH]",
        "PROCARE",
        "PROCARE HOSPICE",
        "UNIFIED CARE HOSPICE",
        "ALL OTHER",
        "[PAYER_COMMERCIAL GENERIC]",
        "PAM",
        "AIG",
        "MANAGED MEDICARE 100%",
        "[PAYER_PENDING NV MEDICAID]",
        "[PAYER_MEDICIAD OUT OF STATE]",
        "[PAYER_CARE 1ST HEALTH PLAN AZ]",
        "[PAYER_STEWARD HEALTH CHOICE GEN]",
        "[PAYER_ONECARE]",
        "CUSTOM INK",
    ],
    None,
    "exclude",
    "not a plan a patient picks (jail, hospice, research, catch-all, out-of-state or unclear)",
)
add(["ONE HEALTH PLAN", "ONE HEALTH"], "One Health Plan")

EMPLOYERS = [
    "CAESAR'S ENTERTAINMENT",
    "MGM GRAND",
    "MIRAGE LAS VEGAS",
    "[PAYER_MGM MIRAGE]",
    "WYNN RESORTS",
    "RESORTS WORLD LAS VEGAS",
    "LAS VEGAS SAND CORPS",
    "VENETIAN/PALAZZO",
    "STATIONS CASINOS",
    "GOLDEN ENTERTAINMENT",
    "GOLDEN NUGGET HOTEL & CASINO",
    "BOYD GROUP",
    "CIRQUE DE SOLEIL",
    "NATIONAL SECURITY TECHNOLOGIES",
    "SWITCH",
    "NEVADA ENERGY",
    "PLI LAS VEGAS",
    "ARROWEYE SOLUTIONS",
    "MARSHALL RETAIL GROUP",
    "TRULINE CORPORATION",
    "REBEL OIL COMPANY",
    "JW MARRIOTT",
    "ZUFFA",
    "SOUTHPOINT (GAGHAN SOUTH)",
    "CITY OF NORTH LAS VEGAS",
    "CITY OF HENDERSON",
    "CLARK COUNTY SELF FUNDED",
    "CLARK COUNTY EPO",
    "LAS VEGAS METRO POLICE DEPT",
    "STATE OF NEVADA",
    "NEVADA HAND",
]
UNIONS = [
    "CEMENT MASONS & PLASTERS H&W",
    "UFCW LOCAL 711 RETAIL CLERKS",
    "LABORERS HEALTH AND WELFARE",
    "BRICKLAYERS LOCAL 13",
    "PLUMBERS & PIPEFITTERS LOC 525",
    "[PAYER_PLUMBERS/PIPEFITTERS 525]",
    "TEAMSTERS LOCAL 631",
    "[PAYER_LOCAL 631]",
    "ELECTRICAL WORKERS",
    "[PAYER_LOCAL 357]",
    "TEAMSTERS LOCAL 14",
    "[PAYER_LOCAL 14]",
    "TEAMSTERS LOCAL 986",
    "[PAYER_LOCAL 986]",
    "OPERATING ENGINEERS",
    "LAS VEGAS FIREFIGHTERS 1285",
    "CLARK COUNTY FIREFIGHTERS 1908",
    "[PAYER_EBMS LOCAL 1908]",
    "EMPLOYEE PAINTERS TRUST",
    "SOUTHWEST CARPENTERS H&W",
    "CALIFORNIA IRONWORK FIELD WELFARE",
    "SHEET METAL WORKERS",
    "SO CA PIPE TRADES H&W",
    "NV HEALTH & WELFARE TRUST",
    "TEACHER'S HEALTH TRUST",
    "TEACHERS TRUST",
    "[PAYER_TEACHERS HEALTH TRUST]",
    "NV LABORERS HEALTH & WELFARE TRUST FUND",
    "[PAYER_CONSTRUCTION/LABORERS 872]",
]
NICE = {
    "[PAYER_MGM MIRAGE]": "MGM Resorts",
    "MGM GRAND": "MGM Resorts",
    "MIRAGE LAS VEGAS": "MGM Resorts",
    "CAESAR'S ENTERTAINMENT": "Caesars Entertainment",
    "VENETIAN/PALAZZO": "The Venetian Resort",
    "LAS VEGAS SAND CORPS": "Las Vegas Sands",
    "STATIONS CASINOS": "Station Casinos",
    "SOUTHPOINT (GAGHAN SOUTH)": "South Point Hotel & Casino",
    "NEVADA ENERGY": "NV Energy",
    "TEACHER'S HEALTH TRUST": "Teachers Health Trust",
    "TEACHERS TRUST": "Teachers Health Trust",
    "[PAYER_TEACHERS HEALTH TRUST]": "Teachers Health Trust",
    "PLUMBERS & PIPEFITTERS LOC 525": "Plumbers & Pipefitters Local 525",
    "[PAYER_PLUMBERS/PIPEFITTERS 525]": "Plumbers & Pipefitters Local 525",
    "TEAMSTERS LOCAL 631": "Teamsters Local 631",
    "[PAYER_LOCAL 631]": "Teamsters Local 631",
    "TEAMSTERS LOCAL 14": "Teamsters Local 14",
    "[PAYER_LOCAL 14]": "Teamsters Local 14",
    "TEAMSTERS LOCAL 986": "Teamsters Local 986",
    "[PAYER_LOCAL 986]": "Teamsters Local 986",
    "ELECTRICAL WORKERS": "IBEW Local 357",
    "[PAYER_LOCAL 357]": "IBEW Local 357",
    "CLARK COUNTY FIREFIGHTERS 1908": "Clark County Firefighters Local 1908",
    "[PAYER_EBMS LOCAL 1908]": "Clark County Firefighters Local 1908",
    "NV LABORERS HEALTH & WELFARE TRUST FUND": "Laborers Health & Welfare Trust (Nevada)",
    "LABORERS HEALTH AND WELFARE": "Laborers Health & Welfare Trust (Nevada)",
    "[PAYER_CONSTRUCTION/LABORERS 872]": "Laborers Health & Welfare Trust (Nevada)",
    "CLARK COUNTY SELF FUNDED": "Clark County (employee plan)",
    "CLARK COUNTY EPO": "Clark County (employee plan)",
    "STATE OF NEVADA": "State of Nevada PEBP",
}
for n in EMPLOYERS:
    P[n] = (
        NICE.get(n, n.title().replace("'S", "'s")),
        "employer",
        "employer's own plan; card usually shows the employer",
    )
for n in UNIONS:
    P[n] = (
        NICE.get(n, n.title().replace("H&W", "H&W").replace("'S", "'s")),
        "union",
        "union health trust; card usually shows the trust",
    )


def norm_payer(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().upper())


def plan_type(raw_plan: str, insurer_note: str, payer_raw: str) -> tuple[str, str, str]:
    """(plan label, product_type, segment)."""
    p = raw_plan.strip()
    u = p.upper().replace("[PLAN_", "").rstrip("]")
    pu = payer_raw.upper()
    if re.search(r"WORKER|WCOMP|\bWC\b|WORKERSCOMP", u):
        return "Workers' compensation", "other", "workers_comp"
    if re.search(r"TRICARE|VETERAN", u):
        return "TRICARE / VA", "other", "tricare"
    if re.search(
        r"MEDICAID|MCAID|\bMCD\b|MGMCD|SMART CHOICE|CHECKUP|NEVADA CHECKUP", u
    ) or re.search(r"MEDICAID|MCAID", pu):
        return "Medicaid plan", "other", "medicaid_managed_care"
    if re.search(r"MEDICARE|\bMCR|MGMCR|MEDIBLUE|SENIOR|PFFS|AARP|GOLD PLUS", u) or re.search(
        r"MEDICARE|MCR ADV|MCARE", pu
    ):
        if "TRADITIONAL" in u or "TRADITIONAL" in pu:
            return "Original Medicare", "other", "medicare_ffs"
        return "Medicare Advantage", "other", "medicare_advantage"
    if (
        re.search(r"HIX|EXCHANGE|MARKETPLACE|\bQHP|PATHWAY|AMBETTER", u)
        or "PATHWAY" in pu
        or "AMBETTER" in pu
    ):
        return "Marketplace (exchange) plan", "other", "exchange"
    if re.fullmatch(
        r"HMO|COMMERCIAL\|HMO|ANTHEM HMO|HPN HMO BRONZE PLAN|CITY OF LAS VEGAS HMO|ALL PRODUCTS_HMO",
        u,
    ):
        return "HMO", "hmo", "commercial"
    if re.fullmatch(
        r"PPO|COMMERCIAL\|PPO|ANTHEM PPO|ANTHEM PAR PPO|COMMPPO|CITY OF LAS VEGAS PPO|SIERRA HEALTH PPO",
        u,
    ):
        return "PPO", "ppo", "commercial"
    if re.fullmatch(r"POSPPO|HPN OPEN ACCESS POS|VALUE NETWORK HMOPOS", u):
        return "POS", "pos", "commercial"
    if re.fullmatch(r"PPO/EPO", u):
        return "PPO / EPO", "ppo", "commercial"
    if re.search(r"OPTIONS ?PPO|UHC OPTIONS", u):
        return "Options PPO", "ppo", "commercial"
    if u in ("OAP",):
        return "Open Access Plus (OAP)", "pos", "commercial"
    if "FEDERAL" in u:
        return "Federal Employee Program", "other", "commercial"
    return "All plans (one rate published for all)", "unknown", "commercial"


# specific plan spellings that name a different company, an employer or a product
OVERRIDE = {
    "HPN HMO BRONZE PLAN": ("Health Plan of Nevada (HPN)", "HMO", "hmo", "commercial", "insurer"),
    "HPN HEALTH PLAN OF NEVADA": (
        "Health Plan of Nevada (HPN)",
        "All plans (one rate published for all)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "HPN OPEN ACCESS POS": ("Health Plan of Nevada (HPN)", "POS", "pos", "commercial", "insurer"),
    "HPN COMMERCIAL": (
        "Health Plan of Nevada (HPN)",
        "All plans (one rate published for all)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "HPN MEDICARE": (
        "Health Plan of Nevada (HPN)",
        "Medicare Advantage",
        "other",
        "medicare_advantage",
        "insurer",
    ),
    "HPN MEDICAID": (
        "Health Plan of Nevada (HPN)",
        "Medicaid plan",
        "other",
        "medicaid_managed_care",
        "insurer",
    ),
    "HPN MEDICAID FKA SMART CHOICE": (
        "Health Plan of Nevada (HPN)",
        "Medicaid plan",
        "other",
        "medicaid_managed_care",
        "insurer",
    ),
    "HPN NEVADA CHECKUP": (
        "Health Plan of Nevada (HPN)",
        "Nevada Check Up (children)",
        "other",
        "medicaid_managed_care",
        "insurer",
    ),
    "WYNNENCORE": (
        "Wynn Resorts",
        "Employee / member plan",
        "unknown",
        "employer_self_funded",
        "employer",
    ),
    "CITY OF LAS VEGAS PPO": (
        "City of Las Vegas",
        "Employee / member plan (PPO)",
        "ppo",
        "employer_self_funded",
        "employer",
    ),
    "CITY OF LAS VEGAS HMO": (
        "City of Las Vegas",
        "Employee / member plan (HMO)",
        "hmo",
        "employer_self_funded",
        "employer",
    ),
    "OXFORD HEALTH": ("UnitedHealthcare", "Oxford Health", "unknown", "commercial", "insurer"),
    "GOLDEN RULE": (
        "Golden Rule (UnitedHealthcare)",
        "All plans (one rate published for all)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "UMR": (
        "UMR (UnitedHealthcare)",
        "All plans (one rate published for all)",
        "unknown",
        "employer_self_funded",
        "insurer",
    ),
    "GLOBALBENEFITPLAN": (
        "UnitedHealthcare",
        "Global (international members)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "INTERNATIONAL PASSPORT TO HEALTH": (
        "Aetna",
        "International members",
        "unknown",
        "commercial",
        "insurer",
    ),
    "HEALTHPARTNERS": ("Cigna", "HealthPartners members", "unknown", "commercial", "insurer"),
    "NORTHERN CA": (
        "Kaiser Permanente",
        "Visiting members (Northern California)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "SOUTHERN CA": (
        "Kaiser Permanente",
        "Visiting members (Southern California)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "HAWAII": (
        "Kaiser Permanente",
        "Visiting members (Hawaii)",
        "unknown",
        "commercial",
        "insurer",
    ),
    "NEVADA DEPARTMENT OF CORRECTIONS": (None, "", "other", "unknown", "exclude"),
    "FRIDAY HEALTH PLANS": (None, "", "other", "unknown", "exclude"),
    "MEDICAL RENTAL PRODUCTS": (None, "", "other", "unknown", "exclude"),
    "LEASE NETWORKS": (None, "", "other", "unknown", "exclude"),
}
OV_NOTE = {
    "NEVADA DEPARTMENT OF CORRECTIONS": "prison health care, not a plan people pick",
    "FRIDAY HEALTH PLANS": "Friday Health Plans closed in 2023",
    "MEDICAL RENTAL PRODUCTS": "network rental, not a plan",
    "LEASE NETWORKS": "network rental, not a plan",
}
MEMBER_GENERIC = re.compile(
    r"^(\[PLAN_)?(HMO/PPO|HMO|PPO|ALL PRODUCTS|COMMERCIAL|COMM|ALL PLANS|ALL|MGM PROPERTIES)\]?$"
)

rows = list(csv.DictReader(open(src, encoding="utf-8")))
rows.sort(key=lambda r: -int(r["prices"]))
fields = [
    "payer_name_raw",
    "plan_name_raw",
    "prices",
    "facilities",
    "facility_names",
    "proposed_insurer",
    "proposed_plan",
    "product_type",
    "segment",
    "kind",
    "use_in_picker",
    "confidence",
    "notes",
]
with open(out, "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    unknown = 0
    for r in rows:
        key = norm_payer(r["payer_name_raw"])
        insurer, kind, note = P.get(key, (None, "unknown", "not recognised; needs a person"))
        if kind == "unknown":
            unknown += 1
        label, pt, seg = plan_type(r["plan_name_raw"], note, key)
        ov = OVERRIDE.get(r["plan_name_raw"].strip().upper())
        if ov:
            insurer, label, pt, seg, kind = ov
            note = OV_NOTE.get(
                r["plan_name_raw"].strip().upper(), "plan name points to this company or product"
            )
        if insurer == "Health Net" and seg == "tricare":
            insurer, kind = "TRICARE", "government"
        use = kind in ("insurer", "employer", "union", "government") and insurer is not None
        if seg == "workers_comp":
            use, kind, note = False, "exclude", "workers' compensation"
        if kind == "government":
            label = {
                "Original Medicare": "Original Medicare",
                "Nevada Medicaid (fee for service)": "Medicaid",
                "TRICARE": "TRICARE",
                "VA Community Care": "VA Community Care",
                "CHAMPVA": "CHAMPVA",
            }.get(insurer, label)
            seg = {
                "Original Medicare": "medicare_ffs",
                "TRICARE": "tricare",
                "VA Community Care": "tricare",
                "CHAMPVA": "tricare",
            }.get(insurer, "medicaid_managed_care" if "Medicaid" in (insurer or "") else seg)
        if kind in ("employer", "union"):
            label, seg = (
                "Employee / member plan",
                ("union_trust" if kind == "union" else "employer_self_funded"),
            )
            # an employer row naming an insurer as the plan, e.g. Caesars | Anthem
            if ov is None and not MEMBER_GENERIC.match(r["plan_name_raw"].strip().upper()):
                extra = {
                    "SHO": "Sierra Health Options",
                    "UHC": "UnitedHealthcare",
                    "IBEW 357": "",
                }.get(r["plan_name_raw"].strip().upper(), r["plan_name_raw"].strip())
                label = f"Employee / member plan ({extra})" if extra else "Employee / member plan"
            elif ov is not None:
                label = ov[1]
        conf = "high"
        if label.startswith("All plans"):
            conf = "medium"
        if "not stated" in (insurer or "") or kind in ("unknown",) or "check" in note:
            conf = "low"
        if not use:
            conf = "-"
        seg_ok = (
            seg
            if seg
            in (
                "commercial",
                "exchange",
                "employer_self_funded",
                "union_trust",
                "medicare_advantage",
                "medicaid_managed_care",
            )
            else ("unknown" if seg not in ("medicare_ffs", "tricare", "workers_comp") else seg)
        )
        w.writerow(
            {
                **{k: r[k] for k in fields[:5]},
                "proposed_insurer": insurer or "",
                "proposed_plan": label if use else "",
                "product_type": pt,
                "segment": seg_ok,
                "kind": kind,
                "use_in_picker": "yes" if use else "no",
                "confidence": conf,
                "notes": note,
            }
        )
print("rows", len(rows), "unrecognised payer spellings", unknown)
