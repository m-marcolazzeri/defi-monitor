"""
app.py
------
Streamlit dashboard for monitoring stablecoin yield strategies on Arbitrum.

Tabs:
  Overview    — all protocols, APY/TVL/utilization charts
  USDC        — USDC-only view
  USDT        — USDT-only view
  DAI         — DAI-only view
  Risk        — protocol risk classification (green/yellow/red)
  Advisor     — rebalancing recommendations
  Anomalies   — Isolation Forest anomaly detection results

Run locally:
    streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

st.set_page_config(page_title="DeFi Strategy Monitor", page_icon="📊", layout="wide")

# ── File paths ────────────────────────────────────────────────────────────────

DATA_FILE        = "data/multi_protocol.csv"
ANOMALIES_FILE   = "data/anomalies.csv"
RISK_FILE        = "data/risk_labels.csv"
ADVISOR_FILE     = "data/rebalancing_recommendations.csv"
BENCHMARK_APY    = 5.0   # US T-Bill rate

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def latest_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    group_key = ["pool_id"] if "pool_id" in df.columns else ["protocol", "symbol"]
    return (
        df.sort_values("timestamp")
        .groupby(group_key)
        .last()
        .reset_index()
        .sort_values("apy_total", ascending=False)
    )


def fmt_util(val) -> str:
    """Format utilization rate safely — handles None and NaN."""
    try:
        if val is None or (isinstance(val, float) and val != val):
            return "N/A"
        return f"{float(val)*100:.1f}%"
    except Exception:
        return "N/A"


# ── Chart helpers ─────────────────────────────────────────────────────────────

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
    df_plot = df.copy()
    if "utilization_source" in df_plot.columns:
        df_plot = df_plot[df_plot["utilization_source"] == "onchain"]
    if df_plot.empty:
        st.info("No on-chain utilization data available for this selection.")
        return
    fig = px.line(
        df_plot, x="timestamp", y="utilization_rate",
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
    snap = snap[snap["utilization_rate"].notna()].copy()
    if snap.empty:
        st.info("No data with utilization rate available.")
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


def tvl_chart(df: pd.DataFrame, title: str):
    fig = px.area(
        df, x="timestamp", y="tvl_usd",
        color="protocol",
        title=title,
        labels={"tvl_usd": "TVL (USD)", "timestamp": "Date"},
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Tab renderers ─────────────────────────────────────────────────────────────

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
            st.caption(f"Util: {fmt_util(row.get('utilization_rate'))}  |  TVL: ${row['tvl_usd']/1e6:.1f}M")


def render_market_tab(df: pd.DataFrame, label: str):
    st.subheader(f"Current snapshot — {label}")
    render_metrics(df)
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        apy_chart(df, f"APY over time — {label}")
    with c2:
        utilization_chart(df, f"Utilization rate — {label}")
    st.divider()
    tvl_chart(df, f"TVL over time — {label}")
    st.divider()
    st.caption("Best position: top-left (high APY, low utilization).")
    scatter_chart(df, f"Risk vs yield — {label}")


def render_risk_tab(df_risk: pd.DataFrame):
    st.subheader("Protocol Risk Classification")
    st.caption(
        "Each protocol is evaluated against objective, verifiable criteria. "
        "No arbitrary weights — each flag is independently justified."
    )

    if df_risk.empty:
        st.info("No risk data found. Run `python models/risk_classifier.py` first.")
        return

    icons = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    label_order = {"red": 0, "yellow": 1, "green": 2}
    df_sorted = df_risk.sort_values("risk_label", key=lambda x: x.map(label_order))

    counts = df_risk["risk_label"].value_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("🟢 Green", counts.get("green", 0))
    c2.metric("🟡 Yellow", counts.get("yellow", 0))
    c3.metric("🔴 Red", counts.get("red", 0))

    st.divider()

    for label in ["red", "yellow", "green"]:
        subset = df_sorted[df_sorted["risk_label"] == label]
        if subset.empty:
            continue
        icon = icons[label]
        st.markdown(f"### {icon} {label.capitalize()}")
        for _, row in subset.iterrows():
            with st.expander(f"{row['protocol']} — {row['symbol']}  |  APY: {row['apy_total']:.2f}%  |  TVL: ${row['tvl_usd']:,.0f}"):
                st.write(f"**Flags:** {row.get('risk_flags', 'none')}")
                if "protocol_type" in row:
                    st.write(f"**Type:** {row['protocol_type']}")


def render_advisor_tab(df_all: pd.DataFrame, df_risk: pd.DataFrame):
    st.subheader("Rebalancing Advisor")
    st.caption(
        "Calculates whether moving capital from your current position to a higher-yielding "
        "alternative makes financial sense after accounting for gas costs. "
        "Only 🟢 green-rated protocols are considered as targets."
    )

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        capital = st.number_input("Capital deployed (USD)", min_value=1.0, value=19.61, step=1.0)
    with col2:
        horizon = st.number_input("Holding period (days)", min_value=1, value=30, step=1)
    with col3:
        gas_cost = st.number_input("Gas cost per round trip (USD)", min_value=0.01, value=0.40, step=0.05)

    protocols = sorted(df_all["protocol"].unique())
    symbols   = sorted(df_all["symbol"].unique())

    col4, col5 = st.columns(2)
    with col4:
        current_protocol = st.selectbox("Current protocol", protocols, index=protocols.index("aave-v3") if "aave-v3" in protocols else 0)
    with col5:
        current_symbol = st.selectbox("Current token", symbols, index=symbols.index("USDC") if "USDC" in symbols else 0)

    # Get current APY
    snap = latest_snapshot(df_all)
    current_rows = snap[(snap["protocol"] == current_protocol) & (snap["symbol"] == current_symbol)]

    if current_rows.empty:
        st.warning("No data found for selected protocol/token.")
        return

    current_apy = current_rows.iloc[0]["apy_total"]
    st.info(f"Current position: **{current_protocol} {current_symbol}** — APY **{current_apy:.2f}%**")

    # Merge risk labels
    if not df_risk.empty:
        merge_key = ["pool_id"] if "pool_id" in snap.columns and "pool_id" in df_risk.columns else ["protocol", "symbol"]
        snap = snap.merge(df_risk[merge_key + ["risk_label"]], on=merge_key, how="left")
    else:
        snap["risk_label"] = "unknown"

    # Find candidates
    MIN_IMPROVEMENT = 0.25
    candidates = snap[
        (snap["symbol"] == current_symbol) &
        (snap["risk_label"] == "green") &
        (snap["apy_total"] > current_apy + MIN_IMPROVEMENT) &
        (snap["protocol"] != current_protocol)
    ].copy()

    st.divider()

    if candidates.empty:
        st.success(
            f"✅ No better alternative available right now. "
            f"No green-rated protocol offers more than {current_apy + MIN_IMPROVEMENT:.2f}% on {current_symbol}."
        )
        return

    candidates["apy_improvement"]  = candidates["apy_total"] - current_apy
    candidates["gross_gain_usd"]   = candidates["apy_improvement"] / 100 * capital * horizon / 365
    candidates["net_benefit_usd"]  = candidates["gross_gain_usd"] - gas_cost
    candidates["breakeven_days"]   = (gas_cost / (candidates["apy_improvement"] / 100 * capital / 365)).round(1)
    candidates["recommendation"]   = candidates["net_benefit_usd"].apply(lambda x: "MOVE" if x > 0 else "WAIT")

    for _, row in candidates.sort_values("net_benefit_usd", ascending=False).iterrows():
        action = "✅ MOVE" if row["recommendation"] == "MOVE" else "⏳ WAIT"
        with st.expander(f"{action} → {row['protocol']} {row['symbol']}  |  APY: {row['apy_total']:.2f}% (+{row['apy_improvement']:.2f}%)"):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Gross gain", f"${row['gross_gain_usd']:.4f}")
            c2.metric("Gas cost", f"${gas_cost:.2f}")
            c3.metric("Net benefit", f"${row['net_benefit_usd']:.4f}")
            c4.metric("Breakeven", f"{row['breakeven_days']} days")
            st.caption(f"TVL: ${row['tvl_usd']:,.0f}  |  Risk: {row['risk_label']}")


# ── Main layout ───────────────────────────────────────────────────────────────

st.title("📊 DeFi Strategy Monitor")
st.markdown(
    "Monitoring system for market-neutral stablecoin yield strategies — "
    "replicating [Dialectic's Chronograph fund](https://dialectic.ky) approach."
)
st.caption(f"Benchmark: US T-Bill {BENCHMARK_APY}%")
st.divider()

df_all       = load_csv(DATA_FILE)
df_anomalies = load_csv(ANOMALIES_FILE)
df_risk      = load_csv(RISK_FILE)

if df_all.empty:
    st.warning("No data found. Run `python pipeline/multi_protocol.py` first.")
    st.stop()

st.caption(f"Last updated: {df_all['timestamp'].max()}")

tabs = st.tabs([
    "🌐 Overview", "🔵 USDC", "🟢 USDT", "🟡 DAI",
    "🛡️ Risk", "💡 Advisor", "🚨 Anomalies"
])

with tabs[0]:
    render_market_tab(df_all, "All protocols")

with tabs[1]:
    render_market_tab(df_all[df_all["symbol"].isin(["USDC", "USDC.e"])], "USDC")

with tabs[2]:
    render_market_tab(df_all[df_all["symbol"] == "USDT"], "USDT")

with tabs[3]:
    render_market_tab(df_all[df_all["symbol"] == "DAI"], "DAI")

with tabs[4]:
    render_risk_tab(df_risk)

with tabs[5]:
    render_advisor_tab(df_all, df_risk)

with tabs[6]:
    st.subheader("Anomaly Detection")
    st.caption(
        "Isolation Forest flags unusual combinations of APY, TVL and utilization rate. "
        "Trained on day-over-day percentage changes — sudden outflows, APY spikes "
        "and extreme utilization are the main signals."
    )
    if df_anomalies.empty:
        st.info("No anomalies detected — or the model has not been run yet.")
    else:
        st.warning(f"⚠️ {len(df_anomalies)} anomalies detected in the historical dataset")
        cols_to_show = [c for c in [
            "timestamp", "protocol", "symbol", "apy_total",
            "tvl_usd", "utilization_rate", "anomaly_score"
        ] if c in df_anomalies.columns]
        st.dataframe(
            df_anomalies[cols_to_show].sort_values("anomaly_score").head(10),
            use_container_width=True,
        )

st.divider()
st.caption(
    "Data: [DefiLlama](https://defillama.com) + Aave v3 & Compound v3 on-chain (Web3.py) · "
    "Updated daily via GitHub Actions · "
    f"Live at [defi-monitor-iymn.onrender.com](https://defi-monitor-iymn.onrender.com)"
)
