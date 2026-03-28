"""
rebalancing_advisor.py
----------------------
Calculates whether it is worth moving capital from the current protocol
to a higher-yielding alternative, accounting for gas costs.

Core question: given my current position, is the yield improvement large
enough to justify the transaction cost of moving?

Net benefit formula:
    gain        = (apy_target - apy_current) * capital * days / 365
    net_benefit = gain - gas_cost_usd * 2   (exit current + enter target)
    breakeven   = (gas_cost_usd * 2) / ((apy_target - apy_current) * capital / 365)

Only green-labelled protocols are considered as rebalancing targets.
Yellow and red protocols are excluded regardless of APY.

Usage:
    python models/rebalancing_advisor.py
    from models.rebalancing_advisor import get_recommendations
"""

import pandas as pd
import os

PROTOCOL_DATA  = "data/multi_protocol.csv"
RISK_DATA      = "data/risk_labels.csv"
OUTPUT_FILE    = "data/rebalancing_recommendations.csv"

# Estimated round-trip gas cost on Arbitrum (exit + enter = 2 transactions)
# Based on observed costs: ~$0.10-0.30 per transaction on Arbitrum
GAS_COST_PER_TX_USD = 0.20
GAS_ROUND_TRIP      = GAS_COST_PER_TX_USD * 2   # $0.40 total

# Minimum APY improvement to surface a recommendation
# Below this threshold the move is not worth the operational overhead
MIN_APY_IMPROVEMENT = 0.25   # 0.25 percentage points


def load_latest_snapshot() -> pd.DataFrame:
    """Load the most recent APY/TVL snapshot for each pool."""
    if not os.path.exists(PROTOCOL_DATA):
        raise FileNotFoundError(f"{PROTOCOL_DATA} not found.")
    df = pd.read_csv(PROTOCOL_DATA)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    group_key = ["pool_id"] if "pool_id" in df.columns else ["protocol", "symbol"]
    return (
        df.sort_values("timestamp")
        .groupby(group_key)
        .last()
        .reset_index()
    )


def load_risk_labels() -> pd.DataFrame:
    """Load risk classification results."""
    if not os.path.exists(RISK_DATA):
        raise FileNotFoundError(
            f"{RISK_DATA} not found. Run models/risk_classifier.py first."
        )
    return pd.read_csv(RISK_DATA)


def merge_risk(snapshot: pd.DataFrame, risk: pd.DataFrame) -> pd.DataFrame:
    """Attach risk labels to the snapshot."""
    key = "pool_id" if "pool_id" in snapshot.columns and "pool_id" in risk.columns else None
    if key:
        return snapshot.merge(risk[["pool_id", "risk_label", "risk_flags"]], on="pool_id", how="left")
    return snapshot.merge(
        risk[["protocol", "symbol", "risk_label", "risk_flags"]],
        on=["protocol", "symbol"], how="left"
    )


def compute_recommendations(
    df: pd.DataFrame,
    capital_usd: float,
    horizon_days: int,
    current_protocol: str,
    current_symbol: str,
) -> pd.DataFrame:
    """
    For a given current position, compute the net benefit of moving to
    each green-rated alternative with a higher APY.

    Parameters
    ----------
    capital_usd       : amount currently deployed (USD)
    horizon_days      : expected holding period (days)
    current_protocol  : name of the current protocol (e.g. "aave-v3")
    current_symbol    : token symbol (e.g. "USDC")

    Returns a dataframe sorted by net_benefit descending.
    """
    # Find current APY
    current = df[
        (df["protocol"] == current_protocol) &
        (df["symbol"] == current_symbol)
    ]
    if current.empty:
        raise ValueError(f"No data found for {current_protocol} {current_symbol}")

    current_apy = current.iloc[0]["apy_total"]

    # Candidates: green protocols with higher APY, same symbol
    candidates = df[
        (df["symbol"] == current_symbol) &
        (df["risk_label"] == "green") &
        (df["apy_total"] > current_apy + MIN_APY_IMPROVEMENT) &
        ~((df["protocol"] == current_protocol))
    ].copy()

    if candidates.empty:
        return pd.DataFrame()

    # Compute net benefit for each candidate
    candidates["current_protocol"] = current_protocol
    candidates["current_apy"]      = current_apy
    candidates["apy_improvement"]  = candidates["apy_total"] - current_apy
    candidates["capital_usd"]      = capital_usd
    candidates["horizon_days"]     = horizon_days
    candidates["gas_cost_usd"]     = GAS_ROUND_TRIP

    candidates["gross_gain_usd"] = (
        candidates["apy_improvement"] / 100 * capital_usd * horizon_days / 365
    )
    candidates["net_benefit_usd"] = candidates["gross_gain_usd"] - GAS_ROUND_TRIP

    # Breakeven: days needed for the gain to cover gas cost
    candidates["breakeven_days"] = (
        GAS_ROUND_TRIP /
        (candidates["apy_improvement"] / 100 * capital_usd / 365)
    ).round(1)

    candidates["recommendation"] = candidates["net_benefit_usd"].apply(
        lambda x: "MOVE" if x > 0 else "WAIT"
    )

    cols = [
        "protocol", "symbol", "apy_total", "tvl_usd", "risk_label",
        "current_protocol", "current_apy", "apy_improvement",
        "gross_gain_usd", "net_benefit_usd", "breakeven_days",
        "gas_cost_usd", "capital_usd", "horizon_days", "recommendation"
    ]
    return candidates[cols].sort_values("net_benefit_usd", ascending=False)


