"""Hardcoded industry × company mapping shared by Part 1 (migration) and
Part 2 (bulk ingest) of S3_PLAN.md.

Conventions:
- Industry directory names use underscores (no spaces), so they translate
  cleanly into S3 keys (no URL-escape surprises).
- Company directory names are `<DisplayName>_<TICKER>` with the same
  underscore rule, so listings sort by company name.
- Industry assignments follow GICS 2024-09. Two cross-cut companies that
  appeared in two industries on the user's wishlist (Alphabet, Meta) are
  resolved here once: Alphabet → Technology (matches existing S3 data),
  Meta → Communication_Services (matches GICS).

`COMPANIES[ticker]` may carry an optional `cik` (zero-padded 10-digit
string). Only set this for tickers SEC's official ticker map cannot
resolve directly (e.g. BRK.B). For everything else `core/sec_edgar.find_cik`
already does the right thing from ticker alone.
"""

from __future__ import annotations

# Canonical list of dashboard / S3 industry buckets.
INDUSTRIES: dict[str, list[str]] = {
    "Technology": [
        "AAPL", "MSFT", "GOOG", "NVDA", "ADBE",
        "CRM", "INTC", "CSCO", "ORCL",
    ],
    "Energy": [
        "XOM", "CVX", "COP", "SLB", "EOG",
        "PXD", "MPC", "VLO",
    ],
    "Consumer_Cyclical": [
        "AMZN", "TSLA", "HD", "MCD", "NKE",
        "SBUX", "BKNG", "LOW", "UBER",
    ],
    "Consumer_Defensive": [
        "PG", "KO", "PEP", "WMT", "COST",
        "PM", "CL", "MDLZ", "KR", "TGT",
    ],
    "Communication_Services": [
        "META", "NFLX", "DIS", "CMCSA",
        "TMUS", "VZ", "T",
    ],
    "Industrials": [
        "BA", "CAT", "HON", "UNP", "MMM",
        "GE", "LMT", "RTX", "DE", "MSI",
    ],
    "Financial_Services": [
        "JPM", "GS", "MS", "BAC", "V",
        "MA", "BLK", "BRK.B",
    ],
    "Utilities": [
        "NEE", "DUK", "SO", "D", "AES", "EXC",
    ],
    "Basic_Materials": [
        "LIN", "APD", "FCX", "NEM", "DOW", "DD",
    ],
    "Real_Estate": [
        "PLD", "AMT", "CCI", "EQIX", "SPG", "O",
    ],
    "Healthcare": [
        "UNH", "JNJ", "PFE", "LLY", "ABBV",
        "MRK", "TMO", "ABT",
    ],
}


