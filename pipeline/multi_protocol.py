"""
Multi-Protocol DeFi Data Pipeline
-----------------------------------
Raccoglie APY, TVL e utilization rate da più protocolli di lending
su Arbitrum: Aave v3, Compound v3, Morpho, Spark.

Confrontare i protocolli è il primo step verso l'ottimizzazione
dell'allocazione — esattamente quello che fa Dialectic con Chronograph.

ESECUZIONE:
    python pipeline/multi_protocol.py
"""

import requests
import pandas as pd
from datetime import datetime, timezone
import os

OUTPUT_FILE = "data/multi_protocol.csv"

# ─── Protocolli da monitorare ─────────────────────────────────────────────────
# Filtriamo da DefiLlama i protocolli più rilevanti per stablecoin su Arbitrum.
# Aggiungere un protocollo = aggiungere una riga qui.

PROTOCOLS = [
    "aave-v3",
    "compound-v3",
    "morpho",
    "spark",
    "fluid",
]

TARGET_CHAINS = ["Arbitrum"]
TARGET_SYMBOLS = ["USDC", "USDT", "DAI", "USDC.e"]


def fetch_pools() -> list[dict]:
    """Scarica tutti i pool da DefiLlama."""
    url = "https://yields.llama.fi/pools"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    return response.json()["data"]


def filter_pools(pools: list[dict]) -> list[dict]:
    """
    Filtra per protocolli, chain e simboli target.
    
    Ogni pool ha:
    - project: nome del protocollo
    - chain: blockchain
    - symbol: token
    - apy: rendimento annualizzato totale
    - apyBase: rendimento da interessi dei borrower
    - apyReward: rendimento da incentivi del protocollo
    - tvlUsd: Total Value Locked
    - utilization: % di liquidità presa in prestito
    - totalSupplyUsd: totale depositato
    - totalBorrowUsd: totale borrowed
    """
    return [
        p for p in pools
        if p.get("project") in PROTOCOLS
        and p.get("chain") in TARGET_CHAINS
        and p.get("symbol") in TARGET_SYMBOLS
    ]


def build_row(pool: dict, timestamp: str) -> dict:
    """Trasforma un pool in una riga del dataframe."""
    return {
        "timestamp":         timestamp,
        "protocol":          pool.get("project"),
        "chain":             pool.get("chain"),
        "symbol":            pool.get("symbol"),
        "apy_total":         round(pool.get("apy", 0) or 0, 4),
        "apy_base":          round(pool.get("apyBase", 0) or 0, 4),
        "apy_reward":        round(pool.get("apyReward", 0) or 0, 4),
        "tvl_usd":           round(pool.get("tvlUsd", 0) or 0, 2),
        "total_supply_usd":  round(pool.get("totalSupplyUsd", 0) or 0, 2),
        "total_borrow_usd":  round(pool.get("totalBorrowUsd", 0) or 0, 2),
        "utilization_rate":  round(pool.get("utilization", 0) or 0, 4),
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

    # Ordina per APY decrescente per vedere subito le opportunità migliori
    df_sorted = df.sort_values("apy_total", ascending=False)

    for _, row in df_sorted.iterrows():
        print(f"\n  {row['protocol']:20s} | {row['symbol']:6s}")
        print(f"  APY totale:        {row['apy_total']:.2f}%")
        print(f"  Utilization rate:  {row['utilization_rate']*100:.1f}%")
        print(f"  TVL:               ${row['tvl_usd']:,.0f}")

    print("\n" + "="*65)

    # Calcola e mostra il best opportunity
    best = df_sorted.iloc[0]
    print(f"\n  → Best yield ora: {best['protocol']} su {best['symbol']}")
    print(f"    APY: {best['apy_total']:.2f}% | "
          f"Utilization: {best['utilization_rate']*100:.1f}%")
    print(f"\n  Dati salvati in: {OUTPUT_FILE}\n")


def main():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching dati da DefiLlama...")

    try:
        all_pools = fetch_pools()
        print(f"  → {len(all_pools)} pool totali trovati")

        filtered = filter_pools(all_pools)
        print(f"  → {len(filtered)} pool rilevanti trovati")

        if not filtered:
            print("  ⚠️  Nessun pool trovato. Controlla i filtri.")
            return

        rows = [build_row(p, timestamp) for p in filtered]
        df = save_snapshot(rows)
        print_summary(df)

    except requests.exceptions.ConnectionError:
        print("  ❌ Errore di connessione.")
    except Exception as e:
        print(f"  ❌ Errore: {e}")


if __name__ == "__main__":
    main()