def print_report(
    recommendations: pd.DataFrame,
    current_protocol: str,
    current_apy: float,
    capital_usd: float,
    horizon_days: int,
):
    print(f"\n{'='*65}")
    print("  Rebalancing Advisor")
    print(f"{'='*65}")
    print(f"  Current position : {current_protocol} — {current_apy:.2f}% APY")
    print(f"  Capital          : ${capital_usd:,.2f}")
    print(f"  Horizon          : {horizon_days} days")
    print(f"  Gas (round trip) : ${GAS_ROUND_TRIP:.2f}")
    print(f"{'='*65}")

    if recommendations.empty:
        print("\n  No better alternatives available right now.")
        print("  Either no green protocol offers a significant APY improvement,")
        print("  or the gas cost exceeds the expected gain for your capital size.")
    else:
        for _, row in recommendations.iterrows():
            action = "✅ MOVE" if row["recommendation"] == "MOVE" else "⏳ WAIT"
            print(
                f"\n  {action}  →  {row['protocol']} {row['symbol']}"
                f"\n    APY:          {row['apy_total']:.2f}% "
                f"(+{row['apy_improvement']:.2f}% vs current)"
                f"\n    Gross gain:   ${row['gross_gain_usd']:.4f} over {horizon_days} days"
                f"\n    Gas cost:     ${row['gas_cost_usd']:.2f}"
                f"\n    Net benefit:  ${row['net_benefit_usd']:.4f}"
                f"\n    Breakeven:    {row['breakeven_days']} days"
                f"\n    TVL:          ${row['tvl_usd']:,.0f}  [{row['risk_label']}]"
            )

    print(f"\n  Saved to: {OUTPUT_FILE}\n")


def get_recommendations(
    capital_usd: float = 20.0,
    horizon_days: int  = 30,
    current_protocol: str = "aave-v3",
    current_symbol: str   = "USDC",
) -> pd.DataFrame:
    """Public interface for use from the dashboard or other modules."""
    snapshot = load_latest_snapshot()
    risk     = load_risk_labels()
    df       = merge_risk(snapshot, risk)
    return compute_recommendations(df, capital_usd, horizon_days, current_protocol, current_symbol)


def main():
    # Default scenario: the position we opened on Aave v3
    CAPITAL          = 19.61    # actual deployed capital in USD
    HORIZON_DAYS     = 30
    CURRENT_PROTOCOL = "aave-v3"
    CURRENT_SYMBOL   = "USDC"

    try:
        snapshot = load_latest_snapshot()
        risk     = load_risk_labels()
        df       = merge_risk(snapshot, risk)

        current_apy = df[
            (df["protocol"] == CURRENT_PROTOCOL) &
            (df["symbol"] == CURRENT_SYMBOL)
        ].iloc[0]["apy_total"]

        recs = compute_recommendations(df, CAPITAL, HORIZON_DAYS, CURRENT_PROTOCOL, CURRENT_SYMBOL)

        if not recs.empty:
            os.makedirs("data", exist_ok=True)
            recs.to_csv(OUTPUT_FILE, index=False)

        print_report(recs, CURRENT_PROTOCOL, current_apy, CAPITAL, HORIZON_DAYS)

    except FileNotFoundError as e:
        print(f"[error] {e}")
    except Exception as e:
        print(f"[error] {e}")
        raise


if __name__ == "__main__":
    main()
