"""
generate_data.py
================
Creates the synthetic dataset for the Treaty Profitability project.

    python generate_data.py

Writes two files into data/:
    treaties.csv     one row per treaty (who, what, how much is ceded)
    treaty_year.csv  one row per treaty per year, 2016-2025 (premium, claims, size)

ALL DATA IS SYNTHETIC. Every treaty and cedent name is invented. No client data is used.

What the generator builds in (and the analysis should find again)
-----------------------------------------------------------------
Rule 1  Line of business drives the loss ratio most: Income Protection and Trauma run worse than Death.
Rule 2  Older treaties run worse (anti-selection: healthy policyholders lapse, the rest stay).
Rule 3  Large claims (above the retention limit) make individual bad years spike.
Rule 4  Size reduces volatility, not the average (law of large numbers).
Rule 5  cession_pct has NO effect. It scales premium and claims together, so it cancels in the ratio. A decoy.
Rule 6  region has NO effect. A second decoy.

Deliberate mess, for the cleaning section of notebook 01
--------------------------------------------------------
Mess 1  About 3% of avg_sum_insured values are missing.
Mess 2  Three treaty-years have claims keyed with an extra zero, giving an impossible loss ratio above 3.0.
Mess 3  cedent_name has inconsistent casing and stray whitespace.
Mess 4  One treaty-year row is duplicated.

Loss ratio (claims_paid / premium_earned) is NOT stored. Compute it in the notebook.
"""
from pathlib import Path

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Settings
# --------------------------------------------------------------------------- #
SEED = 31                   # fixed seed: the same data every run
FIRST_YEAR, LAST_YEAR = 2016, 2025

# The spec asks for "about 120 treaties" AND "about 1,200 treaty-year rows". Those conflict: a treaty can have
# at most 10 years, and later starters have fewer, so 120 treaties give only ~860 rows. 155 treaties, with the
# book weighted towards older treaties (realistic for a closed-book life reinsurer), gives ~1,200 rows.
N_TREATIES = 155

DATA_DIR = Path(__file__).resolve().parent / "data"
rng = np.random.default_rng(SEED)

# --------------------------------------------------------------------------- #
# Reference lists (all names invented)
# --------------------------------------------------------------------------- #
CEDENTS = [
    "Banksia Life", "Coral Coast Assurance", "Wattle Mutual", "Ironbark Life", "Kestrel Insurance",
    "Southern Star Life", "Bluegum Assurance", "Harbourview Life", "Redgum Life", "Silver Wattle Insurance",
    "Cape Otway Assurance", "Mallee Life", "Jacaranda Life", "Brolga Assurance", "Pelican Bay Life",
    "Granite Belt Mutual", "Kookaburra Life", "Coolabah Insurance",
]
TREATY_TYPES = ["Quota Share", "Surplus", "Excess of Loss"]
TREATY_TYPE_WEIGHTS = [0.45, 0.35, 0.20]
LINES = ["Death", "TPD", "Trauma", "Income Protection"]
LINE_WEIGHTS = [0.35, 0.20, 0.20, 0.25]
REGIONS = ["NSW", "VIC", "QLD", "WA", "SA"]
INCEPTION_YEARS = np.arange(2014, 2024)                      # 2014-2023
INCEPTION_WEIGHTS = [0.14, 0.13, 0.12, 0.11, 0.10, 0.09, 0.09, 0.08, 0.07, 0.07]  # older book

# Typical sum insured (Income Protection is an annual benefit, so much smaller) and the annual premium rate
# per dollar of sum insured. These set the premium; they do not change the loss ratio.
MEDIAN_SUM_INSURED = {"Death": 650_000, "TPD": 500_000, "Trauma": 220_000, "Income Protection": 85_000}
PREMIUM_RATE = {"Death": 0.0013, "TPD": 0.0017, "Trauma": 0.0042, "Income Protection": 0.0210}
CLAIM_INCIDENCE = {"Death": 0.0015, "TPD": 0.0010, "Trauma": 0.0022, "Income Protection": 0.0060}

