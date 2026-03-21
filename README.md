# DeFi Strategy Monitor

A data engineering and ML system that replicates and monitors institutional DeFi yield strategies — built as a practical study of how professional operators like [Dialectic](https://dialectic.ky) manage capital on-chain.

## What This Project Does

This system monitors, measures and analyzes **market-neutral stablecoin yield strategies** (equivalent to Dialectic's Chronograph fund) across multiple DeFi lending protocols on Arbitrum.

It answers three questions that matter to any DeFi operator:

1. **Where is the best risk-adjusted yield right now?** — across Aave, Compound, Morpho and others
2. **Is something going wrong?** — anomaly detection on TVL, APY and utilization rate
3. **How has the strategy performed over time?** — risk-adjusted return metrics, benchmarked against the risk-free rate

## Architecture

```
DATA SOURCES                  PIPELINE              OUTPUT
────────────────────          ─────────────         ──────────────────────
DefiLlama API            →                    →     CSV historical data
On-chain via Web3.py     →    GitHub Actions  →     Streamlit Dashboard
                              (daily cron)    →     Anomaly alerts
```

### Project Structure

```
defi-monitor/
│
├── pipeline/
│   ├── aave_tracker.py         # Collects APY, TVL, utilization rate daily
│   └── multi_protocol.py       # Extends tracking to Compound, Morpho, Spark
│
├── models/
│   └── anomaly_detector.py     # Isolation Forest on APY + TVL time series
│
├── dashboard/
│   └── app.py                  # Streamlit dashboard (live at [URL])
│
├── data/
│   └── aave_usdc_arbitrum.csv  # Auto-updated daily via GitHub Actions
│
├── notebooks/
│   └── 01_exploratory.ipynb    # EDA and strategy analysis
│
└── .github/workflows/
    └── collect_data.yml        # Daily data collection automation
```

## Strategy: Chronograph Replication

The **Chronograph** strategy (as described in Dialectic's fund documentation) is a market-neutral USD-denominated yield strategy: deposit stablecoins across lending protocols, optimize allocation for maximum risk-adjusted return.

This project replicates that logic at a small scale:

- Capital deployed: ~$22 USDC on Aave v3 Arbitrum
- Benchmark: US T-Bill rate (~5% APY)
- Goal: understand how APY, utilization rate and TVL interact — and build the monitoring infrastructure that a professional operator needs

## Metrics Tracked

| Metric | Why It Matters |
|---|---|
| APY (base + reward) | Raw yield available to depositors |
| Utilization Rate | % of liquidity borrowed — drives APY |
| TVL | Size and health of the protocol |
| APY spread vs benchmark | Are we beating the risk-free rate? |
| Anomaly score | Is something structurally wrong? |

## ML Component: Anomaly Detection

An Isolation Forest model runs daily on the collected time series. It flags anomalous combinations of APY, TVL and utilization rate — the early warning signal that a protocol may be under stress or exploited.

This mirrors the kind of risk monitoring that institutional DeFi operators run internally to protect capital from smart contract exploits and liquidity crises.

## Stack

- **Python** — Pandas, Requests, Scikit-learn
- **DefiLlama API** — free, no API key required
- **GitHub Actions** — automated daily data collection
- **Streamlit** — live dashboard

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/REPO_NAME
cd REPO_NAME
pip install -r requirements.txt
python pipeline/aave_tracker.py
```

## Context

This project was built as part of a practical study of institutional DeFi strategy management, specifically to understand how operators like Dialectic monitor and optimize yield strategies on infrastructure like [Makina](https://dialectic.ky/editorial/the-makina-blue-chip-thesis).

---

*Data is collected automatically every day via GitHub Actions. The dataset grows over time and feeds the anomaly detection model.*
