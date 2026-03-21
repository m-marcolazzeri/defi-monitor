"""
Multi-Protocol DeFi Data Pipeline
-----------------------------------
Raccoglie APY, TVL e utilization rate da più protocolli di lending
su Arbitrum: Aave v3, Compound v3, Morpho, Spark.

AGGIORNAMENTO:
  L'utilization rate viene ora letto direttamente dalla blockchain
  tramite Web3.py (web3_utils.py), risolvendo il problema del valore
  sempre a 0.0% restituito da DefiLlama.

ESECUZIONE:
    python pipeline/multi_protocol.py
"""

import requests
import pandas as pd
from datetime import datetime, timezone
import os
import sys

# Aggiunge la cartella root al path per importare web3_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from web3_utils import get_all_utilization_rates
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False
    print("  ⚠️  web3 non installato. Utilization rate da DefiLlama (potrebbe essere 0).")
    print("     Installa con: pip install web3")

OUTPUT_FILE = "data/multi_protocol.csv"

PROTOCOLS = [
    "aave-v3",
    "compound-v3",
    "morpho",
    "spark",
    "fluid",
]

TARGET_CHAINS  = ["Arbitrum"]
TARGET_SYMBOLS = ["USDC", "USDT", "DAI", "USDC.e"]


def fetch_pools() -> list[dict]:
    """Scarica tutti i pool da DefiLlama."""
    url = "https://yields.llama.fi/pools"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()["data"]


def filter_pools(pools: list[dict]) -> list[dict]:
    """Filtra per protocolli, chain e simboli target."""
    return [
        p for p in pools
        if p.get("project") in PROTOCOLS
        and p.get("chain") in TARGET_CHAINS
        and p.get("symbol") in TARGET_SYMBOLS
    ]


def build_row(pool: dict, timestamp: str, onchain_rates: dict) -> dict:
    """
    Trasforma un pool in una riga del dataframe.

    Per l'utilization rate:
    - Prima tenta di usare il valore on-chain (Web3, accurato)
    - Fallback al valore DefiLlama (spesso 0, inaffidabile)
    """
    symbol = pool.get("symbol", "")

    # Utilization rate on-chain se disponibile
    onchain_util = onchain_rates.get(symbol)
    defillama_util = pool.get("utilization", 0) or 0

    if onchain_util is not None:
        utilization = onchain_util
        util_source = "onchain"
    else:
        utilization = defillama_util
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
    """Aggiunge lo snapshot al CSV storico."""
    df_new = pd.DataFrame(rows)
    os.makedirs("data", exist_ok=True)

    if os.path.exists(OUTPUT_FILE):
        df_existing = pd.read_csv(OUTPUT_FILE)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_combined = df_new

    df_combined.to_csv(OUTPUT_FILE, index=False)
    return df_new


def print_summary(df: pd.DataFrame):
    """Stampa un confronto leggibile tra i protocolli."""
    print("\n" + "="*65)
    print("  Multi-Protocol Snapshot — Stablecoin Yield su Arbitrum")
    print("="*65)

    df_sorted = df.sort_values("apy_total", ascending=False)

    for _, row in df_sorted.iterrows():
        util_label = f"{row['utilization_rate']*100:.1f}%"
        source_tag = f"[{row.get('utilization_source', '?')}]"
        print(f"\n  {row['protocol']:20s} | {row['symbol']:6s}")
        print(f"  APY totale:        {row['apy_total']:.2f}%")
        print(f"  Utilization rate:  {util_label} {source_tag}")
        print(f"  TVL:               ${row['tvl_usd']:,.0f}")

    print("\n" + "="*65)

    best = df_sorted.iloc[0]
    print(f"\n  → Best yield ora: {best['protocol']} su {best['symbol']}")
    print(f"    APY: {best['apy_total']:.2f}% | "
          f"Utilization: {best['utilization_rate']*100:.1f}%")
    print(f"\n  Dati salvati in: {OUTPUT_FILE}\n")


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching dati da DefiLlama...")

    try:
        # 1. Dati DefiLlama
        all_pools = fetch_pools()
        print(f"  → {len(all_pools)} pool totali trovati")

        filtered = filter_pools(all_pools)
        print(f"  → {len(filtered)} pool rilevanti trovati")

        if not filtered:
            print("  ⚠️  Nessun pool trovato. Controlla i filtri.")
            return

        # 2. Utilization rate on-chain (Web3)
        onchain_rates = {}
        if WEB3_AVAILABLE:
            onchain_rates = get_all_utilization_rates()
        
        # 3. Costruisci righe e salva
        rows = [build_row(p, timestamp, onchain_rates) for p in filtered]
        df = save_snapshot(rows)
        print_summary(df)

    except requests.exceptions.ConnectionError:
        print("  ❌ Errore di connessione a DefiLlama.")
    except Exception as e:
        print(f"  ❌ Errore: {e}")
        raise


if __name__ == "__main__":
    main()
