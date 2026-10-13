"""
Treaty Profitability dashboard.

    streamlit run app.py

Three tabs:
  Portfolio       reads outputs/treaty_results.csv (notebook 03): which treaties lose money now, where to act.
  2026 forecast   reads outputs/treaty_forecast.csv (notebook 03): each treaty's expected loss ratio and chance of
                  losing money next year, tested by training on 2016-2024 and predicting 2025.
  Check a treaty  type in a treaty and see its expected loss ratio, chance of loss, band and the reasons. Uses the
                  regression coefficients and residuals saved by notebook 02, with plain arithmetic: no model file
                  is loaded and nothing typed in is saved.

All data is synthetic.
"""
import json
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

OUT = Path(__file__).resolve().parent / "outputs"
RESULTS = OUT / "treaty_results.csv"
COEFS = OUT / "model_coefficients.csv"
SUMMARY = OUT / "model_summary.json"
RESIDUALS = OUT / "model_residuals.csv"
FORECAST = OUT / "treaty_forecast.csv"
BACKTEST = OUT / "forecast_backtest.json"

BANDS = ["Profitable", "Watch", "Underperforming", "Critical"]
BAND_EDGES = [0.72, 0.90, 1.00]          # same thresholds as notebook 03
ACTIONS = {"Profitable": "Renew as is", "Watch": "Monitor, review pricing",
           "Underperforming": "Reprice at renewal", "Critical": "Restructure or exit"}
BAND_DOTS = {"Profitable": "🟢", "Watch": "🟡", "Underperforming": "🟠", "Critical": "🔴"}   # readable in light and dark mode


def with_dot(band: str) -> str:
    return f"{BAND_DOTS.get(band, '')} {band}"
LINES = ["Death", "TPD", "Trauma", "Income Protection"]
LINE_COLOURS = ["#55A868", "#4C72B0", "#DD8452", "#C44E52"]   # same order as LINES
TYPES = ["Quota Share", "Surplus", "Excess of Loss"]
REGIONS = ["NSW", "VIC", "QLD", "WA", "SA"]

st.set_page_config(page_title="Treaty Profitability", layout="wide")


@st.cache_data
def load_results() -> pd.DataFrame:
    return pd.read_csv(RESULTS)


@st.cache_data
def load_model() -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    summary = json.loads(SUMMARY.read_text())
    resid = pd.read_csv(RESIDUALS)
    resid["band"] = size_band(resid.policies_in_force, summary["size_band_edges"])
    return pd.read_csv(COEFS).fillna({"level": ""}), summary, resid


@st.cache_data
def load_forecast() -> tuple[pd.DataFrame, dict]:
    return pd.read_csv(FORECAST), json.loads(BACKTEST.read_text())


def size_band(policies, edges):
    """Which fifth of the training data (by treaty size) a treaty falls in: 0 = smallest."""
    return np.clip(np.searchsorted(edges, policies, side="right") - 1, 0, 4)


def band_for(loss_ratio: float) -> str:
    return BANDS[int(np.searchsorted(BAND_EDGES, loss_ratio, side="right"))]


if not RESULTS.exists():
    st.error("outputs/treaty_results.csv not found. Run notebooks/03_segmentation.ipynb first.")
    st.stop()

df = load_results()

st.title("Treaty Profitability")

tab_portfolio, tab_forecast, tab_check = st.tabs(["Portfolio", "2026 forecast", "Check a treaty"])

# =========================================================================== #
# Portfolio
# =========================================================================== #
with st.sidebar:
    st.header("Filters")
    lines = st.multiselect("Line of business", LINES, default=LINES)
    types = st.multiselect("Treaty type", TYPES, default=TYPES)
    regions = st.multiselect("Region", sorted(df.region.unique()), default=sorted(df.region.unique()))
    bands = st.multiselect("Current loss ratio band", BANDS, default=BANDS)
    st.divider()
    st.caption("Filters apply to the Portfolio and 2026 forecast tabs. Each treaty is measured on its last three "
               "years (2023-2025). "
               "Loss ratio = claims paid ÷ premium earned.")
    st.caption("Bands: Profitable < 0.72 · Watch 0.72-0.90 · Underperforming 0.90-1.00 · Critical ≥ 1.00")