# Per-ticker metadata. Required fields: name, industry, dir, sec_name.
# Optional: cik (pad to 10 digits), last_year (cap data fetch year for
# delisted / acquired companies), notes.
COMPANIES: dict[str, dict] = {
    # ── Technology ──────────────────────────────────────────────────────
    "AAPL": {"name": "Apple",        "industry": "Technology", "dir": "Apple_AAPL",        "sec_name": "Apple Inc"},
    "MSFT": {"name": "Microsoft",    "industry": "Technology", "dir": "Microsoft_MSFT",    "sec_name": "Microsoft Corp"},
    "GOOG": {"name": "Alphabet",     "industry": "Technology", "dir": "Alphabet_GOOG",     "sec_name": "Alphabet Inc"},
    "NVDA": {"name": "NVIDIA",       "industry": "Technology", "dir": "NVIDIA_NVDA",       "sec_name": "NVIDIA Corp"},
    "ADBE": {"name": "Adobe",        "industry": "Technology", "dir": "Adobe_ADBE",        "sec_name": "Adobe Inc"},
    "CRM":  {"name": "Salesforce",   "industry": "Technology", "dir": "Salesforce_CRM",    "sec_name": "Salesforce Inc"},
    "INTC": {"name": "Intel",        "industry": "Technology", "dir": "Intel_INTC",        "sec_name": "Intel Corp"},
    "CSCO": {"name": "Cisco",        "industry": "Technology", "dir": "Cisco_CSCO",        "sec_name": "Cisco Systems Inc"},
    "ORCL": {"name": "Oracle",       "industry": "Technology", "dir": "Oracle_ORCL",       "sec_name": "Oracle Corp"},
    "MSI":  {"name": "Motorola Solutions", "industry": "Industrials", "dir": "Motorola_Solutions_MSI", "sec_name": "Motorola Solutions Inc"},

    # ── Energy ─────────────────────────────────────────────────────────
    "XOM":  {"name": "ExxonMobil",        "industry": "Energy", "dir": "ExxonMobil_XOM",        "sec_name": "Exxon Mobil Corp"},
    "CVX":  {"name": "Chevron",           "industry": "Energy", "dir": "Chevron_CVX",           "sec_name": "Chevron Corp"},
    "COP":  {"name": "ConocoPhillips",    "industry": "Energy", "dir": "ConocoPhillips_COP",    "sec_name": "ConocoPhillips"},
    "SLB":  {"name": "Schlumberger",      "industry": "Energy", "dir": "Schlumberger_SLB",      "sec_name": "Schlumberger N.V."},
    "EOG":  {"name": "EOG Resources",     "industry": "Energy", "dir": "EOG_Resources_EOG",     "sec_name": "EOG Resources Inc"},
    "PXD":  {"name": "Pioneer Natural Resources", "industry": "Energy", "dir": "Pioneer_Natural_Resources_PXD",
             "sec_name": "Pioneer Natural Resources Co", "last_year": 2023,
             "notes": "Acquired by Exxon May 2024; last 10-K filing is FY2023."},
    "MPC":  {"name": "Marathon Petroleum","industry": "Energy", "dir": "Marathon_Petroleum_MPC","sec_name": "Marathon Petroleum Corp"},
    "VLO":  {"name": "Valero Energy",     "industry": "Energy", "dir": "Valero_Energy_VLO",     "sec_name": "Valero Energy Corp"},

    # ── Consumer Cyclical ──────────────────────────────────────────────
    "AMZN": {"name": "Amazon",        "industry": "Consumer_Cyclical", "dir": "Amazon_AMZN",        "sec_name": "Amazon.com Inc"},
    "TSLA": {"name": "Tesla",         "industry": "Consumer_Cyclical", "dir": "Tesla_TSLA",         "sec_name": "Tesla Inc"},
    "HD":   {"name": "Home Depot",    "industry": "Consumer_Cyclical", "dir": "Home_Depot_HD",      "sec_name": "Home Depot Inc"},
    "MCD":  {"name": "McDonalds",     "industry": "Consumer_Cyclical", "dir": "McDonalds_MCD",      "sec_name": "McDonald's Corp"},
    "NKE":  {"name": "Nike",          "industry": "Consumer_Cyclical", "dir": "Nike_NKE",           "sec_name": "Nike Inc"},
    "SBUX": {"name": "Starbucks",     "industry": "Consumer_Cyclical", "dir": "Starbucks_SBUX",     "sec_name": "Starbucks Corp"},
    "BKNG": {"name": "Booking Holdings","industry":"Consumer_Cyclical","dir":"Booking_Holdings_BKNG","sec_name": "Booking Holdings Inc"},
    "LOW":  {"name": "Lowes",         "industry": "Consumer_Cyclical", "dir": "Lowes_LOW",          "sec_name": "Lowe's Companies Inc"},
    "UBER": {"name": "Uber",          "industry": "Consumer_Cyclical", "dir": "Uber_UBER",          "sec_name": "Uber Technologies Inc"},

    # ── Consumer Defensive ─────────────────────────────────────────────
    "PG":   {"name": "Procter & Gamble", "industry": "Consumer_Defensive", "dir": "Procter_and_Gamble_PG", "sec_name": "Procter & Gamble Co"},
    "KO":   {"name": "Coca-Cola",        "industry": "Consumer_Defensive", "dir": "Coca-Cola_KO",          "sec_name": "Coca-Cola Co"},
    "PEP":  {"name": "PepsiCo",          "industry": "Consumer_Defensive", "dir": "PepsiCo_PEP",           "sec_name": "PepsiCo Inc"},
    "WMT":  {"name": "Walmart",          "industry": "Consumer_Defensive", "dir": "Walmart_WMT",           "sec_name": "Walmart Inc"},
    "COST": {"name": "Costco",           "industry": "Consumer_Defensive", "dir": "Costco_COST",           "sec_name": "Costco Wholesale Corp"},
    "PM":   {"name": "Philip Morris",    "industry": "Consumer_Defensive", "dir": "Philip_Morris_PM",      "sec_name": "Philip Morris International Inc"},
    "CL":   {"name": "Colgate-Palmolive","industry": "Consumer_Defensive", "dir": "Colgate-Palmolive_CL",  "sec_name": "Colgate-Palmolive Co"},
    "MDLZ": {"name": "Mondelez",         "industry": "Consumer_Defensive", "dir": "Mondelez_MDLZ",         "sec_name": "Mondelez International Inc"},
    "KR":   {"name": "Kroger",           "industry": "Consumer_Defensive", "dir": "Kroger_KR",             "sec_name": "Kroger Co"},
    "TGT":  {"name": "Target",           "industry": "Consumer_Defensive", "dir": "Target_TGT",            "sec_name": "Target Corp"},

    # ── Communication Services ─────────────────────────────────────────
    "META": {"name": "Meta",          "industry": "Communication_Services", "dir": "Meta_META",      "sec_name": "Meta Platforms Inc"},
    "NFLX": {"name": "Netflix",       "industry": "Communication_Services", "dir": "Netflix_NFLX",   "sec_name": "Netflix Inc"},
    "DIS":  {"name": "Disney",        "industry": "Communication_Services", "dir": "Disney_DIS",     "sec_name": "Walt Disney Co"},
    "CMCSA":{"name": "Comcast",       "industry": "Communication_Services", "dir": "Comcast_CMCSA",  "sec_name": "Comcast Corp"},
    "TMUS": {"name": "T-Mobile",      "industry": "Communication_Services", "dir": "T-Mobile_TMUS",  "sec_name": "T-Mobile US Inc"},
    "VZ":   {"name": "Verizon",       "industry": "Communication_Services", "dir": "Verizon_VZ",     "sec_name": "Verizon Communications Inc"},
    "T":    {"name": "AT&T",          "industry": "Communication_Services", "dir": "ATT_T",          "sec_name": "AT&T Inc"},

    # ── Industrials ────────────────────────────────────────────────────
    "BA":   {"name": "Boeing",            "industry": "Industrials", "dir": "Boeing_BA",          "sec_name": "Boeing Co"},
    "CAT":  {"name": "Caterpillar",       "industry": "Industrials", "dir": "Caterpillar_CAT",    "sec_name": "Caterpillar Inc"},
    "HON":  {"name": "Honeywell",         "industry": "Industrials", "dir": "Honeywell_HON",      "sec_name": "Honeywell International Inc"},
    "UNP":  {"name": "Union Pacific",     "industry": "Industrials", "dir": "Union_Pacific_UNP",  "sec_name": "Union Pacific Corp"},
    "MMM":  {"name": "3M",                "industry": "Industrials", "dir": "3M_MMM",             "sec_name": "3M Co"},
    "GE":   {"name": "General Electric",  "industry": "Industrials", "dir": "GE_GE",              "sec_name": "GE Aerospace"},
    "LMT":  {"name": "Lockheed Martin",   "industry": "Industrials", "dir": "Lockheed_Martin_LMT","sec_name": "Lockheed Martin Corp"},
    "RTX":  {"name": "RTX",               "industry": "Industrials", "dir": "RTX_RTX",            "sec_name": "RTX Corp"},
    "DE":   {"name": "Deere",             "industry": "Industrials", "dir": "Deere_DE",           "sec_name": "Deere & Co"},

    # ── Financial Services ─────────────────────────────────────────────
    "JPM":  {"name": "JPMorgan",       "industry": "Financial_Services", "dir": "JPMorgan_JPM",       "sec_name": "JPMorgan Chase & Co"},
    "GS":   {"name": "Goldman Sachs",  "industry": "Financial_Services", "dir": "Goldman_Sachs_GS",   "sec_name": "Goldman Sachs Group Inc"},
    "MS":   {"name": "Morgan Stanley", "industry": "Financial_Services", "dir": "Morgan_Stanley_MS",  "sec_name": "Morgan Stanley"},
    "BAC":  {"name": "Bank of America","industry": "Financial_Services", "dir": "Bank_of_America_BAC","sec_name": "Bank of America Corp"},
    "V":    {"name": "Visa",           "industry": "Financial_Services", "dir": "Visa_V",             "sec_name": "Visa Inc"},
    "MA":   {"name": "Mastercard",     "industry": "Financial_Services", "dir": "Mastercard_MA",      "sec_name": "Mastercard Inc"},
    "BLK":  {"name": "BlackRock",      "industry": "Financial_Services", "dir": "BlackRock_BLK",      "sec_name": "BlackRock Inc"},
    "BRK.B":{"name": "Berkshire Hathaway","industry": "Financial_Services","dir": "Berkshire_Hathaway_BRKB",
             "sec_name": "Berkshire Hathaway Inc", "cik": "0001067983",
             "notes": "B-shares ticker; SEC ticker map only carries BRK, must hardcode CIK."},

    # ── Utilities ──────────────────────────────────────────────────────
    "NEE":  {"name": "NextEra Energy",   "industry": "Utilities", "dir": "NextEra_Energy_NEE",  "sec_name": "NextEra Energy Inc"},
    "DUK":  {"name": "Duke Energy",      "industry": "Utilities", "dir": "Duke_Energy_DUK",     "sec_name": "Duke Energy Corp"},
    "SO":   {"name": "Southern Company", "industry": "Utilities", "dir": "Southern_Company_SO", "sec_name": "Southern Co"},
    "D":    {"name": "Dominion Energy",  "industry": "Utilities", "dir": "Dominion_Energy_D",   "sec_name": "Dominion Energy Inc"},
    "AES":  {"name": "AES",              "industry": "Utilities", "dir": "AES_AES",             "sec_name": "AES Corp"},
    "EXC":  {"name": "Exelon",           "industry": "Utilities", "dir": "Exelon_EXC",          "sec_name": "Exelon Corp"},

    # ── Basic Materials ────────────────────────────────────────────────
    "LIN":  {"name": "Linde",            "industry": "Basic_Materials", "dir": "Linde_LIN",            "sec_name": "Linde plc"},
    "APD":  {"name": "Air Products",     "industry": "Basic_Materials", "dir": "Air_Products_APD",     "sec_name": "Air Products and Chemicals Inc"},
    "FCX":  {"name": "Freeport-McMoRan", "industry": "Basic_Materials", "dir": "Freeport-McMoRan_FCX", "sec_name": "Freeport-McMoRan Inc"},
    "NEM":  {"name": "Newmont",          "industry": "Basic_Materials", "dir": "Newmont_NEM",          "sec_name": "Newmont Corp"},
    "DOW":  {"name": "Dow",              "industry": "Basic_Materials", "dir": "Dow_DOW",              "sec_name": "Dow Inc"},
    "DD":   {"name": "DuPont",           "industry": "Basic_Materials", "dir": "DuPont_DD",            "sec_name": "DuPont de Nemours Inc"},

    # ── Real Estate ────────────────────────────────────────────────────
    "PLD":  {"name": "Prologis",         "industry": "Real_Estate", "dir": "Prologis_PLD",        "sec_name": "Prologis Inc"},
    "AMT":  {"name": "American Tower",   "industry": "Real_Estate", "dir": "American_Tower_AMT",  "sec_name": "American Tower Corp"},
    "CCI":  {"name": "Crown Castle",     "industry": "Real_Estate", "dir": "Crown_Castle_CCI",    "sec_name": "Crown Castle Inc"},
    "EQIX": {"name": "Equinix",          "industry": "Real_Estate", "dir": "Equinix_EQIX",        "sec_name": "Equinix Inc"},
    "SPG":  {"name": "Simon Property",   "industry": "Real_Estate", "dir": "Simon_Property_SPG",  "sec_name": "Simon Property Group Inc"},
    "O":    {"name": "Realty Income",    "industry": "Real_Estate", "dir": "Realty_Income_O",     "sec_name": "Realty Income Corp"},

    # ── Healthcare ─────────────────────────────────────────────────────
    "UNH":  {"name": "UnitedHealth",     "industry": "Healthcare", "dir": "UnitedHealth_UNH",     "sec_name": "UnitedHealth Group Inc"},
    "JNJ":  {"name": "Johnson & Johnson","industry": "Healthcare", "dir": "Johnson_and_Johnson_JNJ","sec_name": "Johnson & Johnson"},
    "PFE":  {"name": "Pfizer",           "industry": "Healthcare", "dir": "Pfizer_PFE",           "sec_name": "Pfizer Inc"},
    "LLY":  {"name": "Eli Lilly",        "industry": "Healthcare", "dir": "Eli_Lilly_LLY",        "sec_name": "Eli Lilly and Co"},
    "ABBV": {"name": "AbbVie",           "industry": "Healthcare", "dir": "AbbVie_ABBV",          "sec_name": "AbbVie Inc"},
    "MRK":  {"name": "Merck",            "industry": "Healthcare", "dir": "Merck_MRK",            "sec_name": "Merck & Co Inc"},
    "TMO":  {"name": "Thermo Fisher",    "industry": "Healthcare", "dir": "Thermo_Fisher_TMO",    "sec_name": "Thermo Fisher Scientific Inc"},
    "ABT":  {"name": "Abbott",           "industry": "Healthcare", "dir": "Abbott_ABT",           "sec_name": "Abbott Laboratories"},
}