# --------------------------------------------------------------------------- #
# The rules: every effect below is on the LOSS RATIO
# --------------------------------------------------------------------------- #
BASE_LOSS_RATIO = 0.50
LINE_EFFECT = {"Death": 0.00, "TPD": 0.10, "Trauma": 0.17, "Income Protection": 0.27}   # Rule 1
AGE_EFFECT = 0.018                                                                         # Rule 2, per year
TYPE_EFFECT = {"Quota Share": 0.00, "Surplus": 0.04, "Excess of Loss": 0.07}              # moderate
LARGE_CLAIM_EFFECT = (0.08, 0.20)   # Rule 3: each large claim adds this much to that year's ratio
# Rule 4 lives in loss_ratio_noise(). Rules 5 and 6: cession_pct and region never appear in the formula.


def loss_ratio_noise(policies: int, treaty_type: str) -> float:
    """Rule 4. Multiplicative noise whose spread shrinks with treaty size.

    The -sigma^2/2 term keeps the AVERAGE of the noise at exactly 1, so small treaties swing more
    but are not systematically better or worse. Excess of Loss is lumpier by nature.
    """
    sigma = 0.10 + 8.5 / np.sqrt(policies)          # ~0.48 at 500 policies, ~0.14 at 50,000
    if treaty_type == "Excess of Loss":
        sigma *= 1.3
    return float(np.exp(rng.normal(0, sigma) - sigma ** 2 / 2))


# --------------------------------------------------------------------------- #
# Table 1: treaties
# --------------------------------------------------------------------------- #
def make_treaties() -> pd.DataFrame:
    n = N_TREATIES
    lines = rng.choice(LINES, n, p=LINE_WEIGHTS)
    treaties = pd.DataFrame({
        "treaty_id": [f"TR{i:04d}" for i in range(1, n + 1)],
        "cedent_name": rng.choice(CEDENTS, n),
        "treaty_type": rng.choice(TREATY_TYPES, n, p=TREATY_TYPE_WEIGHTS),
        "line_of_business": lines,
        "inception_year": rng.choice(INCEPTION_YEARS, n, p=INCEPTION_WEIGHTS),
        "cession_pct": rng.uniform(0.20, 0.60, n).round(3),
        "retention_limit": rng.integers(4, 17, n) * 50_000,            # 200k-800k in 50k steps
        "commission_pct": rng.uniform(0.10, 0.30, n).round(3),
        "region": rng.choice(REGIONS, n),
    })
    # Hidden helper columns (dropped before saving). Starting size is log-uniform, so small and large
    # treaties are equally common on a log scale.
    treaties["hidden_policies_start"] = np.exp(rng.uniform(np.log(500), np.log(50_000), n))
    treaties["hidden_sum_insured_start"] = [MEDIAN_SUM_INSURED[l] * rng.lognormal(0, 0.25) for l in lines]
    treaties["hidden_size_trend"] = rng.normal(-0.02, 0.03, n)            # closed books shrink slowly
    return treaties


