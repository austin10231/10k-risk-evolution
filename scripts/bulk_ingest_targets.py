"""Target list for `scripts/bulk_ingest.py` (S3_PLAN.md Part 2).

Each entry is `(ticker, industry_dir)`. Industry must match the canonical
key in `scripts.industry_mapping.INDUSTRIES`. The list is deduplicated
across the user's original wishlist where Alphabet/Meta were listed in
two industries (resolved here to Technology and Communication_Services
respectively, matching `industry_mapping.COMPANIES`).

Tickers already migrated by Part 1 (Apple, Alphabet, NVIDIA, Motorola
Solutions, Chevron, ConocoPhillips, ExxonMobil, Kroger, Target, Walmart,
Boeing, Lockheed Martin, Uber) are still listed here — `bulk_ingest`
will detect existing (company, year) pairs in `10k_filings/index.json`
and skip them.
"""

from __future__ import annotations

TARGETS: list[tuple[str, str]] = [
    # ── Technology ─────────────────────────────────────────────────────
    ("AAPL",  "Technology"),
    ("MSFT",  "Technology"),
    ("GOOG",  "Technology"),
    ("NVDA",  "Technology"),
    ("ADBE",  "Technology"),
    ("CRM",   "Technology"),
    ("INTC",  "Technology"),
    ("CSCO",  "Technology"),
    ("ORCL",  "Technology"),
    ("MSI",   "Industrials"),  # Motorola Solutions retained from legacy data

    # ── Energy ─────────────────────────────────────────────────────────
    ("XOM",   "Energy"),
    ("CVX",   "Energy"),
    ("COP",   "Energy"),
    ("SLB",   "Energy"),
    ("EOG",   "Energy"),
    ("PXD",   "Energy"),  # NB: last_year=2023 (acquired by XOM 2024-05).
    ("MPC",   "Energy"),
    ("VLO",   "Energy"),

    # ── Consumer Cyclical ──────────────────────────────────────────────
    ("AMZN",  "Consumer_Cyclical"),
    ("TSLA",  "Consumer_Cyclical"),
    ("HD",    "Consumer_Cyclical"),
    ("MCD",   "Consumer_Cyclical"),
    ("NKE",   "Consumer_Cyclical"),
    ("SBUX",  "Consumer_Cyclical"),
    ("BKNG",  "Consumer_Cyclical"),
    ("LOW",   "Consumer_Cyclical"),
    ("UBER",  "Consumer_Cyclical"),

    # ── Consumer Defensive ─────────────────────────────────────────────
    ("PG",    "Consumer_Defensive"),
    ("KO",    "Consumer_Defensive"),
    ("PEP",   "Consumer_Defensive"),
    ("WMT",   "Consumer_Defensive"),
    ("COST",  "Consumer_Defensive"),
    ("PM",    "Consumer_Defensive"),
    ("CL",    "Consumer_Defensive"),
    ("MDLZ",  "Consumer_Defensive"),
    ("KR",    "Consumer_Defensive"),
    ("TGT",   "Consumer_Defensive"),

    # ── Communication Services ─────────────────────────────────────────
    ("META",  "Communication_Services"),
    ("NFLX",  "Communication_Services"),
    ("DIS",   "Communication_Services"),
    ("CMCSA", "Communication_Services"),
    ("TMUS",  "Communication_Services"),
    ("VZ",    "Communication_Services"),
    ("T",     "Communication_Services"),

    # ── Industrials ────────────────────────────────────────────────────
    ("BA",    "Industrials"),
    ("CAT",   "Industrials"),
    ("HON",   "Industrials"),
    ("UNP",   "Industrials"),
    ("MMM",   "Industrials"),
    ("GE",    "Industrials"),
    ("LMT",   "Industrials"),
    ("RTX",   "Industrials"),
    ("DE",    "Industrials"),

    # ── Financial Services ─────────────────────────────────────────────
    ("JPM",   "Financial_Services"),
    ("GS",    "Financial_Services"),
    ("MS",    "Financial_Services"),
    ("BAC",   "Financial_Services"),
    ("V",     "Financial_Services"),
    ("MA",    "Financial_Services"),
    ("BLK",   "Financial_Services"),
    ("BRK.B", "Financial_Services"),

    # ── Utilities ──────────────────────────────────────────────────────
    ("NEE",   "Utilities"),
    ("DUK",   "Utilities"),
    ("SO",    "Utilities"),
    ("D",     "Utilities"),
    ("AES",   "Utilities"),
    ("EXC",   "Utilities"),

    # ── Basic Materials ────────────────────────────────────────────────
    ("LIN",   "Basic_Materials"),
    ("APD",   "Basic_Materials"),
    ("FCX",   "Basic_Materials"),
    ("NEM",   "Basic_Materials"),
    ("DOW",   "Basic_Materials"),
    ("DD",    "Basic_Materials"),

    # ── Real Estate ────────────────────────────────────────────────────
    ("PLD",   "Real_Estate"),
    ("AMT",   "Real_Estate"),
    ("CCI",   "Real_Estate"),
    ("EQIX",  "Real_Estate"),
    ("SPG",   "Real_Estate"),
    ("O",     "Real_Estate"),

    # ── Healthcare ─────────────────────────────────────────────────────
    ("UNH",   "Healthcare"),
    ("JNJ",   "Healthcare"),
    ("PFE",   "Healthcare"),
    ("LLY",   "Healthcare"),
    ("ABBV",  "Healthcare"),
    ("MRK",   "Healthcare"),
    ("TMO",   "Healthcare"),
    ("ABT",   "Healthcare"),
]