# ── Migration name-fix table for Part 1 ─────────────────────────────────
# Keys are the safe_company token parsed out of legacy filenames in
# `s3://<bucket>/10k_html_datasets/`. Values are the canonical ticker so
# Part 1 can route the file to its proper company directory.
LEGACY_FILENAME_TO_TICKER: dict[str, str] = {
    "Apple": "AAPL",
    "Alphabet": "GOOG",
    "NVIDIA": "NVDA",
    "Motorola_Solutions_Inc": "MSI",
    # Typo fixes: source file has 3 l's; canonical name has 2.
    "ConocoPhilllips": "COP",
    "ConocoPhillips": "COP",
    "Exxon_Mobil": "XOM",
    "Chevron": "CVX",
    "Walmart": "WMT",
    "Kroger": "KR",
    "Target": "TGT",
    "Boeing": "BA",
    "Uber": "UBER",
    # Lowercase / incomplete name in legacy data; canonical is "Lockheed Martin".
    "lockheed": "LMT",
    "Lockheed_Martin": "LMT",
    # Airbus is intentionally absent — see SKIP_LEGACY_TOKENS below.
}


# Filename tokens that must NOT migrate into the new layout. Default per
# S3_PLAN.md: skip Airbus (European company, files no SEC 10-K).
SKIP_LEGACY_TOKENS: set[str] = {"Airbus"}


def lookup_company(ticker: str) -> dict | None:
    """Fetch metadata for a ticker. Returns None if unknown."""
    t = str(ticker or "").strip().upper()
    return COMPANIES.get(t)


def sec_name_for(ticker: str) -> str:
    meta = lookup_company(ticker) or {}
    return str(meta.get("sec_name", meta.get("name", "")) or "")


def industry_for(ticker: str) -> str:
    meta = lookup_company(ticker) or {}
    return str(meta.get("industry", "Other") or "Other")


def dir_for(ticker: str) -> str:
    meta = lookup_company(ticker) or {}
    return str(meta.get("dir", "") or "")


def cik_for(ticker: str) -> str:
    meta = lookup_company(ticker) or {}
    return str(meta.get("cik", "") or "")


def last_year_for(ticker: str) -> int | None:
    meta = lookup_company(ticker) or {}
    val = meta.get("last_year")
    try:
        return int(val) if val is not None else None
    except Exception:
        return None
