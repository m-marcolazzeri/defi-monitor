"""
multi_protocol.py
-----------------
Collects APY, TVL and utilization rate for stablecoin pools on Arbitrum.

Protocols are selected dynamically by TVL threshold — no hardcoded list.
Each protocol is tagged with a type so downstream models and the dashboard
can treat lending vs non-lending protocols correctly.

Utilization rate sources, in order of preference:
  1. On-chain (Aave v3, Compound v3) — accurate
  2. DefiLlama — unreliable for most protocols, used as fallback
  3. None — for non-lending protocols where utilization is not meaningful

Usage:
    python pipeline/multi_protocol.py
"""

import requests
import pandas as pd
from datetime import datetime, timezone
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from web3_utils import get_all_utilization_rates
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    print("  [warn] web3 not installed — utilization rate from DefiLlama (may be 0)")

OUTPUT_FILE    = "data/multi_protocol.csv"
TARGET_CHAINS  = ["Arbitrum"]
TARGET_SYMBOLS = ["USDC", "USDT", "DAI", "USDC.e"]
MIN_TVL_USD    = 500_000

# Protocols explicitly excluded regardless of TVL
EXCLUDED_PROTOCOLS: list[str] = []

# Protocol type classification
# - lending:            direct deposit/borrow with measurable utilization rate
# - yield_aggregator:   auto-manages funds across other protocols
# - structured_product: options or other structured strategies
# - perpetuals_vault:   USDC liquidity used as counterparty for perp traders
# - cedefi:             hybrid centralized/decentralized yield
# - bridge:             cross-chain liquidity, not a yield protocol
# - unknown:            needs further investigation
PROTOCOL_TYPES: dict[str, str] = {
    "aave-v3":          "lending",
    "compound-v3":      "lending",
    "euler-v2":         "lending",
    "fluid-lending":    "lending",
    "dolomite":         "lending",
    "morpho":           "lending",
    "deltaprime":       "lending",
    "beefy":            "yield_aggregator",
    "woofi-earn":       "yield_aggregator",
    "autofinance":      "yield_aggregator",
    "harmonix-finance": "structured_product",
    "gains-network":    "perpetuals_vault",
    "allbridge-classic":"bridge",
    "zerobase-cedefi":  "cedefi",
    "yo-protocol":      "unknown",
}

# Protocols where utilization rate is not meaningful
NON_LENDING_TYPES = {"yield_aggregator", "structured_product", "perpetuals_vault", "bridge", "cedefi", "unknown"}


def fetch_pools() -> list[dict]:
    response = requests.get("https://yields.llama.fi/pools", timeout=20)
    response.raise_for_status()
    return response.json()["data"]


def filter_pools(pools: list[dict]) -> list[dict]:
    return [
        p for p in pools
        if p.get("chain") in TARGET_CHAINS
        and p.get("symbol") in TARGET_SYMBOLS
        and (p.get("tvlUsd") or 0) >= MIN_TVL_USD
        and p.get("project") not in EXCLUDED_PROTOCOLS
    ]


def build_row(pool: dict, timestamp: str, onchain_rates: dict) -> dict:
    protocol      = pool.get("project", "")
    symbol        = pool.get("symbol", "")
    protocol_type = PROTOCOL_TYPES.get(protocol, "unknown")

    # Utilization rate: only meaningful for lending protocols
    if protocol_type in NON_LENDING_TYPES:
        utilization = None
        util_source = "n/a"
    else:
        onchain_util = onchain_rates.get(protocol, {}).get(symbol)
        if onchain_util is not None:
            utilization = onchain_util
            util_source = "onchain"
        else:
            utilization = pool.get("utilization", 0) or 0
            util_source = "defillama"

    return {
        "timestamp":          timestamp,
        "protocol":           protocol,
        "protocol_type":      protocol_type,
        "chain":              pool.get("chain"),
        "symbol":             symbol,
        "apy_total":          round(pool.get("apy", 0) or 0, 4),
        "apy_base":           round(pool.get("apyBase", 0) or 0, 4),
        "apy_reward":         round(pool.get("apyReward", 0) or 0, 4),
        "tvl_usd":            round(pool.get("tvlUsd", 0) or 0, 2),
        "total_supply_usd":   round(pool.get("totalSupplyUsd", 0) or 0, 2),
        "total_borrow_usd":   round(pool.get("totalBorrowUsd", 0) or 0, 2),
        "utilization_rate":   utilization,
        "utilization_source": util_source,
    }


def save_snapshot(rows: list[dict]) -> pd.DataFrame:
    df_new = pd.DataFrame(rows)
    os.makedirs("data", exist_ok=True)

    if os.path.exists(OUTPUT_FILE):
        df_existing = pd.read_csv(OUTPUT_FILE)
        df_new = pd.concat([df_existing, df_new], ignore_index=True)

    df_new.to_csv(OUTPUT_FILE, index=False)
    return pd.DataFrame(rows)


def print_summary(df: pd.DataFrame):
    print(f"\n{'='*65}")
    print(f"  Stablecoin yield snapshot — Arbitrum (TVL > ${MIN_TVL_USD:,.0f})")
    print(f"{'='*65}")

    for _, row in df.sort_values("apy_total", ascending=False).iterrows():
        util = (
            f"{row['utilization_rate']*100:.1f}% [{row['utilization_source']}]"
            if row["utilization_rate"] is not None
            else f"N/A [{row['utilization_source']}]"
        )
        print(
            f"\n  {row['protocol']:<25} {row['symbol']:<8} [{row['protocol_type']}]"
            f"\n  APY:         {row['apy_total']:.2f}%"
            f"\n  Utilization: {util}"
            f"\n  TVL:         ${row['tvl_usd']:,.0f}"
        )

    best = df.sort_values("apy_total", ascending=False).iloc[0]
    print(f"\n  Best yield:        {best['protocol']} {best['symbol']} — {best['apy_total']:.2f}%")
    print(f"  Protocols tracked: {df['protocol'].nunique()}")
    print(f"  Saved to:          {OUTPUT_FILE}\n")


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching data from DefiLlama...")

    try:
        pools    = fetch_pools()
        filtered = filter_pools(pools)
        print(f"  {len(pools)} total pools — {len(filtered)} matching filters (TVL > ${MIN_TVL_USD:,.0f})")

        if not filtered:
            print("  No pools found. Check filters.")
            return

        onchain_rates = get_all_utilization_rates() if WEB3_AVAILABLE else {}
        rows = [build_row(p, timestamp, onchain_rates) for p in filtered]
        df   = save_snapshot(rows)
        print_summary(df)

    except requests.exceptions.ConnectionError:
        print("  [error] Could not reach DefiLlama API.")
    except Exception as e:
        print(f"  [error] {e}")
        raise


if __name__ == "__main__":
    main()
