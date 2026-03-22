"""
risk_classifier.py
------------------
Assigns a risk label (green / yellow / red) to each protocol based on
objective, verifiable criteria. No arbitrary weights.

Each criterion is binary and independently justifiable:
- Exploit history:  factual on-chain/public record (source: rekt.news)
- TVL:              liquidity depth — proxy for protocol maturity and trust
- Protocol age:     Lindy effect — longer survival = lower expected failure rate
- APY anomaly:      unsustainably high yields historically precede protocol failures
- TVL trend:        sudden outflows are the earliest observable stress signal
- Utilization:      >95% means depositors may not be able to withdraw

Labels:
  green  — no red flags, established protocol
  yellow — one or more caution signals, proceed carefully
  red    — serious warning, avoid or exit

Usage:
    python models/risk_classifier.py
    from models.risk_classifier import classify_protocols
"""

import pandas as pd
import numpy as np
import os

INPUT_FILE  = "data/multi_protocol.csv"
OUTPUT_FILE = "data/risk_labels.csv"

# ── Thresholds ────────────────────────────────────────────────────────────────

TVL_YELLOW = 1_000_000
TVL_RED    = 500_000

APY_ANOMALY_MULTIPLIER = 3.0

TVL_DROP_YELLOW = 0.10
TVL_DROP_RED    = 0.25

UTIL_YELLOW = 0.90
UTIL_RED    = 0.95

EXPLOITED_PROTOCOLS = set()

PROTOCOL_LAUNCH_YEAR = {
    "aave-v3":          2022,
    "compound-v3":      2022,
    "euler-v2":         2024,
    "fluid-lending":    2024,
    "dolomite":         2022,
    "morpho":           2022,
    "deltaprime":       2023,
    "beefy":            2020,
    "gains-network":    2021,
    "woofi-earn":       2021,
    "autofinance":      2023,
    "harmonix-finance": 2024,
    "allbridge-classic":2021,
    "zerobase-cedefi":  2023,
    "yo-protocol":      2024,
}

CURRENT_YEAR = 2026


# ── Classification logic ──────────────────────────────────────────────────────

def classify_protocol(row: pd.Series, median_apy: float, tvl_change: float | None) -> dict:
    flags  = []
    is_red = False

    protocol = row["protocol"]
    apy      = row["apy_total"]
    tvl      = row["tvl_usd"]
    util     = row.get("utilization_rate")

    # 1. Exploit history
    if protocol in EXPLOITED_PROTOCOLS:
        flags.append("exploit_history")
        is_red = True

    # 2. TVL
    if tvl < TVL_RED:
        flags.append(f"tvl_very_low (${tvl:,.0f})")
        is_red = True
    elif tvl < TVL_YELLOW:
        flags.append(f"tvl_low (${tvl:,.0f})")

    # 3. Protocol age
    launch_year = PROTOCOL_LAUNCH_YEAR.get(protocol)
    if launch_year is None:
        flags.append("age_unknown")
    elif (CURRENT_YEAR - launch_year) < 1:
        flags.append(f"age_less_than_1_year (launched {launch_year})")

    # 4. APY anomaly
    if median_apy > 0 and apy > median_apy * APY_ANOMALY_MULTIPLIER:
        flags.append(f"apy_anomaly ({apy:.1f}% vs median {median_apy:.1f}%)")
        is_red = True

    # 5. TVL trend — only applied when pool_id is used as key (avoids cross-pool mixing)
    if tvl_change is not None:
        if tvl_change <= -TVL_DROP_RED:
            flags.append(f"tvl_drop_severe ({tvl_change*100:.1f}%)")
            is_red = True
        elif tvl_change <= -TVL_DROP_YELLOW:
            flags.append(f"tvl_drop ({tvl_change*100:.1f}%)")

    # 6. Utilization rate (lending protocols only)
    if util is not None and not (isinstance(util, float) and np.isnan(util)):
        if util >= UTIL_RED:
            flags.append(f"utilization_critical ({util*100:.1f}%)")
            is_red = True
        elif util >= UTIL_YELLOW:
            flags.append(f"utilization_high ({util*100:.1f}%)")

    if is_red:
        label = "red"
    elif len(flags) > 0:
        label = "yellow"
    else:
        label = "green"

    return {"risk_label": label, "risk_flags": "; ".join(flags) if flags else "none"}


def compute_tvl_changes(df: pd.DataFrame) -> dict[str, float | None]:
    """
    Compute TVL change between the two most recent observations per pool.

    Uses pool_id as the grouping key to avoid false alarms caused by mixing
    distinct pools that share the same protocol name and symbol
    (e.g. two separate Aave USDC pools on Arbitrum with very different TVLs).
    Falls back to protocol+symbol if pool_id is not present.
    """
    changes = {}
    group_key = "pool_id" if "pool_id" in df.columns else None

    if group_key:
        groups = df.groupby("pool_id")
    else:
        # Legacy fallback — less accurate
        groups = df.groupby(["protocol", "symbol"])

    for key, group in groups:
        sorted_group = group.sort_values("timestamp")
        if len(sorted_group) >= 2:
            prev = sorted_group.iloc[-2]["tvl_usd"]
            curr = sorted_group.iloc[-1]["tvl_usd"]
            changes[key] = (curr - prev) / prev if prev > 0 else None
        else:
            changes[key] = None

    return changes


def classify_protocols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the classifier on the latest snapshot of each pool.
    Groups by pool_id to avoid false TVL drops from cross-pool mixing.
    """
    tvl_changes = compute_tvl_changes(df)

    # Get latest snapshot per pool
    group_key = ["pool_id"] if "pool_id" in df.columns else ["protocol", "symbol"]
    latest = (
        df.sort_values("timestamp")
        .groupby(group_key)
        .last()
        .reset_index()
    )

    median_apy = latest["apy_total"].median()

    results = []
    for _, row in latest.iterrows():
        key        = row["pool_id"] if "pool_id" in row else f"{row['protocol']}|{row['symbol']}"
        tvl_change = tvl_changes.get(key)
        result     = classify_protocol(row, median_apy, tvl_change)
        results.append({**row.to_dict(), **result})

    return pd.DataFrame(results)


def print_report(df: pd.DataFrame):
    print(f"\n{'='*65}")
    print("  Protocol Risk Classification Report")
    print(f"{'='*65}")

    label_order = {"red": 0, "yellow": 1, "green": 2}
    df_sorted = df.sort_values("risk_label", key=lambda x: x.map(label_order))
    icons = {"green": "🟢", "yellow": "🟡", "red": "🔴"}

    for _, row in df_sorted.iterrows():
        icon = icons.get(row["risk_label"], "⚪")
        print(
            f"\n  {icon} {row['protocol']:<25} {row['symbol']:<8}"
            f"\n     APY: {row['apy_total']:.2f}%  |  TVL: ${row['tvl_usd']:,.0f}"
            f"\n     Flags: {row['risk_flags']}"
        )

    counts = df["risk_label"].value_counts()
    print(
        f"\n  Summary: "
        f"🟢 {counts.get('green', 0)} green  "
        f"🟡 {counts.get('yellow', 0)} yellow  "
        f"🔴 {counts.get('red', 0)} red"
    )
    print(f"  Saved to: {OUTPUT_FILE}\n")


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[error] {INPUT_FILE} not found. Run pipeline/multi_protocol.py first.")
        return

    df = pd.read_csv(INPUT_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    result = classify_protocols(df)
    os.makedirs("data", exist_ok=True)
    result.to_csv(OUTPUT_FILE, index=False)
    print_report(result)


if __name__ == "__main__":
    main()
