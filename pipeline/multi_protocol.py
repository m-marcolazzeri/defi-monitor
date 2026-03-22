"""
multi_protocol.py
-----------------
Collects APY, TVL and utilization rate for stablecoin pools on Arbitrum
from DefiLlama, with utilization rate overridden by on-chain Aave v3 data
where available.

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
PROTOCOLS      = ["aave-v3", "compound-v3", "morpho", "spark", "fluid"]


def fetch_pools() -> list[dict]:
    response = requests.get("https://yields.llama.fi/pools", timeout=20)
    response.raise_for_status()
    return response.json()["data"]


def filter_pools(pools: list[dict]) -> list[dict]:
    return [
        p for p in pools
        if p.get("project") in PROTOCOLS
        and p.get("chain") in TARGET_CHAINS
        and p.get("symbol") in TARGET_SYMBOLS
    ]


def build_row(pool: dict, timestamp: str, onchain_rates: dict) -> dict:
    symbol       = pool.get("symbol", "")
    onchain_util = onchain_rates.get(symbol)

    if onchain_util is not None:
        utilization = onchain_util
        util_source = "onchain"
    else:
        utilization = pool.get("utilization", 0) or 0
        util_source = "defillama"

    return {
        "timestamp":          timestamp,
        "protocol":           pool.get("project"),
        "chain":              pool.get("chain"),
        "symbol":             symbol,
        "apy_total":          round(pool.get("apy", 0) or 0, 4),
        "apy_base":           round(pool.get("apyBase", 0) or 0, 4),
        "apy_reward":         round(pool.get("apyReward", 0) or 0, 4),
        "tvl_usd":            round(pool.get("tvlUsd", 0) or 0, 2),
        "total_supply_usd":   round(pool.get("totalSupplyUsd", 0) or 0, 2),
        "total_borrow_usd":   round(pool.get("totalBorrowUsd", 0) or 0, 2),
        "utilization_rate":   round(utilization, 6),
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
    print(f"\n{'='*60}")
    print("  Stablecoin yield snapshot — Arbitrum")
    print(f"{'='*60}")

    for _, row in df.sort_values("apy_total", ascending=False).iterrows():
        print(
            f"\n  {row['protocol']:<20} {row['symbol']:<8}"
            f"\n  APY:          {row['apy_total']:.2f}%"
            f"\n  Utilization:  {row['utilization_rate']*100:.1f}% [{row.get('utilization_source', '?')}]"
            f"\n  TVL:          ${row['tvl_usd']:,.0f}"
        )

    best = df.sort_values("apy_total", ascending=False).iloc[0]
    print(f"\n  Best yield: {best['protocol']} {best['symbol']} — {best['apy_total']:.2f}%")
    print(f"  Saved to:   {OUTPUT_FILE}\n")


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching data from DefiLlama...")

    try:
        pools    = fetch_pools()
        filtered = filter_pools(pools)
        print(f"  {len(pools)} total pools — {len(filtered)} matching filters")

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