with tab_portfolio:
    view = df[df.line_of_business.isin(lines) & df.treaty_type.isin(types)
              & df.region.isin(regions) & df.band.isin(bands)]
    if view.empty:
        st.warning("No treaties match these filters.")
    else:
        portfolio_lr = view.annual_claims.sum() / view.annual_premium.sum()
        at_risk = view[view.band.isin(["Underperforming", "Critical"])].annual_premium.sum()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Portfolio loss ratio", f"{portfolio_lr:.2f}", help="Total claims ÷ total premium for the treaties shown")
        c2.metric("Critical treaties", f"{(view.band == 'Critical').sum()} of {len(view)}")
        c3.metric("Dollars lost per year", f"${view.dollars_lost.sum() / 1e6:,.1f}m",
                  help="Claims paid in excess of premium, summed over treaties with a loss ratio above 1.0")
        c4.metric("Premium at risk per year", f"${at_risk / 1e6:,.0f}m",
                  help="Annual premium in the Underperforming and Critical bands")

        left, right = st.columns(2)
        with left:
            st.subheader("Loss ratio by line of business")
            by_line = (view.groupby("line_of_business")[["annual_claims", "annual_premium"]].sum()
                       .assign(loss_ratio=lambda d: d.annual_claims / d.annual_premium).reset_index())
            bars = alt.Chart(by_line).mark_bar().encode(
                x=alt.X("line_of_business:N", sort=LINES, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("loss_ratio:Q", title="Loss ratio (premium-weighted)"),
                tooltip=["line_of_business", alt.Tooltip("loss_ratio:Q", format=".3f")],
            )
            breakeven = alt.Chart(pd.DataFrame({"y": [1.0]})).mark_rule(strokeDash=[5, 4], color="red").encode(y="y:Q")
            st.altair_chart(bars + breakeven, width="stretch")

        with right:
            st.subheader("Dollars lost: worst ten treaties")
            worst = view[view.dollars_lost > 0].nlargest(10, "dollars_lost").copy()
            if worst.empty:
                st.info("No treaty in this selection loses money on claims.")
            else:
                worst["label"] = worst.treaty_id + " · " + worst.line_of_business.replace({"Income Protection": "IP"})
                worst["dollars_lost_m"] = worst.dollars_lost / 1e6
                chart = alt.Chart(worst).mark_bar().encode(
                    x=alt.X("dollars_lost_m:Q", title="$m per year"),
                    y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
                    tooltip=["treaty_id", "cedent_name", "line_of_business",
                             alt.Tooltip("avg_loss_ratio:Q", format=".3f"),
                             alt.Tooltip("dollars_lost_m:Q", format=".2f")],
                )
                st.altair_chart(chart, width="stretch")

        st.subheader("Treaties, worst loss ratio first")
        table = (view.sort_values("avg_loss_ratio", ascending=False)
                 [["treaty_id", "cedent_name", "line_of_business", "treaty_type", "region",
                   "avg_loss_ratio", "annual_premium", "dollars_lost", "band", "action"]]
                 .rename(columns={"treaty_id": "Treaty", "cedent_name": "Cedent", "line_of_business": "Line",
                                  "treaty_type": "Type", "region": "Region", "avg_loss_ratio": "Loss ratio",
                                  "annual_premium": "Premium / yr", "dollars_lost": "Dollars lost / yr",
                                  "band": "Band", "action": "Action"}))
        table["Band"] = table["Band"].map(with_dot)
        styled = (table.style
                  .format({"Loss ratio": "{:.3f}", "Premium / yr": "${:,.0f}", "Dollars lost / yr": "${:,.0f}"}))
        st.dataframe(styled, hide_index=True, width="stretch", height=460)
        st.caption(f"{len(view)} treaties shown. Source: outputs/treaty_results.csv (notebook 03).")

# =========================================================================== #
# 2026 forecast
# =========================================================================== #
with tab_forecast:
    if not (FORECAST.exists() and BACKTEST.exists()):
        st.error("outputs/treaty_forecast.csv not found. Run notebooks/03_segmentation.ipynb to the end.")
    else:
        fc, bt = load_forecast()
        fv = fc[fc.line_of_business.isin(lines) & fc.treaty_type.isin(types)
                & fc.region.isin(regions) & fc.current_band.isin(bands)]
        st.subheader("Which treaties are likely to lose money in 2026?")
        if fv.empty:
            st.warning("No treaties match these filters.")
        else:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("More likely than not to lose money", f"{(fv.chance_of_loss > 0.5).sum()} of {len(fv)}")
            k2.metric("Expected claims shortfall, 2026", f"${fv.expected_shortfall.sum() / 1e6:,.1f}m",
                      help="Expected claims in excess of premium, allowing for each treaty's chance of a bad year")
            k3.metric("Expected to slip into a worse band", f"{fv.moving_to_worse_band.sum()}")
            k4.metric("Average chance of losing money", f"{fv.chance_of_loss.mean():.0%}")

            top = fv.nlargest(15, "chance_of_loss").copy()
            top["label"] = top.treaty_id + " · " + top.line_of_business.replace({"Income Protection": "IP"})
            bars = alt.Chart(top).mark_bar().encode(
                x=alt.X("chance_of_loss:Q", title="Chance of losing money in 2026",
                        axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                y=alt.Y("label:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
                color=alt.Color("line_of_business:N", title="Line", legend=alt.Legend(orient="bottom"),
                                scale=alt.Scale(domain=LINES, range=LINE_COLOURS)),
                tooltip=["treaty_id", "cedent_name", "line_of_business", "treaty_type",
                         alt.Tooltip("expected_loss_ratio:Q", format=".2f", title="expected loss ratio"),
                         alt.Tooltip("chance_of_loss:Q", format=".0%", title="chance of loss"),
                         alt.Tooltip("expected_shortfall:Q", format="$,.0f", title="expected shortfall")],
            )
            half = alt.Chart(pd.DataFrame({"x": [0.5]})).mark_rule(strokeDash=[4, 4], color="grey").encode(x="x:Q")
            st.markdown("**Highest chance of losing money**")
            st.altair_chart(bars + half, width="stretch")

            st.markdown("**Every treaty, highest risk first**")
            ftable = fv.sort_values("chance_of_loss", ascending=False)[
                ["treaty_id", "line_of_business", "chance_of_loss", "expected_loss_ratio", "expected_band",
                 "current_loss_ratio", "current_band", "expected_shortfall", "cedent_name", "treaty_type"]]
            ftable = ftable.assign(chance_of_loss=(ftable.chance_of_loss * 100).round(0),
                                   current_band=ftable.current_band.map(with_dot),
                                   expected_band=ftable.expected_band.map(with_dot),
                                   expected_shortfall=ftable.expected_shortfall.round(0).astype(int))
            st.dataframe(ftable, hide_index=True, width="stretch", height=420, column_config={
                "treaty_id": "Treaty", "cedent_name": "Cedent", "line_of_business": "Line", "treaty_type": "Type",
                "current_loss_ratio": st.column_config.NumberColumn("Loss ratio now", format="%.2f"),
                "current_band": "Band now",
                "expected_loss_ratio": st.column_config.NumberColumn("Expected 2026", format="%.2f"),
                "expected_band": "Band 2026",
                "chance_of_loss": st.column_config.ProgressColumn("Chance of loss", min_value=0, max_value=100, format="%d%%"),
                "expected_shortfall": st.column_config.NumberColumn("Expected shortfall ($)", format="localized"),
            })
            st.caption(
                f"How good is it? Trained on 2016-2024 and tested on 2025, the forecast was "
                f"{1 - bt['rmse_regression'] / bt['rmse_portfolio_average']:.0%} more accurate than the portfolio average "
                f"and ranked loss-making treaties with an AUC of {bt['auc_regression']:.2f} "
                f"(vs {bt['auc_own_history']:.2f} using each treaty's own history). It was too optimistic: it predicted "
                f"{bt['predicted_share_losing']:.0%} of treaties would lose money and {bt['actual_share_losing']:.0%} did, "
                "so read the chances as a ranking of risk. Synthetic data; see notebook 03, section 8.")

# =========================================================================== #
# Check a treaty
# =========================================================================== #
with tab_check:
    if not (COEFS.exists() and SUMMARY.exists() and RESIDUALS.exists()):
        st.error("outputs/model_coefficients.csv not found. Run notebooks/02_regression.ipynb first.")
    else:
        coefs, summary, resid = load_model()
        st.subheader("What loss ratio should we expect from this treaty, and why?")
        st.caption("Enter a treaty's details. The estimate applies the regression from notebook 02, "
                   "so every number below can be traced to a coefficient. Nothing you enter is saved.")

        with st.form("check"):
            a, b, c = st.columns(3)
            line = a.selectbox("Line of business", LINES, index=3)
            ttype = a.selectbox("Treaty type", TYPES)
            region = a.selectbox("Region", REGIONS)
            age = b.number_input("Treaty age (years since inception)", 0, 40, 8)
            large = b.number_input("Large claims expected this year", 0, 10, 1,
                                   help="Claims above the retention limit")
            policies = b.number_input("Policies in force", 500, 50_000, 5_000, step=500)
            cession = c.slider("Cession % (reinsurer's share)", 0.20, 0.60, 0.40, 0.01)
            premium = c.number_input("Annual premium earned ($)", 0, 200_000_000, 5_000_000, step=250_000)
            submitted = st.form_submit_button("Check treaty", type="primary")

        def coef(feature, level=""):
            row = coefs[(coefs.feature == feature) & (coefs.level == level)]
            return (float(row.coefficient.iloc[0]), float(row.p_value.iloc[0])) if len(row) else (0.0, np.nan)

        # Each row: what it is, the value used, its effect on the loss ratio, and whether it is significant
        parts = []
        b0, _ = coef("intercept")
        parts.append(("Starting point", "Death · Quota Share · NSW", b0, 0.0))
        for feature, value, label in [("line_of_business", line, "Line"), ("treaty_type", ttype, "Treaty type"),
                                      ("region", region, "Region")]:
            if value in ("Death", "Quota Share", "NSW"):
                continue  # the reference level is already in the starting point
            k, p = coef(feature, value)
            parts.append((f"{label}: {value}", "vs reference", k, p))
        for feature, value, label, shown in [
            ("treaty_age", age, "Treaty age", f"{age} years"),
            ("large_claim_count", large, "Large claims", f"{large}"),
            ("log_policies", np.log(policies), "Size", f"{policies:,} policies (log)"),
            ("cession_pct", cession, "Cession %", f"{cession:.0%}"),
        ]:
            k, p = coef(feature)
            parts.append((label, shown, k * value, p))

        breakdown = pd.DataFrame(parts, columns=["Driver", "Value", "Effect", "p_value"])
        expected = breakdown.Effect.sum()
        band = band_for(expected)
        rmse = summary["test_rmse"]
        # Chance of losing money: how often treaties of a similar size ended up above 1.0 given this expectation
        similar = resid.residual[resid.band == size_band(policies, summary["size_band_edges"])]
        chance = float((expected + similar > 1).mean())

        m1, m2, m3 = st.columns(3)
        m1.metric("Expected loss ratio", f"{expected:.2f}",
                  help=f"A single year typically lands within about ±{rmse:.2f} of this (test RMSE)")
        m2.metric("Chance of losing money", f"{chance:.0%}",
                  help="Share of similar-sized treaties in the training data that ended above 1.0 from this starting "
                       "point. It can sit below 50% even when the expected loss ratio is above 1.0: bad years are rarer "
                       "but bigger, so they pull the average up. The 2025 backtest suggests real chances run somewhat higher.")
        m3.metric("Band", with_dot(band))
        msg = (f"**Recommended action: {ACTIONS[band]}.** Expected loss ratio **{expected:.2f}**, with a **{chance:.0%} chance** of paying out more than the "
               f"premium in a given year. A single year usually lands between "
               f"{max(expected - rmse, 0):.2f} and {expected + rmse:.2f}.")
        if premium:
            claims = expected * premium
            msg += (f" On ${premium:,.0f} of premium that is about **${claims:,.0f}** in claims, "
                    + (f"a claims surplus of ${premium - claims:,.0f}." if claims <= premium
                       else f"**${claims - premium:,.0f} more than the premium**."))
        msg = msg.replace("$", "\\$")  # Streamlit reads $...$ as maths; show plain dollar signs
        {"Profitable": st.success, "Watch": st.info, "Underperforming": st.warning,
         "Critical": st.error}[band](msg)

        left, right = st.columns([1, 1])
        with left:
            st.markdown("**Why: how each driver moves the loss ratio**")
            wf = breakdown.copy()
            wf["end"] = wf.Effect.cumsum()
            wf["start"] = wf.end - wf.Effect
            wf["order"] = range(len(wf))
            wf["direction"] = np.where(wf.order == 0, "Starting point", np.where(wf.Effect >= 0, "Raises", "Lowers"))
            waterfall = alt.Chart(wf).mark_bar(size=22).encode(
                y=alt.Y("Driver:N", sort=alt.SortField("order"), title=None, axis=alt.Axis(labelLimit=220)),
                x=alt.X("start:Q", title="Loss ratio"), x2="end:Q",
                color=alt.Color("direction:N", scale=alt.Scale(domain=["Starting point", "Raises", "Lowers"],
                                                               range=["#8DA0CB", "#C44E52", "#55A868"]),
                                legend=alt.Legend(title=None, orient="bottom")),
                tooltip=["Driver", "Value", alt.Tooltip("Effect:Q", format="+.3f")],
            )
            rules = alt.Chart(pd.DataFrame({"x": BAND_EDGES})).mark_rule(strokeDash=[4, 4], color="grey").encode(x="x:Q")
            st.altair_chart(waterfall + rules, width="stretch")
            st.caption("Dashed lines: band thresholds at 0.72, 0.90 and 1.00.")
        with right:
            st.markdown("**The numbers behind it**")
            shown = breakdown.assign(
                Significant=np.where(breakdown.p_value.isna(), "", np.where(breakdown.p_value < 0.05, "yes", "no")))
            st.dataframe(shown[["Driver", "Value", "Effect", "Significant"]].style.format({"Effect": "{:+.3f}"}),
                         hide_index=True, width="stretch")
            st.caption("'no' = the regression found no reliable effect (for example region and cession %), "
                       "so treat its contribution as roughly zero.")

        st.markdown("**How it compares with the portfolio**")
        peers = df[(df.line_of_business == line) & (df.treaty_type == ttype)]
        p1, p2 = st.columns(2)
        p1.metric("Worse than this share of current treaties", f"{(df.avg_loss_ratio < expected).mean():.0%}")
        if len(peers):
            p2.metric(f"Current {line} · {ttype} treaties", f"{len(peers)}",
                      f"average loss ratio {peers.annual_claims.sum() / peers.annual_premium.sum():.2f}",
                      delta_color="off")
        else:
            p2.metric(f"Current {line} · {ttype} treaties", "none")
        st.caption(f"Model explains about {summary['test_r2']:.0%} of the year-to-year variation on held-out data; "
                   "the rest is mostly large-claim luck and small-treaty volatility. Synthetic data.")