# --------------------------------------------------------------------------- #
# Table 2: treaty-years
# --------------------------------------------------------------------------- #
def make_treaty_years(treaties: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for t in treaties.itertuples(index=False):
        start = max(FIRST_YEAR, t.inception_year)
        for year in range(start, LAST_YEAR + 1):                    # treaties not yet started are skipped
            years_in = year - start
            policies = t.hidden_policies_start * np.exp(t.hidden_size_trend * years_in) * rng.lognormal(0, 0.03)
            policies = int(np.clip(policies, 500, 50_000))
            avg_sum_insured = t.hidden_sum_insured_start * 1.025 ** (year - FIRST_YEAR)

            premium = (policies * avg_sum_insured * PREMIUM_RATE[t.line_of_business]
                       * t.cession_pct * rng.lognormal(0, 0.02))

            # ---- the loss ratio, built from the rules ----
            age = year - t.inception_year
            expected = (BASE_LOSS_RATIO
                        + LINE_EFFECT[t.line_of_business]          # Rule 1
                        + AGE_EFFECT * age                          # Rule 2
                        + TYPE_EFFECT[t.treaty_type])
            loss_ratio = expected * loss_ratio_noise(policies, t.treaty_type)   # Rule 4

            # Rule 3: large claims. Bigger treaties and lower retentions see more of them;
            # each one hurts a small treaty's ratio a little more than a big one's.
            rate = 0.30 * (policies / 5_000) ** 0.4 * min(2.0, avg_sum_insured / t.retention_limit) ** 0.5
            large_claims = int(rng.poisson(rate))
            for _ in range(large_claims):
                loss_ratio += rng.uniform(*LARGE_CLAIM_EFFECT) * (5_000 / policies) ** 0.15

            # A genuine year above 2.5 would have forced a restructure long before; capping keeps real values
            # clearly separate from the planted data-entry errors (Mess 2), which sit above 3.0.
            loss_ratio = min(loss_ratio, 2.5)
            claims_paid = loss_ratio * premium
            claim_count = max(large_claims, int(rng.poisson(policies * CLAIM_INCIDENCE[t.line_of_business]
                                                             * loss_ratio / expected)))
            rows.append({
                "treaty_id": t.treaty_id,
                "year": year,
                "premium_earned": round(premium, 2),
                "claims_paid": round(claims_paid, 2),
                "claim_count": claim_count,
                "large_claim_count": large_claims,
                "policies_in_force": policies,
                "avg_sum_insured": round(avg_sum_insured, 2),
                "expense_amount": round(premium * rng.uniform(0.05, 0.10), 2),
            })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Deliberate mess
# --------------------------------------------------------------------------- #
def add_mess(treaties: pd.DataFrame, years: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    years = years.copy()
    treaties = treaties.copy()

    # Mess 1: ~3% missing avg_sum_insured
    missing = rng.random(len(years)) < 0.03
    years.loc[missing, "avg_sum_insured"] = np.nan

    # Mess 2: three treaty-years (from three different treaties) with claims keyed with an extra zero
    ratio = years.claims_paid / years.premium_earned
    candidates = years[ratio.between(0.5, 0.9)].drop_duplicates("treaty_id")
    bad = candidates.sample(3, random_state=SEED).index
    years.loc[bad, "claims_paid"] = (years.loc[bad, "claims_paid"] * 10).round(2)

    # Mess 3: cedent_name with inconsistent casing and stray whitespace (about a third of treaties)
    def scruff(name: str) -> str:
        style = rng.integers(0, 5)
        return [name.upper(), name.lower(), f"  {name}", f"{name}   ", name.replace(" ", "  ")][style]
    messy = rng.random(len(treaties)) < 0.33
    treaties.loc[messy, "cedent_name"] = treaties.loc[messy, "cedent_name"].map(scruff)

    # Mess 4: one duplicated treaty-year row, dropped in at a random position
    dup = years.sample(1, random_state=SEED + 1)
    pos = int(rng.integers(0, len(years)))
    years = pd.concat([years.iloc[:pos], dup, years.iloc[pos:]], ignore_index=True)
    return treaties, years


def main() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    treaties = make_treaties()
    years = make_treaty_years(treaties)
    treaties, years = add_mess(treaties, years)

    treaties = treaties.drop(columns=[c for c in treaties.columns if c.startswith("hidden_")])
    treaties.to_csv(DATA_DIR / "treaties.csv", index=False)
    years.to_csv(DATA_DIR / "treaty_year.csv", index=False)

    # Quick sanity report (loss ratio is computed here only to check the data, never saved)
    lr = years.claims_paid / years.premium_earned
    plausible = lr <= 3.0
    by_line = (years.assign(lr=lr)[plausible]
               .merge(treaties[["treaty_id", "line_of_business"]], on="treaty_id")
               .groupby("line_of_business").lr.mean().sort_values())
    print(f"treaties.csv     {len(treaties):>5} rows")
    print(f"treaty_year.csv  {len(years):>5} rows  ({years.year.min()}-{years.year.max()})")
    print(f"mean loss ratio  {lr[plausible].mean():.3f}   (target ~0.75, impossible rows excluded)")
    print(f"share above 1.0  {(lr[plausible] > 1).mean():.1%}   (target ~15%)")
    print(f"rows above 3.0   {(~plausible).sum()}       (planted data-entry errors)")
    print("mean loss ratio by line of business:")
    for line, v in by_line.items():
        print(f"   {line:<18} {v:.3f}")


if __name__ == "__main__":
    main()
