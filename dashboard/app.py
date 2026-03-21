"""
DeFi Strategy Monitor — Dashboard
------------------------------------
Dashboard interattiva con:
- Vista panoramica: tutti i token e protocolli insieme
- Tabs separate per USDC, USDT, DAI
- Anomaly detection results

ESECUZIONE LOCALE:
    streamlit run dashboard/app.py
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import os

# ─── Config ───────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="DeFi Strategy Monitor",
    page_icon="📊",
    layout="wide"
)

MULTI_PROTOCOL_FILE = "data/multi_protocol.csv"
ANOMALIES_FILE      = "data/anomalies.csv"
RISK_FREE_RATE      = 5.0


# ─── Data Loading ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_multi_protocol():
    if not os.path.exists(MULTI_PROTOCOL_FILE):
        return pd.DataFrame()
    df = pd.read_csv(MULTI_PROTOCOL_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data(ttl=3600)
def load_anomalies():
    if not os.path.exists(ANOMALIES_FILE):
        return pd.DataFrame()
    df = pd.read_csv(ANOMALIES_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ─── Helpers ──────────────────────────────────────────────────────────────────

def render_snapshot(df):
    latest = (
        df.sort_values("timestamp")
        .groupby(["protocol", "symbol"])
        .last()
        .reset_index()
        .sort_values("apy_total", ascending=False)
    )
    if latest.empty:
        st.info("Nessun dato disponibile.")
        return
    cols = st.columns(min(len(latest), 4))
    for i, (_, row) in enumerate(latest.iterrows()):
        with cols[i % 4]:
            delta = row["apy_total"] - RISK_FREE_RATE
            st.metric(
                label=f"{row['protocol']} — {row['symbol']}",
                value=f"{row['apy_total']:.2f}%",
                delta=f"{delta:+.2f}% vs T-Bill"
            )
            st.caption(
                f"Util: {row['utilization_rate']*100:.1f}% | "
                f"TVL: ${row['tvl_usd']/1e6:.1f}M"
            )


def render_apy_chart(df, title):
    fig = px.line(
        df, x="timestamp", y="apy_total",
        color="protocol", line_dash="symbol",
        title=title,
        labels={"apy_total": "APY (%)", "timestamp": "Data"}
    )
    fig.add_hline(
        y=RISK_FREE_RATE, line_dash="dash", line_color="gray",
        annotation_text=f"T-Bill {RISK_FREE_RATE}%",
        annotation_position="bottom right"
    )
    st.plotly_chart(fig, use_container_width=True)


def render_utilization_chart(df, title):
    if "utilization_source" in df.columns:
        df = df[df["utilization_source"] == "onchain"]
    fig = px.line(
        df, x="timestamp", y="utilization_rate",
        color="protocol", line_dash="symbol",
        title=title,
        labels={"utilization_rate": "Utilization Rate", "timestamp": "Data"}
    )
    fig.add_hline(
        y=0.90, line_dash="dash", line_color="red",
        annotation_text="Soglia rischio (90%)",
        annotation_position="bottom right"
    )
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)


def render_scatter(df, title):
    latest = (
        df.sort_values("timestamp")
        .groupby(["protocol", "symbol"])
        .last()
        .reset_index()
    )
    if latest.empty:
        return
    latest["label"] = latest["protocol"] + " " + latest["symbol"]
    fig = px.scatter(
        latest,
        x="utilization_rate", y="apy_total",
        size="tvl_usd", color="protocol", text="label",
        title=title,
        labels={
            "utilization_rate": "Utilization Rate (rischio)",
            "apy_total": "APY (%)"
        }
    )
    fig.update_xaxes(tickformat=".0%")
    fig.add_hline(y=RISK_FREE_RATE, line_dash="dash", line_color="gray")
    st.plotly_chart(fig, use_container_width=True)


def render_tab(df, label):
    st.subheader(f"📍 Snapshot {label}")
    render_snapshot(df)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        render_apy_chart(df, f"APY — {label} su Arbitrum")
    with col2:
        render_utilization_chart(df, f"Utilization Rate — {label}")
    st.divider()
    st.caption("Il protocollo ideale è in alto a sinistra: alto APY, bassa utilization rate.")
    render_scatter(df, f"Risk vs Yield — {label}")


# ─── Header ───────────────────────────────────────────────────────────────────

st.title("📊 DeFi Strategy Monitor")
st.markdown(
    "Monitoring system for market-neutral stablecoin yield strategies — "
    "replicating [Dialectic's Chronograph fund](https://dialectic.ky) approach."
)
st.caption(f"Benchmark: T-Bill USA {RISK_FREE_RATE}%")
st.divider()

df_all = load_multi_protocol()
df_anomalies = load_anomalies()

if df_all.empty:
    st.warning("Nessun dato trovato. Esegui prima: `python pipeline/multi_protocol.py`")
    st.stop()

st.caption(f"Ultimo aggiornamento: {df_all['timestamp'].max()}")

# ─── Tabs ─────────────────────────────────────────────────────────────────────

tab_overview, tab_usdc, tab_usdt, tab_dai, tab_anomalie = st.tabs([
    "🌐 Panoramica", "🔵 USDC", "🟢 USDT", "🟡 DAI", "🚨 Anomalie"
])

with tab_overview:
    render_tab(df_all, "Tutti i Protocolli")

with tab_usdc:
    render_tab(df_all[df_all["symbol"].isin(["USDC", "USDC.e"])], "USDC")

with tab_usdt:
    render_tab(df_all[df_all["symbol"] == "USDT"], "USDT")

with tab_dai:
    render_tab(df_all[df_all["symbol"] == "DAI"], "DAI")

with tab_anomalie:
    st.subheader("🚨 Anomaly Detection")
    st.caption(
        "Isolation Forest rileva combinazioni anomale di APY, TVL e utilization rate. "
        "Serve almeno 1 settimana di dati storici."
    )
    if df_anomalies.empty:
        st.info(
            "Nessuna anomalia rilevata — oppure il modello non è ancora stato eseguito.\n\n"
            "```bash\npython models/anomaly_detector.py\n```"
        )
    else:
        st.warning(f"⚠️ {len(df_anomalies)} anomalie rilevate")
        st.dataframe(
            df_anomalies[[
                "timestamp", "protocol", "symbol",
                "apy_total", "tvl_usd", "utilization_rate", "anomaly_score"
            ]].sort_values("anomaly_score").head(10),
            use_container_width=True
        )

st.divider()
st.caption(
    "Data source: [DefiLlama](https://defillama.com) + Aave v3 on-chain (Web3.py) · "
    "Updated daily via GitHub Actions · "
    "Built to study institutional DeFi strategy management"
)
