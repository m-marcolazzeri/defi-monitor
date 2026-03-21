# DeFi Strategy Monitor

A data engineering and ML system for monitoring institutional-grade stablecoin yield strategies across DeFi lending protocols on Arbitrum.

## What it does

This project tracks, compares and analyzes market-neutral yield opportunities on stablecoins across multiple DeFi protocols. It collects APY, TVL and utilization rate data daily, runs an anomaly detection model to flag unusual behavior, and visualizes everything in a live dashboard.

The core question it tries to answer is: given a pool of stablecoin capital, where is the best risk-adjusted yield right now, and is anything going wrong?

## Project structure

```
defi-monitor/
├── pipeline/
│   └── multi_protocol.py       # Daily data collection from DefiLlama API
├── models/
│   └── anomaly_detector.py     # Isolation Forest on APY, TVL and utilization rate
├── dashboard/
│   └── app.py                  # Streamlit dashboard
├── data/                       # CSV files, auto-updated daily via GitHub Actions
├── notebooks/                  # Exploratory analysis
└── .github/workflows/
    └── collect_data.yml        # Automation
```

## How it works

The pipeline fetches data from the [DefiLlama API](https://defillama.com) and stores it as a growing CSV dataset. GitHub Actions runs the pipeline every day at 9:00 UTC and commits the new data automatically.

The anomaly detector uses Isolation Forest to learn what "normal" looks like across APY, TVL and utilization rate, and flags observations that deviate significantly. Sudden TVL drops, APY spikes and extreme utilization rates are the main signals it looks for.

The dashboard lets you compare protocols side by side, track metrics over time and see which anomalies have been flagged.

## Getting started

```bash
git clone https://github.com/m-marcolazzeri/defi-monitor
cd defi-monitor
pip install -r requirements.txt
python pipeline/multi_protocol.py
```

To run the dashboard locally:

```bash
streamlit run dashboard/app.py
```

## Stack

Python, Pandas, Scikit-learn, Streamlit, Plotly, GitHub Actions, DefiLlama API.

## Metrics tracked

| Metric | Description |
|---|---|
| APY (base + reward) | Total annualized yield for depositors |
| Utilization rate | Share of available liquidity that has been borrowed |
| TVL | Total capital deposited in the protocol |
| APY vs benchmark | Spread over the US T-Bill rate |
| Anomaly score | Model output flagging structural anomalies |
