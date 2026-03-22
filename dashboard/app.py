"""
app.py
------
Streamlit dashboard for monitoring stablecoin yield strategies on Arbitrum.

Run locally:
    streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="DeFi Strategy Monitor", page_icon="📊", layout="wide")

DATA_FILE      = "data/multi_protocol.csv"
ANOMALIES_FILE = "data/anomalies.csv"
BENCHMARK_APY  = 5.0  # US T-Bill rate


@st.cache_data(ttl=3600)
def load_data(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.sort_values("timestamp")
        .groupby(["protocol", "symbol"])
        .last()
        .reset_index()
        .sort_values("apy_total", ascending=False)
    )


def render_metrics(df: pd.DataFrame):
    snap = latest_snapshot(df)
    if snap.empty:
        st.info("No data available.")
        return
    cols = st.columns(min(len(snap), 4))
    for i, (_, row) in enumerate(snap.iterrows()):
        with cols[i % 4]:
            st.metric(
                label=f"{row['protocol']} — {row['symbol']}",
                value=f"{row['apy_total']:.2f}%",
                delta=f"{row['apy_total'] - BENCHMARK_APY:+.2f}% vs T-Bill",
            )
            st.caption(
                f"Util: {row['utilization_rate']*100:.1f}%  |  "
                f"TVL: ${row['tvl_usd']/1e6:.1f}M"
            )


def apy_chart(df: pd.DataFrame, title: str):
    fig = px.line(
        df, x="timestamp", y="apy_total",
        color="protocol", line_dash="symbol",
        title=title,
        labels={"apy_total": "APY (%)", "timestamp": "Date"},
    )
    fig.add_hline(
        y=BENCHMARK_APY, line_dash="dash", line_color="gray",
        annotation_text=f"T-Bill {BENCHMARK_APY}%",
        annotation_position="bottom right",
    )
    st.plotly_chart(fig, use_container_width=True)


def utilization_chart(df: pd.DataFrame, title: str):
    # Only plot on-chain readings to avoid DefiLlama artifacts
    if "utilization_source" in df.columns:
        df = df[df["utilization_source"] == "onchain"]
    fig = px.line(
        df, x="timestamp", y="utilization_rate",
        color="protocol", line_dash="symbol",
        title=title,
        labels={"utilization_rate": "Utilization Rate", "timestamp": "Date"},
    )
    fig.add_hline(
        y=0.90, line_dash="dash", line_color="red",
        annotation_text="Risk threshold (90%)",
        annotation_position="bottom right",
    )
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)


def scatter_chart(df: pd.DataFrame, title: str):
    snap = latest_snapshot(df)
    if snap.empty:
        return
    snap["label"] = snap["protocol"] + " " + snap["symbol"]
    fig = px.scatter(
        snap,
        x="utilization_rate", y="apy_total",
        size="tvl_usd", color="protocol", text="label",
        title=title,
        labels={
            "utilization_rate": "Utilization Rate (liquidity risk)",
            "apy_total": "APY (%)",
        },
    )
    fig.update_xaxes(tickformat=".0%")
    fig.add_hline(y=BENCHMARK_APY, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, use_container_width=True)


def render_tab(df: pd.DataFrame, label: str):
    st.subheader(f"Current snapshot — {label}")
    render_metrics(df)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        apy_chart(df, f"APY over time — {label}")
    with c2:
        utilization_chart(df, f"Utilization rate — {label}")
    st.divider()
    st.caption("Best position: top-left (high APY, low utilization).")
    scatter_chart(df, f"Risk vs yield — {label}")


# ── Layout ────────────────────────────────────────────────────────────────────

st.title("📊 DeFi Strategy Monitor")
st.markdown(
    "Monitoring system for market-neutral stablecoin yield strategies — "
    "replicating [Dialectic's Chronograph fund](https://dialectic.ky) approach."
)
st.caption(f"Benchmark: US T-Bill {BENCHMARK_APY}%")
st.divider()

df_all       = load_data(DATA_FILE)
df_anomalies = load_data(ANOMALIES_FILE)

if df_all.empty:
    st.warning("No data found. Run `python pipeline/multi_protocol.py` first.")
    st.stop()

st.caption(f"Last updated: {df_all['timestamp'].max()}")

tab_all, tab_usdc, tab_usdt, tab_dai, tab_anomalies = st.tabs([
    "🌐 Overview", "🔵 USDC", "🟢 USDT", "🟡 DAI", "🚨 Anomalies"
])

with tab_all:
    render_tab(df_all, "All protocols")

with tab_usdc:
    render_tab(df_all[df_all["symbol"].isin(["USDC", "USDC.e"])], "USDC")

with tab_usdt:
    render_tab(df_all[df_all["symbol"] == "USDT"], "USDT")

with tab_dai:
    render_tab(df_all[df_all["symbol"] == "DAI"], "DAI")

with tab_anomalies:
    st.subheader("Anomaly Detection")
    st.caption(
        "Isolation Forest flags unusual combinations of APY, TVL and utilization rate. "
        "Requires at least 7–10 days of historical data."
    )
    if df_anomalies.empty:
        st.info("No anomalies detected — or the model has not been run yet.\n\n"
                "```bash\npython models/anomaly_detector.py\n```")
    else:
        st.warning(f"⚠️ {len(df_anomalies)} anomalies detected")
        st.dataframe(
            df_anomalies[[
                "timestamp", "protocol", "symbol",
                "apy_total", "tvl_usd", "utilization_rate", "anomaly_score"
            ]].sort_values("anomaly_score").head(10),
            use_container_width=True,
        )

st.divider()
st.caption(
    "Data: [DefiLlama](https://defillama.com) + Aave v3 on-chain (Web3.py) · "
    "Updated daily via GitHub Actions"
)
