# defi-monitor

A data pipeline and ML system for monitoring stablecoin yield strategies across DeFi lending protocols on Arbitrum.

Tracks APY, TVL and utilization rate daily, runs anomaly detection to flag unusual protocol behavior, and visualizes everything in a live dashboard. Built to study how institutional DeFi operators like [Dialectic](https://dialectic.ky) monitor and optimize yield strategies.

## Architecture

```
DefiLlama API  ─┐
                ├─▶  pipeline/multi_protocol.py  ─▶  data/multi_protocol.csv
Aave v3 RPC   ─┘                                          │
                                                           ▼
                                               models/anomaly_detector.py
                                                           │
                                                           ▼
                                               dashboard/app.py  (Streamlit)
```

GitHub Actions runs the pipeline daily at 09:00 UTC and commits new data automatically.

## Structure

```
defi-monitor/
├── pipeline/
│   └── multi_protocol.py       # Data collection: DefiLlama + on-chain Web3
├── models/
│   └── anomaly_detector.py     # Isolation Forest on APY, TVL, utilization rate
├── dashboard/
│   └── app.py                  # Streamlit dashboard
├── web3_utils.py               # Aave v3 on-chain data reader
├── data/                       # Auto-updated CSVs (via GitHub Actions)
└── .github/workflows/
    └── collect_data.yml
```

## Quickstart

```bash
git clone https://github.com/m-marcolazzeri/defi-monitor
cd defi-monitor
pip install -r requirements.txt
python pipeline/multi_protocol.py
streamlit run dashboard/app.py
```

## Metrics

| Metric | Description |
|---|---|
| `apy_total` | Annualized yield for depositors (base + rewards) |
| `utilization_rate` | Share of available liquidity currently borrowed |
| `tvl_usd` | Total capital deposited in the protocol |
| `anomaly_score` | Isolation Forest score — more negative = more anomalous |

## Stack

Python · Pandas · Scikit-learn · Web3.py · Streamlit · Plotly · DefiLlama API · GitHub Actions
